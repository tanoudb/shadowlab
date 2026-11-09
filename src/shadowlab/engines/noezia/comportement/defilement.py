"""Simulation de défilement (scroll) avec inertie.

Un humain ne scrolle pas de manière uniforme. Il y a :
- Une phase d'accélération (début du geste)
- Une vitesse de croisière
- Une décélération (fin du geste, inertie)
- Des pauses entre les gestes pour lire
"""

from __future__ import annotations

import random
import time


class SimulateurDefilement:
    """Simule un défilement réaliste sur une page."""

    def __init__(
        self,
        page,
        pixels_par_tick: int = 120,
        ticks_min: int = 1,
        ticks_max: int = 8,
    ):
        self._page = page
        self._ppt = pixels_par_tick
        self._tmin = ticks_min
        self._tmax = ticks_max
        self._rng = random.Random()

    def defiler_bas(self, distance: int | None = None) -> float:
        """Scrolle vers le bas. Retourne la distance réelle scrollée.

        Si distance est None, scrolle un peu (comme un humain qui lit).
        """
        if distance is None:
            ticks = self._rng.randint(self._tmin, self._tmax)
            distance = ticks * self._ppt

        return self._scroll_inertiel(distance)

    def defiler_haut(self, distance: int | None = None) -> float:
        """Scrolle vers le haut."""
        if distance is None:
            ticks = self._rng.randint(self._tmin, min(3, self._tmax))
            distance = ticks * self._ppt

        return self._scroll_inertiel(-distance)

    def _scroll_inertiel(self, distance_totale: float) -> float:
        """Scroll avec profil d'accélération/décélération réaliste."""
        if abs(distance_totale) < 10:
            self._page.mouse.wheel(0, distance_totale)
            return distance_totale

        signe = 1 if distance_totale > 0 else -1
        restant = abs(distance_totale)
        total_scrolle = 0.0
        n_etapes = self._rng.randint(3, max(4, int(restant / 80)))

        for i in range(n_etapes):
            # Profil sinusoïdal : accélère, croisière, décélère
            import math

            t = i / max(1, n_etapes - 1)
            facteur = math.sin(t * math.pi)  # 0 → 1 → 0
            facteur = max(0.2, facteur)

            portion = restant / (n_etapes - i) * facteur * self._rng.uniform(0.8, 1.2)
            portion = min(portion, restant)
            portion = max(10, portion)

            self._page.mouse.wheel(0, signe * portion)
            total_scrolle += portion

            # Délai entre les étapes : plus rapide au milieu
            delai = self._rng.uniform(0.015, 0.06) / max(0.5, facteur)
            time.sleep(delai)

            restant -= portion
            if restant <= 5:
                break

        return signe * total_scrolle

    def lecture_page(self) -> None:
        """Simule un humain qui lit une page : scroll progressif avec pauses."""
        # Lire le haut de la page d'abord
        time.sleep(self._rng.uniform(0.5, 1.5))

        # 2-4 gestes de scroll avec pauses de lecture entre
        n_gestes = self._rng.randint(2, 4)
        for _ in range(n_gestes):
            distance = self._rng.randint(100, 400)
            self.defiler_bas(distance)
            # Pause de lecture : proportionnelle à la distance scrollée
            pause = self._rng.uniform(0.3, 1.2) * (distance / 200.0)
            time.sleep(pause)
