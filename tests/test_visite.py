"""Palier 2, I7 : le scénario `visite` (une visite de la vitrine par un visiteur qui revient).

Pilote factice branché sur le `TestClient` du site du labo : ni réseau, ni navigateur. Ce que ces tests établissent :
la visite lit au plus N pages (15 par défaut), note le visiteur vu par l'Arena (jamais le cookie signé), note l'état de
l'identité du pilote, et passe par le parcours de la récolte (sentinelle, identité, porte d'entrée) ; une identité
refusée par l'Arena (403 avec la vraie page de refus) est notée `banni`, sans autre requête.
"""

from __future__ import annotations

import json
import random

import pytest
from outils_recolte import GRAINE, PiloteFactice
from test_sentinelle import PiloteNavigateur
from test_visiteurs import nouveau_passage, nouvelle_experience

from shadowlab import scenarios
from shadowlab.engines.noezia import identite as ident
from shadowlab.engines.noezia.sentinelle import detecter_defi
from shadowlab.scenarios import SCENARIOS
from shadowlab.site import pages

BASE = "http://127.0.0.1:8770"
TAILLE = 45
MONDE = "c-visite:sujet:endurance"


class Chrome(PiloteNavigateur):
    """Se fait passer pour `noezia` (un navigateur, JavaScript, page relue sur place)."""

    name = "noezia"


class ChromeAvecIdentite(Chrome):
    """Comme `DriverNoezia` en mode identité : expose son identité, note la visite à la fermeture de la session."""

    def __init__(self, client, identite):
        super().__init__(client)
        self.identite_courante = identite
        identite.debut_visite()

    def close_session(self):
        self.identite_courante.fin_visite(pages=len(self.pages_lues()))


@pytest.fixture
def site(reglages, monkeypatch):
    from fastapi.testclient import TestClient

    from shadowlab.config import charger
    from shadowlab.site.app import creer_app

    monkeypatch.setenv("SHADOWLAB_VITRINE_TAILLE", str(TAILLE))
    monkeypatch.setenv("SHADOWLAB_VITRINE_GRAINE", str(GRAINE))
    with TestClient(creer_app(charger()), base_url="http://127.0.0.1") as c:
        yield c


@pytest.fixture(autouse=True)
def lecture_instantanee(monkeypatch):
    """La lecture humaine du scénario garde ses retours à la liste, mais n'attend rien (aucune durée : test rapide)."""
    from shadowlab.engines.noezia.lecture import LectureHumaine

    monkeypatch.setattr(scenarios, "LECTURE_HUMAINE_VISITE", LectureHumaine(duree_s=(0, 0, 0)))


@pytest.fixture
def jeton(reglages):
    return nouveau_passage(reglages, nouvelle_experience(reglages, "visite"), monde=MONDE)


@pytest.fixture
def racine(tmp_path, monkeypatch):
    monkeypatch.setenv("SHADOWLAB_IDENTITES", str(tmp_path / "identites"))
    return tmp_path / "identites"


def visiter(pilote, jeton, pages=None):
    scenario = SCENARIOS["visite"] if pages is None else scenarios.avec_pages(pages)
    return scenario.executer(pilote, BASE, jeton, random.Random(1))


def test_le_scenario_visite_est_declare_et_lit_15_pages_par_defaut():
    assert "visite" in SCENARIOS and SCENARIOS["visite"].attend_js is True
    assert scenarios.PAGES_PAR_VISITE == 15


def test_la_visite_lit_au_plus_n_pages_la_liste_puis_des_fiches_avec_des_retours_a_la_liste(site, jeton):
    pilote = Chrome(site)
    issue = visiter(pilote, jeton, pages=6)
    assert issue.success is True, issue.details
    lues = [d.split("?")[0] for d in pilote.pages_lues()]
    assert lues[0] == "/lab/vitrine/annonces"  # la liste d'abord
    assert "/lab/vitrine/annonces/AN-" in lues[1] and lues[2] == "/lab/vitrine/annonces"  # retour après la 1re fiche
    assert all(d == "/lab/vitrine/annonces" or "/lab/vitrine/annonces/AN-" in d for d in lues)
    assert len(lues) == 6 == issue.details["pages_faites"] + issue.details["relectures"]  # budget, jamais en plus
    assert issue.details["statut"] == "limitee" and issue.details["pages_demandees"] == 6


def test_la_visite_par_defaut_lit_15_pages(site, jeton):
    pilote = Chrome(site)
    issue = visiter(pilote, jeton)
    assert issue.success is True and len(pilote.pages_lues()) == 15
    assert issue.details["pages_faites"] + issue.details["relectures"] == 15 and issue.details["relectures"] >= 1


def test_la_visite_note_le_visiteur_vu_par_l_arena_jamais_le_cookie_signe(site, jeton, reglages):
    issue = visiter(Chrome(site), jeton, pages=3)
    cookie = site.cookies.get("sl_visiteur")
    assert cookie and "." in cookie  # le navigateur porte `<visiteur>.<signature>`
    visiteur, signature = cookie.split(".")
    assert issue.details["visiteur"] == visiteur and issue.details["monde"] == MONDE
    assert issue.details["visite_neuve"] is True
    texte = json.dumps(issue.details)
    assert signature not in texte and cookie not in texte
    # une seconde visite avec le même cookie : le même visiteur, qui n'est plus neuf
    jeton2 = nouveau_passage(reglages, 1, repetition=2, monde=MONDE)
    issue2 = visiter(Chrome(site), jeton2, pages=3)
    assert issue2.details["visiteur"] == visiteur and issue2.details["visite_neuve"] is False


