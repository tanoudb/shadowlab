"""Site d'étude « Humain ou robot ? » : le fond de la nouvelle application publique (cadrage du 13/11/2026, v2).

Cadrage : `docs/recherche/site-public-communaute-2026-11-13.md` (« Règles », « Langue », « Textes de l'accueil »).
Étape 1 : deux langues sans cookie de plus. Étape 2 : l'accueil de l'étude et la notice.
"""

from __future__ import annotations

import json
import re
from html import escape
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from parsel import Selector
from test_public import (
    CONTACT,
    HOTE,
    OBSERVATEUR,
    ORIGINE,
    champs_du_formulaire,
    cles_collectees,
    fabriquer,
    ouvrir,
)

from shadowlab.config import ReglagesPublics
from shadowlab.public.social import MARQUE as MARQUE_SOCIAL

ACCEPT = {"fr": "fr-FR,fr;q=0.9", "en": "en-US,en;q=0.9"}
AUTRE = {"fr": "en", "en": "fr"}
COOKIES = {"__Host-slp-csrf", "__Host-slp-session", "__Host-slp-droits"}
# Mots de l'interface propres à une langue : aucun ne doit paraître sur une page de l'autre langue.
MARQUEURS = {
    "fr": (
        "Ma session",
        "Terminer ma session",
        "Supprimer ma session",
        "Revenir",
        "Participer",
        "Commencer",
        "Envoyer",
        "Requête refusée",
        "Votre message",
        "Merci",
        "Aucune session",
    ),
    "en": (
        "My session",
        "End my session",
        "Delete my session",
        "Back to",
        "Take part",
        "Start the session",
        "Send",
        "Request refused",
        "Your message",
        "Thank you",
        "No session",
    ),
}


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


def langue_html(html: str) -> str | None:
    return Selector(html).css("html::attr(lang)").get()


def accueil(langue: str | None = None) -> str:
    return f"/{langue}" if langue else "/"


def commencer_depuis(client: TestClient, langue: str, navigateur: str | None = None, adresse: str = "203.0.113.7"):
    """« Commencer » depuis l'accueil `/{langue}`, comme un navigateur : champs du formulaire lus dans la page."""
    entetes = {"Accept-Language": ACCEPT[navigateur]} if navigateur else {}
    page = client.get(accueil(langue), headers=entetes)
    assert page.status_code == 200, page.text[:200]
    champs = champs_du_formulaire(page.text, "/session/commencer")
    return client.post(
        "/session/commencer",
        data={**champs, "consentement": "oui"},
        headers={"Origin": ORIGINE, "X-Forwarded-For": adresse, **entetes},
        follow_redirects=False,
    )


def jeton_de_session(client: TestClient) -> str:
    jeton = Selector(client.get("/lab/vitrine").text).css('meta[name="sl-session"]::attr(content)').get()
    assert jeton
    return jeton


def accord_de(reglages: ReglagesPublics, jeton: str) -> dict:
    cx = ouvrir(reglages)
    try:
        ligne = cx.execute("SELECT protection_config FROM runs WHERE session_token = ?", (jeton,)).fetchone()
    finally:
        cx.close()
    return json.loads(ligne[0])


def bandeau_de(html: str) -> str:
    return Selector(html).css("aside.session-publique").get() or ""


def sans_mots_de_l_autre_langue(texte: str, langue: str, ou: str) -> None:
    for mot in MARQUEURS[AUTRE[langue]]:
        assert mot not in texte, f"{ou} ({langue}) : « {mot} »"


# === Étape 1 : deux langues, sans cookie de plus ====================================================


@pytest.mark.parametrize(
    "chemin, navigateur, attendue",
    [
        ("/fr", "en", "fr"),
        ("/en", "fr", "en"),
        ("/en", None, "en"),
        ("/", "en", "en"),
        ("/", "fr", "fr"),
        ("/", None, "fr"),
    ],
)
def test_langue_par_le_prefixe_puis_le_navigateur(client, chemin, navigateur, attendue):
    entetes = {"Accept-Language": ACCEPT[navigateur]} if navigateur else {}
    r = client.get(chemin, headers=entetes)
    assert r.status_code == 200
    assert langue_html(r.text) == attendue


