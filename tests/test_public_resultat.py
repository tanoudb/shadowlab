# ruff: noqa: E501

"""Résultat de fin de session, côté site public (contrat du 17/11/2026, partie B).

À la fin, le visiteur voit si nos détecteurs l'ont pris pour un humain ou un robot, niveau par niveau, et peut
partager son score. Le calcul est fait par le labo dans un sous-processus ; ici un faux calcul le remplace
(`creer_app_publique(..., calcul_resultat=...)`). Sessions fabriquées seulement : jamais la donnée d'un vrai visiteur.
Le côté labo (`shadowlab.resultat_public`) n'est jamais importé ici, sauf par un test qui compare deux constantes.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import os
import re
import stat
import sys
import time
from dataclasses import replace

import pytest
import test_public
from fastapi.testclient import TestClient
from parsel import Selector
from test_public import ORIGINE, champs_du_formulaire, commencer, ouvrir

from shadowlab.public import Limites, creer_app_publique, textes
from shadowlab.public.pages import VERSION_INFORMATION

reglages_publics = test_public.reglages_publics

COOKIES = {"__Host-slp-csrf", "__Host-slp-session", "__Host-slp-droits"}
CSP = (
    "default-src 'self'; script-src 'self'; worker-src 'self' blob:; connect-src 'self'; img-src 'self' data:; "
    "style-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
)
NIVEAUX = ("01", "02", "03", "04", "05", "06", "07")
NOMS = {
    "fr": ["Sans protection", "Contrôles simples", "Empreinte du navigateur", "Défis", "Protection avancée",
           "Défense en couches", "État de l'art"],
    "en": ["No protection", "Basic checks", "Browser fingerprint", "Challenges", "Advanced protection",
           "Layered defence", "State of the art"],
}  # fmt: skip
RAISONS = {
    "fr": {
        "automatisation": "Votre navigateur portait des traces d'un outil d'automatisation.",
        "comportement": "Vos gestes (souris, défilement, rythme des pages) ont paru trop réguliers ou trop rares.",
        "incoherence": "Votre navigateur annonçait une chose et en montrait une autre (système, écran, langue…).",
        "retouche": "Certaines fonctions de votre navigateur semblaient modifiées, par exemple par une extension ou un réglage de confidentialité.",
        "cumul": "Plusieurs petits indices, sans gravité un par un, ont dépassé notre seuil une fois additionnés.",
        "piege": "Un lien ou un champ invisible pour un humain a été touché.",
    },
    "en": {
        "automatisation": "Your browser showed traces of an automation tool.",
        "comportement": "Your movements (mouse, scrolling, page rhythm) looked too regular or too sparse.",
        "incoherence": "Your browser claimed one thing and showed another (system, screen, language…).",
        "retouche": "Some of your browser's functions looked modified, for example by an extension or a privacy setting.",
        "cumul": "Several small clues, harmless one by one, crossed our threshold once added up.",
        "piege": "A link or field invisible to humans was touched.",
    },
}  # fmt: skip
HONNETE_ARRETE = {
    "fr": "Si vous êtes bien une personne, nos détecteurs se sont trompés. C'est exactement ce que cette étude cherche : chaque erreur trouvée nous aide à les corriger.",
    "en": "If you are indeed a person, our detectors got it wrong. That is exactly what this study is looking for: every mistake found helps us fix them.",
}
HONNETE_PASSE = {
    "fr": "Merci : votre session aide à vérifier que nos détecteurs laissent passer les vraies personnes.",
    "en": "Thank you: your session helps check that our detectors let real people through.",
}
TETE_PASSE = {"fr": "Humain, à tous les niveaux", "en": "Human, at every level"}
PARTAGE_PASSE = {
    "fr": "Des détecteurs de robots m'ont pris pour un humain à 6 niveaux sur 6. Et vous ?",
    "en": "Bot detectors took me for a human at 6 levels out of 6. What about you?",
}
# Noms de détecteurs, de signaux et de règles du labo : jamais dans une page du site public.
NOMS_DE_DETECTEURS = [
    "botd", "entropie-interaction", "trajectoire_lineaire", "regles-js", "automation-globals", "chrome-apis",
    "raf-timing", "correlation-session", "canvas-consistency", "deep-proxy", "integrite-proprietes", "honeypot",
]  # fmt: skip

HUMAIN = {
    "jugeable": True,
    "pages": 6,
    "pages_min": 4,
    "niveaux": [{"code": c, "arrete": False, "familles": []} for c in NIVEAUX],
}


def arrete(niveaux: dict[str, list[str]], pages: int = 6) -> dict:
    return {
        "jugeable": True,
        "pages": pages,
        "pages_min": 4,
        "niveaux": [
            {"code": c, "arrete": c in niveaux, "familles": list(niveaux.get(c, []))} for c in NIVEAUX
        ],
    }  # fmt: skip


COMPORTEMENT_05_A_07 = arrete({"05": ["comportement"], "06": ["comportement"], "07": ["comportement"]})


def R():
    """Le module du site public, importé au moment de s'en servir (chaque test échoue seul tant qu'il manque)."""
    return importlib.import_module("shadowlab.public.resultat")


class FauxCalcul:
    """Remplace le sous-processus : garde chaque appel, rend `reponse` après `delai` secondes."""

    def __init__(self, reponse, delai: float = 0.0) -> None:
        self.reponse, self.delai, self.appels = reponse, delai, []

    async def __call__(self, base, jeton):
        self.appels.append((base, jeton))
        if self.delai:
            await asyncio.sleep(self.delai)
        return self.reponse


def attente_courte(monkeypatch, secondes: float) -> None:
    """Réduit ATTENTE_S : la constante du module et, si elle sert de valeur par défaut, celle de `Resultats`."""
    module = R()
    monkeypatch.setattr(module, "ATTENTE_S", secondes)
    defauts = getattr(module.Resultats.__init__, "__kwdefaults__", None) or {}
    if "attente" in defauts:
        monkeypatch.setitem(defauts, "attente", secondes)


def fabriquer(reglages, calcul, **limites) -> TestClient:
    app = creer_app_publique(reglages, replace(Limites(), **limites), calcul_resultat=calcul)
    client = TestClient(app, base_url=ORIGINE)
    client.cookies_posees = set()  # noms de tous les Set-Cookie vus, sur tout le parcours

    def noter(reponse):
        for ligne in reponse.headers.get_list("set-cookie"):
            client.cookies_posees.add(ligne.partition("=")[0])

    client.event_hooks["response"].append(noter)
    return client


def ouvrir_session(client: TestClient, langue: str = "fr", pages: int = 5) -> str:
    """Session consentie avec `pages` empreintes, une par page (envois comme le fait observateur.js)."""
    jeton = commencer(client, langue=langue)
    for i in range(pages):
        corps = {"kind": "empreinte", "page": f"/lab/social/p/{i}", "payload": {"navigateur": {"userAgent": "essai"}}}
        r = client.post(
            f"/lab/collecte?sl={jeton}", content=json.dumps(corps), headers={"Content-Type": "application/json"}
        )
        assert r.status_code == 204, r.text
    return jeton


def terminer(client: TestClient, *, force: bool = False):
    champs = champs_du_formulaire(client.get("/lab/social/fil").text, "/session/terminer")
    if force:
        champs["force"] = "1"
    return client.post("/session/terminer", data=champs, headers={"Origin": ORIGINE})


def texte_de(html: str) -> str:
    morceaux = Selector(html).xpath("//body//text()").getall()
    return re.sub(r"\s+", " ", " ".join(morceaux)).replace("’", "'").strip()


def statut(reglages, jeton: str) -> str:
    cx = ouvrir(reglages)
    try:
        return cx.execute("SELECT status FROM runs WHERE session_token = ?", (jeton,)).fetchone()[0]
    finally:
        cx.close()


def sans_cookie_de_session(client: TestClient) -> None:
    for cookie in [c for c in client.cookies.jar if c.name.endswith("slp-session")]:
        client.cookies.delete(cookie.name, domain=cookie.domain, path=cookie.path)


def sans_style_ni_script(html: str, scripts_permis: list[str]) -> None:
    sel = Selector(html)
    assert not sel.css("style"), "aucun style dans la page"
    assert not sel.xpath("//*[@style]"), "aucun attribut style"
    assert not sel.xpath("//@*[starts-with(name(), 'on')]"), "aucun gestionnaire d'événement"
    assert sel.css("script:not([src])").getall() == [], "aucun script dans la page"
    assert sel.css("script::attr(src)").getall() == scripts_permis


# === 1. Humain partout ====================================================================================


@pytest.mark.parametrize("langue", ["fr", "en"])
def test_humain_partout_page_de_fin_complete(reglages_publics, langue):
    calcul = FauxCalcul(HUMAIN)
    with fabriquer(reglages_publics, calcul) as client:
        jeton = ouvrir_session(client, langue)
        r = terminer(client)
        assert r.status_code == 200
        assert statut(reglages_publics, jeton) == "reussi"
        assert [j for _, j in calcul.appels] == [jeton]
        assert calcul.appels[0][0] == reglages_publics.base_donnees
        html, texte = r.text, texte_de(r.text)
        assert TETE_PASSE[langue] in texte
        assert HONNETE_PASSE[langue] in texte
        for nom in NOMS[langue]:
            assert nom in texte, nom
        for code in NIVEAUX:
            assert code in texte
        assert PARTAGE_PASSE[langue] in texte
        sel = Selector(html)
        bouton = sel.css("button[data-partage]")
        assert len(bouton) == 1
        assert bouton.attrib["type"] == "button" and "hidden" in bouton.attrib
        assert PARTAGE_PASSE[langue] in bouton.attrib["data-texte"].replace("’", "'")
        assert bouton.attrib.get("data-copie") and bouton.attrib.get("data-echec")
        assert sel.css('[role="status"]')
        # L'adresse nue du site, rien d'autre ; la même dans le texte visible.
        adresses = re.findall(rf"https?://{re.escape(test_public.HOTE)}[^\s\"'<]*", html)
        assert adresses and set(adresses) == {f"https://{test_public.HOTE}/"}
        sans_style_ni_script(html, ["/public/static/partage.js"])
        assert not [h for h in sel.css("a::attr(href)").getall() if h.startswith("http")]
        # L'encadré de session reste là, et le retour au site.
        assert jeton in html
        assert sel.css('form[action="/session/supprimer"][method="post"] button')
        assert sel.css('a[href="/lab/social/fil"]')


def test_la_phrase_de_tete_est_sur_les_niveaux_02_a_07(reglages_publics):
    """Le niveau 01 n'a aucune protection : arrêté à lui seul, il ne change rien à la phrase de tête."""
    with fabriquer(reglages_publics, FauxCalcul(arrete({"01": ["automatisation"]}))) as client:
        ouvrir_session(client)
        texte = texte_de(terminer(client).text)
        assert "Pris pour un robot" not in texte
        assert TETE_PASSE["fr"] in texte


