"""Moteur `navigateur` de la récolte : l'adaptateur de `DriverNoezia` en identité native (ni navigateur, ni réseau)."""

from __future__ import annotations

import pytest
from outils_recolte import RECETTE_VITRINE

from shadowlab import commande_recolte
from shadowlab.engines.noezia.moteur import DriverNoezia
from shadowlab.engines.noezia.navigateur import MoteurNavigateur
from shadowlab.engines.noezia.parcours import MoteurDriver
from shadowlab.engines.noezia.recettes import lire_texte

OPTIONS_LABO = {
    "headless": False,
    "channel": "chrome",
    "identite_native": True,
    "interaction_post_page": True,
    "verifier_tls": False,
    "resoudre_defis": True,
}


def recette_de(hote: str):
    texte = RECETTE_VITRINE.read_text(encoding="utf-8").replace("127.0.0.1", hote)
    return lire_texte(texte)


@pytest.fixture
def labo():
    return recette_de("127.0.0.1")


@pytest.fixture
def tiers():
    return recette_de("exemple.fr")


def test_construire_moteur_navigateur_rend_le_bon_adaptateur_sans_lancer_de_navigateur(labo, reglages):
    moteur = commande_recolte.construire_moteur("navigateur", labo, reglages)
    assert isinstance(moteur, MoteurNavigateur) and isinstance(moteur, MoteurDriver)
    assert isinstance(moteur.driver, DriverNoezia) and moteur.nom == "navigateur"
    assert moteur.driver.options == OPTIONS_LABO
    assert moteur.driver._navigateur is None and moteur.driver._pw is None  # rien n'est lancé à la construction


def test_le_moteur_http_reste_le_defaut(labo, reglages):
    moteur = commande_recolte.construire_moteur("http", labo, reglages)
    assert not isinstance(moteur, MoteurNavigateur) and moteur.nom == "http"


def test_moteur_inconnu_refuse(labo, reglages):
    with pytest.raises(Exception, match="moteur"):
        commande_recolte.construire_moteur("firefox", labo, reglages)


def test_identite_native_seulement(labo, reglages):
    options = commande_recolte.construire_moteur("navigateur", labo, reglages).driver.options
    assert options["identite_native"] is True and options["headless"] is False and options["channel"] == "chrome"
    assert "profil" not in options and "locale" not in options  # aucun réglage d'empreinte


def test_resoudre_defis_coupe_hors_du_labo_local(tiers, reglages):
    moteur = commande_recolte.construire_moteur("navigateur", tiers, reglages)
    assert moteur.driver.options["resoudre_defis"] is False
    assert moteur.driver.options["verifier_tls"] is True  # vrai hors du labo local


def test_resoudre_defis_actif_sur_le_labo_local(labo, reglages):
    moteur = commande_recolte.construire_moteur("navigateur", labo, reglages)
    assert moteur.driver.options["resoudre_defis"] is True and moteur.driver.options["verifier_tls"] is False


def test_un_site_a_moitie_local_n_a_pas_de_resolution_de_defis(reglages):
    texte = RECETTE_VITRINE.read_text(encoding="utf-8").replace("hotes: [127.0.0.1]", "hotes: [127.0.0.1, exemple.fr]")
    moteur = commande_recolte.construire_moteur("navigateur", lire_texte(texte), reglages)
    assert moteur.driver.options["resoudre_defis"] is False


def test_verifier_tls_est_une_option_declaree_de_type_bool():
    assert DriverNoezia.options_permises["verifier_tls"] is bool
    with pytest.raises(ValueError, match="verifier_tls"):
        DriverNoezia(("*",), {"verifier_tls": "oui"})


def test_verifier_tls_apparait_dans_la_configuration_enregistree():
    assert DriverNoezia(("*",), {"verifier_tls": True}).configuration()["verifier_tls"] is True
    assert DriverNoezia(("*",), {}).configuration()["verifier_tls"] is False  # défaut du labo : certificat local


def test_les_hotes_de_la_recette_gardent_la_navigation(labo, tiers, reglages):
    assert commande_recolte.construire_moteur("navigateur", labo, reglages).driver.hotes_navigation == ("127.0.0.1",)
    assert commande_recolte.construire_moteur("navigateur", tiers, reglages).driver.hotes_navigation == ("exemple.fr",)


def test_le_perimetre_du_labo_reste_celui_de_reglages(labo, reglages):
    moteur = commande_recolte.construire_moteur("navigateur", labo, reglages)
    assert moteur.driver.hotes_autorises == reglages.hotes_autorises


def test_description_complete_pour_resume_json(labo, reglages):
    pytest.importorskip("patchright")
    description = commande_recolte.construire_moteur("navigateur", labo, reglages).description()
    assert description["nom"] == "navigateur" and description["pilote"] == "noezia"
    assert description["options"] == OPTIONS_LABO
    assert description["configuration"]["identite_native"] is True
    assert description["configuration"]["headless"] is False and description["configuration"]["channel"] == "chrome"
    assert "patchright" in description["versions"]
    assert description["hotes_recette"] == ["127.0.0.1"] and description["perimetre"] == list(reglages.hotes_autorises)
    assert "sous-ressources" in description["charge_de_lui_meme"]


class _Cadre:
    parent_frame = None


class _Requete:
    def __init__(self, url, navigation, cadre=None):
        self.url = url
        self._navigation = navigation
        self.frame = cadre or _Cadre()
        self.resource_type = "document" if navigation else "script"
        self.headers = {}

    def is_navigation_request(self):
        return self._navigation


class _Route:
    def __init__(self, requete):
        self.request = requete
        self.decision = None

    def abort(self, raison=None):
        self.decision = ("abort", raison)

    def continue_(self, **kwargs):
        self.decision = ("continue", kwargs)


def pilote_garde(hotes_navigation, hotes_autorises=("*",)):
    pilote = DriverNoezia(hotes_autorises, {"identite_native": True, "headless": False, "channel": "chrome"})
    pilote.hotes_navigation = hotes_navigation
    pilote.mesures.details["requetes_bloquees"] = 0
    return pilote


def test_une_navigation_vers_un_hote_hors_recette_est_coupee():
    pilote = pilote_garde(("127.0.0.1",))
    route = _Route(_Requete("http://autre.example/connexion", navigation=True))
    pilote._filtrer(route)
    assert route.decision == ("abort", "blockedbyclient") and pilote.mesures.details["requetes_bloquees"] == 1


def test_une_navigation_vers_un_hote_de_la_recette_passe():
    pilote = pilote_garde(("127.0.0.1",))
    route = _Route(_Requete("http://127.0.0.1:8770/lab/vitrine/annonces", navigation=True))
    pilote._filtrer(route)
    assert route.decision == ("continue", {})


def test_une_sous_ressource_d_un_autre_hote_n_est_pas_filtree_par_la_recette():
    """Limite voulue : la règle « hôte de la recette » ne porte que sur les pages (navigations du cadre principal)."""
    pilote = pilote_garde(("127.0.0.1",))
    route = _Route(_Requete("https://cdn.example/app.js", navigation=False))
    pilote._filtrer(route)
    assert route.decision == ("continue", {})


def test_sans_garde_le_comportement_de_noezia_est_inchange():
    pilote = pilote_garde(None)
    route = _Route(_Requete("http://autre.example/x", navigation=True))
    pilote._filtrer(route)
    assert route.decision == ("continue", {})
