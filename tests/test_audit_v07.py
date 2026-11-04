"""Audit adversarial v0.7 — reproduction et non-régression des défauts confirmés.

Chaque classe cible un défaut précis identifié par l'audit. Les tests encodent
le comportement *correct* attendu ; ils échouent sur le code défectueux et
passent une fois la cause racine corrigée.
"""

from __future__ import annotations

import dataclasses
import random

import pytest

from shadowlab import database as db


def _exp_un_groupe(tmp_path, nom, suites):
    """Base avec une expérience et une suite de succès (0/1) pour un groupe moteur×protection×scénario."""
    cx = db.ouvrir(tmp_path / f"{nom}.sqlite3")
    cx.execute(
        "INSERT INTO experiments (id, name, created_at, configuration, status, seed)"
        " VALUES (1, ?, '2026-01-01', '{}', 'termine', 1)",
        (nom,),
    )
    cx.execute(
        "INSERT INTO engines (id, name, version, runtime, configuration) VALUES (1, 'httpx', '{}', 'python', '{}')"
    )
    cx.execute("INSERT INTO scenarios (id, name) VALUES (1, 'static_html')")
    rid = 0
    for rep, succ in enumerate(suites, start=1):
        rid += 1
        issue = "extraction_reussie" if succ else "bloque"
        cx.execute(
            "INSERT INTO runs (id, experiment_id, engine_id, scenario_id, repetition,"
            " session_token, truth, started_at, status, success, protection, issue)"
            " VALUES (?, 1, 1, 1, ?, ?, 'automatise', '2026-01-01', ?, ?, '01', ?)",
            (rid, rep, f"t-{rid}", "reussi" if succ else "echec", succ, issue),
        )
    return cx


# ---------------------------------------------------------------------------
# Défaut #4 — statut du passage calculé avant l'intégration du dépassement mémoire
# ---------------------------------------------------------------------------


class TestStatutDepassementMemoire:
    def test_depassement_avec_succes_nest_pas_reussi(self):
        """Un passage fonctionnellement réussi qui dépasse le plafond mémoire
        est une erreur technique, jamais 'reussi'."""
        from shadowlab.campaigns import _resultat_passage

        statut, erreur, succes = _resultat_passage(erreur=None, succes=True, depassement=True, plafond_mo=512)
        assert statut == "erreur", f"statut incohérent : {statut!r} avec dépassement mémoire"
        assert succes is False
        assert "plafond mémoire" in erreur

    def test_depassement_sans_erreur_prealable(self):
        from shadowlab.campaigns import _resultat_passage

        statut, erreur, succes = _resultat_passage(erreur=None, succes=False, depassement=True, plafond_mo=256)
        assert statut == "erreur"
        assert succes is False

    def test_sans_depassement_succes_reste_reussi(self):
        from shadowlab.campaigns import _resultat_passage

        statut, erreur, succes = _resultat_passage(erreur=None, succes=True, depassement=False, plafond_mo=512)
        assert statut == "reussi"
        assert succes is True
        assert erreur is None

    def test_erreur_prealable_prime(self):
        from shadowlab.campaigns import _resultat_passage

        statut, erreur, succes = _resultat_passage(
            erreur="TimeoutError: x", succes=None, depassement=False, plafond_mo=512
        )
        assert statut == "erreur"
        assert succes is False
        assert erreur == "TimeoutError: x"

    def test_chemin_reel_passage_depassement(self, tmp_path):
        """Chemin d'exécution RÉEL : _passage() avec un plafond mémoire d'1 Mo force
        le dépassement. Le passage est fonctionnellement réussi (scenario_natif) mais
        doit être enregistré en erreur, success=0, avec la cause mémoire."""
        from shadowlab import database as db
        from shadowlab.arena.profils import BASELINE
        from shadowlab.campaigns import Experience, _passage
        from shadowlab.config import charger
        from shadowlab.engines.base import MesuresSession
        from shadowlab.scenarios import SCENARIOS

        class FauxPilote:
            name = "faux"
            runtime = "python"
            executes_javascript = False

            def __init__(self):
                self.mesures = MesuresSession()

            def start_session(self):
                pass

            def scenario_natif(self, nom, base, jeton):
                return {"success": True, "details": {}}  # réussite fonctionnelle

            def close_session(self):
                pass

            def collect_metrics(self):
                return self.mesures

        reglages = dataclasses.replace(
            charger(),
            sorties=tmp_path,
            base_donnees=tmp_path / "db.sqlite3",
            memoire_max_mo=1,  # 1 Mo : dépassement garanti dès le premier relevé
        )
        cx = db.ouvrir(reglages.base_donnees)
        cx.execute(
            "INSERT INTO experiments (id, name, created_at, configuration, status, seed)"
            " VALUES (1, 'reel', '2026-01-01', '{}', 'en_cours', 1)"
        )
        experience = Experience(name="reel", engines=["httpx"], scenarios=["static_html"], repetitions=1, detectors=[])
        engine_id = db.engine_id(cx, "httpx", db.j({}), "python", {"label": "httpx"})
        scenario = SCENARIOS["static_html"]
        scenario_id = db.scenario_id(cx, scenario.name, scenario.description)

        with pytest.raises(MemoryError):
            _passage(
                cx,
                reglages,
                experience,
                1,
                FauxPilote(),
                engine_id,
                scenario,
                scenario_id,
                1,
                BASELINE,
                reglages.url_site,
                random.Random(0),
                tmp_path / "artefacts",
            )

        row = cx.execute("SELECT status, success, error FROM runs WHERE experiment_id = 1").fetchone()
        assert row["status"] == "erreur", f"statut réel incohérent : {row['status']!r}"
        assert row["success"] == 0
        assert "plafond mémoire" in (row["error"] or "")


