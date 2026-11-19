"""Palier 2, I10 : les comptes dans l'Arena (D-104). Table de comptes, bannissement du compte, « nouvel appareil ».

Critère du plan (2.3) : un compte banni est refusé **depuis un autre navigateur** (autre visiteur, autre empreinte E,
nouveau jeton), à la connexion comme sur l'espace privé d'une session déjà ouverte. Le refus a la forme de celui de
D-92 (`gardien.refus_banni`, motif `bannissement`) et porte l'en-tête `X-Arena-Refus: bannissement`, que la sentinelle
du moteur lit sur une page (D-104). Tout cela au seul profil qui bannit (`bannissement.actif`, `endurance`) : aux
niveaux 01 à 07, la connexion reste celle d'avant (cookie lié au jeton, sans durée) et rien de la mémoire des comptes
n'est lu ni écrit.

Règle « nouvel appareil » (D-104) : une connexion depuis un visiteur jamais vu sur le compte est enregistrée
(`appareils.nouvel_appareil`) ; au plus `appareils_par_jour` (4) appareils distincts connectés au compte en 24 h, le 5ᵉ
bannit le compte. Un humain sur deux ou trois appareils n'est jamais pris ; la même identité qui revient garde son
visiteur et n'est jamais un nouvel appareil après sa première connexion.
"""

from __future__ import annotations

import hashlib
import itertools
import sqlite3
from datetime import UTC, datetime, timedelta

import pytest
from test_bannissement import AUTRE_MONDE, MONDE, Navigateur, _bans, _entetes, _envoyer_empreinte
from test_visiteurs import nouveau_passage, nouvelle_experience

from shadowlab import cli, correlation
from shadowlab import database as db
from shadowlab.arena import bannissements, profils, visiteurs
from shadowlab.arena import comptes as comptes_arena
from shadowlab.arena import secret as secrets_arena
from shadowlab.site import comptes as fixtures
from shadowlab.site import gardien, pages

MAINTENANT = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)
SEUILS = profils.Bannissement(actif=True)
MOT_DE_PASSE = fixtures.COMPTES["demo"]


# --- Outils ------------------------------------------------------------------------------------------------


class NavigateurConnecte(Navigateur):
    """Un navigateur qui garde aussi le cookie de connexion (posé, puis effacé à la déconnexion)."""

    def _poser(self, reponse) -> None:
        super()._poser(reponse)
        for entete in reponse.headers.get_list("set-cookie"):
            nom, _, reste = entete.partition("=")
            if nom != gardien.COOKIE_CONNEXION:
                continue
            valeur = reste.split(";")[0].strip('"')
            if valeur and "max-age=0" not in entete.lower():
                self.cookies[nom] = valeur
            else:
                self.cookies.pop(nom, None)

    def page_de_connexion(self, jeton: str):
        return self.aller(jeton, "/lab/connexion")

    def se_connecter(self, jeton: str, compte: str = "demo", mot_de_passe: str | None = None, accept: str = ""):
        corps = {"identifiant": compte, "mot_de_passe": fixtures.COMPTES.get(compte, "") if mot_de_passe is None
                 else mot_de_passe}  # fmt: skip
        self._preparer()
        entetes = _entetes(self.reglages, self.profil, jeton)
        if accept:
            entetes["accept"] = accept
        reponse = self.client.post(f"/lab/connexion?sl={jeton}", headers=entetes, data=corps, follow_redirects=False)
        self._poser(reponse)
        return reponse

    def espace(self, jeton: str, accept: str = ""):
        self._preparer()
        entetes = _entetes(self.reglages, self.profil, jeton)
        if accept:
            entetes["accept"] = accept
        reponse = self.client.get(f"/lab/espace?sl={jeton}", headers=entetes, follow_redirects=False)
        self._poser(reponse)
        return reponse

    def deconnecter(self, jeton: str):
        self._preparer()
        reponse = self.client.get(
            f"/lab/deconnexion?sl={jeton}", headers=_entetes(self.reglages, self.profil, jeton), follow_redirects=False
        )
        self._poser(reponse)
        return reponse

    def entrer_et_se_connecter(self, jeton: str, compte: str = "demo") -> str:
        """Porte d'entrée, page de connexion, formulaire : rend le visiteur."""
        visiteur = self.franchir_la_porte(jeton)
        assert self.page_de_connexion(jeton).status_code == 200
        reponse = self.se_connecter(jeton, compte)
        assert reponse.status_code == 303 and reponse.headers["location"] == "/lab/espace", reponse.text
        return visiteur