@pytest.mark.parametrize("chemin", ["/de", "/fr/", "/en/", "/EN", "/english", "/fr-FR"])
def test_prefixe_inconnu_ou_barre_finale(client, chemin):
    r = client.get(chemin, follow_redirects=False)
    assert r.status_code == 404 and "location" not in r.headers


def test_langue_de_suit_l_ordre_du_cadrage():
    """Préfixe de l'adresse ; sinon langue de la session ; sinon `Accept-Language` ; sinon français."""
    from shadowlab.public.app import langue_de

    def requete(chemin: str, session: str | None, navigateur: str = ""):
        return SimpleNamespace(
            url=SimpleNamespace(path=chemin),
            state=SimpleNamespace(langue_session=session),
            headers={"accept-language": navigateur} if navigateur else {},
        )

    assert langue_de(requete("/en", "fr", "fr")) == "en"
    assert langue_de(requete("/fr", "en", "en")) == "fr"
    assert langue_de(requete("/fr/information", "en", "en")) == "fr"
    assert langue_de(requete("/lab/social/fil", "en", "fr")) == "en", "la session avant le navigateur"
    assert langue_de(requete("/lab/social/fil", None, "en")) == "en"
    assert langue_de(requete("/lab/social/fil", None)) == "fr"
    assert langue_de(requete("/english", None)) == "fr", "« /english » n'est pas le préfixe « /en »"
    assert langue_de(requete("/session", "de", "en")) == "en", "une langue de session inconnue est ignorée"


@pytest.mark.parametrize("langue", ["fr", "en"])
def test_langue_notee_avec_l_accord(client, reglages_publics, langue):
    """Le formulaire de l'accueil porte sa langue : elle est notée avec l'accord, même si le navigateur en préfère
    une autre."""
    r = commencer_depuis(client, langue, navigateur=AUTRE[langue])
    assert r.status_code == 303
    accord = accord_de(reglages_publics, jeton_de_session(client))
    assert accord["langue"] == langue
    assert accord["texte_information"] and accord["conservation_jours"] == 90


