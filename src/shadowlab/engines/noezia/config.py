"""Configuration typée du moteur NOEZIA."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ConfigSouris:
    actif: bool = True
    overshoot_proba: float = 0.12
    sous_mouvements: int = 3
    bruit_vitesse: float = 0.15
    fitts_a: float = 50.0
    fitts_b: float = 150.0


@dataclass(frozen=True)
class ConfigClavier:
    actif: bool = True
    wpm_moyen: float = 65.0
    wpm_ecart: float = 12.0
    proba_erreur: float = 0.02
    fatigue_par_caractere: float = 0.0003


@dataclass(frozen=True)
class ConfigDefilement:
    actif: bool = True
    mode: str = "trackpad"
    pixels_par_tick: int = 120


@dataclass(frozen=True)
class ConfigFurtivite:
    canvas_noise: bool = True
    webgl_spoof: bool = True
    audio_noise: bool = True
    navigator_patches: bool = True
    webrtc_block: bool = True
    toString_natif: bool = True


@dataclass(frozen=True)
class ConfigNoezia:
    headless: bool = True
    locale: str = "fr-FR"
    viewport_width: int = 1920
    viewport_height: int = 1080
    profil: str | None = None
    souris: ConfigSouris = field(default_factory=ConfigSouris)
    clavier: ConfigClavier = field(default_factory=ConfigClavier)
    defilement: ConfigDefilement = field(default_factory=ConfigDefilement)
    furtivite: ConfigFurtivite = field(default_factory=ConfigFurtivite)
    interaction_post_page: bool = True
    eviter_pieges: bool = True
    channel: str | None = None  # navigateur installé à piloter (« chrome ») ; None = le Chromium embarqué
    identite_native: bool = False  # le navigateur tel qu'il est : ni profil, ni User-Agent, ni script d'empreinte