# === 2. Arrêté, avec raisons en mots simples ===============================================================


@pytest.mark.parametrize("langue", ["fr", "en"])
def test_arrete_aux_niveaux_05_a_07_par_le_comportement(reglages_publics, langue):
    with fabriquer(reglages_publics, FauxCalcul(COMPORTEMENT_05_A_07)) as client:
        ouvrir_session(client, langue)
        r = terminer(client)
        assert r.status_code == 200
        texte, bas = texte_de(r.text), r.text.lower()
        tete = {"fr": "Pris pour un robot à 3 niveaux sur 6", "en": "Taken for a bot at 3 levels out of 6"}
        assert tete[langue] in texte
        assert TETE_PASSE[langue] not in texte
        assert RAISONS[langue]["comportement"] in texte
        for autre, raison in RAISONS[langue].items():
            if autre != "comportement":
                assert raison not in texte
        assert HONNETE_ARRETE[langue] in texte and HONNETE_PASSE[langue] not in texte
        for nom in NOMS[langue]:
            assert nom in texte
        partage = {
            "fr": "Des détecteurs de robots m'ont pris pour un robot à 3 niveaux sur 6. Et vous ?",
            "en": "Bot detectors took me for a bot at 3 levels out of 6. What about you?",
        }[langue]
        assert partage in texte
        for detecteur in NOMS_DE_DETECTEURS:
            assert detecteur not in bas, detecteur


