"""Pilote Patchright : Playwright modifié pour masquer les traces de l'automatisation, sans réglage ajouté (D-15)."""

from __future__ import annotations

import importlib.metadata

from .playwright_engine import DriverPlaywright


class DriverPatchright(DriverPlaywright):
    name = "patchright"
    categorie = "anti_detection"

    def _api(self):
        from patchright.sync_api import sync_playwright

        return sync_playwright

    def versions(self) -> dict[str, str]:
        versions = {"patchright": importlib.metadata.version("patchright")}
        if getattr(self, "_navigateur", None) is not None:
            versions["chromium"] = self._navigateur.version
        return versions
