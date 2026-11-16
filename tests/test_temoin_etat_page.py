"""Le témoin classique `playwright` doit pouvoir attendre un défi JavaScript, comme `noezia` (campagne 126).

Sans `etat_page`, `MoteurDriver.relire` rend None : la porte d'entrée abandonne aussitôt (« toujours là après 0 s »)
et l'Arena n'a jamais l'occasion de juger le témoin. `etat_page()` doit avoir le contrat de `DriverNoezia` :
`(statut, adresse, en-têtes en minuscules)` de la dernière page du cadre principal, tel que le navigateur en est là.

Les tests rapides n'ouvrent aucun navigateur (page et réponse simulées) ; le test d'intégration lance un vrai Chromium
sur le site du labo, sans l'Arena.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from outils_recolte import PiloteFactice, creer_client, fabriquer
from test_sentinelle import PAGE_ARENA, PiloteNavigateur, avec_porte

from shadowlab import campaigns
from shadowlab.engines import registre
from shadowlab.engines.noezia.moteur import DriverNoezia
from shadowlab.engines.patchright_engine import DriverPatchright
from shadowlab.engines.playwright_engine import DriverPlaywright


def _pilote_simule(cls, statut=200, adresse="http://127.0.0.1:8770/lab/x", entetes=None):
    pilote = cls(("*",))
    pilote._page = SimpleNamespace(url=adresse)
    pilote._reponse = SimpleNamespace(status=statut, headers=entetes or {"Content-Type": "text/html", "X-Test": "1"})
    return pilote


@pytest.mark.parametrize("cls", [DriverPlaywright, DriverPatchright])
def test_le_pilote_playwright_expose_etat_page_avec_le_contrat_de_noezia(cls):
    pilote = _pilote_simule(cls, statut=403, adresse="http://h/defi")
    statut, adresse, entetes = pilote.etat_page()
    assert (statut, adresse) == (403, "http://h/defi")
    assert entetes == {"content-type": "text/html", "x-test": "1"}  # clés en minuscules, comme DriverNoezia
    # même contrat que le pilote noezia : mêmes paramètres, même type de retour
    assert DriverNoezia.etat_page.__annotations__["return"] == cls.etat_page.__annotations__["return"]


def test_etat_page_sans_reponse_rend_statut_none_et_adresse_courante():
    pilote = DriverPlaywright(("*",))
    pilote._page = SimpleNamespace(url="about:blank")
    pilote._reponse = None
    assert pilote.etat_page() == (None, "about:blank", {})


class PlaywrightSansNavigateur(DriverPlaywright):
    """Le vrai `DriverPlaywright` (donc son `etat_page`), la page venant d'un pilote factice : ni réseau ni Chromium."""

    def __init__(self, client):
        super().__init__(("*",))
        self.faux = PiloteNavigateur(client)
        self.dom_apres = []
        self.relectures = 0
        self._frais = False
        self._page = SimpleNamespace(url="")
        self._reponse = None

    def open(self):
        self.faux.open()

    def close(self):
        self.faux.close()

    def start_session(self):
        self.faux.start_session()

    def close_session(self):
        self.faux.close_session()

    def navigate(self, url):
        resultat = self.faux.navigate(url)
        self._page.url = url
        self._reponse = SimpleNamespace(status=resultat.status, headers={})
        self._frais = True
        return resultat

    def dom(self):
        if self._frais:
            self._frais = False
        else:
            self.relectures += 1
            if self.dom_apres:
                self.faux._texte = self.dom_apres.pop(0)
        return self.faux._texte


def test_devant_le_defi_le_pilote_playwright_attend_comme_noezia(tmp_path, reglages, monkeypatch):
    with creer_client(monkeypatch) as client:
        pilote = PlaywrightSansNavigateur(client)
        pilote.faux.reponses["=/lab/vitrine/annonces"] = (200, PAGE_ARENA)
        vraie_liste = client.get("/lab/vitrine/annonces").text
        pilote.dom_apres = [PAGE_ARENA, PAGE_ARENA, vraie_liste]  # le défi se résout seul dans le navigateur
        p = fabriquer(tmp_path / "recolte", pilote, texte=avec_porte())
        bilan = p.lancer()
    assert bilan.code == 0 and bilan.resume["pages"]["faites"] == 48
    assert pilote.relectures == 3 and sum(p.horloge_factice.pauses) == pytest.approx(2)
    assert bilan.resume["porte_entree"] == {"defi": "arena", "franchie": True, "attente_s": 2.0}


def test_un_defi_qui_ne_se_leve_pas_est_attendu_la_meme_duree_que_pour_noezia(tmp_path, reglages, monkeypatch):
    with creer_client(monkeypatch) as client:
        pilote = PlaywrightSansNavigateur(client)
        pilote.faux.reponses["=/lab/vitrine/annonces"] = (200, PAGE_ARENA)
        p = fabriquer(tmp_path / "recolte", pilote, texte=avec_porte())
        bilan = p.lancer()
    assert bilan.code == 3 and bilan.arret["signe"] == "defi"
    assert sum(p.horloge_factice.pauses) == pytest.approx(15)  # la règle de la porte, inchangée


def test_le_pilote_factice_avec_etat_page_attend_la_resolution_du_defi(tmp_path, reglages, monkeypatch):
    """Garde du côté parcours : un pilote muni d'`etat_page` voit la porte attendre (comportement déjà en place)."""
    with creer_client(monkeypatch) as client:
        pilote = PiloteNavigateur(client)
        pilote.reponses["=/lab/vitrine/annonces"] = (200, PAGE_ARENA)
        pilote.dom_apres_attente = [PAGE_ARENA, client.get("/lab/vitrine/annonces").text]
        p = fabriquer(tmp_path / "recolte", pilote, texte=avec_porte())
        bilan = p.lancer()
    assert bilan.code == 0 and sum(p.horloge_factice.pauses) == pytest.approx(1)
    assert isinstance(pilote, PiloteFactice)


@pytest.mark.integration
@pytest.mark.parametrize("moteur", ["playwright"])
def test_etat_page_dans_un_vrai_chromium_sur_le_site_du_labo(reglages, moteur):
    with campaigns.serveur_local(reglages):
        pilote = registre()[moteur](("127.0.0.1", "localhost"))
        pilote.open()
        try:
            pilote.start_session()
            pilote.navigate(f"{reglages.url_site}/lab/vitrine/annonces")
            statut, adresse, entetes = pilote.etat_page()
            assert statut == 200 and adresse.endswith("/lab/vitrine/annonces")
            assert "text/html" in entetes["content-type"]
            assert all(cle == cle.lower() for cle in entetes)
            pilote.navigate(f"{reglages.url_site}/lab/introuvable-du-temoin")
            assert pilote.etat_page()[0] == 404
            pilote.close_session()
        finally:
            pilote.close()