# ---------------------------------------------------------------------------
# Défaut #7 — lag-1 ne prouve pas l'indépendance : diagnostic complémentaire requis
# ---------------------------------------------------------------------------


class TestDependanceRepetitions:
    def test_diagnostic_complementaire_present(self, tmp_path):
        """Le lag-1 seul ne suffit pas : un test des runs (Wald–Wolfowitz) doit
        accompagner chaque groupe, et le résumé ne doit pas affirmer l'indépendance."""
        from shadowlab.analytics import dependance_repetitions

        cx = _exp_un_groupe(tmp_path, "dep7", [1, 0, 1, 0, 1, 0, 1, 0, 1, 0])
        r = dependance_repetitions(cx, 1)
        assert r["groupes"], "aucun groupe mesuré"
        g = r["groupes"][0]
        assert "runs_test" in g, "diagnostic des runs absent — lag-1 est le seul indicateur"
        # Le résumé doit porter une mise en garde explicite, pas une affirmation d'indépendance.
        assert "avertissement" in r["resume"]

    def test_lag1_nul_mais_dependance_periodique(self, tmp_path):
        """Motif périodique (0,0,1,1,…) : lag-1 proche de 0 alors que la série
        est clairement dépendante. Le code ne doit jamais conclure à l'indépendance."""
        from shadowlab.analytics import dependance_repetitions

        cx = _exp_un_groupe(tmp_path, "dep7b", [0, 0, 1, 1] * 4)
        r = dependance_repetitions(cx, 1)
        g = r["groupes"][0]
        assert abs(g["autocorrelation_lag1"]) < 0.3
        assert "independant" not in g  # aucune affirmation d'indépendance
        assert g["runs_test"] is not None

    def test_runs_test_detecte_le_clustering(self, tmp_path):
        """Une série fortement groupée (0×5 puis 1×5) a trop peu de runs :
        le test des runs doit produire un z négatif marqué."""
        from shadowlab.analytics import dependance_repetitions

        cx = _exp_un_groupe(tmp_path, "dep7c", [0, 0, 0, 0, 0, 1, 1, 1, 1, 1])
        g = dependance_repetitions(cx, 1)["groupes"][0]
        assert g["runs_test"] is not None
        assert g["runs_test"]["runs"] == 2
        assert g["runs_test"]["z"] < -1.5


