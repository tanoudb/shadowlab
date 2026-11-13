"""Application publique réduite (étape 1.6) : vitrine, sessions humaines consenties, collecte. Rien d'autre.

Chaque test est rattaché à une règle de `docs/site-public.md` (R1 à R10) ou à une condition du § 5 du plan.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import unicodedata
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
from shadowlab.public.pages import DONNEES_COMPORTEMENT, DONNEES_RELEVEES, VERSION_INFORMATION

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
    # Réseau social (cadrage du 13/11, v2) : rien du labo sous ses préfixes, ni sous les fichiers statiques publics.
    # Le parcours de toutes ses pages, lui, est dans test_public_social.py (aucun lien vers ces routes).
    "/lab/social/",
    "/lab/social/api/publications",
    "/lab/social/photos/",
    "/lab/social/photos/manifeste.json",
    "/lab/social/photos/%2e%2e/%2e%2e/app.py",
    "/lab/social/static/observateur.js",
    "/lab/social/connexion",
    "/public/static/",
    "/public/static/observateur.js",
    "/public/static/vitrine.css",
    "/public/static/lab.css",
    "/public/static/%2e%2e/app.py",
    "/public/static/social/photos/manifeste.json",
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
    # Réseau social : un fil, une publication, un profil, une étiquette, l'explorateur, et ses deux fichiers.
    fil = client.get("/lab/social/fil")
    assert fil.status_code == 200
    pages.append(fil.text)
    publication = client.get(Selector(fil.text).css('a[href^="/lab/social/p/"]::attr(href)').get())
    assert publication.status_code == 200
    pages.append(publication.text)
    for prefixe in ("/lab/social/u/", "/lab/social/t/"):
        lien = Selector(publication.text).css(f'a[href^="{prefixe}"]::attr(href)').get()
        pages.append(client.get(lien).text)
    for chemin in ("/lab/social/explorer", "/public/static/social.css", "/public/static/social.js"):
        r = client.get(chemin)
        assert r.status_code == 200, chemin
        pages.append(r.text)
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


@pytest.mark.skipif(shutil.which("node") is None, reason="node absent")
@pytest.mark.parametrize("balise", [True, False])
def test_debugger_et_first_input_sautes_quand_la_page_le_demande(balise):
    """Avec la balise, ni instruction `debugger` (elle arrête la page d'un visiteur aux outils de développement
    ouverts) ni lecture de l'entrée first-input : plus aucun détecteur ne les lit (D-62). Sans elle (labo), comme
    avant. Les autres mesures de `cdp_detection` restent."""
    source = OBSERVATEUR.read_text(encoding="utf-8")
    assert len(re.findall(r"\bdebugger\s*;", source)) == 1, "une seule instruction debugger, dans cdpDetectionTest"
    fonction = re.search(r"^function cdpDetectionTest\(\) \{.*?^\}$", source, re.S | re.M).group(0)
    # L'instruction est remplacée par une trace : la voir posée, c'est savoir que la ligne a été exécutée.
    instrumentee, remplacees = re.subn(r"\bdebugger\s*;", "globalThis.debuggerAtteint = true;", fonction)
    assert remplacees == 1
    script = f"""
const META = {json.dumps("1" if balise else None)};
const BALISE = 'meta[name="sl-sans-tiers"]';
globalThis.window = globalThis;
globalThis.document = {{
  querySelector: (s) => (s === BALISE && META ? {{ content: META }} : null),
  querySelectorAll: () => [],
}};
const types = [];
Object.defineProperty(globalThis, 'performance', {{
  configurable: true,
  value: {{ now: () => 0, getEntriesByType: (t) => {{ types.push(t); return []; }} }},
}});
globalThis.debuggerAtteint = false;
{instrumentee}
const r = cdpDetectionTest();
console.log(JSON.stringify({{ r, types, debuggerAtteint: globalThis.debuggerAtteint }}));
"""
    sortie = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True, timeout=30).stdout
    resultat = json.loads(sortie)
    r = resultat["r"]
    assert "console_log_natif" in r and r["cdp_resource_entries"] == 0, "les autres mesures restent"
    if balise:
        assert resultat["debuggerAtteint"] is False
        assert "first-input" not in resultat["types"]
        assert not {"debugger_delta_ms", "debugger_suspect", "has_first_input"} & set(r), r
        assert r["saute"] == "sans-tiers"
    else:
        assert resultat["debuggerAtteint"] is True
        assert "first-input" in resultat["types"]
        assert (r["debugger_delta_ms"], r["debugger_suspect"], r["has_first_input"]) == (0, True, False)
        assert "saute" not in r


def test_description_de_cdp_detection_suit_le_releve_public():
    """La page d'information ne décrit plus ce que le site public ne relève plus (première interaction)."""
    description = dict(DONNEES_RELEVEES)["cdp_detection"]
    assert "interaction" not in description and "mémoire" in description


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
    """La liste affichée couvre exactement ce que le script envoie, dans chaque langue de la notice : un champ ajouté
    sans elle fait échouer ce test."""
    from shadowlab.public.pages import RELEVES

    empreinte, comportement = cles_collectees(OBSERVATEUR.read_text(encoding="utf-8"))
    assert len(empreinte) > 30 and "webrtc_test" in empreinte
    assert {cle for cle, _ in DONNEES_RELEVEES} == empreinte
    assert {cle for cle, _ in DONNEES_COMPORTEMENT} == comportement
    assert set(RELEVES) == {"fr", "en"}
    for langue, (relevees, comport) in RELEVES.items():
        assert {cle for cle, _ in relevees} == empreinte, langue
        assert {cle for cle, _ in comport} == comportement, langue


