"""Application publique réduite (étape 1.6) : vitrine, sessions humaines consenties, collecte. Rien d'autre.

Chaque test est rattaché à une règle de `docs/site-public.md` (R1 à R10) ou à une condition du § 5 du plan.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import sqlite3
import subprocess
import sys
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from html import escape
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from parsel import Selector

from shadowlab import config
from shadowlab import database as db
from shadowlab.config import ReglagesPublics, charger_public
from shadowlab.public import Limites, creer_app_publique, purger
from shadowlab.public import messages as boite
from shadowlab.public.donnees import ENTETES_GARDES
from shadowlab.public.pages import DONNEES_COMPORTEMENT, DONNEES_RELEVEES

HOTE = "vitrine.test"  # domaine réservé aux essais (RFC 2606)
ORIGINE = f"https://{HOTE}"
CONTACT = "Responsable de test — contact@exemple.test"
IP = "203.0.113.57"  # plage réservée à la documentation (RFC 5737)
AUTRE_IP = "198.51.100.23"
OBSERVATEUR = Path(__file__).parents[1] / "src" / "shadowlab" / "site" / "static" / "observateur.js"


@pytest.fixture
def reglages_publics(tmp_path) -> ReglagesPublics:
    return ReglagesPublics(
        hotes=(HOTE,),
        contact=CONTACT,
        conservation_jours=90,
        https=True,
        port=8771,
        base_donnees=tmp_path / "public" / "public.sqlite3",
        entete_ip="X-Forwarded-For",
        vitrine_graine=20261111,
        vitrine_taille=45,
    )


def fabriquer(reglages: ReglagesPublics, **limites) -> TestClient:
    return TestClient(creer_app_publique(reglages, replace(Limites(), **limites)), base_url=ORIGINE)


@pytest.fixture
def client(reglages_publics):
    with fabriquer(reglages_publics) as c:
        yield c


def jeton_csrf(client: TestClient) -> str:
    r = client.get("/")
    assert r.status_code == 200
    jeton = Selector(r.text).css('input[name="csrf"]::attr(value)').get()
    assert jeton
    return jeton


def commencer(client: TestClient, adresse: str = IP) -> str:
    """Ouvre une session consentie et renvoie son jeton, lu dans une page vitrine."""
    r = client.post(
        "/session/commencer",
        data={"consentement": "oui", "csrf": jeton_csrf(client)},
        headers={"Origin": ORIGINE, "X-Forwarded-For": adresse},
        follow_redirects=False,
    )
    assert r.status_code == 303, r.text
    assert r.headers["location"] == "/lab/vitrine"
    jeton = Selector(client.get("/lab/vitrine").text).css('meta[name="sl-session"]::attr(content)').get()
    assert jeton and re.fullmatch(r"[0-9a-f]{32}", jeton)
    return jeton


def collecter(client: TestClient, jeton: str, kind: str = "empreinte", payload=None, headers=None):
    corps = {"kind": kind, "page": "/lab/vitrine", "payload": {"navigateur": {"userAgent": "essai"}}}
    if payload is not None:
        corps["payload"] = payload
    entetes = {"Content-Type": "application/json", **(headers or {})}
    return client.post(f"/lab/collecte?sl={jeton}", content=json.dumps(corps), headers=entetes)


def champs_du_formulaire(html: str, action: str) -> dict[str, str]:
    formulaire = Selector(html).css(f'form[action="{action}"][method="post"]')
    assert formulaire, f"aucun formulaire vers {action}"
    return {e.attrib["name"]: e.attrib.get("value", "") for e in formulaire.css("input[name]")}


def terminer(client: TestClient):
    """« Terminer ma session » : le bouton du bandeau des pages vitrine."""
    champs = champs_du_formulaire(client.get("/lab/vitrine").text, "/session/terminer")
    return client.post("/session/terminer", data=champs, headers={"Origin": ORIGINE})


def ouvrir(reglages: ReglagesPublics):
    return db.ouvrir(reglages.base_donnees)


def contenu_de_la_base(reglages: ReglagesPublics) -> str:
    """Tout le contenu de la base, table par table, en texte."""
    cx = ouvrir(reglages)
    try:
        tables = [r[0] for r in cx.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
        return "\n".join(str(tuple(ligne)) for t in tables for ligne in cx.execute(f"SELECT * FROM {t}"))
    finally:
        cx.close()


def cookie_pose(reponse, nom: str) -> str:
    poses = [c for c in reponse.headers.get_list("set-cookie") if nom in c.split("=", 1)[0]]
    assert len(poses) == 1, reponse.headers.get_list("set-cookie")
    return poses[0]


# --- Surface : rien du laboratoire n'est servi (§ 5.1) -----------------------------------------

ROUTES_INTERDITES = [
    "/api",
    "/api/experiences",
    "/api/docs",
    "/api/openapi.json",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/labo",
    "/labo/",
    "/tableau",
    "/tableau/",
    "/manuel",
    "/manuel/terminer",
    "/lab",
    "/lab/",
    "/lab/connexion",
    "/lab/espace",
    "/lab/recaptcha-v3",
    "/lab/verdict",
    "/lab/statique",
    "/lab/dynamique",
    "/lab/catalogue",
    "/lab/formulaire",
    "/lab/session",
    "/lab/empreinte",
    "/lab/detection",
    "/lab/adaptatif",
    "/lab/sante",
    "/lab/sortie",
    "/lab/piege",
    "/lab/api/articles",
    "/lab/captcha/image",
    "/lab/static/lab.css",
    "/lab/static/defi.js",
    "/lab/static/verdict.js",
    "/lab/static/empreinte.js",
    "/lab/static/dynamique.js",
    "/lab/static/vendor/fingerprintjs-5.3.0.esm.js",
    "/lab/static/vendor/botd-LICENSE.txt",
    "/lab/static/%2e%2e/app.py",
]


@pytest.mark.parametrize("chemin", ROUTES_INTERDITES)
def test_routes_du_labo_absentes(client, chemin):
    assert client.get(chemin).status_code == 404


@pytest.mark.parametrize(
    "chemin",
    ["/api/experiences", "/manuel/commencer", "/lab/defi/verifier", "/lab/connexion", "/lab/recaptcha-v3/verifier"],
)
def test_routes_du_labo_absentes_en_post(client, chemin):
    assert client.post(chemin, json={}).status_code == 404


def test_aucun_module_du_labo_n_est_charge():
    """Ni API, ni interface, ni gardien, ni frontal, ni moteurs, ni détecteurs : ils ne sont même pas importés."""
    code = "import sys, shadowlab.public; print(' '.join(sorted(m for m in sys.modules if m.startswith('shadowlab'))))"
    charges = set(
        subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout.split()
    )
    assert "shadowlab.public" in charges
    interdits = {
        "shadowlab.api",
        "shadowlab.labo",
        "shadowlab.tableau",
        "shadowlab.site.app",
        "shadowlab.site.gardien",
        "shadowlab.arena.frontal",
        "shadowlab.arena.defis",
        "shadowlab.arena.profils",
        "shadowlab.campaigns",
        "shadowlab.scenarios",
        "shadowlab.detection",
        "shadowlab.correlation",
        "shadowlab.passages",
    }
    assert not interdits & charges
    assert not any(m.startswith("shadowlab.engines") for m in charges)


# --- R1 : consentement avant toute collecte ----------------------------------------------------

PAGES_VITRINE = [
    "/lab/vitrine",
    "/lab/vitrine/annonces",
    "/lab/vitrine/annonces?page=2",
    "/lab/vitrine/annonces/AN-000001",
]


@pytest.mark.parametrize("chemin", PAGES_VITRINE)
def test_sans_consentement_ni_observateur_ni_jeton(client, chemin):
    r = client.get(chemin)
    assert r.status_code == 200
    assert "observateur.js" not in r.text
    assert 'name="sl-session"' not in r.text
    assert Selector(r.text).css('a[href="/"]'), "un visiteur doit pouvoir rejoindre la page d'information"


def test_visite_sans_participer_ne_laisse_aucune_trace(client, reglages_publics):
    for chemin in PAGES_VITRINE + ["/lab/vitrine/photos/AN-000001/1.svg", "/lab/static/vitrine.css"]:
        assert client.get(chemin).status_code == 200
    assert client.get("/lab/vitrine/api/annonces/AN-000001/similaires").json()["annonces"]
    cx = ouvrir(reglages_publics)
    for table in ("runs", "observations_http", "observations_js"):
        assert cx.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0, table


def test_consentement_exige(client, reglages_publics):
    csrf = jeton_csrf(client)
    for champs in ({"csrf": csrf}, {"csrf": csrf, "consentement": "non"}):
        r = client.post("/session/commencer", data=champs, headers={"Origin": ORIGINE}, follow_redirects=False)
        assert r.status_code == 422
        assert "slp-session" not in " ".join(r.headers.get_list("set-cookie"))
    assert ouvrir(reglages_publics).execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0


def test_parcours_complet(client, reglages_publics):
    r = client.post(
        "/session/commencer",
        data={"consentement": "oui", "csrf": jeton_csrf(client)},
        headers={"Origin": ORIGINE},
        follow_redirects=False,
    )
    assert r.status_code == 303 and r.headers["location"] == "/lab/vitrine"
    cookie = cookie_pose(r, "slp-session").lower()
    assert cookie.startswith("__host-slp-session=")
    for attribut in ("httponly", "samesite=lax", "secure", "path=/"):
        assert attribut in cookie, attribut

    jeton = Selector(client.get("/lab/vitrine").text).css('meta[name="sl-session"]::attr(content)').get()
    cx = ouvrir(reglages_publics)
    passage = cx.execute("SELECT * FROM runs WHERE session_token = ?", (jeton,)).fetchone()
    assert passage["truth"] == "humain" and passage["status"] == "en_cours" and passage["consent_at"]

    for chemin in PAGES_VITRINE:
        sel = Selector(client.get(chemin).text)
        assert sel.css('script[src="/lab/static/observateur.js"]'), chemin
        assert sel.css('meta[name="sl-session"]::attr(content)').get() == jeton
        assert sel.css('meta[name="sl-sans-tiers"]::attr(content)').get() == "1"
        assert sel.css('form[action="/session/terminer"][method="post"] button'), "le bandeau garde un bouton"
        assert sel.css('a[href="/session"]'), "le bandeau mène à « Ma session »"
    assert client.get("/lab/static/observateur.js").status_code == 200
    assert client.get("/lab/static/vendor/botd-2.0.0.esm.js").status_code == 200

    assert collecter(client, jeton).status_code == 204
    assert collecter(client, jeton, "comportement", {"evenements": {"click": 2}}).status_code == 204
    lignes = cx.execute("SELECT kind, payload FROM observations_js WHERE session_token = ?", (jeton,)).fetchall()
    assert [ligne["kind"] for ligne in lignes] == ["empreinte", "comportement"]
    assert json.loads(lignes[0]["payload"]) == {"navigateur": {"userAgent": "essai"}}
    assert cx.execute("SELECT COUNT(*) FROM observations_http WHERE session_token = ?", (jeton,)).fetchone()[0] > 0

    r = terminer(client)
    assert r.status_code == 200
    efface = cookie_pose(r, "slp-session").lower()
    assert "max-age=0" in efface or "expires=thu, 01 jan 1970" in efface
    sel = Selector(r.text)
    assert sel.css('form[action="/session/supprimer"][method="post"] button')
    passage = cx.execute("SELECT status, completed_at FROM runs WHERE session_token = ?", (jeton,)).fetchone()
    assert passage["status"] != "en_cours" and passage["completed_at"]
    assert "observateur.js" not in client.get("/lab/vitrine").text


def test_double_clic_ne_cree_pas_deux_sessions(client, reglages_publics):
    champs = {"consentement": "oui", "csrf": jeton_csrf(client)}
    for _ in range(2):  # le même formulaire envoyé deux fois
        r = client.post("/session/commencer", data=champs, headers={"Origin": ORIGINE}, follow_redirects=False)
        assert r.status_code == 303
    assert ouvrir(reglages_publics).execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 1
    assert "Une session est déjà en cours" in client.get("/").text


# --- R2 : collecte fermée -----------------------------------------------------------------------


def test_collecte_refusee_sans_session(client, reglages_publics):
    for jeton in ("a" * 32, ""):
        assert collecter(client, jeton).status_code == 403
    assert ouvrir(reglages_publics).execute("SELECT COUNT(*) FROM observations_js").fetchone()[0] == 0


def test_collecte_refusee_jeton_inconnu_ou_cookie_forge(client, reglages_publics):
    jeton = commencer(client)
    assert collecter(client, "b" * 32).status_code == 403  # jeton de l'URL ≠ session du cookie
    nom = next(c.name for c in client.cookies.jar if c.name.endswith("slp-session"))
    client.cookies.set(nom, f"{jeton}.{'0' * 64}", domain=HOTE, path="/")  # signature fausse
    assert collecter(client, jeton).status_code == 403
    client.cookies.set(nom, jeton, domain=HOTE, path="/")  # cookie sans signature
    assert collecter(client, jeton).status_code == 403
    assert ouvrir(reglages_publics).execute("SELECT COUNT(*) FROM observations_js").fetchone()[0] == 0


def test_collecte_refusee_apres_terminer_meme_avec_l_ancien_cookie(client, reglages_publics):
    jeton = commencer(client)
    cookie = next(c for c in client.cookies.jar if c.name.endswith("slp-session"))
    assert terminer(client).status_code == 200
    client.cookies.set(cookie.name, cookie.value, domain=HOTE, path="/")
    assert collecter(client, jeton).status_code == 403
    assert ouvrir(reglages_publics).execute("SELECT COUNT(*) FROM observations_js").fetchone()[0] == 0


def test_collecte_refusee_apres_la_duree_maximale(client, reglages_publics):
    jeton = commencer(client)
    cx = ouvrir(reglages_publics)
    vieux = (datetime.now(UTC) - timedelta(hours=3)).isoformat(timespec="milliseconds")
    cx.execute("UPDATE runs SET started_at = ? WHERE session_token = ?", (vieux, jeton))
    assert collecter(client, jeton).status_code == 403
    assert "observateur.js" not in client.get("/lab/vitrine").text


def test_quota_d_envois_par_session(reglages_publics):
    with fabriquer(reglages_publics, envois_par_session=3) as c:
        jeton = commencer(c)
        assert [collecter(c, jeton).status_code for _ in range(4)] == [204, 204, 204, 429]


def test_quota_de_volume_par_session(reglages_publics):
    with fabriquer(reglages_publics, volume_par_session=2000) as c:
        jeton = commencer(c)
        charge = {"x": "a" * 900}
        assert [collecter(c, jeton, payload=charge).status_code for _ in range(3)] == [204, 204, 429]


def test_corps_trop_gros(client, reglages_publics):
    jeton = commencer(client)
    assert collecter(client, jeton, payload={"x": "a" * 70_000}).status_code == 413
    # Sans Content-Length (envoi par morceaux), la limite tient aussi.
    morceaux = iter([b'{"kind": "empreinte", "page": "/", "payload": {"x": "', b"a" * 70_000, b'"}}'])
    assert client.post(f"/lab/collecte?sl={jeton}", content=morceaux).status_code == 413
    assert ouvrir(reglages_publics).execute("SELECT COUNT(*) FROM observations_js").fetchone()[0] == 0


def test_messages_invalides(client):
    jeton = commencer(client)
    assert collecter(client, jeton, payload=[1, 2]).status_code == 400  # charge qui n'est pas un objet
    assert collecter(client, jeton, kind="autre").status_code == 400
    assert client.post(f"/lab/collecte?sl={jeton}", content=b"pas du json").status_code == 400
    assert client.post(f"/lab/collecte?sl={jeton}", content=b"[1]").status_code == 400


# --- R3 : aucune requête vers un tiers -----------------------------------------------------------


def pages_servies(client: TestClient) -> list[str]:
    pages = [client.get("/").text]
    jeton = commencer(client)
    pages += [client.get(chemin).text for chemin in PAGES_VITRINE]
    pages.append(client.get("/lab/static/vitrine.css").text)
    pages.append(client.get("/lab/static/vitrine.js").text)
    pages.append(client.get("/session").text)
    pages += [client.get("/contact").text, client.get("/contact/envoye").text]
    merci = terminer(client)
    pages.append(merci.text)
    champs = champs_du_formulaire(merci.text, "/session/supprimer")
    pages.append(client.post("/session/supprimer", data=champs, headers={"Origin": ORIGINE}).text)
    assert jeton
    return pages


def test_aucune_adresse_externe_dans_les_pages(client):
    for page in pages_servies(client):
        assert not re.search(r"(?:https?:)?//[a-z0-9]", page, re.I), page[:200]
    csp = client.get("/").headers["content-security-policy"]
    assert "http" not in csp and "*" not in csp


@pytest.mark.skipif(shutil.which("node") is None, reason="node absent")
@pytest.mark.parametrize("balise", [True, False])
def test_sonde_webrtc_sautee_quand_la_page_le_demande(balise):
    """Avec `<meta name="sl-sans-tiers" content="1">`, aucun serveur STUN n'est contacté ; sans elle, rien ne change."""
    source = OBSERVATEUR.read_text(encoding="utf-8")
    fonction = re.search(r"^async function webrtcTest\(\) \{.*?^\}$", source, re.S | re.M).group(0)
    script = f"""
const META = {json.dumps("1" if balise else None)};
const BALISE = 'meta[name="sl-sans-tiers"]';
globalThis.document = {{ querySelector: (s) => (s === BALISE && META ? {{ content: META }} : null) }};
let configuration = null;
globalThis.RTCPeerConnection = class {{
  constructor(c) {{ configuration = c; }}
  createDataChannel() {{}}
  createOffer() {{ return Promise.resolve({{}}); }}
  setLocalDescription() {{ setTimeout(() => this.onicecandidate({{ candidate: null }}), 0); return Promise.resolve(); }}
  get localDescription() {{ return {{ sdp: '' }}; }}
  close() {{}}
}};
{fonction}
webrtcTest().then((r) => console.log(JSON.stringify({{ r, configuration }})));
"""
    sortie = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True, timeout=30).stdout
    resultat = json.loads(sortie)
    if balise:
        assert resultat["configuration"] is None
        assert resultat["r"].get("saute") == "sans-tiers"
    else:
        assert "stun.l.google.com" in json.dumps(resultat["configuration"])
        assert resultat["r"]["disponible"] is True


