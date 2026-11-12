"""Lecteur de robots.txt : groupes par agent, Allow/Disallow avec `*` et `$`, motif le plus long, Crawl-delay."""

import pytest

from shadowlab.engines.noezia.robots import Robots


def lire(texte: str, agent: str = "noezia") -> Robots:
    return Robots.depuis_reponse(200, texte, agent)


def test_fichier_absent_tout_est_permis():
    for statut in (404, 410, 403, 401):
        robots = Robots.depuis_reponse(statut, "", "noezia")
        assert robots.permis("/n-importe-quoi?x=1")
        assert robots.etat == "absent"


def test_erreur_serveur_rien_n_est_permis():
    for statut in (500, 502, 503, 429):
        robots = Robots.depuis_reponse(statut, "", "noezia")
        assert not robots.permis("/")
        assert robots.etat == "inaccessible"


def test_fichier_illisible_ou_sans_reponse_rien_n_est_permis():
    assert not Robots.inaccessible().permis("/")


def test_fichier_vide_tout_est_permis():
    assert lire("").permis("/a")


def test_disallow_par_prefixe():
    robots = lire("User-agent: *\nDisallow: /prive\n")
    assert not robots.permis("/prive")
    assert not robots.permis("/prive/fiche?x=1")
    assert not robots.permis("/privee")  # préfixe : « /prive » couvre « /privee »
    assert robots.permis("/public")


def test_disallow_vide_ne_bloque_rien():
    assert lire("User-agent: *\nDisallow:\n").permis("/a")


def test_disallow_racine_bloque_tout():
    robots = lire("User-agent: *\nDisallow: /\n")
    assert not robots.permis("/") and not robots.permis("/a/b")


def test_joker_etoile():
    robots = lire("User-agent: *\nDisallow: /*/brouillon\nDisallow: /*.pdf\n")
    assert not robots.permis("/annonces/brouillon")
    assert not robots.permis("/a/b/brouillon/x")
    assert not robots.permis("/doc/notice.pdf")
    assert not robots.permis("/doc/notice.pdf?v=2")
    assert robots.permis("/doc/notice.html")


def test_fin_de_motif_dollar():
    robots = lire("User-agent: *\nDisallow: /*.pdf$\nDisallow: /fin$\n")
    assert not robots.permis("/a/notice.pdf")
    assert robots.permis("/a/notice.pdf?v=2")  # le motif finit au « .pdf »
    assert not robots.permis("/fin")
    assert robots.permis("/finale")


def test_le_motif_le_plus_long_l_emporte():
    robots = lire("User-agent: *\nDisallow: /annonces\nAllow: /annonces/AN-0001\n")
    assert robots.permis("/annonces/AN-0001")
    assert robots.permis("/annonces/AN-00012")
    assert not robots.permis("/annonces/AN-0002")
    assert not robots.permis("/annonces")


def test_a_longueur_egale_allow_l_emporte():
    robots = lire("User-agent: *\nDisallow: /a\nAllow: /a\n")
    assert robots.permis("/a/x")
    robots = lire("User-agent: *\nAllow: /a\nDisallow: /a\n")  # l'ordre d'écriture ne change rien
    assert robots.permis("/a/x")


def test_groupe_de_l_agent_prime_sur_l_etoile():
    texte = "User-agent: *\nDisallow: /\n\nUser-agent: noezia\nDisallow: /prive\n"
    robots = lire(texte)
    assert robots.permis("/public")
    assert not robots.permis("/prive")
    assert robots.groupe == "noezia"


def test_la_regle_etoile_s_applique_si_l_agent_n_est_pas_cite():
    texte = "User-agent: gptbot\nDisallow: /\n\nUser-agent: *\nDisallow: /prive\n"
    robots = lire(texte)
    assert robots.permis("/public")
    assert not robots.permis("/prive")
    assert robots.groupe == "*"


def test_agent_compare_sans_casse():
    robots = lire("USER-AGENT: NoEzia\nDISALLOW: /x\n")
    assert not robots.permis("/x")
    assert lire("User-agent: noezia\nDisallow: /x\n", agent="NOEZIA").permis("/y")


def test_plusieurs_agents_pour_un_meme_groupe():
    texte = "User-agent: gptbot\nUser-agent: noezia\nDisallow: /x\n"
    assert not lire(texte).permis("/x")


def test_groupes_du_meme_agent_se_cumulent():
    texte = "User-agent: noezia\nDisallow: /a\n\nUser-agent: autre\nDisallow: /\n\nUser-agent: noezia\nDisallow: /b\n"
    robots = lire(texte)
    assert not robots.permis("/a") and not robots.permis("/b")
    assert robots.permis("/c")


def test_aucun_groupe_correspondant_tout_est_permis():
    assert lire("User-agent: gptbot\nDisallow: /\n").permis("/a")


def test_commentaires_espaces_et_lignes_inconnues():
    texte = (
        "# commentaire\n"
        "Sitemap: http://exemple.test/plan.xml\n"
        "User-agent:   *   # tous\n"
        "Disallow:   /prive   # fiches privées\n"
        "Host: exemple.test\n"
    )
    robots = lire(texte)
    assert not robots.permis("/prive")
    assert robots.permis("/public")


def test_marque_d_ordre_des_octets_et_fins_de_ligne_windows():
    robots = lire("﻿User-agent: *\r\nDisallow: /x\r\n")
    assert not robots.permis("/x")


def test_crawl_delay_du_groupe_retenu():
    texte = "User-agent: *\nCrawl-delay: 5\n\nUser-agent: noezia\nCrawl-delay: 2.5\nDisallow: /x\n"
    assert lire(texte).crawl_delay == 2.5
    assert lire("User-agent: *\nCrawl-delay: 5\n").crawl_delay == 5
    assert lire("User-agent: *\nDisallow: /x\n").crawl_delay is None
    assert lire("User-agent: *\nCrawl-delay: beaucoup\n").crawl_delay is None
    assert lire("User-agent: *\nCrawl-delay: -3\n").crawl_delay is None


def test_les_pourcentages_se_comparent_apres_normalisation():
    robots = lire("User-agent: *\nDisallow: /caf%C3%A9\nDisallow: /a%7eb\n")
    assert not robots.permis("/café")
    assert not robots.permis("/caf%c3%a9")
    assert not robots.permis("/a~b")  # %7E est le tilde : même chose écrite autrement


def test_la_requete_compte_dans_la_comparaison():
    robots = lire("User-agent: *\nDisallow: /*?sl=\nDisallow: /liste?page=3\n")
    assert not robots.permis("/x?sl=abc")
    assert not robots.permis("/liste?page=3")
    assert robots.permis("/liste?page=2")


@pytest.mark.parametrize("ligne", ["Disallow /sans-deux-points", "Disallow", "n'importe quoi", ""])
def test_lignes_mal_formees_ignorees(ligne):
    assert lire(f"User-agent: *\n{ligne}\n").permis("/a")


def test_une_regle_avant_tout_user_agent_est_ignoree():
    assert lire("Disallow: /x\nUser-agent: *\nDisallow: /y\n").permis("/x")


def test_resume_pour_resume_json():
    robots = Robots.depuis_reponse(404, "", "noezia")
    resume = robots.resume("http://127.0.0.1:8770/robots.txt")
    assert resume == {
        "respecte": True,
        "agent": "noezia",
        "adresse": "http://127.0.0.1:8770/robots.txt",
        "statut": 404,
        "etat": "absent",
        "groupe": None,
        "crawl_delay": None,
    }
