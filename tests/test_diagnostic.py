"""Tests de régression pour les quatre rapports du module diagnostic."""

from __future__ import annotations

import json

import pytest

from shadowlab import database as db
from shadowlab import diagnostic as diag


@pytest.fixture
def cx(tmp_path):
    """Base en mémoire peuplée avec deux moteurs, deux protections et des décisions connues."""
    base = tmp_path / "test.sqlite3"
    cx = db.ouvrir(base)

    # Expérience
    cx.execute(
        "INSERT INTO experiments (id, name, created_at, configuration, status, seed)"
        " VALUES (1, 'test', '2026-01-01T00:00:00', '{}', 'termine', 42)"
    )

    # Moteurs
    cx.execute(
        "INSERT INTO engines (id, name, version, runtime, configuration)"
        " VALUES (1, 'playwright', '1.0', 'chromium', '{}')"
    )
    cx.execute(
        "INSERT INTO engines (id, name, version, runtime, configuration) VALUES (2, 'camoufox', '1.0', 'firefox', '{}')"
    )

    # Scénario
    cx.execute("INSERT INTO scenarios (id, name) VALUES (1, 'static_html')")

    # --- Playwright : bloqué dès 02 par fingerprinting (ua_headless) ---
    _run(cx, 1, eng=1, prot="01", success=1, issue="extraction_reussie")
    _run(cx, 2, eng=1, prot="02", success=0, issue="bloque")
    _decision(
        cx,
        "tok-run-2",
        "fingerprinting",
        "bloque",
        motifs=[
            {
                "detecteur": "regles-http",
                "signaux": [
                    {"code": "ua_headless", "description": "User-Agent HeadlessChrome", "poids": 1.0},
                    {"code": "langue_absente", "description": "Accept-Language absent", "poids": 0.5},
                ],
            },
        ],
    )
    _run(cx, 3, eng=1, prot="05", success=0, issue="bloque")
    _decision(
        cx,
        "tok-run-3",
        "fingerprinting",
        "bloque",
        motifs=[
            {
                "detecteur": "regles-http",
                "signaux": [
                    {"code": "ua_headless", "description": "User-Agent HeadlessChrome", "poids": 1.0},
                ],
            },
        ],
    )

    # --- Camoufox : passe 01-04, bloqué à 05 par turnstile ---
    _run(cx, 4, eng=2, prot="01", success=1, issue="extraction_reussie")
    _run(cx, 5, eng=2, prot="04", success=1, issue="extraction_reussie")
    _run(cx, 6, eng=2, prot="05", success=0, issue="echec_fonctionnel")
    _decision(cx, "tok-run-6", "defi-js", "emis")
    _decision(cx, "tok-run-6", "defi-js", "valide")
    _decision(cx, "tok-run-6", "turnstile", "emis")

    # Observations HTTP pour le rapport configurations (niveau 01)
    _obs_http(
        cx,
        "tok-run-1",
        "/lab/dynamique",
        [
            ["Host", "127.0.0.1"],
            ["User-Agent", "HeadlessChrome/1.0"],
            ["Accept-Language", ""],
            ["Sec-Fetch-Dest", "document"],
            ["Sec-CH-UA", '"Chromium"'],
        ],
    )
    _obs_http(
        cx,
        "tok-run-4",
        "/lab/dynamique",
        [
            ["Host", "127.0.0.1"],
            ["User-Agent", "Mozilla/5.0 Firefox/158.0"],
            ["Accept-Language", "en-US,en;q=0.9"],
            ["Sec-Fetch-Dest", "document"],
        ],
    )

    # Observations HTTP pour l'ablation (playwright, pour recalcul de détection)
    _obs_http(
        cx,
        "tok-run-2",
        "/lab/dynamique",
        [
            ["Host", "127.0.0.1"],
            ["User-Agent", "HeadlessChrome/1.0"],
        ],
        http_version="1.1",
    )

    return cx


def _run(cx, run_id, *, eng, prot, success, issue):
    token = f"tok-run-{run_id}"
    cx.execute(
        "INSERT INTO runs (id, experiment_id, engine_id, scenario_id, repetition,"
        " session_token, truth, started_at, status, success, protection, issue)"
        " VALUES (?, 1, ?, 1, 1, ?, 'automatise', '2026-01-01T00:00:00', 'termine', ?, ?, ?)",
        (run_id, eng, token, success, prot, issue),
    )


