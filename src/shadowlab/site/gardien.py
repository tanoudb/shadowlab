"""Protections applicatives de l'Arena : défi JavaScript et CAPTCHA, selon le profil de la session.

Elles ne s'appliquent qu'aux requêtes arrivées par le frontal (sceau valide). Le site servi en direct reste sans
protection : c'est la référence `aucune`. Chaque décision est enregistrée avec ses motifs.
"""

from __future__ import annotations

import base64
import sqlite3
from dataclasses import asdict, dataclass
from urllib.parse import urlsplit

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

from .. import correlation, scoring
from .. import database as db
from ..arena import adresses, bannissements, defis, profils, visiteurs
from ..arena import secret as secrets_arena
from ..detection import CHEMINS_TECHNIQUES, Detecteur, Observations, Signal, est_ressource_de_page, registre
from . import pages

COOKIE_DEFI = "sl_defi"
COOKIE_CAPTCHA = "sl_captcha"
COOKIE_TURNSTILE = "sl_turnstile"
COOKIE_RECAPTCHA = "sl_recaptcha"
COOKIE_CONNEXION = "sl_connexion"  # session authentifiée (niveau connexion)
# Le refus d'un banni (visiteur, empreinte, compte) dit son motif dans cet en-tête, pour une navigation comme pour une
# ressource : la page de refus, elle, ne change pas d'un octet. Pas de préfixe `X-ShadowLab-` : le frontal retire ces
# en-têtes internes avant de répondre (D-104).
ENTETE_REFUS = "X-Arena-Refus"
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
REGLES_JAVASCRIPT = ("botd", "regles-js", "coherence", "comportement")
# Les détecteurs HTTP fonctionnent sans empreinte JS ; les autres attendent l'empreinte.
DETECTEURS_HTTP = frozenset(REGLES_REQUETE)


@dataclass(frozen=True)
class Sceau:
    observation: str
    profil: str
    session: str
    ja4: str
    liaison: str
    lier_tls: bool
    adresse: str | None = (
        None  # l'adresse du visiteur, signée par le frontal (D-105) ; jamais celle d'un en-tête du client
    )


def _adresse_signee(h, secret: bytes, observation: str, session: str) -> str | None:
    """L'adresse que le frontal a signée pour CETTE requête, ou None (absente, mal signée, changée en route)."""
    adresse = h.get(adresses.ENTETE.lower())
    signature = h.get(adresses.ENTETE_SCEAU.lower())
    if not adresse or not signature or adresses.normaliser(adresse) != adresse:
        return None
    return adresse if adresses.verifier(secret, signature, observation, session, adresse) else None


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
    liaison = h.get("x-shadowlab-liaison", "")
    if not secrets_arena.verifier(secret, signature, observation, profil, session, ja4, liaison):
        return None
    configuration = profils.charger().de(profil)
    lier = bool(configuration and configuration.defi_js.lier_tls)
    return Sceau(observation, profil, session, ja4, liaison, lier, _adresse_signee(h, secret, observation, session))


def empreinte_liee(sceau: Sceau) -> str:
    """Empreinte de liaison (JA4 sans `pre_shared_key`) si le niveau lie les cookies au TLS, sinon rien."""
    return sceau.liaison if sceau.lier_tls else ""


def retour_sur(cible: str) -> str:
    """Seul un retour vers le site de test est accepté (pas de redirection ouverte)."""
    parties = urlsplit(cible)
    if parties.scheme or parties.netloc or not parties.path.startswith("/lab"):
        return "/lab/"
    return parties.path + (f"?{parties.query}" if parties.query else "")


def encoder_retour(cible: str) -> str:
    """Encode le retour en base64url pour les hidden fields des formulaires challenge.

    Le WAF CRS rule 932190 (paranoia ≥ 3) détecte le ``?`` de la query string comme un wildcard shell.
    """
    return base64.urlsafe_b64encode(retour_sur(cible).encode()).decode()


