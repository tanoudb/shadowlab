"""Application locale : site de test, serveur de détection, sessions manuelles, API et tableau de bord."""

from __future__ import annotations

import json
import os
import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from .. import database as db
from .. import passages
from ..arena import defis
from ..arena import secret as secrets_arena
from ..arena.profils import BASELINE
from ..arena.profils import charger as charger_profils
from ..config import Reglages, charger
from ..detection import Observations, classer
from . import comptes, gardien, pages

STATIQUES = Path(__file__).parent / "static"
JETON_VALIDE = re.compile(r"^[0-9a-f]{32}$")
COOKIE_SESSION = "sl_session"
TAILLE_MAX_COLLECTE = 64 * 1024
NOMS_LOCAUX = frozenset({"127.0.0.1", "localhost", "::1"})
DESTINATION_EXTERIEURE = "http://example.com/"  # domaine réservé à la documentation (RFC 2606)
CSP = (
    "default-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self' data:; "
    "style-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
)
CSP_TURNSTILE = (
    "default-src 'self'; script-src 'self' 'unsafe-inline' https://challenges.cloudflare.com; "
    "connect-src 'self' https://challenges.cloudflare.com; "
    "frame-src https://challenges.cloudflare.com; img-src 'self' data:; "
    "style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
)
CSP_RECAPTCHA = (
    "default-src 'self'; script-src 'self' 'unsafe-inline'"
    " https://www.google.com/recaptcha/ https://www.gstatic.com/recaptcha/; "
    "connect-src 'self'; frame-src https://www.google.com/recaptcha/ https://www.recaptcha.net/; "
    "img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
    "frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
)
CSP_RECAPTCHA_V3 = (
    "default-src 'self'; script-src 'self' 'unsafe-inline'"
    " https://www.google.com/recaptcha/ https://www.gstatic.com/recaptcha/; "
    "connect-src 'self' https://www.google.com/recaptcha/; "
    "frame-src https://www.google.com/recaptcha/ https://www.recaptcha.net/; "
    "img-src 'self' data: https://www.gstatic.com/recaptcha/; style-src 'self' 'unsafe-inline'; "
    "frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
)


def jeton_de(request: Request) -> str:
    """Jeton de session : paramètre `sl` en priorité, sinon cookie posé à la première visite."""
    sl = request.query_params.getlist("sl")
    if len(sl) > 1:
        return ""
    candidat = sl[0] if sl else request.cookies.get(COOKIE_SESSION) or ""
    return candidat if JETON_VALIDE.match(candidat) else ""


