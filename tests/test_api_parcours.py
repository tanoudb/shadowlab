"""Socle API du parcours expérimental : catalogue, validation, progression, flux SSE, artefacts.

Ces tests ne lancent aucune campagne réelle (pas de navigateur) : ils insèrent des passages
directement en base pour vérifier que les endpoints lisent le véritable état, pas des données simulées.
"""

from __future__ import annotations

from shadowlab import campaigns
from shadowlab import database as db


def _mini_experience() -> campaigns.Experience:
    return campaigns.Experience.model_validate(
        {
            "name": "test-parcours",
            "engines": ["httpx"],
            "protections": ["01"],
            "scenarios": ["static_html"],
            "repetitions": 2,
            "seed": 7,
        }
    )


def _insérer_passage(cx, exp_id, eng, scn, *, repetition, statut, jeton, issue=None, duree=None):
    cx.execute(
        "INSERT INTO runs (experiment_id, engine_id, scenario_id, repetition, session_token, truth,"
        " started_at, status, duration_ms, issue, protection, is_warmup)"
        " VALUES (?, ?, ?, ?, ?, 'automatise', ?, ?, ?, ?, '01', 0)",
        (exp_id, eng, scn, repetition, jeton, db.maintenant(), statut, duree, issue),
    )


def test_catalogue_protections(client):
    data = client.get("/api/protections").json()
    niveaux = {p["code"]: p for p in data["protections"]}
    assert "01" in niveaux
    assert niveaux["01"]["baseline"] is True
    # chaque niveau décrit ce qu'il active : la clé waf doit être présente
    assert all("waf" in p and "defi_js" in p for p in data["protections"])


def test_valider_compte_les_passages(client):
    corps = {
        "experiment": {
            "name": "essai-valide",
            "engines": ["httpx", "selenium"],
            "protections": ["01"],
            "scenarios": ["static_html"],
            "repetitions": 3,
        }
    }
    body = client.post("/api/experiences/valider", json=corps).json()
    assert body["valide"] is True
    assert body["total"] == 6  # 2 moteurs × 1 protection × 1 scénario × 3 répétitions


def test_valider_refuse_moteur_inconnu(client):
    corps = {"experiment": {"name": "x", "engines": ["inexistant"], "scenarios": ["static_html"], "repetitions": 1}}
    body = client.post("/api/experiences/valider", json=corps).json()
    assert body["valide"] is False
    assert "inexistant" in body["erreur"]


def test_progression_lit_le_vrai_etat(client, reglages):
    cx = db.ouvrir(reglages.base_donnees)
    exp_id = campaigns.creer(cx, _mini_experience(), reglages)
    eng = db.engine_id(cx, "httpx", "1", "client", {})
    scn = db.scenario_id(cx, "static_html", "")
    _insérer_passage(cx, exp_id, eng, scn, repetition=1, statut="reussi", jeton="a" * 32, issue="succes", duree=120.0)
    _insérer_passage(cx, exp_id, eng, scn, repetition=2, statut="erreur", jeton="b" * 32, issue="erreur_technique")
    cx.commit()
    cx.close()
    data = client.get(f"/api/experiences/{exp_id}/progression").json()
    assert data["total"] == 2  # 1 × 1 × 1 × 2
    assert data["faits"] == 2
    assert data["par_statut"]["reussi"] == 1
    assert data["par_issue"]["erreur_technique"] == 1
    assert data["pourcentage"] == 100.0


def test_progression_404_si_absente(client):
    assert client.get("/api/experiences/9999/progression").status_code == 404


def test_flux_sse_experience_terminee(client, reglages):
    cx = db.ouvrir(reglages.base_donnees)
    exp_id = campaigns.creer(cx, _mini_experience(), reglages)
    cx.execute("UPDATE experiments SET status = 'termine' WHERE id = ?", (exp_id,))
    cx.commit()
    cx.close()
    r = client.get(f"/api/experiences/{exp_id}/flux")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    assert "data:" in r.text  # au moins un événement de progression


def test_artefact_sert_le_png_et_refuse_hors_sorties(client, reglages, tmp_path):
    cx = db.ouvrir(reglages.base_donnees)
    exp_id = campaigns.creer(cx, _mini_experience(), reglages)
    eng = db.engine_id(cx, "httpx", "1", "client", {})
    scn = db.scenario_id(cx, "static_html", "")
    _insérer_passage(cx, exp_id, eng, scn, repetition=1, statut="echec", jeton="c" * 32)
    run_id = cx.execute("SELECT id FROM runs WHERE experiment_id = ?", (exp_id,)).fetchone()[0]

    dossier = reglages.sorties / "artefacts" / str(exp_id)
    dossier.mkdir(parents=True, exist_ok=True)
    bon = dossier / f"run-{run_id}.png"
    bon.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 16)
    cx.execute(
        "INSERT INTO artifacts (run_id, artifact_type, file_path, created_at) VALUES (?, 'screenshot', ?, ?)",
        (run_id, str(bon), db.maintenant()),
    )
    # un artefact pointant hors du dossier des sorties doit être refusé (anti-traversée)
    exterieur = tmp_path / "secret.png"
    exterieur.write_bytes(b"x")
    cx.execute(
        "INSERT INTO artifacts (run_id, artifact_type, file_path, created_at) VALUES (?, 'screenshot', ?, ?)",
        (run_id, str(exterieur), db.maintenant()),
    )
    cx.commit()
    ids = [r[0] for r in cx.execute("SELECT id FROM artifacts ORDER BY id")]
    cx.close()

    ok = client.get(f"/api/artefacts/{ids[0]}")
    assert ok.status_code == 200
    assert ok.headers["content-type"] == "image/png"
    assert client.get(f"/api/artefacts/{ids[1]}").status_code == 404
