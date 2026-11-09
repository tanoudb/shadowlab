"""Orchestration des scripts de furtivité.

Charge les scripts JS, les paramètre avec le profil, et les injecte dans le contexte
navigateur via add_init_script (exécutés avant tout JS de la page).
"""

from __future__ import annotations

import json
from pathlib import Path

from ..profils.generateur import ProfilNavigateur

SCRIPTS_DIR = Path(__file__).parent


def _charger_script(nom: str) -> str:
    """Charge un script JS depuis le répertoire furtivite/."""
    chemin = SCRIPTS_DIR / nom
    return chemin.read_text(encoding="utf-8")


def script_profil(profil: ProfilNavigateur) -> str:
    """Génère le script d'injection du profil dans window.__NOEZIA_PROFIL__."""
    donnees = {
        "canvas_seed": profil.canvas_seed,
        "audio_seed": profil.audio_seed,
        "gpu_vendor": profil.gpu_vendor,
        "gpu_renderer": profil.gpu_renderer,
        "webgl_extensions": profil.webgl_extensions,
        "hardware_concurrency": profil.hardware_concurrency,
        "device_memory": profil.device_memory,
        "platform": profil.platform,
        "platform_name": profil.platform_name,
        "fonts": profil.fonts,
        "timezone": profil.timezone,
        "screen_width": profil.screen_width,
        "screen_height": profil.screen_height,
        "device_pixel_ratio": profil.device_pixel_ratio,
        "locale": profil.locale,
    }
    return f"window.__NOEZIA_PROFIL__ = {json.dumps(donnees)};"


def scripts_furtivite(
    profil: ProfilNavigateur,
    canvas: bool = True,
    webgl: bool = True,
    audio: bool = True,
    navigateur: bool = True,
    environnement: bool = True,
    iframes: bool = True,
    codecs: bool = True,
    polices: bool = True,
    headless: bool = True,
    automation: bool = True,
    workers: bool = True,
    cdp: bool = True,
) -> list[str]:
    """Retourne la liste ordonnée des scripts à injecter.

    L'ordre est important : le script profil d'abord, puis navigateur
    (qui définit natif()), puis les scripts qui l'utilisent.
    """
    scripts = [script_profil(profil)]

    if navigateur:
        scripts.append(_charger_script("navigateur.js"))

    if iframes:
        scripts.append(_charger_script("iframes.js"))

    if environnement:
        scripts.append(_charger_script("environnement.js"))

    if canvas:
        scripts.append(_charger_script("canvas.js"))

    if webgl:
        scripts.append(_charger_script("webgl.js"))

    if audio:
        scripts.append(_charger_script("audio.js"))

    if codecs:
        scripts.append(_charger_script("codecs.js"))

    if polices:
        scripts.append(_charger_script("polices.js"))

    if headless:
        scripts.append(_charger_script("headless.js"))

    if workers:
        scripts.append(_charger_script("workers.js"))

    if cdp:
        scripts.append(_charger_script("cdp.js"))

    if automation:
        scripts.append(_charger_script("automation.js"))

    return scripts


def injecter(contexte, profil: ProfilNavigateur, **kwargs) -> None:
    """Injecte tous les scripts de furtivité dans un contexte Playwright/Patchright."""
    for script in scripts_furtivite(profil, **kwargs):
        contexte.add_init_script(script)