# --- R4 : moins de données personnelles ----------------------------------------------------------

ENTETES_IP = {
    "X-Forwarded-For": IP,
    "CF-Connecting-IP": IP,
    "X-Real-IP": IP,
    "Forwarded": f"for={IP};proto=https",
    "True-Client-IP": IP,
    "X-Client-IP": IP,
}


def test_entetes_porteurs_d_ip_et_cookies_non_stockes(client, reglages_publics):
    jeton = commencer(client)
    client.cookies.set("pistage", "valeur-de-cookie-privee", domain=HOTE, path="/")
    entetes = {**ENTETES_IP, "Accept-Language": "fr-FR,fr;q=0.9", "Referer": "https://ailleurs.example/x?y=1"}
    assert client.get("/lab/vitrine/annonces", headers=entetes).status_code == 200
    assert collecter(client, jeton, headers=entetes).status_code == 204
    cx = ouvrir(reglages_publics)
    lignes = cx.execute("SELECT headers, cookies FROM observations_http WHERE session_token = ?", (jeton,)).fetchall()
    assert lignes
    interdits = {nom.lower() for nom in ENTETES_IP} | {"cookie"}
    for ligne in lignes:
        noms = {nom.lower() for nom, _ in json.loads(ligne["headers"])}
        assert not noms & interdits, noms & interdits
        assert json.loads(ligne["cookies"]) == []
    gardes = [dict((n.lower(), v) for n, v in json.loads(ligne["headers"])) for ligne in lignes]
    assert any(e.get("accept-language") == "fr-FR,fr;q=0.9" for e in gardes), "les en-têtes utiles restent"
    tout = contenu_de_la_base(reglages_publics)
    for secret in (IP, "valeur-de-cookie-privee", "ailleurs.example"):
        assert secret not in tout, secret


