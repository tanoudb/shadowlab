"""Validation de cohérence d'un profil navigateur.

Vérifie que les propriétés d'un profil sont mutuellement compatibles,
comme le ferait un détecteur sophistiqué : GPU cohérent avec l'OS,
résolution plausible, fonts attendues pour la plateforme, etc.
"""

from __future__ import annotations

from dataclasses import dataclass

from .generateur import (
    FONTS_PAR_OS,
    MACHINES,
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

    # Trouver les machines correspondant à cet OS
    machines_os = [m for m in MACHINES if m.os == profil.os]

    # GPU doit correspondre à une machine de cet OS
    if not any(m.gpu_vendor == profil.gpu_vendor and m.gpu_renderer == profil.gpu_renderer
               for m in machines_os):
        anomalies.append(
            Anomalie("gpu_incoherent",
                     f"GPU {profil.gpu_renderer!r} pas dans les machines {profil.os}", "erreur"))

    # Résolution doit être plausible pour l'OS
    resolutions_os = set()
    for m in machines_os:
        for w, h, _ in m.resolutions:
            resolutions_os.add((w, h))
    if (profil.screen_width, profil.screen_height) not in resolutions_os:
        anomalies.append(
            Anomalie("resolution_inhabituelle",
                     f"{profil.screen_width}x{profil.screen_height} inhabituel pour {profil.os}",
                     "avertissement"))

    # DPR doit correspondre à l'OS et la résolution
    dprs_attendus = set()
    for m in machines_os:
        for w, h, d in m.resolutions:
            if w == profil.screen_width and h == profil.screen_height:
                dprs_attendus.add(d)
    if dprs_attendus and profil.device_pixel_ratio not in dprs_attendus:
        anomalies.append(
            Anomalie("dpr_incoherent",
                     f"DPR {profil.device_pixel_ratio} inattendu pour "
                     f"{profil.screen_width}x{profil.screen_height} sur {profil.os}",
                     "avertissement"))

    # GPU ↔ hardware_concurrency ↔ device_memory corrélation
    machines_gpu = [m for m in machines_os
                    if m.gpu_vendor == profil.gpu_vendor and m.gpu_renderer == profil.gpu_renderer]
    if machines_gpu:
        hw_attendus = {m.hw_concurrency for m in machines_gpu}
        if profil.hardware_concurrency not in hw_attendus:
            anomalies.append(
                Anomalie("hw_gpu_incoherent",
                         f"hardwareConcurrency={profil.hardware_concurrency} incohérent avec "
                         f"GPU {profil.gpu_renderer!r} (attendu: {hw_attendus})", "erreur"))
        dm_attendus = {m.device_memory for m in machines_gpu}
        if profil.device_memory not in dm_attendus:
            anomalies.append(
                Anomalie("mem_gpu_incoherent",
                         f"deviceMemory={profil.device_memory} incohérent avec "
                         f"GPU {profil.gpu_renderer!r} (attendu: {dm_attendus})", "avertissement"))

    # Platform JS doit correspondre à l'OS
    attendu = {"macos": "MacIntel", "windows": "Win32", "linux": "Linux x86_64"}
    if profil.platform != attendu.get(profil.os, ""):
        anomalies.append(
            Anomalie("platform_incoherent", f"platform={profil.platform!r} pour os={profil.os}",
                     "erreur"))

    # UA doit contenir les indices de l'OS
    ua = profil.user_agent.lower()
    if profil.os == "macos" and "macintosh" not in ua:
        anomalies.append(Anomalie("ua_sans_mac", "UA macOS sans 'Macintosh'", "erreur"))
    if profil.os == "windows" and "windows" not in ua:
        anomalies.append(Anomalie("ua_sans_windows", "UA Windows sans 'Windows'", "erreur"))
    if profil.os == "linux" and "linux" not in ua:
        anomalies.append(Anomalie("ua_sans_linux", "UA Linux sans 'Linux'", "erreur"))

    # Chrome version dans l'UA
    if f"chrome/{profil.chrome_full}" not in ua:
        anomalies.append(
            Anomalie("ua_version_chrome", f"UA ne contient pas Chrome/{profil.chrome_full}",
                     "erreur"))

    # Fonts de base de l'OS
    fonts_base = FONTS_PAR_OS.get(profil.os, [])[:5]
    manquantes = [f for f in fonts_base if f not in profil.fonts]
    if manquantes:
        anomalies.append(
            Anomalie("fonts_manquantes",
                     f"Fonts de base manquantes pour {profil.os} : {manquantes}",
                     "avertissement"))

    # sec-ch-ua-platform
    plat_attendu = {"macos": '"macOS"', "windows": '"Windows"', "linux": '"Linux"'}
    if profil.sec_ch_ua_platform != plat_attendu.get(profil.os, ""):
        anomalies.append(
            Anomalie("client_hints_platform",
                     f"Sec-CH-UA-Platform={profil.sec_ch_ua_platform!r} incohérent avec {profil.os}",
                     "erreur"))

    # Locale et timezone
    _verifier_locale_tz(profil, anomalies)

    # Seeds non-nuls et différents
    if profil.canvas_seed == 0:
        anomalies.append(Anomalie("canvas_seed_nul", "canvas_seed = 0", "erreur"))
    if profil.canvas_seed == profil.audio_seed:
        anomalies.append(Anomalie("seeds_identiques", "canvas_seed == audio_seed", "avertissement"))

    return anomalies


LOCALE_TZ_COMPATIBLES: dict[str, set[str]] = {
    "fr-FR": {"Europe/Paris", "Europe/Brussels", "Europe/Luxembourg", "Europe/Monaco"},
    "en-US": {
        "America/New_York", "America/Chicago", "America/Denver",
        "America/Los_Angeles", "America/Phoenix", "America/Anchorage", "Pacific/Honolulu",
    },
    "en-GB": {"Europe/London"},
    "de-DE": {"Europe/Berlin", "Europe/Vienna", "Europe/Zurich"},
    "es-ES": {"Europe/Madrid"},
}


def _verifier_locale_tz(profil: ProfilNavigateur, anomalies: list[Anomalie]) -> None:
    compatibles = LOCALE_TZ_COMPATIBLES.get(profil.locale)
    if compatibles and profil.timezone not in compatibles:
        anomalies.append(
            Anomalie("locale_tz_incoherent",
                     f"locale={profil.locale} avec timezone={profil.timezone}",
                     "avertissement"))
