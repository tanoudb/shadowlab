"""Agrégation des notes de récolte dans `analytics.statistiques` et affichage dans le rapport HTML."""

import json

import pytest

from shadowlab import database as db
from shadowlab.analytics import statistiques
from shadowlab.reports import rapport_html


def _note(completude, exactitude):
    return {"recolte": {"completude": completude, "exactitude": exactitude}}


@pytest.fixture
def cx(tmp_path):
    cx = db.ouvrir(tmp_path / "recolte.sqlite3")
    cx.execute(
        "INSERT INTO experiments (id, name, created_at, configuration, status, seed)"
        " VALUES (1, 'recolte', '2026-01-01', '{}', 'termine', 1)"
    )
    cx.execute(
        "INSERT INTO engines (id, name, version, runtime, configuration)"
        " VALUES (1, 'httpx', '{}', 'python', '{\"label\": \"httpx\"}')"
    )
    cx.execute("INSERT INTO scenarios (id, name) VALUES (1, 'recolte_vitrine')")
    cx.execute("INSERT INTO scenarios (id, name) VALUES (2, 'static_html')")
    passages = [
        # (id, scénario, succès, issue, drapeaux)
        (1, 1, 1, "extraction_reussie", {"details_scenario": _note(1.0, 1.0)}),
        (2, 1, 0, "echec", {"details_scenario": _note(0.5, 0.8)}),
        (3, 1, 0, "bloque", {"details_scenario": _note(0.0, None)}),
        (4, 1, 0, "erreur_technique", {"details_scenario": _note(0.1, 0.1)}),  # en panne : ne compte pas
        (5, 2, 1, "extraction_reussie", {}),  # autre scénario : aucune note
    ]
    for rid, scenario, succes, issue, drapeaux in passages:
        cx.execute(
            "INSERT INTO runs (id, experiment_id, engine_id, scenario_id, repetition,"
            " session_token, truth, started_at, status, success, protection, issue, drapeaux)"
            " VALUES (?, 1, 1, ?, ?, ?, 'automatise', '2026-01-01', ?, ?, '01', ?, ?)",
            (rid, scenario, rid, f"t-{rid}", "reussi" if succes else "echec", succes, issue, json.dumps(drapeaux)),
        )
    return cx


def test_bloc_moteur_porte_la_note_de_recolte(cx):
    r = statistiques(cx, 1)["moteurs"][0]["recolte"]
    assert r["passages_notes"] == 3  # le passage en panne n'entre pas
    assert r["completude_moyenne"] == pytest.approx((1.0 + 0.5 + 0.0) / 3)
    assert r["exactitude_moyenne"] == pytest.approx((1.0 + 0.8) / 2)  # le passage sans exactitude mesurable est écarté
    assert r["passages_exactitude"] == 2


def test_bloc_moteur_x_protection_et_absence_de_note(cx):
    matrice = {(b["scenario"], b["protection"]): b for b in statistiques(cx, 1)["matrice_croisee"]}
    assert matrice[("recolte_vitrine", "01")]["recolte"]["passages_notes"] == 3
    assert "recolte" not in matrice[("static_html", "01")]


def test_rapport_html_affiche_les_deux_notes(cx):
    html = rapport_html(statistiques(cx, 1))
    assert "Récolte du site vitrine" in html
    assert "50.0 %" in html  # complétude moyenne
    assert "90.0 %" in html  # exactitude moyenne


def test_rapport_html_sans_exactitude_mesurable(cx):
    cx.execute("UPDATE runs SET drapeaux = ? WHERE id IN (1, 2)", (json.dumps({"details_scenario": _note(0.0, None)}),))
    html = rapport_html(statistiques(cx, 1))
    assert "n. m." in html and "Récolte du site vitrine" in html