# ---------------------------------------------------------------------------
# Défaut #1 — matrice_confusion mélange des populations non comparables
# ---------------------------------------------------------------------------


def _matrice_confusion_base(tmp_path, nom, *, prot_auto, prot_humain, version_auto="2.0.0", version_humain="2.0.0"):
    """Expérience automatisée sous `prot_auto` et sessions humaines sous `prot_humain`.

    Détecteur 'botd' : 8 VP + 2 FN côté auto ; 5 VN + 1 FP côté humain.
    """
    cx = db.ouvrir(tmp_path / f"{nom}.sqlite3")
    cx.execute(
        "INSERT INTO experiments (id, name, created_at, configuration, status, seed)"
        " VALUES (1, 'auto', '2026-01-01', '{}', 'termine', 1)"
    )
    cx.execute(
        "INSERT INTO experiments (id, name, created_at, configuration, status)"
        " VALUES (2, 'sessions-manuelles', '2026-01-01', '{}', 'permanente')"
    )
    cx.execute(
        "INSERT INTO engines (id, name, version, runtime, configuration) VALUES (1, 'httpx', '{}', 'python', '{}')"
    )
    cx.execute("INSERT INTO scenarios (id, name) VALUES (1, 'static_html')")
    rid = 0

    def ajouter(exp, prot, classif, rep, version="2.0.0"):
        nonlocal rid
        rid += 1
        cx.execute(
            "INSERT INTO runs (id, experiment_id, engine_id, scenario_id, repetition,"
            " session_token, truth, started_at, status, success, protection, issue)"
            " VALUES (?, ?, 1, 1, ?, ?, ?, '2026-01-01', 'reussi', 1, ?, 'extraction_reussie')",
            (rid, exp, rep, f"t-{rid}", "automatise" if exp == 1 else "humain", prot),
        )
        cx.execute(
            "INSERT INTO detections (run_id, detector_name, detector_version, classification, confidence, signals)"
            " VALUES (?, 'botd', ?, ?, 0.5, '[]')",
            (rid, version, classif),
        )

    for i in range(8):
        ajouter(1, prot_auto, "automatise", i + 1, version=version_auto)  # VP
    for i in range(2):
        ajouter(1, prot_auto, "humain", i + 9, version=version_auto)  # FN
    for i in range(5):
        ajouter(2, prot_humain, "humain", i + 1, version=version_humain)  # VN
    ajouter(2, prot_humain, "automatise", 6, version=version_humain)  # FP
    return cx


class TestMatriceConfusionComparabilite:
    def test_populations_non_comparables_neutralisent_precision(self, tmp_path):
        """Auto sous '06', humain sous '01' : precision et F1 ne doivent pas être
        calculés (populations non comparables), et surtout pas valoir 1.0."""
        from shadowlab.analytics import matrice_confusion

        cx = _matrice_confusion_base(tmp_path, "mc1", prot_auto="06", prot_humain="01")
        m = matrice_confusion(cx, 1)["botd"]
        assert m["populations_comparables"] is False
        assert m["precision"] is None
        assert m["f1"] is None
        # Le rappel reste valide (population automatisée seule).
        assert m["rappel"]["taux"] == round(8 / 10, 4)

    def test_populations_comparables_autorisent_precision(self, tmp_path):
        """Auto et humain sous la même protection '06' : precision devient calculable."""
        from shadowlab.analytics import matrice_confusion

        cx = _matrice_confusion_base(tmp_path, "mc2", prot_auto="06", prot_humain="06")
        m = matrice_confusion(cx, 1)["botd"]
        assert m["populations_comparables"] is True
        assert m["precision"] is not None
        assert m["precision"]["taux"] == round(8 / 9, 4)  # VP / (VP + FP)
        assert m["f1"] is not None
        # La précision reste étiquetée dépendante de la prévalence assemblée.
        assert m["precision"]["prevalence_dependante"] is True
        assert m["f1"]["prevalence_dependante"] is True
        assert m["prevalence_assemblee"] == round(10 / 16, 4)  # n_auto=10, fp+vn=6

    def test_versions_detecteur_incompatibles(self, tmp_path):
        """Même protection mais versions de détecteur différentes : precision/F1 neutralisés."""
        from shadowlab.analytics import matrice_confusion

        cx = _matrice_confusion_base(
            tmp_path, "mc3", prot_auto="06", prot_humain="06", version_auto="2.0.0", version_humain="1.0.0"
        )
        m = matrice_confusion(cx, 1)["botd"]
        assert m["populations_comparables"] is False
        assert "versions" in (m["comparabilite"] or "")
        assert m["precision"] is None
        # Le rappel (population auto seule) et le FPR (population humaine seule) restent calculés.
        assert m["rappel"] is not None
        assert m["taux_faux_positifs"] is not None


