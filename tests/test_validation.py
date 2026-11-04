"""Passe 2 — Tests de validation statistique : réconciliation, Wilson CI, stabilité des rapports."""

from __future__ import annotations

import json

import pytest

from shadowlab import database as db
from shadowlab import reports
from shadowlab.analytics import comparer, qualite_metriques, statistiques, wilson
from shadowlab.campaigns import Experience, _plan, unites

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


# ---------------------------------------------------------------------------
# Passe 4 : Reproductibilité — warm-up, dépendance, versions
# ---------------------------------------------------------------------------


class TestWarmup:
    def test_warmup_exclus_des_statistiques(self, tmp_path):
        base = tmp_path / "warmup.sqlite3"
        cx = db.ouvrir(base)
        cx.execute(
            "INSERT INTO experiments (id, name, created_at, configuration, status, seed)"
            " VALUES (1, 'warmup-test', '2026-01-01', '{}', 'termine', 1)"
        )
        cx.execute(
            "INSERT INTO engines (id, name, version, runtime, configuration) VALUES (1, 'httpx', '{}', 'python', '{}')"
        )
        cx.execute("INSERT INTO scenarios (id, name) VALUES (1, 'static_html')")
        for rep in range(1, 6):
            is_warmup = 1 if rep <= 2 else 0
            cx.execute(
                "INSERT INTO runs (experiment_id, engine_id, scenario_id, repetition,"
                " session_token, truth, started_at, status, success, duration_ms,"
                " protection, issue, is_warmup)"
                " VALUES (1, 1, 1, ?, ?, 'automatise', '2026-01-01', 'reussi', 1, 100.0,"
                " '01', 'extraction_reussie', ?)",
                (rep, f"tok-{rep}", is_warmup),
            )
        stats = statistiques(cx, 1)
        assert stats["passages"] == 3
        assert stats["warmup_exclus"] == 2

    def test_warmup_inclus_quand_demande(self, tmp_path):
        from shadowlab.analytics import _passages

        base = tmp_path / "warmup2.sqlite3"
        cx = db.ouvrir(base)
        cx.execute(
            "INSERT INTO experiments (id, name, created_at, configuration, status)"
            " VALUES (1, 'test', '2026-01-01', '{}', 'termine')"
        )
        cx.execute(
            "INSERT INTO engines (id, name, version, runtime, configuration) VALUES (1, 'httpx', '{}', 'python', '{}')"
        )
        cx.execute("INSERT INTO scenarios (id, name) VALUES (1, 'static_html')")
        for rep in range(1, 4):
            cx.execute(
                "INSERT INTO runs (experiment_id, engine_id, scenario_id, repetition,"
                " session_token, truth, started_at, status, success, protection, is_warmup)"
                " VALUES (1, 1, 1, ?, ?, 'automatise', '2026-01-01', 'reussi', 1, '01', ?)",
                (rep, f"tok-{rep}", 1 if rep == 1 else 0),
            )
        assert len(_passages(cx, 1, inclure_warmup=False)) == 2
        assert len(_passages(cx, 1, inclure_warmup=True)) == 3


