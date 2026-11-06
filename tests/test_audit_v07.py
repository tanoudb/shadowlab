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


# ---------------------------------------------------------------------------
# Défaut #3 — serveur_local vérifiait une connexion TCP sans identité
# ---------------------------------------------------------------------------


class TestIdentiteServeur:
    def test_endpoint_sante_signe(self):
        """Le site expose /lab/sante avec une signature identifiable."""
        from fastapi.testclient import TestClient

        from shadowlab.config import charger
        from shadowlab.site.app import creer_app

        # Host autorisé : le garde anti-DNS-rebinding n'accepte que les noms locaux.
        client = TestClient(creer_app(charger()), base_url="http://127.0.0.1")
        r = client.get("/lab/sante")
        assert r.status_code == 200
        assert r.json()["service"] == "shadowlab-site"

    def test_serveur_etranger_refuse(self, tmp_path):
        """Chemin RÉEL : un service étranger écoute sur le port. serveur_local doit
        refuser (identité /lab/sante absente), au lieu de lancer la campagne contre lui."""
        import dataclasses
        import http.server
        import threading

        from shadowlab.campaigns import serveur_local
        from shadowlab.config import charger

        class Etranger(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"je ne suis pas shadowlab")

            def log_message(self, *a):
                pass

        serveur = http.server.HTTPServer(("127.0.0.1", 0), Etranger)
        port = serveur.server_address[1]
        fil = threading.Thread(target=serveur.serve_forever, daemon=True)
        fil.start()
        try:
            reglages = dataclasses.replace(
                charger(), hote="127.0.0.1", port=port, sorties=tmp_path, base_donnees=tmp_path / "db.sqlite3"
            )
            with pytest.raises(RuntimeError, match="étranger|non identifié"):
                with serveur_local(reglages):
                    pass
        finally:
            serveur.shutdown()
            fil.join(timeout=5)

    def test_identite_site_faux_pour_etranger(self, tmp_path):
        """_identite_site renvoie False pour un serveur sans la signature."""
        import dataclasses
        import http.server
        import threading

        from shadowlab.campaigns import _identite_site, _repond
        from shadowlab.config import charger

        class Etranger(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"service": "autre-chose"}')

            def log_message(self, *a):
                pass

        serveur = http.server.HTTPServer(("127.0.0.1", 0), Etranger)
        port = serveur.server_address[1]
        fil = threading.Thread(target=serveur.serve_forever, daemon=True)
        fil.start()
        try:
            reglages = dataclasses.replace(charger(), hote="127.0.0.1", port=port)
            # Ancien critère (connexion TCP seule) : aurait accepté ce serveur étranger.
            assert _repond("127.0.0.1", port) is True
            # Nouveau critère (identité signée) : le rejette.
            assert _identite_site(reglages) is False
        finally:
            serveur.shutdown()
            fil.join(timeout=5)


# ---------------------------------------------------------------------------
# Défaut #6 — campagne déclarée « termine » alors qu'un moteur n'a pas démarré
# ---------------------------------------------------------------------------


class _FauxMoteurCasse:
    name = "faux_casse"
    runtime = "python"
    categorie = "standard"
    options_permises: dict = {}

    def __init__(self, hotes, options=None):
        self.hotes = hotes

    @classmethod
    def controler_options(cls, options):
        if options:
            raise ValueError("aucune option permise")

    @classmethod
    def manque(cls):
        return None

    def open(self):
        raise RuntimeError("binaire introuvable")

    def versions(self):
        return {}

    def configuration(self):
        return {}


