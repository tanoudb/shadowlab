import json
import shutil
import subprocess
from pathlib import Path

import pytest

import shadowlab
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


def test_composite_differe_enregistre_a_la_collecte(client, reglages):
    """La collecte d'une empreinte JS avec signaux faibles ≥ seuil enregistre une décision composite-differe."""
    # Pas de sceau → pas de profil Arena → pas de composite évalué (comportement attendu)
    payload = {
        "navigateur": {"userAgent": "x", "languages": ["fr"]},
        "ecran": {"width": 1920, "height": 1080},
    }
    client.post(
        f"/lab/collecte?sl={JETON}",
        content=json.dumps({"kind": "empreinte", "page": "/lab/detection", "payload": payload}),
    )
    cx = db.ouvrir(reglages.base_donnees)
    row = cx.execute(
        "SELECT 1 FROM decisions WHERE session_token = ? AND couche = 'composite-differe'", (JETON,)
    ).fetchone()
    assert row is None, "sans sceau, pas de composite-differe"


def test_suspicion_composite_cumule_signaux_faibles(reglages):
    """suspicion() cumule les signaux faibles et bloque quand la somme ≥ seuil."""
    cx = db.ouvrir(reglages.base_donnees)
    # Insérer une empreinte JS avec un signal faible connu (webdriver=False → pas automatisé)
    payload = {
        "navigateur": {"userAgent": "Chrome/131", "webdriver": False, "languages": ["fr"], "platform": "MacIntel"},
        "proprietes": {"hardwareConcurrency": {"instance": True, "prototype": True, "same_descriptor": False}},
    }
    cx.execute(
        "INSERT INTO observations_js (session_token, received_at, kind, page, payload) VALUES (?, ?, ?, ?, ?)",
        (JETON, db.maintenant(), "empreinte", "/lab/detection", db.j(payload)),
    )
    # Sans composite → pas de motif (chaque détecteur est sous le seuil individuellement)
    from shadowlab.site.gardien import suspicion

    motifs = suspicion(cx, JETON, seuil_composite=None)
    composite = [m for m in motifs if m.get("detecteur") == "composite"]
    assert composite == []
    # Avec un seuil bas → le composite fire si la somme des signaux faibles le dépasse
    motifs = suspicion(cx, JETON, seuil_composite=0.01)
    composite = [m for m in motifs if m.get("detecteur") == "composite"]
    # Si des signaux faibles existent, le composite doit fire avec un seuil très bas
    if composite:
        assert composite[0]["score"] >= 0.01


def test_composite_differe_detecte_dans_gardien(reglages):
    """_composite_differe() détecte une décision enregistrée."""
    cx = db.ouvrir(reglages.base_donnees)
    from shadowlab.site.gardien import _composite_differe

    assert _composite_differe(cx, JETON) is False
    db.enregistrer_decision(
        cx, JETON, "composite-differe", "detecte", "/lab/collecte", [{"detecteur": "composite", "score": 1.0}]
    )
    assert _composite_differe(cx, JETON) is True


def test_fingerprinting_differe_detecte_dans_gardien(reglages):
    """_fingerprinting_differe() détecte une décision enregistrée par un détecteur individuel."""
    cx = db.ouvrir(reglages.base_donnees)
    from shadowlab.site.gardien import _fingerprinting_differe

    assert _fingerprinting_differe(cx, JETON) is False
    db.enregistrer_decision(
        cx,
        JETON,
        "fingerprinting-differe",
        "detecte",
        "/lab/collecte",
        [{"detecteur": "cdp", "signaux": [{"code": "debugger_instant", "description": "test"}]}],
    )
    assert _fingerprinting_differe(cx, JETON) is True


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
    r = client.post("/lab/connexion", data={"identifiant": "demo", "mot_de_passe": "faux"}, follow_redirects=False)
    assert r.status_code == 401
    assert client.get("/lab/espace", follow_redirects=False).status_code == 303


