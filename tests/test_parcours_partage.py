"""Étape 4.2 : une visite d'une identité sur une récolte partagée (`Parcours.visiter_partage`).

Pilotes factices d'identité sur le `TestClient` du site du labo (vitrine à 45 annonces, 48 pages). Ce que ces tests
prouvent : plusieurs identités se relaient sur une seule passe et chaque page est lue une fois ; une identité bannie en
route s'arrête à la page refusée sans rien demander de plus, cette page revient en file et une autre la lit ; l'alerte
d'une identité n'arrête pas la passe ; une visite sans page à prendre n'ouvre pas de navigateur et ne vole pas les pages
d'une identité vivante ; celles d'une identité coupée net reviennent en file ; deux identités en même temps (deux fils)
ne demandent jamais la même page ; les compteurs d'une visite sont les siens ; la borne de la recette vaut pour la
récolte entière. Aucun navigateur.
"""

from __future__ import annotations

import json
import random
import threading
import time

import pytest
from outils_identites import PiloteIdentite, parcours_partage
from outils_recolte import GRAINE, RECETTE_VITRINE, TAILLE, Coupure, creer_client

from shadowlab import notation
from shadowlab.engines.noezia import identite as ident
from shadowlab.engines.noezia.etat import Etat
from shadowlab.engines.noezia.gestionnaire import verrou_travailleur
from shadowlab.engines.noezia.lecture import LectureHumaine
from shadowlab.engines.noezia.parcours import Options
from shadowlab.site import vitrine

PAGES = TAILLE + 3  # 45 fiches, 3 pages de liste


@pytest.fixture
def racine(tmp_path, monkeypatch):
    monkeypatch.setenv("SHADOWLAB_IDENTITES", str(tmp_path / "identites"))
    return tmp_path / "identites"


@pytest.fixture
def site(reglages, monkeypatch, racine):
    with creer_client(monkeypatch) as client:
        yield client


def _etat(dossier):
    return Etat(dossier / "etat.sqlite3")


def _visite(dossier, site, nom, pages, **reglages):
    pilote = PiloteIdentite(site, nom, bannir_a=reglages.pop("bannir_a", None))
    parcours = parcours_partage(dossier, pilote, **reglages)
    return parcours.visiter_partage(nom, pages), pilote


def _jusqu_au_bout(dossier, site, nom, pages, tours=20):
    for _ in range(tours):
        bilan, _ = _visite(dossier, site, nom, pages)
        if bilan.statut in ("terminee", "finie"):
            return bilan
    raise AssertionError("la récolte n'a pas fini")


def _notes(dossier):
    etat = _etat(dossier)
    try:
        attendues = vitrine.pages_attendues(GRAINE, TAILLE)
        pages = notation.noter_pages(attendues, etat.adresses_couvertes(1))
        recolte = notation.noter_recolte(etat.enregistrements("annonces"), vitrine.verite(GRAINE, TAILLE))
        return pages, recolte, etat.compteurs(1), etat.pages_par_identite(1)
    finally:
        etat.fermer()


def test_trois_identites_se_relaient_chaque_page_lue_une_fois(tmp_path, site):
    dossier = tmp_path / "recolte"
    noms = ["ident-a", "ident-b", "ident-c"]
    statuts = []
    for tour in range(20):
        bilan, _ = _visite(dossier, site, noms[tour % 3], 7)
        statuts.append(bilan.statut)
        if bilan.statut == "terminee":
            break
    assert statuts[-1] == "terminee" and set(statuts[:-1]) == {"limitee"}
    assert bilan.resume["travail_fini"] is True
    assert (dossier / "passe-001" / "resume.json").exists()  # écrit par la visite qui a fini la passe
    pages, recolte, compteurs, par_identite = _notes(dossier)
    assert pages["completude_pages"] == 1.0
    assert recolte["completude"] == 1.0 and recolte["exactitude"] == 1.0
    assert compteurs["faites"] == PAGES and compteurs["a_faire"] == 0 and compteurs["en_cours"] == 0
    assert set(par_identite) == set(noms)
    assert sum(v["lues"] for v in par_identite.values()) == PAGES
    etat = _etat(dossier)
    try:
        assert etat.passe(1)["statut"] == "terminee"
        assert [i["nom"] for i in etat.identites(1)] == noms
        assert sum(i["visites"] for i in etat.identites(1)) == len(statuts)
    finally:
        etat.fermer()


