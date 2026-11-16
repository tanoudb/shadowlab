"""Palier 2, I3 : bannissement dans l'Arena et profil « endurance ».

Spécification : `docs/recherche/identite-qui-dure-2026-11-12.md` § 4.5, § 4.6 et § 7 (I3), précisée par la coordination.
Le bannissement est une **option de profil** (`bannissement.actif`), fausse partout sauf dans `endurance` : les niveaux
01 à 07 ne changent pas d'une décision. Les compteurs de pages se lisent dans `observations_http` (jointe à `visites`) :
rien n'est écrit à chaque requête.

Pièges de test : derrière le frontal (sceau valide), l'application n'écrit pas `observations_http` (c'est le frontal
qui le fait) ; ces tests insèrent donc eux-mêmes les lignes, avec leurs heures. La requête en cours est comptée en
production (le frontal l'a déjà notée) : un test qui veut « la 241ᵉ page » insère 241 lignes puis fait la requête.
"""

from __future__ import annotations

import itertools
import json
import sqlite3
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
import yaml
from test_visiteurs import nouveau_passage, nouvelle_experience

from shadowlab import campaigns, cli, correlation
from shadowlab import database as db
from shadowlab.arena import bannissements, defis, profils, visiteurs
from shadowlab.arena import secret as secrets_arena
from shadowlab.detection import Observations
from shadowlab.site import gardien

MONDE = "campagne-i3"
AUTRE_MONDE = "campagne-autre"
HEURE = timedelta(hours=1)
JOUR = timedelta(hours=24)
MAINTENANT = datetime(2026, 11, 16, 12, 0, tzinfo=UTC)
FICHIER_CAMPAGNE = profils.RACINE / "configs" / "experiments" / "endurance-bannissement.yaml"
PAGE = "/lab/vitrine"


# --- Outils ------------------------------------------------------------------------------------------------


@pytest.fixture
def experience(reglages) -> int:
    return nouvelle_experience(reglages, "endurance")


@pytest.fixture
def nouvelle_session(reglages, experience):
    """Un jeton enregistré dans un passage du monde demandé (comme le ferait une campagne)."""
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
    """Aucun détecteur ne tranche : on isole le bannissement de la détection."""
    monkeypatch.setattr(gardien, "suspicion", lambda *a, **k: [])


def _entetes(reglages, profil: str, jeton: str) -> dict[str, str]:
    secret = secrets_arena.charger(reglages.dossier_arena)
    return {
        "x-shadowlab-sceau": secrets_arena.signer(secret, "obs", profil, jeton, "ja4-reel", ""),
        "x-shadowlab-obs": "obs",
        "x-shadowlab-profil": profil,
        "x-shadowlab-session": jeton,
        "x-shadowlab-ja4": "ja4-reel",
        "x-shadowlab-liaison": "",
    }


class Navigateur:
    """Un client qui garde ses cookies d'une session à l'autre (comme un vrai navigateur) ; `jeter()` les oublie."""

    def __init__(self, client, reglages, profil: str = "endurance") -> None:
        self.client, self.reglages, self.profil = client, reglages, profil
        self.cookies: dict[str, str] = {}

    def jeter(self) -> None:
        self.cookies = {}

    def _poser(self, reponse) -> None:
        for nom in (visiteurs.COOKIE, gardien.COOKIE_DEFI):
            valeur = reponse.cookies.get(nom)
            if valeur:
                self.cookies[nom] = valeur

    def _preparer(self) -> None:
        self.client.cookies.clear()
        for nom, valeur in self.cookies.items():
            self.client.cookies.set(nom, valeur)

    def aller(self, jeton: str, chemin: str = PAGE):
        self._preparer()
        reponse = self.client.get(f"{chemin}?sl={jeton}", headers=_entetes(self.reglages, self.profil, jeton))
        self._poser(reponse)
        return reponse

    def poster(self, jeton: str, chemin: str, **corps):
        self._preparer()
        reponse = self.client.post(f"{chemin}?sl={jeton}", headers=_entetes(self.reglages, self.profil, jeton), **corps)
        self._poser(reponse)
        return reponse

    def resoudre_le_defi(self, jeton: str, difficulte: int = 12):
        secret = secrets_arena.charger(self.reglages.dossier_arena)
        defi = defis.creer_defi(secret, jeton, difficulte)
        nonce = next(n for n in itertools.count() if defis.verifier_defi(secret, jeton, defi, n) is None)
        return self.poster(jeton, "/lab/defi/verifier", json={"defi": defi, "nonce": nonce})

    def franchir_la_porte(self, jeton: str) -> str:
        """Première page (défi), preuve de travail, retour sur la page : renvoie le visiteur."""
        premiere = self.aller(jeton)
        assert premiere.status_code == 403 and premiere.json()["bloque_par"] == "defi-js", premiere.text
        assert self.resoudre_le_defi(jeton, difficulte=18 if self.profil == "endurance" else 12).status_code == 204
        assert self.aller(jeton).status_code == 200
        return self.cookies[visiteurs.COOKIE].split(".")[0]


def _visiteur(valeur_cookie: str) -> str:
    return valeur_cookie.split(".")[0]


