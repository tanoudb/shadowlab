"""Registre des moteurs. Un paquet externe ajoute un moteur par le point d'entrée `shadowlab.engines`
(nom → classe héritant de `Driver`), sans toucher au cœur."""

from __future__ import annotations

from importlib.metadata import entry_points

from .base import Driver, FonctionIndisponible, MesuresSession, RefusProtection, ResultatNavigation
from .curl_cffi_engine import DriverCurlCffi
from .httpx_engine import DriverHttpx
from .noezia import DriverNoezia
from .noezia_engine import DriverNoeziaExperimental
from .patchright_engine import DriverPatchright
from .playwright_engine import DriverPlaywright
from .pont import moteurs_isoles
from .scrapling_engine import DriverScrapling
from .scrapling_furtif import DriverScraplingFurtif
from .selenium_engine import DriverSelenium

INTEGRES: dict[str, type[Driver]] = {
    DriverPlaywright.name: DriverPlaywright,
    DriverSelenium.name: DriverSelenium,
    DriverScrapling.name: DriverScrapling,
    DriverHttpx.name: DriverHttpx,
    DriverCurlCffi.name: DriverCurlCffi,
    DriverPatchright.name: DriverPatchright,
    DriverScraplingFurtif.name: DriverScraplingFurtif,
    DriverNoeziaExperimental.name: DriverNoeziaExperimental,
    DriverNoezia.name: DriverNoezia,
}


def registre() -> dict[str, type[Driver]]:
    moteurs = {**INTEGRES, **moteurs_isoles()}
    for point in entry_points(group="shadowlab.engines"):
        moteurs.setdefault(point.name, point.load())
    return moteurs


__all__ = ["Driver", "FonctionIndisponible", "MesuresSession", "RefusProtection", "ResultatNavigation", "registre"]