class TestDependanceRepetitions:
    def test_autocorrelation_resultats_identiques(self, tmp_path):
        """Si tous les résultats sont identiques, la variance est nulle → autocorrélation non mesurable."""
        from shadowlab.analytics import dependance_repetitions

        base = tmp_path / "dep.sqlite3"
        cx = db.ouvrir(base)
        cx.execute(
            "INSERT INTO experiments (id, name, created_at, configuration, status)"
            " VALUES (1, 'dep', '2026-01-01', '{}', 'termine')"
        )
        cx.execute(
            "INSERT INTO engines (id, name, version, runtime, configuration) VALUES (1, 'httpx', '{}', 'python', '{}')"
        )
        cx.execute("INSERT INTO scenarios (id, name) VALUES (1, 'static_html')")
        for rep in range(1, 11):
            cx.execute(
                "INSERT INTO runs (experiment_id, engine_id, scenario_id, repetition,"
                " session_token, truth, started_at, status, success, protection, issue)"
                " VALUES (1, 1, 1, ?, ?, 'automatise', '2026-01-01', 'reussi', 1, '01',"
                " 'extraction_reussie')",
                (rep, f"tok-{rep}"),
            )
        result = dependance_repetitions(cx, 1)
        assert result["resume"]["n_groupes"] == 1
        assert result["groupes"][0]["autocorrelation_lag1"] is None

    def test_autocorrelation_alternante(self, tmp_path):
        """Un pattern alternant (1, 0, 1, 0, …) donne une autocorrélation fortement négative."""
        from shadowlab.analytics import dependance_repetitions

        base = tmp_path / "dep2.sqlite3"
        cx = db.ouvrir(base)
        cx.execute(
            "INSERT INTO experiments (id, name, created_at, configuration, status)"
            " VALUES (1, 'dep2', '2026-01-01', '{}', 'termine')"
        )
        cx.execute(
            "INSERT INTO engines (id, name, version, runtime, configuration) VALUES (1, 'httpx', '{}', 'python', '{}')"
        )
        cx.execute("INSERT INTO scenarios (id, name) VALUES (1, 'static_html')")
        for rep in range(1, 21):
            success = 1 if rep % 2 == 1 else 0
            issue = "extraction_reussie" if success else "bloque"
            cx.execute(
                "INSERT INTO runs (experiment_id, engine_id, scenario_id, repetition,"
                " session_token, truth, started_at, status, success, protection, issue)"
                " VALUES (1, 1, 1, ?, ?, 'automatise', '2026-01-01', ?, ?, '01', ?)",
                (rep, f"tok-{rep}", "reussi" if success else "echec", success, issue),
            )
        result = dependance_repetitions(cx, 1)
        r1 = result["groupes"][0]["autocorrelation_lag1"]
        assert r1 is not None
        assert r1 < -0.5

    def test_trop_peu_de_repetitions(self, tmp_path):
        """Moins de 4 répétitions → le groupe est exclu."""
        from shadowlab.analytics import dependance_repetitions

        base = tmp_path / "dep3.sqlite3"
        cx = db.ouvrir(base)
        cx.execute(
            "INSERT INTO experiments (id, name, created_at, configuration, status)"
            " VALUES (1, 'dep3', '2026-01-01', '{}', 'termine')"
        )
        cx.execute(
            "INSERT INTO engines (id, name, version, runtime, configuration) VALUES (1, 'httpx', '{}', 'python', '{}')"
        )
        cx.execute("INSERT INTO scenarios (id, name) VALUES (1, 'static_html')")
        for rep in range(1, 4):
            cx.execute(
                "INSERT INTO runs (experiment_id, engine_id, scenario_id, repetition,"
                " session_token, truth, started_at, status, success, protection, issue)"
                " VALUES (1, 1, 1, ?, ?, 'automatise', '2026-01-01', 'reussi', 1, '01',"
                " 'extraction_reussie')",
                (rep, f"tok-{rep}"),
            )
        result = dependance_repetitions(cx, 1)
        assert result["resume"]["n_groupes"] == 0


class TestVersionsEnvironnement:
    def test_environnement_contient_arena_versions(self):
        from shadowlab.campaigns import environnement

        env = environnement()
        assert "shadowlab" in env
        assert "python" in env
        assert "arena_versions" not in env

    def test_experience_warmup_defaut_zero(self):
        from shadowlab.campaigns import Experience

        moteurs = [{"name": "httpx"}]
        exp = Experience(name="test-warmup", engines=moteurs, scenarios=["static_html"], repetitions=5)
        assert exp.warmup == 0

    def test_experience_warmup_positif(self):
        from shadowlab.campaigns import Experience

        moteurs = [{"name": "httpx"}]
        exp = Experience(name="test-warmup", engines=moteurs, scenarios=["static_html"], repetitions=5, warmup=2)
        assert exp.warmup == 2


class TestMigration6:
    def test_colonne_is_warmup_existe(self, tmp_path):
        base = tmp_path / "mig6.sqlite3"
        cx = db.ouvrir(base)
        cx.execute(
            "INSERT INTO experiments (id, name, created_at, configuration, status)"
            " VALUES (1, 'test', '2026-01-01', '{}', 'termine')"
        )
        cx.execute(
            "INSERT INTO engines (id, name, version, runtime, configuration) VALUES (1, 'httpx', '{}', 'python', '{}')"
        )
        cx.execute("INSERT INTO scenarios (id, name) VALUES (1, 'test')")
        cx.execute(
            "INSERT INTO runs (experiment_id, engine_id, scenario_id, repetition,"
            " session_token, truth, started_at, status, is_warmup)"
            " VALUES (1, 1, 1, 1, 'tok-1', 'automatise', '2026-01-01', 'reussi', 1)"
        )
        row = cx.execute("SELECT is_warmup FROM runs WHERE session_token = 'tok-1'").fetchone()
        assert row["is_warmup"] == 1


# ---------------------------------------------------------------------------
# Passe 5 : D1 — Matrice croisée moteur × protection × scénario
# ---------------------------------------------------------------------------