class TestCampagneMoteurAbsent:
    def test_campagne_incomplete_si_moteur_ne_demarre_pas(self, tmp_path, monkeypatch):
        """Chemin RÉEL : executer() avec un moteur dont open() échoue ne doit PAS
        rendre 'termine' mais 'termine_incomplet', tout en enregistrant les passages
        en erreur 'démarrage impossible'."""
        import contextlib
        import dataclasses

        from shadowlab import campaigns
        from shadowlab import database as db
        from shadowlab.arena.profils import BASELINE
        from shadowlab.config import charger

        registre_patche = {"faux_casse": _FauxMoteurCasse}
        monkeypatch.setattr(campaigns, "registre", lambda: registre_patche)
        monkeypatch.setattr(campaigns, "serveur_local", lambda reglages: contextlib.nullcontext())

        reglages = dataclasses.replace(
            charger(),
            sorties=tmp_path,
            base_donnees=tmp_path / "db.sqlite3",
            hotes_autorises=tuple({*charger().hotes_autorises, "127.0.0.1"}),
        )
        cx = db.ouvrir(reglages.base_donnees)
        experience = campaigns.Experience(
            name="moteur-casse",
            engines=["faux_casse"],
            protections=[BASELINE],
            scenarios=["static_html"],
            repetitions=2,
            detectors=[],
            seed=1,
        )
        experiment_id = campaigns.creer(cx, experience, reglages)
        cx.close()

        statut = campaigns.executer(reglages, experiment_id)
        assert statut == "termine_incomplet", f"statut trompeur : {statut!r}"

        cx = db.ouvrir(reglages.base_donnees)
        rows = cx.execute("SELECT status, error FROM runs WHERE experiment_id = ?", (experiment_id,)).fetchall()
        assert rows, "aucun passage enregistré"
        assert all(r["status"] == "erreur" for r in rows)
        assert all("démarrage impossible" in (r["error"] or "") for r in rows)


# ---------------------------------------------------------------------------
# Défaut #2 — confidence est un score heuristique non calibré, pas une probabilité
# ---------------------------------------------------------------------------


def _exp_confidence(tmp_path, nom, confidence):
    cx = db.ouvrir(tmp_path / f"{nom}.sqlite3")
    cx.execute(
        "INSERT INTO experiments (id, name, created_at, configuration, status, seed)"
        " VALUES (1, ?, '2026-01-01', '{}', 'termine', 1)",
        (nom,),
    )
    cx.execute(
        "INSERT INTO engines (id, name, version, runtime, configuration)"
        " VALUES (1, 'httpx', '{}', 'python', '{\"label\": \"httpx\"}')"
    )
    cx.execute("INSERT INTO scenarios (id, name) VALUES (1, 'static_html')")
    for i in range(10):
        classif = "automatise" if i < 7 else "humain"
        cx.execute(
            "INSERT INTO runs (id, experiment_id, engine_id, scenario_id, repetition,"
            " session_token, truth, started_at, status, success, protection, issue)"
            " VALUES (?, 1, 1, 1, ?, ?, 'automatise', '2026-01-01', 'reussi', 1, '01', 'extraction_reussie')",
            (i + 1, i + 1, f"t-{i}"),
        )
        cx.execute(
            "INSERT INTO detections (run_id, detector_name, detector_version, classification, confidence, signals)"
            " VALUES (?, 'botd', '2.0.0', ?, ?, '[]')",
            (i + 1, classif, confidence),
        )
    return cx


class TestConfidenceNonCalibree:
    def test_confidence_ninfluence_aucune_statistique(self, tmp_path):
        """Deux expériences identiques sauf la confidence (0.1 vs 0.99) doivent
        produire exactement les mêmes taux de détection : confidence n'entre dans
        aucun calcul."""
        import json

        from shadowlab.analytics import statistiques

        cx_bas = _exp_confidence(tmp_path, "conf_bas", 0.1)
        cx_haut = _exp_confidence(tmp_path, "conf_haut", 0.99)
        det_bas = statistiques(cx_bas, 1)["moteurs"][0]["detection"]
        det_haut = statistiques(cx_haut, 1)["moteurs"][0]["detection"]
        assert json.dumps(det_bas, sort_keys=True) == json.dumps(det_haut, sort_keys=True)

    def test_limite_documente_confidence(self):
        """La limitation sur la confidence non calibrée est explicitement documentée."""
        from shadowlab.analytics import LIMITES

        assert any("calibr" in limite.lower() for limite in LIMITES)


# ---------------------------------------------------------------------------
# Phase 2 — Isolation de session (évidence partielle pour #7)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Défaut D1 (audit campagne #17) — COUCHES_CHALLENGE manque turnstile et recaptcha
# ---------------------------------------------------------------------------