def _decision(cx, token, couche, decision, *, motifs=None):
    cx.execute(
        "INSERT INTO decisions (session_token, created_at, couche, decision, chemin, motifs)"
        " VALUES (?, '2026-01-01T00:00:00', ?, ?, '/lab/', ?)",
        (token, couche, decision, json.dumps(motifs or [], ensure_ascii=False)),
    )


def _obs_http(cx, token, path, headers, *, http_version="1.1"):
    cx.execute(
        "INSERT INTO observations_http (session_token, received_at, method, path, http_version, headers, cookies)"
        " VALUES (?, '2026-01-01T00:00:00', 'GET', ?, ?, ?, '[]')",
        (token, path, http_version, json.dumps(headers, ensure_ascii=False)),
    )


# ---- 1. signaux ----


class TestSignaux:
    def test_moteurs_detectes(self, cx):
        result = diag.signaux(cx, 1)
        noms = [r["moteur"] for r in result]
        assert "playwright" in noms
        assert "camoufox" not in noms

    def test_signaux_playwright(self, cx):
        result = diag.signaux(cx, 1)
        pw = next(r for r in result if r["moteur"] == "playwright")
        codes = {s["signal"] for s in pw["signaux"]}
        assert "ua_headless" in codes
        assert "langue_absente" in codes

    def test_pas_de_doublon(self, cx):
        result = diag.signaux(cx, 1)
        pw = next(r for r in result if r["moteur"] == "playwright")
        codes = [s["signal"] for s in pw["signaux"]]
        assert len(codes) == len(set(codes))


# ---- 2. chaine ----


class TestChaine:
    def test_playwright_bloque_par_fingerprinting(self, cx):
        result = diag.chaine(cx, 1)
        pw_02 = next(r for r in result if r["moteur"] == "playwright" and r["protection"] == "02")
        assert pw_02["couche_bloquante"] == "fingerprinting"
        assert pw_02["issue"] == "bloque"

    def test_camoufox_bloque_par_turnstile(self, cx):
        result = diag.chaine(cx, 1)
        cam_05 = next(r for r in result if r["moteur"] == "camoufox" and r["protection"] == "05")
        assert cam_05["couche_bloquante"] == "turnstile"

    def test_niveau_01_ok_absent(self, cx):
        """Les passages réussis au niveau 01 n'apparaissent pas dans la chaîne."""
        result = diag.chaine(cx, 1)
        ok_01 = [r for r in result if r["protection"] == "01" and r["issue"] == "extraction_reussie"]
        assert len(ok_01) == 0


# ---- 3. configurations ----


class TestConfigurations:
    def test_deux_moteurs(self, cx):
        result = diag.configurations(cx, 1)
        noms = {r["moteur"] for r in result}
        assert "playwright" in noms
        assert "camoufox" in noms

    def test_ua_differents(self, cx):
        result = diag.configurations(cx, 1)
        pw = next(r for r in result if r["moteur"] == "playwright")
        cam = next(r for r in result if r["moteur"] == "camoufox")
        assert "HeadlessChrome" in pw["user_agent"]
        assert "Firefox" in cam["user_agent"]

    def test_accept_language(self, cx):
        result = diag.configurations(cx, 1)
        cam = next(r for r in result if r["moteur"] == "camoufox")
        assert cam["accept_language"] == "en-US,en;q=0.9"

    def test_sec_fetch_present(self, cx):
        result = diag.configurations(cx, 1)
        pw = next(r for r in result if r["moteur"] == "playwright")
        assert pw["sec_fetch"] is True


# ---- 4. ablation ----


class TestAblation:
    def test_toutes_les_regles(self, cx):
        result = diag.ablation(cx, 1)
        noms = {r["regle_exclue"] for r in result}
        assert "regles-http" in noms
        assert "botd" in noms
        assert "tls" in noms

    def test_structure(self, cx):
        result = diag.ablation(cx, 1)
        for r in result:
            assert "total" in r
            assert "detectes" in r
            assert "echappes" in r
            assert "moteurs_echappes" in r
            assert r["total"] == r["detectes"] + r["echappes"]