class TestMatriceCroisee:
    def test_matrice_croisee_presente(self, cx):
        stats = statistiques(cx, 1)
        assert "matrice_croisee" in stats
        assert len(stats["matrice_croisee"]) > 0

    def test_matrice_croisee_triplets_complets(self, cx):
        stats = statistiques(cx, 1)
        triplets = {(c["moteur"], c["protection"], c["scenario"]) for c in stats["matrice_croisee"]}
        moteurs = {m["label"] for m in stats["moteurs"]}
        protections = {p["protection"] for p in stats["par_protection"]}
        scenarios = {s["scenario"] for s in stats["scenarios"]}
        for m in moteurs:
            for p in protections:
                for s in scenarios:
                    assert (m, p, s) in triplets, f"triplet manquant: {m} × {p} × {s}"

    def test_matrice_croisee_somme_passages(self, cx):
        stats = statistiques(cx, 1)
        total_matrice = sum(c["passages"] for c in stats["matrice_croisee"])
        assert total_matrice == stats["passages"]

    def test_matrice_croisee_reconciliation_issues(self, cx):
        stats = statistiques(cx, 1)
        for c in stats["matrice_croisee"]:
            total_issues = sum(c["par_issue"].values())
            assert total_issues == c["passages"], (
                f"{c['moteur']}×{c['protection']}×{c['scenario']}: {total_issues} != {c['passages']}"
            )


# ---------------------------------------------------------------------------
# Passe 5 : D2 — Taux conditionnel réussite | non-bloqué
# ---------------------------------------------------------------------------


class TestTauxConditionnels:
    def test_reussite_si_non_bloque_presente(self, cx):
        stats = statistiques(cx, 1)
        for m in stats["moteurs"]:
            assert "reussite_si_non_bloque" in m

    def test_reussite_si_non_bloque_valeur_correcte(self, cx):
        stats = statistiques(cx, 1)
        for m in stats["moteurs"]:
            reussis = m["par_issue"].get("extraction_reussie", 0)
            bloques = m["par_issue"].get("bloque", 0)
            evaluables = m["evaluables"]
            non_bloques = evaluables - bloques
            if non_bloques > 0:
                attendu = round(reussis / non_bloques, 4)
                assert m["reussite_si_non_bloque"] is not None
                assert m["reussite_si_non_bloque"]["taux"] == pytest.approx(attendu, abs=1e-10)
            else:
                assert m["reussite_si_non_bloque"] is None

    def test_reussite_si_non_bloque_wilson_valide(self, cx):
        stats = statistiques(cx, 1)
        for m in stats["moteurs"]:
            ic = m["reussite_si_non_bloque"]
            if ic is not None:
                assert 0 <= ic["bas"] <= ic["taux"] <= ic["haut"] <= 1.0

    def test_reussite_si_non_bloque_dans_matrice(self, cx):
        stats = statistiques(cx, 1)
        for c in stats["matrice_croisee"]:
            assert "reussite_si_non_bloque" in c


# ---------------------------------------------------------------------------
# Passe 5 : D6 — Qualité des métriques (observe / estime / limite)
# ---------------------------------------------------------------------------


class TestQualiteMetriques:
    def test_qualite_presente_dans_moteurs(self, cx):
        stats = statistiques(cx, 1)
        for m in stats["moteurs"]:
            assert "qualite" in m
            assert isinstance(m["qualite"], dict)

    def test_qualite_presente_dans_matrice(self, cx):
        stats = statistiques(cx, 1)
        for c in stats["matrice_croisee"]:
            assert "qualite" in c

    def test_qualite_valeurs_permises(self, cx):
        stats = statistiques(cx, 1)
        valeurs_permises = {"observe", "estime", "limite"}
        for m in stats["moteurs"]:
            for cle, val in m["qualite"].items():
                assert val in valeurs_permises, f"{m['label']}.qualite.{cle} = {val!r}"

    def test_effectifs_toujours_observes(self, cx):
        stats = statistiques(cx, 1)
        for m in stats["moteurs"]:
            for cle in ("passages", "evaluables", "erreurs_techniques", "par_issue"):
                assert m["qualite"][cle] == "observe"

    def test_taux_estimes_avec_assez_de_donnees(self, cx):
        stats = statistiques(cx, 1)
        for m in stats["moteurs"]:
            if m["evaluables"] >= 10:
                for cle in ("reussite", "reussite_fonctionnelle"):
                    if m[cle] is not None:
                        assert m["qualite"][cle] == "estime", f"{m['label']}.qualite.{cle}"

    def test_qualite_metriques_petit_echantillon(self):
        bloc_petit = {
            "passages": 3,
            "evaluables": 2,
            "erreurs_techniques": 1,
            "par_issue": {"extraction_reussie": 2, "erreur_technique": 1},
            "reussite": wilson(2, 3),
            "reussite_fonctionnelle": wilson(2, 2),
            "taux_erreur_technique": wilson(1, 3),
            "taux_blocage": wilson(0, 2),
            "reussite_si_non_bloque": wilson(2, 2),
            "duree_ms": {"n": 3, "moyenne": 100.0},
            "navigation_ms": {"n": 3, "moyenne": 50.0},
            "cpu_pct": {"n": 0},
            "cpu_ms": {"n": 0},
            "memoire_mo": {"n": 0},
            "requetes": {"n": 0},
            "detection": {},
        }
        q = qualite_metriques(bloc_petit)
        for cle in ("reussite", "reussite_fonctionnelle", "taux_blocage", "reussite_si_non_bloque"):
            assert q[cle] == "limite", f"qualite.{cle} devrait être 'limite' avec n=2 évaluables"
        assert q["duree_ms"] == "limite"
        assert q["detection"] == "limite"


