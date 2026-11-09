import json

import pytest

from shadowlab import database as db
from shadowlab.site import pages

JETON = "0123456789abcdef0123456789abcdef"


def test_pages_et_resultats_attendus(client):
    r = client.get(f"/lab/statique?sl={JETON}")
    assert r.status_code == 200
    for ref in pages.REFERENCES_STATIQUES:
        assert ref in r.text
    assert "default-src 'self'" in r.headers["content-security-policy"]
    assert client.get("/lab/catalogue?page=6").status_code == 404
    assert client.get("/lab/api/articles?limite=25").json()["total"] == 25


def test_observations_enregistrees_dans_l_ordre(client, reglages):
    client.get(f"/lab/statique?sl={JETON}", headers={"X-Premier": "1", "Accept-Language": "fr"})
    cx = db.ouvrir(reglages.base_donnees)
    http, _ = db.observations(cx, JETON)
    noms = [n for n, _ in http[0]["headers"]]
    assert "x-premier" in noms and "accept-language" in noms
    assert http[0]["path"] == "/lab/statique"


def test_collecte_et_verdict(client):
    client.get(f"/lab/empreinte?sl={JETON}")
    payload = {
        "navigateur": {"userAgent": "x", "webdriver": True, "languages": ["fr"]},
        "botd": {"bot": True, "botKind": "selenium"},
    }
    r = client.post(
        f"/lab/collecte?sl={JETON}", content=json.dumps({"kind": "empreinte", "page": "/", "payload": payload})
    )
    assert r.status_code == 204
    verdicts = {v["detector_name"]: v["classification"] for v in client.get(f"/lab/verdict?sl={JETON}").json()}
    assert verdicts["botd"] == "automatise"
    assert verdicts["regles-js"] == "automatise"


def test_collecte_refuse_les_messages_invalides(client):
    assert client.post("/lab/collecte", content="{}").status_code == 400
    assert client.post(f"/lab/collecte?sl={JETON}", content="pas du json").status_code == 400
    trop = json.dumps({"kind": "empreinte", "payload": "x" * 70_000})
    assert client.post(f"/lab/collecte?sl={JETON}", content=trop).status_code == 400
    assert (
        client.post(f"/lab/collecte?sl={JETON}", content=json.dumps({"kind": "autre", "payload": 1})).status_code == 400
    )