def test_pas_de_hash_de_correlation(client, reglages_publics):
    jeton = commencer(client)
    empreinte = {"navigateur": {"userAgent": "essai", "languages": ["fr"]}, "ecran": {"width": 1}, "canvas": "abcd"}
    assert collecter(client, jeton, payload=empreinte).status_code == 204
    assert ouvrir(reglages_publics).execute("SELECT COUNT(*) FROM empreintes_vues").fetchone()[0] == 0


def test_journaux_sans_jeton_ni_requete_ni_adresse(client):
    messages: list[str] = []

    class Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            messages.append(record.getMessage())

    journal = logging.getLogger("shadowlab.public")
    capture, niveau = Capture(level=logging.DEBUG), journal.level
    journal.addHandler(capture)
    journal.setLevel(logging.DEBUG)
    try:
        jeton = commencer(client)
        client.get(f"/lab/vitrine?sl={jeton}&q=valeur-privee", headers=ENTETES_IP)
        collecter(client, jeton, headers=ENTETES_IP)
        client.get(f"/n-existe-pas?sl={jeton}", headers=ENTETES_IP)
    finally:
        journal.removeHandler(capture)
        journal.setLevel(niveau)
    assert messages, "l'application journalise ses requêtes"
    texte = "\n".join(messages)
    for interdit in (jeton, "sl=", "valeur-privee", IP, "testclient"):
        assert interdit not in texte, interdit


# --- R5 : les humains ne sont jamais bloqués -------------------------------------------------------


def test_aucun_defi_ni_detection_en_direct(client, reglages_publics):
    jeton = commencer(client)
    robot = {"User-Agent": "python-httpx/0.28", "Accept": "*/*"}
    for chemin in PAGES_VITRINE:
        r = client.get(chemin, headers=robot)
        assert r.status_code == 200 and "data-arena" not in r.text
    assert collecter(client, jeton, payload={"navigateur": {"webdriver": True}}, headers=robot).status_code == 204
    cx = ouvrir(reglages_publics)
    for table in ("decisions", "detections", "fingerprints"):
        assert cx.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0, table


# --- R6 : base et hôtes séparés -----------------------------------------------------------------


HOTES_ETRANGERS = ["attaquant.example", "vitrine.test.attaquant.example", "localhost", "127.0.0.1"]
HOTES_ETRANGERS += ["x@vitrine.test", "", "vitrine.test:x"]


@pytest.mark.parametrize("hote", HOTES_ETRANGERS)
def test_hote_etranger_refuse(client, hote):
    for chemin in ("/", "/lab/vitrine"):
        assert client.get(chemin, headers={"Host": hote}).status_code == 400


