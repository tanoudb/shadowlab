"""Quatre règles construites de travers, vues sur un humain connu (D-95, 16/11/2026).

Un humain connu (Chrome sur Mac, 17 pages) était arrêté aux niveaux 05 à 07 et `endurance` par trois règles de
mouvement ; un second (Edge sur Windows, fenêtre agrandie) par `screen_position_zero`. Les seuils numériques ne
bougent pas : on corrige la forme de la règle.

Aucune donnée d'un vrai visiteur ici. Les humains fabriqués n'ont que les propriétés mesurées en agrégat :
- souris : moyennes par page de 0,120 ; 0,178 ; 0,039 (23 angles) ; … ; 0,048, soit 5 pages sur 17 sous 0,08, des
  angles exactement nuls en nombre, la moyenne cumulée jamais sous 0,095 ;
- molette : 50 deltas entiers entre -8 et 8, 7 valeurs distinctes ; délais de `scroll` calés sur l'image
  (médiane 16,6 ms, coefficient de variation 0,07) ;
- fenêtre : `screenX` = `screenY` = 0 mais un cadre de navigateur (barre d'onglets et d'adresse).
Les robots fabriqués, eux, tracent des droites, avancent d'un pas de molette fixe, scrollent toutes les 100 ms, ou
sont un navigateur sans tête (fenêtre sans cadre).
"""

from __future__ import annotations

import random
import statistics
from typing import Any

import pytest

from shadowlab.detection import (
    DetecteurEntropieInteraction,
    DetecteurPositionFenetre,
    DetecteurScroll,
    Observations,
)

# ── Fabrication ────────────────────────────────────────────────────────

# (moyenne, nombre d'angles) par page, dans l'ordre : les agrégats de l'humain connu
PAGES_HUMAIN = [
    (0.120, 40), (0.178, 40), (0.039, 23), (0.106, 40), (0.066, 40), (0.123, 18), (0.084, 31), (0.065, 38),
    (0.064, 40), (0.091, 37), (0.230, 40), (0.142, 40), (0.129, 40), (0.090, 40), (0.110, 40), (0.100, 40),
    (0.048, 40),
]  # fmt: skip