def _lignes(cx, requete: str, *parametres) -> list[sqlite3.Row]:
    return cx.execute(requete, parametres).fetchall()


def _bans(cx) -> list[sqlite3.Row]:
    return _lignes(
        cx, "SELECT m.nom AS monde, b.* FROM bannissements b JOIN mondes m ON m.id = b.monde_id ORDER BY b.id"
    )


def _stamp(instant: datetime) -> str:
    return instant.astimezone(UTC).isoformat(timespec="milliseconds")


def _visite(cx, monde: str, visiteur: str, jeton: str, debut: datetime, neuve: bool = True) -> None:
    cx.execute(
        "INSERT INTO visites (monde_id, visiteur, session_token, neuve, vue_le) VALUES (?, ?, ?, ?, ?)",
        (visiteurs.identifiant_monde(cx, monde), visiteur, jeton, int(neuve), _stamp(debut)),
    )


def _pages(cx, jeton: str, instants: list[datetime], chemin: str = "/lab/vitrine/annonces") -> None:
    cx.executemany(
        "INSERT INTO observations_http (session_token, received_at, method, path, headers, cookies)"
        " VALUES (?, ?, 'GET', ?, '[]', '[]')",
        [(jeton, _stamp(i), chemin) for i in instants],
    )


def _empreinte_js(modele: str) -> dict:
    """Une empreinte JS minimale : `modele` fait la différence entre deux E (profil et canvas)."""
    return {
        "navigateur": {
            "userAgent": f"UA-{modele}",
            "platform": "MacIntel",
            "hardwareConcurrency": 8,
            "languages": ["fr"],
        },
        "ecran": {"width": 1440, "height": 900, "devicePixelRatio": 2},
        "canvas": f"canvas-{modele}",
    }


def _envoyer_empreinte(nav: Navigateur, jeton: str, modele: str):
    corps = {"kind": "empreinte", "page": PAGE, "payload": _empreinte_js(modele)}
    return nav.poster(jeton, "/lab/collecte", content=json.dumps(corps))


# --- Le profil « endurance » -------------------------------------------------------------------------------


def test_endurance_est_le_06_avec_une_porte_par_visiteur_sans_captcha_et_avec_bannissement():
    tous = profils.charger()
    p, le_06 = tous.de("endurance"), tous.de("06")
    assert p is not None and le_06 is not None
    assert p.fingerprinting.detecteurs == le_06.fingerprinting.detecteurs
    assert "correlation-session" in p.fingerprinting.detecteurs
    assert p.fingerprinting.seuil_composite == le_06.fingerprinting.seuil_composite
    assert (p.limitation, p.waf, p.honeypots, p.connexion) == (
        le_06.limitation,
        le_06.waf,
        le_06.honeypots,
        le_06.connexion,
    )
    assert p.defi_js.actif and p.defi_js.par_visiteur and p.defi_js.difficulte == le_06.defi_js.difficulte
    assert p.duree_cookie_s == 24 * 3600
    assert not p.captcha.actif and not p.turnstile.actif and not p.recaptcha.actif
    assert p.bannissement.actif
    assert (p.bannissement.pages_par_heure, p.bannissement.pages_par_jour) == (240, 2000)


def test_les_niveaux_01_a_07_n_ont_ni_bannissement_ni_cookie_par_visiteur():
    for code, p in profils.charger():
        if code == "endurance":
            continue
        assert not p.bannissement.actif, code
        assert not p.defi_js.par_visiteur, code
        assert p.duree_cookie_s == 3600, code


def test_les_niveaux_existants_se_chargent_comme_avant():
    assert profils.charger().codes[:8] == ("01", "02", "03", "04", "05", "06", "07", "endurance")


# --- Migration 11 ------------------------------------------------------------------------------------------