def test_observateur_dit_si_la_page_defile_et_sa_plus_longue_pause():
    """`pas_de_scroll` et `pas_de_pause` lisent ces deux champs (12/11/2026) : envoyés et décrits sur la page."""
    _, comportement = cles_collectees(OBSERVATEUR.read_text(encoding="utf-8"))
    nouveaux = {"page_defilable", "delai_souris_max_ms"}
    assert nouveaux <= comportement
    assert nouveaux <= {cle for cle, _ in DONNEES_COMPORTEMENT}


def test_page_d_information_decrit_l_attente_des_voix_et_les_polices_de_reference():
    """Relevé du 12/11/2026 : la liste des voix est lue après une courte attente, dont la durée est envoyée
    (`voices_attente_ms`, `voices_evenement`), et les polices sont comparées à trois familles génériques (`bases`).
    Ces champs sont décrits sur la page ; un consentement donné sous un texte plus ancien ne les couvrait pas."""
    source = OBSERVATEUR.read_text(encoding="utf-8")
    assert {"r.voices_attente_ms", "r.voices_evenement", "r.bases"} <= set(re.findall(r"r\.\w+", source))
    descriptions = dict(DONNEES_RELEVEES)
    assert "attente" in descriptions["headless_signals"]
    assert "trois familles" in descriptions["font_fingerprint"]
    assert VERSION_INFORMATION not in ("2026-11-12.4", "2026-11-12.5")


def test_collecte_accepte_le_releve_de_comportement_complet(client, reglages_publics):
    """Un relevé de comportement tel qu'observateur.js l'envoie, listes pleines, passe les bornes de la collecte
    et s'enregistre tel quel."""
    jeton = commencer(client)
    releve = {
        "evenements": {"mousemove": 4000, "click": 12, "keydown": 40, "scroll": 300, "touchstart": 0},
        "premiere_interaction_ms": 850,
        "duree_page_ms": 600000,
        "delais_souris_ms": [16.67] * 50,
        "delai_souris_max_ms": 12345.67,
        "angles_segments": [0.123] * 40,
        "delais_clavier_ms": [140.25] * 40,
        "delais_scroll_ms": [33.33] * 50,
        "wheel_deltas": [-120.5] * 50,
        "page_defilable": True,
    }
    assert set(releve) == {cle for cle, _ in DONNEES_COMPORTEMENT}
    assert collecter(client, jeton, "comportement", releve).status_code == 204
    ligne = (
        ouvrir(reglages_publics)
        .execute("SELECT payload FROM observations_js WHERE session_token = ? AND kind = 'comportement'", (jeton,))
        .fetchone()
    )
    assert json.loads(ligne["payload"]) == releve


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
        assert reponse.headers["referrer-policy"] == "origin", "la page suivante ne reçoit que l'origine"
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


def test_contact_absent_du_fichier_de_journal(client, tmp_path):
    """D-57 : un message n'est que son texte et son jour. Le journal tournant, horodaté à la milliseconde, ne garde
    rien des pages de contact ni de ce qu'un navigateur charge avec elles (feuille de style, icône) : rapprochées
    des requêtes notées d'une session à la même milliseconde, ces lignes dateraient l'envoi ; une feuille de style
    chargée sans page notée trahirait aussi une page de contact."""
    from shadowlab.journal import configurer
    from shadowlab.public import ROTATION_JOURNAL

    racine = logging.getLogger("shadowlab")
    anciens, niveau, propage = list(racine.handlers), racine.level, racine.propagate
    enregistrements: list[str] = []

    class Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            enregistrements.append(record.getMessage())

    def messages_du_fichier() -> list[str]:
        return [json.loads(ligne)["message"] for ligne in fichier.read_text(encoding="utf-8").splitlines()]

    journal = logging.getLogger("shadowlab.public")
    capture = Capture(level=logging.DEBUG)
    try:
        configurer(tmp_path / "journal", rotation=ROTATION_JOURNAL)
        fichier = tmp_path / "journal" / "logs" / "shadowlab.jsonl"
        commencer(client)  # pendant une session : ses requêtes /lab/… sont notées en base, à la milliseconde
        client.get("/n-existe-pas")
        avant = messages_du_fichier()
        assert avant, "les erreurs du site restent journalisées"
        journal.addHandler(capture)
        # Ce qu'un navigateur demande : la page, sa feuille de style, l'icône ; l'envoi ; la page de confirmation.
        for chemin in ("/contact", "/lab/static/vitrine.css", "/favicon.ico"):
            client.get(chemin)
        assert ecrire(client, "Bonjour, merci d'effacer ma session.").status_code == 303
        for chemin in ("/contact/envoye", "/lab/static/vitrine.css", "/favicon.ico"):
            client.get(chemin)
        journal.removeHandler(capture)
        assert enregistrements == [], "aucun enregistrement, donc rien pour le fichier"
        apres = messages_du_fichier()
        assert apres == avant, "aucune ligne, pas même celles de la feuille de style ou de l'icône"
        assert not [ligne for ligne in apres if "/contact" in ligne or "message" in ligne]
        client.get("/n-existe-pas")
        assert "GET /n-existe-pas 404" in messages_du_fichier(), "les erreurs du site restent journalisées"
    finally:
        journal.removeHandler(capture)
        for gestionnaire in racine.handlers:
            gestionnaire.close()
        racine.handlers[:] = anciens
        racine.setLevel(niveau)
        racine.propagate = propage


