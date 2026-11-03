"""Journalisation structurée : une ligne JSON par évènement dans `<sorties>/logs/shadowlab.jsonl`,
et une ligne lisible à l'écran."""

from __future__ import annotations

import json
import logging
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


def configurer(sorties: Path, verbeux: bool = False) -> None:
    dossier = sorties / "logs"
    dossier.mkdir(parents=True, exist_ok=True)
    fichier = logging.FileHandler(dossier / "shadowlab.jsonl", encoding="utf-8")
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
