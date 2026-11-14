"""Relevé enrichi du site public (D-76) : `public/static/releve.js`, la nature d'envoi `trace`, la notice.

Cadrage : `docs/recherche/site-public-communaute-2026-11-13.md`, « Relevé enrichi ». Le second script relève des
gestes en nombres seulement (souris, clics, défilement, molette, rythme du clavier, toucher, premier plan, focus,
taille de la fenêtre), jamais une touche, un texte, une adresse ni un identifiant ; il n'est chargé que pendant une
session, sur les pages des deux sites de démonstration ; le serveur valide chaque trace avant de l'écrire ; la notice
la décrit clé par clé, dans les deux langues. L'observateur du labo ne change pas.

Le comportement du script est vérifié sous Node (`tests/banc_releve.js`, navigateur factice dont les propriétés
interdites lèvent une erreur dès qu'elles sont lues), et sa source est lue (accès interdits, adresse unique).
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from html import escape
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from parsel import Selector
from test_public import (
    AUTRE_IP,
    CONTACT,
    HOTE,
    ORIGINE,
    PAGES_VITRINE,
    champs_du_formulaire,
    collecter,
    commencer,
    contenu_de_la_base,
    fabriquer,
    ouvrir,
    terminer,
    vieillir,
)
from test_public_social import (
    DUREES_S,
    entetes_de_chrome,
    instant,
    nature_de,
    parcourir,
    requetes_notees,
    type_de_page,
    visites_sociales,
)
from test_rejeu import COMPORTEMENT_HUMAIN
from test_rejeu import empreinte as empreinte_humaine

from shadowlab import database as db
from shadowlab import rejeu
from shadowlab.config import ReglagesPublics

RACINE = Path(__file__).parents[1]
RELEVE = RACINE / "src" / "shadowlab" / "public" / "static" / "releve.js"
BANC = Path(__file__).parent / "banc_releve.js"
OBSERVATEUR = RACINE / "src" / "shadowlab" / "site" / "static" / "observateur.js"
# Relevée le 14/11/2026 sur le commit 72bed9f, avant ce travail : le script du labo ne change pas d'un octet.
EMPREINTE_OBSERVATEUR = "93bc6217ad740289e404d7fd512c0aaeb01d022807a4d257049f9c5913f22f6e"
BALISE = '<script src="/public/static/releve.js" defer></script>'
JETON = "a" * 32
avec_node = pytest.mark.skipif(shutil.which("node") is None, reason="node absent")


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
        social_taille=12,
    )


@pytest.fixture
def client(reglages_publics):
    with fabriquer(reglages_publics) as c:
        yield c


def source() -> str:
    return RELEVE.read_text(encoding="utf-8")


def sans_commentaires(texte: str) -> str:
    texte = re.sub(r"/\*.*?\*/", "", texte, flags=re.S)
    return re.sub(r"(^|\s)//[^\n]*", r"\1", texte)


def table_des_cles(texte: str) -> dict[str, tuple[int, int, int, tuple[int, ...]] | None]:
    """La table `CLES` de releve.js : clé → None (un nombre) ou (nombres par ligne, lignes par envoi, lignes par
    page, colonnes en différences). C'est le seul endroit du script où les clés de la trace sont déclarées."""
    bloc = re.search(r"const CLES = Object\.freeze\(\{\n(.*?)\n  \}\);", texte, re.S).group(1)
    table: dict = {}
    for ligne in bloc.splitlines():
        m = re.fullmatch(r" {4}(\w+): (?:null|\[(\d+), (\d+), (\d+), \[([\d, ]*)\]\]),", ligne)
        assert m, ligne
        if m[2] is None:
            table[m[1]] = None
        else:
            table[m[1]] = (int(m[2]), int(m[3]), int(m[4]), tuple(int(c) for c in m[5].split(", ")))
    return table


def constante(nom: str) -> int:
    return int(re.search(rf"const {nom} = (\d+);", source()).group(1))


def banc(mode: str, parametres: dict) -> dict:
    sortie = subprocess.run(
        ["node", str(BANC), str(RELEVE), mode, json.dumps(parametres)],
        capture_output=True,
        text=True,
        check=True,
        timeout=120,
    ).stdout
    return json.loads(sortie)


def charges(page: dict) -> list[dict]:
    return [json.loads(envoi["corps"]) for envoi in page["envois"]]


def lignes(liste: list[int], largeur: int, differences: tuple[int, ...]) -> list[list[int]]:
    """Les lignes d'une liste de la trace, différences remises en valeurs."""
    resultat: list[list[int]] = []
    for debut in range(0, len(liste), largeur):
        ligne = liste[debut : debut + largeur]
        if resultat:
            ligne = [v + resultat[-1][i] if i in differences else v for i, v in enumerate(ligne)]
        resultat.append(ligne)
    return resultat


def trace_valide(**changements) -> dict:
    charge = {
        "version": 1,
        "morceau": 0,
        "raison": 2,
        "instant_ms": 8000,
        "cadre": [1280, 800, 1280, 5000, 0, 200, 1],
        "ecartes": 0,
        "souris": [0, 600, 400, 33, 5, -2],
        "clics": [5000, 610, 398, 0, 1, 1],
        "defilement": [2000, 30, 33, 30],
        "molette": [2000, 0, 100, 0],
        "clavier_appuis": [6000, 1, 180, 1],
        "clavier_relaches": [6090, 180],
        "tactile": [],
        "premier_plan": [0, 1, 8000, 0],
        "focus": [0, 1],
        "redimensionnements": [],
    }
    charge.update(changements)
    return charge


