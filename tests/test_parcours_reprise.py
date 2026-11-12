"""Reprise après coupure ou alerte : même résultat, aucune page lue deux fois, recette et attente contrôlées."""

import pytest
from outils_recolte import (
    GRAINE,
    RECETTE_VITRINE,
    TAILLE,
    Coupure,
    PiloteFactice,
    chemin_sans_jeton,
    creer_client,
    fabriquer,
    lu,
)

from shadowlab import notation
from shadowlab.engines.noezia.etat import Etat
from shadowlab.engines.noezia.parcours import Options, RefusParcours
from shadowlab.site import vitrine

TROIS_HEURES_PLUS_TARD = "2026-11-12T13:00:00+00:00"


@pytest.fixture
def site(reglages, monkeypatch):
    with creer_client(monkeypatch) as client:
        yield client


@pytest.fixture
def dossier(tmp_path):
    return tmp_path / "recoltes" / "vitrine-annonces"


def verifier_resultat_complet(dossier, *pilotes):
    """45 enregistrements exacts, 48 pages, aucune page lue deux fois, dans l'ordre d'un parcours sans coupure."""
    etat = Etat(dossier / "etat.sqlite3")
    note = notation.noter_recolte(etat.enregistrements("annonces"), vitrine.verite(GRAINE, TAILLE))
    assert note["completude"] == 1 and note["exactitude"] == 1 and note["enregistrements_retrouves"] == TAILLE
    assert etat.compteurs(1)["faites"] == 48 and etat.compteurs(1)["a_faire"] == 0
    etat.fermer()
    lues = [chemin_sans_jeton(d) for p in pilotes for d in p.pages_lues()]
    assert len(lues) == len(set(lues)) == 48, "une page a été lue deux fois"
    assert lues == vitrine.pages_attendues(GRAINE, TAILLE)


def test_coupure_franche_a_la_page_20_puis_reprendre_meme_resultat(dossier, site):
    premier = PiloteFactice(site)
    premier.coupure_a = 20
    with pytest.raises(Coupure):
        fabriquer(dossier, premier).lancer()
    etat = Etat(dossier / "etat.sqlite3")
    assert etat.pages(1, "en_cours") == 1  # la page qui était en route
    assert etat.compteurs(1)["faites"] == 19
    assert etat.passe(1)["statut"] == "en_cours"  # rien n'a pu être écrit à la coupure
    etat.fermer()

    second = PiloteFactice(site)
    bilan = fabriquer(dossier, second).reprendre()
    assert bilan.code == 0 and bilan.statut == "terminee" and bilan.passe == 1
    verifier_resultat_complet(dossier, premier, second)
    assert lu(dossier)["statut"] == "terminee" and lu(dossier)["pages"]["faites"] == 48


def test_ctrl_c_a_la_page_20_ecrit_le_resume_et_la_reprise_continue(dossier, site):
    premier = PiloteFactice(site)
    premier.interruption_a = 20
    p = fabriquer(dossier, premier)
    bilan = p.lancer()
    assert bilan.code == 1 and bilan.statut == "interrompue"
    assert lu(dossier)["statut"] == "interrompue" and "INTERROMPU" in "\n".join(p.sortie_ecran)
    etat = Etat(dossier / "etat.sqlite3")
    assert etat.pages(1, "en_cours") == 0  # la page en route est rendue à la file
    etat.fermer()
    second = PiloteFactice(site)
    assert fabriquer(dossier, second).reprendre().code == 0
    verifier_resultat_complet(dossier, premier, second)


def test_reprise_apres_alerte_attend_une_heure_sauf_maintenant(dossier, site):
    premier = PiloteFactice(site)
    premier.reponses["AN-000010"] = (429, "<html><body>trop</body></html>")
    assert fabriquer(dossier, premier).lancer().code == 3
    second = PiloteFactice(site)
    with pytest.raises(RefusParcours, match="attendre 1 h"):
        fabriquer(dossier, second).reprendre()
    assert second.requetes_pages == 0
    bilan = fabriquer(dossier, second).reprendre(maintenant=True)
    assert bilan.code == 0
    verifier_resultat_complet(dossier, premier, second)


