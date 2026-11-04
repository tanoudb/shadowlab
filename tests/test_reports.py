"""Tests pour les exports CSV, JSON par passage et rapport HTML."""

from __future__ import annotations

import json

import pytest

from shadowlab import database as db
from shadowlab import reports


@pytest.fixture
def cx(tmp_path):
    """Base peuplée avec une expérience, deux moteurs, deux protections."""
    base = tmp_path / "test.sqlite3"
    cx = db.ouvrir(base)
    cx.execute(
        "INSERT INTO experiments (id, name, description, created_at, configuration, status, seed)"
        " VALUES (1, 'test-reports', 'desc', '2026-01-01T00:00:00', '{}', 'termine', 42)"
    )
    cx.execute(
        "INSERT INTO engines (id, name, version, runtime, configuration)"
        " VALUES (1, 'httpx', '{\"httpx\": \"0.27\"}', 'python', '{}')"
    )
    cx.execute(
        "INSERT INTO engines (id, name, version, runtime, configuration)"
        " VALUES (2, 'playwright', '{\"playwright\": \"1.49\"}', 'chromium', '{}')"
    )
    cx.execute("INSERT INTO scenarios (id, name) VALUES (1, 'static_html')")
    cx.execute("INSERT INTO scenarios (id, name) VALUES (2, 'api_json')")

    _run(cx, 1, eng=1, prot="01", success=1, issue="extraction_reussie", duration=120)
    _run(cx, 2, eng=1, prot="02", success=0, issue="bloque", duration=80)
    _run(cx, 3, eng=2, prot="01", success=1, issue="extraction_reussie", duration=300)
    _run(cx, 4, eng=2, prot="02", success=0, issue="erreur_technique", duration=None)

    cx.execute(
        "INSERT INTO detections (run_id, detector_name, detector_version, classification, confidence, signals)"
        " VALUES (2, 'regles-http', '1.0', 'automatise', 0.9, '[]')"
    )
    cx.execute(
        "INSERT INTO detections (run_id, detector_name, detector_version, classification, confidence, signals)"
        " VALUES (3, 'regles-http', '1.0', 'humain', 0.1, '[]')"
    )
    return cx


def _run(cx, run_id, *, eng, prot, success, issue, duration, scenario_id=1):
    token = f"tok-{run_id}"
    cx.execute(
        "INSERT INTO runs (id, experiment_id, engine_id, scenario_id, repetition,"
        " session_token, truth, started_at, status, success, duration_ms, protection, issue)"
        " VALUES (?, 1, ?, ?, 1, ?, 'automatise', '2026-01-01T00:00:00', ?, ?, ?, ?, ?)",
        (
            run_id,
            eng,
            scenario_id,
            token,
            "reussi" if success else "erreur",
            success,
            duration,
            prot,
            issue,
        ),
    )


class TestCSV:
    def test_colonnes_obligatoires(self, cx):
        csv_str = reports.lignes_csv(cx, 1)
        premiere_ligne = csv_str.split("\n")[0]
        for col in ("protection", "issue", "cause"):
            assert col in premiere_ligne

    def test_nombre_de_lignes(self, cx):
        csv_str = reports.lignes_csv(cx, 1)
        lignes = [x for x in csv_str.strip().split("\n") if x]
        assert len(lignes) == 5  # en-tête + 4 passages

    def test_protection_renseignee(self, cx):
        csv_str = reports.lignes_csv(cx, 1)
        lignes = csv_str.strip().split("\n")
        idx_prot = lignes[0].split(",").index("protection")
        for ligne in lignes[1:]:
            vals = ligne.split(",")
            assert vals[idx_prot] in ("01", "02")


class TestPassagesJSON:
    def test_structure_passage(self, cx):
        brut = reports.passages_json(cx, 1)
        passages = json.loads(brut)
        assert len(passages) == 4
        p = passages[0]
        for cle in ("run_id", "moteur", "engine", "scenario", "protection", "issue", "status", "detections"):
            assert cle in p

    def test_detections_presentes(self, cx):
        brut = reports.passages_json(cx, 1)
        passages = json.loads(brut)
        p2 = next(p for p in passages if p["run_id"] == 2)
        assert len(p2["detections"]) == 1
        assert p2["detections"][0]["detecteur"] == "regles-http"

    def test_metriques_presentes(self, cx):
        brut = reports.passages_json(cx, 1)
        passages = json.loads(brut)
        p = passages[0]
        assert "metriques" in p
        assert "cpu_pct" in p["metriques"]


class TestHTML:
    def test_contient_nom_experience(self, cx):
        from shadowlab.analytics import statistiques

        stats = statistiques(cx, 1)
        html = reports.rapport_html(stats)
        assert "test-reports" in html

    def test_taille_echantillon_affichee(self, cx):
        from shadowlab.analytics import statistiques

        stats = statistiques(cx, 1)
        html = reports.rapport_html(stats)
        assert "(n=" in html

    def test_section_protection(self, cx):
        from shadowlab.analytics import statistiques

        stats = statistiques(cx, 1)
        html = reports.rapport_html(stats)
        assert "Par niveau de protection" in html


class TestExporter:
    def test_trois_formats(self, cx, tmp_path):
        dossier = tmp_path / "export"
        fichiers = reports.exporter(cx, 1, dossier, ["json", "csv", "html"])
        noms = {f.name for f in fichiers}
        assert "statistiques.json" in noms
        assert "passages.json" in noms
        assert "passages.csv" in noms
        assert "rapport.html" in noms
