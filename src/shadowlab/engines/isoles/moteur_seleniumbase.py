"""Pilotes SeleniumBase : mode normal et mode UC (anti-détection)."""

from __future__ import annotations

import importlib.metadata
from typing import Any

from ..base import liste_directe
from ..selenium_engine import DriverSelenium


class DriverSeleniumBase(DriverSelenium):
    name = "seleniumbase"
    uc = False
    options_permises = {"headless": bool}

    def configuration(self) -> dict[str, Any]:
        return {"browser": "chrome", "headless": True, "uc": self.uc, "tls_non_verifie": True, **self.options}

    def versions(self) -> dict[str, str]:
        versions = super().versions()
        versions["seleniumbase"] = importlib.metadata.version("seleniumbase")
        return versions

    def open(self) -> None:
        from seleniumbase import Driver

        self._pilote = Driver(
            browser="chrome",
            headless=self.configuration()["headless"],
            uc=self.uc,
            proxy="127.0.0.1:9",  # verrou réseau : voir MANDATAIRE_BLOQUANT
            proxy_bypass_list=";".join(liste_directe(self.hotes_autorises)),
            chromium_arg="--ignore-certificate-errors",
        )
        self._pilote.set_page_load_timeout(30)


class DriverSeleniumBaseUc(DriverSeleniumBase):
    name = "seleniumbase-uc"
    categorie = "anti_detection"
    uc = True