def test_contact_avis_a_l_ecran_seulement_sur_un_terminal(client, capsys, monkeypatch):
    """L'avis « message de contact reçu » passe par la sortie standard, jamais par le journal ; et seulement si elle
    est un terminal : recueillie (journald sous systemd, fichier), sa ligne horodatée daterait l'envoi."""
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    assert ecrire(client, "premier").status_code == 303
    assert "message de contact reçu" in capsys.readouterr().out
    monkeypatch.setattr(sys.stdout, "isatty", lambda: False)
    assert ecrire(client, "second").status_code == 303
    assert "message" not in capsys.readouterr().out


def test_contact_origine_null_refusee(client, reglages_publics):
    # Pourquoi `Referrer-Policy: no-referrer` est interdit sur /contact : sous cette politique, un vrai
    # navigateur envoie `Origin: null` au POST du formulaire (norme Fetch), même vers le même site. Le garde
    # le refuse (403) et le formulaire ne s'envoie plus jamais. La politique `origin` garde la vraie origine.
    champs = champs_du_formulaire(client.get("/contact").text, "/contact")
    r = client.post("/contact", data={**champs, "message": "essai"}, headers={"Origin": "null"})
    assert r.status_code == 403
    assert messages_recus(reglages_publics) == []


def test_contact_referent_reduit_a_l_origine(client, reglages_publics):
    # Sous la politique `origin`, la page suivante reçoit `https://<hôte>/` : noté « / », jamais « /contact ».
    jeton = commencer(client)
    r = client.get("/lab/static/vitrine.css", headers={"Referer": f"{ORIGINE}/"})
    assert r.status_code == 200
    lignes = (
        ouvrir(reglages_publics)
        .execute(
            "SELECT headers FROM observations_http WHERE session_token = ? AND path = ?",
            (jeton, "/lab/static/vitrine.css"),
        )
        .fetchall()
    )
    referents = [valeur for ligne in lignes for nom, valeur in json.loads(ligne["headers"]) if nom.lower() == "referer"]
    assert referents == ["/"], referents


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


LIANTS = chr(0x200C) + chr(0x200D)  # seuls caractères invisibles gardés : ils lient lettres et emoji composés
SOURIRE = chr(0x1F600)
FAMILLE = chr(0x200D).join([chr(0x1F469), chr(0x1F469), chr(0x1F467)])  # emoji composé par des liants U+200D
# Invisibles, ou qui changent l'affichage dans un terminal : sens d'écriture (U+200E, U+200F, U+061C), espaces
# sans largeur (U+200B, U+2060, U+FEFF), annotation (U+FFF9), balise qui peut cacher du texte (U+E0041).
INVISIBLES = [0x200E, 0x200F, 0x061C, 0x200B, 0x2060, 0xFEFF, 0xFFF9, 0xE0041]


def test_contact_garde_les_emoji_courants(client, reglages_publics):
    texte = f"Merci {SOURIRE} de la part de toute la {FAMILLE}"
    assert ecrire(client, texte).status_code == 303
    assert messages_recus(reglages_publics) == [texte]


def test_nettoyer_ne_garde_que_ce_qui_s_affiche():
    """Liste blanche : saut de ligne, tabulation, caractères affichables (`str.isprintable()`) et les deux liants ;
    une espace particulière devient une espace ordinaire ; tout le reste part (Cc, Cf, Cs, Co, Cn). Prix accepté :
    un emoji plus récent que la table Unicode de Python, ou un drapeau à balises, perd des caractères."""
    for point in INVISIBLES:
        assert boite.nettoyer(f"a{chr(point)}b") == "ab", f"U+{point:04X}"
    assert boite.nettoyer("\x1b[2J\x00fin" + chr(0x202E)) == "[2Jfin", "ESC, NUL, U+202E toujours retirés"
    assert boite.nettoyer(f"{SOURIRE} {FAMILLE}") == f"{SOURIRE} {FAMILLE}"
    espaces = "a" + chr(0x00A0) + "b" + chr(0x202F) + "c" + chr(0x3000) + "d"
    assert boite.nettoyer(espaces) == "a b c d", "les espaces insécables deviennent des espaces"
    assert boite.nettoyer("a\nb\tc\r\nd\re") == "a\nb\tc\nd\ne"
    ecosse = chr(0x1F3F4) + "".join(map(chr, [0xE0067, 0xE0062, 0xE0073, 0xE0063, 0xE0074, 0xE007F]))
    assert boite.nettoyer(ecosse) == chr(0x1F3F4), "limite acceptée : le drapeau perd ses balises"
    # Sur U+0000 à U+30FF, les demi-paires et les balises : ni caractère « autre » (C*) hors les liants, ni
    # séparateur (Z*) autre que l'espace ordinaire.
    tous = "".join(map(chr, [*range(0x3100), *range(0xD800, 0xE000), *range(0xE0000, 0xE0080), *INVISIBLES]))
    garde = "\n\t " + LIANTS
    assert [c for c in boite.nettoyer(tous) if c not in garde and unicodedata.category(c)[0] in "CZ"] == []


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


# --- Une seule adresse ne ferme plus le formulaire (seconde relecture du 12/11) --------------------


