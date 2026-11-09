"""Rythme humain : pauses de réflexion, lecture, hésitation.

Un humain ne clique pas instantanément après le chargement d'une page.
Il regarde, lit, hésite, puis agit. Ce module simule ces pauses.
"""

from __future__ import annotations

import math
import random
import time


def pause_lecture(longueur_estimee: int = 200) -> None:
    """Pause de lecture proportionnelle au contenu.

    longueur_estimee : nombre de mots approximatif sur la page.
    Un humain lit à ~250 mots/min en scan, ~200 en lecture attentive.
    On simule un scan partiel (30-60% de la page).
    """
    mots_lus = longueur_estimee * random.uniform(0.3, 0.6)
    duree_s = mots_lus / random.uniform(200, 300)
    duree_s = max(0.3, min(5.0, duree_s))
    duree_s *= random.uniform(0.8, 1.2)
    time.sleep(duree_s)


def pause_reflexion() -> None:
    """Pause de réflexion entre deux actions (distribution log-normale)."""
    duree = random.lognormvariate(math.log(0.15), 0.5)
    duree = max(0.05, min(2.0, duree))
    time.sleep(duree)


def pause_avant_clic() -> None:
    """Court délai avant un clic (le temps de viser)."""
    time.sleep(random.uniform(0.03, 0.12))


def pause_apres_navigation() -> None:
    """Pause après le chargement d'une page (le temps de voir où on est)."""
    time.sleep(random.uniform(0.4, 1.2))


def pause_entre_pages() -> None:
    """Pause entre deux navigations consécutives."""
    duree = random.lognormvariate(math.log(0.8), 0.6)
    duree = max(0.3, min(4.0, duree))
    time.sleep(duree)


def hesitation(proba: float = 0.15) -> None:
    """Hésitation occasionnelle : l'humain s'arrête un instant."""
    if random.random() < proba:
        time.sleep(random.uniform(0.5, 2.0))