def decoder_retour(valeur: str) -> str:
    """Décode un retour base64url. Fallback sur la valeur brute si le décodage échoue."""
    try:
        return retour_sur(base64.urlsafe_b64decode(valeur.encode()).decode())
    except Exception:  # noqa: BLE001
        return retour_sur(valeur)


def _refus(request: Request, html: str, code: str) -> Response:
    # Une navigation reçoit la page ; un client qui n'accepte pas le HTML reçoit le motif.
    if "text/html" in request.headers.get("accept", ""):
        return HTMLResponse(html, status_code=403, headers={"Cache-Control": "no-store"})
    return JSONResponse({"bloque_par": code}, status_code=403, headers={"Cache-Control": "no-store"})


def suspicion(
    cx: sqlite3.Connection,
    jeton: str,
    inclure_js: bool = True,
    exclure: list[str] | None = None,
    detecteurs: list[str] | None = None,
    seuil_composite: float | None = None,
) -> list[dict]:
    """Motifs de suspicion connus à cet instant, d'après les observations en base (voir `motifs_suspicion`)."""
    http, js = db.observations(cx, jeton)
    observations = Observations(http=http, js=js, tls=db.tls_session(cx, jeton))
    observations.visite_neuve = correlation.visite_neuve(cx, jeton)
    if observations.empreinte_js is not None:
        observations.correlation = asdict(correlation.evaluer_session(cx, jeton))
    pieges = cx.execute(
        "SELECT COUNT(*) FROM decisions WHERE session_token = ? AND couche = 'honeypot' AND decision = 'declenche'",
        (jeton,),
    ).fetchone()[0]
    return motifs_suspicion(observations, pieges, inclure_js, exclure, detecteurs, seuil_composite)


def motifs_suspicion(
    observations: Observations,
    pieges: int = 0,
    inclure_js: bool = True,
    exclure: list[str] | None = None,
    detecteurs: list[str] | None = None,
    seuil_composite: float | None = None,
    tous: dict[str, Detecteur] | None = None,
) -> list[dict]:
    """Règle de décision de l'Arena, sans base : motifs pour ces observations et `pieges` pièges déclenchés.

    *detecteurs* : liste explicite de noms de détecteurs à consulter (depuis le profil Arena).
    Si absent ou vide, les constantes REGLES_REQUETE / REGLES_JAVASCRIPT s'appliquent.

    *seuil_composite* : si défini, les signaux faibles de détecteurs « indéterminés » sont
    cumulés. Si leur somme ≥ seuil_composite et qu'aucun détecteur individuel n'a bloqué,
    un motif synthétique « composite » est ajouté. Permet de détecter les moteurs bien patchés
    qui passent sous le seuil de chaque détecteur pris isolément.

    *tous* remplace le registre des détecteurs (le rejeu y retire les règles dont une session n'a pas la donnée).
    """
    if detecteurs:
        noms = [d for d in detecteurs if d in DETECTEURS_HTTP]
        if inclure_js and observations.empreinte_js is not None:
            noms += [d for d in detecteurs if d not in DETECTEURS_HTTP]
    else:
        noms = list(REGLES_REQUETE)
        if inclure_js and observations.empreinte_js is not None:
            noms += REGLES_JAVASCRIPT
    if exclure:
        noms = [n for n in noms if n not in exclure]
    tous = registre() if tous is None else tous
    motifs: list[dict] = []
    signaux_par_detecteur: list[tuple[str, list[Signal]]] = []
    for nom in noms:
        classement = tous[nom].classer(observations)
        if classement.classification == "automatise":
            motifs.append({"detecteur": nom, "signaux": [_signal(s) for s in classement.signals]})
        elif classement.signals:
            positifs = [s for s in classement.signals if s.poids > 0]
            if positifs:
                signaux_par_detecteur.append((nom, positifs))
    if seuil_composite is not None and not motifs and signaux_par_detecteur:
        score = scoring.score_signaux(signaux_par_detecteur)
        if score >= seuil_composite:
            tous_signaux = [s for _, sigs in signaux_par_detecteur for s in sigs]
            motifs.append(
                {
                    "detecteur": "composite",
                    "score": score,
                    "signaux": [_signal(s) for s in tous_signaux],
                }
            )
    if pieges:
        motifs.append({"detecteur": "honeypot", "signaux": [{"code": "honeypot", "description": f"{pieges} piège(s)"}]})
    return motifs