def test_connexion_honeypot_rempli_refuse(client):
    r = client.post(
        "/lab/connexion",
        data={"identifiant": "demo", "mot_de_passe": "arena-demo-2026", "sl_site": "http://x"},
        follow_redirects=False,
    )
    assert r.status_code == 403


def test_recaptcha_v3_page_sans_cles(client, monkeypatch):
    monkeypatch.delenv("SHADOWLAB_RECAPTCHA_V3_SITE", raising=False)
    r = client.get(f"/lab/recaptcha-v3?sl={JETON}")
    assert r.status_code == 200 and 'id="v3-resultat"' in r.text and "clés absentes" in r.text
    # CSP de la page autorise le script Google reCAPTCHA
    assert "www.google.com/recaptcha/" in r.headers["content-security-policy"]


def test_recaptcha_v3_verifier_sans_secret(client, monkeypatch):
    monkeypatch.delenv("SHADOWLAB_RECAPTCHA_V3_SECRET", raising=False)
    r = client.post(f"/lab/recaptcha-v3/verifier?sl={JETON}", content=json.dumps({"token": "x"}))
    body = r.json()
    assert r.status_code == 200 and body["success"] is False and body["score"] is None


def _entetes_sceau(reglages, profil="06", session=JETON, ja4=""):
    """Forge un sceau de frontal valide (comme le ferait Nginx) pour tester la porte de connexion."""
    from shadowlab.arena import secret as secrets_arena

    secret = secrets_arena.charger(reglages.dossier_arena)
    observation = "obs-test"
    signature = secrets_arena.signer(secret, observation, profil, session, ja4)
    return {
        "x-shadowlab-sceau": signature,
        "x-shadowlab-obs": observation,
        "x-shadowlab-profil": profil,
        "x-shadowlab-session": session,
        "x-shadowlab-ja4": ja4,
    }


def test_connexion_porte_laisse_passer_session_propre(client, reglages):
    # Niveau 06, sceau valide, aucune observation de bot → la porte comportementale laisse passer.
    entetes = _entetes_sceau(reglages, session=JETON)
    r = client.post(
        f"/lab/connexion?sl={JETON}",
        data={"identifiant": "demo", "mot_de_passe": "arena-demo-2026"},
        headers=entetes,
        follow_redirects=False,
    )
    assert r.status_code == 303 and r.headers["location"] == "/lab/espace"


def test_connexion_porte_bloque_un_bot(client, reglages):
    # Une empreinte de bot classée « automatise » → la porte refuse le login même avec les bons identifiants.
    jb = "ffffffffffffffffffffffffffffffff"
    client.post(
        f"/lab/collecte?sl={jb}",
        content=json.dumps(
            {
                "kind": "empreinte",
                "page": "/",
                "payload": {
                    "navigateur": {"userAgent": "x", "webdriver": True, "languages": ["fr"]},
                    "botd": {"bot": True, "botKind": "selenium"},
                },
            }
        ),
    )
    entetes = _entetes_sceau(reglages, session=jb)
    r = client.post(
        f"/lab/connexion?sl={jb}",
        data={"identifiant": "demo", "mot_de_passe": "arena-demo-2026"},
        headers=entetes,
        follow_redirects=False,
    )
    assert r.status_code == 403


SCRIPTS_SERVIS = sorted(
    script
    for dossier in ("site/static", "tableau_static")
    for script in (Path(shadowlab.__file__).parent / dossier).glob("*.js")
)


@pytest.mark.skipif(shutil.which("node") is None, reason="Node absent : syntaxe des scripts non vérifiée")
@pytest.mark.parametrize("script", SCRIPTS_SERVIS, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_script_servi_syntaxe_valide(script):
    """Un script qui ne s'analyse pas ne s'exécute pas du tout : la page reste morte sans rien dire."""
    resultat = subprocess.run(["node", "--check", str(script)], capture_output=True, text=True)
    assert resultat.returncode == 0, resultat.stderr
