"""Pilote Camoufox : Firefox modifié pour échapper aux détecteurs, utilisé dans sa configuration par défaut (D-15)."""

from __future__ import annotations

import importlib.metadata
from typing import Any

from ..base import MANDATAIRE_BLOQUANT, liste_directe
from ..playwright_engine import DriverPlaywright


class DriverCamoufox(DriverPlaywright):
    name = "camoufox"
    categorie = "anti_detection"
    options_permises = {"headless": bool, "humanize": bool, "os": str}

    def configuration(self) -> dict[str, Any]:
        return {"browser": "camoufox", "headless": True, "trace": False, "tls_non_verifie": True, **self.options}

    def versions(self) -> dict[str, str]:
        versions = {
            "camoufox": importlib.metadata.version("camoufox"),
            "playwright": importlib.metadata.version("playwright"),
        }
        if getattr(self, "_navigateur", None) is not None:
            versions["firefox"] = self._navigateur.version
        return versions

    def open(self) -> None:
        from camoufox.sync_api import Camoufox

        reglages = {k: v for k, v in self.options.items() if k != "trace"}
        verrou = {"server": MANDATAIRE_BLOQUANT, "bypass": ",".join(liste_directe(self.hotes_autorises))}
        self._gestion = Camoufox(**{"headless": True, **reglages}, proxy=verrou, i_know_what_im_doing=True)
        self._navigateur = self._gestion.__enter__()

    def close(self) -> None:
        if getattr(self, "_navigateur", None) is not None:
            self._gestion.__exit__(None, None, None)
            self._navigateur = None
