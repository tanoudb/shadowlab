"""Commande `shadowlab recolte` : lancer, reprendre, etat, essayer, noter (pilote factice, sans réseau)."""

import contextlib
import logging

import pytest
from outils_recolte import GRAINE, RECETTE_VITRINE, TAILLE, PiloteFactice, creer_client

from shadowlab import campaigns, commande_recolte
from shadowlab.cli import main
from shadowlab.engines.noezia.etat import Etat
from shadowlab.engines.noezia.parcours import MoteurDriver
from shadowlab.engines.noezia.recettes import Enregistrement
from shadowlab.site import rallye

QUAND = "2026-11-12T10:00:00+00:00"


@pytest.fixture
def site(reglages, monkeypatch):
    with creer_client(monkeypatch) as client:
        yield client


@pytest.fixture
def pilote(site, monkeypatch):
    """Le pilote factice remplace le moteur réel et le démarrage du site du labo."""
    pilote = PiloteFactice(site)
    monkeypatch.setattr(commande_recolte, "construire_moteur", lambda nom, recette, reglages: MoteurDriver(pilote, nom))
    monkeypatch.setattr(commande_recolte, "site_du_labo", lambda recette, reglages: contextlib.nullcontext())
    return pilote


@pytest.fixture
def sortie_vitrine(reglages):
    return reglages.sorties / "recoltes" / "vitrine-annonces"


def lancer(*options, recette=RECETTE_VITRINE):
    return main(["recolte", "lancer", str(recette), *options])


# --- lancer ------------------------------------------------------------------------------------


def test_lancer_la_vitrine_ecrit_etat_et_donnees_dans_les_sorties_du_labo(pilote, sortie_vitrine, capsys):
    assert lancer() == 0
    sortie = capsys.readouterr().out
    assert "Recette vitrine-annonces · moteur http" in sortie and "Terminée : 48 pages" in sortie
    assert (sortie_vitrine / "etat.sqlite3").is_file()
    assert (sortie_vitrine / "passe-001" / "annonces.jsonl").is_file()
    assert (sortie_vitrine / "passe-001" / "annonces.csv").is_file()
    assert (sortie_vitrine / "passe-001" / "resume.json").is_file()


def test_lancer_sortie_ailleurs(pilote, tmp_path):
    assert lancer("--sortie", str(tmp_path / "ailleurs")) == 0
    assert (tmp_path / "ailleurs" / "passe-001" / "resume.json").is_file()


def test_lancer_options_pages_max_sans_tranche(pilote, sortie_vitrine, capsys):
    assert lancer("--pages-max", "5") == 0
    assert "Limite atteinte" in capsys.readouterr().out
    assert len(pilote.pages_lues()) == 5


def test_lancer_sans_et_ignorer_robots(pilote, capsys):
    assert lancer("--sans", "fiche", "--ignorer-robots") == 0
    sortie = capsys.readouterr().out
    assert "robots.txt IGNORÉ" in sortie and not any(d.startswith("/robots.txt") for d in pilote.demandes)
    assert len(pilote.pages_lues()) == 3


def test_tranche_mal_ecrite_refusee(pilote, capsys):
    assert lancer("--tranche", "sans-egal") == 2
    assert "nom=valeur" in capsys.readouterr().err and pilote.demandes == []


def test_recette_fautive_code_2_sans_requete(pilote, tmp_path, capsys):
    fautive = tmp_path / "fautive.yaml"
    fautive.write_text(RECETTE_VITRINE.read_text(encoding="utf-8") + "cle_inconnue: 1\n", encoding="utf-8")
    assert lancer(recette=fautive) == 2
    assert "recette fautive" in capsys.readouterr().err and pilote.demandes == []


def test_recette_introuvable_code_2(pilote, tmp_path, capsys):
    assert lancer(recette=tmp_path / "absente.yaml") == 2
    assert "introuvable" in capsys.readouterr().err