def test_limiteur_sur_une_journee_glissante():
    from shadowlab.public.app import Limiteur

    instant = [1000.0]
    limiteur = Limiteur(2, fenetre_s=24 * 3600, horloge=lambda: instant[0])
    assert [limiteur.autoriser(IP) for _ in range(3)] == [True, True, False]
    instant[0] += 23 * 3600
    assert not limiteur.autoriser(IP), "23 heures plus tard, toujours refusé : la fenêtre dure un jour"
    assert limiteur.autoriser(AUTRE_IP)
    instant[0] += 3600
    assert limiteur.autoriser(IP), "24 heures après les deux premiers, l'adresse peut de nouveau écrire"


def test_contact_limite_par_adresse_et_par_jour(reglages_publics):
    """À 3 par heure, une adresse seule épuisait le plafond du jour (30) en 10 heures et remplissait la boîte (500)
    en 17 jours. Avec un plafond par adresse et par jour, plus bas que celui du jour et que la boîte divisée par la
    durée de conservation, elle ne peut faire ni l'un ni l'autre."""
    limites = Limites()
    assert limites.messages_par_adresse_jour < limites.messages_par_jour
    assert limites.messages_par_adresse_jour * reglages_publics.conservation_jours < limites.messages_gardes
    with fabriquer(reglages_publics, messages_par_adresse=10, messages_par_adresse_jour=2) as c:
        assert [ecrire(c, "essai", IP).status_code for _ in range(2)] == [303, 303]
        refus = ecrire(c, "troisième essai", IP)
        assert refus.status_code == 429 and texte_rendu(refus) == "troisième essai"
        assert ecrire(c, "essai", AUTRE_IP).status_code == 303
    assert len(messages_recus(reglages_publics)) == 3


def test_bloc_d_adresse():
    """Une adresse IPv6 compte pour son /64 ; une IPv4 reste elle-même ; le reste est gardé tel quel, sans erreur."""
    from shadowlab.public.app import bloc_d_adresse

    assert bloc_d_adresse("2001:db8:a:b::1") == bloc_d_adresse("2001:DB8:A:B:ffff::9") == "2001:db8:a:b::/64"
    assert bloc_d_adresse("2001:db8:a:c::1") != bloc_d_adresse("2001:db8:a:b::1")
    assert bloc_d_adresse("fe80::1%eth0") == "fe80::/64"
    assert bloc_d_adresse(IP) == IP
    assert bloc_d_adresse("::ffff:203.0.113.57") == IP, "une IPv4 écrite en IPv6 reste cette IPv4"
    for valeur in ("", "testclient", "pas une adresse", "[2001:db8::1]:443", "2001:db8::1, 10.0.0.1", "x" * 10_000):
        assert bloc_d_adresse(valeur) == valeur


def test_limites_par_adresse_comptent_un_bloc_ipv6(reglages_publics):
    """Un abonné IPv6 reçoit au moins un /64 et y change d'adresse à volonté : les limites par adresse (sessions
    et messages) le comptent comme une seule adresse. Deux /64 différents restent deux adresses ; IPv4 inchangé."""
    meme_bloc = ["2001:db8:a:b::1", "2001:db8:a:b:ffff:ffff:ffff:fffe", "2001:DB8:A:B:0:0:0:9"]
    autre_bloc = "2001:db8:a:c::1"
    with fabriquer(reglages_publics, sessions_par_adresse=2) as c:
        assert [essayer(c, adresse) for adresse in meme_bloc] == [303, 303, 429]
        assert essayer(c, autre_bloc) == 303
        assert [essayer(c, adresse) for adresse in ("192.0.2.1", "192.0.2.1", "192.0.2.2")] == [303, 303, 303]
    with fabriquer(reglages_publics, messages_par_adresse=2) as c:
        assert [ecrire(c, "essai", adresse).status_code for adresse in meme_bloc] == [303, 303, 429]
        assert ecrire(c, "essai", autre_bloc).status_code == 303


def test_effacer_tous_les_messages(monkeypatch, reglages_publics, capsys):
    from shadowlab import cli

    monkeypatch.setenv("SHADOWLAB_PUBLIC_BASE", str(reglages_publics.base_donnees))
    monkeypatch.setenv("SHADOWLAB_PUBLIC_HOTES", HOTE)
    monkeypatch.setenv("SHADOWLAB_PUBLIC_CONTACT", CONTACT)
    monkeypatch.setenv("SHADOWLAB_PUBLIC_CONSERVATION_JOURS", "90")
    with fabriquer(reglages_publics) as c:
        for n in range(3):
            assert ecrire(c, f"message {n}").status_code == 303
    capsys.readouterr()
    assert cli.main(["public", "effacer-message", "tous"]) == 0
    assert "3 message(s)" in capsys.readouterr().out
    assert messages_recus(reglages_publics) == []
    assert cli.main(["public", "effacer-message", "tous"]) == 0
    assert "0 message(s)" in capsys.readouterr().out
    with fabriquer(reglages_publics) as c:
        assert ecrire(c, "après l'effacement").status_code == 303
    cx = boite.connexion(boite.chemin(reglages_publics.base_donnees))
    numeros = [ligne["id"] for ligne in boite.lister(cx)]
    cx.close()
    assert numeros == [4], "un numéro n'est jamais réutilisé"


# --- Troisième relecture (12/11) : le journal ne garde que les erreurs, le contact ne laisse aucune trace ---------