@pytest.mark.parametrize("langue", ["fr", "en"])
def test_les_six_familles_ont_leur_raison_et_le_singulier_est_juste(reglages_publics, langue):
    familles = ["automatisation", "comportement", "incoherence", "retouche", "cumul", "piege"]
    tout = arrete({c: [f] for c, f in zip(NIVEAUX[1:], familles, strict=True)})
    with fabriquer(reglages_publics, FauxCalcul(tout)) as client:
        ouvrir_session(client, langue)
        texte = texte_de(terminer(client).text)
        for famille in familles:
            assert RAISONS[langue][famille] in texte, famille
        assert {"fr": "à 6 niveaux sur 6", "en": "at 6 levels out of 6"}[langue] in texte
    un = arrete({"04": ["cumul", "piege"]})
    with fabriquer(reglages_publics, FauxCalcul(un)) as client2:
        client2.cookies.clear()
        ouvrir_session(client2, langue)
        texte = texte_de(terminer(client2).text)
        assert {"fr": "Pris pour un robot à 1 niveau sur 6", "en": "Taken for a bot at 1 level out of 6"}[
            langue
        ] in texte


# === 3. Moins de 4 pages =====================================================================================


@pytest.mark.parametrize("langue", ["fr", "en"])
def test_trop_peu_de_pages_terminer_ne_clot_pas(reglages_publics, langue):
    calcul = FauxCalcul(HUMAIN)
    with fabriquer(reglages_publics, calcul) as client:
        jeton = ouvrir_session(client, langue, pages=2)
        r = terminer(client)
        assert r.status_code == 200
        assert statut(reglages_publics, jeton) == "en_cours"
        assert calcul.appels == []
        assert not [c for c in r.headers.get_list("set-cookie") if "session=" in c.split(";")[0] and "=;" in c]
        sel = Selector(r.text)
        assert sel.css('a[href="/lab/social/fil"]'), "continuer la visite"
        champs = champs_du_formulaire(r.text, "/session/terminer")
        assert champs["force"] == "1" and champs["csrf"]
        texte = texte_de(r.text)
        if langue == "fr":
            assert "Encore un peu" in texte and "Continuer la visite" in texte and "Terminer quand même" in texte
            assert "il faut au moins 4 pages vues" in texte and "Vous en avez vu 2." in texte
        else:
            assert "Just a little more" in texte
            assert "you need to view at least 4 pages" in texte and "You have viewed 2." in texte
            assert "Encore un peu" not in texte and "Continuer la visite" not in texte
        ouverte = {
            "fr": "Votre session reste ouverte : la suite de votre visite est enregistrée comme avant.",
            "en": "Your session stays open: the rest of your visit is recorded as before.",
        }[langue]
        assert ouverte in texte
        assert TETE_PASSE[langue] not in texte and not sel.css("button[data-partage]")
        assert "partage.js" not in r.text
        # « Terminer quand même » : la session est close, sans calcul.
        fin = client.post("/session/terminer", data=champs, headers={"Origin": ORIGINE})
        assert fin.status_code == 200
        assert statut(reglages_publics, jeton) == "reussi"
        assert calcul.appels == []
        court = {
            "fr": "trop courte pour un verdict (moins de 4 pages vues)",
            "en": "too short for a verdict (fewer than 4 pages viewed)",
        }[langue]
        assert court in texte_de(fin.text).lower()
        assert not Selector(fin.text).css("button[data-partage]")
        # « Ma session » : même état, toujours sans calcul.
        assert court in texte_de(client.get("/session").text).lower()
        assert calcul.appels == []


def test_seuil_de_quatre_pages_exactement(reglages_publics):
    calcul = FauxCalcul(HUMAIN)
    with fabriquer(reglages_publics, calcul) as client:
        ouvrir_session(client, pages=3)
        assert statut(reglages_publics, commencer_jeton(client)) == "en_cours"
        assert terminer(client).status_code == 200 and calcul.appels == []
        collecter_une(client, 3)
        r = terminer(client)  # 4 pages : le verdict
        assert TETE_PASSE["fr"] in texte_de(r.text)
        assert len(calcul.appels) == 1


def commencer_jeton(client: TestClient) -> str:
    jeton = Selector(client.get("/lab/vitrine").text).css('meta[name="sl-session"]::attr(content)').get()
    assert jeton
    return jeton


def collecter_une(client: TestClient, i: int) -> None:
    jeton = commencer_jeton(client)
    corps = {"kind": "empreinte", "page": f"/lab/social/p/{i}", "payload": {"navigateur": {"userAgent": "essai"}}}
    assert (
        client.post(
            f"/lab/collecte?sl={jeton}", content=json.dumps(corps), headers={"Content-Type": "application/json"}
        ).status_code
        == 204
    )


# === 4. Calcul lent ===========================================================================================


