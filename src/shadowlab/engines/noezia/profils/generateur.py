"""Génération de profils navigateur réalistes et cohérents.

Chaque profil est un ensemble de propriétés qui doivent être cohérentes entre elles :
le GPU annoncé correspond à l'OS et au nombre de cœurs, la résolution au type de machine,
les fonts à l'OS, la mémoire au GPU, etc. Un détecteur qui corrèle ces signaux ne doit
trouver aucune incohérence.
"""

from __future__ import annotations

import hashlib
import random
import subprocess
import sys
from dataclasses import dataclass

# ── Machines réalistes (OS + GPU + cœurs + mémoire + écran) ───────────


@dataclass(frozen=True)
class ProfilMachine:
    """Configuration matérielle cohérente d'une vraie machine."""

    os: str
    os_versions: list[str]
    gpu_vendor: str
    gpu_renderer: str
    hw_concurrency: int
    device_memory: int
    resolutions: list[tuple[int, int, float]]


MACHINES: list[ProfilMachine] = [
    # ── macOS ─────────────────────────────────────────────────────────
    ProfilMachine(
        "macos",
        ["14_4_1", "14_6", "15_0", "15_1"],
        "Google Inc. (Apple)",
        "ANGLE (Apple, ANGLE Metal Renderer: Apple M1, Unspecified Version)",
        8,
        8,
        [(1440, 900, 2.0), (1920, 1080, 2.0), (2560, 1440, 2.0)],
    ),
    ProfilMachine(
        "macos",
        ["14_4_1", "14_6", "15_0", "15_1"],
        "Google Inc. (Apple)",
        "ANGLE (Apple, ANGLE Metal Renderer: Apple M1 Pro, Unspecified Version)",
        10,
        8,
        [(1512, 982, 2.0), (1728, 1117, 2.0), (1920, 1080, 2.0), (2560, 1440, 2.0)],
    ),
    ProfilMachine(
        "macos",
        ["14_6", "15_0", "15_1"],
        "Google Inc. (Apple)",
        "ANGLE (Apple, ANGLE Metal Renderer: Apple M2, Unspecified Version)",
        8,
        8,
        [(1440, 900, 2.0), (1512, 982, 2.0), (1920, 1080, 2.0)],
    ),
    ProfilMachine(
        "macos",
        ["14_6", "15_0", "15_1"],
        "Google Inc. (Apple)",
        "ANGLE (Apple, ANGLE Metal Renderer: Apple M2 Pro, Unspecified Version)",
        12,
        8,
        [(1512, 982, 2.0), (1728, 1117, 2.0), (2560, 1440, 2.0)],
    ),
    ProfilMachine(
        "macos",
        ["14_6", "15_0", "15_1"],
        "Google Inc. (Apple)",
        "ANGLE (Apple, ANGLE Metal Renderer: Apple M3, Unspecified Version)",
        8,
        8,
        [(1512, 982, 2.0), (1728, 1117, 2.0), (1920, 1080, 2.0)],
    ),
    ProfilMachine(
        "macos",
        ["15_0", "15_1"],
        "Google Inc. (Apple)",
        "ANGLE (Apple, ANGLE Metal Renderer: Apple M3 Pro, Unspecified Version)",
        12,
        8,
        [(1512, 982, 2.0), (1728, 1117, 2.0), (2560, 1440, 2.0)],
    ),
    ProfilMachine(
        "macos",
        ["15_0", "15_1"],
        "Google Inc. (Apple)",
        "ANGLE (Apple, ANGLE Metal Renderer: Apple M4, Unspecified Version)",
        10,
        8,
        [(1512, 982, 2.0), (1728, 1117, 2.0), (2560, 1440, 2.0)],
    ),
    ProfilMachine(
        "macos",
        ["15_1"],
        "Google Inc. (Apple)",
        "ANGLE (Apple, ANGLE Metal Renderer: Apple M5 Pro, Unspecified Version)",
        18,
        8,
        [(1512, 982, 2.0), (1728, 1117, 2.0), (2560, 1440, 2.0)],
    ),
    # ── Windows — desktop NVIDIA ──────────────────────────────────────
    ProfilMachine(
        "windows",
        ["10.0"],
        "Google Inc. (NVIDIA)",
        "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        8,
        8,
        [(1920, 1080, 1.0), (1920, 1080, 1.25), (2560, 1440, 1.0)],
    ),
    ProfilMachine(
        "windows",
        ["10.0"],
        "Google Inc. (NVIDIA)",
        "ANGLE (NVIDIA, NVIDIA GeForce RTX 3070 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        8,
        8,
        [(1920, 1080, 1.0), (2560, 1440, 1.0), (2560, 1440, 1.25)],
    ),
    ProfilMachine(
        "windows",
        ["10.0"],
        "Google Inc. (NVIDIA)",
        "ANGLE (NVIDIA, NVIDIA GeForce RTX 4060 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        16,
        8,
        [(1920, 1080, 1.0), (2560, 1440, 1.0), (2560, 1440, 1.25)],
    ),
    ProfilMachine(
        "windows",
        ["10.0"],
        "Google Inc. (NVIDIA)",
        "ANGLE (NVIDIA, NVIDIA GeForce RTX 4070 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        16,
        8,
        [(2560, 1440, 1.0), (2560, 1440, 1.25), (3840, 2160, 1.5)],
    ),
    # ── Windows — desktop AMD ─────────────────────────────────────────
    ProfilMachine(
        "windows",
        ["10.0"],
        "Google Inc. (AMD)",
        "ANGLE (AMD, AMD Radeon RX 7600 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        8,
        8,
        [(1920, 1080, 1.0), (2560, 1440, 1.0)],
    ),
    # ── Windows — laptop Intel ────────────────────────────────────────
    ProfilMachine(
        "windows",
        ["10.0"],
        "Google Inc. (Intel)",
        "ANGLE (Intel, Intel(R) UHD Graphics 770 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        8,
        8,
        [(1920, 1080, 1.0), (1920, 1080, 1.25)],
    ),
    ProfilMachine(
        "windows",
        ["10.0"],
        "Google Inc. (Intel)",
        "ANGLE (Intel, Intel(R) Iris(R) Xe Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)",
        4,
        4,
        [(1366, 768, 1.0), (1536, 864, 1.25), (1920, 1080, 1.0)],
    ),
    # ── Linux ─────────────────────────────────────────────────────────
    ProfilMachine(
        "linux",
        ["x86_64"],
        "Mesa",
        "Mesa Intel(R) UHD Graphics 630 (CFL GT2)",
        8,
        8,
        [(1920, 1080, 1.0), (2560, 1440, 1.0)],
    ),
    ProfilMachine(
        "linux", ["x86_64"], "Mesa", "Mesa Intel(R) Xe Graphics (TGL GT2)", 8, 8, [(1920, 1080, 1.0), (2560, 1440, 1.0)]
    ),
    ProfilMachine(
        "linux",
        ["x86_64"],
        "Google Inc. (NVIDIA)",
        "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060/PCIe/SSE2, OpenGL 4.6.0)",
        16,
        8,
        [(1920, 1080, 1.0), (2560, 1440, 1.0), (3840, 2160, 2.0)],
    ),
]

