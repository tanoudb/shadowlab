"""Audit adversarial v0.7 — reproduction et non-régression des défauts confirmés.

Chaque classe cible un défaut précis identifié par l'audit. Les tests encodent
le comportement *correct* attendu ; ils échouent sur le code défectueux et
passent une fois la cause racine corrigée.
"""

from __future__ import annotations

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


def _matrice_confusion_base(tmp_path, nom, *, prot_auto, prot_humain):
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

    def ajouter(exp, prot, classif, rep):
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
            " VALUES (?, 'botd', '2.0.0', ?, 0.5, '[]')",
            (rid, classif),
        )

    for i in range(8):
        ajouter(1, prot_auto, "automatise", i + 1)  # VP
    for i in range(2):
        ajouter(1, prot_auto, "humain", i + 9)  # FN
    for i in range(5):
        ajouter(2, prot_humain, "humain", i + 1)  # VN
    ajouter(2, prot_humain, "automatise", 6)  # FP
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