@pytest.mark.parametrize("langue", ["fr", "en"])
def test_calcul_lent_page_en_cours_puis_verdict(reglages_publics, monkeypatch, langue):
    attente_courte(monkeypatch, 0.1)
    calcul = FauxCalcul(COMPORTEMENT_05_A_07, delai=0.8)
    with fabriquer(reglages_publics, calcul) as client:
        ouvrir_session(client, langue)
        r = terminer(client)
        assert r.status_code == 200
        sel = Selector(r.text)
        refresh = sel.css('head meta[http-equiv="refresh"]')
        assert len(refresh) == 1
        assert refresh.attrib["content"].replace(" ", "") == "3;url=/session"
        assert "<script" not in r.text.lower()
        assert not sel.css("button[data-partage]")
        assert "Pris pour un robot" not in r.text and "Taken for a bot" not in r.text
        assert {"fr": "Calcul de votre résultat", "en": "Calculating your result"}[langue] in texte_de(r.text)
        verdict = None
        for _ in range(60):  # le calcul continue après l'attente
            suite = client.get("/session")
            assert suite.status_code == 200
            if not Selector(suite.text).css('meta[http-equiv="refresh"]'):
                verdict = suite
                break
            time.sleep(0.1)
        assert verdict is not None, "le verdict arrive une fois le calcul fini"
        assert RAISONS[langue]["comportement"] in texte_de(verdict.text)
        assert Selector(verdict.text).css("button[data-partage]")
        assert len(calcul.appels) == 1, "un seul calcul en vol, puis le cache"


def test_resultats_rend_en_cours_puis_le_resultat_sans_recalculer(tmp_path):
    module = R()
    calcul = FauxCalcul(HUMAIN, delai=0.4)

    async def scenario():
        resultats = module.Resultats(calcul, attente=0.05)
        premier = await resultats.obtenir(tmp_path / "b.sqlite3", "a" * 32)
        assert premier is module.EN_COURS
        deuxieme = await resultats.obtenir(tmp_path / "b.sqlite3", "a" * 32)  # même jeton : pas de second calcul
        assert deuxieme is module.EN_COURS
        await asyncio.sleep(0.6)
        assert await resultats.obtenir(tmp_path / "b.sqlite3", "a" * 32) == HUMAIN
        assert len(calcul.appels) == 1

    asyncio.run(scenario())


# === 5. Calcul en échec ==========================================================================================


@pytest.mark.parametrize("langue", ["fr", "en"])
def test_calcul_en_echec_indisponible_et_gardé_en_cache(reglages_publics, langue):
    calcul = FauxCalcul(None)
    with fabriquer(reglages_publics, calcul) as client:
        jeton = ouvrir_session(client, langue)
        r = terminer(client)
        assert r.status_code == 200
        indisponible = {"fr": "n'a pas pu être calculé", "en": "could not be calculated"}[langue]
        assert indisponible in texte_de(r.text).lower()
        assert statut(reglages_publics, jeton) == "reussi"
        for page in (r.text, client.get("/session").text, client.get("/session").text):
            assert jeton in page
            assert Selector(page).css('form[action="/session/supprimer"] button')
            assert not Selector(page).css("button[data-partage]")
            assert "partage.js" not in page
        assert indisponible in texte_de(client.get("/session").text).lower()
        assert len(calcul.appels) == 1, "l'échec est gardé : un rechargement ne relance pas le calcul"


@pytest.mark.parametrize("raison", ["inconnue", "courte", "longue"])
def test_sortie_non_jugeable_du_calcul_page_sans_verdict(reglages_publics, raison):
    sortie = {"jugeable": False, "raison": raison, "pages": 9, "pages_min": 4}
    with fabriquer(reglages_publics, FauxCalcul(sortie)) as client:
        jeton = ouvrir_session(client)
        for page in (terminer(client), client.get("/session")):
            assert page.status_code == 200
            sel = Selector(page.text)
            assert not sel.css("button[data-partage]") and "partage.js" not in page.text
            assert TETE_PASSE["fr"] not in page.text and "Pris pour un robot" not in page.text
            assert jeton in page.text and sel.css('form[action="/session/supprimer"] button')
            if raison == "longue":
                assert "trop longue pour un résultat immédiat" in texte_de(page.text)
            if raison == "courte":
                assert "trop courte pour un verdict (moins de 4 pages vues)" in texte_de(page.text)


# === 6. Oracle : rien pendant la session =========================================================================


def test_pendant_la_session_aucun_resultat_meme_sans_cookie_de_session(reglages_publics):
    calcul = FauxCalcul(HUMAIN)
    with fabriquer(reglages_publics, calcul) as client:
        jeton = ouvrir_session(client, "fr", pages=6)
        en_cours = client.get("/session")
        assert en_cours.status_code == 200
        assert "Votre résultat s'affichera ici quand vous aurez terminé." in texte_de(en_cours.text)
        sans_cookie_de_session(client)
        assert not any(c.name.endswith("slp-session") for c in client.cookies.jar)
        assert statut(reglages_publics, jeton) == "en_cours"
        # Le cookie de droits suffit à retrouver la session : il ne doit rien révéler de plus.
        r = client.get("/session")
        assert r.status_code == 200
        assert jeton in r.text
        for page in (en_cours.text, r.text):
            assert TETE_PASSE["fr"] not in page and "Pris pour un robot" not in page
            assert not Selector(page).css("button[data-partage]") and "partage.js" not in page
            assert not any(nom in page for nom in NOMS["fr"][1:])
        assert calcul.appels == []


def test_pendant_la_session_en_anglais_aucun_resultat(reglages_publics):
    calcul = FauxCalcul(HUMAIN)
    with fabriquer(reglages_publics, calcul) as client:
        ouvrir_session(client, "en", pages=6)
        page = client.get("/session")
        assert TETE_PASSE["en"] not in page.text and "Human, at every level" not in page.text
        assert not Selector(page.text).css("button[data-partage]")
        assert "Your result will appear here once you have finished." in texte_de(page.text)
        assert calcul.appels == []


