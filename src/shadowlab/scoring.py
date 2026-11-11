"""Score composite pondéré par famille de détecteur.

Chaque détecteur appartient à une famille ; chaque famille a un coefficient multiplicateur
appliqué aux poids des signaux individuels. Le score total est comparé à des seuils
pour décider : passé / captcha / bloqué.
"""

from __future__ import annotations

from .detection import Classement, Signal

FAMILLE: dict[str, str] = {
    "regles-http": "transport",
    "tls": "transport",
    "botd": "empreinte",
    "regles-js": "empreinte",
    "headless": "empreinte",
    "chrome-apis": "empreinte",
    "media-codecs": "empreinte",
    "langues": "empreinte",
    "css-media": "empreinte",
    "permissions-etendu": "empreinte",
    "connection-dynamic": "empreinte",
    "position-fenetre": "empreinte",
    "prototypes": "integrite",
    "integrite-proprietes": "integrite",
    "stack-trace": "integrite",
    "stack-getter": "integrite",
    "automation-globals": "integrite",
    "prototype-chain": "integrite",
    "enumerable-props": "integrite",
    "proxy-uadata": "integrite",
    "timing-precision": "integrite",
    "paint-timing": "integrite",
    "deep-proxy": "integrite",
    "cdp": "integrite",
    "math-constants": "integrite",
    "coherence": "coherence",
    "coherence-profonde": "coherence",
    "coherence-environnement": "coherence",
    "canvas-empreinte": "coherence",
    "canvas-consistency": "coherence",
    "worker-consistency": "coherence",
    "raf-timing": "coherence",
    "iframe-consistency": "coherence",
    "audio-context": "coherence",
    "polices": "coherence",
    "domrect": "coherence",
    "comportement": "comportement",
    "entropie-interaction": "comportement",
    "scroll": "comportement",
    "webrtc": "comportement",
    "correlation-session": "correlation",
}

COEFFICIENTS: dict[str, float] = {
    "transport": 1.0,
    "empreinte": 0.7,
    "integrite": 1.2,
    "coherence": 0.8,
    "comportement": 1.0,
    "correlation": 1.5,
}


def score_composite(classements: list[Classement]) -> float:
    """Score pondéré : somme des (poids_signal × coefficient_famille)."""
    score = 0.0
    for c in classements:
        if c.detector_name == "meta-composite":
            continue
        famille = FAMILLE.get(c.detector_name, "empreinte")
        coeff = COEFFICIENTS.get(famille, 1.0)
        for s in c.signals:
            if s.poids > 0:
                score += s.poids * coeff
    return round(score, 3)


def score_signaux(signaux_par_detecteur: list[tuple[str, list[Signal]]]) -> float:
    """Score pondéré à partir de signaux faibles groupés par détecteur."""
    score = 0.0
    for nom, signaux in signaux_par_detecteur:
        famille = FAMILLE.get(nom, "empreinte")
        coeff = COEFFICIENTS.get(famille, 1.0)
        for s in signaux:
            if s.poids > 0:
                score += s.poids * coeff
    return round(score, 3)


def decision(score: float, seuil_blocage: float, seuil_captcha: float | None = None) -> str:
    """Trois zones : bloqué / captcha / passé."""
    if score >= seuil_blocage:
        return "bloque"
    if seuil_captcha is not None and score >= seuil_captcha:
        return "captcha"
    return "passe"