def test_sans_arena_le_visiteur_n_est_pas_connu(site):
    issue = visiter(Chrome(site), "ef" * 16, pages=2)  # un jeton qui n'appartient à aucun passage
    assert issue.details["monde"] == "hors-passage"


def test_la_visite_note_l_etat_de_l_identite(site, jeton, racine):
    ouverte = ident.ouvrir("sujet-essai")
    try:
        issue = visiter(ChromeAvecIdentite(site, ouverte), jeton, pages=3)
    finally:
        ouverte.liberer()
    assert issue.success is True
    assert issue.details["identite"] == {"nom": "sujet-essai", "etat": "ok"}


def test_sans_identite_rien_n_est_note(site, jeton):
    assert visiter(Chrome(site), jeton, pages=2).details["identite"] is None


def test_un_refus_de_l_arena_a_la_premiere_page_est_un_bannissement_et_rien_n_est_redemande(site, jeton, racine):
    """La vraie page de refus (`data-arena="blocage"`) n'est pas un défi à attendre : c'est un refus franc."""
    ouverte = ident.ouvrir("sentinelle-essai")
    pilote = ChromeAvecIdentite(site, ouverte)
    pilote.reponses["annonces?sl="] = (403, pages.page_blocage())  # la liste, avec le jeton du passage
    pilote.statut_actuel = 403  # le navigateur y est toujours : la page n'a pas changé seule
    try:
        issue = visiter(pilote, jeton, pages=6)
    finally:
        ouverte.liberer()
    assert issue.success is False
    assert pilote.requetes_pages == 1  # le refus lui-même, aucune requête après
    assert pilote.relectures <= 1  # au plus un regard sur place (sans requête ni attente) : ce n'est pas une porte
    assert issue.details["identite"]["etat"] == "banni"
    assert issue.details["arret"]["statut"] == 403
    assert json.loads((racine / "sentinelle-essai" / "identite.json").read_text())["etat"] == "banni"


def test_la_page_de_refus_de_l_arena_n_est_pas_un_defi():
    assert detecter_defi(pages.page_blocage(), {}) is None
    # les vrais défis restent reconnus
    assert detecter_defi(pages.page_defi("pow", 12, "/lab/"), {}) == "arena"


def test_un_pilote_sans_navigateur_peut_visiter(site, jeton):
    """Le témoin classique (`playwright`) passe par le même chemin : aucun refus d'outil (sur un site sans défi)."""

    class Playwright(PiloteFactice):
        name = "playwright"
        runtime = "navigateur"
        executes_javascript = True

    issue = visiter(Playwright(site), jeton, pages=3)
    assert issue.success is True and issue.details["moteur"] == "navigateur"


# ── L'état de l'identité est relu avant chaque visite (les visites 4 à 6 d'une identité bannie font 0 requête) ──


def test_verifier_etat_refuse_une_identite_bannie_en_cours_de_route(racine):
    ouverte = ident.ouvrir("a")
    try:
        ouverte.verifier_etat()  # ok
        ouverte.marquer("banni", "403 dès la première page")
        with pytest.raises(ident.IdentiteRefusee, match="bannie"):
            ouverte.verifier_etat()
    finally:
        ouverte.liberer()


def test_verifier_etat_refuse_une_alerte_de_moins_d_une_heure(racine):
    from datetime import UTC, datetime, timedelta

    t0 = datetime(2026, 11, 16, 10, 0, tzinfo=UTC)
    ouverte = ident.ouvrir("a", horloge=lambda: t0 + timedelta(minutes=10))
    try:
        ouverte.marquer("alerte", "statut 429", quand=t0)
        with pytest.raises(ident.IdentiteRefusee, match="alerte"):
            ouverte.verifier_etat()
        ouverte._horloge = lambda: t0 + timedelta(hours=1)
        ouverte.verifier_etat()
    finally:
        ouverte.liberer()


def test_start_session_relit_l_etat_avant_de_lancer_chrome(racine, monkeypatch):
    """Pas de navigateur ici : si l'état est relu, Chrome n'est jamais lancé pour une identité bannie."""
    from shadowlab.engines.noezia.moteur import DriverNoezia

    pilote = DriverNoezia(
        ("127.0.0.1",), {"identite_native": True, "headless": False, "channel": "chrome", "identite": "a"}
    )
    pilote._identite = ident.ouvrir("a")
    try:
        pilote._identite.marquer("banni", "403 dès la première page")

        def jamais(*_):
            raise AssertionError("Chrome ne doit pas être lancé pour une identité bannie")

        monkeypatch.setattr(pilote, "_lancer_identite", jamais)
        with pytest.raises(ident.IdentiteRefusee, match="bannie"):
            pilote.start_session()
    finally:
        pilote._identite.liberer()


def test_un_pilote_javascript_sans_etat_de_page_est_arrete_a_la_porte_par_l_outil(site, jeton):
    """Comportement réel du témoin classique (`playwright`) devant le défi de l'Arena, noté pour ne pas l'oublier : sans
    `etat_page` le parcours ne peut pas relire la page, il ne laisse pas au défi le temps de se valider seul et arrête
    la visite tout de suite sur `defi`. C'est l'outil qui arrête, pas l'empreinte : `refus_par_l_arena` du bilan de la
    soirée dépend de ce que l'Arena a vu pendant ce premier chargement."""
    from test_sentinelle import PAGE_ARENA

    class Playwright(PiloteFactice):
        name = "playwright"
        runtime = "navigateur"
        executes_javascript = True

    pilote = Playwright(site)
    pilote.reponses["annonces?sl="] = (403, PAGE_ARENA)
    issue = visiter(pilote, jeton, pages=6)
    assert issue.success is False and issue.details["arret"]["signe"] == "defi"
    assert pilote.requetes_pages == 1 and issue.details["identite"] is None
