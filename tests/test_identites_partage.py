"""Étape 4.2 : rien de partagé entre les identités d'une récolte (`gestionnaire.controler_identites`).

Refus au lancement, avant toute requête : deux identités au même profil Chrome (lien symbolique, profil copié), au même
proxy (même serveur et même utilisateur dans `proxy.json`, D-99), ou à la même graine (identité copiée) ; plusieurs
identités sans proxy sur un site qui n'est pas local (elles sortiraient par la même adresse) ; une identité bannie,
prise par un autre lancement, ou dont le proxy est inutilisable. Chaque identité reçoit sa propre graine, tirée du
hasard du système, jamais d'une graine commune. Les proxys sont ceux, locaux, de `tests/outils_proxy.py` : deux
identités sortent chacune par le sien. Aucun navigateur.
"""

from __future__ import annotations

import json
import shutil

import pytest
from outils_proxy import CibleDeTest, ProxyHttpDeTest, ecrire_proxy, get_absolu

from shadowlab.engines.noezia import identite as ident
from shadowlab.engines.noezia.gestionnaire import (
    MARQUEUR_PROFIL,
    PartageRefuse,
    controler_identites,
    preparer_identite,
)
from shadowlab.engines.noezia.proxy_identite import RelaisProxy
from shadowlab.engines.noezia.recettes import lire_texte

RECETTE_LOCALE = """
recette: 1
nom: essai-identites
hotes: [127.0.0.1]
depart:
  - url: http://127.0.0.1:8776/lab/vitrine/annonces
    type: liste
pages:
  liste:
    url: '^/lab/vitrine/annonces$'
"""
RECETTE_TIERCE = RECETTE_LOCALE.replace("127.0.0.1", "exemple.test").replace(
    "nom: essai-identites", "nom: essai-identites\nautorisation: périmètre de test autorisé"
)


@pytest.fixture
def racine(tmp_path, monkeypatch):
    dossier = tmp_path / "identites"
    monkeypatch.setenv("SHADOWLAB_IDENTITES", str(dossier))
    return dossier


@pytest.fixture
def locale():
    return lire_texte(RECETTE_LOCALE)


@pytest.fixture
def tierce():
    return lire_texte(RECETTE_TIERCE)


def test_chaque_identite_recoit_sa_graine_tiree_du_systeme(racine, locale):
    a, b = controler_identites(["ident-a", "ident-b"], locale)[0]
    assert a.graine != b.graine
    assert json.loads((racine / "ident-a" / "identite.json").read_text())["graine"] == a.graine
    # relue telle quelle : la graine est celle de l'identité, pas celle d'un lancement
    assert preparer_identite("ident-a").graine == a.graine


def test_la_graine_ne_vient_jamais_d_une_graine_commune(racine, locale, monkeypatch):
    """Même si le hasard de Python est fixé (graine de campagne), les graines des identités viennent du système."""
    import random

    random.seed(20261119)
    premiere = controler_identites(["ident-c"], locale)[0][0].graine
    random.seed(20261119)
    seconde = controler_identites(["ident-d"], locale)[0][0].graine
    assert premiere != seconde


def test_identite_copiee_meme_graine_refusee(racine, locale):
    controler_identites(["ident-a"], locale)
    shutil.copytree(racine / "ident-a", racine / "ident-b", ignore=shutil.ignore_patterns("verrou"))
    with pytest.raises(PartageRefuse, match="graine"):
        controler_identites(["ident-a", "ident-b"], locale)


def test_profil_chrome_par_lien_symbolique_refuse(racine, locale):
    controler_identites(["ident-a", "ident-b"], locale)
    shutil.rmtree(racine / "ident-b" / "chrome")
    (racine / "ident-b" / "chrome").symlink_to(racine / "ident-a" / "chrome")
    with pytest.raises(PartageRefuse, match="profil Chrome"):
        controler_identites(["ident-a", "ident-b"], locale)


def test_profil_chrome_copie_d_une_autre_identite_refuse(racine, locale):
    controler_identites(["ident-a", "ident-b"], locale)
    assert json.loads((racine / "ident-a" / "chrome" / MARQUEUR_PROFIL).read_text())["nom"] == "ident-a"
    shutil.rmtree(racine / "ident-b" / "chrome")
    shutil.copytree(racine / "ident-a" / "chrome", racine / "ident-b" / "chrome")
    with pytest.raises(PartageRefuse, match="profil Chrome"):
        controler_identites(["ident-a", "ident-b"], locale)


def test_meme_identite_deux_fois_refusee(racine, locale):
    with pytest.raises(PartageRefuse, match="deux fois"):
        controler_identites(["ident-a", "ident-a"], locale)


def test_nom_invalide_refuse(racine, locale):
    with pytest.raises(PartageRefuse, match="invalide"):
        controler_identites(["ident-a", "../ailleurs"], locale)


