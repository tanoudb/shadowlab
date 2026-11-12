"""Journalisation structurée : une ligne JSON par évènement dans `<sorties>/logs/shadowlab.jsonl`,
et une ligne lisible à l'écran."""

from __future__ import annotations

import json
import logging
import logging.handlers
from datetime import UTC, datetime
from pathlib import Path


class FormatJson(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        ligne = {
            "moment": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "niveau": record.levelname,
            "source": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            ligne["exception"] = self.formatException(record.exc_info)
        return json.dumps(ligne, ensure_ascii=False)


def configurer(sorties: Path, verbeux: bool = False, rotation: tuple[int, int] | None = None) -> None:
    """`rotation` = (octets par fichier, fichiers gardés en plus du courant) ; sans elle, un seul fichier."""
    dossier = sorties / "logs"
    dossier.mkdir(parents=True, exist_ok=True)
    chemin = dossier / "shadowlab.jsonl"
    if rotation:
        taille, nombre = rotation
        fichier = logging.handlers.RotatingFileHandler(chemin, maxBytes=taille, backupCount=nombre, encoding="utf-8")
    else:
        fichier = logging.FileHandler(chemin, encoding="utf-8")
    fichier.setFormatter(FormatJson())
    fichier.setLevel(logging.DEBUG)
    ecran = logging.StreamHandler()
    ecran.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%H:%M:%S"))
    ecran.setLevel(logging.DEBUG if verbeux else logging.INFO)
    racine = logging.getLogger("shadowlab")
    racine.handlers[:] = [fichier, ecran]
    racine.setLevel(logging.DEBUG)
    racine.propagate = False
    # Scrapling écrit une ligne par requête : utile en mise au point, du bruit pendant une campagne.
    logging.getLogger("scrapling").setLevel(logging.WARNING)
