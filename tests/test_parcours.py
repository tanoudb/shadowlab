"""Parcours d'un site en HTTP : ordre, dédoublonnage, alertes, robots.txt, verrou (pilote factice)."""

from __future__ import annotations

import json
import random

import pytest
from outils_recolte import GRAINE, RECETTE_VITRINE, TAILLE, Horloge, PiloteFactice, creer_client
from shadowlab.engines.noezia.parcours import MoteurDriver, Options, Parcours, RefusParcours, Verrou

from shadowlab import notation
from shadowlab.engines.noezia.etat import Etat
from shadowlab.engines.noezia.recettes import lire, lire_texte
from shadowlab.site import vitrine

QUAND = "2026-11-12T10:00:00+00:00"


@pytest.fixture
def site(reglages, monkeypatch):
    with creer_client(monkeypatch) as client:
        yield client


@pytest.fixture
def pilote(site):
    return PiloteFactice(site)


@pytest.fixture
def dossier(tmp_path):
    return tmp_path / "recoltes" / "vitrine-annonces"


def fabriquer(dossier, pilote, recette=None, texte=None, options=None, horloge=None):
    horloge = horloge or Horloge()
    texte = texte if texte is not None else RECETTE_VITRINE.read_text(encoding="utf-8")
    recette = recette or lire_texte(texte)
    ecran: list[str] = []
    p = Parcours(
        recette,
        texte,
        str(RECETTE_VITRINE),
        MoteurDriver(pilote, "http"),
        dossier,
        options or Options(),
        ecran=ecran.append,
        horloge=horloge,
        dormir=horloge.dormir,
        alea=random.Random(1),
        horodatage=lambda: QUAND,
    )
    p.sortie_ecran = ecran
    p.horloge_factice = horloge
    return p


def chemin_sans_jeton(chemin: str) -> str:
    return notation._adresse(chemin)


def lu(dossier, passe=1):
    return json.loads((dossier / f"passe-{passe:03d}" / "resume.json").read_text(encoding="utf-8"))


# --- Parcours complet --------------------------------------------------------------------------


def test_vitrine_a_45_annonces_45_enregistrements_48_pages(dossier, pilote):
    bilan = fabriquer(dossier, pilote).lancer()
    assert bilan.code == 0 and bilan.statut == "terminee" and bilan.passe == 1
    etat = Etat(dossier / "etat.sqlite3")
    c = etat.compteurs(1)
    assert c["faites"] == 48 and c["echecs"] == 0 and c["a_faire"] == 0  # 3 listes + 45 fiches
    assert etat.faites_par_type(1) == {"fiche": 45, "liste": 3}
    note = notation.noter_recolte(etat.enregistrements("annonces"), vitrine.verite(GRAINE, TAILLE))
    assert note["completude"] == 1 and note["exactitude"] == 1
    assert note["enregistrements_retrouves"] == 45 and note["champs_exacts"] == 45 * 14
    pages = notation.noter_pages(vitrine.pages_attendues(GRAINE, TAILLE), etat.adresses_lues(1))
    assert pages["completude_pages"] == 1 and pages["pages_en_trop"] == 0
    etat.fermer()


def test_ordre_en_profondeur_les_fiches_d_une_liste_avant_la_liste_suivante(dossier, pilote):
    fabriquer(dossier, pilote).lancer()
    lues = [chemin_sans_jeton(d) for d in pilote.pages_lues()]
    assert lues == vitrine.pages_attendues(GRAINE, TAILLE)


def test_aucune_page_lue_deux_fois(dossier, pilote):
    fabriquer(dossier, pilote).lancer()
    lues = [chemin_sans_jeton(d) for d in pilote.pages_lues()]
    assert len(lues) == len(set(lues)) == 48


def test_le_moteur_est_ouvert_une_fois_puis_ferme(dossier, pilote):
    fabriquer(dossier, pilote).lancer()
    assert pilote.sessions == 1 and pilote.ouvert is False


