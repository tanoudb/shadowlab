"""Registre des moteurs. Un paquet externe ajoute un moteur par le point d'entrée `shadowlab.engines`
(nom → classe héritant de `Driver`), sans toucher au cœur."""

from __future__ import annotations

from importlib.metadata import entry_points

from .base import Driver, FonctionIndisponible, MesuresSession, ResultatNavigation
from .httpx_engine import DriverHttpx
from .playwright_engine import DriverPlaywright
from .scrapling_engine import DriverScrapling
from .selenium_engine import DriverSelenium

INTEGRES: dict[str, type[Driver]] = {
    DriverPlaywright.name: DriverPlaywright,
    DriverSelenium.name: DriverSelenium,
    DriverScrapling.name: DriverScrapling,
    DriverHttpx.name: DriverHttpx,
}


def registre() -> dict[str, type[Driver]]:
    moteurs = dict(INTEGRES)
    for point in entry_points(group="shadowlab.engines"):
        moteurs.setdefault(point.name, point.load())
    return moteurs


__all__ = ["Driver", "FonctionIndisponible", "MesuresSession", "ResultatNavigation", "registre"]
