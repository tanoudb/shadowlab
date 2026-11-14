"""Corrections de la quatrième relecture du site public (D-77), au-delà des quinze essais de
`tests/test_public_relecture4.py` : commande `shadowlab public sessions`, journal de la base vidé après une
suppression, lignes orphelines retirées, requêtes HEAD, crédits des photos, vérité des textes de la notice.

Chaque test a été vu en échec avant sa correction.
"""

from __future__ import annotations

import re

import pytest
from parsel import Selector
from test_public import (
    AUTRE_IP,
    CONTACT,
    HOTE,
    IP,
    ORIGINE,
    champs_du_formulaire,
    collecter,
    commencer,
    fabriquer,
    fichier_de_journal,  # noqa: F401  (fixture)
    ouvrir,
)

from shadowlab import database as db
from shadowlab.config import ReglagesPublics
from shadowlab.public import donnees


@pytest.fixture
def reglages_publics(tmp_path) -> ReglagesPublics:
    return ReglagesPublics(
        hotes=(HOTE,),
        contact=CONTACT,
        conservation_jours=90,
        https=True,
        port=8771,
        base_donnees=tmp_path / "public" / "public.sqlite3",
        entete_ip="X-Forwarded-For",
        vitrine_graine=20261111,
        vitrine_taille=45,
    )


@pytest.fixture
def client(reglages_publics):
    with fabriquer(reglages_publics) as c:
        yield c


def supprimer_sa_session(client) -> None:
    champs = champs_du_formulaire(client.get("/session").text, "/session/supprimer")
    assert client.post("/session/supprimer", data=champs, headers={"Origin": ORIGINE}).status_code == 200


# --- B1 : repérer une session abusive ---------------------------------------------------------------


def test_commande_sessions_les_plus_grosses_d_abord(monkeypatch, reglages_publics, capsys):
    """`shadowlab public sessions` liste chaque session (identifiant, début, état, requêtes notées, nombre et volume
    des envois), la plus grosse d'abord : le responsable repère une session abusive et la supprime avec
    `shadowlab public supprimer <identifiant>`."""
    from shadowlab import cli

    monkeypatch.setenv("SHADOWLAB_PUBLIC_BASE", str(reglages_publics.base_donnees))
    monkeypatch.setenv("SHADOWLAB_PUBLIC_HOTES", HOTE)
    monkeypatch.setenv("SHADOWLAB_PUBLIC_CONTACT", CONTACT)
    assert cli.main(["public", "sessions"]) == 0
    assert "Aucune session" in capsys.readouterr().out
    with fabriquer(reglages_publics) as c:
        petite = commencer(c, IP)
        assert collecter(c, petite).status_code == 204
        c.cookies.clear()
        grosse = commencer(c, AUTRE_IP)
        for _ in range(3):
            assert collecter(c, grosse, payload={"remplissage": "a" * 5000}).status_code == 204
        champs = champs_du_formulaire(c.get("/lab/vitrine").text, "/session/terminer")
        assert c.post("/session/terminer", data=champs, headers={"Origin": ORIGINE}).status_code == 200
    capsys.readouterr()
    assert cli.main(["public", "sessions"]) == 0
    sortie = capsys.readouterr().out
    lignes = [ligne.split() for ligne in sortie.splitlines() if re.match(r"[0-9a-f]{32}\b", ligne)]
    assert [ligne[0] for ligne in lignes] == [grosse, petite], sortie
    cx = ouvrir(reglages_publics)
    try:
        for ligne, jeton in zip(lignes, (grosse, petite), strict=True):
            debut = cx.execute("SELECT started_at FROM runs WHERE session_token = ?", (jeton,)).fetchone()[0]
            requetes = cx.execute(
                "SELECT COUNT(*) FROM observations_http WHERE session_token = ?", (jeton,)
            ).fetchone()[0]
            envois, volume = cx.execute(
                "SELECT COUNT(*), SUM(LENGTH(CAST(payload AS BLOB))) FROM observations_js WHERE session_token = ?",
                (jeton,),
            ).fetchone()
            assert (ligne[1], ligne[2]) == (debut[:10], debut[11:16]), ligne  # début, en UTC, à la minute
            assert ligne[3] == ("terminée" if jeton == grosse else "ouverte"), ligne
            assert [int(n) for n in ligne[4:7]] == [requetes, envois, volume], ligne
    finally:
        cx.close()
    assert "shadowlab public supprimer" in sortie