def test_resume_json_d_une_passe_terminee(dossier, pilote):
    fabriquer(dossier, pilote).lancer()
    resume = lu(dossier)
    assert resume["recette"] == "vitrine-annonces" and resume["recette_empreinte"].startswith("sha256:")
    assert resume["passe"] == 1 and resume["statut"] == "terminee" and resume["arret"] is None
    assert resume["moteur"]["nom"] == "http" and resume["moteur"]["pilote"] == "factice"
    assert resume["autorisation"] == "site à nous (labo local)"
    assert resume["tranche"] == {} and resume["bornes"] == {"pages_max": None, "par_type": {}}
    assert resume["pages"]["faites"] == 48 and resume["pages"]["echecs"] == 0
    assert resume["pages"]["interdites_robots"] == 0 and resume["pages"]["hors_site"] == 0
    assert resume["pages"]["anormales"] == 0
    assert resume["enregistrements"] == {"annonces": 45} and resume["relocalisations"] == 0
    assert resume["robots"]["respecte"] is True and resume["robots"]["etat"] == "absent"
    assert resume["debut"] == QUAND and resume["fin"] == QUAND


def test_l_etat_est_dans_le_dossier_de_sortie(dossier, pilote):
    fabriquer(dossier, pilote).lancer()
    assert (dossier / "etat.sqlite3").is_file() and (dossier / "passe-001" / "resume.json").is_file()
    assert not (dossier / "verrou").exists() or not Verrou(dossier / "verrou").pris()


def test_la_progression_est_affichee(dossier, pilote):
    p = fabriquer(dossier, pilote)
    p.lancer()
    texte = "\n".join(p.sortie_ecran)
    assert "Passe 1" in texte and "Terminée : 48 pages" in texte and "45 annonces" in texte


# --- Pages anormales, introuvables, échecs -----------------------------------------------------


def test_une_page_introuvable_est_notee_et_la_passe_continue(dossier, pilote):
    pilote.reponses["AN-000005"] = (404, "<html><body>introuvable</body></html>")
    bilan = fabriquer(dossier, pilote).lancer()
    assert bilan.code == 0
    c = lu(dossier)["pages"]
    assert c["introuvables"] == 1 and c["faites"] == 48
    assert lu(dossier)["enregistrements"] == {"annonces": 44}


def test_une_page_isolee_sans_requis_est_anormale_mais_comptee(dossier, pilote):
    pilote.reponses["AN-000005"] = (200, "<html><body><p>page vide</p></body></html>")
    bilan = fabriquer(dossier, pilote).lancer()
    assert bilan.code == 0 and lu(dossier)["pages"]["anormales"] == 1
    assert lu(dossier)["enregistrements"] == {"annonces": 44}


def test_trois_pages_de_suite_sans_requis_arretent_la_passe(dossier, pilote):
    for n in (5, 6, 7):
        pilote.reponses[f"AN-00000{n}"] = (200, "<html><body><p>vide</p></body></html>")
    bilan = fabriquer(dossier, pilote).lancer()
    assert bilan.code == 3 and bilan.statut == "arretee" and bilan.arret["signe"] == "page_non_conforme"
    assert not any("AN-000008" in d for d in pilote.pages_lues())  # zéro requête ensuite


def test_une_panne_reseau_est_retentee_avec_attente_croissante(dossier, pilote):
    pilote.pannes["AN-000003"] = 2
    p = fabriquer(dossier, pilote)
    bilan = p.lancer()
    assert bilan.code == 0 and lu(dossier)["pages"]["echecs"] == 0
    attentes = p.horloge_factice.pauses
    assert len(attentes) == 2 and attentes[0] < attentes[1]  # 0,5 s puis 1 s, plus un peu de gigue


def test_une_panne_qui_dure_est_un_echec_apres_deux_nouveaux_essais(dossier, pilote):
    pilote.pannes["AN-000003"] = 99
    bilan = fabriquer(dossier, pilote).lancer()
    assert bilan.code == 0 and lu(dossier)["pages"]["echecs"] == 1
    assert pilote.requetes_pages == 48 + 2  # 47 pages lues + 3 essais de la page perdue


def test_un_statut_500_est_retente_puis_echec(dossier, pilote):
    pilote.reponses["AN-000003"] = (500, "erreur")
    bilan = fabriquer(dossier, pilote).lancer()
    assert bilan.code == 0 and lu(dossier)["pages"]["echecs"] == 1