# ---------------------------------------------------------------------------
# Défaut #5 — comparer() ne vérifie pas l'équivalence des designs expérimentaux
# ---------------------------------------------------------------------------


def _exp_comparer(cx, exp_id, *, protections, scenarios, n_ok, n_total):
    import json

    config = json.dumps(
        {
            "name": f"exp{exp_id}",
            "scenarios": scenarios,
            "protections": protections,
            "engines": [{"name": "httpx", "label": "httpx", "options": {}}],
        }
    )
    cx.execute(
        "INSERT INTO experiments (id, name, created_at, configuration, status, seed)"
        " VALUES (?, ?, '2026-01-01', ?, 'termine', 1)",
        (exp_id, f"exp{exp_id}", config),
    )
    if exp_id == 1:
        cx.execute(
            "INSERT INTO engines (id, name, version, runtime, configuration)"
            " VALUES (1, 'httpx', '{}', 'python', '{\"label\": \"httpx\"}')"
        )
        cx.execute("INSERT INTO scenarios (id, name) VALUES (1, 'static_html')")
    base = exp_id * 1000
    for i in range(n_total):
        succ = 1 if i < n_ok else 0
        cx.execute(
            "INSERT INTO runs (id, experiment_id, engine_id, scenario_id, repetition,"
            " session_token, truth, started_at, status, success, protection, issue)"
            " VALUES (?, ?, 1, 1, ?, ?, 'automatise', '2026-01-01', ?, ?, ?, ?)",
            (
                base + i,
                exp_id,
                i + 1,
                f"t-{base + i}",
                "reussi" if succ else "echec",
                succ,
                protections[0],
                "extraction_reussie" if succ else "bloque",
            ),
        )


class TestComparerDesignEquivalence:
    def test_designs_differents_refuses(self, tmp_path):
        """Protections différentes (01 vs 06) : comparer() doit refuser la comparaison
        statistique et signaler la différence, pas émettre un verdict de significativité."""
        from shadowlab.analytics import comparer

        cx = db.ouvrir(tmp_path / "cmp1.sqlite3")
        _exp_comparer(cx, 1, protections=["01"], scenarios=["static_html"], n_ok=28, n_total=30)
        _exp_comparer(cx, 2, protections=["06"], scenarios=["static_html"], n_ok=3, n_total=30)
        res = comparer(cx, 1, 2)
        assert res["comparable"] is False
        assert "protections" in res["differences"]
        # Aucun verdict de significativité ne doit être produit sur des designs non équivalents.
        for m in res.get("moteurs", []):
            assert "significatif" not in m.get("deltas", {}).get("reussite", {})

    def test_designs_identiques_compares(self, tmp_path):
        """Mêmes protections et scénarios : la comparaison est autorisée."""
        from shadowlab.analytics import comparer

        cx = db.ouvrir(tmp_path / "cmp2.sqlite3")
        _exp_comparer(cx, 1, protections=["01"], scenarios=["static_html"], n_ok=28, n_total=30)
        _exp_comparer(cx, 2, protections=["01"], scenarios=["static_html"], n_ok=10, n_total=30)
        res = comparer(cx, 1, 2)
        assert res["comparable"] is True
        reussite = res["moteurs"][0]["deltas"]["reussite"]
        assert "significatif" in reussite
