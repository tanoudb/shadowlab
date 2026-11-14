"""Site d'étude « Humain ou robot ? » : le fond de la nouvelle application publique (cadrage du 13/11/2026, v2).

Cadrage : `docs/recherche/site-public-communaute-2026-11-13.md` (« Règles », « Langue », « Textes de l'accueil »).
Étape 1 : deux langues sans cookie de plus. Étape 2 : l'accueil de l'étude et la notice. Étape 3 : la fréquentation.
Étape 4 : le plafond de sessions par jour devient un réglage.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import replace
from datetime import UTC, datetime, timedelta
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
    vieillir,
)

from shadowlab import config
from shadowlab.config import ReglagesPublics, charger_public
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
    if Selector(page.text).css('form[action="/session/commencer"]'):
        champs = champs_du_formulaire(page.text, "/session/commencer")
    else:  # jour plein : plus de formulaire, le jeton anti-CSRF est dans son cookie (double soumission)
        csrf = next(c.value for c in client.cookies.jar if c.name.endswith("slp-csrf"))
        champs = {"csrf": csrf, "langue": langue}
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


# Texte « Franchise » du cadrage (« Textes de l'accueil »), mot pour mot, depuis le relevé enrichi (D-76).
FRANCHISE = {
    "fr": "Pendant la session, nous relevons les caractéristiques de votre navigateur et votre façon de naviguer : "
    "mouvements de la souris, défilement, rythme des clics et des touches. Jamais ce que vous tapez, ni votre adresse "
    "IP. Vous pouvez tout supprimer d'un clic.",
    "en": "During the session we record your browser's characteristics and how you browse: mouse movements, "
    "scrolling, the rhythm of your clicks and keystrokes. Never what you type, never your IP address. You can delete "
    "everything with one click.",
}


@pytest.mark.parametrize("langue", ["fr", "en"])
def test_accueil_resume_du_releve_exact_et_a_un_seul_endroit(client, langue):
    """Le résumé dit ce que relèvent observateur.js et releve.js (D-76) : le texte « Franchise » du cadrage. Il ne
    promet plus « ni la position de la souris » ; il garde : jamais ce que vous tapez, ni votre adresse IP, ni votre
    localisation, rien qui demande une autorisation."""
    from shadowlab.public.pages import RESUME_RELEVE

    html = client.get(f"/{langue}").text
    resume = RESUME_RELEVE[langue]
    assert set(RESUME_RELEVE) == {"fr", "en"} and set(resume) == set(RESUME_RELEVE["fr"])
    assert resume["franchise"] == FRANCHISE[langue]
    assert texte_de(html, ".releve-franchise") == resume["franchise"]
    assert [texte_de(li, None) for li in Selector(html).css(".releve-oui li").getall()] == resume["oui"]
    assert [texte_de(li, None) for li in Selector(html).css(".releve-non li").getall()] == resume["non"]
    annonce = " ".join([resume["franchise"], *resume["oui"]]).lower()
    assert ("mouvements de la souris" if langue == "fr" else "mouse movements") in annonce
    jamais = " ".join(resume["non"]).lower()
    assert "position" not in jamais, "la position de la souris est relevée"
    attendus = {
        "fr": ("ce que vous tapez", "les touches", "adresse ip", "localisation", "autorisation"),
        "en": ("what you type", "the keys", "ip address", "location", "permission"),
    }
    for mot in attendus[langue]:
        assert mot in jamais, mot


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
    assert sel.css(f'.notice-retour a[href="/{langue}#participer"]'), "retour à l'accueil, droit sur l'accord"
    assert Selector(client.get(f"/{langue}").text).css('form.accord#participer[action="/session/commencer"]')
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

    anciennes = ("2026-11-12.7", "2026-11-14.1", "2026-11-14.2", "2026-11-14.3", "2026-11-14.4")
    assert VERSION_INFORMATION not in anciennes, "le relevé enrichi (D-76) change le texte accepté"


# === Étape 3 : la fréquentation, un compte par jour ===================================================

COLONNES_FREQUENTATION = ["jour", "accueil", "commencees", "terminees"]
COMPTEUR = {
    "fr": {
        0: "0 session enregistrée à ce jour",
        1: "1 session enregistrée à ce jour",
        2: "2 sessions enregistrées à ce jour",
    },
    "en": {0: "0 sessions recorded so far", 1: "1 session recorded so far", 2: "2 sessions recorded so far"},
}
# Ce que la notice dit de la fréquentation, dans les deux langues.
FREQUENTATION = {
    "fr": (
        "l'application tient un compte par jour : le nombre de chargements de la page d'accueil, de sessions "
        "commencées et de sessions terminées",
        "ni adresse IP, ni identifiant, ni navigateur, ni heure",
        "sans limite de durée",
    ),
    "en": (
        "the application keeps one count per day: the number of home page loads, of sessions started and of "
        "sessions ended",
        "no IP address, no identifier, no browser, no time of day",
        "with no time limit",
    ),
}
# Phrases devenues fausses : une visite sans participer laisse le compte du jour.
PHRASES_RETIREES = {
    "fr": ("dans ce cas, rien n'est relevé.", "ni mesure d'audience,"),
    "en": ("in that case, nothing is collected.", "no audience measurement,"),
}


def aujourd_hui() -> str:
    return datetime.now(UTC).date().isoformat()


def frequentation(reglages: ReglagesPublics) -> list[tuple]:
    cx = ouvrir(reglages)
    try:
        return [tuple(ligne) for ligne in cx.execute("SELECT * FROM frequentation ORDER BY jour")]
    finally:
        cx.close()


def terminer_session(client: TestClient):
    champs = champs_du_formulaire(client.get("/session").text, "/session/terminer")
    r = client.post("/session/terminer", data=champs, headers={"Origin": ORIGINE})
    assert r.status_code == 200
    return r


def test_table_de_frequentation_trois_nombres_par_jour(client, reglages_publics):
    client.get("/")
    cx = ouvrir(reglages_publics)
    try:
        colonnes = [c[1] for c in cx.execute("PRAGMA table_info(frequentation)")]
    finally:
        cx.close()
    assert colonnes == COLONNES_FREQUENTATION, "ni adresse, ni identifiant, ni navigateur, ni heure"
    assert frequentation(reglages_publics) == [(aujourd_hui(), 1, 0, 0)]
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", frequentation(reglages_publics)[0][0]), "le jour, jamais l'heure"


def test_comptes_du_jour(client, reglages_publics):
    for chemin in ("/", "/fr", "/en", "/"):
        assert client.get(chemin).status_code == 200
    for chemin in ("/fr/information", "/information", "/lab/social/fil", "/lab/vitrine", "/session", "/contact"):
        assert client.get(chemin).status_code == 200, chemin
    assert client.head("/").status_code in (200, 405), "une requête HEAD ne compte pas"
    assert frequentation(reglages_publics) == [(aujourd_hui(), 4, 0, 0)], "seuls les chargements de l'accueil"
    assert commencer_depuis(client, "fr").status_code == 303  # charge aussi l'accueil
    assert frequentation(reglages_publics) == [(aujourd_hui(), 5, 1, 0)]
    double = client.post(
        "/session/commencer",
        data={**champs_du_formulaire(client.get("/session").text, "/session/terminer"), "consentement": "oui"},
        headers={"Origin": ORIGINE},
        follow_redirects=False,
    )
    assert double.status_code == 303
    assert frequentation(reglages_publics)[0][2] == 1, "un double clic n'ouvre rien, donc ne compte rien"
    terminer_session(client)
    assert frequentation(reglages_publics) == [(aujourd_hui(), 5, 1, 1)]
    champs = champs_du_formulaire(client.get("/session").text, "/session/supprimer")
    sans_session = client.post("/session/terminer", data=champs, headers={"Origin": ORIGINE}, follow_redirects=False)
    assert sans_session.status_code == 303, "plus de session en cours : rien à terminer"
    assert frequentation(reglages_publics) == [(aujourd_hui(), 5, 1, 1)]


def test_visite_hors_session_n_ecrit_que_le_compte_du_jour(client, reglages_publics):
    for chemin in ("/", "/en", "/fr/information", "/lab/social/fil", "/lab/vitrine", "/lab/vitrine/annonces"):
        assert client.get(chemin).status_code == 200, chemin
    cx = ouvrir(reglages_publics)
    try:
        tables = [t for (t,) in cx.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
        remplies = {t for t in tables if t != "frequentation" and cx.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]}
    finally:
        cx.close()
    assert remplies == set(), remplies
    assert frequentation(reglages_publics) == [(aujourd_hui(), 2, 0, 0)]


def test_comptes_survivent_a_la_purge_et_a_la_suppression(client, reglages_publics):
    from shadowlab.public import purger

    assert commencer_depuis(client, "fr").status_code == 303
    terminer_session(client)
    client.cookies.clear()
    assert commencer_depuis(client, "en", adresse="198.51.100.9").status_code == 303
    avant = frequentation(reglages_publics)
    assert avant == [(aujourd_hui(), 2, 2, 1)]
    champs = champs_du_formulaire(client.get("/session").text, "/session/supprimer")
    assert client.post("/session/supprimer", data=champs, headers={"Origin": ORIGINE}).status_code == 200
    cx = ouvrir(reglages_publics)
    try:
        (jeton,) = cx.execute("SELECT session_token FROM runs").fetchone()
        vieillir(cx, jeton, 120)
        assert purger(cx, 90) == 1
        assert cx.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0
    finally:
        cx.close()
    assert frequentation(reglages_publics) == avant


def test_base_pleine_ne_compte_plus(reglages_publics):
    with fabriquer(reglages_publics, taille_max_base=1) as c:
        assert c.get("/").status_code == 200, "la page reste servie"
    assert frequentation(reglages_publics) == []


def test_compte_perdu_si_la_base_tombe_mais_accueil_servi(client, monkeypatch):
    import sqlite3

    from shadowlab.public import donnees

    def panne(*_args, **_kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(donnees, "compter", panne)
    monkeypatch.setattr(donnees, "sessions_terminees", panne)
    r = client.get("/fr")
    assert r.status_code == 200 and "locked" not in r.text
    assert not Selector(r.text).css(".accueil-compteur"), "sans compte lisible, pas de compteur"


@pytest.mark.parametrize("langue", ["fr", "en"])
def test_accueil_affiche_le_total_des_sessions_terminees(client, reglages_publics, langue):
    assert texte_de(client.get(f"/{langue}").text, ".accueil-compteur") == COMPTEUR[langue][0]
    for n, adresse in enumerate(("192.0.2.10", "192.0.2.11"), start=1):
        client.cookies.clear()
        assert commencer_depuis(client, langue, adresse=adresse).status_code == 303
        terminer_session(client)
        assert texte_de(client.get(f"/{langue}").text, ".accueil-compteur") == COMPTEUR[langue][n]
    client.cookies.clear()
    assert commencer_depuis(client, langue, adresse="192.0.2.12").status_code == 303
    assert texte_de(client.get(f"/{langue}").text, ".accueil-compteur") == COMPTEUR[langue][2], "terminées seulement"


def test_total_affiche_sur_tous_les_jours(client, reglages_publics):
    client.get("/")
    cx = ouvrir(reglages_publics)
    try:
        veille = (datetime.now(UTC) - timedelta(days=1)).date().isoformat()
        cx.execute("INSERT INTO frequentation (jour, accueil, commencees, terminees) VALUES (?, 40, 9, 7)", (veille,))
    finally:
        cx.close()
    assert texte_de(client.get("/fr").text, ".accueil-compteur") == "7 sessions enregistrées à ce jour"


@pytest.mark.parametrize("langue", ["fr", "en"])
def test_notice_dit_exactement_le_compte_par_jour(client, langue):
    texte = texte_de(notice(client, langue))
    for phrase in FREQUENTATION[langue]:
        assert phrase in texte, phrase
    for phrase in PHRASES_RETIREES[langue]:
        assert phrase not in texte, phrase
    sans_session = texte_de(client.get(f"/{langue}").text, ".releve-sans-session")
    assert ("un nombre par jour" if langue == "fr" else "one number per day") in sans_session


def test_commande_frequentation(monkeypatch, reglages_publics, capsys):
    from shadowlab import cli

    monkeypatch.setenv("SHADOWLAB_PUBLIC_BASE", str(reglages_publics.base_donnees))
    monkeypatch.setenv("SHADOWLAB_PUBLIC_HOTES", HOTE)
    monkeypatch.setenv("SHADOWLAB_PUBLIC_CONTACT", CONTACT)
    assert cli.main(["public", "frequentation"]) == 0
    assert "Aucune visite" in capsys.readouterr().out
    with fabriquer(reglages_publics) as c:
        assert commencer_depuis(c, "fr").status_code == 303
        terminer_session(c)
        c.get("/en")
    cx = ouvrir(reglages_publics)
    try:
        cx.execute("INSERT INTO frequentation (jour, accueil, commencees, terminees) VALUES ('2026-11-01', 30, 4, 3)")
    finally:
        cx.close()
    assert cli.main(["public", "frequentation"]) == 0
    lignes = capsys.readouterr().out.splitlines()
    par_jour = {ligne.split()[0]: ligne.split()[1:] for ligne in lignes if ligne.split()}
    assert par_jour["2026-11-01"] == ["30", "4", "3"]
    assert par_jour[aujourd_hui()] == ["2", "1", "1"]
    assert par_jour["total"] == ["32", "5", "4"]
    assert [ligne.split()[0] for ligne in lignes if re.match(r"\d{4}-", ligne)] == ["2026-11-01", aujourd_hui()]


# === Étape 4 : le plafond de sessions par jour devient un réglage =====================================

PLEIN = {
    "fr": ("L'étude a fait le plein pour aujourd'hui", "Revenez demain"),
    "en": ("The study is full for today", "come back tomorrow"),
}


@pytest.mark.parametrize(
    "valeur, attendue", [(None, 40), ("250", 250), ("1", 1), ("5000", 5000), ("0", 1), ("-3", 1), ("999999", 5000)]
)
def test_reglage_sessions_par_jour(monkeypatch, tmp_path, valeur, attendue):
    monkeypatch.setattr(config, "_charger_env", lambda *a, **k: None)
    for variable in [v for v in os.environ if v.startswith("SHADOWLAB_")]:
        monkeypatch.delenv(variable)
    monkeypatch.setenv("SHADOWLAB_SORTIES", str(tmp_path))
    if valeur is not None:
        monkeypatch.setenv("SHADOWLAB_PUBLIC_SESSIONS_PAR_JOUR", valeur)
    assert charger_public().sessions_par_jour == attendue


def essai_de_session(client: TestClient, adresse: str, langue: str = "fr"):
    client.cookies.clear()
    return commencer_depuis(client, langue, adresse=adresse)


def test_reglage_applique_sans_limites_explicites(reglages_publics):
    """Le chemin de `shadowlab public servir` : `creer_app_publique(reglages)`, sans `Limites` donnée par un test."""
    from shadowlab.public import creer_app_publique

    app = creer_app_publique(replace(reglages_publics, sessions_par_jour=2))
    with TestClient(app, base_url=ORIGINE) as c:
        statuts = [essai_de_session(c, f"192.0.2.{n}").status_code for n in range(1, 4)]
    assert statuts == [303, 303, 429]


@pytest.mark.parametrize("langue", ["fr", "en"])
def test_plafond_du_jour_atteint_la_page_le_dit(reglages_publics, langue):
    from shadowlab.public import creer_app_publique

    app = creer_app_publique(replace(reglages_publics, sessions_par_jour=1))
    with TestClient(app, base_url=ORIGINE) as tardif, TestClient(app, base_url=ORIGINE) as premier:
        accueil_avant = tardif.get(f"/{langue}").text
        champs = champs_du_formulaire(accueil_avant, "/session/commencer")
        assert essai_de_session(premier, "192.0.2.1", langue).status_code == 303
        refus = tardif.post(
            "/session/commencer",
            data={**champs, "consentement": "oui"},
            headers={"Origin": ORIGINE, "X-Forwarded-For": "192.0.2.2"},
        )
        assert refus.status_code == 429
        titre, demain = PLEIN[langue]
        assert langue_html(refus.text) == langue
        assert titre in texte_de(refus.text) and demain in texte_de(refus.text)
        accueil_plein = tardif.get(f"/{langue}").text
    sel = Selector(accueil_plein)
    assert not sel.css('form[action="/session/commencer"]'), "plus de case à cocher pour rien"
    assert titre in texte_de(accueil_plein, ".accord-complet") and demain in texte_de(accueil_plein, ".accord-complet")
    assert sel.css('a.visiter-sans-participer[href="/lab/social/fil"]'), "on peut encore visiter sans participer"


def test_plafond_du_jour_n_use_pas_la_limite_par_adresse(reglages_publics):
    from shadowlab.public import creer_app_publique

    app = creer_app_publique(replace(reglages_publics, sessions_par_jour=1))
    limiteur = app.state.limiteurs[0]
    with TestClient(app, base_url=ORIGINE) as c:
        assert essai_de_session(c, "192.0.2.1").status_code == 303
        assert essai_de_session(c, "192.0.2.2").status_code == 429
    assert len(limiteur._vues) == 1, "un jour plein ne consomme pas le quota horaire d'une adresse"


def test_plafond_de_la_base_en_sessions_au_pire():
    """Calcul (pas une mesure) repris dans docs/site-public.md : combien de sessions au volume maximal tient la base.

    Une requête notée occupe au pire une page SQLite de 4 Kio (mesuré le 12/11 : une ligne de ~2,3 Ko par page) ;
    les envois d'une session font au plus `volume_par_session` octets de charges pour l'observateur et
    `volume_trace_par_session` pour le relevé enrichi (D-76), plus ~300 octets par ligne."""
    from shadowlab.public import Limites

    limites = Limites()
    envois = limites.envois_par_session + limites.envois_trace_par_session
    pire_session = (
        limites.requetes_par_session * 4096
        + limites.volume_par_session
        + limites.volume_trace_par_session
        + envois * 300
    )
    assert 25_000_000 < pire_session < 26_000_000, pire_session
    sessions = limites.taille_max_base // pire_session
    assert 80 <= sessions <= 90, sessions
    assert limites.sessions_par_jour == 40, "défaut inchangé"


# === Relecture : parité des textes, sous-champs de la notice ==========================================


def test_textes_memes_cles_et_memes_champs_dans_les_deux_langues():
    """Une clé absente dans une langue ferait une erreur 500 ; un champ `{jours}` oublié promettrait moins."""
    import string

    from shadowlab.public.textes import ERREURS, RESUME_RELEVE, T

    def champs(texte: str) -> set[str]:
        return {nom for _, nom, _, _ in string.Formatter().parse(texte) if nom}

    assert set(T["fr"]) == set(T["en"])
    for cle in T["fr"]:
        assert champs(T["fr"][cle]) == champs(T["en"][cle]), cle
    assert set(ERREURS["fr"]) == set(ERREURS["en"])
    for cle in ERREURS["fr"]:
        assert all(texte.strip() for texte in ERREURS["fr"][cle] + ERREURS["en"][cle]), cle
    for partie in ("oui", "non"):
        assert len(RESUME_RELEVE["fr"][partie]) == len(RESUME_RELEVE["en"][partie]), partie


def test_notice_decrit_les_sous_champs_de_navigateur_et_apis():
    """`observateur.js` envoie aussi, dans `navigateur` et `apis`, des champs que la notice ne nommait pas : cookies
    permis, lecteur PDF, types de fichiers, appareil mobile ou non, objet propre à Chrome, périphériques HID."""
    from shadowlab.public.pages import RELEVES

    source = OBSERVATEUR.read_text(encoding="utf-8")
    collecte = re.search(r"^async function collecter\(\) \{(.*?)^\}$", source, re.S | re.M).group(1)
    for sous_champ in ("cookieEnabled:", "pdfViewerEnabled:", "mimeTypes:", "mobile:", "chrome:", "hid:"):
        assert sous_champ in collecte, sous_champ
    attendus = {
        "fr": {"navigateur": ("cookies", "PDF", "types de fichiers", "mobile"), "apis": ("Chrome", "HID")},
        "en": {"navigateur": ("cookies", "PDF", "file types", "mobile"), "apis": ("Chrome", "HID")},
    }
    for langue, par_cle in attendus.items():
        descriptions = dict(RELEVES[langue][0])
        for cle, mots in par_cle.items():
            for mot in mots:
                assert mot in descriptions[cle], (langue, cle, mot)


# === Dessin (14/11/2026) : photos de l'accueil, sommaire de la notice ================================


def references_chargees(html: str) -> list[str]:
    """Ce qu'un navigateur charge pour afficher la page : images (src et srcset), feuilles, scripts."""
    sel = Selector(html)
    refs = sel.css("img::attr(src), link::attr(href), script::attr(src)").getall()
    for jeu in sel.css("img::attr(srcset)").getall():
        refs += [morceau.split()[0] for morceau in jeu.split(",")]
    return refs