def test_migration_11_ajoute_deux_index_et_laisse_la_10_telle_quelle(tmp_path):
    assert len(db.MIGRATIONS) == 11
    assert "CREATE TABLE bannissements" in db.MIGRATIONS[9]
    assert "INDEX" not in db.MIGRATIONS[9].split("CREATE TABLE bannissements")[1]
    cx = db.ouvrir(tmp_path / "neuve.sqlite3")
    assert cx.execute("PRAGMA user_version").fetchone()[0] == 11
    index = {r["name"] for r in cx.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert {"bannissements_visiteur", "bannissements_empreinte"} <= index


def test_migration_11_sur_base_au_schema_10(tmp_path):
    chemin = tmp_path / "dix.sqlite3"
    brut = sqlite3.connect(chemin, isolation_level=None)
    for script in db.MIGRATIONS[:10]:
        for instruction in (s.strip() for s in script.split(";")):
            if instruction:
                brut.execute(instruction)
    brut.execute("PRAGMA user_version=10")
    brut.execute("INSERT INTO mondes (nom, cree_le) VALUES ('m', '2026-11-16T00:00:00.000+00:00')")
    brut.close()
    cx = db.ouvrir(chemin)
    assert cx.execute("PRAGMA user_version").fetchone()[0] == 11
    assert cx.execute("SELECT nom FROM mondes").fetchone()["nom"] == "m"


# --- Les seuils, fonction pure -----------------------------------------------------------------------------

SEUILS = profils.Bannissement(actif=True)


@pytest.mark.parametrize(
    ("heure", "jour", "attendu"),
    [
        (0, 0, None),
        (240, 240, None),  # 240 pages en une heure : pas encore
        (241, 241, "pages_par_heure"),
        (240, 2000, None),  # 2 000 pages en 24 h : pas encore
        (240, 2001, "pages_par_jour"),  # la 2 001ᵉ page (la requête en cours comprise) bannit
        (241, 2001, "pages_par_heure"),  # l'heure d'abord : le motif le plus précis
    ],
)
def test_depassement(heure, jour, attendu):
    assert bannissements.depassement(heure, jour, SEUILS) == attendu


def test_les_seuils_viennent_du_profil():
    serres = profils.Bannissement(actif=True, pages_par_heure=10, pages_par_jour=50)
    assert bannissements.depassement(11, 11, serres) == "pages_par_heure"
    assert bannissements.depassement(10, 51, serres) == "pages_par_jour"


# --- Les compteurs de pages --------------------------------------------------------------------------------


def test_une_photo_ou_un_echange_technique_n_est_pas_une_page(cx):
    """Même définition que les détecteurs (D-78) : le compte SQL et `Observations.documents` s'accordent."""
    chemins = [
        "/lab/vitrine/annonces",
        "/lab/vitrine/annonces/AN-000003",
        "/lab/vitrine/photos/AN-000003.svg",
        "/lab/social/photos/a.jpg",
        "/lab/static/observateur.js",
        "/lab/static/../vitrine/annonces",  # une remontée de dossier n'est pas une ressource
        "/lab/collecte",
        "/lab/defi/verifier",
        "/lab/captcha/image",
        "/lab/verdict",
        "/lab/vitrine/api/AN-000003",  # l'appel de données reste une page (D-78)
        "/lab/rallye/saisons",
        "/lab/piege",
        "/lab/connexion",
    ]
    _visite(cx, MONDE, "v1", "s" * 32, MAINTENANT - timedelta(minutes=30))
    for chemin in chemins:
        _pages(cx, "s" * 32, [MAINTENANT - timedelta(minutes=5)], chemin)
    http = [{"path": c, "method": "GET", "cookies": [], "headers": [], "received_at": ""} for c in chemins]
    attendu = len(Observations(http=http, js=[]).documents)
    assert 0 < attendu < len(chemins)
    assert bannissements.compter_pages(cx, MONDE, "v1", MAINTENANT) == (attendu, attendu)


def test_les_fenetres_glissent_et_toutes_les_sessions_du_visiteur_comptent_ensemble(cx):
    for n in range(3):  # trois sessions du même visiteur (un cookie rejoué)
        _visite(cx, MONDE, "v1", f"{n:032x}", MAINTENANT - timedelta(hours=5), neuve=n == 0)
        _pages(cx, f"{n:032x}", [MAINTENANT - timedelta(minutes=10)] * 100)  # 100 pages dans l'heure, chacune
        _pages(cx, f"{n:032x}", [MAINTENANT - timedelta(hours=3)] * 10)  # 10 de plus, avant l'heure
        _pages(cx, f"{n:032x}", [MAINTENANT - timedelta(hours=30)] * 7)  # hors des 24 h : pas comptées
    assert bannissements.compter_pages(cx, MONDE, "v1", MAINTENANT) == (300, 330)


def test_les_compteurs_ne_voient_ni_un_autre_visiteur_ni_un_autre_monde(cx):
    _visite(cx, MONDE, "v1", "a" * 32, MAINTENANT - HEURE)
    _visite(cx, MONDE, "v2", "b" * 32, MAINTENANT - HEURE)
    _visite(cx, AUTRE_MONDE, "v1", "c" * 32, MAINTENANT - HEURE)
    for jeton in "abc":
        _pages(cx, jeton * 32, [MAINTENANT - timedelta(minutes=1)] * 5)
    assert bannissements.compter_pages(cx, MONDE, "v1", MAINTENANT) == (5, 5)
    assert bannissements.compter_pages(cx, "inconnu", "v1", MAINTENANT) == (0, 0)


def _surveillance_et_secret(reglages):
    return bannissements.Surveillance(), secrets_arena.charger(reglages.dossier_arena)


def _juger(surveillance, cx, secret, jeton, maintenant, *, page=True, cookie=None):
    return surveillance.juger(cx, secret, cookie, jeton, page=page, seuils=SEUILS, maintenant=maintenant)


def test_241_pages_en_une_heure_bannissent_et_240_non(reglages, cx):
    surveillance, secret = _surveillance_et_secret(reglages)
    _visite(cx, MONDE, "v1", "a" * 32, MAINTENANT - HEURE)
    cookie = visiteurs.creer_cookie(secret, MONDE, "v1")
    _pages(cx, "a" * 32, [MAINTENANT - timedelta(minutes=30)] * 240)
    assert _juger(surveillance, cx, secret, "a" * 32, MAINTENANT, cookie=cookie) is None
    assert not _bans(cx)
    _pages(cx, "a" * 32, [MAINTENANT - timedelta(minutes=1)])
    verdict = _juger(surveillance, cx, secret, "a" * 32, MAINTENANT, cookie=cookie)
    assert verdict is not None and verdict.visiteur == "v1" and "pages_par_heure" in verdict.motif
    (ban,) = _bans(cx)
    assert (ban["monde"], ban["visiteur"], ban["empreinte"]) == (MONDE, "v1", None)
    assert "pages_par_heure" in ban["motif"]


def test_2001_pages_en_24_heures_bannissent_et_2000_non(reglages, cx):
    surveillance, secret = _surveillance_et_secret(reglages)
    _visite(cx, MONDE, "v1", "a" * 32, MAINTENANT - JOUR + timedelta(minutes=1))
    cookie = visiteurs.creer_cookie(secret, MONDE, "v1")
    # 2 000 pages sur 23 heures : jamais plus de 240 dans une heure glissante.
    instants = [MAINTENANT - JOUR + timedelta(minutes=2) + timedelta(seconds=41 * i) for i in range(2000)]
    assert max(sum(1 for t in instants if x - HEURE < t <= x) for x in instants[::50]) <= 240
    _pages(cx, "a" * 32, instants)
    assert _juger(surveillance, cx, secret, "a" * 32, MAINTENANT, cookie=cookie) is None
    _pages(cx, "a" * 32, [MAINTENANT - timedelta(seconds=1)])
    verdict = _juger(surveillance, cx, secret, "a" * 32, MAINTENANT, cookie=cookie)
    assert verdict is not None and "pages_par_jour" in verdict.motif


def test_40_pages_par_jour_pendant_7_jours_ne_bannissent_pas(reglages, cx):
    surveillance, secret = _surveillance_et_secret(reglages)
    cookie = visiteurs.creer_cookie(secret, MONDE, "v1")
    for jour in range(7):
        debut = MAINTENANT - timedelta(days=6 - jour)
        jeton = f"{jour:032x}"
        _visite(cx, MONDE, "v1", jeton, debut, neuve=jour == 0)
        _pages(cx, jeton, [debut + timedelta(minutes=3 * i) for i in range(40)])
        fin_de_journee = debut + timedelta(minutes=3 * 40)
        assert _juger(surveillance, cx, secret, jeton, fin_de_journee, cookie=cookie) is None, jour
    assert not _bans(cx)


def test_un_cookie_rejoue_dans_beaucoup_de_sessions_est_compte_une_fois_en_tout(reglages, cx):
    """La limite relevée par la relecture du 15/11 : 30 sessions parallèles de 9 pages : 270 pages, un visiteur."""
    surveillance, secret = _surveillance_et_secret(reglages)
    cookie = visiteurs.creer_cookie(secret, MONDE, "v1")
    for n in range(30):
        jeton = f"{n:032x}"
        _visite(cx, MONDE, "v1", jeton, MAINTENANT - timedelta(minutes=20), neuve=n == 0)
        _pages(cx, jeton, [MAINTENANT - timedelta(minutes=1)] * 9)
    verdict = _juger(surveillance, cx, secret, f"{29:032x}", MAINTENANT, cookie=cookie)
    assert verdict is not None and "pages_par_heure" in verdict.motif


def test_une_requete_qui_n_est_pas_une_page_ne_declenche_pas_les_compteurs(reglages, cx):
    surveillance, secret = _surveillance_et_secret(reglages)
    _visite(cx, MONDE, "v1", "a" * 32, MAINTENANT - HEURE)
    _pages(cx, "a" * 32, [MAINTENANT - timedelta(minutes=1)] * 300)
    cookie = visiteurs.creer_cookie(secret, MONDE, "v1")
    assert _juger(surveillance, cx, secret, "a" * 32, MAINTENANT, page=False, cookie=cookie) is None
    assert not _bans(cx)


# --- Le coût d'une requête ---------------------------------------------------------------------------------


class _Traces:
    def __init__(self, cx: sqlite3.Connection) -> None:
        self.instructions: list[str] = []
        cx.set_trace_callback(self.instructions.append)

    def lectures(self) -> int:
        return sum(1 for i in self.instructions if i.lstrip().upper().startswith(("SELECT", "WITH")))

    def ecritures(self) -> int:
        return sum(1 for i in self.instructions if i.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")))


def test_une_session_connue_coute_une_lecture_et_aucune_ecriture(reglages, cx):
    surveillance, secret = _surveillance_et_secret(reglages)
    _visite(cx, MONDE, "v1", "a" * 32, MAINTENANT - HEURE, neuve=False)  # un visiteur connu : pas d'E à chercher
    cookie = visiteurs.creer_cookie(secret, MONDE, "v1")
    _juger(surveillance, cx, secret, "a" * 32, MAINTENANT, cookie=cookie)  # la première lit la fiche de la session
    for page in (True, False):
        traces = _Traces(cx)
        assert _juger(surveillance, cx, secret, "a" * 32, MAINTENANT, page=page, cookie=cookie) is None
        assert (traces.lectures(), traces.ecritures()) == (1, 0), traces.instructions


def test_une_session_neuve_sans_empreinte_coute_deux_lectures_puis_une(reglages, cx):
    surveillance, secret = _surveillance_et_secret(reglages)
    _visite(cx, MONDE, "v1", "a" * 32, MAINTENANT - HEURE, neuve=True)
    cookie = visiteurs.creer_cookie(secret, MONDE, "v1")
    _juger(surveillance, cx, secret, "a" * 32, MAINTENANT, cookie=cookie)
    traces = _Traces(cx)
    _juger(surveillance, cx, secret, "a" * 32, MAINTENANT, cookie=cookie)
    assert (traces.lectures(), traces.ecritures()) == (2, 0)  # l'empreinte n'est pas encore arrivée : on la cherche
    cx.execute(
        "INSERT INTO observations_js (session_token, received_at, kind, page, payload)"
        " VALUES (?, ?, 'empreinte', '/', ?)",
        ("a" * 32, _stamp(MAINTENANT), json.dumps(_empreinte_js("m"))),
    )
    _juger(surveillance, cx, secret, "a" * 32, MAINTENANT, cookie=cookie)  # elle arrive : retenue en mémoire
    traces = _Traces(cx)
    _juger(surveillance, cx, secret, "a" * 32, MAINTENANT, cookie=cookie)
    assert (traces.lectures(), traces.ecritures()) == (1, 0)


# --- Bannissement par visiteur, dans l'application ---------------------------------------------------------


def test_un_visiteur_detecte_qui_revient_avec_un_nouveau_jeton_recoit_un_403(client, reglages, cx, nouvelle_session):
    nav = Navigateur(client, reglages)
    premiere = nouvelle_session()
    visiteur = nav.franchir_la_porte(premiere)
    # Un piège déclenché : le gardien arrête la session pour suspicion.
    db.enregistrer_decision(cx, premiere, "honeypot", "declenche", "/lab/piege", [])
    arret = nav.aller(premiere)
    assert arret.status_code == 403 and arret.json()["bloque_par"] == "fingerprinting"
    (ban,) = _bans(cx)
    assert (ban["monde"], ban["visiteur"]) == (MONDE, visiteur)
    assert ban["motif"].startswith("detecte")
    # Il revient : nouveau jeton, mêmes cookies.
    seconde = nouvelle_session()
    retour = nav.aller(seconde)
    assert retour.status_code == 403 and retour.json()["bloque_par"] == "bannissement"
    assert any(d["couche"] == "bannissement" and d["decision"] == "bloque" for d in db.decisions_session(cx, seconde))
    assert len(_bans(cx)) == 1  # pas de doublon


def test_un_visiteur_banni_n_obtient_pas_le_cookie_de_porte(client, reglages, cx, nouvelle_session):
    nav = Navigateur(client, reglages)
    visiteur = nav.franchir_la_porte(nouvelle_session())
    bannissements.bannir(cx, MONDE, visiteur=visiteur, motif="manuel")
    jeton = nouvelle_session()
    nav.cookies.pop(gardien.COOKIE_DEFI)
    refus = nav.resoudre_le_defi(jeton, difficulte=18)
    assert refus.status_code == 403
    assert gardien.COOKIE_DEFI not in nav.cookies


def test_le_bannissement_est_propre_au_monde(client, reglages, cx, nouvelle_session):
    nav = Navigateur(client, reglages)
    visiteur = nav.franchir_la_porte(nouvelle_session())
    bannissements.bannir(cx, AUTRE_MONDE, visiteur=visiteur, motif="manuel")
    assert nav.aller(nouvelle_session()).status_code == 200


def test_un_visiteur_qui_jette_ses_cookies_est_un_autre_visiteur(client, reglages, cx, nouvelle_session):
    nav = Navigateur(client, reglages)
    visiteur = nav.franchir_la_porte(nouvelle_session())
    bannissements.bannir(cx, MONDE, visiteur=visiteur, motif="manuel")
    nav.jeter()
    reponse = nav.aller(nouvelle_session())  # sans bannissement par empreinte, rien ne le relie à l'ancien
    assert reponse.status_code == 403 and reponse.json()["bloque_par"] == "defi-js"


def test_un_bannissement_expire(client, reglages, cx, nouvelle_session):
    nav = Navigateur(client, reglages)
    visiteur = nav.franchir_la_porte(nouvelle_session())
    passe = datetime.now(UTC) - timedelta(minutes=1)
    bannissements.bannir(cx, MONDE, visiteur=visiteur, motif="manuel", expire_le=passe)
    assert nav.aller(nouvelle_session()).status_code == 200


def test_les_compteurs_bannissent_dans_l_application(client, reglages, cx, nouvelle_session, sans_suspicion):
    nav = Navigateur(client, reglages)
    jeton = nouvelle_session()
    visiteur = nav.franchir_la_porte(jeton)
    maintenant = datetime.now(UTC)
    _pages(cx, jeton, [maintenant - timedelta(minutes=10)] * 240)
    assert nav.aller(jeton).status_code == 200
    _pages(cx, jeton, [maintenant - timedelta(minutes=1)])  # la 241ᵉ, celle que le frontal vient de noter
    refus = nav.aller(jeton)
    assert refus.status_code == 403 and refus.json()["bloque_par"] == "bannissement"
    (ban,) = _bans(cx)
    assert (ban["visiteur"], ban["empreinte"]) == (visiteur, None) and "pages_par_heure" in ban["motif"]
    assert nav.aller(nouvelle_session()).status_code == 403  # un nouveau jeton n'y change rien


# --- Bannissement par empreinte E : les sessions neuves seulement ------------------------------------------


def test_une_empreinte_bannie_bannit_une_session_neuve_pas_un_visiteur_connu_ni_un_autre_monde(
    client, reglages, cx, nouvelle_session, sans_suspicion
):
    e = correlation.empreinte_e(_empreinte_js("m1"))
    bannissements.bannir(cx, MONDE, visiteur="un-autre", empreinte=e, motif="detecte")
    # 1. Un visiteur connu (il a déjà une visite dans le monde) qui porte la même E n'est pas touché.
    connu = Navigateur(client, reglages)
    connu.franchir_la_porte(nouvelle_session())  # sa 1ʳᵉ visite, avant que son empreinte n'arrive
    retour = nouvelle_session()  # sa 2ᵉ visite : le visiteur n'est plus neuf
    assert connu.aller(retour).status_code == 200
    assert _envoyer_empreinte(connu, retour, "m1").status_code == 204
    assert connu.aller(retour).status_code == 200
    assert len(_bans(cx)) == 1
    # 2. Une session neuve de même E est bannie, même sans aucun cookie de visiteur connu.
    neuf = Navigateur(client, reglages)
    session_neuve = nouvelle_session()
    neuf.franchir_la_porte(session_neuve)
    assert neuf.aller(session_neuve).status_code == 200  # E pas encore connue : rien à lui reprocher
    assert _envoyer_empreinte(neuf, session_neuve, "m1").status_code == 204
    assert any(
        d["couche"] == "bannissement" and d["decision"] == "bloque" for d in db.decisions_session(cx, session_neuve)
    )
    refus = neuf.aller(session_neuve)
    assert refus.status_code == 403 and refus.json()["bloque_par"] == "bannissement"
    # 3. Dans un autre monde, la même E ne dit rien.
    ailleurs = Navigateur(client, reglages)
    session_ailleurs = nouvelle_session(AUTRE_MONDE)
    ailleurs.franchir_la_porte(session_ailleurs)
    assert _envoyer_empreinte(ailleurs, session_ailleurs, "m1").status_code == 204
    assert ailleurs.aller(session_ailleurs).status_code == 200
    # 4. Une autre E, même monde, session neuve : rien.
    autre = Navigateur(client, reglages)
    session_autre = nouvelle_session()
    autre.franchir_la_porte(session_autre)
    assert _envoyer_empreinte(autre, session_autre, "m2").status_code == 204
    assert autre.aller(session_autre).status_code == 200


def test_la_detection_a_la_collecte_bannit_le_visiteur_et_son_empreinte(
    client, reglages, cx, nouvelle_session, monkeypatch
):
    """L'arrêt peut ne venir qu'à la page suivante (un scénario d'une seule page ne la demande jamais) : le gardien
    banni dès que la collecte de l'empreinte révèle l'automate, pour que le passage suivant trouve la ligne."""
    nav = Navigateur(client, reglages)
    jeton = nouvelle_session()
    visiteur = nav.franchir_la_porte(jeton)
    monkeypatch.setattr(gardien, "suspicion", lambda *a, **k: [{"detecteur": "headless", "signaux": []}])
    assert _envoyer_empreinte(nav, jeton, "bot").status_code == 204
    (ban,) = _bans(cx)
    assert (ban["monde"], ban["visiteur"]) == (MONDE, visiteur)
    assert ban["empreinte"] == correlation.empreinte_e(_empreinte_js("bot"))
    assert _envoyer_empreinte(nav, jeton, "bot").status_code == 204  # chaque page renvoie son empreinte
    assert len(_bans(cx)) == 1


# --- Pas de bannissement automatique là où le monde ne se remet jamais à zéro ------------------------------


@pytest.mark.parametrize("monde", [visiteurs.MONDE_MANUEL, visiteurs.MONDE_HORS_PASSAGE])
def test_aucun_bannissement_automatique_dans_les_mondes_partages(
    client, reglages, cx, nouvelle_session, monkeypatch, monde
):
    """`manuel` (les humains de /manuel) et `hors-passage` ne sont jamais remis à zéro : une empreinte bannie y serait
    bannie pour tout humain du même modèle de machine. Rien n'y est écrit, ni détection ni compteur."""
    nav = Navigateur(client, reglages)
    jeton = nouvelle_session(monde) if monde == visiteurs.MONDE_MANUEL else "d" * 32  # sans passage : hors-passage
    nav.franchir_la_porte(jeton)
    assert (
        cx.execute(
            "SELECT m.nom FROM visites v JOIN mondes m ON m.id = v.monde_id WHERE v.session_token = ?", (jeton,)
        ).fetchone()[0]
        == monde
    )
    monkeypatch.setattr(gardien, "suspicion", lambda *a, **k: [{"detecteur": "headless", "signaux": []}])
    assert _envoyer_empreinte(nav, jeton, "bot").status_code == 204
    _pages(cx, jeton, [datetime.now(UTC) - timedelta(minutes=1)] * 500)
    assert nav.aller(jeton).status_code == 403  # l'arrêt de la session, lui, reste celui de toujours
    assert not _bans(cx)


@pytest.mark.parametrize("monde", [visiteurs.MONDE_MANUEL, visiteurs.MONDE_HORS_PASSAGE])
def test_un_bannissement_manuel_vaut_dans_tous_les_mondes(client, reglages, cx, nouvelle_session, monde):
    nav = Navigateur(client, reglages)
    jeton = nouvelle_session(monde) if monde == visiteurs.MONDE_MANUEL else "d" * 32
    visiteur = nav.franchir_la_porte(jeton)
    bannissements.bannir(cx, monde, visiteur=visiteur, motif="manuel")
    refus = nav.aller(jeton)
    assert refus.status_code == 403 and refus.json()["bloque_par"] == "bannissement"


# --- La porte d'entrée, par visiteur -----------------------------------------------------------------------


def _figer(monkeypatch, instant: float) -> None:
    monkeypatch.setattr(defis, "time", SimpleNamespace(time=lambda: instant))


def test_la_deuxieme_session_du_visiteur_dans_les_24_h_n_a_pas_de_defi_apres_24_h_si(
    client, reglages, nouvelle_session, monkeypatch, sans_suspicion
):
    _figer(monkeypatch, 1_000_000)
    nav = Navigateur(client, reglages)
    nav.franchir_la_porte(nouvelle_session())
    _figer(monkeypatch, 1_000_000 + 24 * 3600 - 1)
    assert nav.aller(nouvelle_session()).status_code == 200  # 2ᵉ session : pas de défi
    _figer(monkeypatch, 1_000_000 + 24 * 3600 + 1)
    apres = nav.aller(nouvelle_session())
    assert apres.status_code == 403 and apres.json()["bloque_par"] == "defi-js"


def test_le_cookie_de_porte_est_lie_au_visiteur(client, reglages, nouvelle_session, sans_suspicion):
    nav = Navigateur(client, reglages)
    nav.franchir_la_porte(nouvelle_session())
    voleur = Navigateur(client, reglages)
    voleur.cookies[gardien.COOKIE_DEFI] = nav.cookies[gardien.COOKIE_DEFI]  # le cookie de porte seul, sans le visiteur
    refus = voleur.aller(nouvelle_session())
    assert refus.status_code == 403 and refus.json()["bloque_par"] == "defi-js"


def test_le_cookie_de_porte_est_pose_avec_une_duree_dans_endurance_seulement(client, reglages, nouvelle_session):
    for profil, attendu in (("endurance", "max-age=86400"), ("04", None)):
        nav = Navigateur(client, reglages, profil)
        jeton = nouvelle_session()
        assert nav.aller(jeton).status_code == 403
        reponse = nav.resoudre_le_defi(jeton, difficulte=18 if profil == "endurance" else 12)
        entetes = [e.lower() for e in reponse.headers.get_list("set-cookie") if e.startswith(gardien.COOKIE_DEFI)]
        assert len(entetes) == 1
        if attendu:
            assert attendu in entetes[0]
        else:
            assert "max-age" not in entetes[0] and "expires" not in entetes[0]


def test_aux_niveaux_existants_le_cookie_reste_lie_au_jeton(client, reglages, nouvelle_session, sans_suspicion):
    nav = Navigateur(client, reglages, "04")
    premiere = nouvelle_session()
    assert nav.aller(premiere).status_code == 403
    assert nav.resoudre_le_defi(premiere, difficulte=12).status_code == 204
    assert nav.aller(premiere).status_code == 200
    seconde = nouvelle_session()  # même navigateur, autre jeton : le défi revient (comportement des niveaux 02 à 07)
    refus = nav.aller(seconde)
    assert refus.status_code == 403 and refus.json()["bloque_par"] == "defi-js"


# --- Sans l'option, rien ne change -------------------------------------------------------------------------


def test_sans_l_option_aucune_lecture_ni_ecriture_de_bannissement_ne_change_la_decision(
    client, reglages, cx, nouvelle_session, monkeypatch
):
    nav = Navigateur(client, reglages, "04")
    premiere = nouvelle_session()
    visiteur = nav.franchir_la_porte(premiere)
    empreinte = correlation.empreinte_e(_empreinte_js("m1"))

    def interdit(*a, **k):
        raise AssertionError("le bannissement est lu alors que le profil ne l'active pas")

    monkeypatch.setattr(bannissements.Surveillance, "juger", interdit)
    monkeypatch.setattr(bannissements, "bannir", interdit)
    monkeypatch.setattr(bannissements, "compter_pages", interdit)
    # Des lignes de bannissement existent, pour ce visiteur et pour cette empreinte : elles ne comptent pas.
    cx.execute(
        "INSERT INTO bannissements (monde_id, visiteur, empreinte, motif, cree_le) VALUES (?, ?, ?, 'test', ?)",
        (visiteurs.identifiant_monde(cx, MONDE), visiteur, empreinte, db.maintenant()),
    )
    # Bien plus que 240 pages en une heure, sur une autre session du même visiteur (les détecteurs ne la voient pas).
    _visite(cx, MONDE, visiteur, "e" * 32, datetime.now(UTC) - HEURE / 2, neuve=False)
    _pages(cx, "e" * 32, [datetime.now(UTC) - timedelta(minutes=1)] * 500)
    with monkeypatch.context() as sans_detecteurs:  # l'empreinte d'essai n'est pas celle d'un vrai navigateur
        sans_detecteurs.setattr(gardien, "suspicion", lambda *a, **k: [])
        assert nav.aller(premiere).status_code == 200
        assert _envoyer_empreinte(nav, premiere, "m1").status_code == 204
        assert nav.aller(premiere).status_code == 200
    # Une détection au 04 arrête la session comme avant, et n'écrit aucun bannissement.
    db.enregistrer_decision(cx, premiere, "honeypot", "declenche", "/lab/piege", [])
    arret = nav.aller(premiere)
    assert arret.status_code == 403 and arret.json()["bloque_par"] == "fingerprinting"
    assert len(_bans(cx)) == 1  # la ligne posée par le test, rien d'autre


@pytest.mark.parametrize("niveau", ["01", "02", "03", "04", "05", "06", "07"])
def test_aucun_niveau_de_01_a_07_ne_lit_le_bannissement(niveau):
    p = profils.charger().de(niveau)
    assert p is not None and not p.bannissement.actif and not p.defi_js.par_visiteur


# --- La commande `shadowlab arena bannir` ------------------------------------------------------------------


def test_arena_bannir_ecrit_la_ligne_et_le_visiteur_recoit_ensuite_un_403(
    client, reglages, cx, nouvelle_session, sans_suspicion, capsys
):
    nav = Navigateur(client, reglages)
    visiteur = nav.franchir_la_porte(nouvelle_session())
    assert cli.main(["arena", "bannir", "--visiteur", visiteur, "--monde", MONDE]) == 0
    (ban,) = _bans(cx)
    assert (ban["monde"], ban["visiteur"], ban["empreinte"], ban["motif"], ban["expire_le"]) == (
        MONDE, visiteur, None, "manuel", None,
    )  # fmt: skip
    refus = nav.aller(nouvelle_session())
    assert refus.status_code == 403 and refus.json()["bloque_par"] == "bannissement"
    assert visiteur in capsys.readouterr().out


def test_arena_bannir_exige_le_monde(reglages):
    with pytest.raises(SystemExit) as sortie:
        cli.main(["arena", "bannir", "--visiteur", "abc"])
    assert sortie.value.code == 2


def test_arena_bannir_exige_le_visiteur(reglages):
    with pytest.raises(SystemExit) as sortie:
        cli.main(["arena", "bannir", "--monde", MONDE])
    assert sortie.value.code == 2


def test_arena_bannir_refuse_un_monde_ou_un_visiteur_inconnu(client, reglages, cx, nouvelle_session, capsys):
    nav = Navigateur(client, reglages)
    visiteur = nav.franchir_la_porte(nouvelle_session())
    assert cli.main(["arena", "bannir", "--visiteur", visiteur, "--monde", "monde-inexistant"]) == 2
    assert cli.main(["arena", "bannir", "--visiteur", "inconnu", "--monde", MONDE]) == 2
    assert not _bans(cx)
    assert "monde-inexistant" not in {r["nom"] for r in cx.execute("SELECT nom FROM mondes")}
    assert "inconnu" in capsys.readouterr().err


def test_arena_bannir_ne_demarre_pas_la_pile(client, reglages, nouvelle_session, monkeypatch):
    from shadowlab.arena import pile

    monkeypatch.setattr(pile, "demarrer", lambda *a, **k: pytest.fail("la pile ne doit pas être touchée"))
    nav = Navigateur(client, reglages)
    visiteur = nav.franchir_la_porte(nouvelle_session())
    assert cli.main(["arena", "bannir", "--visiteur", visiteur, "--monde", MONDE]) == 0


# --- La campagne courte (non lancée) -----------------------------------------------------------------------


def test_la_campagne_endurance_bannissement_se_valide(reglages):
    experience = campaigns.lire(FICHIER_CAMPAGNE, reglages)
    assert experience.protections == ["endurance"]
    assert experience.monde == "campagne"
    assert experience.repetitions == 3
    moteurs = {m.nom_affiche: m for m in experience.engines}
    assert {m.name for m in experience.engines} == {"playwright", "noezia"}
    noezia = next(m for m in experience.engines if m.name == "noezia")
    assert noezia.options == {"headless": False, "channel": "chrome", "identite_native": True}
    assert len(moteurs) == 2
    brut = yaml.safe_load(FICHIER_CAMPAGNE.read_text(encoding="utf-8"))
    assert brut["experiment"]["monde"] == "campagne"