def parametres(profil: profils.Profil) -> dict:
    """Réglages de `suspicion` pour ce profil, les mêmes à la réception d'une empreinte (/lab/collecte) et à
    chaque page contrôlée : un détecteur exclu, ou le JavaScript en `bloquer: http`, ne décide nulle part."""
    f = profil.fingerprinting
    return {
        "inclure_js": f.bloquer != "http",
        "exclure": f.exclure or None,
        "detecteurs": f.detecteurs or None,
        "seuil_composite": f.seuil_composite,
    }


def protegee(chemin: str, methode: str) -> bool:
    """Requête que `controler` examine : une page du site de test en GET, hors échanges techniques.

    Les photos en font partie (D-78) : une photo d'annonce porte du contenu (ville, titre), l'exempter laisserait un
    client bloqué ou jamais contrôlé la lire. C'est le compte des pages du détecteur qui est corrigé, pas la protection.
    """
    return chemin.startswith("/lab") and not chemin.startswith(HORS_PROTECTION) and methode == "GET"


def _signal(s: Signal) -> dict:
    return {"code": s.code, "description": s.description}


def _composite_differe(cx: sqlite3.Connection, jeton: str) -> bool:
    """Une collecte JS a-t-elle déjà détecté un score composite au-dessus du seuil ?"""
    row = cx.execute(
        "SELECT 1 FROM decisions WHERE session_token = ? AND couche = 'composite-differe' LIMIT 1",
        (jeton,),
    ).fetchone()
    return row is not None


def _fingerprinting_differe(cx: sqlite3.Connection, jeton: str) -> bool:
    """Une collecte JS a-t-elle détecté un détecteur individuel « automatise » ?"""
    row = cx.execute(
        "SELECT 1 FROM decisions WHERE session_token = ? AND couche = 'fingerprinting-differe' LIMIT 1",
        (jeton,),
    ).fetchone()
    return row is not None


def honeypots_actifs(sceau: Sceau | None) -> bool:
    """Les honeypots ne sont injectés que si le profil Arena les active."""
    if sceau is None:
        return False
    profil = profils.charger().de(sceau.profil)
    return bool(profil and profil.honeypots.actif)


def portee_defi(profil: profils.Profil, jeton: str, monde: str, visiteur: str | None) -> tuple[str, str | None]:
    """(usage, clé) du cookie de réussite du défi : le jeton de session, ou le visiteur du monde (`par_visiteur`).

    Un cookie lié au visiteur ne vaut que pour lui, dans son monde ; sans visiteur connu (première requête d'un
    navigateur neuf) il n'y a rien à lier : la clé est None, aucun cookie n'est valable et le défi est émis.
    """
    if profil.defi_js.par_visiteur:
        return "defi-visiteur", f"{monde}:{visiteur}" if visiteur else None
    return "defi", jeton


def refus_banni(request: Request, cx: sqlite3.Connection, jeton: str, chemin: str, verdict: bannissements.Verdict):
    """403 d'un banni (visiteur, empreinte ou compte), avec sa décision (`bannissement`, `bloque`) pour que le passage
    en garde la cause, et l'en-tête `ENTETE_REFUS` qui dit le motif au navigateur (la page reste celle de toujours)."""
    motif = {"detecteur": "bannissement", "motif": verdict.motif, "par": verdict.par}
    if verdict.compte is not None:
        motif["compte"] = verdict.compte
    db.enregistrer_decision(cx, jeton, "bannissement", "bloque", chemin, [motif])
    reponse = _refus(request, pages.page_blocage(), "bannissement")
    reponse.headers[ENTETE_REFUS] = "bannissement"
    return reponse