class TestCouchesChallenge:
    def test_turnstile_emis_non_valide_donne_challenge_non_valide(self):
        """Un passage où Turnstile est émis mais jamais validé doit être classé
        challenge_non_valide, pas echec_fonctionnel."""
        from shadowlab.issues import evaluer

        decisions = [
            {"couche": "defi-js", "decision": "emis", "motifs": []},
            {"couche": "defi-js", "decision": "valide", "motifs": []},
            {"couche": "turnstile", "decision": "emis", "motifs": []},
        ]
        result = evaluer(
            success=False,
            erreur=None,
            http=[{"status": 200}],
            decisions=decisions,
            classements=[],
            sous_arena=True,
            motif_echec="page de protection à la place de https://localhost:8743/lab/statique",
        )
        assert result.issue == "challenge_non_valide", (
            f"Turnstile émis sans validation : attendu challenge_non_valide, obtenu {result.issue!r}"
        )
        assert "turnstile" in result.cause

    def test_recaptcha_emis_non_valide_donne_challenge_non_valide(self):
        """Même vérification pour reCAPTCHA."""
        from shadowlab.issues import evaluer

        decisions = [
            {"couche": "recaptcha", "decision": "emis", "motifs": []},
        ]
        result = evaluer(
            success=False,
            erreur=None,
            http=[{"status": 200}],
            decisions=decisions,
            classements=[],
            sous_arena=True,
            motif_echec="page de protection",
        )
        assert result.issue == "challenge_non_valide"
        assert "recaptcha" in result.cause

    def test_turnstile_valide_ne_bloque_pas_classification(self):
        """Si Turnstile est émis ET validé, il ne doit pas produire challenge_non_valide."""
        from shadowlab.issues import evaluer

        decisions = [
            {"couche": "turnstile", "decision": "emis", "motifs": []},
            {"couche": "turnstile", "decision": "valide", "motifs": []},
        ]
        result = evaluer(
            success=False,
            erreur=None,
            http=[{"status": 200}],
            decisions=decisions,
            classements=[],
            sous_arena=True,
            motif_echec="résultat attendu non obtenu",
        )
        assert result.issue != "challenge_non_valide"

    def test_couches_challenge_contient_turnstile_et_recaptcha(self):
        """Vérification directe : COUCHES_CHALLENGE inclut les 4 types de challenge."""
        from shadowlab.issues import COUCHES_CHALLENGE

        assert "turnstile" in COUCHES_CHALLENGE
        assert "recaptcha" in COUCHES_CHALLENGE
        assert "captcha" in COUCHES_CHALLENGE
        assert "defi-js" in COUCHES_CHALLENGE


# ---------------------------------------------------------------------------
# P0.2 — Métriques séparées : détection, challenge, challenge non validé
# ---------------------------------------------------------------------------


def _exp_metriques(tmp_path):
    """Expérience avec 6 passages couvrant les 4 issues utiles aux taux P0.2."""
    import json

    cx = db.ouvrir(tmp_path / "metriques.sqlite3")
    cx.execute(
        "INSERT INTO experiments (id, name, created_at, configuration, status, seed)"
        " VALUES (1, 'metriques', '2026-01-01', '{}', 'termine', 1)"
    )
    cx.execute(
        "INSERT INTO engines (id, name, version, runtime, configuration)"
        " VALUES (1, 'httpx', '{}', 'python', '{\"label\": \"httpx\"}')"
    )
    cx.execute("INSERT INTO scenarios (id, name) VALUES (1, 'static_html')")

    passages = [
        # (id, success, issue, drapeaux_dict, has_detection)
        (1, 1, "extraction_reussie", {"challenge_declenche": False}, False),
        (2, 0, "bloque", {"challenge_declenche": False}, True),
        (3, 0, "challenge_non_valide", {"challenge_declenche": True}, True),
        (4, 0, "erreur_technique", {"challenge_declenche": False}, False),
        (5, 0, "bloque", {"challenge_declenche": False}, True),
        (6, 1, "extraction_reussie", {"challenge_declenche": True}, True),
    ]
    for rid, succ, issue, drp, has_det in passages:
        cx.execute(
            "INSERT INTO runs (id, experiment_id, engine_id, scenario_id, repetition,"
            " session_token, truth, started_at, status, success, protection, issue, drapeaux)"
            " VALUES (?, 1, 1, 1, ?, ?, 'automatise', '2026-01-01', ?, ?, '01', ?, ?)",
            (rid, rid, f"t-{rid}", "reussi" if succ else "echec", succ, issue, json.dumps(drp)),
        )
        if has_det:
            cx.execute(
                "INSERT INTO detections (run_id, detector_name, detector_version, classification, confidence, signals)"
                " VALUES (?, 'botd', '2.0.0', 'automatise', 0.8, '[]')",
                (rid,),
            )
    return cx