def test_identite_bannie_en_route_s_arrete_et_sa_page_revient(tmp_path, site, racine):
    dossier = tmp_path / "recolte"
    _visite(dossier, site, "ident-a", 5)
    bilan_b, pilote_b = _visite(dossier, site, "ident-b", 10, bannir_a=3)
    assert bilan_b.statut == "arretee" and bilan_b.code == 3
    assert pilote_b.requetes_pages == 3  # rien demandé après la page refusée
    assert json.loads((racine / "ident-b" / "identite.json").read_text())["etat"] == "banni"
    page_refusee = pilote_b.urls[-1]
    etat = _etat(dossier)
    try:
        assert etat.passe(1)["statut"] == "en_cours"  # l'alerte d'une identité n'arrête pas la récolte
        assert etat.en_cours_par_identite(1) == {}
        rendues = [e["detail"] for e in etat.evenements(1) if e["genre"] == "rendue"]
        assert len(rendues) == 1 and rendues[0]["identite"] == "ident-b" and rendues[0]["adresse"] == page_refusee
        assert rendues[0]["signe"] == "statut"
    finally:
        etat.fermer()
    # une identité bannie ne resservira jamais : son pilote refuse de s'ouvrir, et la page prise est rendue
    with pytest.raises(ident.IdentiteRefusee):
        _visite(dossier, site, "ident-b", 10)
    _jusqu_au_bout(dossier, site, "ident-c", 10)
    pages, recolte, compteurs, par_identite = _notes(dossier)
    assert pages["completude_pages"] == 1.0 and recolte["exactitude"] == 1.0
    assert compteurs["faites"] == PAGES
    assert par_identite["ident-b"]["lues"] == 2  # ses deux pages lues avant le refus
    etat = _etat(dossier)
    try:
        lue_par = {ligne["adresse"]: ligne["identite"] for ligne in etat.lignes_pages(1)}
        assert lue_par[page_refusee] == "ident-c"  # la page refusée à ident-b, relue par ident-c
    finally:
        etat.fermer()


def test_visite_sans_page_a_prendre_n_ouvre_pas_le_navigateur(tmp_path, site):
    dossier = tmp_path / "recolte"
    _visite(dossier, site, "ident-a", 1)  # la liste 1, lue
    verrou = verrou_travailleur(dossier, "ident-z")  # ident-z travaille (processus vivant) et tient tout le reste
    etat = _etat(dossier)
    try:
        while etat.prochaine(1, identite="ident-z") is not None:
            pass
        tenues = etat.en_cours_par_identite(1)["ident-z"]
    finally:
        etat.fermer()
    bilan, pilote = _visite(dossier, site, "ident-b", 5)
    assert bilan.statut == "attente" and bilan.code == 0 and bilan.resume["travail_fini"] is False
    assert pilote.sessions == 0 and pilote.requetes_pages == 0 and not pilote.urls
    etat = _etat(dossier)
    try:
        assert etat.en_cours_par_identite(1) == {"ident-z": tenues}  # rien volé à une identité vivante
    finally:
        etat.fermer()
    # ident-z est coupée net (son verrou de travail se libère) : ses pages reviennent en file, ident-b les lit
    verrou.close()
    bilan, pilote = _visite(dossier, site, "ident-b", 5)
    assert bilan.statut == "limitee" and pilote.requetes_pages == 5
    etat = _etat(dossier)
    try:
        assert etat.en_cours_par_identite(1) == {}
        orphelines = [e["detail"] for e in etat.evenements(1) if e["genre"] == "orphelines"]
        assert orphelines == [{"identite": "ident-b", "rendues": {"ident-z": tenues}}]
    finally:
        etat.fermer()


def test_passe_finie_rien_a_faire(tmp_path, site):
    dossier = tmp_path / "recolte"
    _jusqu_au_bout(dossier, site, "ident-a", 20)
    bilan, pilote = _visite(dossier, site, "ident-b", 5)
    assert bilan.statut == "finie" and bilan.resume["travail_fini"] is True
    assert pilote.sessions == 0 and not pilote.urls


def test_les_compteurs_d_une_visite_sont_les_siens(tmp_path, site):
    dossier = tmp_path / "recolte"
    bilan_a, _ = _visite(dossier, site, "ident-a", 6)
    bilan_b, _ = _visite(dossier, site, "ident-b", 4)
    assert bilan_a.resume["lancement"]["pages"] == 6
    assert bilan_b.resume["lancement"]["pages"] == 4
    assert bilan_b.resume["identite"] == "ident-b"
    assert not (dossier / "passe-001" / "resume.json").exists()  # la passe n'est pas finie : aucun export


def test_une_coupure_en_pleine_visite_rend_les_pages_de_l_identite(tmp_path, site):
    dossier = tmp_path / "recolte"
    _visite(dossier, site, "ident-a", 2)
    pilote = PiloteIdentite(site, "ident-b")
    pilote.coupure_a = 2
    with pytest.raises(Coupure):
        parcours_partage(dossier, pilote).visiter_partage("ident-b", 10)
    etat = _etat(dossier)
    try:
        assert etat.en_cours_par_identite(1) == {}
        assert etat.pages_restantes(1)[1] == 0
    finally:
        etat.fermer()