def envoyer_trace(client: TestClient, jeton: str, charge, page: str = "/lab/social/fil"):
    corps = json.dumps({"kind": "trace", "page": page, "payload": charge})
    return client.post(f"/lab/collecte?sl={jeton}", content=corps, headers={"Content-Type": "application/json"})


def traces_en_base(reglages: ReglagesPublics) -> list:
    cx = ouvrir(reglages)
    try:
        return cx.execute("SELECT session_token, page, payload FROM observations_js WHERE kind = 'trace'").fetchall()
    finally:
        cx.close()


# === Le script : servi par l'application publique seulement, chargé pendant une session seulement ==============


def test_releve_servi_sous_public_static_seulement(client):
    r = client.get("/public/static/releve.js")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/javascript")
    assert r.content == RELEVE.read_bytes()
    assert client.get("/lab/static/releve.js").status_code == 404
    assert not (RACINE / "src" / "shadowlab" / "site" / "static" / "releve.js").exists(), "pas dans le labo"


def test_observateur_du_labo_inchange():
    assert hashlib.sha256(OBSERVATEUR.read_bytes()).hexdigest() == EMPREINTE_OBSERVATEUR


def pages_des_deux_sites(client: TestClient) -> dict[str, str]:
    """Une page de chaque type de la vitrine et du réseau social : chemin → HTML."""
    pages = {chemin: client.get(chemin).text for chemin in PAGES_VITRINE}
    vus: set[str] = set()
    for chemin, html in parcourir(client).items():
        if type_de_page(chemin) not in vus:
            vus.add(type_de_page(chemin))
            pages[chemin] = html
    return pages


@pytest.mark.parametrize("langue", ["fr", "en"])
def test_releve_charge_en_session_sur_les_deux_sites(client, langue):
    jeton = commencer(client, langue=langue)
    pages = pages_des_deux_sites(client)
    assert len(pages) == len(PAGES_VITRINE) + 6
    for chemin, html in pages.items():
        sel = Selector(html)
        balises = sel.css('script[src="/public/static/releve.js"]')
        assert len(balises) == 1, chemin
        assert "defer" in balises[0].attrib and "type" not in balises[0].attrib, chemin
        assert sel.css('meta[name="sl-session"]::attr(content)').get() == jeton, chemin
        for script in sel.css("script"):
            assert script.attrib.get("src", "").startswith("/"), f"{chemin} : script dans la page"
            assert not script.xpath("string()").get().strip(), f"{chemin} : script dans la page"
    # Les pages de l'étude (accueil, notice, session, contact) ne le chargent jamais, même pendant une session.
    for chemin in ("/", f"/{langue}", f"/{langue}/information", "/session", "/contact", "/contact/envoye"):
        assert "releve.js" not in client.get(chemin).text, chemin


def test_releve_absent_hors_session(client):
    for chemin, html in pages_des_deux_sites(client).items():
        assert "releve.js" not in html, chemin
    jeton = commencer(client)
    assert terminer(client).status_code == 200
    for chemin, html in pages_des_deux_sites(client).items():
        assert "releve.js" not in html and jeton not in html, chemin


def test_balise_du_bandeau_de_la_vitrine_et_pages_du_labo():
    """Sur les annonces, la balise vient du HTML de confiance du bandeau de session ; le labo ne la sert jamais."""
    from shadowlab.public import pages, trace
    from shadowlab.site import vitrine

    assert trace.BALISE == BALISE
    for langue in ("fr", "en"):
        assert BALISE in pages.bandeau(langue, "c" * 32)
        assert "releve.js" not in pages.bandeau(langue, None)
    annonces = vitrine.generer(20261111, 45)
    for page in (vitrine.page_accueil(JETON, annonces), vitrine.page_fiche(JETON, annonces[2])):
        assert "releve.js" not in page


# === Les clés : le script, le serveur et la notice disent la même chose ===========================================


def test_cles_du_script_du_serveur_et_de_la_notice():
    from shadowlab.public import trace
    from shadowlab.public.textes import RELEVES_TRACE

    table = table_des_cles(source())
    assert list(table) == list(trace.SCHEMA), "mêmes clés, même ordre"
    for cle, regle in table.items():
        schema = trace.SCHEMA[cle]
        if regle is None:
            assert isinstance(schema, (trace.Nombre, trace.Uplet)), cle
        else:
            largeur, par_envoi, par_page, differences = regle
            assert isinstance(schema, trace.Liste), cle
            assert (schema.largeur, schema.lignes) == (largeur, par_envoi), cle
            assert par_page >= par_envoi and 0 in differences and max(differences) < largeur, cle
    assert constante("VERSION") == trace.VERSION
    assert constante("ENVOIS_PAR_PAGE") == trace.ENVOIS_PAR_PAGE
    assert set(RELEVES_TRACE) == {"fr", "en"}
    francais = dict(RELEVES_TRACE["fr"])
    for langue, liste in RELEVES_TRACE.items():
        assert [cle for cle, _ in liste] == list(table), langue
        assert all(texte.strip() for _, texte in liste), langue
    for cle, texte in RELEVES_TRACE["en"]:
        assert texte != francais[cle], f"{cle} : description non traduite"


