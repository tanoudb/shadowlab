"""Étape 4.2 : la commande `shadowlab recolte lancer <recette> --moteur navigateur --identites a,b,c` (et `etat`,
`reprendre`), et la vie d'une identité dans une récolte partagée (`gestionnaire.vie_d_une_identite`).

Sans navigateur ni réseau : pilotes d'identité factices sur le `TestClient` du site du labo, travailleurs dans des fils
(`commande_recolte.EN_FILS`) au lieu de processus. Ce que ces tests établissent :
1. une identité visite à SON rythme (ordonnanceur de D-90 tiré de SA graine) jusqu'à la fin de la récolte ; bannie, elle
   ne visite plus jamais ; en alerte, elle attend la fin de l'alerte (1 h) ; une visite sans rien à prendre n'est pas
   comptée par l'ordonnanceur ;
2. la commande : trois identités, une bannie en route, les deux autres finissent ; 100 % des pages, champs exacts ;
   `etat` montre chaque identité et la file ; `reprendre` reprend avec les identités de la passe, sans les bannies ;
   refus avant toute requête : moteur http, identité copiée, `--identite` et `--identites` ensemble.
"""

from __future__ import annotations

import json
import random
import shutil
from datetime import datetime, timedelta

import pytest
from outils_identites import PiloteIdentite
from outils_recolte import GRAINE, RECETTE_VITRINE, TAILLE, creer_client

from shadowlab import commande_recolte, notation
from shadowlab.cli import main
from shadowlab.engines.noezia import gestionnaire
from shadowlab.engines.noezia import identite as ident
from shadowlab.engines.noezia.etat import Etat
from shadowlab.engines.noezia.lecture import LectureHumaine
from shadowlab.engines.noezia.parcours import Bilan, MoteurDriver
from shadowlab.site import vitrine

PAGES = TAILLE + 3


# ── 1. La vie d'une identité ─────────────────────────────────────────────────────────────────────


class Horloge:
    def __init__(self):
        self.t = datetime(2026, 11, 19, 10, 0).astimezone()
        self.pauses: list[float] = []

    def __call__(self):
        return self.t

    def dormir(self, secondes):
        self.pauses.append(secondes)
        self.t += timedelta(seconds=secondes)


def _bilan(statut, pages, fini=False):
    resume = {"lancement": {"pages": pages, "echecs": 0, "relectures": 0}, "travail_fini": fini}
    return Bilan(0, statut, 1, None, resume, None)


@pytest.fixture
def racine(tmp_path, monkeypatch):
    monkeypatch.setenv("SHADOWLAB_IDENTITES", str(tmp_path / "identites"))
    return tmp_path / "identites"


def test_une_identite_visite_a_son_rythme_jusqu_a_la_fin(racine):
    horloge = Horloge()
    vues = []
    suite = iter([_bilan("limitee", 10), _bilan("limitee", 10), _bilan("terminee", 4, fini=True)])

    def visiter(pages, alea):
        vues.append((horloge(), pages, alea.random()))
        return next(suite)

    rythme = gestionnaire.Rythme(pages=10, ecart_min=20, plage=(0, 24))
    fin = gestionnaire.vie_d_une_identite("ident-a", 1234, visiter, rythme, horloge=horloge, dormir=horloge.dormir)
    assert fin == "fini" and len(vues) == 3
    assert [p for _, p, _ in vues] == [10, 10, 10]
    assert vues[1][0] - vues[0][0] == timedelta(minutes=20)  # l'écart est compté de la fin d'une visite
    assert vues[0][2] == random.Random("1234:visite:1").random()  # les hasards de la visite : de SA graine


def test_deux_identites_ne_tirent_jamais_la_meme_suite(racine):
    tirages = {}
    for nom, graine in (("ident-a", 1), ("ident-b", 2)):
        horloge = Horloge()
        vues = []

        def visiter(pages, alea, vues=vues):
            vues.append((pages, alea.random()))
            return _bilan("terminee", pages, fini=len(vues) == 3)

        gestionnaire.vie_d_une_identite(
            nom, graine, visiter, gestionnaire.Rythme(), horloge=horloge, dormir=horloge.dormir
        )
        tirages[nom] = vues
    assert tirages["ident-a"] != tirages["ident-b"]


