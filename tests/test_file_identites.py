"""Étape 4.2 : la file d'adresses de la récolte partagée entre plusieurs identités (base de la récolte, `etat.py`).

Ce que ces tests prouvent : une adresse n'est prise que par une identité à la fois ; une identité qui tombe rend ses
seules adresses ; une identité morte (processus tué) laisse ses adresses en cours, que les autres reprennent dès que
son verrou de travail est libre ; à la fin, chaque adresse est faite une fois, sans perte ni doublon, même avec
plusieurs processus sur le même fichier ; une base d'avant reçoit la colonne ; le délai d'attente de SQLite est
explicite. Aucun navigateur.
"""

from __future__ import annotations

import multiprocessing
import os
import signal
import sqlite3
import time

import pytest

from shadowlab.engines.noezia.etat import Etat
from shadowlab.engines.noezia.gestionnaire import travailleur_vivant, verrou_travailleur

QUAND = "2026-11-19T10:00:00+00:00"


def _ouvrir(etat: Etat) -> int:
    return etat.ouvrir_passe(
        recette="essai",
        empreinte="sha256:abc",
        texte_recette="recette: 1\n",
        chemin_recette="configs/recettes/essai.yaml",
        moteur={"nom": "navigateur"},
        options={"tranche": {}},
        quand=QUAND,
    )


@pytest.fixture
def etat(tmp_path):
    e = Etat(tmp_path / "etat.sqlite3")
    yield e
    e.fermer()


def _remplir(etat: Etat, passe: int, n: int) -> None:
    etat.empiler(passe, [(f"http://127.0.0.1/fiche/{i}", "fiche") for i in range(n)])


def test_une_page_prise_ne_sert_qu_une_identite(etat):
    passe = _ouvrir(etat)
    _remplir(etat, passe, 2)
    a = etat.prochaine(passe, identite="ident-a")
    b = etat.prochaine(passe, identite="ident-b")
    assert a is not None and b is not None and a.id != b.id
    assert etat.prochaine(passe, identite="ident-c") is None
    assert etat.en_cours_par_identite(passe) == {"ident-a": 1, "ident-b": 1}


def test_rendre_vide_le_porteur_et_la_page_resert(etat):
    passe = _ouvrir(etat)
    _remplir(etat, passe, 1)
    page = etat.prochaine(passe, identite="ident-a")
    etat.rendre(page)
    assert etat.en_cours_par_identite(passe) == {}
    reprise = etat.prochaine(passe, identite="ident-b")
    assert reprise is not None and reprise.id == page.id
    assert etat.en_cours_par_identite(passe) == {"ident-b": 1}


def test_rendre_de_ne_rend_que_les_pages_de_l_identite(etat):
    passe = _ouvrir(etat)
    _remplir(etat, passe, 4)
    etat.prochaine(passe, identite="ident-a")
    etat.prochaine(passe, identite="ident-a")
    etat.prochaine(passe, identite="ident-b")
    assert etat.rendre_de(passe, "ident-a") == 2
    assert etat.en_cours_par_identite(passe) == {"ident-b": 1}
    assert etat.pages_restantes(passe) == (3, 1)


def test_la_reprise_d_une_passe_ne_vole_pas_les_pages_d_une_identite_vivante(etat):
    """`liberer_orphelines` ne rend que les pages des identités qui ne travaillent plus (verrou libre)."""
    passe = _ouvrir(etat)
    _remplir(etat, passe, 3)
    etat.prochaine(passe, identite="vivante")
    etat.prochaine(passe, identite="morte")
    rendues = etat.liberer_orphelines(passe, lambda nom: nom == "vivante")
    assert rendues == {"morte": 1}
    assert etat.en_cours_par_identite(passe) == {"vivante": 1}
    assert etat.pages_restantes(passe) == (2, 1)


