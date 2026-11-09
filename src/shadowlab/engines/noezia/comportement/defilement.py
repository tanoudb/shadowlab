"""Simulation de défilement (scroll) réaliste.

Modélise deux modes de scroll :
- Trackpad : geste continu avec inertie (macOS/laptop)
- Molette : ticks discrets de 120px (souris classique)

Les intervalles inter-événements suivent des distributions log-normales
(comme les délais souris), et les pauses de lecture entre gestes
suivent le modèle de humain.py.
"""

from __future__ import annotations

import math
import random
import time

from . import humain


class SimulateurDefilement:
    """Simule un défilement réaliste sur une page Playwright/Patchright."""

    def __init__(
        self,
        page,
        mode: str = "trackpad",
        pixels_par_tick: int = 120,
    ):
        self._page = page
        self._mode = mode
        self._ppt = pixels_par_tick
        self._rythme = humain.RythmeHumain(derive_sigma=0.02)

    def defiler_bas(self, distance: int | None = None) -> float:
        if distance is None:
            distance = int(humain.log_normale(300, 0.5, borne_min=80, borne_max=1200))
        return self._geste_scroll(distance)

    def defiler_haut(self, distance: int | None = None) -> float:
        if distance is None:
            distance = int(humain.log_normale(200, 0.4, borne_min=60, borne_max=600))
        return self._geste_scroll(-distance)

    def _geste_scroll(self, distance_totale: float) -> float:
        if abs(distance_totale) < 10:
            self._page.mouse.wheel(0, distance_totale)
            return distance_totale

        if self._mode == "trackpad":
            return self._scroll_trackpad(distance_totale)
        return self._scroll_molette(distance_totale)

    def _scroll_trackpad(self, distance_totale: float) -> float:
        """Geste trackpad : événements rapides avec profil bell-curve + inertie."""
        signe = 1 if distance_totale > 0 else -1
        amplitude = abs(distance_totale)

        # Phase active : 8-20 événements pendant le geste du doigt
        n_actif = max(8, min(int(amplitude / 25), 20))
        total = 0.0

        for i in range(n_actif):
            t = i / max(1, n_actif - 1)
            # Profil bell-curve (accélère puis décélère)
            vitesse = math.sin(t * math.pi)
            vitesse = max(0.15, vitesse)

            delta = (amplitude * 0.7 / n_actif) * vitesse
            delta += random.gauss(0, delta * 0.12)
            delta = max(2, min(delta, amplitude - total))

            self._page.mouse.wheel(0, signe * delta)
            total += delta

            # Intervalle ~8-16ms (60-120 Hz trackpad) avec jitter
            intervalle = humain.ex_gaussienne(12, 3, 4) / 1000.0
            time.sleep(max(0.004, intervalle))

            if total >= amplitude * 0.7:
                break

        # Phase d'inertie : 4-8 événements décroissants
        restant = amplitude - total
        if restant > 5:
            n_inertie = random.randint(4, 8)
            decroissance = random.uniform(0.55, 0.75)
            delta_inertie = restant / (n_inertie * 0.6)

            for _ in range(n_inertie):
                delta_inertie *= decroissance
                if delta_inertie < 1:
                    break
                actual = delta_inertie + random.gauss(0, delta_inertie * 0.1)
                actual = max(1, min(actual, restant))
                self._page.mouse.wheel(0, signe * actual)
                total += actual
                restant -= actual

                # Intervalles d'inertie de plus en plus longs (log-normal)
                intervalle = humain.log_normale(25, 0.4, borne_min=10, borne_max=80) / 1000.0
                time.sleep(intervalle)

                if restant < 1:
                    break

        return signe * total

    def _scroll_molette(self, distance_totale: float) -> float:
        """Scroll molette : ticks discrets avec intervalles log-normaux."""
        signe = 1 if distance_totale > 0 else -1
        restant = abs(distance_totale)
        total = 0.0

        while restant > 20:
            # Un tick = ~100-140px (variation mécanique)
            tick = self._ppt * random.uniform(0.85, 1.15)
            tick = min(tick, restant)
            self._page.mouse.wheel(0, signe * tick)
            total += tick
            restant -= tick

            # Intervalle inter-tick log-normal (médiane ~90ms pour un scroll continu)
            delai_ms = humain.log_normale(90, 0.5, borne_min=30, borne_max=400)
            delai_ms = self._rythme.moduler(delai_ms)
            time.sleep(delai_ms / 1000.0)

        return signe * total

    def lecture_page(self) -> None:
        """Simule un humain qui parcourt une page : scroll + pauses de lecture."""
        # Pause initiale (lecture du haut de page)
        time.sleep(humain.pause_lecture_ms(mots_page=80) / 1000.0)

        # 2-5 gestes de scroll entrecoupés de lecture
        n_gestes = random.randint(2, 5)
        for i in range(n_gestes):
            # Distance variable (log-normale)
            distance = int(humain.log_normale(250, 0.5, borne_min=80, borne_max=800))
            self.defiler_bas(distance)

            # Pause de lecture entre gestes (log-normale, proportionnelle au contenu)
            mots_estimes = max(20, distance // 4)
            pause = humain.pause_lecture_ms(mots_page=mots_estimes)
            pause = self._rythme.moduler(pause)
            time.sleep(pause / 1000.0)

            # Parfois un micro-scroll arrière (relecture)
            if random.random() < 0.15:
                recul = int(humain.log_normale(60, 0.4, borne_min=20, borne_max=150))
                self.defiler_haut(recul)
                time.sleep(humain.pause_reflexion_ms() / 1000.0)
