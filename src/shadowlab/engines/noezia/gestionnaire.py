"""Gestionnaire d'identités (étape 4.2 du plan) : plusieurs identités persistantes se partagent une récolte.

Ce module tient ce qui est commun à la commande (`shadowlab recolte lancer --identites a,b,c`) et à la campagne
(bras d'une même `recolte_partagee`) :
- le **verrou de travail** d'une identité dans une récolte (`verrou_travailleur`, `travailleur_vivant`) : tenu par le
  processus qui travaille pour elle, toute sa vie ; libre, ses pages en cours sont orphelines et reviennent en file
  (`Etat.liberer_orphelines`) ;
"""

from __future__ import annotations

import fcntl
import time
from pathlib import Path
from typing import IO

from .identite import verifier_nom

DOSSIER_TRAVAILLEURS = "travailleurs"
ATTENTE_VERROU_S = 5.0  # un autre processus peut tenir ce verrou une fraction de seconde : il le teste


def _chemin_verrou(dossier: Path, nom: str) -> Path:
    return Path(dossier) / DOSSIER_TRAVAILLEURS / f"{verifier_nom(nom)}.verrou"


def verrou_travailleur(dossier: Path, nom: str, attente_s: float = ATTENTE_VERROU_S) -> IO[str]:
    """Prend le verrou de travail de l'identité `nom` dans la récolte `dossier` et le rend ouvert : le processus le
    garde (référence vivante) tant qu'il travaille pour elle ; il disparaît avec lui, même tué. Un autre processus peut
    le tenir un instant pour tester s'il est libre (`travailleur_vivant`) : on réessaie pendant `attente_s`. Pris par un
    autre travailleur au-delà : `BlockingIOError` (une identité ne travaille qu'à un endroit à la fois)."""
    chemin = _chemin_verrou(dossier, nom)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    fichier = chemin.open("a+", encoding="utf-8")
    limite = time.monotonic() + attente_s
    while True:
        try:
            fcntl.flock(fichier, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return fichier
        except OSError:
            if time.monotonic() >= limite:
                fichier.close()
                raise BlockingIOError(
                    f"identité {nom!r} : un autre processus travaille déjà pour elle ({chemin})"
                ) from None
            time.sleep(0.05)


def travailleur_vivant(dossier: Path, nom: str) -> bool:
    """Vrai si un processus tient le verrou de travail de `nom` dans cette récolte (essai non bloquant, aussitôt
    relâché). Faux : personne ne travaille pour elle, ses pages en cours sont orphelines."""
    chemin = _chemin_verrou(dossier, nom)
    if not chemin.exists():
        return False
    with chemin.open("a+", encoding="utf-8") as fichier:
        try:
            fcntl.flock(fichier, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return True
        fcntl.flock(fichier, fcntl.LOCK_UN)
        return False
