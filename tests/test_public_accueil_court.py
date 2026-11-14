"""Accueil court de l'étude « Humain ou robot ? » (demande du client, 14/11/2026 : « trop long, trop de trucs »).

Un visiteur comprend en cinq secondes et commence en un clic : un titre, une phrase, la franchise sur ce qui est
relevé, un seul bouton « J'accepte et je commence » (plus de case à cocher) ; le détail se replie dans un
`<details>` ; la navigation du haut ne garde que la marque et la langue, les liens utiles vont au pied de page.
"""

from __future__ import annotations

import re

import pytest
from parsel import Selector
from test_public import CONTACT, HOTE, ORIGINE, champs_du_formulaire, fabriquer
from test_public_etude import ACCEPT, AUTRE, parcours_complet

from shadowlab.config import ReglagesPublics

LANGUES = ["fr", "en"]
BOUTON = {"fr": "J'accepte et je commence", "en": "I agree, start"}
DETAIL = {"fr": "Ce qui est relevé, en détail", "en": "What is recorded, in detail"}
DEUX_MINUTES = {"fr": "2 minutes", "en": "2 minutes"}
ANCIENNE_DUREE = re.compile(r"5\s+(à|to)\s+10")
CASE_A_COCHER = re.compile(r"\b(coch\w*|case à cocher|la case|tick\w*|checkbox|check the box)\b", re.I)
PIED = {
    "fr": {"information": "/fr/information", "session": "/session", "contact": "/contact"},
    "en": {"information": "/en/information", "session": "/session", "contact": "/contact"},
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


def texte(html: str | None, css: str | None = None) -> str:
    sel = Selector(html or "<p></p>")
    noeuds = sel.css(css) if css else sel
    return " ".join(" ".join(noeuds.xpath(".//text()").getall()).split())


@pytest.mark.parametrize("langue", LANGUES)
def test_accueil_un_formulaire_un_bouton_sans_case_a_cocher(client, langue):
    html = client.get(f"/{langue}").text
    sel = Selector(html)
    formulaire = sel.css('main form[action="/session/commencer"][method="post"]')
    assert len(formulaire) == 1
    assert not sel.css('input[type="checkbox"]'), "plus de case à cocher"
    boutons = formulaire.css('button[type="submit"][name="consentement"][value="oui"]')
    assert len(boutons) == 1 and texte(boutons.get()) == BOUTON[langue]
    assert len(formulaire.css("button")) == 1, "un seul bouton"
    assert formulaire.css('input[type="hidden"][name="csrf"]')
    assert formulaire.css('input[type="hidden"][name="langue"]::attr(value)').get() == langue
    assert formulaire.css(f'a[href="/{langue}/information"]'), "la notice complète à un clic avant d'accepter"
    assert formulaire.css('a.visiter-sans-participer[href="/lab/social/fil"]'), "visiter sans participer, à côté"
    assert texte(html, ".releve-franchise") in texte(formulaire.get()), "la franchise est dans le formulaire"


@pytest.mark.parametrize("langue", LANGUES)
def test_accueil_formulaire_avant_le_detail_replie(client, langue):
    html = client.get(f"/{langue}").text
    sel = Selector(html)
    details = sel.css("main details")
    assert len(details) == 1
    assert "open" not in details[0].attrib, "fermé par défaut"
    assert texte(details.css("summary").get()) == DETAIL[langue]
    assert html.index('action="/session/commencer"') < html.index("<details")
    for classe in ("releve-oui", "releve-non", "releve-sans-session", "accueil-but"):
        assert details.css(f".{classe}"), classe
    assert details.css(f'a[href="/{langue}/information"]'), "le lien vers la notice dans le détail"
    assert not sel.css("script"), "aucun JavaScript"
    assert "style=" not in html


@pytest.mark.parametrize("langue", LANGUES)
def test_accueil_court_sans_etapes_ni_section_des_sites(client, langue):
    html = client.get(f"/{langue}").text
    sel = Selector(html)
    assert not sel.css(".accueil-etapes, ol.etapes, .etape, .accueil-sites, .site-vedette, .site-second, .fictif")
    assert not sel.css("a.bouton-principal[href='#participer']"), "plus de bouton qui mène à l'ancre"
    assert not sel.css(".accueil-sous-titre"), "une seule phrase d'accroche"
    assert len(sel.css("main .accueil-accroche")) == 1
    assert not sel.css('main a[href="/lab/vitrine"]'), "le second site n'est plus cité sur l'accueil"
    assert sel.css("main .accueil-mosaique"), "la mosaïque de photos reste"


@pytest.mark.parametrize("langue", LANGUES)
def test_accueil_dit_deux_minutes_et_aucune_page_ne_dit_cinq_a_dix(client, langue):
    html = client.get(f"/{langue}").text
    assert DEUX_MINUTES[langue] in texte(html, ".accueil-accroche")
    pages = {"accueil": html, "notice": client.get(f"/{langue}/information").text, **parcours_complet(client, langue)}
    assert any(DEUX_MINUTES[langue] in texte(h) for h in pages.values())
    assert DEUX_MINUTES[langue] in texte(pages["notice"], "#deroulement")
    for nom, page in pages.items():
        assert not ANCIENNE_DUREE.search(texte(page)), nom


@pytest.mark.parametrize("langue", LANGUES)
def test_plus_aucun_texte_ne_parle_de_case_a_cocher(client, langue):
    pages = {"accueil": client.get(f"/{langue}").text, "notice": client.get(f"/{langue}/information").text}
    pages.update(parcours_complet(client, langue))
    champs = champs_du_formulaire(client.get(f"/{langue}").text, "/session/commencer")  # jeton du moment
    refus = client.post(
        "/session/commencer",
        data={k: v for k, v in champs.items()},
        headers={"Origin": ORIGINE, "Accept-Language": ACCEPT[langue]},
    )
    assert refus.status_code == 422
    pages["accord-manquant"] = refus.text
    for nom, page in pages.items():
        trouve = CASE_A_COCHER.search(texte(page))
        assert not trouve, f"{nom} : « {trouve and trouve.group(0)} »"
    assert "participer" in texte(refus.text, ".erreur").lower() or "take part" in texte(refus.text, ".erreur").lower()
    assert BOUTON[langue] in texte(refus.text, ".erreur") or BOUTON[langue] in texte(refus.text, "form")


@pytest.mark.parametrize("langue", LANGUES)
def test_la_base_legale_est_le_bouton(client, langue):
    notice = texte(client.get(f"/{langue}/information").text)
    assert BOUTON[langue] in notice, "la notice nomme le bouton qui donne le consentement"


@pytest.mark.parametrize("langue", LANGUES)
def test_cliquer_le_bouton_ouvre_une_session(client, langue):
    page = client.get(f"/{langue}", headers={"Accept-Language": ACCEPT[AUTRE[langue]]})
    champs = champs_du_formulaire(page.text, "/session/commencer")
    assert "consentement" not in champs, "c'est le bouton qui porte le champ"
    reponse = client.post(
        "/session/commencer",
        data={**champs, "consentement": "oui"},
        headers={"Origin": ORIGINE},
        follow_redirects=False,
    )
    assert reponse.status_code == 303 and reponse.headers["location"] == "/lab/social/fil"
    assert any(c.name.endswith("slp-session") for c in client.cookies.jar)


@pytest.mark.parametrize("envoi", [{}, {"consentement": ""}, {"consentement": "non"}], ids=["absent", "vide", "non"])
def test_sans_consentement_toujours_refuse(client, envoi):
    champs = champs_du_formulaire(client.get("/fr").text, "/session/commencer")
    reponse = client.post(
        "/session/commencer", data={**champs, **envoi}, headers={"Origin": ORIGINE}, follow_redirects=False
    )
    assert reponse.status_code == 422
    assert not any(c.name.endswith("slp-session") for c in client.cookies.jar)
    assert not Selector(client.get("/lab/vitrine").text).css('meta[name="sl-session"]')


@pytest.mark.parametrize("langue", LANGUES)
def test_navigation_du_haut_allegee(client, langue):
    pages = {"accueil": client.get(f"/{langue}").text, "notice": client.get(f"/{langue}/information").text}
    pages.update({"ma-session": client.get("/session").text, "contact": client.get("/contact").text})
    for nom, html in pages.items():
        entete = Selector(html).css("header.etude-entete")
        liens = entete.css("a::attr(href)").getall()
        assert liens, nom
        assert len(entete.css("a.etude-marque")) == 1, nom
        autre = entete.css(".autre-langue a::attr(href)").getall()
        reste = [h for h in liens if h not in autre]
        assert len(reste) == 1, (nom, liens)  # la marque
        for h in ("/session", "/contact", f"/{langue}/information", "/lab/social/credits", "/lab/social/fil"):
            assert h not in liens, (nom, h)


@pytest.mark.parametrize("langue", LANGUES)
def test_pied_de_page_porte_les_liens_sur_chaque_page(client, langue):
    client.headers["Accept-Language"] = ACCEPT[langue]
    attendus = PIED[langue]
    for chemin in (f"/{langue}", f"/{langue}/information", "/session", "/contact"):
        pied = Selector(client.get(chemin).text).css("footer.etude-pied")
        liens = pied.css("a::attr(href)").getall()
        for nom, href in attendus.items():
            assert href in liens, (chemin, nom, liens)
    for chemin in (f"/{langue}", f"/{langue}/information", "/session"):
        pied = Selector(client.get(chemin).text).css("footer.etude-pied")
        assert "/lab/social/credits" in pied.css("a::attr(href)").getall(), chemin


@pytest.mark.parametrize("langue", LANGUES)
def test_session_en_cours_garde_reprendre_la_visite(client, langue):
    champs = champs_du_formulaire(client.get(f"/{langue}").text, "/session/commencer")
    client.post("/session/commencer", data={**champs, "consentement": "oui"}, headers={"Origin": ORIGINE})
    sel = Selector(client.get(f"/{langue}").text)
    assert not sel.css('form[action="/session/commencer"]')
    assert sel.css('.accord-en-cours a.bouton-principal[href="/lab/social/fil"]')
