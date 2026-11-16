"""Palier 2, I7 : `shadowlab recolte lancer --identite <nom>` (conception § 5.6), moteur `navigateur` seulement.

Pilote factice qui se comporte comme `DriverNoezia` en mode identité (il ouvre vraiment l'identité : verrou, refus d'une
identité bannie ou en alerte, état écrit par la sentinelle). Ce que ces tests prouvent : la même identité sert deux
passes, une identité refusée donne le code 2 sans aucune requête, la sentinelle l'écrit `banni`, la reprise la
retrouve. Ce qu'ils ne prouvent pas : que Chrome rende le même VISITEUR à l'Arena (cookie `sl_visiteur`) : cela demande un
vrai Chrome sur le site du labo, voir `tests/test_moteur_navigateur.py` pour l'état de ce chantier.
"""

from __future__ import annotations

import contextlib
import json

import pytest
from outils_recolte import RECETTE_VITRINE, PiloteFactice, creer_client

from shadowlab import commande_recolte
from shadowlab.cli import main
from shadowlab.engines.noezia import identite as ident
from shadowlab.engines.noezia.parcours import MoteurDriver, RefusParcours
from shadowlab.engines.noezia.recettes import lire_texte

PAGE_REFUS = "<html><body><p>accès refusé</p></body></html>"
LISTE = "=/lab/vitrine/annonces"


class PiloteChrome(PiloteFactice):
    name = "noezia"
    runtime = "navigateur"
    executes_javascript = True

    def __init__(self, client, nom):
        super().__init__(client)
        self.nom = nom
        self._identite = None

    @property
    def identite_courante(self):
        return self._identite

    def configuration(self):
        return {"identite": self.nom}

    def open(self):
        self._identite = ident.ouvrir(self.nom)  # comme `DriverNoezia.open` : refuse bannie, alerte récente, verrou pris

    def start_session(self):
        self._identite.debut_visite()

    def close_session(self):
        self._identite.fin_visite(pages=len(self.pages_lues()))

    def close(self):
        if self._identite is not None:
            self._identite.liberer()
            self._identite = None

    def etat_page(self):
        return 200, self.urls[-1], {}


@pytest.fixture
def racine(tmp_path, monkeypatch):
    monkeypatch.setenv("SHADOWLAB_IDENTITES", str(tmp_path / "identites"))
    return tmp_path / "identites"


@pytest.fixture
def site(reglages, monkeypatch):
    with creer_client(monkeypatch) as client:
        yield client


@pytest.fixture
def demandes(site, racine, monkeypatch):
    """Les identités demandées au moteur, et le pilote de chaque passe."""
    notes = {"identites": [], "pilotes": [], "personnaliser": lambda pilote: None}

    def construire(nom, recette, reglages, identite=None):
        notes["identites"].append((nom, identite))
        pilote = PiloteChrome(site, identite or "")
        notes["personnaliser"](pilote)
        notes["pilotes"].append(pilote)
        return MoteurDriver(pilote, nom)

    monkeypatch.setattr(commande_recolte, "construire_moteur", construire)
    monkeypatch.setattr(commande_recolte, "site_du_labo", lambda recette, reglages: contextlib.nullcontext())
    return notes


def lancer(*options):
    return main(["recolte", "lancer", str(RECETTE_VITRINE), *options])


def resume(reglages, passe=1):
    dossier = reglages.sorties / "recoltes" / "vitrine-annonces" / f"passe-{passe:03d}"
    return json.loads((dossier / "resume.json").read_text(encoding="utf-8"))


def visites(racine, nom="vitrine-suivi"):
    return [json.loads(ligne) for ligne in (racine / nom / "visites.jsonl").read_text(encoding="utf-8").splitlines()]


def test_deux_lancer_avec_la_meme_identite_la_gardent(demandes, racine, reglages):
    assert lancer("--moteur", "navigateur", "--identite", "vitrine-suivi", "--pages-max", "5") == 0
    assert lancer("--moteur", "navigateur", "--identite", "vitrine-suivi", "--pages-max", "5", "--tout-refaire") == 0
    assert demandes["identites"] == [("navigateur", "vitrine-suivi")] * 2
    # un seul dossier d'identité, deux visites journalisées dedans : c'est la même identité qui est revenue
    assert [d.name for d in racine.iterdir()] == ["vitrine-suivi"]
    assert [v["statut"] for v in visites(racine)] == ["ok", "ok"]
    # la passe garde l'identité dans sa description du moteur (la reprise s'en sert)
    assert resume(reglages, 1)["moteur"]["configuration"]["identite"] == "vitrine-suivi"
    assert resume(reglages, 2)["moteur"]["configuration"]["identite"] == "vitrine-suivi"


