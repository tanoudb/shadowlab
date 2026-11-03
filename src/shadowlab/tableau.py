"""Tableau de bord : une page servie sous `/tableau`, qui lit l'API."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from .api import autoriser

DOSSIER = Path(__file__).parent / "tableau_static"

routeur = APIRouter(dependencies=[Depends(autoriser)], include_in_schema=False)


@routeur.get("/tableau")
def tableau() -> FileResponse:
    return FileResponse(DOSSIER / "index.html", headers={"Cache-Control": "no-store"})


@routeur.get("/tableau/{fichier}")
def ressource(fichier: str) -> FileResponse:
    chemin = (DOSSIER / fichier).resolve()
    if chemin.parent != DOSSIER.resolve() or not chemin.is_file():
        from fastapi import HTTPException

        raise HTTPException(404)
    return FileResponse(chemin, headers={"Cache-Control": "no-store"})
