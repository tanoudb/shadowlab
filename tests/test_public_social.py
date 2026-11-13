"""Réseau social fictif « Mosaïk Démo » de l'application publique : le squelette (cadrage du 13/11/2026, v2).

Le cadrage (`docs/recherche/site-public-communaute-2026-11-13.md`) impose la forme : de vraies pages courtes sous
`/lab/social/…`, notées pendant une session comme la vitrine, aucune écriture venant du visiteur, la politique de
sécurité inchangée, aucune route du labo. Ces tests vérifient cette forme ; le dessin viendra après.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections import deque
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient
from parsel import Selector
from PIL import Image
from test_public import (
    CONTACT,
    HOTE,
    ORIGINE,
    ROUTES_INTERDITES,
    collecter,
    commencer,
    fabriquer,
    ouvrir,
)
from test_rejeu import COMPORTEMENT_HUMAIN, UA
from test_rejeu import empreinte as empreinte_humaine

from shadowlab import config, rejeu
from shadowlab import database as db
from shadowlab.arena import profils
from shadowlab.config import ReglagesPublics, charger_public
from shadowlab.detection import Observations
from shadowlab.public import Limites, donnees, social
from shadowlab.public.app import CSP, langue_de
from shadowlab.site import gardien

RACINE = Path(__file__).parents[1]
SOCIAL_JS = RACINE / "src" / "shadowlab" / "public" / "static" / "social.js"
SOCIAL_CSS = RACINE / "src" / "shadowlab" / "public" / "static" / "social.css"
# Relevée le 13/11/2026 sur le commit f4e0452, avant toute modification : l'application du labo ne change pas.
EMPREINTE_SITE_APP = "571e2067c9b6ea148795615c2d369922264dfc135ac191756607b7641afda629"
# Copie littérale de la politique de sécurité du 13/11/2026 : le réseau social n'y change rien.
CSP_ATTENDUE = (
    "default-src 'self'; script-src 'self'; worker-src 'self' blob:; connect-src 'self'; img-src 'self' data:; "
    "style-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
)
GRAINE, TAILLE = 20261113, 30
LANGUES = {"fr": "fr-FR,fr;q=0.9", "en": "en-US,en;q=0.9"}
TYPES_DE_PAGE = ("fil", "explorer", "p", "u", "t", "credits")
# Seuls liens sortants du site : sur les pages de crédits, vers la page d'origine de chaque photo et vers sa licence.
HOTES_CREDITS = frozenset({"commons.wikimedia.org", "creativecommons.org"})
# Ce qu'une page du réseau social peut lier ou charger : ses propres pages, la vitrine (l'autre site), l'observateur
# du labo (pendant une session), ses deux fichiers statiques, et les pages de l'application publique.
PREFIXES_PERMIS = (
    "/lab/social/",
    "/lab/vitrine",
    "/public/static/social.css",
    "/public/static/social.js",
    "/lab/static/observateur.js",
)
CHEMINS_PERMIS = {"/", "/session", "/session/terminer", "/contact"}
MARQUES = (
    "instagram",
    "facebook",
    "meta",
    "twitter",
    "tiktok",
    "pinterest",
    "flickr",
    "unsplash",
    "pexels",
    "snapchat",
    "google",
    "apple",
    "iphone",
    "android",
    "samsung",
    "nikon",
    "canon",
    "sony",
    "leica",
    "fujifilm",
    "kodak",
    "gopro",
    "adobe",
    "photoshop",
    "lightroom",
    "vsco",
    "wikipedia",
    "wikimedia",
)
COURRIEL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


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
        social_graine=GRAINE,
        social_taille=TAILLE,
    )


@pytest.fixture
def client(reglages_publics):
    with fabriquer(reglages_publics) as c:
        yield c


def type_de_page(chemin: str) -> str:
    return chemin.removeprefix("/lab/social/").split("/")[0].split("?")[0]


def parcourir(client: TestClient, langue: str = "fr") -> dict[str, str]:
    """Toutes les pages du réseau social atteignables depuis le fil, en suivant les liens : chemin → HTML."""
    entetes = {"Accept-Language": LANGUES[langue]}
    vues: dict[str, str] = {}
    a_voir = deque(["/lab/social/fil"])
    while a_voir:
        chemin = a_voir.popleft()
        if chemin in vues:
            continue
        r = client.get(chemin, headers=entetes)
        assert r.status_code == 200, chemin
        assert r.headers["content-type"].startswith("text/html"), chemin
        vues[chemin] = r.text
        for lien in Selector(r.text).css("a::attr(href)").getall():
            lien = lien.split("#")[0]  # une ancre ne fait pas une autre page (le serveur ne la voit jamais)
            if lien.startswith("/lab/social/") and lien not in vues:
                a_voir.append(lien)
    return vues


def references(html: str) -> list[str]:
    """Tout ce qu'une page lie, charge ou envoie : liens, images, scripts, feuilles, formulaires."""
    sel = Selector(html)
    return sel.css("a::attr(href), img::attr(src), script::attr(src), link::attr(href), form::attr(action)").getall()


def lien_sortant_permis(html: str, ref: str) -> bool:
    """`ref` est un lien `<a>` de la page, en https, vers l'un des HOTES_CREDITS exactement, avec
    `rel="noopener noreferrer"` sur chaque lien qui y mène. Rien d'autre (ni image, ni script, ni formulaire)."""
    morceaux = urlsplit(ref)
    if morceaux.scheme != "https" or morceaux.hostname not in HOTES_CREDITS or morceaux.port is not None:
        return False
    liens = [a for a in Selector(html).css("a") if a.attrib.get("href") == ref]
    autres = Selector(html).css("img, script, link, form, iframe, source")
    if any(ref in (e.attrib.get(n) or "") for e in autres for n in ("src", "href", "action", "srcset")):
        return False
    return bool(liens) and all({"noopener", "noreferrer"} <= set(a.attrib.get("rel", "").split()) for a in liens)