def angles_humain(rng: random.Random, moyenne: float, n: int) -> list[float]:
    """n angles de moyenne `moyenne`, dont plusieurs exactement nuls, à la façon d'une souris humaine."""
    zeros = min(1 + n // 3, 16)
    brut = [0.0] * zeros + [rng.expovariate(1.0) for _ in range(n - zeros)]
    rng.shuffle(brut)
    facteur = moyenne * n / sum(brut)
    return [round(a * facteur, 3) for a in brut]


def delais_souris(angles: list[float]) -> list[float]:
    """Les délais qu'une page à n angles relève (n + 1 mouvements, au plus 50), variés."""
    return [20.0 + (i * 37) % 160 for i in range(min(len(angles) + 1, 50))]


def releve(**champs: Any) -> dict[str, Any]:
    base = {
        "evenements": {"mousemove": 60, "click": 2, "keydown": 0, "scroll": 5, "touchstart": 0},
        "delais_souris_ms": [],
        "angles_segments": [],
        "delais_clavier_ms": [],
    }
    base.update(champs)
    return {"kind": "comportement", "page": "/lab/x", "payload": base}


def observations(releves: list[dict[str, Any]]) -> Observations:
    return Observations(http=[], js=releves, attend_js=True)


def codes(classement) -> set[str]:
    return {s.code for s in classement.signals}


def session_humaine(graine: int = 7) -> list[dict[str, Any]]:
    rng = random.Random(graine)
    pages = [angles_humain(rng, m, n) for m, n in PAGES_HUMAIN]
    return [releve(angles_segments=a, delais_souris_ms=delais_souris(a)) for a in pages]


def session_robot_droit(pages: int) -> list[dict[str, Any]]:
    """Un robot qui trace une droite sur chaque page : points colinéaires, angles quasi nuls."""
    angles = [0.0, 0.002, 0.0, 0.004, 0.0, 0.001, 0.0, 0.003] * 5
    return [releve(angles_segments=angles, delais_souris_ms=delais_souris(angles)) for _ in range(pages)]


# ── trajectoire_lineaire ───────────────────────────────────────────────


def test_humain_fabrique_a_les_proprietes_mesurees():
    """Garde-fou de la fabrication : 5 pages sur 17 sous 0,08, cumul jamais sous 0,09."""
    session = session_humaine()
    moyennes = [statistics.mean(r["payload"]["angles_segments"]) for r in session]
    assert sum(m < 0.08 for m in moyennes) == 5
    cumul: list[float] = []
    for r in session:
        cumul += r["payload"]["angles_segments"]
        assert statistics.mean(cumul) > 0.09
    assert any(a == 0.0 for r in session for a in r["payload"]["angles_segments"])


@pytest.mark.parametrize("graine", [7, 8, 9])
def test_humain_sans_trajectoire_lineaire_a_chaque_prefixe(graine):
    """Le gardien juge page après page : aucun préfixe de la session ne porte le signal."""
    session = session_humaine(graine)
    detecteur = DetecteurEntropieInteraction()
    for k in range(1, len(session) + 1):
        classement = detecteur.classer(observations(session[:k]))
        assert "trajectoire_lineaire" not in codes(classement), f"signal dès {k} pages"
        assert classement.classification != "automatise"


def test_une_seule_page_droite_ne_suffit_pas():
    """Une page sous 0,08 ne prouve rien (décision du 15/11) : la règle ne conclut pas sur une page isolée."""
    classement = DetecteurEntropieInteraction().classer(observations(session_robot_droit(1)))
    assert "trajectoire_lineaire" not in codes(classement)


def test_robot_en_ligne_droite_a_toujours_le_signal_des_que_les_preuves_sont_la():
    detecteur = DetecteurEntropieInteraction()
    session = session_robot_droit(17)
    avec_signal = [
        k for k in range(1, 18) if "trajectoire_lineaire" in codes(detecteur.classer(observations(session[:k])))
    ]
    assert avec_signal, "jamais de signal"
    premier = avec_signal[0]
    assert premier <= 3, f"premier signal à la page {premier}"
    assert avec_signal == list(range(premier, 18)), "le signal doit tenir à chaque préfixe suivant"
    assert detecteur.classer(observations(session[:premier])).classification == "automatise"


def test_trajectoire_lineaire_au_plus_un_signal():
    classement = DetecteurEntropieInteraction().classer(observations(session_robot_droit(10)))
    assert [s.code for s in classement.signals].count("trajectoire_lineaire") == 1


# ── deltas_uniformes ───────────────────────────────────────────────────


def deltas_humain(graine: int = 3) -> list[float]:
    """50 deltas entiers entre -8 et 8 : une molette lente ou un pavé tactile, 7 valeurs distinctes."""
    rng = random.Random(graine)
    valeurs = [-5, -2, 1, 2, 3, 5, 8]
    deltas = valeurs + [rng.choice(valeurs) for _ in range(43)]
    rng.shuffle(deltas)
    return [float(d) for d in deltas]


def delais_images(graine: int = 3) -> list[float]:
    """Délais entre événements `scroll` d'un geste continu à 60 Hz : médiane 16,6 ms, CV d'environ 0,07."""
    rng = random.Random(graine)
    return [round(rng.gauss(16.6, 1.16), 2) for _ in range(50)]


def test_humain_fabrique_molette_a_les_proprietes_mesurees():
    deltas = deltas_humain()
    assert len(deltas) == 50 and len(set(deltas)) == 7 and 7 / 50 < 0.15
    delais = delais_images()
    assert 16.0 < statistics.median(delais) < 17.2
    assert 0.04 < statistics.stdev(delais) / statistics.mean(delais) < 0.1


def test_petits_entiers_ne_sont_pas_un_pas_fixe():
    classement = DetecteurScroll().classer(observations([releve(wheel_deltas=deltas_humain())]))
    assert "deltas_uniformes" not in codes(classement)


@pytest.mark.parametrize("pas", [[100.0] * 30, [100.0, -100.0] * 15, [-100.0] * 12, [120.0] * 50])
def test_robot_a_pas_de_molette_fixe_a_toujours_deltas_uniformes(pas):
    classement = DetecteurScroll().classer(observations([releve(wheel_deltas=pas)]))
    assert "deltas_uniformes" in codes(classement)


# ── scroll_timing_regulier ─────────────────────────────────────────────


def test_delais_cales_sur_l_image_ne_concluent_pas():
    classement = DetecteurScroll().classer(observations([releve(delais_scroll_ms=delais_images())]))
    assert "scroll_timing_regulier" not in codes(classement)


@pytest.mark.parametrize("delais", [[100.0] * 50, [100.0, 101.0, 99.0, 100.5] * 12, [250.0] * 20, [60.0] * 30])
def test_robot_a_delais_reguliers_hors_image_a_toujours_scroll_timing_regulier(delais):
    classement = DetecteurScroll().classer(observations([releve(delais_scroll_ms=delais)]))
    assert "scroll_timing_regulier" in codes(classement)


def test_humain_fabrique_complet_sans_regle_de_defilement_de_robot():
    """Les deux règles de défilement ensemble, page après page, sur la même session."""
    detecteur = DetecteurScroll()
    pages = [releve(wheel_deltas=deltas_humain(g), delais_scroll_ms=delais_images(g)) for g in range(17)]
    for k in range(1, 18):
        c = codes(detecteur.classer(observations(pages[:k])))
        assert not c & {"deltas_uniformes", "scroll_timing_regulier"}


# ── screen_position_zero ───────────────────────────────────────────────


def empreinte(fenetre: dict[str, int] | None, x: int = 0, y: int = 0) -> Observations:
    p: dict[str, Any] = {"performance_memory": {"screenX": x, "screenY": y}}
    if fenetre is not None:
        p["fenetre"] = fenetre
    return Observations(http=[], js=[{"kind": "empreinte", "payload": p}], attend_js=True)


def test_fenetre_agrandie_sous_windows_n_est_pas_sans_tete():
    """Edge agrandi : (0, 0) mais 95 px de barres d'onglets et d'adresse entre la fenêtre et la page."""
    obs = empreinte({"innerWidth": 1920, "innerHeight": 945, "outerWidth": 1920, "outerHeight": 1040})
    assert "screen_position_zero" not in codes(DetecteurPositionFenetre().classer(obs))


@pytest.mark.parametrize(
    "fenetre",
    [
        {"innerWidth": 1280, "innerHeight": 720, "outerWidth": 1280, "outerHeight": 720},  # patchright sans tête
        {"innerWidth": 412, "innerHeight": 915, "outerWidth": 412, "outerHeight": 915},  # chrome-mobile émulé
        {"innerWidth": 800, "innerHeight": 600, "outerWidth": 800, "outerHeight": 600},
        {"innerWidth": 1280, "innerHeight": 720, "outerWidth": 1280, "outerHeight": 728},  # 8 px : pas un cadre
        None,  # relevé sans fenêtre : la règle ne peut pas exempter
    ],
)
def test_navigateur_sans_tete_a_toujours_screen_position_zero(fenetre):
    assert "screen_position_zero" in codes(DetecteurPositionFenetre().classer(empreinte(fenetre)))


def test_fenetre_decalee_reste_humaine():
    obs = empreinte(None, x=120, y=45)
    assert DetecteurPositionFenetre().classer(obs).classification == "humain"
