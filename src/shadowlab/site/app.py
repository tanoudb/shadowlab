"""Application locale : site de test, serveur de détection, sessions manuelles, API et tableau de bord."""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import parse_qs

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from .. import database as db
from .. import passages
from ..config import Reglages, charger
from ..detection import Observations, classer
from . import pages

STATIQUES = Path(__file__).parent / "static"
JETON_VALIDE = re.compile(r"^[0-9a-f]{32}$")
COOKIE_SESSION = "sl_session"
TAILLE_MAX_COLLECTE = 64 * 1024
DESTINATION_EXTERIEURE = "http://example.com/"  # domaine réservé à la documentation (RFC 2606)
CSP = (
    "default-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self' data:; "
    "style-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
)


def jeton_de(request: Request) -> str:
    """Jeton de session : paramètre `sl` en priorité, sinon cookie posé à la première visite."""
    candidat = request.query_params.get("sl") or request.cookies.get(COOKIE_SESSION) or ""
    return candidat if JETON_VALIDE.match(candidat) else ""


def creer_app(reglages: Reglages | None = None) -> FastAPI:
    reglages = reglages or charger()
    app = FastAPI(title="NOEZIA ShadowLab", version="0.1.0", docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.state.reglages = reglages

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
        observable = chemin.startswith("/lab") and not chemin.startswith("/lab/static")
        jeton = jeton_de(request) if observable else ""
        if jeton:
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
        reponse: Response = await call_next(request)
        if chemin.startswith("/lab") or chemin.startswith("/manuel"):
            reponse.headers["Content-Security-Policy"] = CSP
            reponse.headers["X-Content-Type-Options"] = "nosniff"
            reponse.headers["Referrer-Policy"] = "same-origin"
        if jeton and request.query_params.get("sl") == jeton:
            reponse.set_cookie(COOKIE_SESSION, jeton, httponly=True, samesite="lax", path="/")
        return reponse

    # --- Site de test -------------------------------------------------------------------------------

    @app.get("/", include_in_schema=False)
    def racine() -> RedirectResponse:
        return RedirectResponse("/tableau")

    @app.get("/lab/", response_class=HTMLResponse, tags=["site"])
    def accueil(request: Request) -> str:
        return pages.accueil(jeton_de(request))

    @app.get("/lab/statique", response_class=HTMLResponse, tags=["site"])
    def statique(request: Request) -> str:
        return pages.statique(jeton_de(request))

    @app.get("/lab/dynamique", response_class=HTMLResponse, tags=["site"])
    def dynamique(request: Request) -> str:
        return pages.dynamique(jeton_de(request))

    @app.get("/lab/catalogue", response_class=HTMLResponse, tags=["site"])
    def catalogue(request: Request, page: int = 1) -> str:
        if not 1 <= page <= pages.NB_PAGES_CATALOGUE:
            raise HTTPException(404, "page inexistante")
        return pages.catalogue(jeton_de(request), page)

    @app.get("/lab/formulaire", response_class=HTMLResponse, tags=["site"])
    def formulaire(request: Request) -> str:
        return pages.formulaire(jeton_de(request))

    @app.post("/lab/formulaire", response_class=HTMLResponse, tags=["site"])
    async def formulaire_envoye(request: Request) -> str:
        champs = parse_qs((await request.body()).decode("utf-8", "replace"))
        nom = (champs.get("nom") or [""])[0].strip()[:60]
        modele = (champs.get("modele") or [""])[0]
        if not nom or modele not in pages.MODELES:
            raise HTTPException(422, "formulaire incomplet")
        return pages.confirmation(jeton_de(request), nom, modele)

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
        return Response(status_code=204)

    @app.get("/lab/verdict", tags=["détection"])
    def verdict(request: Request) -> list[dict]:
        jeton = jeton_de(request)
        if not jeton:
            raise HTTPException(400, "session inconnue")
        with base() as cx:
            http, js = db.observations(cx, jeton)
        return [
            {
                "detector_name": c.detector_name,
                "classification": c.classification,
                "confidence": c.confidence,
                "signals": [s.en_dict() for s in c.signals],
            }
            for c in classer(Observations(http=http, js=js))
        ]

    app.mount("/lab/static", StaticFiles(directory=STATIQUES), name="lab-static")

    # --- Sessions manuelles (référence humaine) -----------------------------------------------------

    @app.get("/manuel", response_class=HTMLResponse, tags=["sessions manuelles"])
    def manuel() -> str:
        return pages.manuel()

    @app.post("/manuel/commencer", tags=["sessions manuelles"])
    def manuel_commencer() -> RedirectResponse:
        with base() as cx:
            experience = passages.experience_manuelle(cx)
            moteur = db.engine_id(cx, "navigateur-manuel", "n/a", "humain", {})
            scenario = db.scenario_id(cx, "navigation_manuelle", "Navigation libre par une personne")
            _, jeton = passages.demarrer(cx, experience, moteur, scenario, 1, "humain")
        return RedirectResponse(f"/lab/?sl={jeton}", status_code=303)

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

    # --- API et tableau de bord ---------------------------------------------------------------------
    from ..api import routeur as routeur_api
    from ..tableau import routeur as routeur_tableau

    app.include_router(routeur_api)
    app.include_router(routeur_tableau)

    @app.exception_handler(sqlite3.OperationalError)
    async def base_occupee(_: Request, erreur: sqlite3.OperationalError) -> JSONResponse:
        return JSONResponse({"detail": f"base indisponible : {erreur}"}, status_code=503)

    return app