@pytest.fixture
def experience(reglages) -> int:
    return nouvelle_experience(reglages, "comptes")


@pytest.fixture
def nouvelle_session(reglages, experience):
    compteur = itertools.count(1)

    def creer(monde: str = MONDE) -> str:
        return nouveau_passage(reglages, experience, repetition=next(compteur), monde=monde)

    return creer


@pytest.fixture
def cx(reglages):
    connexion = db.ouvrir(reglages.base_donnees)
    yield connexion
    connexion.close()


@pytest.fixture
def sans_suspicion(monkeypatch):
    """Aucun détecteur ne tranche (ni porte comportementale du login, ni page) : on isole les comptes."""
    monkeypatch.setattr(gardien, "suspicion", lambda *a, **k: [])


def _appareils(cx, compte: str = "demo", monde: str = MONDE) -> list[sqlite3.Row]:
    return cx.execute(
        "SELECT a.* FROM appareils a JOIN comptes c ON c.id = a.compte_id JOIN mondes m ON m.id = c.monde_id"
        " WHERE m.nom = ? AND c.identifiant = ? ORDER BY a.id",
        (monde, compte),
    ).fetchall()


def _bans_de_compte(cx) -> list[sqlite3.Row]:
    return [b for b in _bans(cx) if b["compte"] is not None]


def _decision_bannissement(cx, jeton: str) -> dict:
    lignes = [d for d in db.decisions_session(cx, jeton) if d["couche"] == "bannissement"]
    assert lignes, "aucune décision `bannissement` pour cette session"
    motifs = lignes[-1]["motifs"]
    return motifs[0] if isinstance(motifs, list) else motifs


def _est_un_refus_de_banni(reponse) -> bool:
    return (
        reponse.status_code == 403
        and reponse.headers.get(gardien.ENTETE_REFUS) == "bannissement"
        and gardien.COOKIE_CONNEXION not in reponse.cookies
    )


# --- Migration 12 ------------------------------------------------------------------------------------------


def test_les_migrations_passees_ne_changent_pas():
    """Règle du projet : on ajoute à la fin de `database.MIGRATIONS`, on ne touche jamais une migration passée."""
    assert len(db.MIGRATIONS) >= 12
    onze = hashlib.sha256("\x00".join(db.MIGRATIONS[:11]).encode()).hexdigest()
    assert onze == "681cc9a6629ca3f79de0f4a7c8ce9d0526d1488fc4ab055f37156b7d7f833212"


