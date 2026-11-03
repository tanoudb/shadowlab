import json

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


def test_session_manuelle_de_bout_en_bout(client, reglages):
    r = client.post("/manuel/commencer", follow_redirects=False)
    assert r.status_code == 303
    jeton = r.headers["location"].split("sl=")[1]
    client.get(r.headers["location"])
    r = client.get("/manuel/terminer")
    assert r.status_code == 200 and "Session enregistrée" in r.text
    cx = db.ouvrir(reglages.base_donnees)
    run = cx.execute("SELECT truth, status FROM runs WHERE session_token = ?", (jeton,)).fetchone()
    assert (run["truth"], run["status"]) == ("humain", "reussi")


def test_api_ecriture_exige_l_entete_anti_csrf(client):
    assert client.post("/api/arret").status_code == 403
    assert client.get("/api/sante").json() == {"statut": "ok"}


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