def creer_app(reglages: Reglages | None = None) -> FastAPI:
    reglages = reglages or charger()
    app = FastAPI(title="NOEZIA ShadowLab", version="0.1.0", docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.state.reglages = reglages
    secret = secrets_arena.charger(reglages.dossier_arena)

    @contextmanager
    def base() -> Iterator[sqlite3.Connection]:
        cx = db.ouvrir(reglages.base_donnees)
        try:
            yield cx
        finally:
            cx.close()

    app.state.base = base

    @app.middleware("http")
    async def observer(request: Request, call_next):
        """Enregistre chaque requête du site de test (en-têtes dans l'ordre reçu) et pose le cookie de session."""
        chemin = request.url.path
        observable = chemin.startswith("/lab")
        jeton = jeton_de(request) if observable else ""
        sceau = gardien.lire_sceau(request, secret)
        request.state.sceau = sceau
        # Derrière le frontal, il a déjà tout noté, avant que les mandataires ne réécrivent les en-têtes.
        if jeton and sceau is None:
            entetes = [[nom.decode("latin-1"), valeur.decode("latin-1")] for nom, valeur in request.scope["headers"]]
            with base() as cx:
                cx.execute(
                    "INSERT INTO observations_http (session_token, received_at, method, path, http_version, headers,"
                    " cookies) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        jeton,
                        db.maintenant(),
                        request.method,
                        chemin,
                        request.scope.get("http_version"),
                        db.j(entetes),
                        db.j(sorted(request.cookies)),
                    ),
                )
        reponse: Response | None = None
        if sceau is not None and jeton:
            with base() as cx:
                reponse = gardien.controler(request, cx, secret, sceau, jeton, chemin)
        if reponse is None:
            reponse = await call_next(request)
        if chemin.startswith("/lab") or chemin.startswith("/manuel"):
            est_turnstile = "X-ShadowLab-Turnstile" in reponse.headers
            est_recaptcha = "X-ShadowLab-Recaptcha" in reponse.headers
            est_v3 = "X-ShadowLab-RecaptchaV3" in reponse.headers
            if est_turnstile:
                del reponse.headers["X-ShadowLab-Turnstile"]
            if est_recaptcha:
                del reponse.headers["X-ShadowLab-Recaptcha"]
            if est_v3:
                del reponse.headers["X-ShadowLab-RecaptchaV3"]
            csp = (
                CSP_RECAPTCHA_V3
                if est_v3
                else CSP_TURNSTILE
                if est_turnstile
                else CSP_RECAPTCHA
                if est_recaptcha
                else CSP
            )
            reponse.headers["Content-Security-Policy"] = csp
            reponse.headers["X-Content-Type-Options"] = "nosniff"
            reponse.headers["Referrer-Policy"] = "same-origin"
        sl = request.query_params.getlist("sl")
        if jeton and len(sl) == 1 and sl[0] == jeton:
            reponse.set_cookie(COOKIE_SESSION, jeton, httponly=True, samesite="lax", path="/")
        return reponse

    from ..api import _local

    # Contre le « DNS rebinding » : en écoute locale (sans jeton), une page tierce dont le nom pointerait vers
    # 127.0.0.1 enverrait son propre nom dans `Host`. Seuls les noms locaux et les hôtes autorisés sont servis.
    # Déclaré après `observer`, ce contrôle passe avant lui : une requête refusée n'est pas enregistrée.
    # Le ``*`` du périmètre moteur (illimité) ne s'applique PAS au serveur de test : sa protection
    # anti-DNS-rebinding reste stricte (correspondance exacte d'hôte), on filtre donc le ``*``.
    hotes_servis = NOMS_LOCAUX | {h for h in reglages.hotes_autorises if h != "*"} if _local(reglages.hote) else None

    @app.middleware("http")
    async def controler_hote(request: Request, call_next):
        if hotes_servis is not None:
            try:
                nom = urlsplit("//" + request.headers.get("host", "")).hostname
            except ValueError:
                nom = None
            if nom not in hotes_servis:
                return PlainTextResponse("hôte non reconnu", status_code=400)
        return await call_next(request)

    # --- Site de test -------------------------------------------------------------------------------

    @app.get("/", include_in_schema=False)
    def racine() -> RedirectResponse:
        return RedirectResponse("/tableau")

    @app.get("/lab/sante", tags=["site"])
    def sante() -> dict[str, str]:
        """Signature d'identité : permet à une campagne de vérifier qu'elle parle
        bien au site ShadowLab et non à un service étranger sur le même port."""
        return {"service": "shadowlab-site", "role": "cible-de-test"}

    @app.get("/lab/", response_class=HTMLResponse, tags=["site"])
    def accueil(request: Request) -> str:
        hp = gardien.honeypots_actifs(request.state.sceau)
        return pages.accueil(jeton_de(request), honeypot=hp)

    @app.get("/lab/statique", response_class=HTMLResponse, tags=["site"])
    def statique(request: Request) -> str:
        hp = gardien.honeypots_actifs(request.state.sceau)
        return pages.statique(jeton_de(request), honeypot=hp)

    @app.get("/lab/adaptatif", response_class=HTMLResponse, tags=["site"])
    def adaptatif(request: Request) -> str:
        hp = gardien.honeypots_actifs(request.state.sceau)
        return pages.adaptatif(jeton_de(request), honeypot=hp)

    @app.get("/lab/dynamique", response_class=HTMLResponse, tags=["site"])
    def dynamique(request: Request) -> str:
        hp = gardien.honeypots_actifs(request.state.sceau)
        return pages.dynamique(jeton_de(request), honeypot=hp)

    @app.get("/lab/catalogue", response_class=HTMLResponse, tags=["site"])
    def catalogue(request: Request, page: int = 1) -> str:
        if not 1 <= page <= pages.NB_PAGES_CATALOGUE:
            raise HTTPException(404, "page inexistante")
        hp = gardien.honeypots_actifs(request.state.sceau)
        return pages.catalogue(jeton_de(request), page, honeypot=hp)

    @app.get("/lab/formulaire", response_class=HTMLResponse, tags=["site"])
    def formulaire(request: Request) -> str:
        hp = gardien.honeypots_actifs(request.state.sceau)
        return pages.formulaire(jeton_de(request), honeypot=hp)

    @app.post("/lab/formulaire", response_class=HTMLResponse, tags=["site"])
    async def formulaire_envoye(request: Request) -> str:
        champs = parse_qs((await request.body()).decode("utf-8", "replace"))
        nom = (champs.get("nom") or [""])[0].strip()[:60]
        modele = (champs.get("modele") or [""])[0]
        piege = (champs.get("sl_telephone") or [""])[0]
        jeton = jeton_de(request)
        if piege and jeton:
            with base() as cx:
                db.enregistrer_decision(cx, jeton, "honeypot", "declenche", "/lab/formulaire", [{"type": "champ"}])
        if not nom or modele not in pages.MODELES:
            raise HTTPException(422, "formulaire incomplet")
        return pages.confirmation(jeton, nom, modele)

    # --- Niveau authentifié : login protégé par détection comportementale ---------------------------

    @app.get("/lab/connexion", response_class=HTMLResponse, tags=["site"])
    def connexion_page(request: Request) -> str:
        hp = gardien.honeypots_actifs(request.state.sceau)
        return pages.connexion(jeton_de(request), honeypot=hp)

    @app.post("/lab/connexion", tags=["site"])
    async def connexion_envoyee(request: Request) -> Response:
        sceau, jeton = request.state.sceau, jeton_de(request)
        champs = parse_qs((await request.body()).decode("utf-8", "replace"))
        identifiant = (champs.get("identifiant") or [""])[0].strip()[:60]
        mot_de_passe = (champs.get("mot_de_passe") or [""])[0][:120]
        piege = (champs.get("sl_site") or [""])[0]
        profil = charger_profils().de(sceau.profil) if sceau else None
        porte = bool(profil and profil.connexion.actif)
        hp_actif = gardien.honeypots_actifs(sceau)

        def journal(decision: str, motifs: list[dict]) -> None:
            if jeton:
                with base() as cx:
                    db.enregistrer_decision(cx, jeton, "connexion", decision, "/lab/connexion", motifs)

        def refus(message: str, motifs: list[dict]) -> Response:
            journal("refuse", motifs)
            return HTMLResponse(pages.connexion(jeton, honeypot=hp_actif, erreur=message), status_code=403)

        # 1) Champ piège rempli → robot aveugle (même sans porte active, un humain ne le remplit pas)
        if piege:
            return refus("Accès refusé.", [{"code": "honeypot", "type": "champ"}])

        # 2) Limite de tentatives (anti force brute)
        if porte and jeton:
            with base() as cx:
                tentatives = cx.execute(
                    "SELECT COUNT(*) FROM decisions WHERE session_token = ? AND couche = 'connexion'"
                    " AND decision IN ('refuse', 'tentative')",
                    (jeton,),
                ).fetchone()[0]
            if tentatives >= profil.connexion.tentatives_max:
                return refus("Trop de tentatives.", [{"code": "rate-limit", "tentatives": tentatives}])

        # 3) Porte comportementale : signaux de bot connus à cet instant (empreinte, comportement, honeypot…)
        if porte and jeton:
            with base() as cx:
                motifs = gardien.suspicion(
                    cx,
                    jeton,
                    detecteurs=profil.fingerprinting.detecteurs or None,
                    seuil_composite=profil.fingerprinting.seuil_composite,
                )
            if motifs:
                return refus("Accès refusé.", motifs)

        # 4) Vérification des identifiants (comptes de test)
        if not comptes.verifier(identifiant, mot_de_passe):
            journal("tentative", [{"code": "identifiants"}])
            return HTMLResponse(
                pages.connexion(jeton, honeypot=hp_actif, erreur="Identifiants incorrects."), status_code=401
            )

        # 5) Succès : cookie de session authentifiée, lié à l'empreinte si le niveau l'exige
        journal("valide", [{"compte": identifiant}])
        reponse = RedirectResponse("/lab/espace", status_code=303)
        lie = gardien.empreinte_liee(sceau) if sceau else ""
        reponse.set_cookie(
            gardien.COOKIE_CONNEXION,
            defis.creer_cookie(secret, "connexion", jeton, lie),
            httponly=True,
            samesite="lax",
            path="/lab",
        )
        return reponse

    @app.get("/lab/espace", tags=["site"])
    def espace(request: Request) -> Response:
        sceau, jeton = request.state.sceau, jeton_de(request)
        lie = gardien.empreinte_liee(sceau) if sceau else ""
        cookie = request.cookies.get(gardien.COOKIE_CONNEXION)
        if not defis.cookie_valide(secret, "connexion", cookie, jeton, lie):
            return RedirectResponse("/lab/connexion", status_code=303)
        identifiant = "?"
        if jeton:
            with base() as cx:
                ligne = cx.execute(
                    "SELECT motifs FROM decisions WHERE session_token = ? AND couche = 'connexion'"
                    " AND decision = 'valide' ORDER BY id DESC LIMIT 1",
                    (jeton,),
                ).fetchone()
            if ligne and ligne["motifs"]:
                try:
                    identifiant = (json.loads(ligne["motifs"]) or [{}])[0].get("compte", "?")
                except (ValueError, TypeError, AttributeError, IndexError):
                    pass
        return HTMLResponse(pages.espace(jeton, identifiant))

    @app.get("/lab/deconnexion", tags=["site"])
    def deconnexion() -> Response:
        reponse = RedirectResponse("/lab/connexion", status_code=303)
        reponse.delete_cookie(gardien.COOKIE_CONNEXION, path="/lab")
        return reponse

    @app.get("/lab/piege", status_code=204, tags=["site"])
    def piege(request: Request) -> Response:
        """Lien invisible : seul un robot le visite. Enregistre le déclenchement."""
        jeton = jeton_de(request)
        if jeton:
            with base() as cx:
                db.enregistrer_decision(cx, jeton, "honeypot", "declenche", "/lab/piege", [{"type": "lien"}])
        return Response(status_code=204)

    @app.get("/lab/session", response_class=HTMLResponse, tags=["site"])
    def session(request: Request) -> HTMLResponse:
        try:
            visites = int(request.cookies.get("visites", "0")) + 1
        except ValueError:
            visites = 1
        reponse = HTMLResponse(pages.session(jeton_de(request), visites))
        reponse.set_cookie("visites", str(visites), httponly=True, samesite="lax", path="/lab")
        return reponse

    @app.get("/lab/empreinte", response_class=HTMLResponse, tags=["site"])
    def empreinte(request: Request) -> str:
        return pages.empreinte(jeton_de(request))

    @app.get("/lab/detection", response_class=HTMLResponse, tags=["site"])
    def detection(request: Request) -> str:
        return pages.detection(jeton_de(request))

    @app.get("/lab/sortie", tags=["site"])
    def sortie() -> RedirectResponse:
        """Redirige hors du périmètre : sert à vérifier que chaque moteur refuse de suivre."""
        return RedirectResponse(DESTINATION_EXTERIEURE, status_code=302)

    @app.get("/lab/api/articles", tags=["site"])
    def articles(limite: int = 25) -> dict:
        limite = max(1, min(limite, 100))
        return {
            "total": limite,
            "articles": [{"id": f"ART-{n:03d}", "prix": 100 + n} for n in range(1, limite + 1)],
        }

    # --- Serveur de détection -----------------------------------------------------------------------

    @app.post("/lab/collecte", status_code=204, tags=["détection"])
    async def collecte(request: Request) -> Response:
        jeton = jeton_de(request)
        brut = await request.body()
        if not jeton or len(brut) > TAILLE_MAX_COLLECTE:
            raise HTTPException(400, "collecte refusée")
        try:
            message = json.loads(brut)
            kind = str(message["kind"])[:32]
            page = str(message.get("page", ""))[:200]
            payload = message["payload"]
        except (ValueError, KeyError, TypeError) as erreur:
            raise HTTPException(400, "message illisible") from erreur
        if kind not in ("empreinte", "comportement"):
            raise HTTPException(400, "type inconnu")
        with base() as cx:
            cx.execute(
                "INSERT INTO observations_js (session_token, received_at, kind, page, payload) VALUES (?, ?, ?, ?, ?)",
                (jeton, db.maintenant(), kind, page, db.j(payload)),
            )
            if kind == "empreinte":
                sceau = request.state.sceau
                if sceau:
                    profil = charger_profils().de(sceau.profil)
                    if profil and profil.fingerprinting.actif and profil.fingerprinting.seuil_composite is not None:
                        motifs = gardien.suspicion(
                            cx,
                            jeton,
                            detecteurs=profil.fingerprinting.detecteurs or None,
                            seuil_composite=profil.fingerprinting.seuil_composite,
                        )
                        composite = [m for m in motifs if m.get("detecteur") == "composite"]
                        if composite:
                            db.enregistrer_decision(
                                cx, jeton, "composite-differe", "detecte", page or "/lab/collecte", composite
                            )
        return Response(status_code=204)

    @app.get("/lab/verdict", tags=["détection"])
    def verdict(request: Request) -> list[dict]:
        jeton = jeton_de(request)
        if not jeton:
            raise HTTPException(400, "session inconnue")
        with base() as cx:
            http, js = db.observations(cx, jeton)
            tls = db.tls_session(cx, jeton)
        return [
            {
                "detector_name": c.detector_name,
                "classification": c.classification,
                "confidence": c.confidence,
                "signals": [s.en_dict() for s in c.signals],
            }
            for c in classer(Observations(http=http, js=js, tls=tls))
        ]

    # --- Protections de l'Arena : défi JavaScript et CAPTCHA de démonstration ---------------------------

    @app.post("/lab/defi/verifier", status_code=204, tags=["arena"])
    async def defi_verifier(request: Request) -> Response:
        sceau, jeton = request.state.sceau, jeton_de(request)
        if sceau is None or not jeton:
            raise HTTPException(400, "défi hors de l'Arena")
        try:
            message = json.loads(await request.body())
            defi, nonce = str(message["defi"]), message["nonce"]
        except (ValueError, KeyError, TypeError) as erreur:
            raise HTTPException(400, "message illisible") from erreur
        motif = defis.verifier_defi(secret, jeton, defi, nonce)
        with base() as cx:
            if motif:
                db.enregistrer_decision(cx, jeton, "defi-js", "echec", request.url.path, [{"code": motif}])
                raise HTTPException(403, motif)
            duree = message.get("ms") if isinstance(message.get("ms"), int | float) else None
            db.enregistrer_decision(cx, jeton, "defi-js", "valide", request.url.path, [{"duree_ms": duree}])
        reponse = Response(status_code=204)
        lie = gardien.empreinte_liee(sceau)
        reponse.set_cookie(
            gardien.COOKIE_DEFI,
            defis.creer_cookie(secret, "defi", jeton, lie),
            httponly=True,
            samesite="lax",
            path="/lab",
        )
        return reponse

    @app.get("/lab/captcha/image", tags=["arena"])
    def captcha_image(request: Request, c: str = "") -> Response:
        image = defis.image_captcha(secret, jeton_de(request), c)
        if image is None:
            raise HTTPException(404, "captcha inconnu")
        return Response(image, media_type="image/png", headers={"Cache-Control": "no-store"})

    @app.post("/lab/captcha/verifier", tags=["arena"])
    async def captcha_verifier(request: Request) -> Response:
        sceau, jeton = request.state.sceau, jeton_de(request)
        if sceau is None or not jeton:
            raise HTTPException(400, "captcha hors de l'Arena")
        champs = parse_qs((await request.body()).decode("utf-8", "replace"))
        captcha = (champs.get("c") or [""])[0]
        code = (champs.get("code") or [""])[0]
        retour_brut = (champs.get("retour") or ["/lab/"])[0]
        retour = gardien.decoder_retour(retour_brut)
        motif = defis.verifier_captcha(secret, jeton, captcha, code)
        with base() as cx:
            if motif:
                db.enregistrer_decision(cx, jeton, "captcha", "echec", request.url.path, [{"code": motif}])
                nouveau = defis.creer_captcha(secret, jeton)
                retour_enc = gardien.encoder_retour(retour)
                return HTMLResponse(pages.page_captcha(nouveau, retour_enc, erreur=True), status_code=403)
            db.enregistrer_decision(cx, jeton, "captcha", "valide", request.url.path)
        reponse = RedirectResponse(retour, status_code=303)
        reponse.set_cookie(
            gardien.COOKIE_CAPTCHA,
            defis.creer_cookie(secret, "captcha", jeton, gardien.empreinte_liee(sceau)),
            httponly=True,
            samesite="lax",
            path="/lab",
        )
        return reponse

    @app.post("/lab/turnstile/verifier", tags=["arena"])
    async def turnstile_verifier(request: Request) -> Response:
        sceau, jeton = request.state.sceau, jeton_de(request)
        if sceau is None or not jeton:
            raise HTTPException(400, "turnstile hors de l'Arena")
        champs = parse_qs((await request.body()).decode("utf-8", "replace"))
        token = (champs.get("cf-turnstile-response") or [""])[0]
        retour_brut = (champs.get("retour") or ["/lab/"])[0]
        retour = gardien.decoder_retour(retour_brut)
        resultat = defis.verifier_turnstile(token)
        with base() as cx:
            if not resultat.get("success"):
                codes = resultat.get("error-codes", [])
                db.enregistrer_decision(cx, jeton, "turnstile", "echec", request.url.path, [{"codes": codes}])
                site_key = defis.turnstile_site_key("pass")
                reponse = HTMLResponse(pages.page_turnstile(site_key, gardien.encoder_retour(retour)), status_code=403)
                reponse.headers["X-ShadowLab-Turnstile"] = "1"
                return reponse
            db.enregistrer_decision(cx, jeton, "turnstile", "captcha_test", request.url.path)
        reponse = RedirectResponse(retour, status_code=303)
        reponse.set_cookie(
            gardien.COOKIE_TURNSTILE,
            defis.creer_cookie(secret, "turnstile", jeton, gardien.empreinte_liee(sceau)),
            httponly=True,
            samesite="lax",
            path="/lab",
        )
        return reponse

    @app.post("/lab/recaptcha/verifier", tags=["arena"])
    async def recaptcha_verifier(request: Request) -> Response:
        sceau, jeton = request.state.sceau, jeton_de(request)
        if sceau is None or not jeton:
            raise HTTPException(400, "recaptcha hors de l'Arena")
        champs = parse_qs((await request.body()).decode("utf-8", "replace"))
        token = (champs.get("g-recaptcha-response") or [""])[0]
        retour_brut = (champs.get("retour") or ["/lab/"])[0]
        retour = gardien.decoder_retour(retour_brut)
        resultat = defis.verifier_recaptcha(token)
        with base() as cx:
            if not resultat.get("success"):
                codes = resultat.get("error-codes", [])
                db.enregistrer_decision(cx, jeton, "recaptcha", "echec", request.url.path, [{"codes": codes}])
                site_key = defis.recaptcha_site_key()
                reponse = HTMLResponse(pages.page_recaptcha(site_key, gardien.encoder_retour(retour)), status_code=403)
                reponse.headers["X-ShadowLab-Recaptcha"] = "1"
                return reponse
            db.enregistrer_decision(cx, jeton, "recaptcha", "captcha_test", request.url.path)
        reponse = RedirectResponse(retour, status_code=303)
        reponse.set_cookie(
            gardien.COOKIE_RECAPTCHA,
            defis.creer_cookie(secret, "recaptcha", jeton, gardien.empreinte_liee(sceau)),
            httponly=True,
            samesite="lax",
            path="/lab",
        )
        return reponse

    # --- Démo reCAPTCHA v3 RÉEL (score, pas de puzzle) — clés dans .env ----------------------------

    @app.get("/lab/recaptcha-v3", response_class=HTMLResponse, tags=["arena"])
    def recaptcha_v3_page(request: Request) -> Response:
        site = os.environ.get("SHADOWLAB_RECAPTCHA_V3_SITE", "")
        reponse = HTMLResponse(pages.recaptcha_v3(jeton_de(request), site))
        reponse.headers["X-ShadowLab-RecaptchaV3"] = "1"
        return reponse

    @app.post("/lab/recaptcha-v3/verifier", tags=["arena"])
    async def recaptcha_v3_verifier(request: Request) -> Response:
        """Vérifie le token v3 auprès de Google et renvoie le score. Le secret ne sort jamais."""
        jeton = jeton_de(request)
        secret = os.environ.get("SHADOWLAB_RECAPTCHA_V3_SECRET", "")
        if not secret:
            return JSONResponse({"success": False, "score": None, "erreur": "clé secrète absente (.env)"})
        try:
            corps = json.loads(await request.body())
            token = str(corps["token"])[:4000]
        except (ValueError, KeyError, TypeError) as erreur:
            raise HTTPException(400, "token illisible") from erreur
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.post(
                    "https://www.google.com/recaptcha/api/siteverify",
                    data={"secret": secret, "response": token},
                )
            res = r.json()
        except (httpx.HTTPError, ValueError) as erreur:
            raise HTTPException(502, "vérification Google indisponible") from erreur
        score = res.get("score")
        succes = bool(res.get("success"))
        if jeton:
            with base() as cx:
                db.enregistrer_decision(
                    cx,
                    jeton,
                    "recaptcha-v3",
                    "mesure",
                    "/lab/recaptcha-v3",
                    [{"score": score, "success": succes, "action": res.get("action")}],
                )
        return JSONResponse(
            {
                "success": succes,
                "score": score,
                "action": res.get("action"),
                "hostname": res.get("hostname"),
                "erreur": None if succes else res.get("error-codes"),
            }
        )

    app.mount("/lab/static", StaticFiles(directory=STATIQUES), name="lab-static")

    # --- Sessions manuelles (référence humaine) -----------------------------------------------------

    @app.get("/manuel", response_class=HTMLResponse, tags=["sessions manuelles"])
    def manuel() -> str:
        return pages.manuel()

    @app.post("/manuel/commencer", tags=["sessions manuelles"])
    async def manuel_commencer(request: Request) -> Response:
        champs = parse_qs((await request.body()).decode("utf-8", "replace"))
        profils = charger_profils()
        protection = (champs.get("protection") or [BASELINE])[0]
        if protection not in profils:
            raise HTTPException(422, "protection inconnue")
        consentement = (champs.get("consentement") or [None])[0]
        if consentement != "oui":
            raise HTTPException(422, "consentement requis pour enregistrer une session humaine")
        with base() as cx:
            experience = passages.experience_manuelle(cx)
            moteur = db.engine_id(cx, "navigateur-manuel", "n/a", "humain", {})
            scenario = db.scenario_id(cx, "navigation_manuelle", "Navigation libre par une personne")
            _, jeton = passages.demarrer(cx, experience, moteur, scenario, 1, "humain", protection=protection)
            cx.execute("UPDATE runs SET consent_at = ? WHERE session_token = ?", (db.maintenant(), jeton))
        if protection == BASELINE:
            return RedirectResponse(f"/lab/?sl={jeton}", status_code=303)
        # Une page et non une redirection : la politique `form-action 'self'` interdit de changer d'origine.
        return HTMLResponse(pages.manuel_pret(f"{reglages.url_arena}/lab/?sl={jeton}"))

    @app.get("/manuel/terminer", response_class=HTMLResponse, tags=["sessions manuelles"])
    def manuel_terminer(request: Request) -> str:
        jeton = jeton_de(request)
        with base() as cx:
            ligne = cx.execute(
                "SELECT id, started_at FROM runs WHERE session_token = ? AND truth = 'humain' AND status = 'en_cours'",
                (jeton,),
            ).fetchone()
            if not ligne:
                raise HTTPException(404, "aucune session manuelle en cours dans ce navigateur")
            classements = passages.finaliser(cx, ligne["id"], jeton, status="reussi", success=True, duration_ms=None)
        return pages.fin_manuelle(
            [{"detector_name": c.detector_name, "classification": c.classification} for c in classements]
        )

    # --- API, interface du laboratoire, ancien tableau de bord --------------------------------------
    from ..api import routeur as routeur_api
    from ..labo import routeur as routeur_labo
    from ..tableau import routeur as routeur_tableau

    app.include_router(routeur_api)
    app.include_router(routeur_labo)
    app.include_router(routeur_tableau)

    @app.exception_handler(sqlite3.OperationalError)
    async def base_occupee(_: Request, erreur: sqlite3.OperationalError) -> JSONResponse:
        return JSONResponse({"detail": f"base indisponible : {erreur}"}, status_code=503)

    return app
