"""Site vitrine à contenu connu : génération déterministe, parcours complet = vérité à 100 %."""

import json
import re
from dataclasses import asdict, replace

import pytest
from parsel import Selector

from shadowlab.site import vitrine

TAILLE = 45
GRAINE = 20261111
CHAMPS = [
    "reference",
    "titre",
    "type_bien",
    "ville",
    "code_postal",
    "surface",
    "pieces",
    "prix",
    "dpe",
    "description",
    "date_publication",
    "nb_photos",
    "agence",
    "telephone",
]


# --- Génération --------------------------------------------------------------------------------


def test_meme_graine_memes_annonces():
    assert vitrine.generer(GRAINE, 60) == vitrine.generer(GRAINE, 60)


def test_graine_differente_annonces_differentes():
    assert vitrine.generer(1, 30) != vitrine.generer(2, 30)


def test_taille_respectee_et_references_uniques():
    for taille in (1, 45, 500):
        annonces = vitrine.generer(GRAINE, taille)
        assert len(annonces) == taille
        refs = [a.reference for a in annonces]
        assert len(set(refs)) == taille
    assert vitrine.generer(GRAINE, 3)[0].reference == "AN-000001"
    assert vitrine.generer(GRAINE, 3)[2].reference == "AN-000003"


def test_valeurs_plausibles_et_fictives():
    for a in vitrine.generer(GRAINE, 300):
        assert 9 <= a.surface <= 400
        assert 1 <= a.pieces <= 10
        assert 10_000 <= a.prix <= 5_000_000
        assert a.dpe in "ABCDEFG" and len(a.dpe) == 1
        assert re.fullmatch(r"\d{5}", a.code_postal)
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", a.date_publication)
        assert 3 <= a.nb_photos <= 6
        assert re.fullmatch(r"01 99 00 \d\d \d\d", a.telephone)
        assert a.titre and a.description and a.agence and a.ville and a.type_bien


def test_verite_coherente_avec_generer():
    v = vitrine.verite(GRAINE, TAILLE)
    json.dumps(v)  # sérialisable
    assert v["graine"] == GRAINE and v["taille"] == TAILLE
    assert v["par_page"] == 20 and v["nb_pages"] == 3
    assert v["annonces"] == [asdict(a) for a in vitrine.generer(GRAINE, TAILLE)]
    assert vitrine.verite(GRAINE, 40)["nb_pages"] == 2


# --- Site --------------------------------------------------------------------------------------


@pytest.fixture
def client_vitrine(reglages, monkeypatch):
    monkeypatch.setenv("SHADOWLAB_VITRINE_TAILLE", str(TAILLE))
    monkeypatch.setenv("SHADOWLAB_VITRINE_GRAINE", str(GRAINE))
    from fastapi.testclient import TestClient

    from shadowlab.config import charger
    from shadowlab.site.app import creer_app

    with TestClient(creer_app(charger()), base_url="http://127.0.0.1") as c:
        yield c


def lire_fiche(html: str) -> dict:
    sel = Selector(html)
    donnees = {}
    for champ in CHAMPS:
        noeud = sel.css(f'[data-champ="{champ}"]')
        assert len(noeud) == 1, champ
        donnees[champ] = noeud[0].attrib.get("data-valeur", noeud.css("::text").get() or "")
    for champ in ("surface", "pieces", "prix", "nb_photos"):
        donnees[champ] = int(donnees[champ])
    return donnees


def test_parcours_complet_egale_la_verite(client_vitrine):
    liens = []
    url = "/lab/vitrine/annonces"
    pages_vues = 0
    while url:
        r = client_vitrine.get(url)
        assert r.status_code == 200
        pages_vues += 1
        sel = Selector(r.text)
        liens += sel.css("a.fiche::attr(href)").getall()
        suivante = sel.css('a[rel="next"]::attr(href)').get()
        url = suivante
    verite = vitrine.verite(GRAINE, TAILLE)
    assert pages_vues == verite["nb_pages"]
    assert len(liens) == len(set(liens)) == TAILLE

    recolte = []
    for lien in liens:
        r = client_vitrine.get(lien)
        assert r.status_code == 200
        recolte.append(lire_fiche(r.text))
    assert sorted(recolte, key=lambda a: a["reference"]) == verite["annonces"]


