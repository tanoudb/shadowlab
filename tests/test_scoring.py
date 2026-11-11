"""Tests du score composite pondéré par famille."""

from shadowlab.detection import Classement, Signal
from shadowlab.scoring import (
    COEFFICIENTS,
    FAMILLE,
    decision,
    score_composite,
    score_signaux,
)


def _cls(nom: str, classification: str, signaux: list[Signal]) -> Classement:
    return Classement(
        detector_name=nom,
        detector_version="1",
        classification=classification,
        confidence=0.8,
        signals=signaux,
    )


def test_score_composite_vide():
    assert score_composite([]) == 0.0


def test_score_composite_un_signal_transport():
    s = Signal(code="ua_manquant", description="", poids=1.0)
    c = _cls("regles-http", "indetermine", [s])
    assert score_composite([c]) == 1.0 * COEFFICIENTS["transport"]


def test_score_composite_integrite_amplifie():
    s = Signal(code="prototype_patched", description="", poids=0.5)
    c = _cls("prototypes", "indetermine", [s])
    score = score_composite([c])
    assert score == round(0.5 * COEFFICIENTS["integrite"], 3)
    assert score > 0.5


def test_score_composite_empreinte_attenue():
    s = Signal(code="headless_detected", description="", poids=1.0)
    c = _cls("headless", "indetermine", [s])
    score = score_composite([c])
    assert score == COEFFICIENTS["empreinte"]
    assert score < 1.0


def test_score_composite_ignore_meta():
    s = Signal(code="session_parfaite", description="", poids=0.8)
    c = _cls("meta-composite", "automatise", [s])
    assert score_composite([c]) == 0.0


def test_score_composite_ignore_poids_negatif():
    s = Signal(code="ok", description="", poids=-0.3)
    c = _cls("tls", "humain", [s])
    assert score_composite([c]) == 0.0


def test_score_composite_cumul_multi_detecteurs():
    c1 = _cls("comportement", "indetermine", [Signal(code="a", description="", poids=0.4)])
    c2 = _cls("coherence", "indetermine", [Signal(code="b", description="", poids=0.3)])
    c3 = _cls("cdp", "indetermine", [Signal(code="c", description="", poids=0.5)])
    score = score_composite([c1, c2, c3])
    attendu = round(0.4 * 1.0 + 0.3 * 0.8 + 0.5 * 1.2, 3)
    assert score == attendu


def test_score_signaux():
    signaux = [
        ("tls", [Signal(code="a", description="", poids=0.5)]),
        ("comportement", [Signal(code="b", description="", poids=0.3)]),
    ]
    score = score_signaux(signaux)
    attendu = round(0.5 * 1.0 + 0.3 * 1.0, 3)
    assert score == attendu


def test_decision_bloque():
    assert decision(1.5, seuil_blocage=1.0) == "bloque"


def test_decision_captcha():
    assert decision(0.7, seuil_blocage=1.0, seuil_captcha=0.5) == "captcha"


def test_decision_passe():
    assert decision(0.3, seuil_blocage=1.0, seuil_captcha=0.5) == "passe"


def test_decision_sans_captcha():
    assert decision(0.7, seuil_blocage=1.0) == "passe"


def test_tous_detecteurs_ont_une_famille():
    """Vérifie que chaque détecteur connu a une famille dans le scoring."""
    from shadowlab.detection import registre

    tous = registre()
    manquants = [nom for nom in tous if nom not in FAMILLE and nom != "meta-composite"]
    assert manquants == [], f"Détecteurs sans famille : {manquants}"