def test_hotes_et_base_independants_du_labo(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "_charger_env", lambda *a, **k: None)
    for variable in [v for v in list(__import__("os").environ) if v.startswith("SHADOWLAB_")]:
        monkeypatch.delenv(variable)
    monkeypatch.setenv("SHADOWLAB_SORTIES", str(tmp_path))
    monkeypatch.setenv("SHADOWLAB_HOTES_AUTORISES", "*")
    publics = charger_public()
    assert "*" not in publics.hotes
    assert publics.base_donnees != config.charger().base_donnees
    assert publics.base_donnees == tmp_path / "public" / "public.sqlite3"
    assert (publics.conservation_jours, publics.https, publics.contact) == (90, True, "")

    monkeypatch.setenv("SHADOWLAB_PUBLIC_HOTES", "Vitrine.Example, www.vitrine.example")
    monkeypatch.setenv("SHADOWLAB_PUBLIC_CONTACT", CONTACT)
    monkeypatch.setenv("SHADOWLAB_PUBLIC_CONSERVATION_JOURS", "30")
    monkeypatch.setenv("SHADOWLAB_PUBLIC_HTTPS", "0")
    monkeypatch.setenv("SHADOWLAB_PUBLIC_PORT", "9001")
    monkeypatch.setenv("SHADOWLAB_PUBLIC_BASE", str(tmp_path / "ailleurs.sqlite3"))
    monkeypatch.setenv("SHADOWLAB_PUBLIC_ENTETE_IP", "CF-Connecting-IP")
    publics = charger_public()
    assert publics.hotes == ("vitrine.example", "www.vitrine.example")
    assert (publics.contact, publics.conservation_jours, publics.https, publics.port) == (CONTACT, 30, False, 9001)
    assert publics.base_donnees == tmp_path / "ailleurs.sqlite3"
    assert publics.entete_ip == "CF-Connecting-IP"
    assert config.charger().hotes_autorises == ("*",), "le périmètre des moteurs ne bouge pas"


def test_base_du_labo_refusee(reglages_publics):
    cx = ouvrir(reglages_publics)
    cx.execute(
        "INSERT INTO experiments (name, created_at, configuration, status) VALUES ('campagne-90', '2026', '{}', 'x')"
    )
    cx.close()
    with pytest.raises(ValueError, match="base"):
        creer_app_publique(reglages_publics)


@pytest.mark.parametrize("hotes", [("*",), (), ("*.vitrine.test",)])
def test_hotes_invalides_refuses(reglages_publics, hotes):
    with pytest.raises(ValueError, match="hôte"):
        creer_app_publique(replace(reglages_publics, hotes=hotes))


# --- R7 : cookies et en-têtes de sécurité ----------------------------------------------------------


def test_entetes_de_securite(client):
    for chemin in ("/", "/lab/vitrine", "/lab/static/vitrine.css", "/n-existe-pas"):
        r = client.get(chemin)
        csp = r.headers["content-security-policy"]
        assert "default-src 'self'" in csp and "frame-ancestors 'none'" in csp and "object-src 'none'" in csp
        assert r.headers["x-content-type-options"] == "nosniff"
        assert r.headers["referrer-policy"] == "same-origin"
        assert r.headers["strict-transport-security"].startswith("max-age=")
    for chemin in ("/", "/lab/vitrine", "/session"):
        assert client.get(chemin).headers["cache-control"] == "no-store", chemin
    client.cookies.clear()
    csrf = cookie_pose(client.get("/"), "slp-csrf").lower()
    for attribut in ("__host-", "httponly", "samesite=lax", "secure", "path=/"):
        assert attribut in csrf


def test_mode_http_sans_secure_ni_hsts(reglages_publics):
    with TestClient(creer_app_publique(replace(reglages_publics, https=False)), base_url=f"http://{HOTE}") as c:
        r = c.get("/")
        assert "strict-transport-security" not in r.headers
        csrf = cookie_pose(r, "slp-csrf").lower()
        assert "secure" not in csrf and not csrf.startswith("__host-")


# --- CSRF sur les formulaires -------------------------------------------------------------------


def test_commencer_depuis_une_autre_origine_refuse(client, reglages_publics):
    csrf = jeton_csrf(client)
    for origine in ("https://attaquant.example", "null", f"http://{HOTE}", f"https://{HOTE}.attaquant.example"):
        r = client.post(
            "/session/commencer",
            data={"consentement": "oui", "csrf": csrf},
            headers={"Origin": origine},
            follow_redirects=False,
        )
        assert r.status_code == 403, origine
    r = client.post(
        "/session/commencer",
        data={"consentement": "oui", "csrf": csrf},
        headers={"Sec-Fetch-Site": "cross-site"},
        follow_redirects=False,
    )
    assert r.status_code == 403
    assert ouvrir(reglages_publics).execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0


def test_commencer_sans_jeton_csrf_refuse(client, reglages_publics):
    jeton_csrf(client)
    for champs in ({"consentement": "oui"}, {"consentement": "oui", "csrf": "c" * 32}):
        r = client.post("/session/commencer", data=champs, headers={"Origin": ORIGINE}, follow_redirects=False)
        assert r.status_code == 403
    assert ouvrir(reglages_publics).execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0


# --- R8 : page d'information complète, démarrage refusé sans contact -----------------------------


def cles_collectees(source: str) -> tuple[set[str], set[str]]:
    """Clés de premier niveau envoyées par `observateur.js` : empreinte, puis comportement."""
    collecte = re.search(r"^async function collecter\(\) \{(.*?)^\}$", source, re.S | re.M).group(1)
    empreinte = set(re.findall(r"^ {4}(\w+):", collecte, re.M))
    bloc = re.search(r"envoyer\('comportement', \{(.*?)\}, true\)", source, re.S).group(1)
    comportement = set(re.findall(r"(?:^|[{,])\s*([a-z_]+)(?=\s*[:,}]|\s*$)", bloc, re.M))
    return empreinte, comportement


def test_liste_des_donnees_tiree_de_l_observateur():
    """La liste affichée couvre exactement ce que le script envoie : un champ ajouté sans elle fait échouer ce test."""
    empreinte, comportement = cles_collectees(OBSERVATEUR.read_text(encoding="utf-8"))
    assert len(empreinte) > 30 and "webrtc_test" in empreinte
    assert {cle for cle, _ in DONNEES_RELEVEES} == empreinte
    assert {cle for cle, _ in DONNEES_COMPORTEMENT} == comportement


def test_page_d_information_complete(client):
    r = client.get("/")
    texte = r.text
    for cle, description in DONNEES_RELEVEES + DONNEES_COMPORTEMENT:
        assert f"<code>{cle}</code>" in texte and escape(description) in texte, cle
    for entete in ENTETES_GARDES:
        assert entete in texte
    assert "90 jours" in texte
    assert escape(CONTACT) in texte
    for mention in ("adresse IP", "Supprimer ma session", "consentement", "CNIL", "Pourquoi", "Vos droits"):
        assert mention in texte, mention
    sel = Selector(texte)
    formulaire = sel.css('form[action="/session/commencer"][method="post"]')
    assert formulaire.css('input[type="checkbox"][name="consentement"][value="oui"][required]')
    assert formulaire.css('input[type="hidden"][name="csrf"]')
    assert sel.css('a[href="/lab/vitrine"]'), "visiter sans participer"
    assert sel.css('meta[name="sl-sans-tiers"][content="1"]')
    assert "observateur.js" not in texte


@pytest.mark.parametrize("contact", ["", "   "])
def test_demarrage_refuse_sans_contact(reglages_publics, contact):
    with pytest.raises(ValueError, match="contact"):
        creer_app_publique(replace(reglages_publics, contact=contact))


def test_conservation_invalide_refusee(reglages_publics):
    with pytest.raises(ValueError, match="conservation"):
        creer_app_publique(replace(reglages_publics, conservation_jours=0))