@pytest.mark.parametrize("langue", ["fr", "en"])
def test_notice_decrit_la_trace_cle_par_cle(client, langue):
    from shadowlab.public.textes import RELEVES_TRACE

    texte = client.get(f"/{langue}/information").text
    for cle, description in RELEVES_TRACE[langue]:
        assert f"<code>{cle}</code>" in texte and escape(description) in texte, cle
    assert "<code>trace</code>" in texte, "la nature de l'envoi est nommée"


def nombre_ecrit(n: int, langue: str) -> str:
    return f"{n:,}".replace(",", " " if langue == "fr" else ",")


def test_notice_dit_les_plafonds_par_page():
    """Chaque liste de la trace dit dans la notice combien de lignes une page peut en relever, au plus ; les flux
    échantillonnés disent « 30 par seconde »."""
    from shadowlab.public.textes import RELEVES_TRACE

    table = table_des_cles(source())
    for langue, liste in RELEVES_TRACE.items():
        descriptions = dict(liste)
        for cle, regle in table.items():
            if regle is not None:
                assert nombre_ecrit(regle[2], langue) in descriptions[cle], (langue, cle)
        for cle in ("souris", "defilement", "tactile", "redimensionnements"):
            assert ("30 par seconde" if langue == "fr" else "30 per second") in descriptions[cle], (langue, cle)
        assert ("trentième de seconde" if langue == "fr" else "thirtieth of a second") in descriptions["molette"]


# === Limites dures, lues dans la source ===========================================================================

PROPRIETES_INTERDITES = (
    "key",
    "code",
    "keyCode",
    "which",
    "charCode",
    "value",
    "textContent",
    "innerText",
    "innerHTML",
    "outerHTML",
    "clipboardData",
    "getSelection",
    "selectionStart",
    "selectionEnd",
    "dataset",
    "id",
    "href",
    "src",
    "className",
    "getAttribute",
    "attributes",
    "nodeValue",
    "data",
)


def test_releve_ne_lit_ni_touche_ni_texte_ni_element():
    code = sans_commentaires(source())
    noms = "|".join(PROPRIETES_INTERDITES)
    assert not re.search(rf"\.\s*(?:{noms})\b", code), re.search(rf"\.\s*(?:{noms})\b", code)
    assert not re.search(rf"\[\s*['\"`](?:{noms})['\"`]\s*\]", code), "accès entre crochets"
    assert not re.search(rf"\{{[^{{}}]*\b(?:{noms})\b[^{{}}]*\}}\s*=", code), "déstructuration"
    for mot in ("getSelection", "clipboard", "selection", "KeyboardEvent", "InputEvent"):
        assert mot not in code, mot
    # Aucun événement qui porte un texte tapé, copié ou sélectionné.
    texte = r"input|beforeinput|keypress|composition\w*|copy|cut|paste|select|selectionchange|change"
    assert not re.search(rf"addEventListener\(\s*['\"](?:{texte})['\"]", code)


def test_releve_ni_autorisation_ni_stockage_ni_ailleurs():
    code = sans_commentaires(source())
    interdits = (
        "geolocation",
        "getUserMedia",
        "getDisplayMedia",
        "mediaDevices",
        "devicemotion",
        "deviceorientation",
        "DeviceMotion",
        "DeviceOrientation",
        "Accelerometer",
        "Gyroscope",
        "Magnetometer",
        "AmbientLight",
        "Notification",
        "requestPermission",
        "permissions",
        "bluetooth",
        "cookie",
        "Storage",
        "localStorage",
        "sessionStorage",
        "indexedDB",
        "caches",
        "XMLHttpRequest",
        "WebSocket",
        "EventSource",
        "postMessage",
        "import(",
        "importScripts",
        "Worker",
        "window.open",
        "eval(",
        "Function(",
        "setInterval",
    )
    for mot in interdits:
        assert mot not in code, mot
    for mot in ("usb", "hid", "serial", "nfc"):
        assert not re.search(rf"\b{mot}\b", code, re.I), mot
    assert not re.search(r"(?:https?:)?//[a-z0-9]", code, re.I), "aucune adresse vers un autre hôte"
    # Une seule adresse dans le script, celle du point d'entrée de ce site ; tout envoi passe par elle.
    adresses = {m for m in re.findall(r"'(/[^']*)'", code)}
    assert adresses == {"/lab/collecte?sl="}, adresses
    assert set(re.findall(r"(?:fetch|sendBeacon)\(\s*(\w+)", code)) == {"adresse"}
    assert "const adresse = ADRESSE + encodeURIComponent(jeton);" in code
    # Hors session, rien : le script s'arrête avant le premier écouteur.
    assert code.index("if (!jeton) return;") < code.index("addEventListener")


# === Sous Node : ce que le script fait vraiment ===================================================================

