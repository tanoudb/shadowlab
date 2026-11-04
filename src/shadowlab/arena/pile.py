"""Pilotage de la pile Docker de l'Arena (Nginx et Coraza) : configurations générées, démarrage, état."""

from __future__ import annotations

import http.client
import os
import subprocess
from pathlib import Path

from ..config import RACINE, Reglages
from . import profils as module_profils

COMPOSE = RACINE / "docker" / "arena" / "docker-compose.yml"


class ArenaIndisponible(RuntimeError):
    """La chaîne de protection ne répond pas."""


def generer(reglages: Reglages) -> Path:
    """Écrit les configurations Nginx et Coraza à partir des profils. Renvoie le dossier généré."""
    profils = module_profils.charger()
    dossier = reglages.dossier_arena / "generes"
    dossier.mkdir(parents=True, exist_ok=True)
    (reglages.dossier_arena / "journaux").mkdir(parents=True, exist_ok=True)
    (dossier / "nginx.conf").write_text(module_profils.rendre_nginx(profils), encoding="utf-8")
    (dossier / "coraza-profils.conf").write_text(module_profils.rendre_coraza(profils), encoding="utf-8")
    return dossier


def _compose(reglages: Reglages, *arguments: str, delai: int = 600) -> subprocess.CompletedProcess:
    environnement = {
        **os.environ,
        "SHADOWLAB_ARENA_DIR": str(reglages.dossier_arena.resolve()),
        "SHADOWLAB_PORT_AVAL": str(reglages.port_aval),
    }
    return subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE), *arguments],
        env=environnement,
        capture_output=True,
        text=True,
        timeout=delai,
    )


def demarrer(reglages: Reglages, reconstruire: bool = False) -> str:
    generer(reglages)
    arguments = ["up", "-d", "--wait", "--force-recreate"]
    if reconstruire:
        arguments.append("--build")
    resultat = _compose(reglages, *arguments)
    if resultat.returncode != 0:
        raise ArenaIndisponible(f"docker compose a échoué : {resultat.stderr.strip()[-800:]}")
    return resultat.stderr.strip()


def arreter(reglages: Reglages) -> None:
    _compose(reglages, "down", delai=120)


def sante(reglages: Reglages) -> bool:
    """Vrai si Nginx et Coraza répondent tous les deux (Nginx relaie la sonde vers Coraza)."""
    connexion = http.client.HTTPConnection("127.0.0.1", reglages.port_aval, timeout=2)
    try:
        connexion.request("GET", "/arena-sante")
        return connexion.getresponse().status == 200
    except OSError:
        return False
    finally:
        connexion.close()


def versions(reglages: Reglages) -> dict[str, str]:
    """Versions des composants Docker de l'Arena, ou dict vide si la pile n'est pas active."""
    if not sante(reglages):
        return {}
    resultat: dict[str, str] = {}
    try:
        r = _compose(reglages, "images", "--format", "{{.Repository}}:{{.Tag}}", delai=10)
        if r.returncode == 0:
            for ligne in r.stdout.strip().splitlines():
                nom = ligne.split("/")[-1].split(":")[0] if "/" in ligne else ligne.split(":")[0]
                resultat[nom] = ligne.strip()
    except Exception:
        pass
    return resultat


def etat(reglages: Reglages) -> dict:
    return {"chaine_active": sante(reglages), "port_aval": reglages.port_aval, "url_arena": reglages.url_arena}