def test_trop_d_echecs_arretent_la_passe(dossier, pilote):
    for n in range(1, 8):
        pilote.reponses[f"AN-00000{n}"] = (502, "passerelle")
    bilan = fabriquer(dossier, pilote).lancer()
    assert bilan.code == 3 and bilan.arret["signe"] == "echecs"


# --- Signes d'alerte : arrêt, état gardé ------------------------------------------------------


@pytest.mark.parametrize("statut", [403, 429])
def test_un_statut_d_alerte_arrete_sans_nouvel_essai(dossier, pilote, statut):
    pilote.reponses["AN-000005"] = (statut, "<html><body>non</body></html>")
    p = fabriquer(dossier, pilote)
    bilan = p.lancer()
    assert bilan.code == 3 and bilan.statut == "arretee"
    assert bilan.arret["signe"] == "statut" and bilan.arret["statut"] == statut
    assert sum("AN-000005" in d for d in pilote.pages_lues()) == 1
    assert not any("AN-000006" in d for d in pilote.pages_lues())
    texte = "\n".join(p.sortie_ecran)
    assert "ARRÊT" in texte and str(statut) in texte and "reprendre vitrine-annonces" in texte
    etat = Etat(dossier / "etat.sqlite3")
    assert etat.passe(1)["statut"] == "arretee" and etat.pages(1, "en_cours") == 0
    assert etat.pages(1, "a_faire") > 0  # l'état est gardé, la page refusée est à refaire
    etat.fermer()
    assert lu(dossier)["statut"] == "arretee" and lu(dossier)["arret"]["signe"] == "statut"


def test_redirection_vers_un_autre_hote_alerte_et_arret(dossier, pilote):
    pilote.redirections["AN-000010"] = "http://autre.example/connexion"
    bilan = fabriquer(dossier, pilote).lancer()
    assert bilan.code == 3 and bilan.arret["signe"] == "hors_site"
    assert "autre.example" in bilan.arret["detail"]
    assert not any("AN-000011" in d for d in pilote.pages_lues())


def test_redirection_dans_le_site_vers_une_page_hors_motif_alerte(dossier, pilote):
    pilote.redirections["AN-000010"] = "http://127.0.0.1:8770/lab/connexion"
    bilan = fabriquer(dossier, pilote).lancer()
    assert bilan.code == 3 and bilan.arret["signe"] == "hors_motif"


def test_les_liens_hors_site_sont_ignores_et_comptes(dossier, pilote):
    html = (
        "<html><body><a class='fiche' href='/lab/vitrine/annonces/AN-000001'>1</a>"
        "<a class='fiche' href='http://autre.example/x'>ailleurs</a></body></html>"
    )
    pilote.reponses["=/lab/vitrine/annonces"] = (200, html)  # « = » : adresse exacte
    recette = lire(RECETTE_VITRINE)
    bilan = fabriquer(dossier, pilote, recette=recette).lancer()
    assert bilan.code == 0
    assert lu(dossier)["pages"]["hors_site"] == 1
    assert not any("autre.example" in d for d in pilote.pages_lues())


# --- robots.txt --------------------------------------------------------------------------------


def test_robots_interdit_une_fiche_elle_n_est_jamais_demandee_et_comptee(dossier, pilote):
    pilote.robots = (200, "User-agent: *\nDisallow: /lab/vitrine/annonces/AN-000007\n")
    bilan = fabriquer(dossier, pilote).lancer()
    assert bilan.code == 0
    assert not any("AN-000007" in d for d in pilote.pages_lues())
    resume = lu(dossier)
    assert resume["pages"]["interdites_robots"] == 1 and resume["pages"]["faites"] == 47
    assert resume["enregistrements"] == {"annonces": 44}
    assert resume["robots"]["respecte"] is True and resume["robots"]["etat"] == "lu"
    assert resume["robots"]["adresse"].endswith("/robots.txt") and resume["robots"]["statut"] == 200


def test_robots_est_lu_une_seule_fois_et_avant_les_pages(dossier, pilote):
    fabriquer(dossier, pilote).lancer()
    assert (
        pilote.demandes[0].startswith("/robots.txt") and sum(d.startswith("/robots.txt") for d in pilote.demandes) == 1
    )