TOUS_LES_GESTES = [
    [10, "souris", 100, 100],
    [50, "souris", 110, 104],
    [90, "souris", 125, 110],
    [120, "clic", 125, 110, 0, "lien"],
    [130, "clic", 300, 200, 2, "bouton"],
    [140, "clic", 310, 210, 0, "image", "pen"],
    [150, "clic", 320, 220, 1, "texte", "touch"],
    [160, "clic", 330, 230, 0, "autre"],
    [200, "defiler", 40],
    [240, "defiler", 95],
    [260, "molette", 0, 100],
    [270, "molette", 3, 20],
    [400, "molette", 0, -50, 1],
    [500, "appui", 1, 0],
    [520, "appui", 1, 1],  # répétition d'une touche maintenue : pas une frappe
    [590, "relache"],
    [700, "appui", 0, 0],
    [790, "relache"],
    [800, "toucher", 0, 50, 60, 1, 12.4, 0.5],
    [810, "toucher", 1, 55, 66, 1, 12.4, 0.5],
    [900, "toucher", 2, 55, 66, 0],
    [950, "focus", 0],
    [960, "focus", 1],
    [1000, "taille", 1024, 700],
    [1100, "cacher"],
    [1200, "montrer"],
    [1300, "souris", 400, 300],
    [1400, "quitter"],
]


@avec_node
def test_releve_sous_node_ne_lit_rien_d_interdit_et_n_envoie_que_des_nombres():
    from shadowlab.public import trace

    resultat = banc("pas", {"options": {"chemin": "/lab/social/p/abc"}, "pas": TOUS_LES_GESTES})
    assert resultat["lues"] == [] and resultat["erreurs"] == [], resultat
    (page,) = resultat["pages"]
    assert page["envois"], "au moins un envoi"
    for envoi in page["envois"]:
        assert envoi["url"] == f"/lab/collecte?sl={JETON}"
        corps = json.loads(envoi["corps"])
        assert set(corps) == {"kind", "page", "payload"}
        assert corps["kind"] == "trace" and corps["page"] == "/lab/social/p/abc"
        charge = corps["payload"]
        assert list(charge) == list(table_des_cles(source())), "les clés de la table, dans son ordre"
        for valeur in charge.values():
            nombres = valeur if isinstance(valeur, list) else [valeur]
            assert all(type(n) is int for n in nombres), valeur
        assert trace.valider(charge) == charge, "le serveur accepte ce que le script envoie"


@avec_node
def test_releve_sans_session_ne_fait_rien():
    resultat = banc("pas", {"options": {"jeton": ""}, "pas": TOUS_LES_GESTES})
    (page,) = resultat["pages"]
    assert page["ecouteurs"] == 0 and page["envois"] == []
    assert resultat["lues"] == [] and resultat["erreurs"] == []


@avec_node
def test_releve_contenu_d_une_trace():
    table = table_des_cles(source())
    resultat = banc("pas", {"pas": TOUS_LES_GESTES})
    envois = resultat["pages"][0]["envois"]
    # La page passe à l'arrière-plan (un envoi), revient, puis on la quitte (un second envoi).
    assert [(e["via"], json.loads(e["corps"])["payload"]["raison"]) for e in envois] == [("beacon", 1), ("beacon", 2)]
    premier, second = (json.loads(e["corps"])["payload"] for e in envois)
    assert (premier["morceau"], second["morceau"]) == (0, 1)

    def decoder(charge: dict, cle: str) -> list[list[int]]:
        largeur, _, _, differences = table[cle]
        return lignes(charge[cle], largeur, differences)

    assert decoder(premier, "souris") == [[10, 100, 100], [50, 110, 104], [90, 125, 110]]
    assert decoder(second, "souris") == [[1300, 400, 300]], "chaque envoi repart de valeurs entières"
    clics = decoder(premier, "clics")
    assert [c[4] for c in clics] == [1, 2, 3, 4, 0], "lien, bouton, image, zone de texte, autre"
    assert [c[3] for c in clics] == [0, 2, 0, 1, 0], "bouton de la souris"
    assert [c[5] for c in clics] == [1, 1, 2, 3, 1], "souris, stylet, doigt"
    assert decoder(premier, "defilement") == [[200, 40], [240, 95]]
    assert decoder(premier, "molette") == [[260, 3, 120, 0], [400, 0, -50, 1]], "pas cumulés sur 1/30 s"
    assert decoder(premier, "clavier_appuis") == [[500, 1], [700, 0]], "la répétition n'est pas une frappe"
    assert decoder(premier, "clavier_relaches") == [[590], [790]]
    assert decoder(premier, "tactile") == [
        [800, 50, 60, 1, 12, 50, 0],
        [810, 55, 66, 1, 12, 50, 1],
        [900, 55, 66, 0, -1, -1, 2],
    ]
    assert decoder(premier, "focus") == [[0, 1], [950, 0], [960, 1]]
    assert decoder(premier, "redimensionnements") == [[1000, 1024, 700]]
    assert decoder(premier, "premier_plan") == [[0, 1], [1100, 0]]
    assert decoder(second, "premier_plan") == [[1200, 1]]
    assert premier["cadre"] == [1024, 700, 1280, 5000, 95, 200, 1]
    assert premier["instant_ms"] == 1100 and second["instant_ms"] == 1400


