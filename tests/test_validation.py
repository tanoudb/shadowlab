"""Passe 2 — Tests de validation statistique : réconciliation, Wilson CI, stabilité des rapports."""

from __future__ import annotations

import json

import pytest

from shadowlab import database as db
from shadowlab import reports
from shadowlab.analytics import comparer, statistiques, wilson

# ---------------------------------------------------------------------------
# Fixture : base réaliste avec erreurs techniques, blocages, réussites
# ---------------------------------------------------------------------------


@pytest.fixture
def cx(tmp_path):
    base = tmp_path / "test.sqlite3"
    cx = db.ouvrir(base)
    cx.execute(
        "INSERT INTO experiments (id, name, description, created_at, configuration, status, seed)"
        " VALUES (1, 'validation', 'test validation', '2026-01-01T00:00:00', '{}', 'termine', 1)"
    )
    cx.execute(
        "INSERT INTO experiments (id, name, description, created_at, configuration, status, seed)"
        " VALUES (2, 'validation-2', 'test validation 2', '2026-01-01T00:00:00', '{}', 'termine', 2)"
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

    rid = 0
    for exp in (1, 2):
        for eng in (1, 2):
            for sc in (1, 2):
                for prot in ("01", "02", "03"):
                    for rep in range(1, 4):
                        rid += 1
                        if rid % 7 == 0:
                            issue = "erreur_technique"
                            success = 0
                        elif rid % 5 == 0:
                            issue = "bloque"
                            success = 0
                        elif rid % 11 == 0:
                            issue = "challenge_non_valide"
                            success = 0
                        else:
                            issue = "extraction_reussie"
                            success = 1
                        _run(cx, rid, exp=exp, eng=eng, sc=sc, prot=prot, rep=rep, success=success, issue=issue)
    return cx


def _run(cx, rid, *, exp, eng, sc, prot, rep, success, issue):
    status = "reussi" if success else "erreur"
    cx.execute(
        "INSERT INTO runs (id, experiment_id, engine_id, scenario_id, repetition,"
        " session_token, truth, started_at, status, success, duration_ms, protection, issue)"
        " VALUES (?, ?, ?, ?, ?, ?, 'automatise', '2026-01-01T00:00:00', ?, ?, ?, ?, ?)",
        (rid, exp, eng, sc, rep, f"tok-{rid}", status, success, float(rid * 10), prot, issue),
    )


# ---------------------------------------------------------------------------
# E2+E3 : Réconciliation — Σ par_issue == total, dénominateurs cohérents
# ---------------------------------------------------------------------------


class TestReconciliation:
    def test_somme_issues_egal_total_par_moteur(self, cx):
        stats = statistiques(cx, 1)
        for m in stats["moteurs"]:
            total_issues = sum(m["par_issue"].values())
            assert total_issues == m["passages"], f"{m['label']}: {total_issues} != {m['passages']}"

    def test_somme_issues_egal_total_par_protection(self, cx):
        stats = statistiques(cx, 1)
        for p in stats.get("par_protection", []):
            total_issues = sum(p["par_issue"].values())
            assert total_issues == p["passages"], f"{p['protection']}: {total_issues} != {p['passages']}"

    def test_somme_issues_egal_total_par_scenario(self, cx):
        stats = statistiques(cx, 1)
        for s in stats["scenarios"]:
            total_issues = sum(s["par_issue"].values())
            assert total_issues == s["passages"], f"{s['label']}/{s['scenario']}: {total_issues} != {s['passages']}"

    def test_evaluables_plus_erreurs_egal_total(self, cx):
        stats = statistiques(cx, 1)
        for m in stats["moteurs"]:
            assert m["evaluables"] + m["erreurs_techniques"] == m["passages"]

    def test_denominateur_reussite_fonctionnelle(self, cx):
        stats = statistiques(cx, 1)
        for m in stats["moteurs"]:
            if m["reussite_fonctionnelle"] is not None:
                reussis = m["par_issue"].get("extraction_reussie", 0)
                evaluables = m["evaluables"]
                assert m["reussite_fonctionnelle"]["taux"] == pytest.approx(
                    round(reussis / evaluables, 4) if evaluables else 0, abs=1e-10
                )

    def test_denominateur_taux_blocage(self, cx):
        stats = statistiques(cx, 1)
        for m in stats["moteurs"]:
            if m["taux_blocage"] is not None:
                bloques = m["par_issue"].get("bloque", 0)
                evaluables = m["evaluables"]
                assert m["taux_blocage"]["taux"] == pytest.approx(
                    round(bloques / evaluables, 4) if evaluables else 0, abs=1e-10
                )


# ---------------------------------------------------------------------------
# E4 : Validité des intervalles de Wilson
# ---------------------------------------------------------------------------


class TestWilsonValidity:
    @pytest.mark.parametrize("k,n", [(0, 10), (5, 10), (10, 10), (1, 1), (0, 1), (3, 100)])
    def test_bornes_ordonnees(self, k, n):
        ic = wilson(k, n)
        assert ic is not None
        assert 0 <= ic["bas"] <= ic["taux"] <= ic["haut"] <= 1.0

    def test_wilson_zero_total_renvoie_none(self):
        assert wilson(0, 0) is None

    def test_wilson_k_egal_n(self):
        ic = wilson(20, 20)
        assert ic["taux"] == 1.0
        assert ic["haut"] == 1.0

    def test_wilson_k_zero(self):
        ic = wilson(0, 20)
        assert ic["taux"] == 0.0
        assert ic["bas"] == 0.0

    def test_tous_les_wilson_dans_statistiques(self, cx):
        """Vérifie que tous les IC Wilson dans les statistiques respectent 0 ≤ bas ≤ taux ≤ haut ≤ 1."""
        stats = statistiques(cx, 1)
        cles_wilson = ("reussite", "reussite_fonctionnelle", "taux_erreur_technique", "taux_blocage")
        for m in stats["moteurs"]:
            for cle in cles_wilson:
                ic = m[cle]
                if ic is not None:
                    assert 0 <= ic["bas"] <= ic["taux"] <= ic["haut"] <= 1.0, (
                        f"{m['label']}.{cle}: bas={ic['bas']}, taux={ic['taux']}, haut={ic['haut']}"
                    )


# ---------------------------------------------------------------------------
# E7 : Stabilité des rapports — mêmes données → même sortie
# ---------------------------------------------------------------------------


class TestStabiliteRapports:
    def test_csv_deterministe(self, cx):
        csv1 = reports.lignes_csv(cx, 1)
        csv2 = reports.lignes_csv(cx, 1)
        assert csv1 == csv2

    def test_json_deterministe(self, cx):
        j1 = reports.passages_json(cx, 1)
        j2 = reports.passages_json(cx, 1)
        assert j1 == j2

    def test_html_deterministe(self, cx):
        stats = statistiques(cx, 1)
        html1 = reports.rapport_html(stats)
        html2 = reports.rapport_html(stats)
        assert html1 == html2

    def test_statistiques_deterministes(self, cx):
        s1 = json.dumps(statistiques(cx, 1), sort_keys=True, default=str)
        s2 = json.dumps(statistiques(cx, 1), sort_keys=True, default=str)
        assert s1 == s2


# ---------------------------------------------------------------------------
# A4 : comparer() utilise des effectifs exacts (pas d'arrondi)
# ---------------------------------------------------------------------------


class TestComparerEffectifsExacts:
    def test_effectifs_coherents_avec_par_issue(self, cx):
        result = comparer(cx, 1, 2)
        stats_ref = statistiques(cx, 1)
        stats_new = statistiques(cx, 2)
        ref_moteurs = {m["label"]: m for m in stats_ref["moteurs"]}
        new_moteurs = {m["label"]: m for m in stats_new["moteurs"]}

        for m in result["moteurs"]:
            if m.get("only_in"):
                continue
            label = m["label"]
            r = ref_moteurs[label]
            n = new_moteurs[label]
            d = m["deltas"]["reussite"]
            r_ok = r["par_issue"].get("extraction_reussie", 0)
            n_ok = n["par_issue"].get("extraction_reussie", 0)
            r_taux = round(r_ok / r["passages"], 4) if r["passages"] else 0
            n_taux = round(n_ok / n["passages"], 4) if n["passages"] else 0
            assert d["reference"] == pytest.approx(r_taux, abs=1e-10)
            assert d["nouveau"] == pytest.approx(n_taux, abs=1e-10)

    def test_delta_est_difference_exacte(self, cx):
        result = comparer(cx, 1, 2)
        for m in result["moteurs"]:
            if m.get("only_in"):
                continue
            d = m["deltas"]["reussite"]
            ref_val = d["reference"] if d["reference"] is not None else 0
            new_val = d["nouveau"] if d["nouveau"] is not None else 0
            assert d["delta"] == pytest.approx(new_val - ref_val, abs=1e-4)