def test_avec_la_lecture_humaine_une_visite_qui_reprend_entre_par_la_liste(tmp_path, site):
    dossier = tmp_path / "recolte"
    _visite(dossier, site, "ident-a", 4, options=Options(lecture=LectureHumaine()))
    bilan, pilote = _visite(dossier, site, "ident-b", 4, options=Options(lecture=LectureHumaine()))
    pages_demandees = [u for u in pilote.demandes if not u.startswith("/robots.txt")]
    assert pages_demandees[0].startswith("/lab/vitrine/annonces") and "AN-" not in pages_demandees[0]
    assert bilan.statut in ("limitee", "terminee")


def test_la_borne_de_la_recette_vaut_pour_toute_la_recolte(tmp_path, site):
    dossier = tmp_path / "recolte"
    texte = RECETTE_VITRINE.read_text(encoding="utf-8")
    texte = texte.replace("rythme: libre", "rythme: libre\nbornes: {pages_max: 10}")
    bilan_a, _ = _visite(dossier, site, "ident-a", 6, texte=texte)
    bilan_b, _ = _visite(dossier, site, "ident-b", 6, texte=texte)
    assert bilan_a.resume["lancement"]["pages"] == 6 and bilan_a.statut == "limitee"
    assert bilan_b.resume["lancement"]["pages"] == 4 and bilan_b.resume["travail_fini"] is True
    bilan_c, pilote_c = _visite(dossier, site, "ident-c", 6, texte=texte)
    assert bilan_c.statut == "limitee" and bilan_c.resume["travail_fini"] is True and pilote_c.sessions == 0
    etat = _etat(dossier)
    try:
        assert etat.compteurs(1)["lues"] == 10 and etat.passe(1)["statut"] == "limitee"
    finally:
        etat.fermer()


def test_deux_identites_en_meme_temps_ne_demandent_jamais_la_meme_page(tmp_path, reglages, monkeypatch, racine):
    dossier = tmp_path / "recolte"
    visites: list[tuple[str, str, list[str]]] = []
    erreurs: list[BaseException] = []
    clients = [creer_client(monkeypatch), creer_client(monkeypatch)]

    def travailler(nom, client):
        try:
            for tour in range(400):
                pilote = PiloteIdentite(client, nom)
                bilan = parcours_partage(dossier, pilote, alea=random.Random(tour)).visiter_partage(nom, 3)
                visites.append((nom, bilan.statut, list(pilote.demandes)))
                if bilan.statut in ("terminee", "finie"):
                    return
                if bilan.statut == "attente":
                    time.sleep(0.01)
        except BaseException as erreur:  # noqa: BLE001 — remonté au fil principal
            erreurs.append(erreur)

    with clients[0], clients[1]:
        fils = [
            threading.Thread(target=travailler, args=(nom, client))
            for nom, client in zip(("ident-a", "ident-b"), clients, strict=True)
        ]
        for f in fils:
            f.start()
        for f in fils:
            f.join(timeout=120)
    assert not erreurs, erreurs
    pages, recolte, compteurs, par_identite = _notes(dossier)
    assert compteurs["faites"] == PAGES and recolte["exactitude"] == 1.0 and pages["completude_pages"] == 1.0
    lues = [d for _, _, demandes in visites for d in demandes if not d.startswith("/robots.txt")]
    assert len(lues) == len(set(lues)) == PAGES  # aucune page demandée deux fois, par la même ou une autre identité
    assert set(par_identite) == {"ident-a", "ident-b"}


def test_une_recolte_partagee_ne_rejoint_jamais_une_passe_simple(tmp_path, site):
    """Une passe lancée sans identités (`recolte lancer`) n'est jamais rejointe par une identité : sa reprise remettrait
    en file les pages des identités vivantes, et inversement."""
    from outils_recolte import PiloteFactice, fabriquer

    from shadowlab.engines.noezia.parcours import RefusParcours

    dossier = tmp_path / "recolte"
    fabriquer(dossier, PiloteFactice(site), options=Options(pages_max=3)).lancer()  # passe simple, limitée
    pilote = PiloteIdentite(site, "ident-a")
    with pytest.raises(RefusParcours, match="sans identités"):
        parcours_partage(dossier, pilote).visiter_partage("ident-a", 5)
    assert pilote.sessions == 0 and not pilote.urls


def test_une_passe_partagee_ne_se_reprend_pas_comme_une_passe_simple(tmp_path, site):
    from outils_recolte import PiloteFactice, fabriquer

    from shadowlab.engines.noezia.parcours import RefusParcours

    dossier = tmp_path / "recolte"
    _visite(dossier, site, "ident-a", 3)
    pilote = PiloteFactice(site)
    with pytest.raises(RefusParcours, match="partagée"):
        fabriquer(dossier, pilote).reprendre()
    with pytest.raises(RefusParcours, match="partagée"):
        fabriquer(dossier, pilote).visiter(5)
    assert not pilote.urls
