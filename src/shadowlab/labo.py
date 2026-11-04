"""Interface du laboratoire : sert le front construit (`frontend/dist`) sous `/labo`.

En développement, le front tourne sous Vite (`npm --prefix frontend run dev`, port 5173) qui relaie `/api`.
En production, `npm --prefix frontend run build` produit `frontend/dist`, servi ici. Tout chemin inconnu
renvoie `index.html` (routage côté client de React Router).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from .api import autoriser
from .config import RACINE

DIST = RACINE / "frontend" / "dist"

routeur = APIRouter(dependencies=[Depends(autoriser)], include_in_schema=False)

_ABSENT = "interface non construite : lancez `npm --prefix frontend install && npm --prefix frontend run build`"


def _index() -> FileResponse:
    index = DIST / "index.html"
    if not index.is_file():
        raise HTTPException(503, _ABSENT)
    return FileResponse(index, headers={"Cache-Control": "no-store"})


@routeur.get("/labo")
@routeur.get("/labo/")
def accueil() -> FileResponse:
    return _index()


@routeur.get("/labo/{chemin:path}")
def ressource(chemin: str) -> FileResponse:
    cible = (DIST / chemin).resolve()
    if DIST.resolve() in cible.parents and cible.is_file():
        return FileResponse(cible)
    return _index()  # chemin inconnu : routage côté client