@pytest.mark.parametrize("champ, navigateur, attendue", [(None, "en", "en"), ("de", "en", "en"), (None, None, "fr")])
def test_langue_de_l_accord_sans_champ_valide(client, reglages_publics, champ, navigateur, attendue):
    """Sans champ `langue` (ou avec une valeur inconnue), la langue notée est celle de la requête."""
    page = client.get("/")
    champs = {k: v for k, v in champs_du_formulaire(page.text, "/session/commencer").items() if k != "langue"}
    if champ:
        champs["langue"] = champ
    entetes = {"Accept-Language": ACCEPT[navigateur]} if navigateur else {}
    r = client.post(
        "/session/commencer",
        data={**champs, "consentement": "oui"},
        headers={"Origin": ORIGINE, **entetes},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert accord_de(reglages_publics, jeton_de_session(client))["langue"] == attendue


def test_langue_de_la_session_avant_celle_du_navigateur(client):
    assert commencer_depuis(client, "en", navigateur="fr").status_code == 303
    francais = {"Accept-Language": ACCEPT["fr"]}
    assert langue_html(client.get("/lab/social/fil", headers=francais).text) == "en"
    assert langue_html(client.get("/session", headers=francais).text) == "en"
    assert langue_html(client.get("/contact", headers=francais).text) == "en"
    bandeau = bandeau_de(client.get("/lab/vitrine", headers=francais).text)
    assert "End my session" in bandeau and "Terminer ma session" not in bandeau
    assert langue_html(client.get("/fr", headers=francais).text) == "fr", "le préfixe passe avant la session"


def parcours_complet(client: TestClient, langue: str) -> dict[str, str]:
    """Toutes les pages de l'application publique, dans une langue : chemin → HTML. Hors session avec la langue du
    navigateur, puis une session commencée depuis `/{langue}` (navigateur réglé sur l'autre langue)."""
    entetes = {"Accept-Language": ACCEPT[langue]}
    pages = {
        "accueil": client.get(accueil(langue), headers={"Accept-Language": ACCEPT[AUTRE[langue]]}).text,
        "racine": client.get("/", headers=entetes).text,
        "aucune-session": client.get("/session", headers=entetes).text,
        "contact": client.get("/contact", headers=entetes).text,
        "contact-envoye": client.get("/contact/envoye", headers=entetes).text,
        "vitrine-hors-session": bandeau_de(client.get("/lab/vitrine", headers=entetes).text),
    }
    refus = client.post("/session/commencer", data={}, headers={"Origin": "https://ailleurs.example", **entetes})
    assert refus.status_code == 403
    pages["erreur"] = refus.text
    champs = champs_du_formulaire(pages["contact"], "/contact")
    vide = client.post("/contact", data={**champs, "message": "  "}, headers={"Origin": ORIGINE, **entetes})
    assert vide.status_code == 422
    pages["contact-refus"] = vide.text

    assert commencer_depuis(client, langue, navigateur=AUTRE[langue]).status_code == 303
    autre = {"Accept-Language": ACCEPT[AUTRE[langue]]}
    pages["ma-session"] = client.get("/session", headers=autre).text
    pages["vitrine-en-session"] = bandeau_de(client.get("/lab/vitrine", headers=autre).text)
    pages["accueil-en-session"] = client.get("/", headers=autre).text
    champs = champs_du_formulaire(pages["ma-session"], "/session/terminer")
    merci = client.post("/session/terminer", data=champs, headers={"Origin": ORIGINE, **autre})
    assert merci.status_code == 200
    pages["merci"] = merci.text
    champs = champs_du_formulaire(merci.text, "/session/supprimer")
    supprimee = client.post("/session/supprimer", data=champs, headers={"Origin": ORIGINE, **autre})
    assert supprimee.status_code == 200
    pages["supprimee"] = supprimee.text
    return pages


@pytest.mark.parametrize("langue", ["fr", "en"])
def test_pages_publiques_dans_les_deux_langues(client, langue):
    for nom, html in parcours_complet(client, langue).items():
        if nom.startswith("vitrine"):
            assert html, f"{nom} : bandeau absent"
        else:
            assert langue_html(html) == langue, nom
        sans_mots_de_l_autre_langue(html, langue, nom)


def test_bandeau_de_la_vitrine_dans_les_deux_langues(client):
    fr = bandeau_de(client.get("/lab/vitrine", headers={"Accept-Language": ACCEPT["fr"]}).text)
    en = bandeau_de(client.get("/lab/vitrine", headers={"Accept-Language": ACCEPT["en"]}).text)
    assert "Vous visitez sans participer" in fr and "without taking part" in en
    for bandeau in (fr, en):
        assert Selector(bandeau).css('a[href="/"]') and Selector(bandeau).css('a[href="/lab/social/fil"]')


def test_liste_des_donnees_dans_les_deux_langues_tiree_de_l_observateur():
    """Même liste de clés, dans le même ordre, dans les deux langues ; chaque description est traduite."""
    from shadowlab.public.pages import RELEVES

    empreinte, comportement = cles_collectees(OBSERVATEUR.read_text(encoding="utf-8"))
    assert set(RELEVES) == {"fr", "en"}
    for langue, (relevees, comport) in RELEVES.items():
        assert {cle for cle, _ in relevees} == empreinte, langue
        assert {cle for cle, _ in comport} == comportement, langue
        assert [c for c, _ in relevees] == [c for c, _ in RELEVES["fr"][0]], "même ordre"
        assert all(texte.strip() for _, texte in relevees + comport), langue
    francais = dict(RELEVES["fr"][0] + RELEVES["fr"][1])
    for cle, texte in RELEVES["en"][0] + RELEVES["en"][1]:
        assert texte != francais[cle], f"{cle} : description non traduite"


def notice(client: TestClient, langue: str) -> str:
    """La notice complète dans une langue, à son adresse (étape 2)."""
    r = client.get(f"/{langue}/information")
    assert r.status_code == 200
    return r.text


@pytest.mark.parametrize("langue", ["fr", "en"])
def test_notice_complete_dans_chaque_langue(client, langue):
    from shadowlab.public.donnees import ENTETES_GARDES
    from shadowlab.public.pages import RELEVES

    texte = notice(client, langue)
    relevees, comport = RELEVES[langue]
    for cle, description in relevees + comport:
        assert f"<code>{cle}</code>" in texte and escape(description) in texte, cle
    for entete in ENTETES_GARDES:
        assert entete in texte, entete
    for cookie in ("slp-csrf", "slp-session", "slp-droits"):
        assert f"<code>{cookie}</code>" in texte, cookie
    assert escape(CONTACT) in texte
    assert ("90 jours" if langue == "fr" else "90 days") in texte
    assert "CNIL" in texte


def squelette(html: str) -> list[tuple[str, str]]:
    """Suite des éléments du contenu principal : balise et classe, sans le texte."""
    return [(e.root.tag, e.attrib.get("class", "")) for e in Selector(html).css("main *")]


def test_notices_de_meme_structure(client):
    """Phrase pour phrase : mêmes sections, mêmes paragraphes, mêmes éléments de liste, mêmes codes."""
    fr, en = notice(client, "fr"), notice(client, "en")
    assert squelette(fr) == squelette(en)
    for balise in ("h2", "p", "li", "code", "dt", "dd"):
        assert len(Selector(fr).css(f"main {balise}")) == len(Selector(en).css(f"main {balise}")), balise


def test_toujours_exactement_trois_cookies(reglages_publics):
    """Les deux langues, tout le parcours : jamais d'autre cookie que les trois de la notice."""
    poses: set[str] = set()
    for langue in ("fr", "en"):
        with fabriquer(reglages_publics) as c:
            original = c.request

            def espion(*args, _original=original, **kwargs):
                reponse = _original(*args, **kwargs)
                for precedente in [*reponse.history, reponse]:
                    poses.update(e.split("=", 1)[0] for e in precedente.headers.get_list("set-cookie"))
                return reponse

            c.request = espion
            parcours_complet(c, langue)
            fil = c.get("/lab/social/fil")
            assert fil.status_code == 200
            assert {k.name for k in c.cookies.jar} <= COOKIES
    assert poses == COOKIES


# === Étape 2 : l'accueil de l'étude et la notice =====================================================

PUBLIC_CSS = Path(__file__).parents[1] / "src" / "shadowlab" / "public" / "static" / "public.css"
# Textes du cadrage (« Textes de l'accueil »), mot pour mot.
TEXTES_ACCUEIL = {
    "fr": (
        "Humain ou robot ?",
        "Une étude ouverte sur la façon dont de vraies personnes naviguent sur le Web.",
        "Les sites se protègent des robots avec des détecteurs. Ces détecteurs se trompent parfois et prennent de "
        "vraies personnes pour des robots. Aidez-nous à les améliorer : promenez-vous 5 à 10 minutes sur un faux "
        "réseau social de photos, comme vous le feriez sur un vrai.",
    ),
    "en": (
        "Human or bot?",
        "An open study of how real people browse the web.",
        "Websites use detectors to keep bots out. Those detectors sometimes get it wrong and flag real people. Help "
        "us make them better: spend 5 to 10 minutes browsing a fake photo-sharing network, the way you would browse "
        "a real one.",
    ),
}
LIEN_HABITAT = {
    "fr": "un second site de démonstration, des annonces fictives",
    "en": "a second demonstration site, with fictional listings",
}
BUT = {
    "fr": ("mesurer et améliorer nos détecteurs de robots", "ne servent à rien d'autre"),
    "en": ("measure and improve our bot detectors", "used for nothing else"),
}
# Classes stables, pour le dessin à venir.
CLASSES_ACCUEIL = (
    "accueil",
    "accueil-entete",
    "accueil-titre",
    "accueil-sous-titre",
    "accueil-accroche",
    "accueil-etapes",
    "etapes",
    "etape",
    "accueil-releve",
    "releve-franchise",
    "releve-oui",
    "releve-non",
    "accueil-but",
    "accueil-sites",
    "site-vedette",
    "site-second",
    "fictif",
    "accord",
    "accord-notice",
    "accord-case",
    "lien-notice",
    "bouton-principal",
    "visiter-sans-participer",
    "autre-langue",
)
CLASSES_NOTICE = ("notice", "notice-chapeau", "notice-section", "notice-retour", "autre-langue", "donnees")


def texte_de(html: str | None, css: str | None = "main") -> str:
    """Texte visible d'une page (ou d'un fragment, `css=None`), espaces normalisées."""
    sel = Selector(html or "<p></p>")
    noeuds = sel.css(css) if css else sel
    return " ".join(" ".join(noeuds.xpath(".//text()").getall()).split())


def classes_de(html: str) -> set[str]:
    return {c for valeur in Selector(html).css("[class]::attr(class)").getall() for c in valeur.split()}


@pytest.mark.parametrize("langue", ["fr", "en"])
def test_accueil_de_l_etude(client, langue):
    html = client.get(f"/{langue}").text
    sel = Selector(html)
    titre, sous_titre, accroche = TEXTES_ACCUEIL[langue]
    assert [texte_de(h, None) for h in sel.css("main h1").getall()] == [titre], "un seul titre de premier niveau"
    assert texte_de(html, ".accueil-sous-titre") == sous_titre
    assert texte_de(html, ".accueil-accroche") == accroche
    etapes = sel.css("main ol.etapes > li.etape")
    assert len(etapes) == 3, "trois étapes « comment ça se passe »"
    assert all(e.css("h3") and e.css("p") for e in etapes)
    for section in sel.css("main section"):
        assert section.css("h2"), "chaque section a son titre"
    assert set(CLASSES_ACCUEIL) <= classes_de(html), set(CLASSES_ACCUEIL) - classes_de(html)
    assert sel.css('link[rel="stylesheet"]::attr(href)').getall() == ["/public/static/public.css"]


@pytest.mark.parametrize("langue", ["fr", "en"])
def test_accueil_resume_du_releve_exact_et_a_un_seul_endroit(client, langue):
    """Le résumé dit ce que relève AUJOURD'HUI observateur.js : des nombres et des délais. Pas la position de la
    souris, pas ce qui est tapé. La phrase du cadrage sur les « mouvements de la souris » attend le second script."""
    from shadowlab.public.pages import RESUME_RELEVE

    html = client.get(f"/{langue}").text
    resume = RESUME_RELEVE[langue]
    assert set(RESUME_RELEVE) == {"fr", "en"} and set(resume) == set(RESUME_RELEVE["fr"])
    assert texte_de(html, ".releve-franchise") == resume["franchise"]
    assert [texte_de(li, None) for li in Selector(html).css(".releve-oui li").getall()] == resume["oui"]
    assert [texte_de(li, None) for li in Selector(html).css(".releve-non li").getall()] == resume["non"]
    annonce = " ".join([resume["franchise"], *resume["oui"]]).lower()
    for futur in ("mouvements de la souris", "mouse movements", "trajectoire", "trajectory", "rythme des clics"):
        assert futur not in annonce, futur
    jamais = " ".join(resume["non"]).lower()
    assert "position" in jamais
    assert ("ce que vous tapez" if langue == "fr" else "what you type") in jamais


@pytest.mark.parametrize("langue", ["fr", "en"])
def test_accueil_presente_mosaik_en_grand_et_habitat_en_lien_discret(client, langue):
    html = client.get(f"/{langue}").text
    sel = Selector(html)
    assert MARQUE_SOCIAL in texte_de(html, ".site-vedette")
    liens = sel.css('.site-second a[href="/lab/vitrine"]').getall()
    assert [texte_de(a, None) for a in liens] == [LIEN_HABITAT[langue]]
    assert ("Tout y est fictif" if langue == "fr" else "Everything there is fictional") in texte_de(html, ".fictif")


@pytest.mark.parametrize("langue", ["fr", "en"])
def test_accueil_accord_notice_a_cote_et_visite_sans_participer(client, langue):
    sel = Selector(client.get(f"/{langue}").text)
    formulaire = sel.css('form.accord[action="/session/commencer"][method="post"]')
    assert formulaire.css('input[type="checkbox"][name="consentement"][value="oui"][required]')
    assert formulaire.css('input[type="hidden"][name="csrf"]')
    assert formulaire.css('input[type="hidden"][name="langue"]::attr(value)').get() == langue
    case = formulaire.css(".accord-case")
    libelle = texte_de(case.get(), "label")
    assert ("J'ai lu la notice complète" if langue == "fr" else "I have read the full notice") in libelle
    assert case.css(f'a.lien-notice[href="/{langue}/information"]'), "la notice juste à côté de la case"
    assert formulaire.css('button[type="submit"]')
    assert sel.css('a.visiter-sans-participer[href="/lab/social/fil"]')
    autre = AUTRE[langue]
    assert sel.css(f'.autre-langue a[href="/{autre}"][hreflang="{autre}"]'), "lien vers l'autre langue"


def test_racine_dans_la_langue_du_navigateur_avec_lien_vers_l_autre(client):
    for langue in ("fr", "en"):
        html = client.get("/", headers={"Accept-Language": ACCEPT[langue]}).text
        assert texte_de(html, "main h1") == TEXTES_ACCUEIL[langue][0]
        assert Selector(html).css(f'.autre-langue a[href="/{AUTRE[langue]}"]')


@pytest.mark.parametrize("langue", ["fr", "en"])
def test_accueil_et_notice_disent_le_but(client, langue):
    mesurer, rien_d_autre = BUT[langue]
    for html in (client.get(f"/{langue}").text, notice(client, langue)):
        texte = texte_de(html)
        assert mesurer in texte and rien_d_autre in texte
    assert "ne servent qu'à ce calcul" not in notice(client, "fr")


def test_commencer_mene_au_reseau_social(client):
    r = commencer_depuis(client, "fr")
    assert r.status_code == 303 and r.headers["location"] == "/lab/social/fil"
    accueil_en_session = Selector(client.get("/fr").text)
    assert not accueil_en_session.css('form[action="/session/commencer"]'), "pas un second accord"
    assert accueil_en_session.css('a.bouton-principal[href="/lab/social/fil"]'), "reprendre la visite"
    double = client.post(
        "/session/commencer",
        data={**champs_du_formulaire(client.get("/session").text, "/session/terminer"), "consentement": "oui"},
        headers={"Origin": ORIGINE},
        follow_redirects=False,
    )
    assert double.status_code == 303 and double.headers["location"] == "/lab/social/fil"


@pytest.mark.parametrize("langue", ["fr", "en"])
def test_notice_a_son_adresse(client, langue):
    html = notice(client, langue)
    sel = Selector(html)
    assert langue_html(html) == langue
    assert not sel.css('form[action="/session/commencer"]'), "l'accord se donne sur l'accueil"
    assert sel.css(f'.notice-retour a[href="/{langue}"]'), "retour à l'accueil pour participer"
    assert sel.css(f'.autre-langue a[href="/{AUTRE[langue]}/information"]')
    assert set(CLASSES_NOTICE) <= classes_de(html), set(CLASSES_NOTICE) - classes_de(html)
    assert sel.css('link[rel="stylesheet"]::attr(href)').getall() == ["/public/static/public.css"]


def test_ancien_chemin_de_la_notice(client):
    """« /information », sans préfixe, sert la notice dans la langue du navigateur ; « / » garde l'accord."""
    for langue in ("fr", "en"):
        r = client.get("/information", headers={"Accept-Language": ACCEPT[langue]})
        assert r.status_code == 200 and langue_html(r.text) == langue
        assert squelette(r.text) == squelette(notice(client, langue))
    assert Selector(client.get("/").text).css('form[action="/session/commencer"]')


def test_feuille_de_style_de_l_etude(client):
    r = client.get("/public/static/public.css")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/css")
    assert r.content == PUBLIC_CSS.read_bytes()
    contact = client.get("/contact/style.css")
    assert contact.content == PUBLIC_CSS.read_bytes(), "les pages de contact ont la même feuille, sous /contact/"
    assert not re.search(r"(?:https?:)?//[a-z0-9]|@import|url\(", r.text, re.I), "aucune ressource extérieure"


@pytest.mark.parametrize("langue", ["fr", "en"])
def test_pages_de_l_etude_sans_style_ni_script_dans_la_page(client, langue):
    pages = parcours_complet(client, langue)
    pages["notice"] = notice(client, langue)
    for nom, html in pages.items():
        if nom.startswith("vitrine"):
            continue
        assert "<style" not in html.lower() and "<script" not in html.lower(), nom
        assert not re.search(r"(?:https?:)?//[a-z0-9]", html, re.I), nom
        for element in Selector(html).xpath("//*"):
            for attribut in element.attrib:
                assert attribut.lower() != "style" and not attribut.lower().startswith("on"), (nom, attribut)
        feuilles = Selector(html).css('link[rel="stylesheet"]::attr(href)').getall()
        assert feuilles in (["/public/static/public.css"], ["/contact/style.css"]), (nom, feuilles)


def test_version_du_texte_d_information_changee():
    from shadowlab.public.pages import VERSION_INFORMATION

    assert VERSION_INFORMATION not in ("2026-11-12.7", "2026-11-14.1")