# === 7. Session commencée sous une ancienne notice ================================================================


def test_session_sous_une_ancienne_notice_aucun_calcul(reglages_publics):
    calcul = FauxCalcul(HUMAIN)
    with fabriquer(reglages_publics, calcul) as client:
        jeton = ouvrir_session(client, "fr", pages=6)
        cx = ouvrir(reglages_publics)
        try:
            accord = json.loads(
                cx.execute("SELECT protection_config FROM runs WHERE session_token = ?", (jeton,)).fetchone()[0]
            )
            assert accord["texte_information"] == VERSION_INFORMATION
            accord["texte_information"] = "2026-11-14.9"
            cx.execute("UPDATE runs SET protection_config = ? WHERE session_token = ?", (json.dumps(accord), jeton))
        finally:
            cx.close()
        r = terminer(client)  # ancienne notice : comme avant, la session est close, même sous 4 pages
        assert r.status_code == 200 and statut(reglages_publics, jeton) == "reussi"
        for page in (r.text, client.get("/session").text):
            assert "Votre session a commencé avant l'arrivée du résultat : il n'est pas calculé pour elle." in texte_de(
                page
            )
            assert TETE_PASSE["fr"] not in page and not Selector(page).css("button[data-partage]")
            assert jeton in page and Selector(page).css('form[action="/session/supprimer"] button')
        assert calcul.appels == []


def test_ancienne_notice_et_peu_de_pages_terminer_clot_comme_avant(reglages_publics):
    calcul = FauxCalcul(HUMAIN)
    with fabriquer(reglages_publics, calcul) as client:
        jeton = ouvrir_session(client, "fr", pages=1)
        cx = ouvrir(reglages_publics)
        try:
            cx.execute(
                "UPDATE runs SET protection_config = json_set(protection_config, '$.texte_information', '2026-11-14.9')"
                " WHERE session_token = ?",
                (jeton,),
            )
        finally:
            cx.close()
        assert terminer(client).status_code == 200
        assert statut(reglages_publics, jeton) == "reussi"
        assert calcul.appels == []


# === 8. Cache ==================================================================================================


def test_apres_terminer_ma_session_ne_rappelle_pas_le_calcul_puis_supprimer_oublie(reglages_publics):
    calcul = FauxCalcul(HUMAIN)
    with fabriquer(reglages_publics, calcul) as client:
        jeton = ouvrir_session(client)
        assert TETE_PASSE["fr"] in texte_de(terminer(client).text)
        for _ in range(3):
            assert TETE_PASSE["fr"] in texte_de(client.get("/session").text)
        assert len(calcul.appels) == 1
        page = client.get("/session")
        champs = champs_du_formulaire(page.text, "/session/supprimer")
        suppression = client.post("/session/supprimer", data=champs, headers={"Origin": ORIGINE})
        assert suppression.status_code == 200
        after = client.get("/session")
        assert TETE_PASSE["fr"] not in after.text and jeton not in after.text
        assert len(calcul.appels) == 1


def test_resultats_oublier_efface_le_cache_et_garde_les_autres(tmp_path):
    module, base = R(), tmp_path / "b.sqlite3"
    calcul = FauxCalcul(HUMAIN)

    async def scenario():
        resultats = module.Resultats(calcul, attente=1.0)
        assert await resultats.obtenir(base, "a" * 32) == HUMAIN
        assert await resultats.obtenir(base, "b" * 32) == HUMAIN
        assert len(calcul.appels) == 2
        assert await resultats.obtenir(base, "a" * 32) == HUMAIN and len(calcul.appels) == 2
        resultats.oublier("a" * 32)
        resultats.oublier("c" * 32)  # inconnu : sans effet
        assert await resultats.obtenir(base, "b" * 32) == HUMAIN and len(calcul.appels) == 2
        assert await resultats.obtenir(base, "a" * 32) == HUMAIN and len(calcul.appels) == 3

    asyncio.run(scenario())


def test_resultats_garde_aussi_l_echec_expire_et_reste_borne(tmp_path):
    module, base = R(), tmp_path / "b.sqlite3"

    async def scenario():
        echec = FauxCalcul(None)
        resultats = module.Resultats(echec, attente=1.0, duree=60, duree_echec=0.2)
        assert await resultats.obtenir(base, "a" * 32) is None
        assert await resultats.obtenir(base, "a" * 32) is None
        assert len(echec.appels) == 1
        await asyncio.sleep(0.3)  # le cache expire
        assert await resultats.obtenir(base, "a" * 32) is None
        assert len(echec.appels) == 2
        reussi = FauxCalcul(HUMAIN)
        long = module.Resultats(reussi, attente=1.0, duree=60, duree_echec=0.1)
        assert await long.obtenir(base, "a" * 32) == HUMAIN
        await asyncio.sleep(0.25)  # `duree_echec` ne vaut que pour un échec
        assert await long.obtenir(base, "a" * 32) == HUMAIN
        assert len(reussi.appels) == 1
        bornes = FauxCalcul(HUMAIN)
        petit = module.Resultats(bornes, attente=1.0, taille=2)
        for jeton in ("a", "b", "c"):
            await petit.obtenir(base, jeton * 32)
        assert len(bornes.appels) == 3
        await petit.obtenir(base, "c" * 32)
        assert len(bornes.appels) == 3
        await petit.obtenir(base, "a" * 32)  # le plus ancien est sorti du cache
        assert len(bornes.appels) == 4

    asyncio.run(scenario())


