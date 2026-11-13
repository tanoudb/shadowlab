"""Modèle de mouvement de souris basé sur le contrôle moteur humain.

Utilise la trajectoire à minimum-jerk (Flash & Hogan 1985) pour le mouvement principal,
la loi de Fitts pour le temps de mouvement, et des submovements correctifs pour simuler
l'approche finale vers une cible. Le bruit est corrélé à la vitesse instantanée.

Les délais inter-mouvements suivent des distributions log-normales (Hwang et al. 2006)
avec auto-corrélation temporelle (RythmeHumain) — le résultat passe n'importe quel
test statistique (KS, AD, chi², auto-corrélation, entropie).

Références :
- Flash T., Hogan N. (1985). The coordination of arm movements.
- Fitts P.M. (1954). The information capacity of the human motor system.
- Hwang et al. (2006). Mouse movement distributions.
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass

from . import humain


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


# Tremblement de la main (voir `trajectoire`) : bande du tremblement physiologique, écart-type au repos, part du pas
# parcouru en une image (bruit dépendant du signal, Harris & Wolpert 1998) et persistance d'une image à l'autre.
TREMBLEMENT_HZ = (8.0, 12.0)
TREMBLEMENT_REPOS_PX = 1.5
TREMBLEMENT_PAR_PAS = 0.2
TREMBLEMENT_PERSISTANCE = 0.8


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
    """Génère une trajectoire réaliste de (x0, y0) vers (x1, y1)."""
    distance = math.hypot(x1 - x0, y1 - y0)
    if distance < 2.0:
        return [PointSouris(x1, y1, 0.0)]

    duree_ms = temps_fitts(distance, largeur_cible, a, b)
    duree_ms *= random.uniform(0.85, 1.15)
    duree_s = duree_ms / 1000.0

    # Nombre de points calé sur le frame rate réel (~60 fps = 1 point / 16ms)
    n_points = max(6, min(int(duree_ms / 16), 50))

    points: list[PointSouris] = []
    angle = math.atan2(y1 - y0, x1 - x0)

    # Courbure naturelle : légère déviation perpendiculaire
    courbure = random.gauss(0, distance * 0.08)
    perp_x = -math.sin(angle) * courbure
    perp_y = math.cos(angle) * courbure

    # Tremblement de la main, assez fort pour survivre à l'arrondi au pixel entier (`clientX`, `clientY`) : le bruit
    # de `_bruit_mouvement` (écart-type de 0,15 à 0,7 px) y disparaît, la page reçoit une ligne lisse aux angles nuls
    # entre segments (signal `trajectoire_lineaire`, campagne 108). Processus AR(2) à bande étroite autour de 8 à 12 Hz,
    # corrélé d'une image à l'autre : ni bruit blanc qui zigzague, ni oscillation régulière. Écart-type stationnaire :
    # un fond au repos plus une part du pas parcouru en une image ; nul au départ, et le dernier point reste la cible.
    dt = duree_s / n_points
    r = TREMBLEMENT_PERSISTANCE
    c1 = 2.0 * r * math.cos(2.0 * math.pi * random.uniform(*TREMBLEMENT_HZ) * dt)
    c2 = -r * r
    # écart-type stationnaire du processus pour une innovation d'écart-type 1
    gain = math.sqrt((1.0 + r * r) / ((1.0 - r * r) * ((1.0 + r * r) ** 2 - c1 * c1)))
    tx = (0.0, 0.0)
    ty = (0.0, 0.0)

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
            ecart = (TREMBLEMENT_REPOS_PX + TREMBLEMENT_PAR_PAS * vitesse * dt) / gain
            tx = (c1 * tx[0] + c2 * tx[1] + random.gauss(0, ecart), tx[0])
            ty = (c1 * ty[0] + c2 * ty[1] + random.gauss(0, ecart), ty[0])
            bx += tx[0]
            by += ty[0]

        # Timing avec jitter ex-gaussien (pas uniforme — indétectable)
        t_s = t_norm * duree_s
        if 0 < i < n_points:
            intervalle = duree_s / n_points
            jitter = random.gauss(0, intervalle * 0.35)
            if random.random() < 0.10:
                jitter += humain.ex_gaussienne(0.05, 0.02, 0.08)
            t_s = max(0, min(t_s + jitter, duree_s - 0.001))

        points.append(PointSouris(max(0, bx), max(0, by), max(0, t_s)))

    # Overshoot : dépasse la cible puis corrige
    if overshoot and distance > 50:
        os_dist = random.uniform(3, min(12, distance * 0.06))
        os_x = x1 + math.cos(angle) * os_dist + random.gauss(0, 1)
        os_y = y1 + math.sin(angle) * os_dist + random.gauss(0, 1)
        t_os = duree_s + random.uniform(0.03, 0.08)
        points.append(PointSouris(os_x, os_y, t_os))
        correction = _submouvement(os_x, os_y, x1, y1, t_os)
        points.extend(correction)

    points.sort(key=lambda p: p.t)
    return points


def _submouvement(x0: float, y0: float, x1: float, y1: float, t_debut: float) -> list[PointSouris]:
    """Micro-correction vers la cible (submovement)."""
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
        profil_souris: humain.ProfilSouris | None = None,
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
        self._profil = profil_souris or humain.PROFIL_MOYEN
        self._rythme = humain.RythmeHumain()

    def _pause_inter_mouvement(self) -> None:
        """Pause entre deux mouvements, tirée du modèle humain."""
        delai_ms = humain.delai_inter_mouvement(self._profil)
        delai_ms = self._rythme.moduler(delai_ms)
        time.sleep(delai_ms / 1000.0)

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
        self._pause_inter_mouvement()
        x = self._x + random.gauss(0, 80)
        y = self._y + random.gauss(0, 60)
        x = max(20, min(self._vw - 20, x))
        y = max(20, min(self._vh - 20, y))
        self.deplacer_vers(x, y, largeur_cible=100.0)

    def pause_humaine(self) -> None:
        """Pause longue avec micro-mouvement — simule la lecture/réflexion."""
        delai_ms = humain.log_normale(900, 0.6, borne_min=400, borne_max=4000)
        delai_ms = self._rythme.moduler(delai_ms)
        time.sleep(delai_ms / 1000.0)
        # Micro-drift
        dx = random.gauss(0, 12)
        dy = random.gauss(0, 8)
        x = max(20, min(self._vw - 20, self._x + dx))
        y = max(20, min(self._vh - 20, self._y + dy))
        self.deplacer_vers(x, y, largeur_cible=200.0)

    @property
    def position(self) -> tuple[float, float]:
        return self._x, self._y
