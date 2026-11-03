"""Pilote undetected-chromedriver : chromedriver modifié pour échapper aux détecteurs, sans réglage ajouté (D-15)."""

from __future__ import annotations

import importlib.metadata
from typing import Any

from ..base import MANDATAIRE_BLOQUANT, liste_directe
from ..selenium_engine import DriverSelenium


class DriverUndetectedChromedriver(DriverSelenium):
    name = "undetected-chromedriver"
    categorie = "anti_detection"
    options_permises = {"headless": bool}

    def configuration(self) -> dict[str, Any]:
        return {"browser": "chrome", "headless": True, "tls_non_verifie": True, **self.options}

    def versions(self) -> dict[str, str]:
        versions = super().versions()
        versions["undetected-chromedriver"] = importlib.metadata.version("undetected-chromedriver")
        return versions

    def open(self) -> None:
        import undetected_chromedriver as uc

        options = uc.ChromeOptions()
        options.add_argument(f"--proxy-server={MANDATAIRE_BLOQUANT}")
        options.add_argument(f"--proxy-bypass-list={';'.join(liste_directe(self.hotes_autorises))}")
        options.add_argument("--ignore-certificate-errors")
        self._pilote = uc.Chrome(options=options, headless=self.configuration()["headless"])
        self._pilote.set_page_load_timeout(30)