def test_formulaire(client):
    r = client.post(
        "/lab/formulaire",
        content="nom=Alice&modele=Rally4",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert "Merci Alice — modèle Rally4" in r.text
    assert client.post("/lab/formulaire", content="nom=&modele=Rally4").status_code == 422


def test_honeypot_lien_piege(client, reglages):
    r = client.get(f"/lab/piege?sl={JETON}")
    assert r.status_code == 204
    cx = db.ouvrir(reglages.base_donnees)
    dec = cx.execute(
        "SELECT decision, motifs FROM decisions WHERE session_token = ? AND couche = 'honeypot'", (JETON,)
    ).fetchone()
    assert dec is not None
    assert dec["decision"] == "declenche"
    assert "lien" in dec["motifs"]


def test_honeypot_champ_piege(client, reglages):
    r = client.post(
        f"/lab/formulaire?sl={JETON}",
        content="nom=Bot&modele=Rally2&sl_telephone=0612345678",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 200
    cx = db.ouvrir(reglages.base_donnees)
    dec = cx.execute(
        "SELECT decision, motifs FROM decisions WHERE session_token = ? AND couche = 'honeypot'", (JETON,)
    ).fetchone()
    assert dec is not None
    assert "champ" in dec["motifs"]


def test_honeypot_absent_sans_arena(client):
    r = client.get("/lab/formulaire")
    assert "sl_telephone" not in r.text
    assert "/lab/piege" not in r.text


def test_session_manuelle_de_bout_en_bout(client, reglages):
    r = client.post("/manuel/commencer", data={"consentement": "oui"}, follow_redirects=False)
    assert r.status_code == 303
    jeton = r.headers["location"].split("sl=")[1]
    client.get(r.headers["location"])
    r = client.get("/manuel/terminer")
    assert r.status_code == 200 and "Session enregistrée" in r.text
    cx = db.ouvrir(reglages.base_donnees)
    run = cx.execute("SELECT truth, status, consent_at FROM runs WHERE session_token = ?", (jeton,)).fetchone()
    assert (run["truth"], run["status"]) == ("humain", "reussi")
    assert run["consent_at"] is not None


def test_session_manuelle_refuse_sans_consentement(client):
    r = client.post("/manuel/commencer", follow_redirects=False)
    assert r.status_code == 422


def test_api_ecriture_exige_l_entete_anti_csrf(client):
    assert client.post("/api/arret").status_code == 403
    assert client.get("/api/sante").json() == {"statut": "ok"}


def test_hote_inconnu_refuse_en_local(client, reglages):
    """DNS rebinding : une page tierce qui pointerait vers 127.0.0.1 envoie son propre nom dans Host."""
    for chemin in ("/api/sante", "/lab/", "/tableau"):
        assert client.get(chemin, headers={"host": "attaquant.example"}).status_code == 400
    assert client.get("/api/sante", headers={"host": f"localhost:{reglages.port}"}).status_code == 200


def test_verrou_libere_si_la_creation_echoue(client, monkeypatch):
    from shadowlab import api, campaigns

    def echec(*_):
        raise RuntimeError("base indisponible")

    monkeypatch.setattr(campaigns, "creer", echec)
    yaml_valide = "experiment: {name: essai, engines: [httpx], scenarios: [static_html], repetitions: 1}"
    with pytest.raises(RuntimeError):
        client.post("/api/experiences", content=yaml_valide, headers={"X-ShadowLab": "1"})
    assert not api._verrou_campagne.locked()


def test_api_decisions_et_protections(client, reglages):
    cx = db.ouvrir(reglages.base_donnees)
    cx.execute(
        "INSERT INTO experiments (name, created_at, configuration, status) VALUES (?, ?, '{}', 'termine')",
        ("test_arena", db.maintenant()),
    )
    eid = cx.execute("SELECT last_insert_rowid()").fetchone()[0]
    decisions = client.get(f"/api/experiences/{eid}/decisions").json()
    assert decisions == {"couches": {}}
    protections = client.get(f"/api/experiences/{eid}/protections").json()
    assert protections == {"protections": {}}


def test_cles_turnstile_sont_les_cles_officielles_de_test():
    """Les clés Turnstile doivent être celles documentées par Cloudflare pour le mode test."""
    from shadowlab.arena.defis import (
        TURNSTILE_SECRET_BLOCK,
        TURNSTILE_SECRET_PASS,
        TURNSTILE_SITE_BLOCK,
        TURNSTILE_SITE_PASS,
        TURNSTILE_VERIFY_URL,
    )

    assert TURNSTILE_SITE_PASS == "1x00000000000000000000AA"
    assert TURNSTILE_SECRET_PASS == "1x0000000000000000000000000000000AA"
    assert TURNSTILE_SITE_BLOCK == "2x00000000000000000000AB"
    assert TURNSTILE_SECRET_BLOCK == "2x0000000000000000000000000000000AB"
    assert TURNSTILE_VERIFY_URL == "https://challenges.cloudflare.com/turnstile/v0/siteverify"


def test_cles_recaptcha_sont_les_cles_officielles_de_test():
    """Les clés reCAPTCHA v2 doivent être celles documentées par Google pour le mode test."""
    from shadowlab.arena.defis import RECAPTCHA_SECRET_KEY, RECAPTCHA_SITE_KEY, RECAPTCHA_VERIFY_URL

    assert RECAPTCHA_SITE_KEY == "6LeIxAcTAAAAAJcZVRqyHh71UMIEGNQ_MXjiZKhI"
    assert RECAPTCHA_SECRET_KEY == "6LeIxAcTAAAAAGG-vFI1TnRWxMZNFuojJ4WifJWe"
    assert RECAPTCHA_VERIFY_URL == "https://www.google.com/recaptcha/api/siteverify"


def test_interface_exposee_exige_un_jeton(reglages, monkeypatch):
    from fastapi.testclient import TestClient

    from shadowlab.config import charger
    from shadowlab.site.app import creer_app

    monkeypatch.setenv("SHADOWLAB_HOTE", "0.0.0.0")
    monkeypatch.setenv("SHADOWLAB_JETON", "secret-de-test")
    with TestClient(creer_app(charger())) as c:
        assert c.get("/api/experiences").status_code == 401
        assert c.get("/tableau").status_code == 401
        ok = c.get("/api/experiences", headers={"Authorization": "Bearer secret-de-test"})
        assert ok.status_code == 200


def test_connexion_page_et_succes(client):
    r = client.get(f"/lab/connexion?sl={JETON}")
    assert r.status_code == 200 and "formulaire-connexion" in r.text
    # espace protégé : sans cookie d'auth, on est renvoyé vers la connexion
    r = client.get("/lab/espace", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/lab/connexion"
    # login correct (compte de test) → espace privé avec le bon compte
    r = client.post("/lab/connexion", data={"identifiant": "demo", "mot_de_passe": "arena-demo-2026"})
    assert r.status_code == 200 and 'id="espace-prive"' in r.text and 'data-compte="demo"' in r.text


def test_connexion_mauvais_identifiants(client):
    r = client.post(
        "/lab/connexion", data={"identifiant": "demo", "mot_de_passe": "faux"}, follow_redirects=False
    )
    assert r.status_code == 401
    assert client.get("/lab/espace", follow_redirects=False).status_code == 303


def test_connexion_honeypot_rempli_refuse(client):
    r = client.post(
        "/lab/connexion",
        data={"identifiant": "demo", "mot_de_passe": "arena-demo-2026", "sl_site": "http://x"},
        follow_redirects=False,
    )
    assert r.status_code == 403