@avec_node
def test_releve_echantillonne_30_par_seconde_au_plus():
    table = table_des_cles(source())
    pas = [[t, "souris", t % 700, 300] for t in range(0, 1000, 4)]
    pas += [[t, "defiler", t] for t in range(1, 1000, 4)]
    pas += [[1000, "quitter"]]
    (charge,) = charges(banc("pas", {"pas": pas})["pages"][0])
    for cle in ("souris", "defilement"):
        instants = [ligne[0] for ligne in lignes(charge["payload"][cle], table[cle][0], table[cle][3])]
        assert 25 <= len(instants) <= 30, (cle, len(instants))
        assert all(b > a for a, b in zip(instants, instants[1:], strict=False)), cle


@avec_node
def test_releve_plafonds_par_page_et_morceaux():
    """Vingt minutes de souris sur une seule page : 9 000 positions au plus, par morceaux de 600 envoyés pendant la
    visite (requête ordinaire), le dernier à la sortie ; au-delà, des gestes « écartés », comptés."""
    from shadowlab.public import Limites, trace

    resultat = banc("promenade", {"pages": 1, "duree_ms": 20 * 60 * 1000, "souris_ms": 34})
    assert resultat["lues"] == [] and resultat["erreurs"] == []
    envois = resultat["pages"][0]["envois"]
    corps = [json.loads(e["corps"])["payload"] for e in envois]
    par_envoi = [len(c["souris"]) // 3 for c in corps]
    assert sum(par_envoi) == 9000 and max(par_envoi) == 600
    assert len(envois) <= trace.ENVOIS_PAR_PAGE
    morceaux = [(e, c) for e, c in zip(envois, corps, strict=True) if c["raison"] == 0]
    assert morceaux and all(e["via"] == "fetch" and not e["keepalive"] for e, _ in morceaux)
    assert envois[-1]["via"] == "beacon" and corps[-1]["raison"] in (1, 2)
    assert corps[-1]["ecartes"] > 0
    assert [c["morceau"] for c in corps] == list(range(len(corps)))
    assert all(trace.valider(c) == c for c in corps)
    assert max(len(e["corps"].encode()) for e in envois) < Limites().taille_corps // 4


@avec_node
def test_releve_une_trace_par_page_ordinaire():
    """En quittant une page, le navigateur la cache puis la décharge (ou l'inverse) : un seul envoi."""
    for fin in (["cacher", "quitter"], ["quitter", "cacher"]):
        pas = [[10, "souris", 1, 1], [500, fin[0]], [501, fin[1]]]
        assert len(banc("pas", {"pas": pas})["pages"][0]["envois"]) == 1, fin


@avec_node
def test_releve_terminer_envoie_avant_la_fin_de_la_session():
    """« Terminer ma session » est un formulaire : la trace part à l'envoi, avant que la session ne soit close."""
    pas = [[10, "souris", 1, 1], [100, "soumettre"], [300, "quitter"]]
    envois = banc("pas", {"pas": pas})["pages"][0]["envois"]
    assert len(envois) == 1 and envois[0]["via"] == "beacon"
    assert json.loads(envois[0]["corps"])["payload"]["instant_ms"] == 100


# === Le serveur : validation stricte, quotas à part =============================================================


def test_collecte_accepte_une_trace_valide_et_la_stocke_compacte(client, reglages_publics):
    jeton = commencer(client)
    charge = trace_valide()
    assert envoyer_trace(client, jeton, charge, page="/lab/social/p/abc").status_code == 204
    reponse = envoyer_trace(client, jeton, trace_valide(morceau=1), page="/lab/vitrine/annonces/AN-000001")
    assert reponse.status_code == 204
    (ligne, autre) = traces_en_base(reglages_publics)
    assert ligne["session_token"] == jeton and ligne["page"] == "/lab/social/p/abc"
    assert json.loads(ligne["payload"]) == charge
    assert ligne["payload"] == json.dumps(charge, separators=(",", ":"), sort_keys=True), "sans espace"
    assert autre["page"] == "/lab/vitrine/annonces/AN-000001"


def test_trace_stockee_ne_contient_que_des_nombres(client, reglages_publics):
    from shadowlab.public import trace

    jeton = commencer(client)
    for n in range(3):
        assert envoyer_trace(client, jeton, trace_valide(morceau=n)).status_code == 204
    nombre = r"-?\d+"
    valeur = rf"(?:{nombre}|\[(?:{nombre}(?:,{nombre})*)?\])"
    for ligne in traces_en_base(reglages_publics):
        assert re.fullmatch(rf'\{{"[a-z_]+":{valeur}(?:,"[a-z_]+":{valeur})*\}}', ligne["payload"]), ligne["payload"]
        assert set(json.loads(ligne["payload"])) == set(trace.SCHEMA)


def sans(cle: str) -> dict:
    charge = trace_valide()
    del charge[cle]
    return charge


INVALIDES = {
    "cle inconnue": {**trace_valide(), "texte": 1},
    "cle manquante": sans("souris"),
    "texte dans une liste": trace_valide(souris=["mot de passe", 1, 2]),
    "texte pour un nombre": trace_valide(version="1"),
    "nombre a virgule": trace_valide(souris=[0.5, 1, 2]),
    "booleen": trace_valide(raison=True),
    "booleen dans une liste": trace_valide(focus=[0, True]),
    "null": trace_valide(ecartes=None),
    "objet dans une liste": trace_valide(souris=[{"x": 1}, 1, 2]),
    "liste imbriquee": trace_valide(souris=[[0, 1, 2]]),
    "objet pour une liste": trace_valide(souris={"0": 1}),
    "ligne incomplete": trace_valide(souris=[0, 1]),
    "trop de lignes": trace_valide(souris=[0, 1, 1] * 601),
    "instant negatif": trace_valide(souris=[-1, 0, 0]),
    "instant trop grand": trace_valide(instant_ms=3 * 3600 * 1000 + 1),
    "position hors bornes": trace_valide(souris=[0, 10**6, 0]),
    "entier geant": trace_valide(ecartes=10**30),
    "sorte hors liste": trace_valide(clics=[0, 1, 1, 0, 5, 1]),
    "sorte negative": trace_valide(clics=[0, 1, 1, 0, -1, 1]),
    "zone de texte ni oui ni non": trace_valide(clavier_appuis=[0, 2]),
    "pression au-dela de 100": trace_valide(tactile=[0, 1, 1, 1, 10, 101, 0]),
    "autre version": trace_valide(version=2),
    "morceau au-dela du plafond": trace_valide(morceau=60),
    "cadre trop court": trace_valide(cadre=[1280, 800]),
    "cadre en texte": trace_valide(cadre="1280x800"),
}


@pytest.mark.parametrize("charge", list(INVALIDES.values()), ids=list(INVALIDES))
def test_collecte_refuse_toute_trace_invalide(client, reglages_publics, charge):
    jeton = commencer(client)
    assert envoyer_trace(client, jeton, charge).status_code == 400
    assert traces_en_base(reglages_publics) == []


@pytest.mark.parametrize(
    "remplacement",
    ['"ecartes": NaN', '"ecartes": Infinity', '"ecartes": -Infinity', '"ecartes": 1e999', '"ecartes": 1.0'],
)
def test_collecte_refuse_les_nombres_non_entiers_ou_infinis(client, reglages_publics, remplacement):
    jeton = commencer(client)
    corps = json.dumps({"kind": "trace", "page": "/lab/social/fil", "payload": trace_valide()})
    assert '"ecartes": 0' in corps
    corps = corps.replace('"ecartes": 0', remplacement)
    r = client.post(f"/lab/collecte?sl={jeton}", content=corps, headers={"Content-Type": "application/json"})
    assert r.status_code == 400
    assert traces_en_base(reglages_publics) == []


@pytest.mark.parametrize(
    "page",
    [
        "/lab/collecte",
        "/session",
        "/",
        "/lab/socialx",
        "/lab/social/fil?q=bonjour",
        "/lab/social/mot de passe",
        "/lab/vitrine/<b>",
        "/lab/social/" + "a" * 200,
        "",
        None,
        12,
    ],
)
def test_collecte_refuse_une_trace_hors_des_deux_sites(client, reglages_publics, page):
    jeton = commencer(client)
    assert envoyer_trace(client, jeton, trace_valide(), page=page).status_code == 400
    assert traces_en_base(reglages_publics) == []


def test_collecte_refuse_une_trace_sans_session(client, reglages_publics):
    assert envoyer_trace(client, JETON, trace_valide()).status_code == 403
    jeton = commencer(client)
    assert terminer(client).status_code == 200
    assert envoyer_trace(client, jeton, trace_valide()).status_code == 403
    assert traces_en_base(reglages_publics) == []


def test_quotas_des_traces_a_part_de_l_observateur(reglages_publics):
    """Les traces ont leurs propres plafonds : pleines, elles ne privent jamais l'observateur de ses envois (le rejeu
    a besoin de l'empreinte et du comportement), et l'inverse."""
    with fabriquer(reglages_publics, envois_trace_par_session=3, envois_par_session=2) as c:
        jeton = commencer(c)
        assert [envoyer_trace(c, jeton, trace_valide()).status_code for _ in range(4)] == [204, 204, 204, 429]
        assert collecter(c, jeton).status_code == 204
        assert collecter(c, jeton, "comportement", {"evenements": {"click": 1}}).status_code == 204
        assert collecter(c, jeton).status_code == 429, "le quota de l'observateur reste le sien"
    taille = len(json.dumps(trace_valide(), separators=(",", ":"), sort_keys=True).encode())
    with fabriquer(reglages_publics, volume_trace_par_session=2 * taille + 10) as c:
        c.cookies.clear()
        jeton = commencer(c, AUTRE_IP)
        assert [envoyer_trace(c, jeton, trace_valide()).status_code for _ in range(3)] == [204, 204, 429]
        assert collecter(c, jeton).status_code == 204


@avec_node
def test_ce_que_le_script_envoie_passe_au_serveur(client, reglages_publics):
    jeton = commencer(client)
    resultat = banc("pas", {"options": {"jeton": jeton, "chemin": "/lab/vitrine/annonces"}, "pas": TOUS_LES_GESTES})
    envois = resultat["pages"][0]["envois"]
    for envoi in envois:
        assert envoi["url"] == f"/lab/collecte?sl={jeton}"
        r = client.post(envoi["url"], content=envoi["corps"], headers={"Content-Type": "application/json"})
        assert r.status_code == 204, r.text
    assert len(traces_en_base(reglages_publics)) == len(envois)


# === Plafonds : 150 pages et 20 minutes de navigation active tiennent largement, une session reste bornée =========


@avec_node
def test_promenade_de_150_pages_et_20_minutes_tient_largement(client):
    """150 pages de 8 secondes (20 minutes) avec la souris en mouvement continu, du défilement et de la molette, deux
    clics par page et de la frappe une page sur cinq : le pire raisonnable d'une session active. Elle tient dans les
    plafonds avec une marge large, sans toucher à ceux de l'observateur."""
    from shadowlab.public import Limites, trace

    limites = Limites()
    parametres = {"pages": 150, "duree_ms": 8000, "souris_ms": 16, "defilement": [2000, 4000]}
    parametres |= {"clics": [5000, 6500], "frappe": {"toutes_les": 5, "debut": 6000, "touches": 30}}
    resultat = banc("promenade", parametres)
    assert resultat["lues"] == [] and resultat["erreurs"] == []
    envois = [json.loads(e["corps"])["payload"] for p in resultat["pages"] for e in p["envois"]]
    assert all(trace.valider(c) == c for c in envois)
    volume = sum(len(json.dumps(c, separators=(",", ":"), sort_keys=True).encode()) for c in envois)
    assert len(envois) * 3 <= limites.envois_trace_par_session, len(envois)
    assert volume * 4 <= limites.volume_trace_par_session, volume
    # Requêtes notées : au pire 17 par page avec les deux envois de l'observateur (mesuré sur le réseau social à 120
    # publications, le 14/11), plus les traces, qui passent aussi par /lab/collecte.
    commencer(client)
    assert max(1 + len(requetes_notees(html)) + 2 for html in parcourir(client).values()) <= 17
    assert (150 * 17 + len(envois)) * 4 <= limites.requetes_par_session * 3, "un quart de marge au moins"
    assert limites.envois_par_session >= 2 * 150, "l'observateur garde ses deux envois par page"


def test_un_envoi_au_pire_tient_dans_le_corps_permis():
    """Toutes les listes pleines, chaque nombre à sa plus grande écriture : un envoi reste sous `taille_corps`."""
    from shadowlab.public import Limites, trace

    def largeur(bornes: tuple[int, int]) -> int:
        return max(len(str(b)) for b in bornes) + 1  # la virgule

    pire = 60 * len(trace.SCHEMA) + 200  # clés, crochets, kind, page
    for regle in trace.SCHEMA.values():
        if isinstance(regle, trace.Liste):
            pire += regle.lignes * sum(largeur(b) for b in regle.colonnes)
        elif isinstance(regle, trace.Uplet):
            pire += sum(largeur(b) for b in regle.colonnes)
        else:
            pire += largeur(regle.bornes)
    assert pire < Limites().taille_corps, pire


# === Suppression, purge, rejeu ====================================================================================


def test_suppression_et_purge_effacent_les_traces(client, reglages_publics):
    autre = TestClient(client.app, base_url=ORIGINE)
    gardee = commencer(autre, AUTRE_IP)
    assert envoyer_trace(autre, gardee, trace_valide()).status_code == 204

    jeton = commencer(client)
    assert envoyer_trace(client, jeton, trace_valide()).status_code == 204
    page = client.get("/session").text
    champs = champs_du_formulaire(page, "/session/supprimer")
    r = client.post("/session/supprimer", data=champs, headers={"Origin": ORIGINE})
    assert r.status_code == 200
    assert jeton not in contenu_de_la_base(reglages_publics)
    assert [ligne["session_token"] for ligne in traces_en_base(reglages_publics)] == [gardee]

    from shadowlab.public import purger

    cx = ouvrir(reglages_publics)
    try:
        vieillir(cx, gardee, 91)
        assert purger(cx, 90) == 1
    finally:
        cx.close()
    assert traces_en_base(reglages_publics) == []


def session_publique(chemin_base: Path, visites: list[tuple[str, list[str]]], traces: bool) -> str:
    """Une session humaine dans une base publique, notée comme le fait l'application (comme
    `test_public_social.fabriquer_session`), avec ou sans les traces du relevé enrichi : un morceau au milieu de chaque
    page et un à la sortie, chacun avec sa requête POST /lab/collecte notée. Tout est écrit dans l'ordre d'arrivée."""
    from shadowlab.public import donnees

    cx = donnees.ouvrir(chemin_base)
    jeton = donnees.creer_session(cx, {"texte_information": "essai", "conservation_jours": 90})

    def requete(t: float, methode: str, adresse: str, entetes: list) -> None:
        cx.execute(
            "INSERT INTO observations_http (session_token, received_at, method, path, http_version, headers, cookies)"
            " VALUES (?, ?, ?, ?, '1.1', ?, '[]')",
            (jeton, instant(t), methode, adresse.split("?")[0], db.j(entetes)),
        )

    def message(t: float, kind: str, page: str, charge: dict) -> None:
        requete(t, "POST", "/lab/collecte", entetes_de_chrome("envoi", page))
        cx.execute(
            "INSERT INTO observations_js (session_token, received_at, kind, page, payload) VALUES (?, ?, ?, ?, ?)",
            (jeton, instant(t), kind, page, db.j(charge)),
        )

    t, precedente = 0.0, None
    for i, (page, ressources) in enumerate(visites):
        chemin = page.split("?")[0]
        requete(t, "GET", page, entetes_de_chrome("page", precedente))
        for k, ressource in enumerate(ressources):
            requete(t + 0.05 + 0.02 * k, "GET", ressource, entetes_de_chrome(nature_de(ressource), chemin))
        message(t + 1.0, "empreinte", chemin, empreinte_humaine(webrtc_test={"saute": "sans-tiers"}))
        duree = DUREES_S[i % len(DUREES_S)]
        if traces:
            message(t + duree / 2, "trace", chemin, trace_valide(raison=0))
        comportement = {**COMPORTEMENT_HUMAIN, "duree_page_ms": duree * 1000, "page_defilable": True}
        message(t + duree, "comportement", chemin, comportement)
        if traces:
            message(t + duree + 0.01, "trace", chemin, trace_valide(morceau=1))
        precedente, t = chemin, t + duree + 0.4
    cx.close()
    return jeton


def test_rejeu_ignore_les_traces(client, tmp_path):
    """`rejeu.py` n'est pas modifié : une session avec traces (et leurs requêtes notées) se rejoue exactement comme la
    même session sans elles."""
    commencer(client)
    visites = visites_sociales(client)
    resultats = []
    for traces in (False, True):
        chemin = tmp_path / ("avec" if traces else "sans") / "public.sqlite3"
        jeton = session_publique(chemin, visites, traces)
        cx = rejeu.ouvrir_publique(chemin)
        try:
            nb_traces = cx.execute("SELECT COUNT(*) FROM observations_js WHERE kind = 'trace'").fetchone()[0]
            assert nb_traces == (2 * len(visites) if traces else 0)
            resultat = rejeu.rejouer(cx, publique=True)
        finally:
            cx.close()
        assert resultat["sessions"] == {"total": 1, "rejouees": 1, "inutilisables": 0}
        resultats.append(json.dumps(resultat, sort_keys=True, default=str).replace(jeton, "JETON"))
    assert resultats[0] == resultats[1]


# === La notice et l'accueil ======================================================================================

JAMAIS = {
    "fr": (
        "ni ce que vous tapez (ni le texte, ni les touches",
        "Ni votre adresse IP",
        "Aucune géolocalisation n'est demandée ni relevée",
        "ni ce que vous copiez ou sélectionnez",
        "Rien qui demande une autorisation",
    ),
    "en": (
        "not what you type (neither the text nor the keys",
        "Not your IP address",
        "No geolocation is requested or recorded",
        "not what you copy or select",
        "Nothing that needs your permission",
    ),
}
PROMESSES_RETIREES = ("position de la souris", "mouse's position", "en chiffres seulement", "as numbers only")


@pytest.mark.parametrize("langue", ["fr", "en"])
def test_notice_jamais_releve_sans_la_position_de_la_souris(client, langue):
    html = client.get(f"/{langue}/information").text
    texte = " ".join(" ".join(Selector(html).css("main").xpath(".//text()").getall()).split())
    for promesse in PROMESSES_RETIREES:
        assert promesse not in texte, promesse
    jamais = " ".join(" ".join(Selector(html).css("#non-releve").xpath(".//text()").getall()).split())
    for phrase in JAMAIS[langue]:
        assert phrase in jamais, phrase
    souris = "mouvements de la souris" if langue == "fr" else "mouse movements"
    assert souris in " ".join(Selector(html).css("#releve li").xpath(".//text()").getall())


@pytest.mark.parametrize("langue", ["fr", "en"])
def test_rien_de_l_ancienne_promesse_ailleurs(client, langue):
    """Ni l'accueil, ni le bandeau des deux sites, ni la notice ne promettent encore « ni la position de la souris »."""
    pages = [client.get(f"/{langue}").text, client.get(f"/{langue}/information").text]
    commencer(client, langue=langue)
    pages += [client.get("/lab/social/fil").text, client.get("/lab/vitrine").text, client.get("/session").text]
    for html in pages:
        for promesse in PROMESSES_RETIREES:
            assert promesse not in html, promesse


def test_decision_d76_et_documentation():
    decisions = (RACINE / "docs" / "DECISIONS.md").read_text(encoding="utf-8")
    assert decisions.count("- **D-76 — ") == 1
    assert decisions.rindex("- **D-76 — ") > decisions.rindex("- **D-75 — "), "à la fin"
    d76 = decisions[decisions.rindex("- **D-76 — ") :]
    for mot in ("releve.js", "trace", "position de la souris", "Décidé par : coordination"):
        assert mot in d76, mot
    site_public = (RACINE / "docs" / "site-public.md").read_text(encoding="utf-8")
    mots = ("releve.js", "envois_trace_par_session", "volume_trace_par_session", "SHADOWLAB_PUBLIC_SESSIONS_PAR_JOUR")
    for mot in mots:
        assert mot in site_public, mot