def test_identite_bannie_refusee_au_lancement_ecartee_a_la_reprise(racine, locale):
    controler_identites(["ident-a", "ident-b"], locale)
    ouverte = ident.ouvrir("ident-b")
    ouverte.marquer("banni", "statut 403 (motif bannissement)")
    ouverte.liberer()
    with pytest.raises(PartageRefuse, match="bannie"):
        controler_identites(["ident-a", "ident-b"], locale)
    gardees, ecartees = controler_identites(["ident-a", "ident-b"], locale, ecarter_bannies=True)
    assert [i.nom for i in gardees] == ["ident-a"] and ecartees == ["ident-b"]


def test_identite_prise_par_un_autre_lancement_refusee(racine, locale):
    ouverte = ident.ouvrir("ident-a")
    try:
        with pytest.raises(PartageRefuse, match="déjà utilisée"):
            controler_identites(["ident-a", "ident-b"], locale)
    finally:
        ouverte.liberer()


def test_meme_proxy_meme_utilisateur_refuse(racine, locale):
    ecrire_proxy(racine, "ident-a", "http://127.0.0.1:3128", "client-1", "mdp-a")
    ecrire_proxy(racine, "ident-b", "socks5://127.0.0.1:3128", "client-1", "mdp-b")  # même serveur, même utilisateur
    with pytest.raises(PartageRefuse, match="même proxy"):
        controler_identites(["ident-a", "ident-b"], locale)


def test_meme_serveur_autres_utilisateurs_accepte(racine, locale):
    """Un fournisseur de proxys résidentiels donne une sortie par utilisateur derrière un seul serveur."""
    ecrire_proxy(racine, "ident-a", "http://127.0.0.1:3128", "client-1", "mdp")
    ecrire_proxy(racine, "ident-b", "http://127.0.0.1:3128", "client-2", "mdp")
    gardees, _ = controler_identites(["ident-a", "ident-b"], locale)
    assert [i.proxy_masque for i in gardees] == ["http://***:***@127.0.0.1:3128"] * 2


def test_proxy_inutilisable_refuse_sans_rien_citer(racine, locale):
    ecrire_proxy(racine, "ident-a", "", brut='{"serveur": "ftp://secret:motdepasse@x:1"}')
    with pytest.raises(PartageRefuse) as erreur:
        controler_identites(["ident-a", "ident-b"], locale)
    assert "motdepasse" not in str(erreur.value)


def test_plusieurs_identites_sans_proxy_sur_un_site_tiers_refusees(racine, tierce):
    with pytest.raises(PartageRefuse, match="même adresse"):
        controler_identites(["ident-a", "ident-b"], tierce)


def test_une_seule_identite_sans_proxy_sur_un_site_tiers_acceptee(racine, tierce):
    gardees, _ = controler_identites(["ident-a"], tierce)
    assert gardees[0].proxy is None


def test_identites_sans_proxy_acceptees_sur_le_labo_local(racine, locale):
    """Sur nos sites locaux (l'Arena) on mesure sans proxy : toutes sortent par l'adresse du poste, ce qui est dit."""
    gardees, _ = controler_identites(["ident-a", "ident-b", "ident-c"], locale)
    assert [i.proxy for i in gardees] == [None, None, None]


def test_chaque_identite_sort_par_son_propre_proxy(racine, locale):
    """Deux identités, deux proxys locaux : le relais construit pour chacune (le code de `DriverNoezia.open`) ne joint
    que le sien, et la cible ne voit aucune connexion directe."""
    with CibleDeTest() as cible, ProxyHttpDeTest("ua", "pa", "A") as pa, ProxyHttpDeTest("ub", "pb", "B") as pb:
        ecrire_proxy(racine, "ident-a", pa.adresse, "ua", "pa")
        ecrire_proxy(racine, "ident-b", pb.adresse, "ub", "pb")
        gardees, _ = controler_identites(["ident-a", "ident-b"], locale)
        for info, proxy in zip(gardees, (pa, pb), strict=True):
            with RelaisProxy(ident.lire_proxy(info.nom), ("127.0.0.1",)) as relais:
                port = int(relais.adresse.rsplit(":", 1)[1])
                reponse = get_absolu(port, f"http://127.0.0.1:{cible.port}/page?id={info.nom}")
            assert reponse.split(b"\r\n", 1)[0].split()[1] == b"200", info.nom
            assert len(proxy.connexions) == 1, info.nom
        # la cible n'a vu que deux connexions, chacune venue d'un proxy : ni connexion directe, ni proxy partagé
        assert sorted(cible.connexions_recues) == sorted(
            [pa.connexions[0]["port_source"], pb.connexions[0]["port_source"]]
        )