def test_ignorer_robots_ne_le_lit_pas_et_l_ecrit_dans_le_resume(dossier, pilote):
    pilote.robots = (200, "User-agent: *\nDisallow: /lab/vitrine/annonces/AN-000007\n")
    p = fabriquer(dossier, pilote, options=Options(ignorer_robots=True))
    bilan = p.lancer()
    assert bilan.code == 0
    assert any("AN-000007" in d for d in pilote.pages_lues())
    assert not any(d.startswith("/robots.txt") for d in pilote.demandes)
    resume = lu(dossier)
    assert resume["robots"]["respecte"] is False and resume["robots"]["ignore_par"] == "--ignorer-robots"
    assert resume["pages"]["interdites_robots"] == 0
    assert "robots.txt IGNORÉ" in "\n".join(p.sortie_ecran)


def test_robots_qui_interdit_le_depart_refuse_avant_toute_page(dossier, pilote):
    pilote.robots = (200, "User-agent: *\nDisallow: /lab/vitrine/annonces$\n")
    with pytest.raises(RefusParcours, match="robots.txt interdit le départ"):
        fabriquer(dossier, pilote).lancer()
    assert pilote.pages_lues() == []
    assert not (dossier / "passe-001").exists()


def test_robots_en_erreur_serveur_refuse_la_passe(dossier, pilote):
    pilote.robots = (503, "")
    with pytest.raises(RefusParcours, match="robots.txt"):
        fabriquer(dossier, pilote).lancer()
    assert pilote.pages_lues() == []


def test_le_crawl_delay_est_applique_meme_en_libre(dossier, pilote):
    pilote.robots = (200, "User-agent: *\nCrawl-delay: 2\n")
    p = fabriquer(dossier, pilote)
    p.lancer()
    assert len(p.horloge_factice.pauses) == 47  # 48 pages : toutes sauf la première
    assert all(a == pytest.approx(2) for a in p.horloge_factice.pauses)
    assert lu(dossier)["robots"]["crawl_delay"] == 2


# --- Verrou et refus ---------------------------------------------------------------------------


def test_deux_passes_en_meme_temps_sur_la_meme_recette_refus(dossier, pilote):
    seconde = fabriquer(dossier, PiloteFactice(pilote.client))
    refus: list[str] = []

    def pendant():
        try:
            seconde.lancer()
        except RefusParcours as e:
            refus.append(str(e))

    pilote.pendant = pendant
    bilan = fabriquer(dossier, pilote).lancer()
    assert bilan.code == 0
    assert refus and "verrou" in refus[0].lower()


def test_le_verrou_est_libere_a_la_fin_meme_en_cas_de_coupure(dossier, pilote):
    from outils_recolte import Coupure

    pilote.coupure_a = 5
    with pytest.raises(Coupure):
        fabriquer(dossier, pilote).lancer()
    assert not Verrou(dossier / "verrou").pris()


def test_verrou_pris_refuse_et_se_libere(tmp_path):
    chemin = tmp_path / "verrou"
    premier = Verrou(chemin)
    premier.prendre()
    assert Verrou(chemin).pris()
    with pytest.raises(RefusParcours, match="verrou"):
        Verrou(chemin).prendre()
    premier.liberer()
    assert not Verrou(chemin).pris()


def test_site_qui_n_est_pas_a_nous_sans_autorisation_refus_avant_toute_requete(dossier, pilote):
    recette = lire(RECETTE_VITRINE).model_copy(update={"autorisation": None, "hotes": ["exemple.fr"]})
    with pytest.raises(RefusParcours, match="autorisation"):
        fabriquer(dossier, pilote, recette=recette).lancer()
    assert pilote.demandes == [] and pilote.sessions == 0


def test_une_passe_non_finie_n_est_pas_ecrasee_par_un_nouveau_lancer(dossier, pilote):
    pilote.reponses["AN-000005"] = (429, "non")
    fabriquer(dossier, pilote).lancer()
    pilote.reponses.clear()
    with pytest.raises(RefusParcours, match="reprendre"):
        fabriquer(dossier, pilote).lancer()