@pytest.mark.parametrize("langue", ["fr", "en"])
def test_accueil_montre_de_vraies_photos_du_reseau_social(client, langue):
    """Hors session : la mosaïque du haut (photos chargées tout de suite) et les vignettes de la carte du site
    (chargées en différé), de vraies photos du manifeste, dimensions réelles et description dans la langue."""
    from shadowlab.public import social
    from shadowlab.public.pages import DESCRIPTIONS_PHOTOS, PHOTOS_VEDETTE, PLACES_MOSAIQUE

    sel = Selector(client.get(f"/{langue}").text)
    photos = {p.id: p for p in social.charger_photos(social.DOSSIER_PHOTOS)}
    attendues = [i for _, i in PLACES_MOSAIQUE if i] + list(PHOTOS_VEDETTE)
    images = sel.css("main img")
    assert [img.attrib["src"] for img in images] == [f"/lab/social/photos/{i}-480.jpg" for i in attendues]
    for img, ident in zip(images, attendues, strict=True):
        assert (img.attrib["width"], img.attrib["height"]) == tuple(str(n) for n in photos[ident].dimensions(480))
        assert img.attrib["alt"] == DESCRIPTIONS_PHOTOS[ident][1 if langue == "en" else 0] != ""
        assert client.get(img.attrib["src"]).status_code == 200
    haut, bas = sel.css(".accueil-mosaique img"), sel.css(".site-vedette img")
    assert haut and all("loading" not in img.attrib for img in haut), "premier écran : chargées tout de suite"
    assert bas and all(img.attrib.get("loading") == "lazy" for img in bas), "plus bas : chargées en différé"
    for ref in references_chargees(sel.get()):
        assert ref.startswith(("/lab/social/photos/", "/public/static/")), ref
        assert client.get(ref).status_code == 200, ref