# ---------------------------------------------------------------------------
# Passe 6 : E1 — Golden dataset à résultats connus
# ---------------------------------------------------------------------------


def _golden_run(cx, rid, *, eng, sc, prot, issue, success, detections=None):
    status = "reussi" if success else "erreur"
    cx.execute(
        "INSERT INTO runs (id, experiment_id, engine_id, scenario_id, repetition,"
        " session_token, truth, started_at, status, success, duration_ms, protection, issue)"
        " VALUES (?, 1, ?, ?, ?, ?, 'automatise', '2026-01-01T00:00:00', ?, ?, ?, ?, ?)",
        (rid, eng, sc, rid, f"gold-{rid}", status, int(success), float(rid * 100), prot, issue),
    )
    if detections:
        for det_name, classification in detections.items():
            cx.execute(
                "INSERT INTO detections (run_id, detector_name, detector_version,"
                " classification, confidence, signals) VALUES (?, ?, '1.0', ?, 1.0, '[]')",
                (rid, det_name, classification),
            )


@pytest.fixture
def golden(tmp_path):
    base = tmp_path / "golden.sqlite3"
    cx = db.ouvrir(base)
    cx.execute(
        "INSERT INTO experiments (id, name, description, created_at, configuration, status, seed)"
        " VALUES (1, 'golden', 'golden dataset', '2026-01-01T00:00:00', '{}', 'termine', 42)"
    )
    cx.execute(
        "INSERT INTO engines (id, name, version, runtime, configuration)"
        " VALUES (1, 'httpx', '{\"httpx\": \"0.27\"}', 'python', '{}')"
    )
    cx.execute("INSERT INTO scenarios (id, name) VALUES (1, 'static_html')")

    _golden_run(
        cx,
        1,
        eng=1,
        sc=1,
        prot="01",
        issue="extraction_reussie",
        success=True,
        detections={"BotD": "humain"},
    )
    _golden_run(
        cx,
        2,
        eng=1,
        sc=1,
        prot="01",
        issue="extraction_reussie",
        success=True,
        detections={"BotD": "automatise"},
    )
    _golden_run(
        cx,
        3,
        eng=1,
        sc=1,
        prot="01",
        issue="bloque",
        success=False,
        detections={"BotD": "automatise"},
    )
    _golden_run(
        cx,
        4,
        eng=1,
        sc=1,
        prot="02",
        issue="extraction_reussie",
        success=True,
        detections={"BotD": "automatise"},
    )
    _golden_run(
        cx,
        5,
        eng=1,
        sc=1,
        prot="02",
        issue="erreur_technique",
        success=False,
        detections={"BotD": "indetermine"},
    )
    _golden_run(
        cx,
        6,
        eng=1,
        sc=1,
        prot="02",
        issue="challenge_non_valide",
        success=False,
        detections={"BotD": "automatise"},
    )
    return cx


