"""Site d'étude « Humain ou robot ? » : le fond de la nouvelle application publique (cadrage du 13/11/2026, v2).

Cadrage : `docs/recherche/site-public-communaute-2026-11-13.md` (« Règles », « Langue », « Textes de l'accueil »).
Étape 1 : deux langues sans cookie de plus.
"""

from __future__ import annotations

import json
from html import escape
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
    """La notice complète dans une langue (étape 1 : l'accueil `/{langue}` la porte encore en entier)."""
    r = client.get(f"/{langue}")
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
