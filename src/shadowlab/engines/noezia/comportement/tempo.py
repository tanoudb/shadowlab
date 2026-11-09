"""Rythme humain : pauses de réflexion, lecture, hésitation.

Toutes les pauses utilisent les distributions de `humain.py` —
log-normales et ex-gaussiennes calibrées sur la littérature,
pas des uniform() détectables par un test de distribution.
"""

from __future__ import annotations

import time

from . import humain


def pause_lecture(longueur_estimee: int = 200) -> None:
    """Pause de lecture proportionnelle au contenu."""
    time.sleep(humain.pause_lecture_ms(longueur_estimee) / 1000.0)


def pause_reflexion() -> None:
    """Pause de réflexion entre deux actions."""
    time.sleep(humain.pause_reflexion_ms() / 1000.0)


def pause_avant_clic() -> None:
    """Court délai avant un clic (temps de réaction + visée)."""
    time.sleep(humain.pause_avant_action_ms() / 1000.0)


def pause_apres_navigation() -> None:
    """Pause après le chargement d'une page."""
    time.sleep(humain.pause_apres_navigation_ms() / 1000.0)


def pause_entre_pages() -> None:
    """Pause entre deux navigations consécutives."""
    time.sleep(humain.pause_entre_pages_ms() / 1000.0)


def hesitation(proba: float = 0.12) -> None:
    """Hésitation occasionnelle."""
    ms = humain.pause_hesitation_ms(proba)
    if ms > 0:
        time.sleep(ms / 1000.0)
