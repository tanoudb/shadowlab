"""Ordonnanceur des visites d'un visiteur régulier (coquille : le code vient au commit suivant)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Reglages:
    plage: tuple[int, int] = (8, 23)
    ecart_min_min: float = 45
    ecart_med_min: float = 90
    ecart_max_min: float = 180
    pages_min: int = 5
    pages_med: int = 15
    pages_max: int = 40
    pages_par_heure: int = 120
    pages_par_jour: int = 200
    rythme_visite: object = None


@dataclass(frozen=True)
class Visite:
    debut: datetime
    pages: int


class Ordonnanceur:
    def __init__(self, reglages=None, alea=None, horloge=datetime.now, dormir=None) -> None:
        self._horloge = horloge
        self._dormir = dormir

    def prochaine(self) -> Visite:
        return Visite(self._horloge(), 0)

    def attendre_prochaine(self) -> Visite:
        self._dormir(3600)
        return self.prochaine()

    def terminer(self, visite: Visite, pages_lues: int) -> None:
        pass

    def rejouer(self, visites) -> None:
        pass