class TestMetriquesSeparees:
    def test_quatre_taux_presents_et_distincts(self, tmp_path):
        """statistiques() renvoie 4 taux Wilson séparés : succès, détection, challenge, blocage."""
        from shadowlab.analytics import statistiques

        cx = _exp_metriques(tmp_path)
        stats = statistiques(cx, 1)
        m = stats["moteurs"][0]
        for cle in ("reussite", "taux_detection", "taux_challenge", "taux_challenge_non_valide", "taux_blocage"):
            assert cle in m, f"taux manquant : {cle}"
            assert m[cle] is not None, f"{cle} est None"
            assert "taux" in m[cle] and "bas" in m[cle] and "haut" in m[cle], f"{cle} sans IC Wilson"

    def test_taux_detection_correct(self, tmp_path):
        """taux_detection = passages classés automatisé par ≥1 détecteur / évaluables."""
        from shadowlab.analytics import statistiques

        cx = _exp_metriques(tmp_path)
        m = statistiques(cx, 1)["moteurs"][0]
        # 6 passages, 1 erreur technique → 5 évaluables
        # Passages avec détection automatisé : 2, 3, 5, 6 → 4
        assert m["taux_detection"]["taux"] == round(4 / 5, 4)

    def test_taux_challenge_correct(self, tmp_path):
        """taux_challenge = passages avec challenge déclenché / évaluables."""
        from shadowlab.analytics import statistiques

        cx = _exp_metriques(tmp_path)
        m = statistiques(cx, 1)["moteurs"][0]
        # Passages avec challenge_declenche=True : 3, 6 → 2
        assert m["taux_challenge"]["taux"] == round(2 / 5, 4)

    def test_taux_challenge_non_valide_correct(self, tmp_path):
        """taux_challenge_non_valide = passages issue=challenge_non_valide / évaluables."""
        from shadowlab.analytics import statistiques

        cx = _exp_metriques(tmp_path)
        m = statistiques(cx, 1)["moteurs"][0]
        # Passage 3 seul a issue=challenge_non_valide → 1
        assert m["taux_challenge_non_valide"]["taux"] == round(1 / 5, 4)

    def test_qualite_taux_nouveaux(self, tmp_path):
        """Les 3 nouveaux taux ont une qualification de qualité dans le bloc."""
        from shadowlab.analytics import statistiques

        cx = _exp_metriques(tmp_path)
        m = statistiques(cx, 1)["moteurs"][0]
        for cle in ("taux_detection", "taux_challenge", "taux_challenge_non_valide"):
            assert cle in m["qualite"], f"qualite manquante pour {cle}"

    def test_sans_drapeaux_challenge_zero(self, tmp_path):
        """Passages sans colonne drapeaux : taux_challenge doit être 0, pas une erreur."""
        from shadowlab.analytics import statistiques

        cx = db.ouvrir(tmp_path / "no_drp.sqlite3")
        cx.execute(
            "INSERT INTO experiments (id, name, created_at, configuration, status, seed)"
            " VALUES (1, 'nd', '2026-01-01', '{}', 'termine', 1)"
        )
        cx.execute(
            "INSERT INTO engines (id, name, version, runtime, configuration)"
            " VALUES (1, 'httpx', '{}', 'python', '{\"label\": \"httpx\"}')"
        )
        cx.execute("INSERT INTO scenarios (id, name) VALUES (1, 'static_html')")
        cx.execute(
            "INSERT INTO runs (id, experiment_id, engine_id, scenario_id, repetition,"
            " session_token, truth, started_at, status, success, protection, issue)"
            " VALUES (1, 1, 1, 1, 1, 't-1', 'automatise', '2026-01-01', 'reussi', 1, '01', 'extraction_reussie')"
        )
        m = statistiques(cx, 1)["moteurs"][0]
        assert m["taux_challenge"]["taux"] == 0.0


# ---------------------------------------------------------------------------
# P0.3 — Versionnement des détecteurs et moteurs
# ---------------------------------------------------------------------------