def test_la_page_faite_garde_le_nom_de_l_identite_qui_l_a_lue(etat):
    passe = _ouvrir(etat)
    _remplir(etat, passe, 2)
    page = etat.prochaine(passe, identite="ident-a")
    etat.terminer_page(page, etat="faite", decision="ok", quand=QUAND, statut=200)
    page = etat.prochaine(passe, identite="ident-b")
    etat.terminer_page(page, etat="echec", decision="echec", quand=QUAND, statut=500)
    assert etat.pages_par_identite(passe) == {"ident-a": {"lues": 1, "echecs": 0}, "ident-b": {"lues": 1, "echecs": 1}}


def test_sans_identite_rien_ne_change(etat):
    """Une récolte à une seule identité (ou sans) prend ses pages comme avant : aucun porteur noté."""
    passe = _ouvrir(etat)
    _remplir(etat, passe, 1)
    page = etat.prochaine(passe)
    assert page is not None
    assert etat.en_cours_par_identite(passe) == {}
    assert etat.pages_restantes(passe) == (0, 1)


def test_terminer_si_finie_seulement_sans_page_a_faire_ni_en_cours(etat):
    passe = _ouvrir(etat)
    _remplir(etat, passe, 1)
    assert not etat.terminer_si_finie(passe, QUAND)  # une page à faire
    page = etat.prochaine(passe, identite="ident-a")
    assert not etat.terminer_si_finie(passe, QUAND)  # une page en cours : elle peut encore échouer et revenir
    etat.terminer_page(page, etat="faite", decision="ok", quand=QUAND, statut=200)
    assert etat.terminer_si_finie(passe, QUAND)
    assert etat.passe(passe)["statut"] == "terminee"
    assert not etat.terminer_si_finie(passe, QUAND)  # une seule identité la termine


def test_passe_partagee_ouverte_une_fois_puis_rejointe(etat):
    """Plusieurs identités démarrent : la première ouvre la passe (départs empilés), les autres la rejoignent ; une
    passe finie n'est jamais rouverte par une identité (le travail est fait)."""
    commun = dict(
        recette="essai", empreinte="sha256:abc", texte_recette="recette: 1\n", chemin_recette="r.yaml",
        moteur={"nom": "navigateur"}, options={}, departs=[("http://127.0.0.1/liste", "liste")],
    )  # fmt: skip
    premiere, statut = etat.passe_partagee(**commun, quand=QUAND)
    assert statut == "ouverte"
    assert etat.pages_restantes(premiere) == (1, 0)
    seconde, statut = etat.passe_partagee(**commun, quand=QUAND)
    assert (seconde, statut) == (premiere, "rejointe")
    page = etat.prochaine(premiere, identite="ident-a")
    etat.terminer_page(page, etat="faite", decision="ok", quand=QUAND, statut=200)
    assert etat.terminer_si_finie(premiere, QUAND)
    assert etat.passe_partagee(**commun, quand=QUAND) == (premiere, "finie")


def test_identites_et_visites_notees(etat):
    passe = _ouvrir(etat)
    etat.enregistrer_identites(passe, {"ident-a": None, "ident-b": "http://***:***@proxy-b:3128"}, QUAND)
    etat.noter_visite(passe, "ident-a", debut=QUAND, fin=QUAND, pages=3, statut="limitee", arret=None)
    etat.noter_visite(
        passe, "ident-b", debut=QUAND, fin=QUAND, pages=1, statut="arretee",
        arret={"signe": "statut", "detail": "statut 403 (motif bannissement)"},
    )  # fmt: skip
    identites = {i["nom"]: i for i in etat.identites(passe)}
    assert identites["ident-a"]["visites"] == 1 and identites["ident-a"]["proxy"] is None
    assert identites["ident-b"]["proxy"] == "http://***:***@proxy-b:3128"
    assert identites["ident-b"]["derniere_visite"]["statut"] == "arretee"