# --- Après une suppression : rien ne reste lisible dans le journal de la base -------------------------


@pytest.mark.parametrize("par", ["visiteur", "purge"])
def test_suppression_ne_laisse_rien_dans_le_journal_de_la_base(reglages_publics, par):
    """`secure_delete` vide les pages dans la base ; le journal WAL, lui, garde les versions précédentes des pages
    jusqu'au point de contrôle suivant. Après une suppression (par le visiteur ou par la purge), le journal est vidé :
    ni lui ni la base ne contiennent plus les octets de la session.

    Une seconde connexion reste ouverte, inactive, pendant tout l'essai : sans elle, la fermeture de la dernière
    connexion viderait le journal d'elle-même et l'essai passerait sans la correction."""
    from datetime import UTC, datetime, timedelta

    temoin = "marque-a-effacer-7f3a9c"
    gardienne = ouvrir(reglages_publics)
    try:
        with fabriquer(reglages_publics) as c:
            jeton = commencer(c)
            assert collecter(c, jeton, payload={"temoin": temoin}).status_code == 204
            if par == "visiteur":
                supprimer_sa_session(c)
        if par == "purge":
            cx = donnees.ouvrir(reglages_publics.base_donnees)
            try:
                assert donnees.purger(cx, 90, maintenant=datetime.now(UTC) + timedelta(days=91)) == 1
            finally:
                cx.close()
        base = reglages_publics.base_donnees
        journal = base.with_name(base.name + "-wal")
        assert temoin.encode() not in (journal.read_bytes() if journal.exists() else b""), "journal WAL"
        assert temoin.encode() not in base.read_bytes(), "base"
    finally:
        gardienne.close()


# --- C2 : aucune ligne d'observation sans sa session ------------------------------------------------


def test_purge_et_suppression_retirent_les_lignes_orphelines(client, reglages_publics):
    """Une ligne d'observation dont la session n'existe plus (envoi arrivé après une suppression, base écrite par
    une version plus ancienne) n'est jamais retrouvée par la purge, qui part des sessions : elle est retirée par
    la purge et par toute suppression."""
    orpheline = "0" * 32

    def semer() -> None:
        cx = ouvrir(reglages_publics)
        try:
            cx.execute(
                "INSERT INTO observations_js (session_token, received_at, kind, page, payload)"
                " VALUES (?, ?, 'empreinte', '/lab/vitrine', '{}')",
                (orpheline, db.maintenant()),
            )
            cx.execute(
                "INSERT INTO observations_http (session_token, received_at, method, path, headers, cookies)"
                " VALUES (?, ?, 'GET', '/lab/vitrine', '[]', '[]')",
                (orpheline, db.maintenant()),
            )
        finally:
            cx.close()

    def restes() -> int:
        cx = ouvrir(reglages_publics)
        try:
            return sum(
                cx.execute(f"SELECT COUNT(*) FROM {table} WHERE session_token = ?", (orpheline,)).fetchone()[0]
                for table in ("observations_js", "observations_http")
            )
        finally:
            cx.close()

    garder = commencer(client)
    semer()
    cx = donnees.ouvrir(reglages_publics.base_donnees)
    try:
        assert donnees.purger(cx, 90) == 0
    finally:
        cx.close()
    assert restes() == 0, "purge"
    semer()
    client.cookies.clear()
    commencer(client, AUTRE_IP)
    supprimer_sa_session(client)
    assert restes() == 0, "suppression"
    cx = ouvrir(reglages_publics)
    try:
        assert cx.execute("SELECT COUNT(*) FROM runs WHERE session_token = ?", (garder,)).fetchone()[0] == 1
        assert cx.execute("SELECT COUNT(*) FROM observations_http WHERE session_token = ?", (garder,)).fetchone()[0]
    finally:
        cx.close()