def test_liste_precedente_et_hors_bornes(client_vitrine):
    sel = Selector(client_vitrine.get("/lab/vitrine/annonces?page=2").text)
    assert sel.css('a[rel="prev"]::attr(href)').get()
    assert sel.css('a[rel="next"]::attr(href)').get()
    assert not Selector(client_vitrine.get("/lab/vitrine/annonces?page=1").text).css('a[rel="prev"]')
    assert client_vitrine.get("/lab/vitrine/annonces?page=3").status_code == 200
    assert not Selector(client_vitrine.get("/lab/vitrine/annonces?page=3").text).css('a[rel="next"]')
    for page in (0, 4, -1):
        assert client_vitrine.get(f"/lab/vitrine/annonces?page={page}").status_code == 404


def test_accueil_a_la_une(client_vitrine):
    r = client_vitrine.get("/lab/vitrine")
    assert r.status_code == 200
    sel = Selector(r.text)
    assert sel.css("a.fiche")
    assert sel.css('a[href="/lab/vitrine/annonces"]')
    assert "Site de démonstration — annonces fictives" in r.text


def test_similaires_absent_du_html_et_servi_par_l_api(client_vitrine):
    ref = vitrine.generer(GRAINE, TAILLE)[0].reference
    html = client_vitrine.get(f"/lab/vitrine/annonces/{ref}").text
    similaires = client_vitrine.get(f"/lab/vitrine/api/annonces/{ref}/similaires")
    assert similaires.status_code == 200
    donnees = similaires.json()
    assert donnees["annonces"] and all(a["reference"] != ref for a in donnees["annonces"])
    for a in donnees["annonces"]:
        assert a["reference"] not in html
        assert a["lien"].startswith("/lab/vitrine/annonces/AN-")
    assert "Annonces similaires" in html  # le conteneur existe, vide
    assert Selector(html).css("#similaires a").getall() == []
    assert Selector(html).css("script[src$='vitrine.js']")


def test_photo_svg(client_vitrine):
    a = vitrine.generer(GRAINE, TAILLE)[0]
    r = client_vitrine.get(f"/lab/vitrine/photos/{a.reference}/1.svg")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/svg+xml")
    assert r.text.lstrip().startswith("<svg") and len(r.content) < 5_000
    assert r.content == client_vitrine.get(f"/lab/vitrine/photos/{a.reference}/1.svg").content
    assert client_vitrine.get(f"/lab/vitrine/photos/{a.reference}/{a.nb_photos + 1}.svg").status_code == 404
    imgs = Selector(client_vitrine.get(f"/lab/vitrine/annonces/{a.reference}").text).css("img::attr(src)").getall()
    assert len(imgs) == a.nb_photos


def test_inconnu_donne_404(client_vitrine):
    assert client_vitrine.get("/lab/vitrine/annonces/AN-999999").status_code == 404
    assert client_vitrine.get("/lab/vitrine/annonces/n-importe-quoi").status_code == 404
    assert client_vitrine.get("/lab/vitrine/photos/AN-999999/1.svg").status_code == 404
    assert client_vitrine.get("/lab/vitrine/api/annonces/AN-999999/similaires").status_code == 404


def test_pages_protegees_comme_le_reste_du_site(client_vitrine):
    r = client_vitrine.get("/lab/vitrine")
    assert "default-src 'self'" in r.headers["content-security-policy"]
    assert 'name="sl-session"' in r.text and "observateur.js" in r.text
    # Aucune requête vers un tiers.
    assert not re.search(r'(?:src|href)="https?://', r.text)


def test_echappement_html():
    a = replace(vitrine.generer(GRAINE, 1)[0], titre="<script>alert(1)</script>", description="a & b <i>")
    page = vitrine.page_fiche("", a)
    assert "<script>alert" not in page and "&lt;script&gt;" in page
    assert "<i>" not in page
    assert Selector(page).css('[data-champ="titre"]::text').get() == "<script>alert(1)</script>"