def test_site_tiers_sans_autorisation_code_2_avant_toute_requete(pilote, tmp_path, capsys):
    texte = (
        RECETTE_VITRINE.read_text(encoding="utf-8")
        .replace("127.0.0.1", "exemple.fr")
        .replace("autorisation: site à nous (labo local)\n", "")
    )
    recette = tmp_path / "tiers.yaml"
    recette.write_text(texte, encoding="utf-8")
    assert lancer(recette=recette) == 2
    assert "autorisation" in capsys.readouterr().err and pilote.demandes == [] and pilote.sessions == 0


def test_moteur_navigateur_pas_encore_disponible_code_2(pilote, capsys):
    assert lancer("--moteur", "navigateur") == 2
    assert "navigateur" in capsys.readouterr().err and pilote.demandes == []


def test_robots_qui_refuse_le_depart_code_2(pilote, capsys):
    pilote.robots = (200, "User-agent: *\nDisallow: /\n")
    assert lancer() == 2
    assert "robots.txt interdit le départ" in capsys.readouterr().err and pilote.pages_lues() == []


def test_alerte_code_3_puis_reprendre(pilote, capsys):
    pilote.reponses["AN-000010"] = (429, "non")
    assert lancer() == 3
    sortie = capsys.readouterr().out
    assert "ARRÊT" in sortie and "recolte reprendre vitrine-annonces" in sortie
    assert main(["recolte", "reprendre", "vitrine-annonces"]) == 2  # trop tôt
    assert "attendre 1 h" in capsys.readouterr().err
    pilote.reponses.clear()
    assert main(["recolte", "reprendre", "vitrine-annonces", "--maintenant"]) == 0
    assert "Terminée : 48 pages" in capsys.readouterr().out


# --- reprendre ---------------------------------------------------------------------------------


def test_reprendre_sans_recolte_code_2(pilote, capsys):
    assert main(["recolte", "reprendre", "inconnue"]) == 2
    assert "aucune récolte" in capsys.readouterr().err


def test_reprendre_une_passe_interrompue_avec_la_recette_de_depart(pilote, capsys):
    pilote.interruption_a = 20
    assert lancer() == 1  # Ctrl-C
    pilote.interruption_a = None
    assert main(["recolte", "reprendre", "vitrine-annonces"]) == 0
    assert "Reprise de la passe 1" in capsys.readouterr().out


def test_reprendre_recette_modifiee_demande_l_option(pilote, tmp_path, capsys):
    copie = tmp_path / "vitrine.yaml"
    copie.write_text(RECETTE_VITRINE.read_text(encoding="utf-8"), encoding="utf-8")
    pilote.interruption_a = 20
    assert lancer(recette=copie) == 1
    pilote.interruption_a = None
    copie.write_text(copie.read_text(encoding="utf-8") + "# modifiée\n", encoding="utf-8")
    assert main(["recolte", "reprendre", "vitrine-annonces"]) == 2
    assert "--recette-modifiee" in capsys.readouterr().err
    assert main(["recolte", "reprendre", "vitrine-annonces", "--recette-modifiee"]) == 0


def test_reprendre_borne_plus_haute(pilote, capsys):
    assert lancer("--pages-max", "5") == 0
    assert main(["recolte", "reprendre", "vitrine-annonces", "--pages-max", "1000"]) == 0
    assert "Terminée : 48 pages" in capsys.readouterr().out


# --- etat --------------------------------------------------------------------------------------


def test_etat_resume_de_la_derniere_passe(pilote, capsys):
    lancer()
    capsys.readouterr()
    assert main(["recolte", "etat", "vitrine-annonces"]) == 0
    sortie = capsys.readouterr().out
    assert "passe 1" in sortie and "terminee" in sortie and "48 pages faites" in sortie and "45 annonces" in sortie


def test_etat_avec_le_journal_des_pages(pilote, capsys):
    lancer()
    capsys.readouterr()
    assert main(["recolte", "etat", "vitrine-annonces", "--pages"]) == 0
    lignes = [ligne for ligne in capsys.readouterr().out.splitlines() if "/lab/vitrine/annonces" in ligne]
    assert len(lignes) == 48 and "fiche" in lignes[1] and "200" in lignes[1]


def test_etat_d_une_recolte_inconnue_code_2(pilote, capsys):
    assert main(["recolte", "etat", "inconnue"]) == 2