def test_migration_12_ajoute_les_comptes_les_appareils_et_le_compte_d_un_bannissement(tmp_path):
    assert "CREATE TABLE comptes" in db.MIGRATIONS[11] and "CREATE TABLE appareils" in db.MIGRATIONS[11]
    cx = db.ouvrir(tmp_path / "neuve.sqlite3")
    assert cx.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION >= 12
    tables = {r["name"] for r in cx.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"comptes", "appareils"} <= tables
    colonnes = {r["name"] for r in cx.execute("PRAGMA table_info(bannissements)")}
    assert "compte" in colonnes
    index = {r["name"] for r in cx.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert {"comptes_monde", "appareils_compte", "bannissements_compte"} <= index


def test_migration_12_sur_base_au_schema_11_garde_les_bannissements(tmp_path):
    chemin = tmp_path / "onze.sqlite3"
    brut = sqlite3.connect(chemin, isolation_level=None)
    for script in db.MIGRATIONS[:11]:
        for instruction in (s.strip() for s in script.split(";")):
            if instruction:
                brut.execute(instruction)
    brut.execute("PRAGMA user_version=11")
    brut.execute("INSERT INTO mondes (nom, cree_le) VALUES ('m', '2026-11-19T00:00:00.000+00:00')")
    brut.execute(
        "INSERT INTO bannissements (monde_id, visiteur, motif, cree_le) VALUES (1, 'v1', 'manuel', '2026-11-19')"
    )
    brut.close()
    cx = db.ouvrir(chemin)
    assert cx.execute("PRAGMA user_version").fetchone()[0] >= 12
    (ligne,) = cx.execute("SELECT visiteur, compte, motif FROM bannissements").fetchall()
    assert (ligne["visiteur"], ligne["compte"], ligne["motif"]) == ("v1", None, "manuel")


# --- Le profil ---------------------------------------------------------------------------------------------


def test_endurance_garde_la_connexion_30_jours_et_admet_4_appareils_par_jour():
    p = profils.charger().de("endurance")
    assert p is not None and p.bannissement.actif
    assert p.bannissement.appareils_par_jour == 4
    assert p.bannissement.duree_connexion_s == 30 * 24 * 3600


@pytest.mark.parametrize("niveau", ["01", "02", "03", "04", "05", "06", "07"])
def test_aucun_niveau_de_01_a_07_n_a_la_memoire_des_comptes(niveau):
    p = profils.charger().de(niveau)
    assert p is not None and not p.bannissement.actif


# --- La règle « nouvel appareil », fonction par fonction ---------------------------------------------------


def _visite(cx, monde: str, visiteur: str) -> None:
    """Le visiteur a déjà été vu dans le monde (comme après sa première page)."""
    cx.execute(
        "INSERT INTO visites (monde_id, visiteur, session_token, neuve, vue_le) VALUES (?, ?, NULL, 1, ?)",
        (visiteurs.identifiant_monde(cx, monde), visiteur, db.maintenant()),
    )


def test_le_premier_appareil_n_est_pas_un_nouvel_appareil_le_second_si(cx):
    premiere = comptes_arena.connecter(cx, MONDE, "ordinateur", "demo", SEUILS, MAINTENANT)
    assert (premiere.nouvel_appareil, premiere.appareils_24h, premiere.banni) == (False, 1, None)
    seconde = comptes_arena.connecter(cx, MONDE, "telephone", "demo", SEUILS, MAINTENANT + timedelta(minutes=5))
    assert (seconde.nouvel_appareil, seconde.appareils_24h, seconde.banni) == (True, 2, None)
    lignes = _appareils(cx)
    assert [(a["visiteur"], a["nouvel_appareil"]) for a in lignes] == [("ordinateur", 0), ("telephone", 1)]


def test_la_meme_identite_qui_revient_n_est_jamais_un_nouvel_appareil(cx):
    """Le moteur garde son visiteur d'une visite à l'autre : une ligne, `nouvel_appareil` à 0, à chaque reconnexion."""
    for jour in range(7):
        connexion = comptes_arena.connecter(cx, MONDE, "identite", "demo", SEUILS, MAINTENANT + timedelta(days=jour))
        assert not connexion.nouvel_appareil and connexion.banni is None
    (ligne,) = _appareils(cx)
    assert ligne["nouvel_appareil"] == 0 and ligne["visiteur"] == "identite"


def test_un_humain_sur_trois_appareils_n_est_jamais_banni(cx):
    """Ordinateur, téléphone, tablette : chacun se reconnecte plusieurs fois par jour pendant une semaine."""
    instant = MAINTENANT
    for _ in range(7 * 4):
        for appareil in ("ordinateur", "telephone", "tablette"):
            assert comptes_arena.connecter(cx, MONDE, appareil, "demo", SEUILS, instant).banni is None
            instant += timedelta(hours=2)
    assert not _bans_de_compte(cx)
    assert sum(a["nouvel_appareil"] for a in _appareils(cx)) == 2


def test_le_cinquieme_appareil_en_24_h_bannit_le_compte_et_quatre_non(cx):
    for n in range(4):
        connexion = comptes_arena.connecter(cx, MONDE, f"v{n}", "demo", SEUILS, MAINTENANT + timedelta(hours=n))
        assert connexion.banni is None, n
    assert not _bans_de_compte(cx)
    cinquieme = comptes_arena.connecter(cx, MONDE, "v4", "demo", SEUILS, MAINTENANT + timedelta(hours=5))
    assert cinquieme.banni == "appareils_par_jour" and cinquieme.appareils_24h == 5
    (ban,) = _bans_de_compte(cx)
    assert (ban["monde"], ban["compte"], ban["visiteur"], ban["empreinte"]) == (MONDE, "demo", None, None)
    assert ban["motif"] == "appareils_par_jour"
    # le refusé n'est pas connecté : sa ligne existe (la tentative est notée) mais sans durée de connexion
    refuse = next(a for a in _appareils(cx) if a["visiteur"] == "v4")
    assert refuse["connecte_jusqu_au"] is None


def test_les_appareils_de_plus_de_24_h_ne_comptent_pas(cx):
    for n in range(4):
        comptes_arena.connecter(cx, MONDE, f"ancien{n}", "demo", SEUILS, MAINTENANT - timedelta(hours=30))
    for n in range(4):
        assert comptes_arena.connecter(cx, MONDE, f"v{n}", "demo", SEUILS, MAINTENANT).banni is None
    assert not _bans_de_compte(cx)


def test_le_seuil_vient_du_profil(cx):
    serre = profils.Bannissement(actif=True, appareils_par_jour=1)
    assert comptes_arena.connecter(cx, MONDE, "a", "demo", serre, MAINTENANT).banni is None
    assert comptes_arena.connecter(cx, MONDE, "b", "demo", serre, MAINTENANT).banni == "appareils_par_jour"


@pytest.mark.parametrize("monde", [visiteurs.MONDE_MANUEL, visiteurs.MONDE_HORS_PASSAGE])
def test_aucun_bannissement_automatique_de_compte_dans_les_mondes_partages(cx, monde):
    for n in range(8):
        assert comptes_arena.connecter(cx, monde, f"v{n}", "demo", SEUILS, MAINTENANT).banni is None
    assert not _bans_de_compte(cx)


def test_les_comptes_sont_propres_au_monde(cx):
    for n in range(4):
        comptes_arena.connecter(cx, MONDE, f"v{n}", "demo", SEUILS, MAINTENANT)
    assert comptes_arena.connecter(cx, AUTRE_MONDE, "v9", "demo", SEUILS, MAINTENANT).banni is None
    assert len(_appareils(cx, monde=AUTRE_MONDE)) == 1


# --- La connexion dans l'application (profil `endurance`) --------------------------------------------------


def test_une_connexion_enregistre_le_compte_et_pose_un_cookie_durable(
    client, reglages, cx, nouvelle_session, sans_suspicion
):
    nav = NavigateurConnecte(client, reglages)
    jeton = nouvelle_session()
    visiteur = nav.franchir_la_porte(jeton)
    assert nav.page_de_connexion(jeton).status_code == 200
    reponse = nav.se_connecter(jeton)
    assert reponse.status_code == 303 and reponse.headers["location"] == "/lab/espace"
    (entete,) = [e for e in reponse.headers.get_list("set-cookie") if e.startswith(gardien.COOKIE_CONNEXION)]
    assert f"max-age={30 * 24 * 3600}" in entete.lower() and "httponly" in entete.lower()
    assert MOT_DE_PASSE not in entete
    (appareil,) = _appareils(cx)
    assert (appareil["visiteur"], appareil["nouvel_appareil"]) == (visiteur, 0)
    assert appareil["connecte_jusqu_au"] is not None
    espace = nav.espace(jeton)
    assert espace.status_code == 200 and 'data-compte="demo"' in espace.text


def test_la_connexion_survit_a_une_nouvelle_session_du_meme_navigateur(
    client, reglages, nouvelle_session, sans_suspicion
):
    """Le test de la ligne 2.5 du plan, côté Arena : fermeture du navigateur, relance, nouveau jeton, même visiteur."""
    nav = NavigateurConnecte(client, reglages)
    nav.entrer_et_se_connecter(nouvelle_session())
    retour = nouvelle_session()
    espace = nav.espace(retour)
    assert espace.status_code == 200 and 'data-compte="demo"' in espace.text


def test_le_cookie_de_connexion_ne_vaut_que_pour_son_visiteur(client, reglages, nouvelle_session, sans_suspicion):
    nav = NavigateurConnecte(client, reglages)
    nav.entrer_et_se_connecter(nouvelle_session())
    voleur = NavigateurConnecte(client, reglages)
    jeton = nouvelle_session()
    voleur.franchir_la_porte(jeton)
    voleur.cookies[gardien.COOKIE_CONNEXION] = nav.cookies[gardien.COOKIE_CONNEXION]
    reponse = voleur.espace(jeton)
    assert reponse.status_code == 303 and reponse.headers["location"] == "/lab/connexion"


def test_un_cookie_de_connexion_falsifie_est_refuse(client, reglages, nouvelle_session, sans_suspicion):
    nav = NavigateurConnecte(client, reglages)
    jeton = nouvelle_session()
    nav.entrer_et_se_connecter(jeton)
    valeur = nav.cookies[gardien.COOKIE_CONNEXION]
    nav.cookies[gardien.COOKIE_CONNEXION] = "analyste" + valeur[valeur.index(".") :]  # un autre compte, même signature
    assert nav.espace(jeton).status_code == 303


def test_un_second_appareil_est_enregistre_sans_bannir(client, reglages, cx, nouvelle_session, sans_suspicion):
    ordinateur, telephone = NavigateurConnecte(client, reglages), NavigateurConnecte(client, reglages)
    a = ordinateur.entrer_et_se_connecter(nouvelle_session())
    b = telephone.entrer_et_se_connecter(nouvelle_session())
    assert [(x["visiteur"], x["nouvel_appareil"]) for x in _appareils(cx)] == [(a, 0), (b, 1)]
    assert not _bans_de_compte(cx)
    for nav in (ordinateur, telephone):
        assert nav.espace(nouvelle_session()).status_code == 200


def test_le_meme_navigateur_qui_se_reconnecte_reste_un_seul_appareil(
    client, reglages, cx, nouvelle_session, sans_suspicion
):
    nav = NavigateurConnecte(client, reglages)
    jeton = nouvelle_session()
    nav.entrer_et_se_connecter(jeton)
    for _ in range(3):
        assert nav.deconnecter(jeton).status_code == 303
        assert gardien.COOKIE_CONNEXION not in nav.cookies
        jeton = nouvelle_session()
        assert nav.page_de_connexion(jeton).status_code == 200
        assert nav.se_connecter(jeton).status_code == 303
    (appareil,) = _appareils(cx)
    assert appareil["nouvel_appareil"] == 0


def test_le_cinquieme_navigateur_en_24_h_est_refuse_et_le_compte_banni(
    client, reglages, cx, nouvelle_session, sans_suspicion
):
    navs = [NavigateurConnecte(client, reglages) for _ in range(5)]
    for nav in navs[:4]:
        nav.entrer_et_se_connecter(nouvelle_session())
    jeton = nouvelle_session()
    navs[4].franchir_la_porte(jeton)
    assert navs[4].page_de_connexion(jeton).status_code == 200
    refus = navs[4].se_connecter(jeton)
    assert _est_un_refus_de_banni(refus)
    assert refus.json() == {"bloque_par": "bannissement"}
    decision = _decision_bannissement(cx, jeton)
    assert (decision["par"], decision["motif"], decision["compte"]) == ("compte", "appareils_par_jour", "demo")
    # le compte est banni pour tous ses appareils, même le premier
    assert _est_un_refus_de_banni(navs[0].espace(nouvelle_session()))


# --- Le critère du plan : un compte banni est refusé depuis un autre navigateur ----------------------------


def test_un_compte_banni_est_refuse_a_la_connexion_depuis_un_autre_navigateur(
    client, reglages, cx, nouvelle_session, sans_suspicion
):
    premier = NavigateurConnecte(client, reglages)
    jeton_a = nouvelle_session()
    visiteur_a = premier.entrer_et_se_connecter(jeton_a)
    assert _envoyer_empreinte(premier, jeton_a, "mac-a").status_code == 204
    assert comptes_arena.bannir_compte_connu(cx, MONDE, "demo") is True
    # Un autre navigateur : autre visiteur, autre empreinte E, nouveau jeton.
    autre = NavigateurConnecte(client, reglages)
    jeton_b = nouvelle_session()
    visiteur_b = autre.franchir_la_porte(jeton_b)
    assert _envoyer_empreinte(autre, jeton_b, "pc-b").status_code == 204
    assert visiteur_b != visiteur_a and jeton_b != jeton_a
    assert correlation.empreinte_de_session(cx, jeton_b) != correlation.empreinte_de_session(cx, jeton_a)
    assert autre.page_de_connexion(jeton_b).status_code == 200  # la page du formulaire reste servie
    refus = autre.se_connecter(jeton_b)
    assert _est_un_refus_de_banni(refus)
    assert refus.json() == {"bloque_par": "bannissement"}  # la forme du refus de D-92
    decision = _decision_bannissement(cx, jeton_b)
    assert (decision["par"], decision["compte"], decision["motif"]) == ("compte", "demo", "manuel")
    assert not _appareils(cx) or all(a["visiteur"] != visiteur_b for a in _appareils(cx))
    # une navigation reçoit la page de refus de toujours, octet pour octet, avec l'en-tête
    page = autre.se_connecter(jeton_b, accept="text/html,application/xhtml+xml")
    assert _est_un_refus_de_banni(page) and page.text == pages.page_blocage()


def test_un_compte_banni_est_refuse_sur_l_espace_d_une_session_deja_ouverte(
    client, reglages, cx, nouvelle_session, sans_suspicion
):
    nav = NavigateurConnecte(client, reglages)
    jeton = nouvelle_session()
    nav.entrer_et_se_connecter(jeton)
    assert nav.espace(jeton).status_code == 200
    comptes_arena.bannir_compte_connu(cx, MONDE, "demo")
    refus = nav.espace(jeton, accept="text/html")
    assert _est_un_refus_de_banni(refus) and refus.text == pages.page_blocage()
    assert _decision_bannissement(cx, jeton)["par"] == "compte"
    assert _est_un_refus_de_banni(nav.espace(nouvelle_session()))  # et à la visite suivante


def test_les_identifiants_faux_d_un_compte_banni_restent_un_401(client, reglages, cx, nouvelle_session, sans_suspicion):
    """Le bannissement ne se lit qu'avec le bon mot de passe : un inconnu n'apprend pas qu'un compte est banni."""
    NavigateurConnecte(client, reglages).entrer_et_se_connecter(nouvelle_session())
    comptes_arena.bannir_compte_connu(cx, MONDE, "demo")
    autre = NavigateurConnecte(client, reglages)
    jeton = nouvelle_session()
    autre.franchir_la_porte(jeton)
    assert autre.se_connecter(jeton, mot_de_passe="faux").status_code == 401


def test_un_compte_banni_ne_bannit_ni_le_visiteur_ni_l_empreinte(
    client, reglages, cx, nouvelle_session, sans_suspicion
):
    nav = NavigateurConnecte(client, reglages)
    nav.entrer_et_se_connecter(nouvelle_session())
    comptes_arena.bannir_compte_connu(cx, MONDE, "demo")
    assert nav.aller(nouvelle_session()).status_code == 200  # les pages publiques restent servies
    assert nav.se_connecter(nouvelle_session(), "analyste").status_code == 303  # un autre compte aussi
    assert [b["visiteur"] for b in _bans(cx)] == [None]


def test_le_bannissement_d_un_compte_est_propre_au_monde(client, reglages, cx, nouvelle_session, sans_suspicion):
    ailleurs = NavigateurConnecte(client, reglages)
    ailleurs.entrer_et_se_connecter(nouvelle_session(AUTRE_MONDE))
    comptes_arena.bannir_compte_connu(cx, AUTRE_MONDE, "demo")
    ici = NavigateurConnecte(client, reglages)
    ici.entrer_et_se_connecter(nouvelle_session())  # ne lève pas : connexion acceptée


def test_un_visiteur_banni_ne_se_connecte_pas(client, reglages, cx, nouvelle_session, sans_suspicion):
    nav = NavigateurConnecte(client, reglages)
    jeton = nouvelle_session()
    visiteur = nav.franchir_la_porte(jeton)
    assert nav.page_de_connexion(jeton).status_code == 200
    bannissements.bannir(cx, MONDE, visiteur=visiteur, motif="manuel")
    refus = nav.se_connecter(jeton)
    assert _est_un_refus_de_banni(refus)
    assert _decision_bannissement(cx, jeton)["par"] == "visiteur"
    assert not _appareils(cx)


# --- Bannissement automatique : un visiteur banni alors qu'il est connecté ---------------------------------


def test_un_visiteur_banni_pendant_qu_il_est_connecte_fait_bannir_son_compte(
    client, reglages, cx, nouvelle_session, sans_suspicion
):
    nav = NavigateurConnecte(client, reglages)
    visiteur = nav.entrer_et_se_connecter(nouvelle_session())
    bannissements.bannir(cx, MONDE, visiteur=visiteur, motif="detecte:composite")
    (ban,) = _bans_de_compte(cx)
    assert (ban["monde"], ban["compte"], ban["visiteur"]) == (MONDE, "demo", None)
    assert ban["motif"] == "visiteur_banni:detecte:composite"
    autre = NavigateurConnecte(client, reglages)
    jeton = nouvelle_session()
    autre.franchir_la_porte(jeton)
    assert _est_un_refus_de_banni(autre.se_connecter(jeton))
    bannissements.bannir(cx, MONDE, visiteur=visiteur, motif="detecte:composite")  # rien en double
    assert len(_bans_de_compte(cx)) == 1


def test_un_visiteur_deconnecte_puis_banni_ne_fait_pas_bannir_le_compte(
    client, reglages, cx, nouvelle_session, sans_suspicion
):
    nav = NavigateurConnecte(client, reglages)
    jeton = nouvelle_session()
    visiteur = nav.entrer_et_se_connecter(jeton)
    assert nav.deconnecter(jeton).status_code == 303
    bannissements.bannir(cx, MONDE, visiteur=visiteur, motif="manuel")
    assert not _bans_de_compte(cx)


def test_un_visiteur_banni_dont_la_connexion_a_expire_ne_fait_pas_bannir_le_compte(cx):
    comptes_arena.connecter(cx, MONDE, "v1", "demo", SEUILS, datetime.now(UTC) - timedelta(days=31))
    bannissements.bannir(cx, MONDE, visiteur="v1", motif="manuel")
    assert not _bans_de_compte(cx)


def test_la_propagation_ne_touche_ni_un_autre_visiteur_ni_un_autre_monde(cx):
    maintenant = datetime.now(UTC)
    comptes_arena.connecter(cx, MONDE, "v1", "demo", SEUILS, maintenant)
    comptes_arena.connecter(cx, MONDE, "v2", "analyste", SEUILS, maintenant)
    comptes_arena.connecter(cx, AUTRE_MONDE, "v1", "analyste", SEUILS, maintenant)
    bannissements.bannir(cx, MONDE, visiteur="v1", motif="manuel")
    assert [(b["monde"], b["compte"]) for b in _bans_de_compte(cx)] == [(MONDE, "demo")]


@pytest.mark.parametrize("monde", [visiteurs.MONDE_MANUEL, visiteurs.MONDE_HORS_PASSAGE])
def test_pas_de_propagation_dans_les_mondes_partages(cx, monde):
    comptes_arena.connecter(cx, monde, "v1", "demo", SEUILS, datetime.now(UTC))
    bannissements.bannir(cx, monde, visiteur="v1", motif="manuel")  # le bannissement manuel du visiteur vaut
    assert len(_bans(cx)) == 1 and not _bans_de_compte(cx)  # mais rien n'est déduit pour le compte


# --- L'en-tête du refus, et rien d'autre ne change ---------------------------------------------------------


def test_le_refus_d_un_visiteur_banni_porte_l_en_tete_et_la_page_de_toujours(
    client, reglages, cx, nouvelle_session, sans_suspicion
):
    nav = NavigateurConnecte(client, reglages)
    visiteur = nav.franchir_la_porte(nouvelle_session())
    bannissements.bannir(cx, MONDE, visiteur=visiteur, motif="manuel")
    jeton = nouvelle_session()
    nav._preparer()
    entetes = {**_entetes(reglages, "endurance", jeton), "accept": "text/html"}
    refus = client.get(f"/lab/vitrine?sl={jeton}", headers=entetes)
    assert refus.status_code == 403 and refus.headers.get(gardien.ENTETE_REFUS) == "bannissement"
    assert refus.text == pages.page_blocage()


def test_un_refus_qui_n_est_pas_un_bannissement_n_a_pas_l_en_tete(client, reglages, cx, nouvelle_session):
    nav = NavigateurConnecte(client, reglages, "04")
    jeton = nouvelle_session()
    nav.franchir_la_porte(jeton)
    db.enregistrer_decision(cx, jeton, "honeypot", "declenche", "/lab/piege", [])
    arret = nav.aller(jeton)
    assert arret.status_code == 403 and gardien.ENTETE_REFUS not in arret.headers
    defi = NavigateurConnecte(client, reglages).aller(nouvelle_session())
    assert defi.status_code == 403 and gardien.ENTETE_REFUS not in defi.headers


@pytest.mark.parametrize("niveau", ["05", "06", "07"])
def test_aux_niveaux_05_a_07_la_connexion_reste_celle_d_avant(
    client, reglages, cx, nouvelle_session, sans_suspicion, monkeypatch, niveau
):
    """Cookie lié au jeton, sans durée ; un nouveau jeton renvoie à la connexion ; rien de la mémoire des comptes."""

    def interdit(*a, **k):
        raise AssertionError("la mémoire des comptes est appelée alors que le profil ne bannit pas")

    for nom in ("connecter", "motif_bannissement", "deconnecter", "creer_cookie", "lire_cookie"):
        monkeypatch.setattr(comptes_arena, nom, interdit)
    monkeypatch.setattr(bannissements.Surveillance, "juger", interdit)
    nav = NavigateurConnecte(client, reglages, niveau)
    jeton = nouvelle_session()
    _portes_du_niveau_franchies(nav, reglages, jeton)
    reponse = nav.se_connecter(jeton)
    assert reponse.status_code == 303 and reponse.headers["location"] == "/lab/espace"
    (entete,) = [e for e in reponse.headers.get_list("set-cookie") if e.startswith(gardien.COOKIE_CONNEXION)]
    assert "max-age" not in entete.lower() and "expires" not in entete.lower()
    espace = nav.espace(jeton)
    assert espace.status_code == 200 and 'data-compte="demo"' in espace.text
    autre = nouvelle_session()
    _portes_du_niveau_franchies(nav, reglages, autre)
    retour = nav.espace(autre)
    assert retour.status_code == 303 and retour.headers["location"] == "/lab/connexion"  # cookie lié à la session
    _portes_du_niveau_franchies(nav, reglages, jeton)
    assert nav.deconnecter(jeton).status_code == 303
    assert cx.execute("SELECT COUNT(*) FROM comptes").fetchone()[0] == 0
    assert not _bans(cx)


def _portes_du_niveau_franchies(nav: NavigateurConnecte, reglages, jeton: str) -> None:
    """Les cookies de réussite des portes d'un niveau 05 à 07 (défi, Turnstile, reCAPTCHA, CAPTCHA), pour ce jeton :
    seule la connexion est examinée ici."""
    from shadowlab.arena import defis

    secret = secrets_arena.charger(reglages.dossier_arena)
    for usage, nom in (
        ("defi", gardien.COOKIE_DEFI),
        ("turnstile", gardien.COOKIE_TURNSTILE),
        ("recaptcha", gardien.COOKIE_RECAPTCHA),
        ("captcha", gardien.COOKIE_CAPTCHA),
    ):
        nav.cookies[nom] = defis.creer_cookie(secret, usage, jeton, "")


# --- La commande `shadowlab arena bannir --compte` ---------------------------------------------------------


def test_arena_bannir_un_compte_ecrit_la_ligne_et_le_compte_est_refuse(
    client, reglages, cx, nouvelle_session, sans_suspicion, capsys
):
    NavigateurConnecte(client, reglages).entrer_et_se_connecter(nouvelle_session())
    assert cli.main(["arena", "bannir", "--compte", "demo", "--monde", MONDE]) == 0
    (ban,) = _bans_de_compte(cx)
    assert (ban["monde"], ban["compte"], ban["visiteur"], ban["empreinte"], ban["motif"], ban["expire_le"]) == (
        MONDE, "demo", None, None, "manuel", None,
    )  # fmt: skip
    assert "demo" in capsys.readouterr().out
    autre = NavigateurConnecte(client, reglages)
    jeton = nouvelle_session()
    autre.franchir_la_porte(jeton)
    assert _est_un_refus_de_banni(autre.se_connecter(jeton))
    assert cli.main(["arena", "bannir", "--compte", "demo", "--monde", MONDE]) == 0  # déjà banni : rien de plus
    assert len(_bans_de_compte(cx)) == 1


def test_arena_bannir_refuse_un_compte_ou_un_monde_inconnu(client, reglages, cx, nouvelle_session, sans_suspicion,
                                                           capsys):  # fmt: skip
    NavigateurConnecte(client, reglages).entrer_et_se_connecter(nouvelle_session())
    assert cli.main(["arena", "bannir", "--compte", "demo", "--monde", "monde-inexistant"]) == 2
    assert cli.main(["arena", "bannir", "--compte", "analyste", "--monde", MONDE]) == 2  # jamais connecté ici
    assert cli.main(["arena", "bannir", "--compte", "inconnu", "--monde", MONDE]) == 2
    assert not _bans(cx)
    assert "monde-inexistant" not in {r["nom"] for r in cx.execute("SELECT nom FROM mondes")}
    assert "analyste" in capsys.readouterr().err


@pytest.mark.parametrize(
    "arguments",
    [
        ["arena", "bannir", "--monde", MONDE],
        ["arena", "bannir", "--visiteur", "v1", "--compte", "demo", "--monde", MONDE],
        ["arena", "bannir", "--compte", "demo"],
    ],
)
def test_arena_bannir_exige_un_visiteur_ou_un_compte_et_le_monde(reglages, arguments):
    with pytest.raises(SystemExit) as sortie:
        cli.main(arguments)
    assert sortie.value.code == 2