def requetes_notees(html: str) -> list[str]:
    """Requêtes `/lab/…` qu'un navigateur fait pour afficher cette page, la page exclue, dans l'ordre du HTML.

    L'observateur charge BotD par un import (`./vendor/botd-2.0.0.esm.js`), absent du HTML."""
    sel = Selector(html)
    chemins = [
        c
        for c in sel.css("link[rel=stylesheet]::attr(href), script::attr(src), img::attr(src)").getall()
        if c.startswith("/lab/")
    ]
    if "/lab/static/observateur.js" in chemins:
        chemins.insert(chemins.index("/lab/static/observateur.js") + 1, "/lab/static/vendor/botd-2.0.0.esm.js")
    return chemins


# --- Les pages : toutes répondent, tous les liens mènent à une page qui existe -------------------


def test_social_redirige_vers_le_fil(client):
    r = client.get("/lab/social", follow_redirects=False)
    assert r.status_code in (302, 303, 307)
    assert r.headers["location"] == "/lab/social/fil", "adresse relative : jamais http:// derrière le mandataire"


@pytest.mark.parametrize("langue", list(LANGUES))
@pytest.mark.parametrize("en_session", [False, True], ids=["hors-session", "en-session"])
def test_parcours_de_toutes_les_pages(client, langue, en_session):
    jeton = commencer(client) if en_session else None
    pages = parcourir(client, langue)
    assert {type_de_page(c) for c in pages} == set(TYPES_DE_PAGE), "les cinq types de page sont atteints"
    assert sum(type_de_page(c) == "p" for c in pages) == TAILLE, "chaque publication a sa page"
    deja: dict[str, int] = {}
    for chemin, html in pages.items():
        assert f'<html lang="{langue}">' in html, chemin
        for ref in references(html):
            if type_de_page(chemin) == "credits" and lien_sortant_permis(html, ref):
                continue  # vérifié par test_liens_sortants_seulement_sur_les_credits
            assert ref.startswith("/") and not ref.startswith("//"), f"{chemin} : lien qui sort du site ({ref})"
            sans_requete = ref.split("?")[0]
            assert sans_requete not in ROUTES_INTERDITES, f"{chemin} : route du labo ({ref})"
            assert sans_requete in CHEMINS_PERMIS or sans_requete.startswith(PREFIXES_PERMIS), f"{chemin} : {ref}"
            if ref == "/session/terminer" or ref in pages:
                continue
            if ref not in deja:
                deja[ref] = client.get(ref, headers={"Accept-Language": LANGUES[langue]}).status_code
            assert deja[ref] == 200, f"{chemin} : {ref} répond {deja[ref]}"
        sel = Selector(html)
        assert sel.css('meta[name="sl-sans-tiers"]::attr(content)').get() == "1", chemin
        assert sel.css('a[href="/lab/vitrine"]'), f"{chemin} : lien vers l'autre site"
        if en_session:
            assert sel.css('meta[name="sl-session"]::attr(content)').get() == jeton, chemin
            assert sel.css('script[type="module"][src="/lab/static/observateur.js"]'), chemin
            assert sel.css('form[action="/session/terminer"][method="post"] button'), chemin
            assert sel.css('a[href="/session"]'), chemin
        else:
            assert "observateur.js" not in html and 'name="sl-session"' not in html, chemin
            assert sel.css('a[href="/"]'), f"{chemin} : rejoindre la page d'information"


