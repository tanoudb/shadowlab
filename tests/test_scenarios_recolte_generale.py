"""Scénarios `recolte_recette_vitrine` et `recolte_recette_rallye` : la récolte générale dans un passage de campagne.

Pilote factice branché sur le `TestClient` du site du labo : ni réseau, ni navigateur, ni serveur. Ce que ces tests
établissent : les deux scénarios notent pages, enregistrements et champs à 100 % sur un site complet ; le moteur du
passage est refusé s'il n'est pas pris en charge ; le jeton de session et l'adresse d'entrée du passage (donc le niveau
de l'Arena) arrivent jusqu'à chaque requête du parcours, `robots.txt` compris ; les deux campagnes sont valides.
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from outils_recolte import GRAINE, TAILLE, PiloteFactice

from shadowlab.engines.base import FonctionIndisponible
from shadowlab.scenarios import SCENARIOS

RACINE = Path(__file__).resolve().parents[1]
JETON = "ab" * 16
BASE_ARENA = "https://localhost:8743"  # l'entrée de l'Arena, là où le niveau du passage s'applique
BASE_SITE = "http://127.0.0.1:8770"
TAILLE_RALLYE = 3


class PiloteCurl(PiloteFactice):
    name = "curl-cffi"


class PiloteNavigateur(PiloteFactice):
    """Se fait passer pour `noezia` en identité native (le moteur `navigateur` de la récolte), sans navigateur."""

    name = "noezia"
    runtime = "navigateur"

    def __init__(self, client, native: bool = True):
        super().__init__(client)
        self.options = {"headless": False, "channel": "chrome", "identite_native": native}
        self.hotes_navigation = None


@pytest.fixture
def client(monkeypatch):
    from fastapi.testclient import TestClient

    from shadowlab.config import charger
    from shadowlab.site.app import creer_app

    monkeypatch.setenv("SHADOWLAB_VITRINE_TAILLE", str(TAILLE))
    monkeypatch.setenv("SHADOWLAB_VITRINE_GRAINE", str(GRAINE))
    monkeypatch.setenv("SHADOWLAB_RALLYE_TAILLE", str(TAILLE_RALLYE))
    monkeypatch.setenv("SHADOWLAB_RALLYE_GRAINE", str(GRAINE))
    with TestClient(creer_app(charger()), base_url="http://127.0.0.1") as c:
        yield c


def lancer(nom, pilote, base=BASE_SITE, jeton=JETON):
    return SCENARIOS[nom].executer(pilote, base, jeton, random.Random(1))


def test_les_deux_scenarios_sont_declares():
    for nom in ("recolte_recette_vitrine", "recolte_recette_rallye"):
        assert nom in SCENARIOS and SCENARIOS[nom].name == nom
    assert "recolte_vitrine" in SCENARIOS  # l'ancien scénario reste


@pytest.mark.parametrize(
    ("nom", "attendu_pages"),
    [("recolte_recette_vitrine", 3 + TAILLE), ("recolte_recette_rallye", None)],
)
def test_note_a_100_pour_cent_avec_le_moteur_http(client, nom, attendu_pages):
    issue = lancer(nom, PiloteCurl(client))
    note = issue.details["recolte"]
    assert note["pages"] == 1.0 and note["enregistrements"] == 1.0 and note["champs"] == 1.0, issue.details
    assert issue.success is True
    assert issue.details["moteur"] == "http" and issue.details["statut"] == "terminee"
    if attendu_pages is not None:
        assert note["pages_lues"] == attendu_pages
    json.dumps(issue.details)  # la campagne l'enregistre en JSON


def test_note_a_100_pour_cent_avec_le_moteur_navigateur(client):
    pilote = PiloteNavigateur(client)
    issue = lancer("recolte_recette_vitrine", pilote)
    note = issue.details["recolte"]
    assert issue.success is True and note["champs"] == 1.0
    assert issue.details["moteur"] == "navigateur"
    assert pilote.hotes_navigation is None  # remis comme avant à la fin du passage


def test_un_moteur_non_pris_en_charge_est_refuse(client):
    class PilotePlaywright(PiloteFactice):
        name = "playwright"

    with pytest.raises(FonctionIndisponible) as erreur:
        lancer("recolte_recette_vitrine", PilotePlaywright(client))
    message = str(erreur.value)
    assert "playwright" in message and "curl-cffi" in message and "identité native" in message


def test_noezia_sans_identite_native_est_refuse(client):
    with pytest.raises(FonctionIndisponible, match="identité native"):
        lancer("recolte_recette_vitrine", PiloteNavigateur(client, native=False))


def test_le_jeton_et_le_niveau_du_passage_arrivent_a_chaque_requete(client):
    """Le niveau de l'Arena se lit dans le jeton `sl` (table `runs`) : sans lui, `PROFIL_SANS_SESSION`.
    Chaque adresse demandée, `robots.txt` compris, porte donc le jeton et l'entrée du passage (l'Arena)."""
    pilote = PiloteCurl(client)
    issue = lancer("recolte_recette_vitrine", pilote, base=BASE_ARENA)
    assert issue.success is True, issue.details
    assert len(pilote.urls) >= 3 + TAILLE
    for adresse in pilote.urls:
        morceaux = urlsplit(adresse)
        assert f"{morceaux.scheme}://{morceaux.netloc}" == BASE_ARENA, adresse
        assert parse_qs(morceaux.query).get("sl") == [JETON], adresse  # une seule fois


def test_la_recette_du_passage_vise_l_entree_du_passage_et_ignore_le_jeton():
    from shadowlab.scenarios import recette_du_passage

    recette, texte = recette_du_passage("rallye-demo", BASE_ARENA)
    assert [d.url for d in recette.depart] == [f"{BASE_ARENA}/lab/rallye/saisons"]
    assert recette.hotes == ["localhost"]
    assert "sl" in recette.parametres_ignores
    assert "rallye-demo" in texte


@pytest.mark.parametrize("fichier", ["recolte-generale.yaml", "recolte-generale-essai.yaml"])
def test_les_campagnes_sont_valides(reglages, fichier):
    from shadowlab.campaigns import lire

    experience = lire(RACINE / "configs" / "experiments" / fichier, reglages)
    assert [m.nom_affiche for m in experience.engines] == ["curl-cffi", "noezia"]
    noezia = experience.engines[1]
    assert noezia.options == {"headless": False, "channel": "chrome", "identite_native": True}
    assert experience.protections == ["01"]
    assert experience.scenarios == ["recolte_recette_vitrine", "recolte_recette_rallye"]
    assert experience.repetitions == (3 if fichier == "recolte-generale.yaml" else 1)
