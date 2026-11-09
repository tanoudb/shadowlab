"""Validation de cohérence d'un profil navigateur.

Vérifie que les propriétés d'un profil sont mutuellement compatibles,
comme le ferait un détecteur sophistiqué : GPU cohérent avec l'OS,
résolution plausible, fonts attendues pour la plateforme, etc.
"""

from __future__ import annotations

from dataclasses import dataclass

from .generateur import (
    DEVICE_MEMORY,
    FONTS_PAR_OS,
    GPUS,
    HARDWARE_CONCURRENCY,
    RESOLUTIONS,
    ProfilNavigateur,
)


@dataclass
class Anomalie:
    code: str
    description: str
    severite: str  # "erreur" ou "avertissement"


def valider(profil: ProfilNavigateur) -> list[Anomalie]:
    """Vérifie la cohérence interne du profil. Retourne les anomalies trouvées."""
    anomalies: list[Anomalie] = []

    # GPU doit correspondre à l'OS
    gpus_os = GPUS.get(profil.os, [])
    if not any(v == profil.gpu_vendor and r == profil.gpu_renderer for v, r in gpus_os):
        anomalies.append(
            Anomalie(
                "gpu_incoherent",
                f"GPU {profil.gpu_renderer!r} pas dans la liste {profil.os}",
                "erreur",
            )
        )

    # Résolution doit être plausible pour l'OS
    rez_os = RESOLUTIONS.get(profil.os, [])
    if not any(w == profil.screen_width and h == profil.screen_height for w, h, _ in rez_os):
        anomalies.append(
            Anomalie(
                "resolution_inhabituelle",
                f"{profil.screen_width}x{profil.screen_height} inhabituel pour {profil.os}",
                "avertissement",
            )
        )

    # DPR doit correspondre à l'OS et la résolution
    dprs_attendus = [d for w, h, d in rez_os if w == profil.screen_width and h == profil.screen_height]
    if dprs_attendus and profil.device_pixel_ratio not in dprs_attendus:
        anomalies.append(
            Anomalie(
                "dpr_incoherent",
                f"DPR {profil.device_pixel_ratio} inattendu pour "
                f"{profil.screen_width}x{profil.screen_height} sur {profil.os}",
                "avertissement",
            )
        )

    # Platform JS doit correspondre à l'OS
    attendu = {"macos": "MacIntel", "windows": "Win32", "linux": "Linux x86_64"}
    if profil.platform != attendu.get(profil.os, ""):
        anomalies.append(
            Anomalie(
                "platform_incoherent",
                f"platform={profil.platform!r} pour os={profil.os}",
                "erreur",
            )
        )

    # UA doit contenir les indices de l'OS
    ua = profil.user_agent.lower()
    if profil.os == "macos" and "macintosh" not in ua:
        anomalies.append(Anomalie("ua_sans_mac", "UA macOS sans 'Macintosh'", "erreur"))
    if profil.os == "windows" and "windows" not in ua:
        anomalies.append(Anomalie("ua_sans_windows", "UA Windows sans 'Windows'", "erreur"))
    if profil.os == "linux" and "linux" not in ua:
        anomalies.append(Anomalie("ua_sans_linux", "UA Linux sans 'Linux'", "erreur"))

    # Chrome version dans l'UA doit correspondre
    if f"chrome/{profil.chrome_full}" not in ua:
        anomalies.append(
            Anomalie(
                "ua_version_chrome",
                f"UA ne contient pas Chrome/{profil.chrome_full}",
                "erreur",
            )
        )

    # Hardware concurrency plausible
    hw_os = HARDWARE_CONCURRENCY.get(profil.os, [])
    if hw_os and profil.hardware_concurrency not in hw_os:
        anomalies.append(
            Anomalie(
                "hw_concurrency_inhabituel",
                f"hardwareConcurrency={profil.hardware_concurrency} inhabituel pour {profil.os}",
                "avertissement",
            )
        )

    # Device memory plausible
    dm_os = DEVICE_MEMORY.get(profil.os, [])
    if dm_os and profil.device_memory not in dm_os:
        anomalies.append(
            Anomalie(
                "device_memory_inhabituel",
                f"deviceMemory={profil.device_memory} inhabituel pour {profil.os}",
                "avertissement",
            )
        )

    # Fonts de base de l'OS doivent être présentes
    fonts_base = FONTS_PAR_OS.get(profil.os, [])[:5]
    manquantes = [f for f in fonts_base if f not in profil.fonts]
    if manquantes:
        anomalies.append(
            Anomalie(
                "fonts_manquantes",
                f"Fonts de base manquantes pour {profil.os} : {manquantes}",
                "avertissement",
            )
        )

    # sec-ch-ua-platform doit correspondre à l'OS
    plat_attendu = {"macos": '"macOS"', "windows": '"Windows"', "linux": '"Linux"'}
    if profil.sec_ch_ua_platform != plat_attendu.get(profil.os, ""):
        anomalies.append(
            Anomalie(
                "client_hints_platform",
                f"Sec-CH-UA-Platform={profil.sec_ch_ua_platform!r} incohérent avec {profil.os}",
                "erreur",
            )
        )

    # Locale et timezone doivent être plausibles ensemble
    _verifier_locale_tz(profil, anomalies)

    # Canvas et audio seeds doivent être non-nuls et différents
    if profil.canvas_seed == 0:
        anomalies.append(Anomalie("canvas_seed_nul", "canvas_seed = 0 (pas de variation)", "erreur"))
    if profil.canvas_seed == profil.audio_seed:
        anomalies.append(Anomalie("seeds_identiques", "canvas_seed == audio_seed", "avertissement"))

    return anomalies


LOCALE_TZ_COMPATIBLES: dict[str, set[str]] = {
    "fr-FR": {"Europe/Paris", "Europe/Brussels", "Europe/Luxembourg", "Europe/Monaco"},
    "en-US": {
        "America/New_York",
        "America/Chicago",
        "America/Denver",
        "America/Los_Angeles",
        "America/Phoenix",
        "America/Anchorage",
        "Pacific/Honolulu",
    },
    "en-GB": {"Europe/London"},
    "de-DE": {"Europe/Berlin", "Europe/Vienna", "Europe/Zurich"},
    "es-ES": {"Europe/Madrid"},
}


def _verifier_locale_tz(profil: ProfilNavigateur, anomalies: list[Anomalie]) -> None:
    compatibles = LOCALE_TZ_COMPATIBLES.get(profil.locale)
    if compatibles and profil.timezone not in compatibles:
        anomalies.append(
            Anomalie(
                "locale_tz_incoherent",
                f"locale={profil.locale} avec timezone={profil.timezone}",
                "avertissement",
            )
        )