def _est_une_page(chemin: str) -> bool:
    """Une requête de page au sens de D-78 (pas une photo, une ressource ni un échange technique)."""
    return not chemin.startswith(CHEMINS_TECHNIQUES) and not est_ressource_de_page(chemin)


def bannir_si_arret(
    cx: sqlite3.Connection,
    surveillance: bannissements.Surveillance,
    secret: bytes,
    request: Request,
    profil: profils.Profil,
    jeton: str,
    motifs: list[dict],
) -> None:
    """Le gardien arrête la session pour suspicion : si le profil bannit, son visiteur et son empreinte sont bannis."""
    if profil.bannissement.actif and profil.fingerprinting.bloquer != "non":
        detecteurs = [str(m.get("detecteur", "")) for m in motifs if m.get("detecteur")]
        surveillance.bannir_detection(cx, secret, request.cookies.get(visiteurs.COOKIE), jeton, detecteurs)


def apres_empreinte(
    cx: sqlite3.Connection,
    surveillance: bannissements.Surveillance,
    secret: bytes,
    request: Request,
    profil: profils.Profil,
    jeton: str,
    motifs: list[dict],
    page: str,
) -> None:
    """À la réception d'une empreinte JS, pour un profil qui bannit.

    - un automate révélé par l'empreinte est banni tout de suite (visiteur et E) : un scénario d'une seule page ne
      redemande jamais de page, l'arrêt « à la page suivante » n'arriverait pas et le passage suivant n'aurait rien ;
    - sinon, une session **neuve** dont E est déjà bannie dans le monde est refusée (décision `bannissement`) et son
      visiteur banni à son tour. Un visiteur connu qui porte la même E n'est pas touché.
    """
    if not profil.bannissement.actif:
        return
    if motifs and profil.fingerprinting.bloquer != "non":
        bannir_si_arret(cx, surveillance, secret, request, profil, jeton, motifs)
        return
    cookie = request.cookies.get(visiteurs.COOKIE)
    verdict = surveillance.juger(cx, secret, cookie, jeton, page=False, seuils=profil.bannissement)
    if verdict and verdict.par == "empreinte":
        db.enregistrer_decision(
            cx,
            jeton,
            "bannissement",
            "bloque",
            page,
            [{"detecteur": "bannissement", "motif": verdict.motif, "par": "empreinte"}],
        )
        surveillance.bannir_visiteur(cx, secret, cookie, jeton, "empreinte_bannie")


