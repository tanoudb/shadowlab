"""Scénario `recolte_vitrine` : parcours complet du site vitrine à travers un pilote d'essai, sans navigateur."""

import random
from urllib.parse import urlsplit

import pytest
from parsel import Selector

from shadowlab.engines.base import Driver, ResultatNavigation
from shadowlab.scenarios import SCENARIOS

GRAINE = 20261112
TAILLE = 45
BASE = "http://127.0.0.1"


class PiloteEssai(Driver):
    """Pilote minimal branché sur l'application en mémoire. N'exécute pas de JavaScript."""

    name = "essai"
    runtime = "http"

    def __init__(self, client, pages_perdues=(), page_refusee=None):
        super().__init__(("*",))
        self.client = client
        self.pages_perdues = set(pages_perdues)  # pages de la liste dont les fiches disparaissent
        self.page_refusee = page_refusee  # page de la liste servie en 403 + page de protection
        self.vues: list[str] = []
        self._texte = ""

    def versions(self):
        return {"essai": "0"}

    def start_session(self):
        pass

    def close_session(self):
        pass

    def navigate(self, url):
        morceaux = urlsplit(url)
        chemin = f"{morceaux.path}?{morceaux.query}"
        self.vues.append(chemin)
        reponse = self.client.get(chemin)
        texte = reponse.text
        status = reponse.status_code
        if self.page_refusee and f"page={self.page_refusee}" in chemin:
            status, texte = 403, "<html><body data-arena='blocage'>Refusé</body></html>"
        for page in self.pages_perdues:
            if f"page={page}" in chemin:
                texte = texte.replace('class="fiche"', 'class="masque"')
        self._texte = texte
        return ResultatNavigation(status, url, 0.0)

    def content(self):
        return self._texte

    def texts(self, selector):
        return Selector(self._texte).css(f"{selector}::text").getall()

    def click(self, selector):
        raise NotImplementedError

    def fill(self, selector, value):
        raise NotImplementedError

    def select(self, selector, value):
        raise NotImplementedError

    def wait_for_element(self, selector, timeout_ms=5000):
        raise NotImplementedError


@pytest.fixture
def client_recolte(reglages, monkeypatch):
    monkeypatch.setenv("SHADOWLAB_VITRINE_TAILLE", str(TAILLE))
    monkeypatch.setenv("SHADOWLAB_VITRINE_GRAINE", str(GRAINE))
    from fastapi.testclient import TestClient

    from shadowlab.config import charger
    from shadowlab.site.app import creer_app

    with TestClient(creer_app(charger()), base_url=BASE) as c:
        yield c


def lancer(pilote):
    return SCENARIOS["recolte_vitrine"].executer(pilote, BASE, "jeton-test", random.Random(1))


def test_scenario_enregistre():
    assert "recolte_vitrine" in SCENARIOS


def test_recolte_complete_donne_1_et_1(client_recolte):
    pilote = PiloteEssai(client_recolte)
    issue = lancer(pilote)
    note = issue.details["recolte"]
    assert note["completude"] == 1 and note["exactitude"] == 1
    assert note["annonces_retrouvees"] == TAILLE and note["champs_exacts"] == TAILLE * 14
    assert issue.success is True
    # 3 pages de liste + 45 fiches, chacune demandée avec le jeton de session.
    assert len(pilote.vues) == 3 + TAILLE
    assert all("sl=jeton-test" in v for v in pilote.vues)


def test_page_perdue_complétude_inférieure_à_1(client_recolte):
    issue = lancer(PiloteEssai(client_recolte, pages_perdues=[2]))
    note = issue.details["recolte"]
    assert note["completude"] == (TAILLE - 20) / TAILLE
    assert note["exactitude"] == 1
    assert len(note["references_manquantes"]) == 20
    assert issue.success is False


def test_refus_en_cours_de_route_note_la_recolte_partielle(client_recolte):
    issue = lancer(PiloteEssai(client_recolte, page_refusee=2))
    note = issue.details["recolte"]
    assert note["annonces_retrouvees"] == 20 and note["completude"] == 20 / TAILLE
    assert note["exactitude"] == 1
    assert "refus" in issue.details
    assert issue.success is False