# --- Suppression par le visiteur (§ 5.6) -----------------------------------------------------------


def formulaire_de_suppression(client: TestClient) -> dict[str, str]:
    r = terminer(client)
    assert r.status_code == 200
    return champs_du_formulaire(r.text, "/session/supprimer")


def test_supprimer_efface_la_session_dans_toutes_les_tables(client, reglages_publics):
    autre_client = TestClient(client.app, base_url=ORIGINE)
    autre = commencer(autre_client, AUTRE_IP)
    assert collecter(autre_client, autre).status_code == 204

    jeton = commencer(client)
    client.get("/lab/vitrine/annonces/AN-000003")
    assert collecter(client, jeton).status_code == 204
    assert collecter(client, jeton, "comportement", {"evenements": {}}).status_code == 204
    cx = ouvrir(reglages_publics)
    run_id = cx.execute("SELECT id FROM runs WHERE session_token = ?", (jeton,)).fetchone()[0]
    # Tables que l'application n'écrit pas aujourd'hui : la suppression doit les couvrir quand même.
    tls_id = cx.execute(
        "INSERT INTO observations_tls (received_at, ja3, ja3_hash, ja4, details) VALUES ('t', 'a', 'b', 'c', '{}')"
    ).lastrowid
    cx.execute("UPDATE observations_http SET tls_id = ? WHERE session_token = ?", (tls_id, jeton))
    cx.execute(
        "INSERT INTO decisions (session_token, created_at, couche, decision) VALUES (?, 't', 'x', 'y')", (jeton,)
    )
    cx.execute(
        "INSERT INTO empreintes_vues (type, hash, premiere_vue, derniere_vue, sessions)"
        " VALUES ('canvas', 'h', 't', 't', ?)",
        (json.dumps([jeton]),),
    )
    cx.execute(
        "INSERT INTO fingerprints (run_id, browser_properties, http_properties, tls_properties,"
        " session_properties) VALUES (?, '{}', '{}', '{}', '{}')",
        (run_id,),
    )
    cx.execute(
        "INSERT INTO detections (run_id, detector_name, detector_version, classification, confidence, signals)"
        " VALUES (?, 'd', '1', 'humain', 1, '[]')",
        (run_id,),
    )
    cx.execute("INSERT INTO metrics (run_id) VALUES (?)", (run_id,))
    cx.execute(
        "INSERT INTO artifacts (run_id, artifact_type, file_path, created_at) VALUES (?, 'x', '/nulle-part', 't')",
        (run_id,),
    )

    champs = formulaire_de_suppression(client)
    r = client.post("/session/supprimer", data=champs, headers={"Origin": ORIGINE})
    assert r.status_code == 200 and "supprimée" in r.text

    for (table,) in cx.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall():
        colonnes = [c[1] for c in cx.execute(f"PRAGMA table_info({table})")]
        for ligne in cx.execute(f"SELECT * FROM {table}"):
            assert jeton not in " ".join(str(v) for v in ligne), table
            if "run_id" in colonnes:
                assert ligne["run_id"] != run_id, table
            if table == "runs":
                assert ligne["id"] != run_id
    assert cx.execute("SELECT COUNT(*) FROM observations_tls WHERE id = ?", (tls_id,)).fetchone()[0] == 0
    # L'autre session est intacte.
    assert cx.execute("SELECT COUNT(*) FROM runs WHERE session_token = ?", (autre,)).fetchone()[0] == 1
    assert cx.execute("SELECT COUNT(*) FROM observations_js WHERE session_token = ?", (autre,)).fetchone()[0] == 1


def test_supprimer_protege(client, reglages_publics):
    jeton = commencer(client)
    champs = formulaire_de_suppression(client)
    jeton_falsifie = {**champs, "session": f"{jeton}.{'0' * 64}"}
    assert client.post("/session/supprimer", data=jeton_falsifie, headers={"Origin": ORIGINE}).status_code == 400
    attaque = client.post("/session/supprimer", data=champs, headers={"Origin": "https://attaquant.example"})
    assert attaque.status_code == 403
    sans_csrf = {k: v for k, v in champs.items() if k != "csrf"}
    assert client.post("/session/supprimer", data=sans_csrf, headers={"Origin": ORIGINE}).status_code == 403
    assert ouvrir(reglages_publics).execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 1


# --- R9 : purge ---------------------------------------------------------------------------------


def vieillir(cx, jeton: str, jours: int) -> None:
    moment = (datetime.now(UTC) - timedelta(days=jours)).isoformat(timespec="milliseconds")
    cx.execute("UPDATE runs SET started_at = ? WHERE session_token = ?", (moment, jeton))


def test_purge_efface_les_vieilles_sessions_et_garde_les_recentes(client, reglages_publics):
    vieille = commencer(client)
    collecter(client, vieille)
    client.cookies.clear()
    recente = commencer(client, AUTRE_IP)
    collecter(client, recente)
    cx = ouvrir(reglages_publics)
    vieillir(cx, vieille, 91)
    vieillir(cx, recente, 89)
    assert purger(cx, 90) == 1
    tout = contenu_de_la_base(reglages_publics)
    assert vieille not in tout
    assert cx.execute("SELECT COUNT(*) FROM observations_js WHERE session_token = ?", (recente,)).fetchone()[0] == 1
    assert purger(cx, 90) == 0


def test_purge_au_demarrage(client, reglages_publics):
    vieille = commencer(client)
    vieillir(ouvrir(reglages_publics), vieille, 120)
    creer_app_publique(reglages_publics)
    assert vieille not in contenu_de_la_base(reglages_publics)


def test_commandes_public(monkeypatch, tmp_path, reglages_publics, capsys):
    from shadowlab import cli

    monkeypatch.setenv("SHADOWLAB_PUBLIC_BASE", str(reglages_publics.base_donnees))
    monkeypatch.setenv("SHADOWLAB_PUBLIC_HOTES", HOTE)
    monkeypatch.setenv("SHADOWLAB_PUBLIC_CONTACT", CONTACT)
    monkeypatch.setenv("SHADOWLAB_PUBLIC_CONSERVATION_JOURS", "90")
    monkeypatch.setenv("SHADOWLAB_PUBLIC_PORT", "8799")
    with fabriquer(reglages_publics) as c:
        vieille = commencer(c)
        c.cookies.clear()
        gardee = commencer(c, AUTRE_IP)
    vieillir(ouvrir(reglages_publics), vieille, 100)
    assert cli.main(["public", "purger"]) == 0
    assert "1 session" in capsys.readouterr().out
    assert cli.main(["public", "supprimer", gardee]) == 0
    assert ouvrir(reglages_publics).execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0

    import uvicorn

    appels: dict = {}
    monkeypatch.setattr(uvicorn, "run", lambda app, **options: appels.update(options, app=app))
    assert cli.main(["public", "servir"]) == 0
    assert appels["host"] == "127.0.0.1" and appels["port"] == 8799
    assert appels["access_log"] is False and appels["server_header"] is False

    appels.clear()
    monkeypatch.setenv("SHADOWLAB_PUBLIC_CONTACT", "")
    assert cli.main(["public", "servir"]) == 2
    assert not appels, "le serveur ne doit pas démarrer sans contact"


# --- R10 : limite d'ouverture de sessions ---------------------------------------------------------


def essayer(client: TestClient, adresse: str) -> int:
    client.cookies.clear()
    r = client.post(
        "/session/commencer",
        data={"consentement": "oui", "csrf": jeton_csrf(client)},
        headers={"Origin": ORIGINE, "X-Forwarded-For": f"10.0.0.1, {adresse}"},
        follow_redirects=False,
    )
    return r.status_code