CHROME_VERSIONS = [
    ("129", "129.0.6668.100"),
    ("130", "130.0.6723.116"),
    ("131", "131.0.6778.85"),
    ("132", "132.0.6834.57"),
]

LOCALES: list[tuple[str, str, str]] = [
    ("fr-FR", "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7", "Europe/Paris"),
    ("en-US", "en-US,en;q=0.9", "America/New_York"),
    ("en-US", "en-US,en;q=0.9", "America/Chicago"),
    ("en-US", "en-US,en;q=0.9", "America/Los_Angeles"),
    ("en-GB", "en-GB,en;q=0.9,en-US;q=0.8", "Europe/London"),
    ("de-DE", "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7", "Europe/Berlin"),
    ("es-ES", "es-ES,es;q=0.9,en-US;q=0.8,en;q=0.7", "Europe/Madrid"),
]

FONTS_PAR_OS: dict[str, list[str]] = {
    "macos": [
        "Arial",
        "Helvetica",
        "Helvetica Neue",
        "Times New Roman",
        "Courier New",
        "Georgia",
        "Verdana",
        "Trebuchet MS",
        "Lucida Grande",
        "Menlo",
        "Monaco",
        "SF Pro",
        "SF Mono",
        "Futura",
        "Optima",
        "Palatino",
        "American Typewriter",
        "Avenir",
        "Avenir Next",
        "Gill Sans",
    ],
    "windows": [
        "Arial",
        "Helvetica",
        "Times New Roman",
        "Courier New",
        "Georgia",
        "Verdana",
        "Trebuchet MS",
        "Tahoma",
        "Segoe UI",
        "Calibri",
        "Cambria",
        "Consolas",
        "Lucida Console",
        "Impact",
        "Comic Sans MS",
        "Candara",
        "Constantia",
        "Corbel",
        "Franklin Gothic Medium",
    ],
    "linux": [
        "Arial",
        "Helvetica",
        "Times New Roman",
        "Courier New",
        "DejaVu Sans",
        "DejaVu Serif",
        "DejaVu Sans Mono",
        "Liberation Sans",
        "Liberation Serif",
        "Liberation Mono",
        "Noto Sans",
        "Noto Serif",
        "Ubuntu",
        "Ubuntu Mono",
    ],
}

