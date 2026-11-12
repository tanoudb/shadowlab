"""Bornes et tranches : --pages-max, plafond par type, --sans, variables de la recette (--tranche)."""

import pytest
from outils_recolte import (
    GRAINE,
    RECETTE_VITRINE,
    TAILLE,
    PiloteFactice,
    chemin_sans_jeton,
    creer_client,
    fabriquer,
    lu,
)

from shadowlab.engines.noezia.etat import Etat
from shadowlab.engines.noezia.parcours import Options, RefusParcours
from shadowlab.site import vitrine


@pytest.fixture
def site(reglages, monkeypatch):
    with creer_client(monkeypatch) as client:
        yield client


@pytest.fixture
def dossier(tmp_path):
    return tmp_path / "recoltes" / "vitrine-annonces"


def texte_vitrine(ajout: str = "") -> str:
    return RECETTE_VITRINE.read_text(encoding="utf-8") + ajout


# --- --pages-max -------------------------------------------------------------------------------


def test_pages_max_arrete_apres_n_pages_lues(dossier, site):
    pilote = PiloteFactice(site)
    p = fabriquer(dossier, pilote, options=Options(pages_max=10))
    bilan = p.lancer()
    assert bilan.code == 0 and bilan.statut == "limitee"
    assert len(pilote.pages_lues()) == 10
    assert bilan.resume["bornes"]["pages_max"] == 10 and bilan.resume["pages"]["faites"] == 10
    assert "Limite atteinte" in "\n".join(p.sortie_ecran)
    etat = Etat(dossier / "etat.sqlite3")
    assert etat.passe(1)["statut"] == "limitee" and etat.compteurs(1)["a_faire"] > 0
    etat.fermer()


def test_reprendre_une_passe_limitee_lit_n_pages_de_plus_ou_va_au_bout(dossier, site):
    premier = PiloteFactice(site)
    fabriquer(dossier, premier, options=Options(pages_max=10)).lancer()
    second = PiloteFactice(site)
    assert fabriquer(dossier, second).reprendre(pages_max=5).statut == "limitee"  # 5 pages de plus, pas 5 en tout
    assert len(second.pages_lues()) == 5
    dernier = PiloteFactice(site)
    bilan = fabriquer(dossier, dernier).reprendre()  # la limite du lancement ne vaut plus
    assert bilan.statut == "terminee"
    lues = [chemin_sans_jeton(d) for d in premier.pages_lues() + second.pages_lues() + dernier.pages_lues()]
    assert lues == vitrine.pages_attendues(GRAINE, TAILLE)


def test_la_borne_de_la_recette_et_celle_de_la_commande_la_plus_basse_gagne(dossier, site):
    texte = texte_vitrine("bornes: {pages_max: 6}\n")
    pilote = PiloteFactice(site)
    bilan = fabriquer(dossier, pilote, texte=texte, options=Options(pages_max=9)).lancer()
    assert len(pilote.pages_lues()) == 6 and bilan.resume["bornes"]["pages_max"] == 6


# --- Plafond par type, --sans ------------------------------------------------------------------


def test_plafond_par_type_de_page(dossier, site):
    pilote = PiloteFactice(site)
    bilan = fabriquer(dossier, pilote, texte=texte_vitrine("bornes: {par_type: {fiche: 7}}\n")).lancer()
    assert bilan.code == 0 and bilan.statut == "terminee"
    assert bilan.resume["pages"]["par_type"] == {"fiche": 7, "liste": 3}
    assert bilan.resume["pages"]["liens_exclus"] == 38  # 13 + 20 + 5 fiches refusées au plafond
    assert bilan.resume["enregistrements"] == {"annonces": 7}


def test_sans_ne_visite_pas_ces_types(dossier, site):
    pilote = PiloteFactice(site)
    bilan = fabriquer(dossier, pilote, options=Options(sans=("fiche",))).lancer()
    assert bilan.code == 0 and bilan.resume["pages"]["par_type"] == {"liste": 3}
    assert bilan.resume["pages"]["liens_exclus"] == TAILLE and bilan.resume["enregistrements"] == {}
    assert bilan.resume["sans"] == ["fiche"]


def test_sans_un_type_inconnu_est_refuse_avant_toute_requete(dossier, site):
    pilote = PiloteFactice(site)
    with pytest.raises(RefusParcours, match="--sans"):
        fabriquer(dossier, pilote, options=Options(sans=("rallye",))).lancer()
    assert pilote.demandes == [] and pilote.sessions == 0


# --- Tranches (variables de la recette) --------------------------------------------------------

RECETTE_TRANCHES = """
recette: 1
nom: genres
autorisation: site à nous (labo local)
hotes: [127.0.0.1]
depart: [{url: 'http://127.0.0.1/a', type: accueil}]
variables: {genre: '*'}
pages:
  accueil:
    url: '^/a$'
    requis: 'ul.genres'
    suivre:
      - liens: 'ul.genres a'
        vers: page
        garder_si: {contient: '{genre}'}
  page:
    url: '^/p\\d$'
    requis: 'h1'
    enregistrements:
      - {collection: pages, cle: id, champs: {id: {adresse: '/p(\\d)$', format: entier}, titre: h1}}
"""
SITE_TRANCHES = {
    "=/a": (200, '<ul class="genres"><li><a href="/p1">alpha</a></li><li><a href="/p2">beta</a></li></ul>'),
    "=/p1": (200, "<h1>Page un</h1>"),
    "=/p2": (200, "<h1>Page deux</h1>"),
}


def pilote_tranches():
    pilote = PiloteFactice(None)
    pilote.reponses.update(SITE_TRANCHES)
    return pilote


def test_sans_tranche_tout_est_suivi(tmp_path):
    pilote = pilote_tranches()
    bilan = fabriquer(tmp_path / "g", pilote, texte=RECETTE_TRANCHES).lancer()
    assert bilan.resume["enregistrements"] == {"pages": 2} and bilan.resume["tranche"] == {}


def test_tranche_ne_suit_que_la_valeur_donnee(tmp_path):
    pilote = pilote_tranches()
    bilan = fabriquer(
        tmp_path / "g", pilote, texte=RECETTE_TRANCHES, options=Options(tranche={"genre": "beta"})
    ).lancer()
    assert bilan.resume["enregistrements"] == {"pages": 1} and bilan.resume["tranche"] == {"genre": "beta"}
    assert pilote.pages_lues() == ["/a", "/p2"]
    etat = Etat(tmp_path / "g" / "etat.sqlite3")
    assert etat.enregistrements("pages")[0]["titre"] == "Page deux"
    etat.fermer()


def test_tranche_inconnue_refusee_avant_toute_requete(tmp_path):
    pilote = pilote_tranches()
    with pytest.raises(RefusParcours, match="variable inconnue"):
        fabriquer(tmp_path / "g", pilote, texte=RECETTE_TRANCHES, options=Options(tranche={"saison": "2025"})).lancer()
    assert pilote.demandes == []


def test_la_tranche_survit_a_la_reprise(tmp_path):
    pilote = pilote_tranches()
    pilote.interruption_a = 2  # avant /p2
    fabriquer(tmp_path / "g", pilote, texte=RECETTE_TRANCHES, options=Options(tranche={"genre": "beta"})).lancer()
    second = pilote_tranches()
    bilan = fabriquer(tmp_path / "g", second, texte=RECETTE_TRANCHES).reprendre()
    assert bilan.resume["tranche"] == {"genre": "beta"} and bilan.resume["enregistrements"] == {"pages": 1}
    assert lu(tmp_path / "g")["pages"]["faites"] == 2