def test_limite_par_adresse(reglages_publics):
    with fabriquer(reglages_publics, sessions_par_adresse=2) as c:
        assert [essayer(c, IP) for _ in range(3)] == [303, 303, 429]
        assert essayer(c, AUTRE_IP) == 303
    assert IP not in contenu_de_la_base(reglages_publics)


def test_plafond_global_par_jour(reglages_publics):
    with fabriquer(reglages_publics, sessions_par_jour=2) as c:
        assert [essayer(c, f"192.0.2.{n}") for n in range(1, 4)] == [303, 303, 429]


def test_plafond_de_taille_de_la_base(reglages_publics):
    with fabriquer(reglages_publics, taille_max_base=1) as c:
        assert essayer(c, IP) == 503


# === Corrections après audit (points A à D) =======================================================

# --- A. Disque : lignes de requêtes bornées, plafond de taille respecté à chaque écriture ----------


def test_requetes_notees_bornees(client, reglages_publics):
    jeton = commencer(client)
    enormes = {f"sec-ch-{'x' * n}": "v" * 600 for n in range(1, 120)}
    enormes["sec-fetch-" + "y" * 5000] = "z"
    assert client.get("/lab/vitrine", headers=enormes).status_code == 200
    client.request("X" * 1000, "/lab/vitrine")
    lignes = (
        ouvrir(reglages_publics)
        .execute("SELECT method, path, headers FROM observations_http WHERE session_token = ?", (jeton,))
        .fetchall()
    )
    assert len(lignes) >= 3
    for ligne in lignes:
        entetes = json.loads(ligne["headers"])
        assert len(ligne["headers"].encode()) <= 2048
        assert len(entetes) <= 40
        assert all(len(nom) <= 64 for nom, _ in entetes)
        assert len(ligne["method"]) <= 16 and len(ligne["path"]) <= 200
    assert any(nom.lower() == "user-agent" for nom, _ in json.loads(lignes[1]["headers"]))


def test_plafond_de_taille_respecte_a_l_ecriture(reglages_publics):
    """Une session ouverte avant que la base soit pleine ne peut plus rien y écrire ensuite."""
    with fabriquer(reglages_publics) as c:
        jeton = commencer(c)
        avant = ouvrir(reglages_publics).execute("SELECT COUNT(*) FROM observations_http").fetchone()[0]
        app_pleine = creer_app_publique(reglages_publics, replace(Limites(), taille_max_base=1))
        with TestClient(app_pleine, base_url=ORIGINE, cookies=c.cookies) as plein:
            assert plein.get("/lab/vitrine").status_code == 200, "la page reste servie"
            assert collecter(plein, jeton).status_code == 503
    cx = ouvrir(reglages_publics)
    assert cx.execute("SELECT COUNT(*) FROM observations_http").fetchone()[0] == avant
    assert cx.execute("SELECT COUNT(*) FROM observations_js").fetchone()[0] == 0


# --- B. Journal tournant, taille et nombre de fichiers bornés --------------------------------------


def test_journal_tourne_avec_taille_et_nombre_bornes(monkeypatch, tmp_path, reglages_publics):
    from logging.handlers import RotatingFileHandler

    from shadowlab import cli
    from shadowlab.journal import configurer
    from shadowlab.public import ROTATION_JOURNAL

    racine = logging.getLogger("shadowlab")
    anciens = list(racine.handlers)
    try:
        monkeypatch.setenv("SHADOWLAB_PUBLIC_BASE", str(reglages_publics.base_donnees))
        assert cli.main(["public", "purger"]) == 0
        tournants = [h for h in racine.handlers if isinstance(h, RotatingFileHandler)]
        assert len(tournants) == 1
        assert (tournants[0].maxBytes, tournants[0].backupCount) == ROTATION_JOURNAL
        assert 0 < ROTATION_JOURNAL[0] <= 10 * 1024 * 1024 and 0 < ROTATION_JOURNAL[1] <= 5

        configurer(tmp_path / "essai", rotation=(2000, 2))
        journal = logging.getLogger("shadowlab.public")
        for n in range(500):
            journal.debug("GET /lab/vitrine 200 %d", n)
        fichiers = sorted((tmp_path / "essai" / "logs").glob("shadowlab.jsonl*"))
        assert 2 <= len(fichiers) <= 3, fichiers
        assert all(f.stat().st_size <= 2000 for f in fichiers)
    finally:
        for gestionnaire in racine.handlers:
            gestionnaire.close()
        racine.handlers[:] = anciens


# --- C. Droit d'effacement dès le début, et après la session --------------------------------------


def test_ma_session_accessible_des_le_debut(client, reglages_publics):
    assert "Aucune session" in client.get("/session").text
    jeton = commencer(client)
    page = client.get("/session")
    assert page.status_code == 200 and jeton in page.text
    assert champs_du_formulaire(page.text, "/session/terminer")
    r = client.post(
        "/session/supprimer", data=champs_du_formulaire(page.text, "/session/supprimer"), headers={"Origin": ORIGINE}
    )
    assert r.status_code == 200 and "supprimée" in r.text
    assert jeton not in contenu_de_la_base(reglages_publics)
    assert jeton not in client.get("/session").text
    assert "observateur.js" not in client.get("/lab/vitrine").text


@pytest.mark.parametrize("fin", ["expiree_navigateur_relance", "terminee"])
def test_effacement_possible_apres_la_session(client, reglages_publics, fin):
    jeton = commencer(client)
    if fin == "terminee":
        merci = terminer(client)
        assert jeton in merci.text
        assert "tant que cette page est ouverte" not in merci.text
        assert 'href="/session"' in merci.text
    else:
        vieux = (datetime.now(UTC) - timedelta(hours=3)).isoformat(timespec="milliseconds")
        ouvrir(reglages_publics).execute("UPDATE runs SET started_at = ? WHERE session_token = ?", (vieux, jeton))
        for cookie in [c for c in client.cookies.jar if c.name.endswith("slp-csrf")]:  # cookie de navigation
            client.cookies.delete(cookie.name, domain=cookie.domain, path=cookie.path)
        assert "observateur.js" not in client.get("/lab/vitrine").text
    page = client.get("/session")
    assert jeton in page.text
    champs = champs_du_formulaire(page.text, "/session/supprimer")
    assert client.post("/session/supprimer", data=champs, headers={"Origin": ORIGINE}).status_code == 200
    assert jeton not in contenu_de_la_base(reglages_publics)


# --- D. Points mineurs ----------------------------------------------------------------------------


def test_terminer_exige_post_et_csrf(client, reglages_publics):
    jeton = commencer(client)
    cx = ouvrir(reglages_publics)

    def statut() -> str:
        return cx.execute("SELECT status FROM runs WHERE session_token = ?", (jeton,)).fetchone()[0]

    assert client.get("/session/terminer").status_code in (404, 405)
    champs = champs_du_formulaire(client.get("/lab/vitrine").text, "/session/terminer")
    assert client.post("/session/terminer", data={}, headers={"Origin": ORIGINE}).status_code == 403
    attaque = client.post("/session/terminer", data=champs, headers={"Origin": "https://attaquant.example"})
    assert attaque.status_code == 403
    assert statut() == "en_cours"
    assert client.post("/session/terminer", data=champs, headers={"Origin": ORIGINE}).status_code == 200
    assert statut() == "reussi"


def test_page_d_information_decrit_cookies_et_transit(client):
    texte = client.get("/").text
    for cookie in ("slp-csrf", "slp-session", "slp-droits"):
        assert f"<code>{cookie}</code>" in texte, cookie
    assert "ni vos cookies" not in texte
    assert "en transit" in texte
    assert "onglet" in texte and "premier plan" in texte
    r = client.post(
        "/session/commencer",
        data={"consentement": "oui", "csrf": jeton_csrf(client)},
        headers={"Origin": ORIGINE},
        follow_redirects=False,
    )
    droits = cookie_pose(r, "slp-droits").lower()
    for attribut in ("__host-", "httponly", "secure", "samesite=lax", "path=/", f"max-age={90 * 86400}"):
        assert attribut in droits, attribut
    assert f"max-age={2 * 3600}" in cookie_pose(r, "slp-session").lower()