WEBGL_EXTENSIONS = [
    "ANGLE_instanced_arrays",
    "EXT_blend_minmax",
    "EXT_color_buffer_half_float",
    "EXT_disjoint_timer_query",
    "EXT_float_blend",
    "EXT_frag_depth",
    "EXT_shader_texture_lod",
    "EXT_texture_compression_bptc",
    "EXT_texture_compression_rgtc",
    "EXT_texture_filter_anisotropic",
    "EXT_sRGB",
    "KHR_parallel_shader_compile",
    "OES_element_index_uint",
    "OES_fbo_render_mipmap",
    "OES_standard_derivatives",
    "OES_texture_float",
    "OES_texture_float_linear",
    "OES_texture_half_float",
    "OES_texture_half_float_linear",
    "OES_vertex_array_object",
    "WEBGL_color_buffer_float",
    "WEBGL_compressed_texture_s3tc",
    "WEBGL_compressed_texture_s3tc_srgb",
    "WEBGL_debug_renderer_info",
    "WEBGL_debug_shaders",
    "WEBGL_depth_texture",
    "WEBGL_draw_buffers",
    "WEBGL_lose_context",
    "WEBGL_multi_draw",
]


@dataclass
class ProfilNavigateur:
    """Profil complet et cohérent d'un navigateur simulé."""

    nom: str
    os: str
    os_version: str
    chrome_major: str
    chrome_full: str
    gpu_vendor: str
    gpu_renderer: str
    screen_width: int
    screen_height: int
    device_pixel_ratio: float
    locale: str
    accept_language: str
    timezone: str
    fonts: list[str]
    webgl_extensions: list[str]
    hardware_concurrency: int
    device_memory: int
    canvas_seed: int
    audio_seed: int
    user_agent: str = ""
    platform: str = ""
    platform_name: str = ""
    sec_ch_ua: str = ""
    sec_ch_ua_platform: str = ""

    def __post_init__(self) -> None:
        if not self.user_agent:
            self.user_agent = self._construire_ua()
        if not self.platform:
            self.platform = self._plateforme()
        if not self.platform_name:
            self.platform_name = {"macos": "macOS", "windows": "Windows", "linux": "Linux"}[self.os]
        if not self.sec_ch_ua:
            self.sec_ch_ua = self._client_hints()
        if not self.sec_ch_ua_platform:
            self.sec_ch_ua_platform = self._plateforme_hints()

    def _construire_ua(self) -> str:
        if self.os == "macos":
            return (
                f"Mozilla/5.0 (Macintosh; Intel Mac OS X {self.os_version}) "
                f"AppleWebKit/537.36 (KHTML, like Gecko) "
                f"Chrome/{self.chrome_full} Safari/537.36"
            )
        if self.os == "windows":
            return (
                f"Mozilla/5.0 (Windows NT {self.os_version}; Win64; x64) "
                f"AppleWebKit/537.36 (KHTML, like Gecko) "
                f"Chrome/{self.chrome_full} Safari/537.36"
            )
        return (
            f"Mozilla/5.0 (X11; Linux x86_64) "
            f"AppleWebKit/537.36 (KHTML, like Gecko) "
            f"Chrome/{self.chrome_full} Safari/537.36"
        )

    def _plateforme(self) -> str:
        return {"macos": "MacIntel", "windows": "Win32", "linux": "Linux x86_64"}[self.os]

    def _client_hints(self) -> str:
        m = self.chrome_major
        return f'"Not:A-Brand";v="8", "Chromium";v="{m}", "Google Chrome";v="{m}"'

    def _plateforme_hints(self) -> str:
        return {"macos": '"macOS"', "windows": '"Windows"', "linux": '"Linux"'}[self.os]

    def viewport(self) -> dict[str, int]:
        w = min(self.screen_width, 1920)
        h = min(self.screen_height, 1080)
        return {"width": w, "height": h}

    def digest(self) -> str:
        cle = f"{self.nom}:{self.canvas_seed}:{self.audio_seed}"
        return hashlib.sha256(cle.encode()).hexdigest()[:16]

    def en_dict(self) -> dict:
        return {
            "nom": self.nom,
            "os": self.os,
            "os_version": self.os_version,
            "chrome_major": self.chrome_major,
            "chrome_full": self.chrome_full,
            "gpu_vendor": self.gpu_vendor,
            "gpu_renderer": self.gpu_renderer,
            "screen_width": self.screen_width,
            "screen_height": self.screen_height,
            "device_pixel_ratio": self.device_pixel_ratio,
            "locale": self.locale,
            "accept_language": self.accept_language,
            "timezone": self.timezone,
            "fonts": self.fonts,
            "webgl_extensions": self.webgl_extensions,
            "hardware_concurrency": self.hardware_concurrency,
            "device_memory": self.device_memory,
            "canvas_seed": self.canvas_seed,
            "audio_seed": self.audio_seed,
            "user_agent": self.user_agent,
            "platform": self.platform,
            "platform_name": self.platform_name,
            "sec_ch_ua": self.sec_ch_ua,
            "sec_ch_ua_platform": self.sec_ch_ua_platform,
        }

    @classmethod
    def de_dict(cls, d: dict) -> ProfilNavigateur:
        return cls(**d)


