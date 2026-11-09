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
        "platform_name": {"MacIntel": "macOS", "Win32": "Windows", "Linux x86_64": "Linux"}.get(
            profil.platform, profil.platform
        ),
        "fonts": profil.fonts,
        "timezone": profil.timezone,
    }
    return f"window.__NOEZIA_PROFIL__ = {json.dumps(donnees)};"


def scripts_furtivite(
    profil: ProfilNavigateur,
    canvas: bool = True,
    webgl: bool = True,
    audio: bool = True,
    navigateur: bool = True,
) -> list[str]:
    """Retourne la liste ordonnée des scripts à injecter.

    L'ordre est important : le script profil d'abord, puis navigateur
    (qui définit natif()), puis les scripts qui l'utilisent.
    """
    scripts = [script_profil(profil)]

    if navigateur:
        scripts.append(_charger_script("navigateur.js"))

    if canvas:
        scripts.append(_charger_script("canvas.js"))

    if webgl:
        scripts.append(_charger_script("webgl.js"))

    if audio:
        scripts.append(_charger_script("audio.js"))

    return scripts


def injecter(contexte, profil: ProfilNavigateur, **kwargs) -> None:
    """Injecte tous les scripts de furtivité dans un contexte Playwright/Patchright."""
    for script in scripts_furtivite(profil, **kwargs):
        contexte.add_init_script(script)