def test_identifiants_d_extension_masques(client, reglages_publics):
    jeton = commencer(client)
    ids = ["abcdefghijklmnopabcdefghijklmnop", "12345678-1234-4234-9234-123456789abc", "ABCDEF12-3456-7890-ABCD-EF12"]
    pile = [
        f"at f (chrome-extension://{ids[0]}/contenu.js:1:2)",
        f"g@moz-extension://{ids[1]}/x.js:3:4",
        f"h@Safari-Web-Extension://{ids[2]}/y.js:5:6",
    ]
    charge = {"stack_trace_test": {"stack_brut": pile}, "integrite": {"toDataURL_error_stack": [pile[0]]}}
    assert collecter(client, jeton, payload=charge).status_code == 204
    cx = ouvrir(reglages_publics)
    stocke = cx.execute("SELECT payload FROM observations_js WHERE session_token = ?", (jeton,)).fetchone()[0]
    for identifiant in ids:
        assert identifiant not in stocke, identifiant
    assert "chrome-extension://" in stocke and "contenu.js" in stocke, "la forme de la trace reste lisible"


@pytest.mark.parametrize("chemin", ["/lab/vitrine/", "/lab/vitrine/annonces/", "/session/"])
def test_pas_de_redirection_sur_barre_finale(client, chemin):
    r = client.get(chemin, follow_redirects=False)
    assert r.status_code == 404 and "location" not in r.headers


def test_json_trop_imbrique_refuse(client, reglages_publics):
    jeton = commencer(client)
    for profond in (
        '{"kind": "empreinte", "page": "/", "payload": {"a": ' + "[" * 20000 + "]" * 20000 + "}}",  # RecursionError
        '{"kind": "empreinte", "page": "/", "payload": ' + '{"a": ' * 5000 + "1" + "}" * 5000 + "}",  # absurde
    ):
        assert len(profond) < 64 * 1024
        assert client.post(f"/lab/collecte?sl={jeton}", content=profond.encode()).status_code == 400
    assert ouvrir(reglages_publics).execute("SELECT COUNT(*) FROM observations_js").fetchone()[0] == 0


def test_erreur_de_base_donne_503_avec_les_entetes(client, monkeypatch):
    from shadowlab.public import donnees

    jeton = commencer(client)

    def panne(*_args, **_kwargs):
        raise sqlite3.DatabaseError("database disk image is malformed")

    monkeypatch.setattr(donnees, "noter_collecte", panne)
    r = collecter(client, jeton)
    assert r.status_code == 503 and "malformed" not in r.text
    monkeypatch.setattr(donnees, "session_en_cours", panne)
    r = client.get("/lab/vitrine")
    assert r.status_code == 503 and "malformed" not in r.text
    assert "default-src 'self'" in r.headers["content-security-policy"]
    assert r.headers["x-content-type-options"] == "nosniff"


def test_secret_vide_refuse(tmp_path, reglages_publics):
    from shadowlab.arena import secret as secret_arena

    dossier = tmp_path / "secret-vide"
    dossier.mkdir()
    for contenu in ("", "  \n"):
        (dossier / "secret").write_text(contenu)
        with pytest.raises(ValueError, match="vide"):
            secret_arena.charger(dossier)
    reglages_publics.base_donnees.parent.mkdir(parents=True)
    (reglages_publics.base_donnees.parent / "secret").write_text("")
    with pytest.raises(ValueError, match="vide"):
        creer_app_publique(reglages_publics)


def test_secret_valide_inchange_et_cree_s_il_manque(tmp_path):
    from shadowlab.arena import secret as secret_arena

    dossier = tmp_path / "nouveau"
    cle = secret_arena.charger(dossier)
    assert re.fullmatch(rb"[0-9a-f]{64}", cle)
    assert (dossier / "secret").stat().st_mode & 0o777 == 0o600
    assert secret_arena.charger(dossier) == cle
    assert [p.name for p in dossier.iterdir()] == ["secret"], "aucun fichier temporaire ne reste"
    (dossier / "secret").write_text("cle-choisie\n")
    assert secret_arena.charger(dossier) == b"cle-choisie"


# === E. Formulaire de contact (D-57) : écrire au responsable sans qu'une adresse soit affichée ====


def ecrire(client: TestClient, texte: str, adresse: str = IP, **entetes):
    """Envoie le formulaire de contact comme un navigateur : jeton lu dans la page, même origine."""
    champs = champs_du_formulaire(client.get("/contact").text, "/contact")
    return client.post(
        "/contact",
        data={**champs, "message": texte},
        headers={"Origin": ORIGINE, "X-Forwarded-For": adresse, **entetes},
        follow_redirects=False,
    )


def texte_rendu(reponse) -> str | None:
    """Texte remis dans le formulaire de contact par une réponse de refus."""
    assert champs_du_formulaire(reponse.text, "/contact")["csrf"]
    return Selector(reponse.text).css('form[action="/contact"] textarea[name="message"]::text').get()


def messages_recus(reglages: ReglagesPublics) -> list[str]:
    cx = boite.connexion(boite.chemin(reglages.base_donnees))
    try:
        return [ligne["texte"] for ligne in boite.lister(cx)]
    finally:
        cx.close()


def test_contact_remplace_l_adresse_dans_les_pages(client):
    page = Selector(client.get("/contact").text)
    formulaire = page.css('form[action="/contact"][method="post"]')
    assert formulaire.css('textarea[name="message"][required][maxlength="2000"]')
    assert formulaire.css('input[type="hidden"][name="csrf"]')
    assert "90 jours" in client.get("/contact").text, "la durée de conservation du message est annoncée"

    information = client.get("/").text
    assert Selector(information).css('a[href="/contact"]'), "la page d'information mène au formulaire"
    assert escape(CONTACT) in information, "le responsable reste nommé"
    sans_session = client.get("/session").text
    commencer(client)
    ma_session = client.get("/session").text
    merci = terminer(client).text
    for texte in (sans_session, ma_session, merci):
        assert Selector(texte).css('a[href="/contact"]'), texte[:200]
        assert "écrivez à :" not in texte and escape(CONTACT) not in texte


def test_contact_textes_exacts(client):
    information = client.get("/").text
    assert "ce que vous écrivez vous-même dans le formulaire de contact" in information
    for texte in (information, client.get("/contact").text):
        assert "jour de sa réception" in texte and "tel quel" not in texte and "ni lien avec" not in texte


def test_base_nommee_comme_la_boite_refusee(reglages_publics):
    homonyme = reglages_publics.base_donnees.with_name(boite.FICHIER)
    with pytest.raises(ValueError, match="messages"):
        creer_app_publique(replace(reglages_publics, base_donnees=homonyme))