@pytest.fixture
def fichier_de_journal(tmp_path):
    """Branche le journal tournant de l'application dans `tmp_path` ; renvoie une fonction qui lit ses messages."""
    from shadowlab.journal import configurer
    from shadowlab.public import ROTATION_JOURNAL

    racine = logging.getLogger("shadowlab")
    anciens, niveau, propage = list(racine.handlers), racine.level, racine.propagate
    configurer(tmp_path / "journal", rotation=ROTATION_JOURNAL)
    fichier = tmp_path / "journal" / "logs" / "shadowlab.jsonl"

    def lire() -> list[str]:
        return [json.loads(ligne)["message"] for ligne in fichier.read_text(encoding="utf-8").splitlines()]

    try:
        yield lire
    finally:
        for gestionnaire in racine.handlers:
            gestionnaire.close()
        racine.handlers[:] = anciens
        racine.setLevel(niveau)
        racine.propagate = propage


def test_journal_ne_garde_que_les_erreurs(client, fichier_de_journal):
    """« Rien n'est enregistré » pour qui visite sans participer, et le journal, qui ne suit pas la purge, ne date
    plus chaque requête ordinaire : seules les réponses de code 400 ou plus y laissent « méthode chemin statut »."""
    jeton = commencer(client)  # POST (303), puis GET : redirection et pages réussies
    for chemin in ("/", "/lab/vitrine", "/session", "/lab/static/vitrine.css", "/contact"):
        assert client.get(chemin).status_code == 200
    assert collecter(client, jeton).status_code == 204
    assert fichier_de_journal() == [], "une requête réussie ou redirigée n'écrit plus rien"

    assert client.get(f"/n-existe-pas?sl={jeton}").status_code == 404
    assert client.get("/lab/vitrine/annonces?page=999").status_code == 404
    assert client.post("/session/commencer", data={}, headers={"Origin": ORIGINE}).status_code == 403
    # Toujours hors du journal : les pages de contact (même en erreur) et les fichiers de la page.
    assert client.post("/contact", data={}, headers={"Origin": ORIGINE}).status_code == 403
    assert client.get("/lab/static/inconnu.js").status_code == 404
    assert fichier_de_journal() == [
        "GET /n-existe-pas 404",
        "GET /lab/vitrine/annonces 404",
        "POST /session/commencer 403",
    ]
    assert jeton not in "\n".join(fichier_de_journal())


def test_page_d_information_dit_la_verite_sur_le_journal_et_l_adresse(client):
    assert VERSION_INFORMATION == "2026-11-12.7", "le texte a changé : nouvelle version du texte accepté"
    texte = client.get("/").text
    for phrase in (
        "Un journal technique ne garde que les erreurs (réponses de code 400 ou plus) : la page demandée, "
        "le code de réponse et l'heure, sans adresse IP ni identifiant de session.",
        "Pour compter les ouvertures de session et les messages d'un même visiteur, une empreinte de votre adresse "
        "(pas l'adresse elle-même) est gardée en mémoire vive le temps de limiter les abus : une journée, un peu "
        "plus si personne ne visite le site entre-temps. Elle n'est jamais écrite sur le disque et disparaît à "
        "l'arrêt du serveur.",
        "n'enregistre pas votre adresse IP",
        "rien n'est relevé",
        "efface aussitôt toutes les données qui la concernent",
        "effacée automatiquement 90 jours après",
        "l'effacement peut avoir lieu un jour plus tard",
    ):
        assert phrase in texte, phrase
    assert "non réversible" not in texte and "24 heures au plus" not in texte, "promesses trop fortes retirées"
    bandeau = client.get("/lab/vitrine").text
    assert "Vous visitez sans participer : rien n'est enregistré" in bandeau
    assert "journal technique des erreurs" in bandeau, "la phrase du bandeau reste vraie : une erreur est journalisée"


def test_purge_des_messages_au_jour_limite(client, reglages_publics):
    """Un message n'est daté que du jour : à 90 jours révolus, il est effacé (avec `<`, il restait 91 jours)."""
    assert ecrire(client, "limite").status_code == 303
    assert ecrire(client, "veille").status_code == 303
    vieillir_message(reglages_publics, "limite", 90)
    vieillir_message(reglages_publics, "veille", 89)
    creer_app_publique(reglages_publics)
    assert messages_recus(reglages_publics) == ["veille"]


def attributs_de_liens(html: str) -> list[str]:
    """Toutes les adresses que la page demande ou propose : liens, ressources, actions de formulaire."""
    page = Selector(html)
    return (
        page.css("[href]::attr(href)").getall()
        + page.css("[src]::attr(src)").getall()
        + page.css("[action]::attr(action)").getall()
    )