def test_resultats_un_calcul_a_la_fois_et_un_seul_par_jeton(tmp_path):
    module, base = R(), tmp_path / "b.sqlite3"
    actifs, maximum = [0], [0]
    appels = []

    async def calcul(_base, jeton):
        appels.append(jeton)
        actifs[0] += 1
        maximum[0] = max(maximum[0], actifs[0])
        await asyncio.sleep(0.1)
        actifs[0] -= 1
        return HUMAIN

    async def scenario():
        resultats = module.Resultats(calcul, attente=2.0)
        lots = [resultats.obtenir(base, j * 32) for j in "aabbcc"]
        sorties = await asyncio.gather(*lots)
        assert all(s == HUMAIN for s in sorties)
        assert sorted(appels) == ["a" * 32, "b" * 32, "c" * 32], "un seul calcul en vol par jeton"
        assert maximum[0] == 1, "un seul calcul à la fois"

    asyncio.run(scenario())


# === 9. Cookies ===================================================================================================


def test_aucun_cookie_hors_les_trois_sur_tout_le_parcours(reglages_publics):
    with fabriquer(reglages_publics, FauxCalcul(COMPORTEMENT_05_A_07)) as client:
        client.get("/")
        client.get("/en/information")
        ouvrir_session(client, "fr", pages=2)
        courte = terminer(client)  # « Encore un peu »
        fin = client.post(
            "/session/terminer",
            data=champs_du_formulaire(courte.text, "/session/terminer"),
            headers={"Origin": ORIGINE},
        )
        assert fin.status_code == 200
        client.get("/session")
        client.get("/public/static/partage.js")
        client.post(
            "/session/supprimer",
            data=champs_du_formulaire(client.get("/session").text, "/session/supprimer"),
            headers={"Origin": ORIGINE},
        )
        client.get("/session")
        assert client.cookies_posees <= COOKIES
        assert {c.name for c in client.cookies.jar} <= COOKIES
    with fabriquer(reglages_publics, FauxCalcul(COMPORTEMENT_05_A_07)) as client2:
        ouvrir_session(client2, "en", pages=5)
        assert terminer(client2).status_code == 200
        client2.get("/session")
        assert client2.cookies_posees <= COOKIES
        assert {c.name for c in client2.cookies.jar} <= COOKIES


# === 10. Partage ====================================================================================================


def test_partage_js_servi_en_javascript_et_utile(reglages_publics):
    with fabriquer(reglages_publics, FauxCalcul(HUMAIN)) as client:
        r = client.get("/public/static/partage.js")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/javascript")
        assert "navigator.share" in r.text and "clipboard" in r.text
        assert "data-partage" in r.text or "partage" in r.text
        assert r.headers["Content-Security-Policy"] == CSP


@pytest.mark.parametrize("langue", ["fr", "en"])
def test_le_jeton_n_est_ni_dans_un_data_ni_dans_le_texte_partage(reglages_publics, langue):
    with fabriquer(reglages_publics, FauxCalcul(COMPORTEMENT_05_A_07)) as client:
        jeton = ouvrir_session(client, langue)
        signes = [c.value for c in client.cookies.jar if c.name.endswith(("slp-session", "slp-droits"))]
        assert signes
        for page in (terminer(client).text, client.get("/session").text):
            sel = Selector(page)
            bouton = sel.css("button[data-partage]")
            assert bouton
            attributs = [(k, v) for e in sel.xpath("//*[@*]") for k, v in e.attrib.items() if k.startswith("data-")]
            assert attributs
            for nom, valeur in attributs:
                assert jeton not in valeur, nom
                assert not any(s in valeur or s.split(".")[0] in valeur for s in signes), nom
            assert jeton not in bouton.attrib["data-texte"]
            # Le texte partagé : une phrase et l'adresse du site, rien qui retrouve la session.
            visible = re.sub(r"\s+", " ", "".join(sel.css("[data-partage] ~ *::text, [data-partage]::text").getall()))
            assert jeton not in visible


# === 11. CSP ==========================================================================================================


def test_csp_inchangee_sur_chaque_page_de_resultat(reglages_publics, monkeypatch):
    attente_courte(monkeypatch, 0.05)
    with fabriquer(reglages_publics, FauxCalcul(HUMAIN, delai=0.3)) as client:
        ouvrir_session(client, "fr", pages=1)
        assert terminer(client).headers["Content-Security-Policy"] == CSP  # « Encore un peu »
        for i in (1, 2, 3):
            collecter_une(client, i)
        lent = terminer(client)  # « calcul en cours »
        assert lent.headers["Content-Security-Policy"] == CSP
        time.sleep(0.6)
        verdict = client.get("/session")
        assert Selector(verdict.text).css("button[data-partage]")
        assert verdict.headers["Content-Security-Policy"] == CSP


# === 12. Notice ==========================================================================================================


def test_version_de_la_notice():
    assert VERSION_INFORMATION == "2026-11-17.2"
    assert R().annonce_resultat(VERSION_INFORMATION) is True


@pytest.mark.parametrize("langue", ["fr", "en"])
def test_notice_annonce_le_resultat(reglages_publics, langue):
    with fabriquer(reglages_publics, FauxCalcul(HUMAIN)) as client:
        html = client.get(f"/{langue}/information").text
        assert html.count('id="resultat"') == 1
        assert html.index('id="pourquoi"') < html.index('id="resultat"') < html.index('id="duree"')
        section = Selector(html).css("#resultat")
        titre = {"fr": "Votre résultat", "en": "Your result"}[langue]
        assert titre in texte_de(section.get())
        assert "4" in texte_de(section.get()), "au moins 4 pages pour un verdict"
        pourquoi = textes.T[langue]["pourquoi"].lower()
        assert "hors ligne" not in pourquoi and "offline" not in pourquoi
        label = {"fr": "Terminer et voir mon résultat", "en": "End and see my result"}[langue]
        etape = {
            "fr": "Avec moins de 4 pages vues, le site vous propose de continuer la visite, ou de terminer sans résultat.",
            "en": "With fewer than 4 pages viewed, the site offers to let you keep browsing, or to end without a result.",
        }[langue]
        assert etape in texte_de(html)
        assert label in textes.T[langue]["deroulement_3"]
        assert label in texte_de(html)