def test_etat_dit_si_une_passe_tourne(pilote, sortie_vitrine, capsys):
    from shadowlab.engines.noezia.parcours import Verrou

    lancer()
    capsys.readouterr()
    verrou = Verrou(sortie_vitrine / "verrou")
    verrou.prendre()
    try:
        main(["recolte", "etat", "vitrine-annonces"])
    finally:
        verrou.liberer()
    assert "une passe tourne" in capsys.readouterr().out


# --- essayer -----------------------------------------------------------------------------------


def test_essayer_une_adresse_montre_champs_et_liens_sans_rien_ecrire(pilote, reglages, capsys):
    code = main(["recolte", "essayer", str(RECETTE_VITRINE), "http://127.0.0.1:8770/lab/vitrine/annonces/AN-000001"])
    assert code == 0
    sortie = capsys.readouterr().out
    assert "type fiche" in sortie and "reference" in sortie and "AN-000001" in sortie
    assert not (reglages.sorties / "recoltes").exists()


def test_essayer_une_liste_montre_les_liens(pilote, capsys):
    assert main(["recolte", "essayer", str(RECETTE_VITRINE), "http://127.0.0.1:8770/lab/vitrine/annonces"]) == 0
    sortie = capsys.readouterr().out
    assert "type liste" in sortie and "Liens à suivre (21)" in sortie and "AN-000001" in sortie


def test_essayer_un_fichier_html(site, tmp_path, pilote, capsys):
    html = tmp_path / "fiche.html"
    html.write_text(site.get("/lab/vitrine/annonces/AN-000002").text, encoding="utf-8")
    code = main(
        [
            "recolte",
            "essayer",
            str(RECETTE_VITRINE),
            str(html),
            "--type",
            "fiche",
            "--base",
            "http://127.0.0.1:8770/lab/vitrine/annonces/AN-000002",
        ]
    )
    assert code == 0 and "AN-000002" in capsys.readouterr().out and pilote.demandes == []


def test_essayer_une_adresse_hors_de_la_recette_code_2(pilote, capsys):
    assert main(["recolte", "essayer", str(RECETTE_VITRINE), "http://127.0.0.1:8770/autre/chose"]) == 2
    assert "aucun type de page" in capsys.readouterr().err and pilote.demandes == []


def test_essayer_respecte_robots_txt(pilote, capsys):
    pilote.robots = (200, "User-agent: *\nDisallow: /lab/vitrine/annonces/AN-000001\n")
    adresse = "http://127.0.0.1:8770/lab/vitrine/annonces/AN-000001"
    assert main(["recolte", "essayer", str(RECETTE_VITRINE), adresse]) == 2
    assert "robots.txt" in capsys.readouterr().err and pilote.pages_lues() == []
    assert main(["recolte", "essayer", str(RECETTE_VITRINE), adresse, "--ignorer-robots"]) == 0


# --- noter -------------------------------------------------------------------------------------


def test_noter_la_vitrine_contre_le_seuil_de_99_pour_cent(pilote, capsys):
    lancer()
    capsys.readouterr()
    assert main(["recolte", "noter", "vitrine-annonces", "--verite", "vitrine"]) == 0
    sortie = capsys.readouterr().out
    assert "pages 48/48" in sortie and "enregistrements 45/45" in sortie and f"champs {45 * 14}/{45 * 14}" in sortie
    assert f"graine {GRAINE}" in sortie and f"taille {TAILLE}" in sortie


def test_noter_une_recolte_partielle_echoue(pilote, capsys):
    lancer("--pages-max", "10")
    capsys.readouterr()
    assert main(["recolte", "noter", "vitrine-annonces", "--verite", "vitrine"]) == 1
    assert "sous le seuil" in capsys.readouterr().out


def test_noter_une_recolte_inconnue_code_2(pilote):
    assert main(["recolte", "noter", "inconnue", "--verite", "vitrine"]) == 2