def test_reprise_apres_alerte_une_heure_plus_tard_sans_option(dossier, site):
    premier = PiloteFactice(site)
    premier.reponses["AN-000010"] = (403, "<html><body>non</body></html>")
    fabriquer(dossier, premier).lancer()
    second = PiloteFactice(site)
    bilan = fabriquer(dossier, second, horodatage=lambda: TROIS_HEURES_PLUS_TARD).reprendre()
    assert bilan.code == 0
    verifier_resultat_complet(dossier, premier, second)


def test_la_reprise_garde_les_signes_d_alerte_deja_vus(dossier, site):
    """Deux pages vides avant la coupure, une après : trois de suite, donc alerte."""
    premier = PiloteFactice(site)
    for n in (5, 6, 7):
        premier.reponses[f"AN-00000{n}"] = (200, "<html><body><p>vide</p></body></html>")
    premier.interruption_a = 8  # avant la lecture d'AN-000007
    assert fabriquer(dossier, premier).lancer().statut == "interrompue"
    second = PiloteFactice(site)
    second.reponses.update(premier.reponses)
    bilan = fabriquer(dossier, second).reprendre()
    assert bilan.code == 3 and bilan.arret["signe"] == "page_non_conforme"


def test_recette_modifiee_refus_sauf_option(dossier, site):
    premier = PiloteFactice(site)
    premier.coupure_a = 10
    with pytest.raises(Coupure):
        fabriquer(dossier, premier).lancer()
    modifiee = RECETTE_VITRINE.read_text(encoding="utf-8") + "\n# un commentaire de plus\n"
    second = PiloteFactice(site)
    with pytest.raises(RefusParcours, match="recette a changé"):
        fabriquer(dossier, second, texte=modifiee).reprendre()
    assert second.requetes_pages == 0
    bilan = fabriquer(dossier, second, texte=modifiee).reprendre(recette_modifiee=True)
    assert bilan.code == 0
    etat = Etat(dossier / "etat.sqlite3")
    assert etat.passe(1)["texte_recette"] == modifiee  # la passe se termine avec la recette actuelle
    etat.fermer()


def test_rien_a_reprendre(dossier, site):
    with pytest.raises(RefusParcours, match="aucune passe"):
        fabriquer(dossier, PiloteFactice(site)).reprendre()
    fabriquer(dossier, PiloteFactice(site)).lancer()
    with pytest.raises(RefusParcours, match="terminee"):
        fabriquer(dossier, PiloteFactice(site)).reprendre()


def test_la_reprise_garde_les_options_de_depart(dossier, site):
    premier = PiloteFactice(site)
    premier.interruption_a = 2  # pendant la deuxième page de liste
    fabriquer(dossier, premier, options=Options(sans=("fiche",), ignorer_robots=True)).lancer()
    second = PiloteFactice(site)
    p = fabriquer(dossier, second)  # options par défaut : celles de la passe l'emportent
    bilan = p.reprendre()
    assert bilan.code == 0 and len(second.pages_lues()) == 2  # listes 2 et 3 : la 1re était faite, aucune fiche
    assert bilan.resume["sans"] == ["fiche"] and bilan.resume["robots"]["respecte"] is False
    assert not any(d.startswith("/robots.txt") for d in second.demandes)


def test_nouveau_lancer_apres_une_passe_terminee_relit_tout_sans_doubler(dossier, site):
    fabriquer(dossier, PiloteFactice(site)).lancer()
    second = PiloteFactice(site)
    bilan = fabriquer(dossier, second).lancer()
    assert bilan.passe == 2 and bilan.code == 0
    assert len(second.pages_lues()) == 48
    assert bilan.resume["enregistrements"] == {"annonces": 45}
    etat = Etat(dossier / "etat.sqlite3")
    assert len(etat.enregistrements("annonces")) == 45 and etat.enregistrements("annonces")[0]["_passe"] == 2
    etat.fermer()


def test_tout_refaire_abandonne_la_passe_non_finie_et_repart_de_zero(dossier, site):
    premier = PiloteFactice(site)
    premier.reponses["AN-000010"] = (429, "non")
    fabriquer(dossier, premier).lancer()
    second = PiloteFactice(site)
    bilan = fabriquer(dossier, second, options=Options(tout_refaire=True)).lancer()
    assert bilan.passe == 2 and bilan.code == 0
    etat = Etat(dossier / "etat.sqlite3")
    assert etat.passe(1)["statut"] == "abandonnee" and etat.passe(2)["statut"] == "terminee"
    assert len(etat.enregistrements("annonces")) == 45
    etat.fermer()