def test_notice_memes_cles_dans_les_deux_langues():
    assert set(textes.T["fr"]) == set(textes.T["en"])
    assert textes.T["fr"]["terminer"] == "Terminer et voir mon résultat"
    assert textes.T["en"]["terminer"] == "End and see my result"
    for langue in ("fr", "en"):
        assert "ma session" not in textes.T[langue]["terminer"].lower()


@pytest.mark.parametrize("langue", ["fr", "en"])
def test_libelle_du_bouton_de_fin_partout(reglages_publics, langue):
    attendu = {"fr": "Terminer et voir mon résultat", "en": "End and see my result"}[langue]
    with fabriquer(reglages_publics, FauxCalcul(HUMAIN)) as client:
        ouvrir_session(client, langue)
        for chemin in ("/lab/social/fil", "/lab/vitrine", "/session"):
            bouton = Selector(client.get(chemin).text).css('form[action="/session/terminer"] button::text').get()
            assert bouton and bouton.strip() == attendu, chemin


# === 13. Accueil =======================================================================================================


@pytest.mark.parametrize("langue", ["fr", "en"])
def test_l_accueil_promet_le_resultat(reglages_publics, langue):
    attendu = {
        "fr": "Baladez-vous 2 minutes sur un faux réseau social de photos, puis découvrez si nos détecteurs vous ont pris pour un robot.",
        "en": "Spend 2 minutes on a fake photo-sharing network, then find out whether our detectors took you for a bot.",
    }[langue]
    assert textes.T[langue]["accueil_accroche"] == attendu
    with fabriquer(reglages_publics, FauxCalcul(HUMAIN)) as client:
        assert attendu in texte_de(client.get(f"/{langue}").text)


# === 14. Validation de la sortie du labo ===================================================================================


def test_valider_accepte_les_deux_formes_du_contrat():
    valider = R().valider
    assert valider(json.loads(json.dumps(HUMAIN))) == HUMAIN
    assert valider(COMPORTEMENT_05_A_07) == COMPORTEMENT_05_A_07
    tout = arrete({c: ["automatisation", "piege"] for c in NIVEAUX[1:]})
    assert valider(tout) == tout
    for raison in ("inconnue", "courte", "longue"):
        sortie = {"jugeable": False, "raison": raison, "pages": 2, "pages_min": 4}
        assert valider(sortie) == sortie


def _mauvaises_sorties() -> dict[str, object]:
    def avec(**modifs):
        sortie = json.loads(json.dumps(COMPORTEMENT_05_A_07))
        sortie.update(modifs)
        return sortie

    def niveau(i: int, **modifs):
        sortie = json.loads(json.dumps(COMPORTEMENT_05_A_07))
        sortie["niveaux"][i].update(modifs)
        return sortie

    non_jugeable = {"jugeable": False, "raison": "courte", "pages": 2, "pages_min": 4}
    return {
        "pas un dictionnaire": ["jugeable"],
        "texte": json.dumps(HUMAIN),
        "none": None,
        "vide": {},
        "code de niveau inconnu": niveau(0, code="08"),
        "profil endurance": niveau(0, code="endurance"),
        "famille inconnue": niveau(5, familles=["magie"]),
        "famille sans chaîne": niveau(5, familles=[3]),
        "familles pas une liste": niveau(5, familles="comportement"),
        "clé en trop au sommet": avec(detecteurs=["botd"]),
        "clé en trop dans un niveau": niveau(5, detecteur="botd"),
        "clé manquante dans un niveau": {
            **COMPORTEMENT_05_A_07,
            "niveaux": [{"code": "01", "arrete": False}] + COMPORTEMENT_05_A_07["niveaux"][1:],
        },
        "pages en chaîne": avec(pages="6"),
        "pages négatives": avec(pages=-1),
        "arrete en chaîne": niveau(5, arrete="oui"),
        "jugeable en chaîne": avec(jugeable="oui"),
        "niveaux pas une liste": avec(niveaux="01"),
        "six niveaux seulement": avec(niveaux=COMPORTEMENT_05_A_07["niveaux"][:6]),
        "niveaux sans clé": {k: v for k, v in COMPORTEMENT_05_A_07.items() if k != "niveaux"},
        "non jugeable : raison inconnue": {**non_jugeable, "raison": "autre"},
        "non jugeable : sans pages": {k: v for k, v in non_jugeable.items() if k != "pages"},
        "non jugeable : clé en trop": {**non_jugeable, "niveaux": []},
        "non jugeable : raison en nombre": {**non_jugeable, "raison": 1},
    }


@pytest.mark.parametrize("nom", sorted(_mauvaises_sorties()))
def test_valider_refuse_une_sortie_mal_formee(nom):
    assert R().valider(_mauvaises_sorties()[nom]) is None, nom


@pytest.mark.parametrize(
    ("version", "attendu"),
    [
        ("2026-11-17.1", True),
        ("2026-11-17.10", True),  # N compare comme un entier : 10 > 9, et pas « .1 » avant « .10 »
        ("2026-11-17.2", True),
        ("2026-11-18.1", True),
        ("2026-12-01.0", True),
        ("2026-11-17.0", False),
        ("2026-11-14.9", False),
        ("2025-12-31.99", False),
        ("2026-11-17", False),
        ("essai", False),
        ("", False),
        (None, False),
    ],
)
def test_annonce_resultat(version, attendu):
    assert R().annonce_resultat(version) is attendu