def test_reglages_par_defaut(reglages):
    assert reglages.vitrine_graine == 20261111
    assert reglages.vitrine_taille == 500


def test_lien_piege_masque_sur_les_pages_vitrine(client_vitrine):
    """Le lien piège ne doit jamais être visible d'un humain, sinon un clic honnête le fait passer pour un bot.

    Il est masqué par la feuille de style : celle des pages vitrine doit donc porter la règle `.sl-hp`.
    """
    page = vitrine.page_liste("", vitrine.generer(GRAINE, TAILLE), 1, honeypot=True)
    sel = Selector(page)
    assert sel.css("a.sl-hp"), "le lien piège doit être présent quand les honeypots sont actifs"
    css = "".join(client_vitrine.get(href).text for href in sel.css('link[rel="stylesheet"]::attr(href)').getall())
    regle = re.search(r"\.sl-hp\s*\{([^}]*)\}", css)
    assert regle, "aucune règle .sl-hp dans les feuilles de style de la page"
    assert "position: absolute" in regle.group(1) and "-9999px" in regle.group(1)


def test_marque_clairement_fictive():
    """Le site sera public : son nom ne doit pas pouvoir passer pour celui d'une vraie agence."""
    assert "démo" in vitrine.MARQUE.lower()


# --- Illustrations et mise en page de la fiche -------------------------------------------------


def _annonce_de_type(type_bien):
    return replace(vitrine.generer(GRAINE, 1)[0], type_bien=type_bien)


def _rectangles(svg, role):
    """Rectangles (x, y, largeur, hauteur) du dessin qui portent `data-e="<role>"`."""
    rectangles = []
    for balise in re.findall(rf'<rect[^>]*data-e="{role}"[^>]*>', svg):
        v = {cle: float(valeur) for cle, valeur in re.findall(r'\b(x|y|width|height)="([\d.]+)"', balise)}
        rectangles.append((v["x"], v["y"], v["width"], v["height"]))
    return rectangles


def _se_chevauchent(a, b):
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


@pytest.mark.parametrize("type_bien", ["Maison", "Appartement", "Studio", "Loft", "Duplex"])
def test_facade_porte_et_fenetres_ne_se_chevauchent_pas(type_bien):
    svg = vitrine.photo_svg(_annonce_de_type(type_bien), 1)
    portes, fenetres = _rectangles(svg, "porte"), _rectangles(svg, "fenetre")
    assert len(portes) == 1 and len(fenetres) >= 2
    assert not any(_se_chevauchent(portes[0], f) for f in fenetres)
    assert not any(_se_chevauchent(f, g) for i, f in enumerate(fenetres) for g in fenetres[i + 1 :])


def test_illustration_depend_du_bien_et_de_la_vue():
    """Une maison et un appartement n'ont pas la même façade ; les six vues d'un bien diffèrent."""
    maison, appartement = _annonce_de_type("Maison"), _annonce_de_type("Appartement")
    assert vitrine.photo_svg(maison, 1) != vitrine.photo_svg(appartement, 1)
    assert len({vitrine.photo_svg(maison, n) for n in range(1, 7)}) == 6
    for bien in (maison, appartement):
        for n in range(1, 7):
            assert len(vitrine.photo_svg(bien, n).encode()) < 5_000


def test_legende_des_photos():
    assert vitrine.legende_photo(1) == "Façade"
    assert len({vitrine.legende_photo(n) for n in range(1, 7)}) == 6
    page = vitrine.page_fiche("", vitrine.generer(GRAINE, 1)[0])
    assert Selector(page).css(".galerie img::attr(alt)").getall()[0].startswith("Façade")


def test_prix_affiche_avant_la_galerie():
    """Le prix se lit sans faire défiler : il précède la galerie dans la fiche."""
    page = vitrine.page_fiche("", vitrine.generer(GRAINE, 1)[0])
    assert page.index('data-champ="prix"') < page.index('class="galerie"')