def test_pages_de_contact_sans_trace_dans_la_session(client, reglages_publics, fichier_de_journal):
    """Pendant une session, `preparer` note en base toute requête sous /lab/ (à la milliseconde). Une page de contact
    ne charge donc rien sous /lab/, et ne propose aucun lien vers /lab/ : ni sa feuille de style, ni la page suivante
    ne trahissent l'ouverture du formulaire ou l'envoi."""
    from shadowlab.public.app import NON_JOURNALISES

    jeton = commencer(client)

    def requetes_notees() -> list[tuple]:
        cx = ouvrir(reglages_publics)
        try:
            return [tuple(r) for r in cx.execute("SELECT * FROM observations_http WHERE session_token = ?", (jeton,))]
        finally:
            cx.close()

    client.get("/n-existe-pas")  # prouve que le journal écrit encore (une erreur du site)
    notees, journalisees = requetes_notees(), fichier_de_journal()
    assert notees and journalisees == ["GET /n-existe-pas 404"]

    contact = client.get("/contact")
    feuille = Selector(contact.text).css('link[rel="stylesheet"]::attr(href)').getall()
    assert feuille == ["/contact/style.css"]
    assert client.get(feuille[0]).status_code == 200
    refus = client.post("/contact", data={}, headers={"Origin": "https://ailleurs.test"})
    assert refus.status_code == 403, "page d'erreur du formulaire"
    envoi = ecrire(client, "Bonjour, merci d'effacer ma session.")
    assert envoi.status_code == 303 and envoi.headers["location"] == "/contact/envoye"
    envoye = client.get("/contact/envoye")
    assert client.get(feuille[0]).status_code == 200

    assert requetes_notees() == notees, "aucune requête de contact notée dans la session"
    assert fichier_de_journal() == journalisees, "aucune ligne de journal pour le contact"
    assert "/contact/style.css".startswith(NON_JOURNALISES) and not "/contact/style.css".startswith("/lab/")

    for page in (contact, refus, envoye):
        assert page.status_code in (200, 403)
        assert "/lab/" not in page.text, "aucune adresse sous /lab/ (ressource, lien, pied de page)"
        assert not Selector(page.text).css("script"), "aucun observateur ni script : rien n'est envoyé à /lab/collecte"
        for adresse in attributs_de_liens(page.text):
            assert adresse == "/" or adresse.startswith("/contact"), adresse

    # Même contenu et mêmes en-têtes que la feuille du site, servie sous /contact/.
    css, ancienne = client.get("/contact/style.css"), client.get("/lab/static/vitrine.css")
    assert css.text == ancienne.text and css.headers["content-type"] == ancienne.headers["content-type"]
    assert css.headers["content-type"].startswith("text/css")
    assert css.headers["cache-control"] == ancienne.headers["cache-control"]
    assert css.headers["referrer-policy"] == "origin"
    assert client.get("/contact/autre.css").status_code == 404, "seule la feuille de style est servie"


# --- Limiteur en mémoire : balayage régulier, table pleine, en-tête d'adresse absent -------------------------


def test_limiteur_balaie_les_adresses_expirees_une_fois_par_minute_au_plus():
    """Avant : les empreintes expirées ne partaient que lorsque la table atteignait 10 000 entrées."""
    from shadowlab.public.app import Limiteur

    instant = [1000.0]
    limiteur = Limiteur(5, fenetre_s=100, horloge=lambda: instant[0])
    for adresse in ("192.0.2.1", "192.0.2.2", "192.0.2.3"):
        assert limiteur.autoriser(adresse)
    instant[0] = 1030.0
    assert limiteur.autoriser("192.0.2.4")
    assert len(limiteur._vues) == 4
    instant[0] = 1105.0  # les trois premières sont sorties de la fenêtre, la quatrième y est encore
    assert limiteur.autoriser("192.0.2.4")
    assert len(limiteur._vues) == 1, "le balayage retire toute clé dont la dernière action est hors fenêtre"
    instant[0] = 1300.0  # une fenêtre sans activité : la table se vide (reste la seule adresse de cet appel)
    assert limiteur.autoriser("192.0.2.5")
    assert len(limiteur._vues) == 1

    court = Limiteur(5, fenetre_s=10, horloge=lambda: instant[0])
    assert court.autoriser("192.0.2.1")
    instant[0] += 20.0
    assert court.autoriser("192.0.2.2")
    assert len(court._vues) == 2, "moins d'une minute depuis le dernier balayage : pas de nouveau balayage"
    instant[0] += 45.0
    assert court.autoriser("192.0.2.3")
    assert len(court._vues) == 1, "plus d'une minute : les deux premières, expirées, sont retirées"


def test_limiteur_table_pleine_ne_remet_aucun_compteur_a_zero():
    """Avant : une table pleine d'entrées valides était vidée d'un coup (`clear()`) : en tournant sur beaucoup de
    blocs d'adresses, on remettait tous les compteurs à zéro."""
    from shadowlab.public.app import Limiteur

    instant = [1000.0]
    limiteur = Limiteur(2, fenetre_s=3600, horloge=lambda: instant[0])
    limiteur.ADRESSES_MAX = 3
    assert [limiteur.autoriser("192.0.2.1") for _ in range(3)] == [True, True, False]
    assert limiteur.autoriser("192.0.2.2") and limiteur.autoriser("192.0.2.3")
    assert not limiteur.autoriser("192.0.2.4"), "table pleine : une adresse inconnue est refusée"
    assert not limiteur.autoriser("192.0.2.1"), "une adresse connue garde son compte : rien n'a été remis à zéro"
    assert limiteur.autoriser("192.0.2.2"), "une adresse connue qui n'a pas atteint son maximum passe encore"
    instant[0] += 3700.0  # la fenêtre est passée : les entrées sortent au balayage, la table se libère
    assert limiteur.autoriser("192.0.2.4")


def test_en_tete_d_adresse_absent_avertit_une_seule_fois_sans_adresse(client):
    """Entête configuré mais absent : tous les visiteurs partagent la limite de l'adresse de la connexion. Un
    avertissement au journal, une fois par démarrage, sans aucune adresse."""
    avertissements: list[str] = []

    class Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            if record.levelno >= logging.WARNING:
                avertissements.append(record.getMessage())

    journal = logging.getLogger("shadowlab.public")
    capture = Capture(level=logging.DEBUG)
    journal.addHandler(capture)
    try:
        champs = champs_du_formulaire(client.get("/contact").text, "/contact")
        for n in range(2):  # sans « X-Forwarded-For » : l'adresse de la connexion sert de repli
            r = client.post(
                "/contact",
                data={**champs, "message": f"essai {n}"},
                headers={"Origin": ORIGINE},
                follow_redirects=False,  # sinon le client suit la redirection et rend 200
            )
            assert r.status_code == 303
        assert len(avertissements) == 1, "un avertissement, une seule fois"
        assert "X-Forwarded-For" in avertissements[0]
        assert "testclient" not in avertissements[0] and IP not in avertissements[0]
        ecrire(client, "avec l'en-tête", AUTRE_IP)
        assert len(avertissements) == 1
    finally:
        journal.removeHandler(capture)