def test_sans_l_option_aucune_identite_n_est_demandee(demandes, racine):
    assert lancer("--moteur", "navigateur", "--pages-max", "3") == 0
    assert demandes["identites"] == [("navigateur", None)]
    assert not racine.exists()


def test_l_identite_exige_le_moteur_navigateur(demandes, racine, capsys):
    assert lancer("--moteur", "http", "--identite", "vitrine-suivi") == 2
    erreur = capsys.readouterr().err
    assert "navigateur" in erreur and "--identite" in erreur
    assert demandes["pilotes"] == [] and not racine.exists()


def test_la_recette_au_moteur_http_par_defaut_refuse_aussi(demandes, capsys):
    assert lancer("--identite", "vitrine-suivi") == 2  # la recette vitrine est en `moteur: http`
    assert "navigateur" in capsys.readouterr().err


@pytest.mark.parametrize("nom", ["Majuscule", "avec espace", "../evade", "x" * 41])
def test_un_nom_d_identite_invalide_est_un_refus(demandes, nom, capsys):
    assert lancer("--moteur", "navigateur", "--identite", nom) == 2
    assert "identité" in capsys.readouterr().err and demandes["pilotes"] == []


def test_une_identite_bannie_est_un_refus_sans_aucune_requete(demandes, racine, capsys):
    prise = ident.ouvrir("vitrine-suivi")
    prise.marquer("banni", "403 dès la première page")
    prise.liberer()
    assert lancer("--moteur", "navigateur", "--identite", "vitrine-suivi") == 2
    assert "bannie" in capsys.readouterr().err
    pilote = demandes["pilotes"][0]
    assert pilote.demandes == [] and pilote.requetes_pages == 0


def test_une_identite_prise_par_un_autre_lancement_est_un_refus(demandes, racine, capsys):
    autre = ident.ouvrir("vitrine-suivi")
    try:
        assert lancer("--moteur", "navigateur", "--identite", "vitrine-suivi") == 2
    finally:
        autre.liberer()
    assert "verrou" in capsys.readouterr().err or "utilisée" in capsys.readouterr().err


def test_la_sentinelle_ecrit_l_etat_de_l_identite_pendant_la_recolte(demandes, racine):
    # la première page est refusée franchement : l'identité est bannie, et la passe s'arrête
    demandes["personnaliser"] = lambda pilote: pilote.reponses.update({LISTE: (403, PAGE_REFUS)})
    assert lancer("--moteur", "navigateur", "--identite", "vitrine-suivi") == 3
    assert demandes["pilotes"][-1].requetes_pages == 1
    assert json.loads((racine / "vitrine-suivi" / "identite.json").read_text())["etat"] == "banni"
    # et la suivante est refusée avant toute requête
    assert lancer("--moteur", "navigateur", "--identite", "vitrine-suivi") == 2


def test_la_reprise_retrouve_l_identite_de_la_passe(demandes, racine):
    def interrompre_le_premier(pilote):
        pilote.interruption_a = None if demandes["pilotes"] else 20  # Ctrl-C à la 20e page de la première passe

    demandes["personnaliser"] = interrompre_le_premier
    assert lancer("--moteur", "navigateur", "--identite", "vitrine-suivi") == 1
    assert main(["recolte", "reprendre", "vitrine-annonces"]) == 0
    assert demandes["identites"] == [("navigateur", "vitrine-suivi")] * 2


def test_identite_de_la_passe():
    assert commande_recolte.identite_de_la_passe({"moteur": {"options": {"identite": "x", "headless": False}}}) == "x"
    assert commande_recolte.identite_de_la_passe({"moteur": {"options": {"headless": False}}}) is None
    assert commande_recolte.identite_de_la_passe({"moteur": {"nom": "http"}}) is None


def test_le_vrai_moteur_navigateur_recoit_l_identite_sans_lancer_chrome(racine, reglages):
    recette = lire_texte(RECETTE_VITRINE.read_text(encoding="utf-8"))
    moteur = commande_recolte.construire_moteur("navigateur", recette, reglages, identite="vitrine-suivi")
    options = moteur.driver.options
    assert options["identite"] == "vitrine-suivi" and options["identite_native"] is True and options["headless"] is False
    assert moteur.description()["options"]["identite"] == "vitrine-suivi"
    with pytest.raises(RefusParcours, match="navigateur"):
        commande_recolte.construire_moteur("http", recette, reglages, identite="vitrine-suivi")
    assert "identite" not in commande_recolte.construire_moteur("navigateur", recette, reglages).driver.options