def test_pages_inexistantes(client):
    univers = social.generer(GRAINE, TAILLE, social.charger_photos(social.DOSSIER_PHOTOS))
    derniere_fil = -(-TAILLE // social.PAR_PAGE_FIL)
    derniere_grille = -(-TAILLE // social.PAR_PAGE_GRILLE)
    assert client.get(f"/lab/social/fil?page={derniere_fil}").status_code == 200
    assert client.get(f"/lab/social/explorer?page={derniere_grille}").status_code == 200
    for chemin in (
        f"/lab/social/fil?page={derniere_fil + 1}",
        "/lab/social/fil?page=0",
        f"/lab/social/explorer?page={derniere_grille + 1}",
        "/lab/social/p/inconnu",
        "/lab/social/u/personne",
        "/lab/social/t/rien-du-tout",
        "/lab/social/",
        "/lab/social/autre",
    ):
        assert client.get(chemin).status_code == 404, chemin
    assert univers.publications, "l'univers n'est pas vide"


def test_les_deux_sites_se_lient(client):
    """Le bandeau de chaque site mène à l'autre, hors session et pendant une session."""
    for en_session in (False, True):
        if en_session:
            commencer(client)
        for chemin in ("/lab/vitrine", "/lab/vitrine/annonces", "/lab/vitrine/annonces/AN-000001"):
            assert Selector(client.get(chemin).text).css('a[href="/lab/social/fil"]'), (chemin, en_session)
        assert Selector(client.get("/lab/social/fil").text).css('a[href="/lab/vitrine"]'), en_session


# --- Hors session, rien n'est écrit ; pendant une session, comme la vitrine -----------------------


def test_visite_hors_session_n_ecrit_rien(client, reglages_publics):
    pages = parcourir(client)
    for html in pages.values():
        for ref in requetes_notees(html) + ["/public/static/social.css", "/public/static/social.js"]:
            assert client.get(ref).status_code == 200, ref
    cx = ouvrir(reglages_publics)
    for table in ("runs", "observations_http", "observations_js"):
        assert cx.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0, table
    assert not client.cookies, "aucun cookie hors session : pas même le jeton anti-CSRF (aucun formulaire)"


def test_en_session_pages_et_photos_notees(client, reglages_publics):
    jeton = commencer(client)
    html = client.get("/lab/social/fil").text
    publication = Selector(html).css('a[href^="/lab/social/p/"]::attr(href)').get()
    page = client.get(publication).text
    attendu = ["/lab/social/fil", publication]
    for ref in requetes_notees(page):
        assert client.get(ref).status_code == 200, ref
        attendu.append(ref)
    for statique in ("/public/static/social.css", "/public/static/social.js"):
        assert client.get(statique).status_code == 200
    assert collecter(client, jeton, payload={"navigateur": {"userAgent": "essai"}}).status_code == 204
    chemins = [
        r["path"]
        for r in ouvrir(reglages_publics).execute(
            "SELECT path FROM observations_http WHERE session_token = ? ORDER BY id", (jeton,)
        )
    ]
    debut = chemins.index("/lab/social/fil")
    assert chemins[debut : debut + len(attendu)] == attendu, "la page, puis chacune de ses requêtes /lab/"
    assert any(c.startswith("/lab/social/photos/") for c in attendu), "les photos sont notées"
    assert not any(c.startswith("/public/") for c in chemins), "seules les requêtes /lab/ sont notées"
    assert chemins[-1] == "/lab/collecte"


def test_observateur_charge_comme_sur_la_vitrine(client):
    jeton = commencer(client)

    def tete(chemin: str) -> tuple:
        sel = Selector(client.get(chemin).text)
        return (
            sel.css('meta[name="sl-session"]::attr(content)').get(),
            sel.css('meta[name="sl-sans-tiers"]::attr(content)').get(),
            sel.css('script[src="/lab/static/observateur.js"]::attr(type)').getall(),
        )

    assert tete("/lab/social/fil") == tete("/lab/vitrine") == (jeton, "1", ["module"])


def test_trois_cookies_au_plus(client):
    attendus = {"__Host-slp-csrf", "__Host-slp-session", "__Host-slp-droits"}
    commencer(client)
    poses: set[str] = set()
    for chemin in parcourir(client):
        for entete in client.get(chemin).headers.get_list("set-cookie"):
            poses.add(entete.split("=", 1)[0])
    assert poses <= attendus
    assert {c.name for c in client.cookies.jar} <= attendus


# --- Politique de sécurité ----------------------------------------------------------------------


@pytest.mark.parametrize("en_session", [False, True], ids=["hors-session", "en-session"])
def test_politique_de_securite(client, en_session):
    assert CSP == CSP_ATTENDUE, "la politique de sécurité de l'application publique a changé"
    if en_session:
        commencer(client)
    for langue in LANGUES:
        for chemin, html in parcourir(client, langue).items():
            assert client.get(chemin).headers["content-security-policy"] == CSP_ATTENDUE, chemin
            texte = html
            if type_de_page(chemin) == "credits":  # seule exception : les liens de crédit (page d'origine, licence)
                texte = re.sub(r'href="https://(?:commons\.wikimedia\.org|creativecommons\.org)/[^"]*"', "", html)
            assert not re.search(r"(?:https?:)?//[a-z0-9]", texte, re.I), f"{chemin} : adresse vers un autre hôte"
            assert "<style" not in html.lower(), chemin
            sel = Selector(html)
            for element in sel.xpath("//*"):
                for nom, valeur in element.attrib.items():
                    assert nom.lower() != "style", f"{chemin} : attribut style"
                    assert not nom.lower().startswith("on"), f"{chemin} : gestionnaire {nom}"
                    assert "javascript:" not in valeur.lower(), chemin
            for script in sel.css("script"):
                assert script.attrib.get("src", "").startswith("/"), f"{chemin} : script dans la page"
                assert not script.xpath("string()").get().strip(), f"{chemin} : script dans la page"


@pytest.mark.parametrize("en_session", [False, True], ids=["hors-session", "en-session"])
def test_aucun_formulaire_ni_champ_qui_partirait(client, en_session):
    if en_session:
        commencer(client)
    for chemin, html in parcourir(client).items():
        sel = Selector(html)
        formulaires = sel.css("form")
        if en_session:
            assert len(formulaires) == 1, chemin
            assert formulaires.attrib["action"] == "/session/terminer", chemin
            assert [e.attrib["name"] for e in formulaires.css("[name]")] == ["csrf"], chemin
        else:
            assert not formulaires, chemin
        hors_bandeau = sel.xpath("//*[@name][not(ancestor::form)][not(self::meta)]")
        assert not hors_bandeau, f"{chemin} : champ nommé hors du formulaire du bandeau"


def test_social_js_n_envoie_ni_ne_stocke_rien():
    source = SOCIAL_JS.read_text(encoding="utf-8")
    interdits = (
        "fetch(",
        "XMLHttpRequest",
        "sendBeacon",
        "WebSocket",
        "EventSource",
        "cookie",
        "localStorage",
        "sessionStorage",
        "indexedDB",
        "innerHTML",
        "outerHTML",
        "insertAdjacentHTML",
        "location",
        "submit",
        "import(",
        "postMessage",
        "window.open",
    )
    for mot in interdits:
        assert mot not in source, mot
    assert not re.search(r"(?:https?:)?//[a-z0-9]", source, re.I)
    assert "textContent" in source, "le texte tapé s'affiche par textContent"


def test_fichiers_statiques_du_reseau_social(client):
    for chemin, type_media, fichier in (
        ("/public/static/social.css", "text/css", SOCIAL_CSS),
        ("/public/static/social.js", "text/javascript", SOCIAL_JS),
    ):
        r = client.get(chemin)
        assert r.status_code == 200 and r.headers["content-type"].startswith(type_media), chemin
        assert r.content == fichier.read_bytes()
    for chemin in (
        "/public/static/",
        "/public/static/observateur.js",
        "/public/static/vitrine.css",
        "/public/static/social/photos/manifeste.json",
        "/public/static/%2e%2e/app.py",
        "/public/static/..%2fapp.py",
        "/public/static/social.js.bak",
        "/public/app.py",
    ):
        assert client.get(chemin).status_code == 404, chemin


def test_fichiers_statiques_jamais_au_journal(client):
    """Comme `/lab/static/` : ce que le navigateur charge avec chaque page n'écrit rien, même en erreur (D-65)."""
    messages: list[str] = []

    class Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            messages.append(record.getMessage())

    journal = logging.getLogger("shadowlab.public")
    capture, niveau = Capture(level=logging.DEBUG), journal.level
    journal.addHandler(capture)
    journal.setLevel(logging.DEBUG)
    try:
        assert client.get("/public/static/inconnu.js").status_code == 404
        assert client.get("/lab/social/p/inconnu").status_code == 404
    finally:
        journal.removeHandler(capture)
        journal.setLevel(niveau)
    assert messages == ["GET /lab/social/p/inconnu 404"]


# --- Photos : liste blanche du manifeste ----------------------------------------------------------


def test_photos_servies_depuis_le_manifeste_seulement(client):
    photos = social.charger_photos(social.DOSSIER_PHOTOS)
    assert len(photos) >= 1
    for photo in photos:
        for taille in (1080, 480):
            r = client.get(f"/lab/social/photos/{photo.id}-{taille}.jpg")
            assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
            assert r.headers["cache-control"] == "public, max-age=3600"
            assert r.content == (social.DOSSIER_PHOTOS / f"{photo.id}-{taille}.jpg").read_bytes()
    premiere = photos[0].id
    # Un « .. » en clair est résolu par le client avant l'envoi (il deviendrait /lab/social) : seules ses formes
    # encodées atteignent le serveur.
    for nom in (
        "inconnu.jpg",
        "manifeste.json",
        "%2e%2e",
        "%2e%2e%2fmanifeste.json",
        "..%2f..%2fapp.py",
        "%2e%2e/%2e%2e/app.py",
        f"{premiere}-1080.jpg.bak",
        f"{premiere}-720.jpg",
        f"{premiere.upper()}-1080.JPG",
        f"{premiere}-1080.jpg%00",
    ):
        assert client.get(f"/lab/social/photos/{nom}").status_code == 404, nom


def test_manifeste_photos_chaque_fichier_existe_sans_metadonnees():
    photos = social.charger_photos(social.DOSSIER_PHOTOS)
    for photo in photos:
        assert re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", photo.id)
        for taille in (1080, 480):
            with Image.open(social.DOSSIER_PHOTOS / f"{photo.id}-{taille}.jpg") as image:
                # `taille` borne le grand côté ; une photo source plus petite n'est jamais agrandie.
                assert image.format == "JPEG" and max(image.size) <= taille
                assert not image.getexif(), "aucune métadonnée EXIF"
                if taille == 1080:  # le manifeste donne les dimensions de ce fichier (la page réserve la place)
                    assert image.size == (photo.largeur, photo.hauteur)
        assert photo.licence and photo.auteur


def dossier_de_photos(tmp_path: Path, n: int, sujets=("mer", "Coquillages & crustacés")) -> Path:
    """Un manifeste de `n` photos minuscules, au format attendu."""
    dossier = tmp_path / f"photos-{n}"
    dossier.mkdir()
    entrees = []
    for i in range(n):
        ident = f"essai-{i:03d}"
        for taille in (1080, 480):
            Image.new("RGB", (8, 6), (i % 256, 90, 160)).save(
                dossier / f"{ident}-{taille}.jpg"
            )  # contenu sans importance
        entrees.append(
            {
                "id": ident,
                "sujet": sujets[i % len(sujets)],
                "largeur": 1080,
                "hauteur": 720,
                "auteur": "image d'essai",
                "licence": "CC0",
                "origine": None,
            }
        )
    (dossier / "manifeste.json").write_text(json.dumps({"photos": entrees}), encoding="utf-8")
    return dossier


@pytest.mark.parametrize("n", [1, 100])
def test_le_site_marche_avec_une_photo_comme_avec_cent(tmp_path, monkeypatch, reglages_publics, n):
    monkeypatch.setattr(social, "DOSSIER_PHOTOS", dossier_de_photos(tmp_path, n))
    with fabriquer(replace(reglages_publics, social_taille=120)) as c:
        pages = parcourir(c)
        servies = {ref for html in pages.values() for ref in requetes_notees(html)}
        photos = {ref for ref in servies if ref.startswith("/lab/social/photos/")}
        assert {p.rsplit("/", 1)[1].rsplit("-", 1)[0] for p in photos} == {f"essai-{i:03d}" for i in range(n)}
        for photo in sorted(photos)[:5]:
            assert c.get(photo).status_code == 200
        assert c.get("/lab/social/photos/manifeste.json").status_code == 404


@pytest.mark.parametrize(
    "entrees",
    [
        [],
        [{"id": "../dehors", "sujet": "mer", "largeur": 1080, "hauteur": 720}],
        [{"id": "absente", "sujet": "mer", "largeur": 1080, "hauteur": 720}],
        [{"id": "sans-hauteur", "sujet": "mer", "largeur": 1080}],
    ],
    ids=["vide", "chemin", "fichier-absent", "champ-manquant"],
)
def test_manifeste_invalide_refuse(tmp_path, entrees):
    (tmp_path / "manifeste.json").write_text(json.dumps({"photos": entrees}), encoding="utf-8")
    Image.new("RGB", (8, 6)).save(tmp_path / "sans-hauteur-1080.jpg")
    Image.new("RGB", (8, 6)).save(tmp_path / "sans-hauteur-480.jpg")
    with pytest.raises(ValueError):
        social.charger_photos(tmp_path)


# --- Crédits des photos : les licences demandent l'attribution -------------------------------------

CREDIT = {"fr": "Photo : {auteur} · {licence} · crédits", "en": "Photo: {auteur} · {licence} · credits"}


def texte_de(sel) -> str:
    return " ".join(" ".join(sel.xpath(".//text()").getall()).split())


def titre_affiche(titre: str) -> str:
    """Le titre de la photo sur Commons, sans l'extension du fichier."""
    return re.sub(r"\.(?:jpe?g|png|tiff?)$", "", titre, flags=re.I).replace("_", " ").strip()


def en_https(adresse: str) -> str:
    return "https://" + adresse.removeprefix("http://").removeprefix("https://")


def pages_de_credits(client: TestClient, langue: str) -> dict[str, str]:
    return {c: h for c, h in parcourir(client, langue).items() if type_de_page(c) == "credits"}


def test_manifeste_porte_les_credits():
    for photo in social.charger_photos(social.DOSSIER_PHOTOS):
        assert photo.titre and photo.auteur and photo.licence and photo.modifie, photo.id
        assert urlsplit(photo.origine).hostname == "commons.wikimedia.org", photo.id
        assert photo.licence_url is None or urlsplit(photo.licence_url).hostname == "creativecommons.org", photo.id


@pytest.mark.parametrize("langue", list(LANGUES))
def test_ligne_de_credit_sur_chaque_publication(client, langue):
    """Chaque publication crédite sa photo (auteur, licence) et mène à son entrée dans la page de crédits."""
    entetes = {"Accept-Language": LANGUES[langue]}
    univers = social.generer(GRAINE, TAILLE, social.charger_photos(social.DOSSIER_PHOTOS))
    for publication in univers.publications:
        sel = Selector(client.get(f"/lab/social/p/{publication.identifiant}", headers=entetes).text)
        credit = sel.css(".credit")
        assert len(credit) == 1, publication.identifiant
        photo = publication.photo
        assert texte_de(credit) == CREDIT[langue].format(auteur=photo.auteur, licence=photo.licence)
        liens = credit.css("a")
        assert len(liens) == 1 and texte_de(liens) == CREDIT[langue].rsplit(" ", 1)[1]
        adresse = liens.attrib["href"]
        chemin, _, ancre = adresse.partition("#")
        assert chemin.startswith("/lab/social/credits") and ancre == f"photo-{photo.id}", adresse
        page = Selector(client.get(chemin, headers=entetes).text)
        assert page.css(f'[id="photo-{photo.id}"]'), f"{adresse} : l'ancre est sur la page visée"


@pytest.mark.parametrize("langue", list(LANGUES))
def test_page_de_credits_complete(client, langue):
    """Toutes les photos du manifeste, chacune une fois : vignette, titre, auteur, licence (et son lien quand il
    existe), page d'origine, mention « redimensionnée ». Au plus PAR_PAGE_GRILLE par page (plafonds d'une session)."""
    photos = social.charger_photos(social.DOSSIER_PHOTOS)
    pages = pages_de_credits(client, langue)
    assert "/lab/social/credits" in pages, "la page de crédits est atteinte depuis le fil"
    vues: list[str] = []
    for chemin, html in pages.items():
        sel = Selector(html)
        entrees = sel.css('[id^="photo-"]')
        assert 1 <= len(entrees) <= social.PAR_PAGE_GRILLE, chemin
        vues += [e.attrib["id"].removeprefix("photo-") for e in entrees]
        intro = texte_de(sel.css(".credits-intro"))
        if langue == "fr":
            assert all(m in intro for m in ("vraies photos", "licence libre", "fictifs")), intro
        else:
            assert all(m in intro for m in ("real photos", "free licence", "fictional")), intro
    assert sorted(vues) == sorted(p.id for p in photos), "chaque photo du manifeste, une fois"
    entrees = {
        e.attrib["id"].removeprefix("photo-"): e
        for html in pages.values()
        for e in Selector(html).css('[id^="photo-"]')
    }
    for photo in photos:
        entree = entrees[photo.id]
        texte = texte_de(entree)
        assert entree.css(f'img[src="/lab/social/photos/{photo.id}-480.jpg"][alt]'), photo.id
        for attendu in (titre_affiche(photo.titre), photo.auteur, photo.licence):
            assert attendu in texte, (photo.id, attendu)
        assert ("redimensionnée" if langue == "fr" else "resized") in texte, photo.id
        sortants = {a.attrib["href"]: texte_de(a) for a in entree.css("a")}
        assert en_https(photo.origine) in sortants, photo.id
        if photo.licence_url:
            assert sortants.get(en_https(photo.licence_url)) == photo.licence, photo.id
        else:
            assert not any(urlsplit(h).hostname == "creativecommons.org" for h in sortants), photo.id


def test_credits_pagination(client):
    nb = social.nb_pages(len(social.charger_photos(social.DOSSIER_PHOTOS)), social.PAR_PAGE_GRILLE)
    assert client.get("/lab/social/credits").text == client.get("/lab/social/credits?page=1").text
    assert client.get(f"/lab/social/credits?page={nb}").status_code == 200
    for page in (0, nb + 1, -1):
        assert client.get(f"/lab/social/credits?page={page}").status_code == 404, page


def test_pied_de_page_mene_aux_credits(client):
    for chemin, html in parcourir(client).items():
        assert Selector(html).css('footer a[href="/lab/social/credits"]'), chemin


@pytest.mark.parametrize("langue", list(LANGUES))
@pytest.mark.parametrize("en_session", [False, True], ids=["hors-session", "en-session"])
def test_liens_sortants_seulement_sur_les_credits(client, langue, en_session):
    """Les seuls liens vers un autre hôte : `<a>` en https vers commons.wikimedia.org ou creativecommons.org
    exactement, avec rel="noopener noreferrer", sur les pages de crédits. Aucune ressource extérieure nulle part."""
    if en_session:
        commencer(client)
    sortants = 0
    for chemin, html in parcourir(client, langue).items():
        sel = Selector(html)
        for ref in sel.css("img::attr(src), script::attr(src), link::attr(href), form::attr(action)").getall():
            assert ref.startswith("/") and not ref.startswith("//"), f"{chemin} : ressource extérieure ({ref})"
        for ref in sel.css("a::attr(href)").getall():
            if ref.startswith("/") and not ref.startswith("//"):
                continue
            assert type_de_page(chemin) == "credits", f"{chemin} : lien sortant hors des crédits ({ref})"
            assert lien_sortant_permis(html, ref), f"{chemin} : lien sortant refusé ({ref})"
            sortants += 1
    assert sortants >= len(social.charger_photos(social.DOSSIER_PHOTOS)), "page d'origine de chaque photo"


def test_liens_de_credit_verifies_au_rendu(tmp_path, monkeypatch, reglages_publics):
    """Un manifeste qui pointerait ailleurs ne produit aucun lien ; une adresse en http passe en https."""
    dossier = dossier_de_photos(tmp_path, 3)
    manifeste = json.loads((dossier / "manifeste.json").read_text(encoding="utf-8"))
    autres = [
        {"origine": "https://exemple.org/File:a.jpg", "licence_url": "https://exemple.org/licence"},
        {"origine": "http://commons.wikimedia.org/wiki/File:b.jpg", "licence_url": "http://creativecommons.org/x/"},
        {"origine": "https://commons.wikimedia.org.exemple.org/c", "licence_url": "javascript:alert(1)"},
    ]
    for entree, champs in zip(manifeste["photos"], autres, strict=True):
        entree.update(champs, titre="Essai.jpg", modifie="redimensionnée")
    (dossier / "manifeste.json").write_text(json.dumps(manifeste), encoding="utf-8")
    monkeypatch.setattr(social, "DOSSIER_PHOTOS", dossier)
    with fabriquer(reglages_publics) as c:
        html = c.get("/lab/social/credits").text
    liens = Selector(html).css("a::attr(href)").getall()
    assert "https://commons.wikimedia.org/wiki/File:b.jpg" in liens
    assert "https://creativecommons.org/x/" in liens
    assert not [h for h in liens if "exemple.org" in h or "javascript" in h or h.startswith("http://")], liens


# --- Le générateur ------------------------------------------------------------------------------


def photos_factices(n: int) -> tuple:
    sujets = ("mer", "montagne", "Coquillages & crustacés")
    return tuple(
        social.Photo(id=f"essai-{i:03d}", sujet=sujets[i % len(sujets)], largeur=1080, hauteur=720) for i in range(n)
    )


def test_generateur_deterministe(tmp_path, reglages_publics):
    photos = photos_factices(12)
    assert social.generer(GRAINE, TAILLE, photos) == social.generer(GRAINE, TAILLE, photos)
    assert social.generer(GRAINE, TAILLE, photos) != social.generer(GRAINE + 1, TAILLE, photos)
    autres = replace(reglages_publics, base_donnees=tmp_path / "autre" / "public.sqlite3")
    with fabriquer(reglages_publics) as a, fabriquer(autres) as b:
        for langue in LANGUES:
            pages_a, pages_b = parcourir(a, langue), parcourir(b, langue)
            assert pages_a == pages_b, "même graine, mêmes pages, octet pour octet"
    with fabriquer(replace(autres, social_graine=GRAINE + 1)) as c:
        assert c.get("/lab/social/fil").text != pages_a["/lab/social/fil"]


@pytest.mark.parametrize("n", [1, 100])
def test_generateur_partage_les_photos(n):
    univers = social.generer(GRAINE, 120, photos_factices(n))
    assert len(univers.publications) == 120
    assert {p.photo.id for p in univers.publications} == {f"essai-{i:03d}" for i in range(n)}
    assert len({p.identifiant for p in univers.publications}) == 120
    for p in univers.publications:
        assert re.fullmatch(r"[a-z0-9]+", p.identifiant)
        assert all(re.fullmatch(r"[a-z0-9-]+", e) for e in p.etiquettes), p.etiquettes
    for a in univers.auteurs:
        assert re.fullmatch(r"[a-z0-9._]+", a.pseudonyme)
        assert any(p.auteur == a.pseudonyme for p in univers.publications), "chaque auteur a publié"


@pytest.mark.parametrize("taille", [1, 2, 7])
def test_generateur_petite_taille(taille, reglages_publics):
    univers = social.generer(GRAINE, taille, photos_factices(3))
    assert len(univers.publications) == taille
    with fabriquer(replace(reglages_publics, social_taille=taille)) as c:
        assert {type_de_page(ch) for ch in parcourir(c)} == set(TYPES_DE_PAGE)


@pytest.mark.parametrize("langue", list(LANGUES))
def test_aucune_marque_ni_adresse_ni_vraie_personne(client, langue):
    univers = social.generer(GRAINE, TAILLE, social.charger_photos(social.DOSSIER_PHOTOS))
    for auteur in univers.auteurs:
        assert (auteur.pseudonyme, auteur.nom) in social.AUTEURS, "les auteurs viennent d'une liste fixe, relue"
    for chemin, html in parcourir(client, langue).items():
        texte = " ".join(Selector(html).xpath("//body//text()").getall())
        assert not COURRIEL.search(texte), chemin
        if type_de_page(chemin) == "credits":
            continue  # les crédits citent de vrais auteurs et les titres d'origine (« Apple-tree blossoms… »)
        for marque in MARQUES:
            assert not re.search(rf"\b{marque}\b", texte, re.I), f"{chemin} : {marque}"
    for _, nom in social.AUTEURS:
        assert len(nom.split()) != 2 or nom.split()[1][0].islower(), f"« {nom} » ressemble à un prénom et un nom"


def test_pages_traduites(client):
    fr = client.get("/lab/social/fil", headers={"Accept-Language": LANGUES["fr"]}).text
    en = client.get("/lab/social/fil", headers={"Accept-Language": LANGUES["en"]}).text
    assert "Voir plus" in fr and "Voir plus" not in en
    assert "See more" in en and "See more" not in fr
    assert '<html lang="fr">' in client.get("/lab/social/fil").text, "français par défaut"


@pytest.mark.parametrize(
    "entete, attendue",
    [
        ("", "fr"),
        ("en-US,en;q=0.9", "en"),
        ("en", "en"),
        ("fr-FR,fr;q=0.9,en;q=0.8", "fr"),
        ("de-DE,de;q=0.9,en;q=0.5,fr;q=0.8", "fr"),
        ("de-DE,en-GB;q=0.7", "en"),
        ("en;q=0, fr;q=0.1", "fr"),
        ("es, it", "fr"),
        ("en;q=abc", "fr"),
        ("*", "fr"),
    ],
)
def test_langue_lue_dans_accept_language(entete, attendue):
    class Requete:
        headers = {"accept-language": entete} if entete else {}

    assert langue_de(Requete()) == attendue


def test_reglages_du_reseau_social(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "_charger_env", lambda *a, **k: None)
    for variable in [v for v in __import__("os").environ if v.startswith("SHADOWLAB_")]:
        monkeypatch.delenv(variable)
    monkeypatch.setenv("SHADOWLAB_SORTIES", str(tmp_path))
    publics = charger_public()
    assert (publics.social_graine, publics.social_taille) == (20261113, 120)
    monkeypatch.setenv("SHADOWLAB_PUBLIC_SOCIAL_GRAINE", "7")
    monkeypatch.setenv("SHADOWLAB_PUBLIC_SOCIAL_TAILLE", "0")
    publics = charger_public()
    assert (publics.social_graine, publics.social_taille) == (7, 1), "au moins une publication"


# --- Plafonds d'une session : combien de pages tient-elle ? ----------------------------------------


def test_plafonds_laissent_parcourir_150_pages(client):
    """Calculé à partir du HTML, sans cache du navigateur (le pire cas) : la page, ses requêtes `/lab/` (photos,
    observateur, BotD) et les deux envois de l'observateur à `/lab/collecte` (empreinte, comportement)."""
    limites = Limites()
    commencer(client)
    par_type: dict[str, int] = {}
    for chemin, html in parcourir(client).items():
        n = 1 + len(requetes_notees(html)) + 2
        par_type[type_de_page(chemin)] = max(par_type.get(type_de_page(chemin), 0), n)
    assert set(par_type) == set(TYPES_DE_PAGE)
    pire = max(par_type.values())
    assert 150 * pire <= limites.requetes_par_session, par_type
    assert limites.envois_par_session // 2 >= 150, "deux envois de l'observateur par page"


# --- Le labo n'a pas changé -----------------------------------------------------------------------


def test_application_du_labo_inchangee():
    contenu = (RACINE / "src" / "shadowlab" / "site" / "app.py").read_bytes()
    assert hashlib.sha256(contenu).hexdigest() == EMPREINTE_SITE_APP


# --- Rejeu : une session faite sur ces pages se relit ----------------------------------------------

T0 = datetime(2026, 11, 13, 20, 0, tzinfo=UTC)
DUREES_S = (14, 31, 9, 22, 45, 12, 27, 18)  # temps passé sur chaque page, varié comme chez un humain


def instant(secondes: float) -> str:
    return (T0 + timedelta(seconds=secondes)).isoformat(timespec="milliseconds")


def entetes_de_chrome(nature: str, referent: str | None) -> list[list[str]]:
    """En-têtes d'un Chrome 142 sous macOS selon la nature de la requête, gardés comme `donnees.entetes_gardes`."""
    paires = [
        ("host", HOTE),
        ("sec-ch-ua", '"Chromium";v="142", "Google Chrome";v="142", "Not_A Brand";v="99"'),
        ("sec-ch-ua-mobile", "?0"),
        ("sec-ch-ua-platform", '"macOS"'),
    ]
    if nature == "page":
        paires += [("upgrade-insecure-requests", "1"), ("user-agent", UA)]
        paires.append(
            ("accept", "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8")
        )
        paires += [("sec-fetch-site", "same-origin" if referent else "none"), ("sec-fetch-mode", "navigate")]
        paires += [("sec-fetch-user", "?1"), ("sec-fetch-dest", "document")]
    elif nature == "image":
        paires += [("user-agent", UA), ("accept", "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8")]
        paires += [("sec-fetch-site", "same-origin"), ("sec-fetch-mode", "no-cors"), ("sec-fetch-dest", "image")]
    elif nature == "style":
        paires += [("user-agent", UA), ("accept", "text/css,*/*;q=0.1")]
        paires += [("sec-fetch-site", "same-origin"), ("sec-fetch-mode", "no-cors"), ("sec-fetch-dest", "style")]
    elif nature == "script":
        paires += [("origin", ORIGINE), ("user-agent", UA), ("accept", "*/*")]
        paires += [("sec-fetch-site", "same-origin"), ("sec-fetch-mode", "cors"), ("sec-fetch-dest", "script")]
    else:  # envoi de l'observateur ou appel JSON de la page
        paires += [("origin", ORIGINE), ("user-agent", UA), ("content-type", "application/json"), ("accept", "*/*")]
        paires += [("sec-fetch-site", "same-origin"), ("sec-fetch-mode", "cors"), ("sec-fetch-dest", "empty")]
    if referent:
        paires.append(("referer", f"{ORIGINE}{referent}"))
    paires += [("accept-encoding", "gzip, deflate, br, zstd"), ("accept-language", "fr-FR,fr;q=0.9,en;q=0.8")]
    return donnees.entetes_gardes(paires, HOTE)


def nature_de(chemin: str) -> str:
    if chemin.endswith(".css"):
        return "style"
    if chemin.endswith(".js"):
        return "script"
    if "/photos/" in chemin:
        return "image"
    return "envoi"


def fabriquer_session(chemin_base: Path, visites: list[tuple[str, list[str]]]) -> str:
    """Une session humaine dans une base publique, notée comme le fait l'application (chemin sans paramètres,
    aucun cookie), avec le rythme d'une personne : chaque page, ses requêtes juste derrière (rafale de photos),
    l'empreinte une seconde après, le relevé de comportement à la sortie."""
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
        comportement = {**COMPORTEMENT_HUMAIN, "duree_page_ms": duree * 1000, "page_defilable": True}
        message(t + duree, "comportement", chemin, comportement)
        precedente, t = chemin, t + duree + 0.4
    cx.close()
    return jeton


def visites_sociales(client: TestClient) -> list[tuple[str, list[str]]]:
    """Fil, publication, profil, étiquette, explorer, autre publication, fil page 2 : la forme réelle des pages,
    lue pendant une session (observateur compris)."""
    fil = Selector(client.get("/lab/social/fil").text)
    publication = fil.css('a[href^="/lab/social/p/"]::attr(href)').get()
    page = Selector(client.get(publication).text)
    profil = page.css('a[href^="/lab/social/u/"]::attr(href)').get()
    etiquette = page.css('a[href^="/lab/social/t/"]::attr(href)').get()
    explorer = Selector(client.get("/lab/social/explorer").text)
    autre = [h for h in explorer.css('a[href^="/lab/social/p/"]::attr(href)').getall() if h != publication][0]
    chemins = [
        "/lab/social/fil",
        publication,
        profil,
        etiquette,
        "/lab/social/explorer",
        autre,
        "/lab/social/fil?page=2",
    ]
    return [(c, requetes_notees(client.get(c).text)) for c in chemins]


def visites_vitrine(client: TestClient) -> list[tuple[str, list[str]]]:
    """Témoin : la même promenade sur la vitrine publique (photos SVG, feuille, script et appel « similaires »)."""
    chemins = ["/lab/vitrine", "/lab/vitrine/annonces", "/lab/vitrine/annonces/AN-000003", "/lab/vitrine/annonces"]
    chemins += ["/lab/vitrine/annonces?page=2", "/lab/vitrine/annonces/AN-000025", "/lab/vitrine"]
    visites = []
    for chemin in chemins:
        html = client.get(chemin).text
        ressources = requetes_notees(html)
        api = Selector(html).css("#similaires::attr(data-url)").get()
        if api:
            ressources += [api] + [a["photo"] for a in client.get(api).json()["annonces"]]
        visites.append((chemin, ressources))
    return visites


def rejouer_base(chemin_base: Path) -> tuple[dict, list, list]:
    cx = rejeu.ouvrir_publique(chemin_base)
    try:
        resultat = rejeu.rejouer(cx, publique=True)
        jeton = resultat["detail"][0]["jeton"]
        http, js = db.observations(cx, jeton)
    finally:
        cx.close()
    return resultat, [dict(o) for o in http], [dict(o) for o in js]


@pytest.fixture
def sessions_rejouees(client, tmp_path):
    """La session du réseau social et son témoin vitrine, chacun dans sa base publique, rejoués."""
    commencer(client)
    sociale = rejouer_base_de(tmp_path / "social" / "public.sqlite3", visites_sociales(client))
    temoin = rejouer_base_de(tmp_path / "vitrine" / "public.sqlite3", visites_vitrine(client))
    return sociale, temoin


def rejouer_base_de(chemin: Path, visites: list[tuple[str, list[str]]]) -> dict:
    fabriquer_session(chemin, visites)
    resultat, http, js = rejouer_base(chemin)
    pages = [page.split("?")[0] for page, _ in visites]
    ressources = sorted({r for _, liste in visites for r in liste})
    return {"resultat": resultat, "http": http, "js": js, "pages": pages, "ressources": ressources}


def test_rejeu_lit_une_session_du_reseau_social(sessions_rejouees):
    sociale, _ = sessions_rejouees
    resultat = sociale["resultat"]
    assert resultat["base"] == "publique"
    assert resultat["sessions"] == {"total": 1, "rejouees": 1, "inutilisables": 0}
    assert {n["niveau"] for n in resultat["niveaux"]} == set(profils.charger().codes)
    chemins = [o["path"] for o in sociale["http"]]
    assert set(sociale["pages"]) | set(sociale["ressources"]) <= set(chemins)
    assert any(r.startswith("/lab/social/photos/") for r in sociale["ressources"])
    observations = Observations(http=sociale["http"], js=sociale["js"])
    documents = [o["path"] for o in observations.documents]
    for page in sociale["pages"]:
        assert page in documents, f"la page {page} est prise comme une page"
    moments = [m for m, _, _ in rejeu._moments(sociale["http"], sociale["js"]) if m["type"] == "page"]
    assert [m["chemin"] for m in moments if not m["chemin"].startswith("/lab/social/photos/")] == sociale["pages"]
    assert {o["path"] for o in observations.ressources} == {
        "/lab/static/observateur.js",
        "/lab/static/vendor/botd-2.0.0.esm.js",
    }


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Défaut connu, hors du périmètre de ce squelette (rejeu.py et detection.py ne se touchent pas ici) : "
        "`Observations.documents` prend tout chemin `/lab/` hors CHEMINS_TECHNIQUES, donc chaque photo "
        "`/lab/social/photos/…` (comme `/lab/vitrine/photos/…`) compte comme une page pour `rythme_soutenu` et "
        "`navigation_lineaire`, n'est pas une ressource (`ressources` ne lit que `/lab/static`), et "
        "`gardien.protegee` en fait un moment de contrôle de page au rejeu."
    ),
)
def test_rejeu_prend_les_photos_pour_des_ressources(sessions_rejouees):
    sociale, _ = sessions_rejouees
    observations = Observations(http=sociale["http"], js=sociale["js"])
    photos = {r for r in sociale["ressources"] if "/photos/" in r}
    assert not photos & {o["path"] for o in observations.documents}, "une photo n'est pas une page"
    assert photos <= {o["path"] for o in observations.ressources}, "une photo est une ressource"
    assert not any(gardien.protegee(p, "GET") for p in photos), "une photo n'est pas un moment de contrôle"