def test_en_tete_d_adresse_present_n_avertit_pas(client):
    avertissements: list[str] = []

    class Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            avertissements.append(record.getMessage())

    journal = logging.getLogger("shadowlab.public")
    capture = Capture(level=logging.WARNING)
    journal.addHandler(capture)
    try:
        assert ecrire(client, "essai", IP).status_code == 303
        assert avertissements == []
    finally:
        journal.removeHandler(capture)


# --- Droits des fichiers dès la création, effacement sans promesse fausse -------------------------------------


def test_droits_des_fichiers_des_leur_creation(monkeypatch, reglages_publics):
    """Le dossier de la base est en 700 et les deux fichiers en 600 AVANT que SQLite les ouvre : aucune fenêtre où un
    fichier existe avec des droits plus larges, avec ou sans le script de tunnel."""
    vus: dict[str, tuple[int, int | None]] = {}
    vrai = sqlite3.connect

    def espion(base, *args, **kwargs):
        chemin = Path(base)
        existe = chemin.exists()
        vus.setdefault(
            chemin.name, (chemin.parent.stat().st_mode & 0o777, chemin.stat().st_mode & 0o777 if existe else None)
        )
        return vrai(base, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", espion)
    with fabriquer(reglages_publics) as c:
        assert ecrire(c, "essai").status_code == 303
    assert vus["public.sqlite3"] == (0o700, 0o600), "créé en 600 avant l'ouverture, dans un dossier en 700"
    assert vus["messages.sqlite3"] == (0o700, 0o600)
    dossier = reglages_publics.base_donnees.parent
    assert dossier.stat().st_mode & 0o777 == 0o700
    fichiers = sorted(dossier.glob("*.sqlite3*"))
    assert fichiers and all(f.stat().st_mode & 0o777 == 0o600 for f in fichiers), fichiers


def test_droits_resserres_sur_un_dossier_et_des_fichiers_existants(reglages_publics):
    dossier = reglages_publics.base_donnees.parent
    dossier.mkdir(parents=True)
    dossier.chmod(0o755)
    for nom in ("public.sqlite3", "messages.sqlite3"):
        (dossier / nom).touch()
        (dossier / nom).chmod(0o644)
    with fabriquer(reglages_publics) as c:
        assert ecrire(c, "essai").status_code == 303
    assert dossier.stat().st_mode & 0o777 == 0o700
    assert all(f.stat().st_mode & 0o777 == 0o600 for f in dossier.glob("*.sqlite3*"))


def test_documentation_sans_promesse_d_ecrasement_physique():
    """`secure_delete` vide les pages dans la base ; il ne garantit pas l'écrasement physique (journal de SQLite,
    SSD, copie sur écriture, sauvegardes). Docstrings et documentation ne le promettent plus."""
    from shadowlab.public import donnees

    doc = (Path(__file__).parents[1] / "docs" / "site-public.md").read_text(encoding="utf-8")
    for texte in (doc, donnees.connexion.__doc__, boite.connexion.__doc__):
        assert not re.search(r"est écrasé", texte), "plus de promesse d'écrasement sur le disque"
    assert "ne garantit pas" in doc and "FileVault" in doc
    assert re.search(r"exclure.{0,40}outputs/", doc, re.S), "exclure outputs/ des sauvegardes"


# --- L'application publique ne charge que ses propres variables ------------------------------------------------

FICHIER_ENV = """# commentaire
SHADOWLAB_PUBLIC_CONTACT=Pseudo
export SHADOWLAB_VITRINE_TAILLE=7
SHADOWLAB_SORTIES=/tmp/sorties-essai
SHADOWLAB_JETON=jeton-du-labo
SHADOWLAB_PUBLICITE=non
CLE_API_DU_LABO=secret-du-labo
"""


@pytest.fixture
def environnement_isole(monkeypatch, tmp_path) -> dict[str, str]:
    """Un `.env` temporaire à la racine, et un environnement de processus que le test peut lire sans fuite."""
    (tmp_path / ".env").write_text(FICHIER_ENV, encoding="utf-8")
    monkeypatch.setattr(config, "RACINE", tmp_path)
    environnement = {k: v for k, v in os.environ.items() if not k.startswith("SHADOWLAB_")}
    monkeypatch.setattr(os, "environ", environnement)
    return environnement


def test_charger_public_ne_charge_que_ses_variables(environnement_isole):
    reglages = charger_public()
    assert reglages.contact == "Pseudo" and reglages.vitrine_taille == 7, "ses propres variables sont lues"
    assert environnement_isole["SHADOWLAB_PUBLIC_CONTACT"] == "Pseudo"
    for autre in ("SHADOWLAB_JETON", "SHADOWLAB_PUBLICITE", "CLE_API_DU_LABO"):
        assert autre not in environnement_isole, f"{autre} appartient au labo : il n'entre pas dans le processus"


def test_charger_public_garde_la_priorite_de_l_environnement(environnement_isole):
    environnement_isole["SHADOWLAB_PUBLIC_CONTACT"] = "Exporté"
    assert charger_public().contact == "Exporté"


def test_le_labo_charge_toujours_tout_le_fichier_env(environnement_isole):
    reglages = config.charger()
    assert reglages.jeton_api == "jeton-du-labo"
    assert environnement_isole["CLE_API_DU_LABO"] == "secret-du-labo"


# --- Journal de cloudflared : filtré avant d'être écrit --------------------------------------------------------

SCRIPT_TUNNEL = Path(__file__).parents[1] / "scripts" / "site-public-tunnel.sh"
HOTE_TUNNEL = "abc-def.trycloudflare.com"


def filtre_du_tunnel() -> str:
    """L'expression `sed` du script (variable `FILTRE_JOURNAL`), lue telle qu'il l'applique."""
    trouve = re.search(r"^FILTRE_JOURNAL='([^']+)'$", SCRIPT_TUNNEL.read_text(encoding="utf-8"), re.M)
    assert trouve, "le script doit garder son expression de filtrage dans la variable FILTRE_JOURNAL='…'"
    return trouve.group(1)


def filtrer_comme_le_tunnel(lignes: list[str]) -> list[str]:
    sortie = subprocess.run(
        ["sed", "-E", filtre_du_tunnel()], input="\n".join(lignes) + "\n", capture_output=True, text=True, check=True
    )
    return sortie.stdout.splitlines()


@pytest.mark.skipif(shutil.which("sed") is None, reason="sed absent")
def test_journal_du_tunnel_filtre_chemins_requetes_et_jetons():
    jeton = "0123456789abcdef0123456789abcdef"
    lignes = [
        f'2026-11-12T10:00:00Z ERR Request failed error="dial tcp 127.0.0.1:8771: refused" connIndex=0 '
        f"dest=https://{HOTE_TUNNEL}/lab/collecte?sl={jeton} event=1 ip=198.41.200.1 type=http",
        f"2026-11-12T10:00:01Z INF |  https://{HOTE_TUNNEL}                                        |",
        "2026-11-12T10:00:02Z INF Settings: map[url:http://127.0.0.1:8771] originService=http://127.0.0.1:8771",
        f'2026-11-12T10:00:03Z ERR msg="GET https://{HOTE_TUNNEL}/lab/vitrine/annonces/AN-000001?q=prive HTTP/1.1"',
        f"2026-11-12T10:00:04Z ERR path=/lab/collecte?sl={jeton}&x=1 status=502",
        f"2026-11-12T10:00:05Z ERR champ sl={jeton} perdu",
    ]
    sortie = filtrer_comme_le_tunnel(lignes)
    assert len(sortie) == len(lignes), "une ligne en entrée, une ligne en sortie"
    texte = "\n".join(sortie)
    for interdit in (jeton, "sl=" + jeton[:8], "/lab/", "collecte", "prive", "AN-000001", "q=", "?sl", "&x=1"):
        assert interdit not in texte, interdit
    assert f"dest=https://{HOTE_TUNNEL} event=1" in sortie[0], "l'adresse est réduite à schéma://hôte, le reste intact"
    assert re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", sortie[1]), "le script retrouve toujours l'adresse"
    assert HOTE_TUNNEL in sortie[1]
    assert "originService=http://127.0.0.1:8771" in sortie[2], "l'hôte local reste lisible"
    assert "status=502" in sortie[4] and "perdu" in sortie[5], "seul ce qui doit être masqué l'est"


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash absent")
def test_script_du_tunnel_garde_le_pid_de_cloudflared_et_filtre_sa_sortie():
    script = SCRIPT_TUNNEL.read_text(encoding="utf-8")
    assert subprocess.run(["bash", "-n", str(SCRIPT_TUNNEL)], capture_output=True).returncode == 0
    lancement = re.search(r"^cloudflared tunnel .*$", script, re.M)
    assert lancement, "cloudflared est lancé en arrière-plan"
    ligne = lancement.group(0)
    assert "> >(sed -l -E" in ligne and "FILTRE_JOURNAL" in ligne and ligne.rstrip().endswith("&")
    assert "|" not in ligne.replace("> >(", ""), "pas de tube : `$!` resterait le PID de cloudflared, pas de sed"
    assert re.search(r"^tunnel=\$!$", script, re.M) and 'kill "$tunnel"' in script
    assert "n'écrit aucune requête" not in script, "cette affirmation n'a jamais été vérifiée"
    assert "Non vérifié" in script or "jamais vérifié" in script


def test_une_requete_ordinaire_balaie_les_empreintes_expirees_de_chaque_limiteur(reglages_publics):
    """Le balayage ne dépend plus d'un appel du limiteur (ouverture de session, message) : la première requête
    reçue après la fin de la fenêtre retire les empreintes expirées de tous les limiteurs de l'application."""
    app = creer_app_publique(reglages_publics)
    limiteurs = app.state.limiteurs
    assert len(limiteurs) == 3
    instant = [1000.0]
    for limiteur in limiteurs:
        limiteur._horloge = lambda: instant[0]
        limiteur._dernier_balayage = instant[0]
        assert limiteur.autoriser(IP) and len(limiteur._vues) == 1
    instant[0] += 24 * 3600 + 120  # une fenêtre de jour passée, sans aucun appel d'un limiteur
    with TestClient(app, base_url=ORIGINE) as c:
        assert c.get("/").status_code == 200
    assert [len(limiteur._vues) for limiteur in limiteurs] == [0, 0, 0]
