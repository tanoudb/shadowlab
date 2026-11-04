"""Protections applicatives de l'Arena : défi JavaScript et CAPTCHA, selon le profil de la session.

Elles ne s'appliquent qu'aux requêtes arrivées par le frontal (sceau valide). Le site servi en direct reste sans
protection : c'est la référence `aucune`. Chaque décision est enregistrée avec ses motifs.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from urllib.parse import urlsplit

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

from .. import database as db
from ..arena import defis, profils
from ..arena import secret as secrets_arena
from ..detection import Observations, Signal, registre
from . import pages

COOKIE_DEFI = "sl_defi"
COOKIE_CAPTCHA = "sl_captcha"
COOKIE_TURNSTILE = "sl_turnstile"
COOKIE_RECAPTCHA = "sl_recaptcha"
# Échanges techniques du laboratoire et des protections : ils ne sont pas des pages à protéger.
HORS_PROTECTION = (
    "/lab/static",
    "/lab/collecte",
    "/lab/verdict",
    "/lab/defi",
    "/lab/captcha",
    "/lab/piege",
    "/lab/turnstile",
    "/lab/recaptcha",
)
# Règles consultées en direct : celles qui peuvent trancher dès la requête, puis celles qui lisent le JavaScript.
REGLES_REQUETE = ("regles-http", "tls")
REGLES_JAVASCRIPT = ("botd", "regles-js", "coherence")


@dataclass(frozen=True)
class Sceau:
    observation: str
    profil: str
    session: str
    ja4: str
    lier_tls: bool


def lire_sceau(request: Request, secret: bytes) -> Sceau | None:
    """Vérifie que la requête vient bien du frontal, qui signe les en-têtes internes."""
    h = request.headers
    signature = h.get("x-shadowlab-sceau")
    if not signature:
        return None
    observation = h.get("x-shadowlab-obs", "")
    profil = h.get("x-shadowlab-profil", "")
    session = h.get("x-shadowlab-session", "")
    ja4 = h.get("x-shadowlab-ja4", "")
    if not secrets_arena.verifier(secret, signature, observation, profil, session, ja4):
        return None
    configuration = profils.charger().de(profil)
    lier = bool(configuration and configuration.defi_js.lier_tls)
    return Sceau(observation, profil, session, ja4, lier)


def empreinte_liee(sceau: Sceau) -> str:
    return sceau.ja4 if sceau.lier_tls else ""


def retour_sur(cible: str) -> str:
    """Seul un retour vers le site de test est accepté (pas de redirection ouverte)."""
    parties = urlsplit(cible)
    if parties.scheme or parties.netloc or not parties.path.startswith("/lab"):
        return "/lab/"
    return parties.path + (f"?{parties.query}" if parties.query else "")


def _refus(request: Request, html: str, code: str) -> Response:
    # Une navigation reçoit la page ; un client qui n'accepte pas le HTML reçoit le motif.
    if "text/html" in request.headers.get("accept", ""):
        return HTMLResponse(html, status_code=403, headers={"Cache-Control": "no-store"})
    return JSONResponse({"bloque_par": code}, status_code=403, headers={"Cache-Control": "no-store"})


def suspicion(cx: sqlite3.Connection, jeton: str, inclure_js: bool = True) -> list[dict]:
    """Motifs de suspicion connus à cet instant. Le JavaScript ne compte qu'une fois l'empreinte reçue."""
    http, js = db.observations(cx, jeton)
    observations = Observations(http=http, js=js, tls=db.tls_session(cx, jeton))
    noms = list(REGLES_REQUETE)
    if inclure_js and observations.empreinte_js is not None:
        noms += REGLES_JAVASCRIPT
    detecteurs = registre()
    motifs: list[dict] = []
    for nom in noms:
        classement = detecteurs[nom].classer(observations)
        if classement.classification == "automatise":
            motifs.append({"detecteur": nom, "signaux": [_signal(s) for s in classement.signals]})
    hp = cx.execute(
        "SELECT COUNT(*) FROM decisions WHERE session_token = ? AND couche = 'honeypot' AND decision = 'declenche'",
        (jeton,),
    ).fetchone()[0]
    if hp:
        motifs.append({"detecteur": "honeypot", "signaux": [{"code": "honeypot", "description": f"{hp} piège(s)"}]})
    return motifs


def _signal(s: Signal) -> dict:
    return {"code": s.code, "description": s.description}


def honeypots_actifs(sceau: Sceau | None) -> bool:
    """Les honeypots ne sont injectés que si le profil Arena les active."""
    if sceau is None:
        return False
    profil = profils.charger().de(sceau.profil)
    return bool(profil and profil.honeypots.actif)


def controler(
    request: Request, cx: sqlite3.Connection, secret: bytes, sceau: Sceau, jeton: str, chemin: str
) -> Response | None:
    """Renvoie la réponse de la protection qui s'applique, ou None si la requête peut passer."""
    if not chemin.startswith("/lab") or chemin.startswith(HORS_PROTECTION) or request.method != "GET":
        return None
    profil = profils.charger().de(sceau.profil)
    if profil is None:
        return None
    lie = empreinte_liee(sceau)
    if profil.defi_js.actif and not defis.cookie_valide(secret, "defi", request.cookies.get(COOKIE_DEFI), jeton, lie):
        defi = defis.creer_defi(secret, jeton, profil.defi_js.difficulte)
        motifs = [{"difficulte": profil.defi_js.difficulte}]
        db.enregistrer_decision(cx, jeton, "defi-js", "emis", chemin, motifs)
        cible = retour_sur(request.url.path + (f"?{request.url.query}" if request.url.query else ""))
        return _refus(request, pages.page_defi(defi, profil.defi_js.difficulte, cible), "defi-js")
    if profil.fingerprinting.actif:
        inclure_js = profil.fingerprinting.bloquer != "http"
        motifs = suspicion(cx, jeton, inclure_js=inclure_js)
        if motifs:
            if profil.fingerprinting.bloquer != "non":
                db.enregistrer_decision(cx, jeton, "fingerprinting", "bloque", chemin, motifs)
                return _refus(request, pages.page_blocage(), "fingerprinting")
            db.enregistrer_decision(cx, jeton, "fingerprinting", "suspect", chemin, motifs)
    if profil.turnstile.actif and not defis.cookie_valide(
        secret, "turnstile", request.cookies.get(COOKIE_TURNSTILE), jeton, lie
    ):
        db.enregistrer_decision(cx, jeton, "turnstile", "emis", chemin, [])
        cible = retour_sur(request.url.path + (f"?{request.url.query}" if request.url.query else ""))
        site_key = defis.turnstile_site_key("pass")
        reponse = _refus(request, pages.page_turnstile(site_key, cible), "turnstile")
        reponse.headers["X-ShadowLab-Turnstile"] = "1"
        return reponse
    if profil.recaptcha.actif and not defis.cookie_valide(
        secret, "recaptcha", request.cookies.get(COOKIE_RECAPTCHA), jeton, lie
    ):
        db.enregistrer_decision(cx, jeton, "recaptcha", "emis", chemin, [])
        cible = retour_sur(request.url.path + (f"?{request.url.query}" if request.url.query else ""))
        reponse = _refus(request, pages.page_recaptcha(defis.recaptcha_site_key(), cible), "recaptcha")
        reponse.headers["X-ShadowLab-Recaptcha"] = "1"
        return reponse
    if profil.captcha.actif and not defis.cookie_valide(
        secret, "captcha", request.cookies.get(COOKIE_CAPTCHA), jeton, lie
    ):
        motifs = suspicion(cx, jeton)
        if motifs:
            db.enregistrer_decision(cx, jeton, "captcha", "emis", chemin, motifs)
            cible = retour_sur(request.url.path + (f"?{request.url.query}" if request.url.query else ""))
            return _refus(request, pages.page_captcha(defis.creer_captcha(secret, jeton), cible), "captcha")
    return None