def test_une_identite_bannie_ne_visite_plus_jamais(racine):
    ouverte = ident.ouvrir("ident-a")
    ouverte.marquer("banni", "statut 403 (motif bannissement)")
    ouverte.liberer()
    horloge = Horloge()
    fin = gestionnaire.vie_d_une_identite(
        "ident-a", 1, lambda p, a: pytest.fail("visite d'une bannie"), gestionnaire.Rythme(), horloge=horloge,
        dormir=horloge.dormir,
    )  # fmt: skip
    assert fin == "bannie"


def test_une_identite_bannie_en_visite_s_arrete_la(racine):
    horloge = Horloge()

    def visiter(pages, alea):
        ouverte = ident.ouvrir("ident-a", maintenant=True)
        ouverte.marquer("banni", "statut 403 (motif bannissement)")
        ouverte.liberer()
        return _bilan("arretee", 2)

    fin = gestionnaire.vie_d_une_identite(
        "ident-a", 1, visiter, gestionnaire.Rythme(), horloge=horloge, dormir=horloge.dormir
    )
    assert fin == "bannie"


def test_une_identite_en_alerte_attend_la_fin_de_l_alerte(racine):
    horloge = Horloge()
    vues = []

    def visiter(pages, alea):
        vues.append(horloge())
        if len(vues) == 1:
            ouverte = ident.ouvrir("ident-a", maintenant=True)
            ouverte.marquer("alerte", "statut 429", horloge())
            ouverte.liberer()
            return _bilan("arretee", 3)
        return _bilan("terminee", 5, fini=True)

    rythme = gestionnaire.Rythme(pages=10, ecart_min=5, plage=(0, 24))
    assert (
        gestionnaire.vie_d_une_identite("ident-a", 1, visiter, rythme, horloge=horloge, dormir=horloge.dormir) == "fini"
    )
    assert vues[1] - vues[0] >= timedelta(seconds=ident.ATTENTE_ALERTE_S)


def test_une_visite_sans_rien_a_prendre_n_est_pas_comptee(racine):
    horloge = Horloge()
    vues = []
    suite = iter([_bilan("attente", 0), _bilan("attente", 0), _bilan("terminee", 7, fini=True)])

    def visiter(pages, alea):
        vues.append(horloge())
        return next(suite)

    rythme = gestionnaire.Rythme(pages=10, ecart_min=60, plage=(0, 24))
    gestionnaire.vie_d_une_identite(
        "ident-a", 1, visiter, rythme, horloge=horloge, dormir=horloge.dormir, attente_file_s=30
    )
    assert [(v - vues[0]).total_seconds() for v in vues] == [0, 30, 60]  # pas 60 minutes : rien n'a été lu


def test_le_rythme_par_defaut_est_celui_de_d90():
    o = gestionnaire.Rythme().ordonnanceur(1, Horloge(), lambda s: None)
    assert (o.reglages.plage, o.reglages.pages_par_heure, o.reglages.pages_par_jour) == ((8, 23), 120, 200)
    assert (o.reglages.ecart_min_min, o.reglages.ecart_max_min) == (45, 180)


# ── 2. La commande ───────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def site(reglages, monkeypatch):
    with creer_client(monkeypatch) as client:
        yield client


@pytest.fixture
def pilotes(site, monkeypatch):
    """Un pilote d'identité factice par visite, dans des fils ; `bannir` : {identité: n-ième page refusée}."""
    bannir: dict[str, int] = {}
    construits: list[PiloteIdentite] = []

    def construire(nom, recette, reglages, identite=None):
        bannir_a = None
        if identite in bannir:  # la n-ième page demandée par l'identité, toutes visites comprises
            deja = sum(p.requetes_pages for p in construits if p.nom == identite)
            bannir_a = max(1, bannir[identite] - deja)
        pilote = PiloteIdentite(site, identite, bannir_a=bannir_a)
        construits.append(pilote)
        return MoteurDriver(pilote, nom)

    monkeypatch.setattr(commande_recolte, "construire_moteur", construire)
    monkeypatch.setattr(commande_recolte, "EN_FILS", True)
    monkeypatch.setattr(commande_recolte, "ATTENTE_FILE_S", 0.01)
    monkeypatch.setattr(commande_recolte, "LECTURE_PARTAGEE", LectureHumaine(duree_s=(0, 0, 0)))
    return bannir, construits


RAPIDE = ["--pages-visite", "8", "--ecart", "0.001", "--plage", "0-24"]