def test_constantes_du_contrat_et_accord_avec_le_labo():
    module = R()
    assert module.PAGES_MIN == 4 and module.ATTENTE_S == 4.0 and module.DELAI_MAX_S == 30.0
    assert module.DUREE_ECHEC_S == 120
    assert module.DUREE_CACHE_S == 15 * 60 and module.TAILLE_CACHE == 1000
    assert module.VERSION_MIN == ("2026-11-17", 1)
    assert module.EN_COURS is not None and module.EN_COURS is not False
    labo = importlib.import_module("shadowlab.resultat_public")  # le seul import du labo de ce fichier
    assert labo.PAGES_MIN == module.PAGES_MIN
    assert tuple(labo.NIVEAUX) == NIVEAUX
    assert tuple(labo.FAMILLES) == tuple(RAISONS["fr"])  # chaque famille du labo a sa raison ici, dans cet ordre


# === 15. Le sous-processus ===================================================================================================

FAUX_EXECUTABLE = """#!{python}
import json, os, sys, time
dossier = os.environ["FAUX_DIR"]
mode = os.environ["FAUX_MODE"]
entree = sys.stdin.read()
with open(os.path.join(dossier, "trace.json"), "w") as f:
    json.dump({{"argv": sys.argv[1:], "stdin": entree, "env": dict(os.environ)}}, f)
if mode == "valide":
    sys.stdout.write(os.environ["FAUX_SORTIE"])
elif mode == "texte":
    sys.stdout.write("pas du json")
elif mode == "gros":
    sys.stdout.write(json.dumps({{"jugeable": False, "raison": "courte", "pages": 1, "pages_min": 4, "x": "a" * 200000}}))
elif mode == "echec":
    sys.exit(1)
elif mode == "dort":
    with open(os.path.join(dossier, "pid"), "w") as f:
        f.write(str(os.getpid()))
    time.sleep(60)
"""


@pytest.fixture
def faux_labo(tmp_path, monkeypatch):
    """Un faux exécutable Python à la place de `sys.executable` : il écrit ce qu'il a reçu dans `trace.json`."""
    dossier = tmp_path / "faux"
    dossier.mkdir()
    script = dossier / "faux-python"
    script.write_text(FAUX_EXECUTABLE.format(python=sys.executable))
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setattr(sys, "executable", str(script))
    monkeypatch.setenv("FAUX_DIR", str(dossier))
    monkeypatch.setenv("SHADOWLAB_PROFILS_EXTRA", "configs/arena/profils-sans-correlation.yaml")

    def regler(mode: str, sortie: object = None):
        monkeypatch.setenv("FAUX_MODE", mode)
        monkeypatch.setenv("FAUX_SORTIE", json.dumps(sortie))
        return dossier

    return regler


JETON = "0123456789abcdef" * 2


def test_sous_processus_sortie_valide_rendue_et_jeton_par_stdin(faux_labo, tmp_path):
    dossier = faux_labo("valide", COMPORTEMENT_05_A_07)
    base = tmp_path / "public.sqlite3"
    sortie = asyncio.run(R().calculer_par_processus(base, JETON))
    assert sortie == COMPORTEMENT_05_A_07
    trace = json.loads((dossier / "trace.json").read_text())
    assert trace["argv"] == ["-m", "shadowlab.resultat_public"]
    assert JETON not in " ".join(trace["argv"]) and str(base) not in " ".join(trace["argv"])
    assert json.loads(trace["stdin"]) == {"base": str(base), "jeton": JETON}
    assert "SHADOWLAB_PROFILS_EXTRA" not in trace["env"]
    assert trace["env"]["FAUX_MODE"] == "valide", "le reste de l'environnement passe"
    assert os.environ["SHADOWLAB_PROFILS_EXTRA"], "l'environnement du site n'est pas modifié"


def test_sous_processus_sortie_non_jugeable_valide_rendue(faux_labo, tmp_path):
    sortie = {"jugeable": False, "raison": "courte", "pages": 2, "pages_min": 4}
    faux_labo("valide", sortie)
    assert asyncio.run(R().calculer_par_processus(tmp_path / "b.sqlite3", JETON)) == sortie


@pytest.mark.parametrize(
    ("mode", "sortie"),
    [
        ("valide", {"jugeable": True}),
        ("valide", {"jugeable": False, "raison": "autre", "pages": 1, "pages_min": 4}),
        ("valide", {**COMPORTEMENT_05_A_07, "detecteur": "botd"}),
        ("valide", [1, 2]),
        ("texte", None),
        ("gros", None),
        ("echec", None),
    ],
    ids=["incomplet", "raison-inconnue", "cle-en-trop", "liste", "pas-du-json", "trop-gros", "code-1"],
)
def test_sous_processus_sortie_invalide_ou_echec_donne_none(faux_labo, tmp_path, mode, sortie):
    faux_labo(mode, sortie)
    assert asyncio.run(R().calculer_par_processus(tmp_path / "b.sqlite3", JETON)) is None


def test_sous_processus_delai_depasse_donne_none_et_tue_le_processus(faux_labo, tmp_path, monkeypatch):
    dossier = faux_labo("dort")
    monkeypatch.setattr(R(), "DELAI_MAX_S", 1.0)
    debut = time.monotonic()
    assert asyncio.run(R().calculer_par_processus(tmp_path / "b.sqlite3", JETON)) is None
    assert time.monotonic() - debut < 10, "le délai réduit s'applique, le sous-processus n'est pas attendu 60 s"
    pid = int((dossier / "pid").read_text())
    for _ in range(50):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.1)
    else:
        os.kill(pid, 9)  # ne laisse rien derrière soi, puis échoue
        pytest.fail("le sous-processus n'a pas été tué")


def test_calculer_par_processus_ne_journalise_jamais_le_jeton(faux_labo, tmp_path, caplog):
    faux_labo("echec")
    with caplog.at_level("DEBUG"):
        asyncio.run(R().calculer_par_processus(tmp_path / "b.sqlite3", JETON))
    assert JETON not in caplog.text