def test_contact_enregistre_le_message_a_part_sans_adresse(client, reglages_publics):
    journalises: list[str] = []

    class Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            journalises.append(record.getMessage())

    journal = logging.getLogger("shadowlab.public")
    capture, niveau = Capture(level=logging.DEBUG), journal.level
    journal.addHandler(capture)
    journal.setLevel(logging.DEBUG)
    texte = "Bonjour,\nmerci d'effacer la session 0123456789abcdef0123456789abcdef.\nRéponse : moi@exemple.test"
    try:
        r = ecrire(client, texte.replace("\n", "\r\n"), **ENTETES_IP)
    finally:
        journal.removeHandler(capture)
        journal.setLevel(niveau)
    assert r.status_code == 303 and r.headers["location"] == "/contact/envoye"
    assert client.get("/contact/envoye").status_code == 200
    assert messages_recus(reglages_publics) == [texte]
    for reponse in (r, client.get("/contact"), client.get("/contact/envoye")):
        assert reponse.headers["referrer-policy"] == "no-referrer", "la page suivante ne dit pas d'où l'on vient"
    assert client.get("/").headers["referrer-policy"] == "same-origin"

    fichier = boite.chemin(reglages_publics.base_donnees)
    assert fichier.parent == reglages_publics.base_donnees.parent and fichier != reglages_publics.base_donnees
    assert fichier.stat().st_mode & 0o777 == 0o600
    cx = sqlite3.connect(fichier)
    lignes = cx.execute("SELECT * FROM messages").fetchall()
    cx.close()
    assert [ligne[1] for ligne in lignes] == [datetime.now(UTC).date().isoformat()], "le jour, jamais l'heure"
    tout = "\n".join(str(ligne) for ligne in lignes)
    assert IP not in tout and "testclient" not in tout, "ni adresse, ni client : le texte et sa date seulement"
    assert "moi@exemple.test" not in contenu_de_la_base(reglages_publics), "jamais dans la base des sessions"
    assert "moi@exemple.test" not in "\n".join(journalises) and IP not in "\n".join(journalises)


def test_contact_protege(client, reglages_publics):
    champs = champs_du_formulaire(client.get("/contact").text, "/contact")
    donnees = {**champs, "message": "essai"}
    assert client.post("/contact", data=donnees, headers={"Origin": "https://ailleurs.test"}).status_code == 403
    for envoi in ({"message": "essai"}, {**donnees, "csrf": "0" * 32}):
        r = client.post("/contact", data=envoi, headers={"Origin": ORIGINE})
        assert r.status_code == 403
        assert texte_rendu(r) == "essai", "formulaire expiré : le texte tapé est rendu, avec un jeton neuf"
    assert client.get("/contact/envoye").status_code == 200, "page fixe, sans effet"
    assert messages_recus(reglages_publics) == []


def test_contact_message_vide_ou_trop_long(client, reglages_publics):
    assert ecrire(client, "   ").status_code == 422
    trop_long = "<script>alert(1)</script>" + "x" * 2000
    r = ecrire(client, trop_long)
    assert r.status_code == 422
    assert "<script>alert(1)" not in r.text and escape("<script>alert(1)</script>") in r.text, "texte rendu, échappé"
    assert messages_recus(reglages_publics) == []
    accents = "é" * 2000  # 12 000 octets une fois encodé dans le formulaire : la borne compte les caractères
    assert ecrire(client, accents).status_code == 303
    assert messages_recus(reglages_publics) == [accents]
    assert ecrire(client, "x" * 40_000).status_code == 400, "formulaire démesuré : refusé sans être lu en entier"
    with fabriquer(reglages_publics, taille_message=5000) as c:
        assert ecrire(c, "é" * 5000, AUTRE_IP).status_code == 303, "la borne du formulaire suit la limite de caractères"


def test_contact_retire_les_caracteres_de_controle(client, reglages_publics):
    recu = "ligne 1\n\x1b[31mrouge\x00\u202e fin\tici"
    assert ecrire(client, recu).status_code == 303
    # Les espaces insécables (posées par macOS et iOS avant « ? » et « ! ») deviennent des espaces ordinaires.
    assert ecrire(client, "Jean\u00a0Dupont, d'accord\u202f?").status_code == 303
    assert messages_recus(reglages_publics) == ["ligne 1\n[31mrouge fin\tici", "Jean Dupont, d'accord ?"]


def test_contact_limite_par_adresse(reglages_publics):
    with fabriquer(reglages_publics, messages_par_adresse=2) as c:
        assert [ecrire(c, "essai", IP).status_code for _ in range(2)] == [303, 303]
        refus = ecrire(c, "troisième essai", IP)
        assert refus.status_code == 429 and texte_rendu(refus) == "troisième essai"
        assert ecrire(c, "essai", AUTRE_IP).status_code == 303
    assert len(messages_recus(reglages_publics)) == 3


def test_contact_plafond_par_jour_et_boite_pleine(reglages_publics):
    with fabriquer(reglages_publics, messages_par_jour=2) as c:
        assert [ecrire(c, "essai", f"192.0.2.{n}").status_code for n in range(1, 4)] == [303, 303, 429]
    with fabriquer(reglages_publics, messages_gardes=2) as c:
        refus = ecrire(c, "boîte pleine", "192.0.2.9")
        assert refus.status_code == 503 and texte_rendu(refus) == "boîte pleine"
    assert len(messages_recus(reglages_publics)) == 2


def vieillir_message(reglages: ReglagesPublics, texte: str, jours: int) -> None:
    moment = (datetime.now(UTC) - timedelta(days=jours)).date().isoformat()
    cx = boite.connexion(boite.chemin(reglages.base_donnees))
    cx.execute("UPDATE messages SET recu_le = ? WHERE texte = ?", (moment, texte))
    cx.close()


def test_purge_des_messages(client, reglages_publics):
    assert ecrire(client, "vieux").status_code == 303
    assert ecrire(client, "récent").status_code == 303
    vieillir_message(reglages_publics, "vieux", 91)
    vieillir_message(reglages_publics, "récent", 89)
    creer_app_publique(reglages_publics)  # purge au démarrage, comme pour les sessions
    assert messages_recus(reglages_publics) == ["récent"]


def test_commandes_messages(monkeypatch, reglages_publics, capsys):
    from shadowlab import cli

    monkeypatch.setenv("SHADOWLAB_PUBLIC_BASE", str(reglages_publics.base_donnees))
    monkeypatch.setenv("SHADOWLAB_PUBLIC_HOTES", HOTE)
    monkeypatch.setenv("SHADOWLAB_PUBLIC_CONTACT", CONTACT)
    monkeypatch.setenv("SHADOWLAB_PUBLIC_CONSERVATION_JOURS", "90")
    assert cli.main(["public", "messages"]) == 0
    assert "Aucun message" in capsys.readouterr().out
    with fabriquer(reglages_publics) as c:
        assert ecrire(c, "premier message\nsur deux lignes").status_code == 303
        assert ecrire(c, "second \x1b[2Jmessage").status_code == 303
        assert ecrire(c, "à purger").status_code == 303
    assert cli.main(["public", "messages"]) == 0
    sortie = capsys.readouterr().out
    assert "3 message(s)" in sortie and "premier message" in sortie and "sur deux lignes" in sortie
    assert "\x1b" not in sortie, "aucune séquence de terminal venue d'un visiteur"
    cx = boite.connexion(boite.chemin(reglages_publics.base_donnees))
    brut = boite.ajouter(cx, "écrit sans passer par le formulaire \x1b[2J")
    cx.close()
    assert cli.main(["public", "messages"]) == 0
    assert "\x1b" not in capsys.readouterr().out, "nettoyé à l'affichage aussi"
    assert cli.main(["public", "effacer-message", str(brut)]) == 0
    capsys.readouterr()
    numero = re.search(r"n° (\d+) .*\n\s+second", sortie).group(1)
    assert cli.main(["public", "effacer-message", numero]) == 0
    assert cli.main(["public", "effacer-message", numero]) == 1, "déjà effacé"
    assert cli.main(["public", "effacer-message"]) == 2
    vieillir_message(reglages_publics, "à purger", 100)
    capsys.readouterr()
    assert cli.main(["public", "purger"]) == 0
    assert "1 message" in capsys.readouterr().out
    assert messages_recus(reglages_publics) == ["premier message\nsur deux lignes"]
