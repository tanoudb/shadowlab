"""Pilote du navigateur furtif de Scrapling (`StealthySession`, Patchright + réglages d'empreinte), D-15.

Les réglages de la session restent ceux de Scrapling. Le scénario pilote directement son contexte de navigation,
car `fetch()` ne permet pas d'enchaîner des actions : ce qui ne s'applique que dans `fetch()` (faux référent Google)
n'est donc pas mesuré. `solve_cloudflare` reste coupé et n'est pas proposé : aucun solveur dans ce laboratoire.
"""

from __future__ import annotations

import importlib.metadata
from typing import Any

from .base import MANDATAIRE_BLOQUANT, liste_directe
from .playwright_engine import DriverPlaywright


class DriverScraplingFurtif(DriverPlaywright):
    name = "scrapling-furtif"
    categorie = "anti_detection"
    options_permises = {"headless": bool, "hide_canvas": bool, "real_chrome": bool}

    def configuration(self) -> dict[str, Any]:
        return {"session": "StealthySession", "headless": True, "trace": False, "tls_non_verifie": True, **self.options}

    def versions(self) -> dict[str, str]:
        return {
            "scrapling": importlib.metadata.version("scrapling"),
            "patchright": importlib.metadata.version("patchright"),
        }

    def open(self) -> None:
        from scrapling.fetchers import StealthySession

        drapeaux = (
            f"--proxy-server={MANDATAIRE_BLOQUANT}",
            f"--proxy-bypass-list={';'.join(liste_directe(self.hotes_autorises))}",
        )
        self._session = StealthySession(
            **{"headless": True, **self.options},
            extra_flags=drapeaux,
            additional_args={"ignore_https_errors": True},
        )
        self._session.start()
        self._partage = self._session.context
        self._partage.route("**/*", self._filtrer)

    def close(self) -> None:
        if getattr(self, "_session", None) is not None:
            self._session.close()
            self._session = None

    def _nouveau_contexte(self):
        self._partage.clear_cookies()  # contexte persistant unique : on repart sans cookies à chaque passage
        return self._partage

    def _fermer_contexte(self) -> None:
        self._page.close()