def test_un_etat_d_avant_recoit_la_colonne_des_identites(tmp_path):
    """Une base de récolte écrite avant l'étape 4.2 (table `pages` sans colonne `identite`) s'ouvre et sert."""
    chemin = tmp_path / "etat.sqlite3"
    ancien = Etat(chemin)
    passe = _ouvrir(ancien)
    _remplir(ancien, passe, 1)
    ancien.fermer()
    cx = sqlite3.connect(chemin)
    cx.execute("ALTER TABLE pages DROP COLUMN identite")
    cx.execute("DROP TABLE IF EXISTS identites")
    cx.execute("DROP TABLE IF EXISTS visites_identites")
    cx.commit()
    cx.close()
    etat = Etat(chemin)
    try:
        page = etat.prochaine(passe, identite="ident-a")
        assert page is not None
        assert etat.en_cours_par_identite(passe) == {"ident-a": 1}
    finally:
        etat.fermer()


def test_delai_d_attente_de_sqlite_explicite(etat):
    """Plusieurs processus écrivent la même base : chacun attend son tour au lieu d'échouer après 5 s."""
    assert etat._cx.execute("PRAGMA busy_timeout").fetchone()[0] >= 30_000


# --- Verrou de travail d'une identité (vivante ou morte) ---------------------------------------------------------


def test_verrou_de_travail_dit_si_l_identite_travaille(tmp_path):
    assert not travailleur_vivant(tmp_path, "ident-a")
    verrou = verrou_travailleur(tmp_path, "ident-a")
    try:
        assert travailleur_vivant(tmp_path, "ident-a")
        assert not travailleur_vivant(tmp_path, "ident-b")
    finally:
        verrou.close()
    assert not travailleur_vivant(tmp_path, "ident-a")


def test_verrou_de_travail_refuse_un_nom_invalide(tmp_path):
    with pytest.raises(ValueError):
        verrou_travailleur(tmp_path, "../ailleurs")


# --- Plusieurs processus sur le même fichier, l'un tué en tenant une page -----------------------------------------


def test_plusieurs_processus_chaque_adresse_faite_une_fois_meme_si_l_un_meurt(tmp_path):
    from outils_identites import travailleur

    chemin = tmp_path / "etat.sqlite3"
    etat = Etat(chemin)
    passe = _ouvrir(etat)
    total = 60
    _remplir(etat, passe, total)
    etat.fermer()
    contexte = multiprocessing.get_context("spawn")
    noms = ["ident-a", "ident-b", "ident-c"]
    journaux = {nom: tmp_path / f"{nom}.txt" for nom in noms}
    processus = {
        nom: contexte.Process(
            target=travailleur,
            args=(str(chemin), passe, nom, str(journaux[nom]), 0.01, 5 if nom == "ident-c" else 0),
        )
        for nom in noms
    }
    for p in processus.values():
        p.start()
    # ident-c tient une page au bout de 5 pages faites : on le tue (coupure franche, aucun nettoyage).
    limite = time.monotonic() + 60
    while time.monotonic() < limite:
        if journaux["ident-c"].exists() and len(journaux["ident-c"].read_text().split()) >= 6:
            break
        time.sleep(0.05)
    else:
        pytest.fail("ident-c n'a jamais pris sa 6e page")
    os.kill(processus["ident-c"].pid, signal.SIGKILL)
    processus["ident-c"].join(timeout=10)
    for nom in ("ident-a", "ident-b"):
        processus[nom].join(timeout=60)
        assert processus[nom].exitcode == 0, nom
    etat = Etat(chemin)
    try:
        compteurs = etat.compteurs(passe)
        assert compteurs["faites"] == total
        assert compteurs["a_faire"] == 0 and compteurs["en_cours"] == 0
        prises = [int(x) for nom in noms for x in journaux[nom].read_text().split()]
        tenue = int(journaux["ident-c"].read_text().split()[-1])  # la page tenue par ident-c à sa mort
        assert sorted(prises) == sorted([*range(1, total + 1), tenue])  # prise deux fois : par ident-c, puis reprise
        par_identite = etat.pages_par_identite(passe)
        assert par_identite["ident-c"]["lues"] == 5
        assert sum(v["lues"] for v in par_identite.values()) == total
    finally:
        etat.fermer()