# --- HEAD : une page servie en GET répond aussi en HEAD, sans corps ----------------------------------

PAGES_EN_GET = ("/", "/fr", "/en/information", "/session", "/contact", "/lab/vitrine", "/lab/social/fil")


@pytest.mark.parametrize("chemin", PAGES_EN_GET)
def test_head_repond_comme_get_sans_corps_ni_ligne_au_journal(client, fichier_de_journal, chemin):  # noqa: F811
    """Un robot de vérification de lien ou un outil de surveillance envoie HEAD : avant, 405 et une ligne au journal
    des erreurs. HEAD répond comme GET (statut, type, en-têtes de sécurité), sans corps."""
    get, head = client.get(chemin), client.head(chemin)
    assert head.status_code == get.status_code == 200, head.status_code
    assert head.content == b""
    for entete in ("content-type", "content-security-policy", "x-frame-options", "strict-transport-security"):
        assert head.headers.get(entete) == get.headers.get(entete), entete
    assert fichier_de_journal() == []


def test_head_sur_l_accueil_ne_compte_aucun_chargement(client, reglages_publics):
    for chemin in ("/", "/fr", "/en"):
        assert client.head(chemin).status_code == 200
    cx = ouvrir(reglages_publics)
    try:
        assert cx.execute("SELECT COALESCE(SUM(accueil), 0) FROM frequentation").fetchone()[0] == 0
    finally:
        cx.close()
    assert client.get("/fr").status_code == 200
    cx = ouvrir(reglages_publics)
    try:
        assert cx.execute("SELECT COALESCE(SUM(accueil), 0) FROM frequentation").fetchone()[0] == 1
    finally:
        cx.close()


# --- B3 : crédits des photos ------------------------------------------------------------------------


@pytest.mark.parametrize("langue", ["fr", "en"])
def test_pied_des_pages_de_l_etude_mene_aux_credits_sauf_le_contact(client, langue):
    """Les photos sous CC BY et CC BY-SA demandent l'attribution : le pied de chaque page de l'étude mène à la page
    des crédits, dans la langue de la page. Les pages de contact ne mènent qu'à « / » et « /contact… » (D-67) : pas
    de lien vers les crédits."""
    libelle = {"fr": "Crédits des photos", "en": "Photo credits"}[langue]
    client.headers["Accept-Language"] = langue
    for chemin in (f"/{langue}", f"/{langue}/information", "/session"):
        pied = Selector(client.get(chemin).text).css("footer.etude-pied")
        assert pied.css('a[href="/lab/social/credits"]::text').get() == libelle, chemin
    accueil = Selector(client.get(f"/{langue}").text)
    sous_les_photos = accueil.css('main a[href="/lab/social/credits"]::text').getall()
    assert sous_les_photos == [libelle, libelle], "sous la mosaïque et sous les vignettes"
    for chemin in ("/contact", "/contact/envoye"):
        liens = Selector(client.get(chemin).text).css("a::attr(href)").getall()
        assert "/lab/social/credits" not in liens, chemin
        assert all(lien == "/" or lien.startswith("/contact") for lien in liens), (chemin, liens)


def test_aucun_texte_ne_compte_encore_94_photos():
    """`objets-03` (une fresque créditée à son peintre, pas au photographe) est retirée : 93 photos."""
    from pathlib import Path

    from shadowlab.public import social

    racine = Path(__file__).parents[1]
    photos = social.charger_photos(social.DOSSIER_PHOTOS)
    assert len(photos) == 93 and "objets-03" not in {p.id for p in photos}
    assert not list(social.DOSSIER_PHOTOS.glob("objets-03*"))
    for fichier in [
        racine / "docs" / "site-public.md",
        *sorted((racine / "src" / "shadowlab" / "public").glob("*.py")),
    ]:
        assert not re.search(r"\b94 (?:photos|fichiers|images)", fichier.read_text(encoding="utf-8")), fichier