@pytest.fixture
def recolte_rallye(reglages, monkeypatch):
    """Un état qui contient exactement la vérité du site de rallye (graine et taille du labo)."""
    monkeypatch.setenv("SHADOWLAB_RALLYE_TAILLE", "12")
    verite = rallye.verite(int(reglages.rallye_graine), 12)
    dossier = reglages.sorties / "recoltes" / "rallye-demo"
    etat = Etat(dossier / "etat.sqlite3")
    passe = etat.ouvrir_passe("rallye-demo", "sha256:x", "t", "c", {"nom": "http"}, {}, QUAND)
    pages = verite["pages"]
    etat.empiler(passe, [(f"http://127.0.0.1:8770{p['adresse']}", p["type"]) for p in pages])
    toutes = [
        Enregistrement(nom, tuple(e[c] for c in verite["cles"][nom]), dict(e))
        for nom, lignes in verite["collections"].items()
        for e in lignes
    ]
    premiere = True
    while (page := etat.prochaine(passe)) is not None:
        etat.terminer_page(
            page,
            etat="faite",
            statut=200,
            decision="ok",
            quand=QUAND,
            enregistrements=toutes if premiere else (),
        )
        premiere = False
    etat.terminer_passe(passe, "terminee", None, QUAND)
    etat.fermer()
    return verite


def test_noter_le_rallye_collection_par_collection(recolte_rallye, capsys):
    assert main(["recolte", "noter", "rallye-demo", "--verite", "rallye"]) == 0
    sortie = capsys.readouterr().out
    assert f"pages {recolte_rallye['nb_pages']}/{recolte_rallye['nb_pages']}" in sortie
    for collection in recolte_rallye["collections"]:
        assert collection in sortie


def test_noter_le_rallye_dit_la_collection_qui_pech(recolte_rallye, reglages, capsys):
    etat = Etat(reglages.sorties / "recoltes" / "rallye-demo" / "etat.sqlite3")
    etat._cx.execute("DELETE FROM enregistrements WHERE collection = 'temps'")
    etat.fermer()
    assert main(["recolte", "noter", "rallye-demo", "--verite", "rallye"]) == 1
    sortie = capsys.readouterr().out
    assert "temps 0/" in sortie and "sous le seuil" in sortie


# --- Détails -----------------------------------------------------------------------------------


def test_l_ecran_ne_laisse_passer_aucun_caractere_de_controle_venu_du_site(pilote, capsys):
    pilote.redirections["AN-000010"] = "http://autre.example/\x1b[2Jmalin"
    assert lancer() == 3
    assert "\x1b" not in capsys.readouterr().out


def test_les_evenements_vont_aussi_au_journal(pilote, caplog):
    with caplog.at_level(logging.DEBUG, logger="shadowlab.recolte"):
        lancer()
    assert any("debut" in r.getMessage() for r in caplog.records if r.name == "shadowlab.recolte")


def test_le_site_du_labo_n_est_demarre_que_s_il_ne_tourne_pas(monkeypatch, reglages, capsys):
    from shadowlab.engines.noezia.recettes import lire

    appels = []

    @contextlib.contextmanager
    def faux_serveur(_reglages):
        appels.append("demarre")
        yield

    monkeypatch.setattr(campaigns, "serveur_local", faux_serveur)
    recette = lire(RECETTE_VITRINE).model_copy(deep=True)
    recette.depart[0].url = f"http://127.0.0.1:{reglages.port}/lab/vitrine/annonces"
    monkeypatch.setattr(campaigns, "_repond", lambda hote, port: False)
    with commande_recolte.site_du_labo(recette, reglages):
        pass
    assert appels == ["demarre"] and "Site du labo démarré" in capsys.readouterr().out
    monkeypatch.setattr(campaigns, "_repond", lambda hote, port: True)
    appels.clear()
    with commande_recolte.site_du_labo(recette, reglages):
        pass
    assert appels == ["demarre"]  # serveur_local vérifie lui-même l'identité du site déjà là
    assert "Site du labo démarré" not in capsys.readouterr().out
    # une recette dont le départ n'est pas sur le port du labo : rien à lancer
    recette.depart[0].url = f"http://127.0.0.1:{reglages.port + 1}/lab/vitrine/annonces"
    appels.clear()
    with commande_recolte.site_du_labo(recette, reglages):
        pass
    assert appels == []