class TestGoldenDataset:
    """E1 — Résultats attendus calculés à la main, vérifiés contre statistiques()."""

    def test_comptages_globaux(self, golden):
        s = statistiques(golden, 1)
        assert s["passages"] == 6
        m = s["moteurs"][0]
        assert m["passages"] == 6
        assert m["evaluables"] == 5
        assert m["erreurs_techniques"] == 1
        assert m["par_issue"] == {
            "extraction_reussie": 3,
            "bloque": 1,
            "erreur_technique": 1,
            "challenge_non_valide": 1,
        }

    def test_taux_globaux(self, golden):
        m = statistiques(golden, 1)["moteurs"][0]
        assert m["reussite"]["taux"] == round(3 / 6, 4)
        assert m["reussite_fonctionnelle"]["taux"] == round(3 / 5, 4)
        assert m["taux_erreur_technique"]["taux"] == round(1 / 6, 4)
        assert m["taux_blocage"]["taux"] == round(1 / 5, 4)
        assert m["reussite_si_non_bloque"]["taux"] == round(3 / 4, 4)

    def test_detection_botd(self, golden):
        m = statistiques(golden, 1)["moteurs"][0]
        det = m["detection"]["BotD"]
        assert det["vp"] == 4
        assert det["fn"] == 1
        assert det["indetermine"] == 1
        assert det["taux_detection"]["taux"] == round(4 / 5, 4)

    def test_matrice_par_protection(self, golden):
        s = statistiques(golden, 1)
        par_prot = {p["protection"]: p for p in s["par_protection"]}
        p01 = par_prot["01"]
        assert p01["passages"] == 3
        assert p01["evaluables"] == 3
        assert p01["par_issue"]["extraction_reussie"] == 2
        assert p01["par_issue"]["bloque"] == 1
        assert p01["reussite"]["taux"] == round(2 / 3, 4)
        assert p01["reussite_si_non_bloque"]["taux"] == round(2 / 2, 4)

        p02 = par_prot["02"]
        assert p02["passages"] == 3
        assert p02["evaluables"] == 2
        assert p02["par_issue"]["extraction_reussie"] == 1
        assert p02["taux_erreur_technique"]["taux"] == round(1 / 3, 4)

    def test_matrice_croisee_golden(self, golden):
        s = statistiques(golden, 1)
        mc = {(c["moteur"], c["protection"], c["scenario"]): c for c in s["matrice_croisee"]}
        assert len(mc) == 2

        c01 = mc[("httpx", "01", "static_html")]
        assert c01["passages"] == 3
        assert c01["reussite"]["taux"] == round(2 / 3, 4)

        c02 = mc[("httpx", "02", "static_html")]
        assert c02["passages"] == 3
        assert c02["reussite"]["taux"] == round(1 / 3, 4)

    def test_qualite_tags_golden(self, golden):
        m = statistiques(golden, 1)["moteurs"][0]
        q = m["qualite"]
        assert q["passages"] == "observe"
        assert q["par_issue"] == "observe"
        assert q["reussite"] == "limite"
        assert q["duree_ms"] == "limite"


# ---------------------------------------------------------------------------
# Passe 6 : E6 — Reproductibilité bout en bout par seed
# ---------------------------------------------------------------------------


class TestReproductibiliteSeed:
    def test_plan_deterministe_meme_seed(self):
        moteurs = [{"name": "httpx"}, {"name": "playwright"}]
        exp = Experience(
            name="repro",
            engines=moteurs,
            scenarios=["static_html", "api_json", "pagination"],
            protections=["01", "02"],
            repetitions=5,
            seed=12345,
        )
        plan1 = [(m.nom_affiche, p) for m, p in unites(exp)]
        plan2 = [(m.nom_affiche, p) for m, p in unites(exp)]
        assert plan1 == plan2

    def test_plan_scenarios_deterministe(self):
        moteurs = [{"name": "httpx"}]
        exp = Experience(
            name="repro-sc",
            engines=moteurs,
            scenarios=["static_html", "api_json", "pagination", "form_interaction"],
            protections=["01"],
            repetitions=3,
            seed=99999,
        )
        ordres1 = list(_plan(exp, exp.engines[0], "01"))
        ordres2 = list(_plan(exp, exp.engines[0], "01"))
        assert ordres1 == ordres2

    def test_seed_different_ordre_different(self):
        moteurs = [{"name": "httpx"}, {"name": "playwright"}, {"name": "selenium"}]
        exp_a = Experience(
            name="a",
            engines=moteurs,
            scenarios=["static_html", "api_json"],
            protections=["01", "02", "03"],
            repetitions=3,
            seed=111,
        )
        exp_b = Experience(
            name="b",
            engines=moteurs,
            scenarios=["static_html", "api_json"],
            protections=["01", "02", "03"],
            repetitions=3,
            seed=222,
        )
        plan_a = [(m.nom_affiche, p) for m, p in unites(exp_a)]
        plan_b = [(m.nom_affiche, p) for m, p in unites(exp_b)]
        assert set(plan_a) == set(plan_b)
        assert plan_a != plan_b

    def test_statistiques_identiques_deux_appels(self, golden):
        s1 = json.dumps(statistiques(golden, 1), sort_keys=True, default=str)
        s2 = json.dumps(statistiques(golden, 1), sort_keys=True, default=str)
        assert s1 == s2