def verdicts(resultat: dict) -> dict[str, tuple[bool, list[str]]]:
    session = resultat["detail"][0]
    return {
        code: (v["arretee"], sorted(c for codes in v["classes"].values() for c in codes))
        for code, v in session["niveaux"].items()
    }


def test_rejeu_session_sociale_comme_le_temoin_vitrine(sessions_rejouees):
    """Même personne (empreinte, comportement, rythme), deux sites : la forme du réseau social ne doit faire arrêter
    la session à aucun niveau où le témoin passe."""
    sociale, temoin = sessions_rejouees
    v_sociale, v_temoin = verdicts(sociale["resultat"]), verdicts(temoin["resultat"])
    for code in v_temoin:
        if not v_temoin[code][0]:
            assert not v_sociale[code][0], f"niveau {code} : {v_sociale[code]} (témoin : {v_temoin[code]})"


def test_rejeu_sans_photos_la_meme_personne_passe_partout(client, tmp_path):
    """Contrôle de la cause : la même session sociale, privée de ses requêtes de photos, n'est arrêtée nulle part."""
    commencer(client)
    visites = [(page, [r for r in ressources if "/photos/" not in r]) for page, ressources in visites_sociales(client)]
    session = rejouer_base_de(tmp_path / "sans-photos" / "public.sqlite3", visites)
    assert not any(arretee for arretee, _ in verdicts(session["resultat"]).values())


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Défaut connu, mesuré le 13/11 et hors du périmètre de ce squelette : aux niveaux 06 et 07, la session est "
        "arrêtée à la première empreinte par le score composite, signal `rythme_soutenu` seul (0,5 ≥ seuil 0,5 au "
        "06 et 0,3 au 07). Les photos comptant comme des pages (`Observations.documents`), la page et ses photos "
        "chargées dans la même seconde font plus de 4 « pages » par seconde. Deux photos par page suffisent ; une "
        "seule, ou aucune, et la session passe partout. Le témoin vitrine (photos SVG) est arrêté de la même façon."
    ),
)
def test_rejeu_aucun_niveau_n_arrete_la_session_sociale(sessions_rejouees):
    sociale, _ = sessions_rejouees
    arrets = {code: v for code, v in verdicts(sociale["resultat"]).items() if v[0]}
    assert not arrets, arrets