def lancer(*options):
    return main(["recolte", "lancer", str(RECETTE_VITRINE), "--moteur", "navigateur", *options])


def test_trois_identites_une_bannie_en_route_les_autres_finissent(pilotes, reglages, racine, capsys):
    bannir, construits = pilotes
    bannir["ident-b"] = 3
    assert lancer("--identites", "ident-a,ident-b,ident-c", *RAPIDE) == 0
    sortie = capsys.readouterr().out
    assert "ARRÊT de l'identité ident-b" in sortie
    dossier = reglages.sorties / "recoltes" / "vitrine-annonces"
    etat = Etat(dossier / "etat.sqlite3")
    try:
        assert etat.passe(1)["statut"] == "terminee"
        par_identite = etat.pages_par_identite(1)
        note = notation.noter_recolte(etat.enregistrements("annonces"), vitrine.verite(GRAINE, TAILLE))
        pages = notation.noter_pages(vitrine.pages_attendues(GRAINE, TAILLE), etat.adresses_couvertes(1))
        identites = {i["nom"]: i for i in etat.identites(1)}
    finally:
        etat.fermer()
    assert note["completude"] == 1.0 and note["exactitude"] == 1.0 and pages["completude_pages"] == 1.0
    assert par_identite["ident-b"]["lues"] == 2 and sum(v["lues"] for v in par_identite.values()) == PAGES
    assert set(identites) == {"ident-a", "ident-b", "ident-c"}
    assert json.loads((racine / "ident-b" / "identite.json").read_text())["etat"] == "banni"
    # rien demandé par ident-b après son refus : sa dernière visite s'arrête sur la page refusée
    de_b = [p for p in construits if p.nom == "ident-b"]
    assert sum(1 for p in de_b if p.statuts and p.statuts[-1] == 403) == 1
    assert [p.statuts[-1] for p in de_b if p.statuts][-1] == 403
    resume = json.loads((dossier / "passe-001" / "resume.json").read_text())
    assert set(resume["identites"]) == {"ident-a", "ident-b", "ident-c"}

    assert main(["recolte", "etat", "vitrine-annonces"]) == 0
    texte = capsys.readouterr().out
    assert "identités : 3" in texte and "ident-b · banni" in texte and "file : 0 à faire, 0 en cours" in texte


def test_refus_avant_toute_requete(pilotes, racine, capsys):
    _, construits = pilotes
    assert main(["recolte", "lancer", str(RECETTE_VITRINE), "--identites", "ident-a,ident-b"]) == 2  # moteur http
    assert "navigateur" in capsys.readouterr().err
    assert lancer("--identites", "ident-a", "--identite", "ident-b") == 2
    gestionnaire.preparer_identite("ident-a")
    shutil.copytree(racine / "ident-a", racine / "ident-c", ignore=shutil.ignore_patterns("verrou"))
    assert lancer("--identites", "ident-a,ident-c", *RAPIDE) == 2
    assert "graine" in capsys.readouterr().err
    assert construits == []


def test_reprendre_avec_les_identites_de_la_passe_sans_les_bannies(pilotes, reglages, racine, capsys):
    bannir, _ = pilotes
    bannir["ident-a"] = 1
    bannir["ident-b"] = 1  # les deux tombent à leur première page : la récolte s'arrête, rien n'est perdu
    assert lancer("--identites", "ident-a,ident-b", *RAPIDE) == 3
    dossier = reglages.sorties / "recoltes" / "vitrine-annonces"
    etat = Etat(dossier / "etat.sqlite3")
    try:
        assert etat.passe(1)["statut"] == "arretee" and etat.compteurs(1)["en_cours"] == 0
    finally:
        etat.fermer()
    capsys.readouterr()
    # toutes bannies : `reprendre` sans nouvelle identité est un refus
    assert main(["recolte", "reprendre", "vitrine-annonces", *RAPIDE]) == 2
    assert "bannies" in capsys.readouterr().err
    assert main(["recolte", "reprendre", "vitrine-annonces", "--identites", "ident-c", *RAPIDE]) == 0
    etat = Etat(dossier / "etat.sqlite3")
    try:
        assert etat.passe(1)["statut"] == "terminee" and etat.compteurs(1)["faites"] == PAGES
        assert [i["nom"] for i in etat.identites(1)] == ["ident-a", "ident-b", "ident-c"]
    finally:
        etat.fermer()