def test_accueil_en_session_ne_charge_rien_sous_lab(client):
    """Pendant une session, toute requête sous /lab/ est notée : l'accueil ne charge alors aucune photo (la notice ne
    promet un relevé que sur les sites de démonstration). La mosaïque garde sa forme, en tesselles de couleur."""
    assert commencer_depuis(client, "fr").status_code == 303
    for chemin in ("/fr", "/en", "/"):
        html = client.get(chemin).text
        assert not [ref for ref in references_chargees(html) if ref.startswith("/lab/")], chemin
        sel = Selector(html)
        assert sel.css('.accueil-mosaique[aria-hidden="true"] .tesselle'), chemin
        assert not sel.css("main img"), chemin


def test_accueil_sans_les_photos_choisies(monkeypatch, tmp_path, reglages_publics):
    """Un manifeste qui n'a pas les photos choisies (photos d'essai) : l'accueil se rend, sans image."""
    from test_public_social import dossier_de_photos

    from shadowlab.public import social

    monkeypatch.setattr(social, "DOSSIER_PHOTOS", dossier_de_photos(tmp_path, 3))
    with fabriquer(reglages_publics) as c:
        r = c.get("/fr")
    assert r.status_code == 200
    assert not Selector(r.text).css("main img") and Selector(r.text).css(".accueil-mosaique .tesselle")


@pytest.mark.parametrize("langue", ["fr", "en"])
def test_sommaire_de_la_notice_suit_ses_sections(client, langue):
    sel = Selector(notice(client, langue))
    sections = [(s.attrib["id"], texte_de(s.css("h2").get(), None)) for s in sel.css("main section.notice-section")]
    liens = [(a.attrib["href"], texte_de(a.get(), None)) for a in sel.css("main nav.notice-sommaire ol a")]
    assert len(sections) >= 9 and liens == [(f"#{ident}", titre) for ident, titre in sections]
    assert sel.css(f'main nav.notice-sommaire .sommaire-retour a[href="/{langue}#participer"]'), "l'accord à un clic"