def _gpu_hote() -> str | None:
    """Détecte le chipset GPU de la machine hôte (macOS uniquement)."""
    if sys.platform != "darwin":
        return None
    try:
        out = subprocess.check_output(
            ["system_profiler", "SPDisplaysDataType"],
            text=True,
            timeout=5,
        )
        for ligne in out.splitlines():
            if "Chipset Model" in ligne:
                return ligne.split(":", 1)[1].strip()
    except Exception:
        pass
    return None


def generer_profil(nom: str | None = None, os: str | None = None, rng: random.Random | None = None) -> ProfilNavigateur:
    """Génère un profil navigateur complet et cohérent.

    Tous les signaux sont corrélés via la table MACHINES : le GPU, les cœurs,
    la mémoire et la résolution d'écran correspondent à une vraie configuration.
    Sur macOS avec Metal, le GPU réel est exposé par Chrome via ANGLE — le profil
    doit correspondre au matériel réel pour éviter une incohérence GPU détectable.
    """
    r = rng or random.Random()

    # Filtrer par OS si demandé (fallback sur toutes les machines si l'OS est inconnu)
    candidates = ([m for m in MACHINES if m.os == os] or MACHINES) if os else MACHINES

    # Sur macOS, filtrer aussi par GPU réel : Chrome expose le renderer ANGLE natif
    # (Metal) et un profil M3 sur un M5 Pro réel serait incohérent.
    if os == "macos":
        gpu = _gpu_hote()
        if gpu:
            gpu_match = [m for m in candidates if gpu in m.gpu_renderer]
            if gpu_match:
                candidates = gpu_match

    machine = r.choice(candidates)

    os_version = r.choice(machine.os_versions)
    chrome_major, chrome_full = r.choice(CHROME_VERSIONS)
    screen_w, screen_h, dpr = r.choice(machine.resolutions)
    locale, accept_lang, tz = r.choice(LOCALES)
    fonts = FONTS_PAR_OS[machine.os][:]
    r.shuffle(fonts)
    canvas_seed = r.randint(0, 0x7FFFFFFF)
    audio_seed = r.randint(0, 0x7FFFFFFF)

    if nom is None:
        nom = f"profil-{hashlib.sha256(r.randbytes(16)).hexdigest()[:8]}"

    return ProfilNavigateur(
        nom=nom,
        os=machine.os,
        os_version=os_version,
        chrome_major=chrome_major,
        chrome_full=chrome_full,
        gpu_vendor=machine.gpu_vendor,
        gpu_renderer=machine.gpu_renderer,
        screen_width=screen_w,
        screen_height=screen_h,
        device_pixel_ratio=dpr,
        locale=locale,
        accept_language=accept_lang,
        timezone=tz,
        fonts=fonts,
        webgl_extensions=WEBGL_EXTENSIONS[:],
        hardware_concurrency=machine.hw_concurrency,
        device_memory=machine.device_memory,
        canvas_seed=canvas_seed,
        audio_seed=audio_seed,
    )
