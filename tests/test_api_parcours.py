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


def test_passage_detail_inclut_decisions_requetes_et_cache_le_jeton(client, reglages):
    cx = db.ouvrir(reglages.base_donnees)
    exp_id = campaigns.creer(cx, _mini_experience(), reglages)
    eng = db.engine_id(cx, "httpx", "1", "client", {})
    scn = db.scenario_id(cx, "static_html", "")
    jeton = "d" * 32
    _insérer_passage(cx, exp_id, eng, scn, repetition=1, statut="echec", jeton=jeton, issue="bloque_waf")
    run_id = cx.execute("SELECT id FROM runs WHERE session_token = ?", (jeton,)).fetchone()[0]
    motifs = db.j([{"code": "sqli", "description": "motif WAF"}])
    cx.execute(
        "INSERT INTO decisions (session_token, created_at, couche, decision, chemin, motifs) VALUES (?, ?, ?, ?, ?, ?)",
        (jeton, db.maintenant(), "waf", "bloque", "/lab/statique", motifs),
    )
    cx.execute(
        "INSERT INTO observations_http (session_token, received_at, method, path, http_version, headers, cookies,"
        " status, source) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (jeton, db.maintenant(), "GET", "/lab/statique", "HTTP/2", db.j([["user-agent", "x"]]), db.j([]), 403, "site"),
    )
    cx.commit()
    cx.close()

    d = client.get(f"/api/passages/{run_id}").json()
    assert d["passage"]["issue"] == "bloque_waf"
    assert "session_token" not in d["passage"]  # le jeton de session ne fuite jamais
    assert d["decisions_couches"][0] == {
        "couche": "waf",
        "decision": "bloque",
        "chemin": "/lab/statique",
        "motifs": [{"code": "sqli", "description": "motif WAF"}],
    }
    assert d["requetes"][0]["status"] == 403
    assert d["requetes"][0]["nb_entetes"] == 1


def test_matrice_separe_reussis_echecs_erreurs(client, reglages):
    cx = db.ouvrir(reglages.base_donnees)
    exp = campaigns.Experience.model_validate(
        {
            "name": "cmp",
            "engines": ["httpx", "selenium"],
            "protections": ["01"],
            "scenarios": ["static_html"],
            "repetitions": 3,
            "seed": 1,
        }
    )
    exp_id = campaigns.creer(cx, exp, reglages)
    scn = db.scenario_id(cx, "static_html", "")
    httpx = db.engine_id(cx, "httpx", "1", "client", {})
    selenium = db.engine_id(cx, "selenium", "1", "navigateur", {})
    # httpx : 2 réussis, 1 échec ; durée moyenne = (100+200+300)/3 = 200
    _insérer_passage(cx, exp_id, httpx, scn, repetition=1, statut="reussi", jeton="h" + "1" * 31, duree=100.0)
    _insérer_passage(cx, exp_id, httpx, scn, repetition=2, statut="reussi", jeton="h" + "2" * 31, duree=200.0)
    _insérer_passage(cx, exp_id, httpx, scn, repetition=3, statut="echec", jeton="h" + "3" * 31, duree=300.0)
    # selenium : 1 réussi, 1 échec, 1 erreur (exclue de la durée) ; durée = (100+200)/2 = 150
    _insérer_passage(cx, exp_id, selenium, scn, repetition=1, statut="reussi", jeton="s" + "1" * 31, duree=100.0)
    _insérer_passage(cx, exp_id, selenium, scn, repetition=2, statut="echec", jeton="s" + "2" * 31, duree=200.0)
    _insérer_passage(cx, exp_id, selenium, scn, repetition=3, statut="erreur", jeton="s" + "3" * 31, duree=999.0)
    cx.commit()
    cx.close()

    m = client.get(f"/api/experiences/{exp_id}/matrice").json()
    assert m["moteurs"] == ["httpx", "selenium"]
    assert m["cellules"]["01"]["httpx"] == {
        "total": 3,
        "reussis": 2,
        "echecs": 1,
        "erreurs": 0,
        "duree_moy": 200.0,
    }
    sel = m["cellules"]["01"]["selenium"]
    assert (sel["reussis"], sel["echecs"], sel["erreurs"]) == (1, 1, 1)
    assert sel["duree_moy"] == 150.0  # l'erreur (999 ms) est exclue
