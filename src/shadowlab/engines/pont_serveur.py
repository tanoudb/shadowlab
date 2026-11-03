"""Côté enfant du pont : reçoit les appels en JSON et les exécute sur le pilote réel. Voir `pont.py`."""

from __future__ import annotations

import dataclasses
import json
import os
import sys
from importlib import import_module
from pathlib import Path
from typing import Any

from .base import Driver, MesuresSession


def _simple(valeur: Any) -> Any:
    if dataclasses.is_dataclass(valeur):
        return dataclasses.asdict(valeur)
    if isinstance(valeur, Path):
        return str(valeur)
    return valeur


def main() -> int:
    module, _, nom = sys.argv[1].partition(":")
    classe: type[Driver] = getattr(import_module(module), nom)
    # La sortie standard porte le protocole : ce qu'une bibliothèque y écrirait part vers l'erreur standard.
    sortie = os.fdopen(os.dup(1), "w", buffering=1, encoding="utf-8")
    os.dup2(2, 1)
    pilote: Driver | None = None
    for ligne in sys.stdin:
        message = json.loads(ligne)
        methode, arguments = message["m"], message["a"]
        try:
            if methode == "creer":
                pilote = classe(tuple(arguments[0]), arguments[1])
                resultat = None
            elif methode == "start_session":
                pilote.mesures = MesuresSession()
                resultat = pilote.start_session()
            elif methode == "capture_screenshot":
                resultat = pilote.capture_screenshot(Path(arguments[0]))
            else:
                resultat = getattr(pilote, methode)(*arguments)
            reponse = {"r": _simple(resultat)}
        except Exception as erreur:  # noqa: BLE001 — l'erreur repart vers le lanceur, qui la classe
            reponse = {"e": type(erreur).__name__, "t": str(erreur)[:800]}
        sortie.write(json.dumps(reponse, default=str) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