def controler(
    request: Request,
    cx: sqlite3.Connection,
    secret: bytes,
    sceau: Sceau,
    jeton: str,
    chemin: str,
    surveillance: bannissements.Surveillance | None = None,
) -> Response | None:
    """Renvoie la réponse de la protection qui s'applique, ou None si la requête peut passer."""
    if not protegee(chemin, request.method):
        return None
    profil = profils.charger().de(sceau.profil)
    if profil is None:
        return None
    surveillance = surveillance or bannissements.Surveillance()
    cookie_visiteur = request.cookies.get(visiteurs.COOKIE)
    # Le bannissement se lit en tête, avant tout défi, et seulement si le profil l'active (niveaux 01 à 07 : jamais).
    if profil.bannissement.actif:
        verdict = surveillance.juger(
            cx,
            secret,
            cookie_visiteur,
            jeton,
            page=_est_une_page(chemin),
            seuils=profil.bannissement,
            adresse=sceau.adresse,
        )
        if verdict:
            return refus_banni(request, cx, jeton, chemin, verdict)
    lie = empreinte_liee(sceau)
    usage_defi, cle_defi = "defi", jeton
    if profil.defi_js.par_visiteur:
        monde, visiteur = surveillance.visiteur_de(cx, secret, cookie_visiteur, jeton)
        usage_defi, cle_defi = portee_defi(profil, jeton, monde, visiteur)
    if profil.defi_js.actif and (
        cle_defi is None or not defis.cookie_valide(secret, usage_defi, request.cookies.get(COOKIE_DEFI), cle_defi, lie)
    ):
        defi = defis.creer_defi(secret, jeton, profil.defi_js.difficulte)
        motifs = [{"difficulte": profil.defi_js.difficulte}]
        db.enregistrer_decision(cx, jeton, "defi-js", "emis", chemin, motifs)
        cible = encoder_retour(request.url.path + (f"?{request.url.query}" if request.url.query else ""))
        return _refus(request, pages.page_defi(defi, profil.defi_js.difficulte, cible, jeton=jeton), "defi-js")
    if profil.fingerprinting.actif:
        if _fingerprinting_differe(cx, jeton):
            if profil.fingerprinting.bloquer != "non":
                db.enregistrer_decision(
                    cx, jeton, "fingerprinting", "bloque", chemin, [{"detecteur": "fingerprinting-differe"}]
                )
                bannir_si_arret(
                    cx, surveillance, secret, request, profil, jeton, [{"detecteur": "fingerprinting-differe"}]
                )
                return _refus(request, pages.page_blocage(), "fingerprinting-differe")
            db.enregistrer_decision(
                cx, jeton, "fingerprinting", "suspect", chemin, [{"detecteur": "fingerprinting-differe"}]
            )
        if profil.fingerprinting.seuil_composite is not None and _composite_differe(cx, jeton):
            if profil.fingerprinting.bloquer != "non":
                db.enregistrer_decision(
                    cx, jeton, "fingerprinting", "bloque", chemin, [{"detecteur": "composite-differe"}]
                )
                bannir_si_arret(cx, surveillance, secret, request, profil, jeton, [{"detecteur": "composite-differe"}])
                return _refus(request, pages.page_blocage(), "composite-differe")
            db.enregistrer_decision(
                cx, jeton, "fingerprinting", "suspect", chemin, [{"detecteur": "composite-differe"}]
            )
        motifs = suspicion(cx, jeton, **parametres(profil))
        if motifs:
            if profil.fingerprinting.bloquer != "non":
                db.enregistrer_decision(cx, jeton, "fingerprinting", "bloque", chemin, motifs)
                bannir_si_arret(cx, surveillance, secret, request, profil, jeton, motifs)
                return _refus(request, pages.page_blocage(), "fingerprinting")
            db.enregistrer_decision(cx, jeton, "fingerprinting", "suspect", chemin, motifs)
    if profil.turnstile.actif and not defis.cookie_valide(
        secret, "turnstile", request.cookies.get(COOKIE_TURNSTILE), jeton, lie
    ):
        db.enregistrer_decision(cx, jeton, "turnstile", "emis", chemin, [])
        cible = encoder_retour(request.url.path + (f"?{request.url.query}" if request.url.query else ""))
        site_key = defis.turnstile_site_key("pass")
        reponse = _refus(request, pages.page_turnstile(site_key, cible, jeton=jeton), "turnstile")
        reponse.headers["X-ShadowLab-Turnstile"] = "1"
        return reponse
    if profil.recaptcha.actif and not defis.cookie_valide(
        secret, "recaptcha", request.cookies.get(COOKIE_RECAPTCHA), jeton, lie
    ):
        db.enregistrer_decision(cx, jeton, "recaptcha", "emis", chemin, [])
        cible = encoder_retour(request.url.path + (f"?{request.url.query}" if request.url.query else ""))
        reponse = _refus(request, pages.page_recaptcha(defis.recaptcha_site_key(), cible, jeton=jeton), "recaptcha")
        reponse.headers["X-ShadowLab-Recaptcha"] = "1"
        return reponse
    if profil.captcha.actif and not defis.cookie_valide(
        secret, "captcha", request.cookies.get(COOKIE_CAPTCHA), jeton, lie
    ):
        motifs = suspicion(cx, jeton, **parametres(profil))
        if motifs:
            db.enregistrer_decision(cx, jeton, "captcha", "emis", chemin, motifs)
            cible = encoder_retour(request.url.path + (f"?{request.url.query}" if request.url.query else ""))
            page = pages.page_captcha(defis.creer_captcha(secret, jeton), cible, jeton=jeton)
            return _refus(request, page, "captcha")
    return None
