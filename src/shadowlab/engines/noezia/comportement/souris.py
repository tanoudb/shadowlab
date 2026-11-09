"""Modèle de mouvement de souris basé sur le contrôle moteur humain.

Utilise la trajectoire à minimum-jerk (Flash & Hogan 1985) pour le mouvement principal,
la loi de Fitts pour le temps de mouvement, et des submovements correctifs pour simuler
l'approche finale vers une cible. Le bruit est corrélé à la vitesse instantanée.

Références :
- Flash T., Hogan N. (1985). The coordination of arm movements.
- Fitts P.M. (1954). The information capacity of the human motor system.
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass


@dataclass
class PointSouris:
    x: float
    y: float
    t: float  # temps relatif en secondes


def minimum_jerk(t: float) -> float:
    """Polynôme à minimum-jerk : s(t) = 10t³ - 15t⁴ + 6t⁵, t ∈ [0, 1]."""
    t2 = t * t
    t3 = t2 * t
    return 10.0 * t3 - 15.0 * t2 * t2 + 6.0 * t2 * t3


def temps_fitts(distance: float, largeur_cible: float, a: float = 50.0, b: float = 150.0) -> float:
    """Temps de mouvement selon la loi de Fitts (ms). ID = log₂(D/W + 1)."""
    if distance < 1.0:
        return a
    indice = math.log2(distance / max(largeur_cible, 1.0) + 1.0)
    return a + b * indice


def _bruit_mouvement(vitesse: float, amplitude: float = 0.15) -> float:
    """Bruit corrélé à la vitesse : plus on va vite, plus le bruit est grand."""
    sigma = amplitude * (1.0 + vitesse * 0.002)
    return random.gauss(0, sigma)


def trajectoire(
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    largeur_cible: float = 20.0,
    a: float = 50.0,
    b: float = 150.0,
    overshoot: bool = False,
) -> list[PointSouris]:
    """Génère une trajectoire réaliste de (x0, y0) vers (x1, y1).

    Retourne une liste de points avec timestamps relatifs.
    """
    distance = math.hypot(x1 - x0, y1 - y0)
    if distance < 2.0:
        return [PointSouris(x1, y1, 0.0)]

    duree_ms = temps_fitts(distance, largeur_cible, a, b)
    duree_ms *= random.uniform(0.85, 1.15)
    duree_s = duree_ms / 1000.0

    # Nombre de points proportionnel à la distance et la durée
    n_points = max(8, min(int(distance / 4.0 + duree_ms / 8.0), 120))

    points: list[PointSouris] = []
    angle = math.atan2(y1 - y0, x1 - x0)

    # Courbure naturelle : légère déviation perpendiculaire
    courbure = random.gauss(0, distance * 0.08)
    perp_x = -math.sin(angle) * courbure
    perp_y = math.cos(angle) * courbure

    for i in range(n_points + 1):
        t_norm = i / n_points
        s = minimum_jerk(t_norm)

        # Position sur la ligne droite + courbure
        courbe = 4.0 * t_norm * (1.0 - t_norm)  # max au milieu
        bx = x0 + (x1 - x0) * s + perp_x * courbe
        by = y0 + (y1 - y0) * s + perp_y * courbe

        # Vitesse instantanée (dérivée du minimum-jerk)
        ds = 30.0 * t_norm * t_norm - 60.0 * t_norm * t_norm * t_norm + 30.0 * t_norm**4
        vitesse = ds * distance / duree_s if duree_s > 0 else 0

        # Bruit proportionnel à la vitesse
        if 0 < i < n_points:
            bx += _bruit_mouvement(vitesse)
            by += _bruit_mouvement(vitesse)

        # Timing avec jitter humain (CV cible > 0.20)
        t_s = t_norm * duree_s
        if 0 < i < n_points:
            intervalle = duree_s / n_points
            jitter = random.gauss(0, intervalle * 0.40)
            # Micro-hésitation (~8% des points) : pause 50-300ms
            if random.random() < 0.08:
                jitter += random.uniform(0.05, 0.30)
            # Clamper pour ne jamais dépasser le point final
            t_s = max(0, min(t_s + jitter, duree_s - 0.001))

        points.append(PointSouris(max(0, bx), max(0, by), max(0, t_s)))

    # Overshoot : dépasse la cible puis corrige
    if overshoot and distance > 50:
        os_dist = random.uniform(3, min(12, distance * 0.06))
        os_x = x1 + math.cos(angle) * os_dist + random.gauss(0, 1)
        os_y = y1 + math.sin(angle) * os_dist + random.gauss(0, 1)
        t_os = duree_s + random.uniform(0.03, 0.08)
        points.append(PointSouris(os_x, os_y, t_os))
        # Correction
        correction = _submouvement(os_x, os_y, x1, y1, t_os)
        points.extend(correction)

    # Tri par temps (l'overshoot peut désorganiser)
    points.sort(key=lambda p: p.t)
    return points


def _submouvement(x0: float, y0: float, x1: float, y1: float, t_debut: float) -> list[PointSouris]:
    """Micro-correction vers la cible (submovement). Plus court et plus lent."""
    dist = math.hypot(x1 - x0, y1 - y0)
    duree = random.uniform(0.04, 0.12)
    n = max(3, int(dist / 2))
    pts: list[PointSouris] = []
    for i in range(1, n + 1):
        t = i / n
        s = minimum_jerk(t)
        px = x0 + (x1 - x0) * s + (random.gauss(0, 0.3) if i < n else 0)
        py = y0 + (y1 - y0) * s + (random.gauss(0, 0.3) if i < n else 0)
        pts.append(PointSouris(px, py, t_debut + t * duree))
    return pts


class SimulateurSouris:
    """Gère le mouvement de souris sur une page Playwright/Patchright."""

    def __init__(
        self,
        page,
        viewport_w: int = 1920,
        viewport_h: int = 1080,
        a: float = 50.0,
        b: float = 150.0,
        overshoot_proba: float = 0.12,
        bruit_vitesse: float = 0.15,
    ):
        self._page = page
        self._vw = viewport_w
        self._vh = viewport_h
        self._a = a
        self._b = b
        self._overshoot_proba = overshoot_proba
        self._bruit = bruit_vitesse
        self._x = random.uniform(self._vw * 0.2, self._vw * 0.5)
        self._y = random.uniform(self._vh * 0.2, self._vh * 0.5)
        self._derniere_action = time.monotonic()

    def deplacer_vers(self, x: float, y: float, largeur_cible: float = 20.0) -> None:
        """Déplace la souris vers (x, y) avec un mouvement réaliste."""
        overshoot = random.random() < self._overshoot_proba
        pts = trajectoire(
            self._x,
            self._y,
            x,
            y,
            largeur_cible=largeur_cible,
            a=self._a,
            b=self._b,
            overshoot=overshoot,
        )

        t_prec = 0.0
        for pt in pts:
            delai = pt.t - t_prec
            if delai > 0.001:
                time.sleep(delai)
            px = max(0, min(self._vw - 1, pt.x))
            py = max(0, min(self._vh - 1, pt.y))
            self._page.mouse.move(px, py)
            t_prec = pt.t

        self._x = x
        self._y = y
        self._derniere_action = time.monotonic()

    def deplacer_vers_element(self, selector: str) -> None:
        """Déplace vers le centre d'un élément avec un léger décalage humain."""
        try:
            box = self._page.eval_on_selector(
                selector,
                "e => { const r = e.getBoundingClientRect(); return {x: r.x, y: r.y, w: r.width, h: r.height}; }",
            )
            if not box:
                return
            # Clic pas exactement au centre — décalage gaussien
            cx = box["x"] + box["w"] / 2 + random.gauss(0, box["w"] * 0.1)
            cy = box["y"] + box["h"] / 2 + random.gauss(0, box["h"] * 0.1)
            cx = max(box["x"] + 2, min(box["x"] + box["w"] - 2, cx))
            cy = max(box["y"] + 2, min(box["y"] + box["h"] - 2, cy))
            largeur = min(box["w"], box["h"])
            self.deplacer_vers(cx, cy, largeur_cible=largeur)
        except Exception:
            pass

    def mouvement_aleatoire(self) -> None:
        """Mouvement oisif — la souris bouge un peu pendant la lecture."""
        # Pause pré-mouvement (humain ne bouge pas en continu)
        time.sleep(random.uniform(0.1, 0.6))
        x = self._x + random.gauss(0, 80)
        y = self._y + random.gauss(0, 60)
        x = max(20, min(self._vw - 20, x))
        y = max(20, min(self._vh - 20, y))
        self.deplacer_vers(x, y, largeur_cible=100.0)

    @property
    def position(self) -> tuple[float, float]:
        return self._x, self._y