class TestVersionnement:
    def test_schema_version_dans_experiments(self, tmp_path):
        """creer() enregistre le numéro de schéma courant dans schema_version."""
        from shadowlab import campaigns
        from shadowlab.campaigns import Experience

        cx = db.ouvrir(tmp_path / "ver.sqlite3")
        experience = Experience(
            name="ver", engines=["httpx"], scenarios=["static_html"], repetitions=1, detectors=[], seed=1
        )
        exp_id = campaigns.creer(cx, experience)
        row = cx.execute("SELECT schema_version FROM experiments WHERE id = ?", (exp_id,)).fetchone()
        assert row["schema_version"] == db.SCHEMA_VERSION
        assert row["schema_version"] >= 7

    def test_engine_version_dans_run(self, tmp_path):
        """demarrer() enregistre engine_version sur le run."""
        from shadowlab.passages import demarrer

        cx = db.ouvrir(tmp_path / "ev.sqlite3")
        cx.execute(
            "INSERT INTO experiments (id, name, created_at, configuration, status, seed)"
            " VALUES (1, 'ev', '2026-01-01', '{}', 'en_cours', 1)"
        )
        cx.execute(
            "INSERT INTO engines (id, name, version, runtime, configuration) VALUES (1, 'httpx', '{}', 'python', '{}')"
        )
        cx.execute("INSERT INTO scenarios (id, name) VALUES (1, 'static_html')")
        run_id, _ = demarrer(cx, 1, 1, 1, 1, "automatise", engine_version='{"httpx": "0.28.1"}')
        row = cx.execute("SELECT engine_version FROM runs WHERE id = ?", (run_id,)).fetchone()
        assert row["engine_version"] == '{"httpx": "0.28.1"}'

    def test_engine_version_defaut_vide(self, tmp_path):
        """Sans engine_version, la colonne vaut '' (pas NULL)."""
        from shadowlab.passages import demarrer

        cx = db.ouvrir(tmp_path / "ev2.sqlite3")
        cx.execute(
            "INSERT INTO experiments (id, name, created_at, configuration, status, seed)"
            " VALUES (1, 'ev2', '2026-01-01', '{}', 'en_cours', 1)"
        )
        cx.execute(
            "INSERT INTO engines (id, name, version, runtime, configuration) VALUES (1, 'httpx', '{}', 'python', '{}')"
        )
        cx.execute("INSERT INTO scenarios (id, name) VALUES (1, 'static_html')")
        run_id, _ = demarrer(cx, 1, 1, 1, 1, "automatise")
        row = cx.execute("SELECT engine_version FROM runs WHERE id = ?", (run_id,)).fetchone()
        assert row["engine_version"] == ""

    def test_detector_version_existe_deja(self, tmp_path):
        """La colonne detector_version existe sur detections depuis la migration 1."""
        cx = db.ouvrir(tmp_path / "col.sqlite3")
        colonnes = [r[1] for r in cx.execute("PRAGMA table_info(detections)")]
        assert "detector_version" in colonnes

    def test_migration_7_ajoute_colonnes(self, tmp_path):
        """Migration 7 ajoute engine_version sur runs et schema_version sur experiments."""
        cx = db.ouvrir(tmp_path / "mig.sqlite3")
        colonnes_runs = [r[1] for r in cx.execute("PRAGMA table_info(runs)")]
        assert "engine_version" in colonnes_runs
        colonnes_exp = [r[1] for r in cx.execute("PRAGMA table_info(experiments)")]
        assert "schema_version" in colonnes_exp


class TestIsolationSession:
    def test_httpx_jar_cookies_remis_a_zero(self):
        """httpx : chaque start_session ouvre un client neuf → le jar de cookies ne
        fuit pas d'une session à l'autre. Isolation vérifiée sur le vrai pilote."""
        from shadowlab.engines.httpx_engine import DriverHttpx

        d = DriverHttpx(("127.0.0.1",))
        d.start_session()
        client_1 = d._client
        d._client.cookies.set("sid", "secret", domain="127.0.0.1")
        assert len(d._client.cookies) == 1
        d.close_session()

        d.start_session()
        client_2 = d._client
        assert client_2 is not client_1, "le client httpx est réutilisé entre sessions"
        assert len(d._client.cookies) == 0, "fuite de cookies entre sessions httpx"
        d.close_session()
