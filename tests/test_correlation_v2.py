"""`correlation-session` 2.0 (palier 2, I2) : on compte des visiteurs neufs, pas des jetons.

Spécification : `docs/recherche/identite-qui-dure-2026-11-12.md` § 4.3 à 4.5. La règle est une fonction pure
(`correlation.evaluer`) ; ces tests la prennent seule, puis de bout en bout par `gardien.suspicion` (la décision de
l'Arena) et par le rejeu des sessions humaines.
"""

from __future__ import annotations

import sqlite3
from dataclasses import asdict
from datetime import UTC, datetime, timedelta

import pytest
from test_rejeu import empreinte, message, niveau, session_labo, t, visite

from shadowlab import correlation, rejeu
from shadowlab import database as db
from shadowlab.arena import visiteurs
from shadowlab.detection import DetecteurCorrelationSession, Observations, registre
from shadowlab.site import gardien

MAINTENANT = datetime(2026, 11, 15, 20, 0, tzinfo=UTC)
SECRET = b"secret-d-essai"
E = "e" * 16


def v(n: int, il_y_a: timedelta, *, neuve: bool = True, empreinte: str | None = E, visiteur: str | None = None):
    return correlation.VisiteObservee(f"s{n}", visiteur or f"v{n}", neuve, MAINTENANT - il_y_a, empreinte)


def juger(visites: list, session: str, maintenant: datetime = MAINTENANT) -> dict[str, float]:
    """Signaux (code → poids) du détecteur pour la session `session` d'un monde dont voici les visites."""
    donnees = asdict(correlation.evaluer(visites, session, maintenant))
    c = DetecteurCorrelationSession().classer(Observations(http=[], js=[], correlation=donnees))
    return {s.code: s.poids for s in c.signals if s.poids > 0}


# --- La règle, fonction pure ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("n", "attendu"),
    [(4, {}), (5, {"empreinte_sans_memoire": 0.7}), (9, {"empreinte_sans_memoire": 0.7})]
    + [(10, {"empreinte_sans_memoire": 1.0}), (11, {"empreinte_sans_memoire": 1.0})],
)
def test_sessions_neuves_de_meme_empreinte_en_une_heure(n, attendu):
    visites = [v(i, timedelta(minutes=50 - 4 * i)) for i in range(n)]  # la dernière est la session jugée
    assert juger(visites, f"s{n - 1}") == attendu


def test_le_retour_d_un_visiteur_connu_n_est_jamais_compte_contre_lui():
    anciennes = [v(i, timedelta(days=1, hours=i)) for i in range(12)]  # 12 neufs, il y a plus de 24 h
    retour = v(99, timedelta(minutes=1), neuve=False, visiteur="v0")
    assert juger([*anciennes, retour], "s99") == {}


def test_les_retours_ne_comptent_pas_dans_les_neuves():
    # Dix retours d'un même visiteur en une soirée + une première visite : un seul neuf, aucun signal.
    retours = [v(i, timedelta(minutes=60 - 5 * i), neuve=False, visiteur="v0") for i in range(10)]
    neuve = v(50, timedelta(minutes=1))
    assert juger([*retours, neuve], "s50") == {}


def test_trente_sessions_en_59_minutes_font_un_debit():
    debut = timedelta(minutes=59)
    neuves = [v(i, debut - timedelta(seconds=114 * i)) for i in range(30)]
    assert juger(neuves, "s29") == {"empreinte_sans_memoire": 1.0, "debit_empreinte": 0.8}
    # Des retours seulement : le débit juge toute session ; « sans mémoire » ne juge que les neuves.
    retours = [v(i, debut - timedelta(seconds=114 * i), neuve=False, visiteur="vx") for i in range(30)]
    assert juger(retours, "s29") == {"debit_empreinte": 0.8}


def test_vingt_neuf_sessions_en_une_heure_pas_de_debit():
    visites = [v(i, timedelta(minutes=50) - timedelta(seconds=100 * i), neuve=False, visiteur="vx") for i in range(29)]
    assert juger(visites, "s28") == {}


def test_dix_sessions_en_cinquante_secondes_sont_comptees():
    visites = [v(i, timedelta(seconds=50 - 5 * i)) for i in range(10)]
    r = correlation.evaluer(visites, "s9", MAINTENANT)
    assert (r.debit_60min, r.sessions_neuves_24h) == (10, 10)


def test_443_sessions_il_y_a_deux_jours_puis_une_seule_ne_donnent_aucun_debit():
    anciennes = [v(i, timedelta(days=2, seconds=i)) for i in range(443)]
    seule = v(999, timedelta(seconds=1))
    r = correlation.evaluer([*anciennes, seule], "s999", MAINTENANT)
    assert (r.debit_60min, r.sessions_neuves_24h) == (1, 1)
    assert juger([*anciennes, seule], "s999") == {}


def test_une_autre_empreinte_n_est_pas_comptee():
    autres = [v(i, timedelta(minutes=5), empreinte="a" * 16) for i in range(40)]
    assert juger([*autres, v(100, timedelta(seconds=1))], "s100") == {}


def test_une_visite_sans_empreinte_n_est_pas_comptee():
    sans = [v(i, timedelta(minutes=5), empreinte=None) for i in range(40)]
    assert juger([*sans, v(100, timedelta(seconds=1))], "s100") == {}


def test_une_visite_postérieure_n_est_pas_vue():
    # Rejeu : à l'instant d'une session, seules les visites déjà commencées existent.
    apres = [v(i, -timedelta(minutes=1 + i)) for i in range(20)]
    assert juger([v(100, timedelta(0)), *apres], "s100") == {}


def test_une_session_inconnue_ne_donne_rien():
    assert juger([v(1, timedelta(minutes=1))], "autre") == {}


def test_les_trois_cas_du_tableau_de_la_conception():
    # § 4.4 : humain qui revient (jamais pris), cookies jetés (pris à la 5e neuve), identité à 30 visites/h (débit).
    humain = [v(i, timedelta(days=9 - i), neuve=i == 0, visiteur="h") for i in range(10)]
    assert juger(humain, "s9") == {}
    jetes = [v(i, timedelta(minutes=10 - i)) for i in range(5)]
    assert juger(jetes, "s4") == {"empreinte_sans_memoire": 0.7}
    identite = [v(i, timedelta(minutes=59, seconds=-100 * i), neuve=False, visiteur="id") for i in range(30)]
    assert juger(identite, "s29") == {"debit_empreinte": 0.8}


# --- L'empreinte E ----------------------------------------------------------------------------------------


def test_empreinte_e_stable_et_sensible_au_canvas_et_au_profil():
    a = correlation.empreinte_e(empreinte(0))
    assert a and a == correlation.empreinte_e(empreinte(0))
    assert a != correlation.empreinte_e(empreinte(1))  # `empreinte(n)` change écran et canvas


def test_empreinte_e_sans_canvas_exploitable_reste_calculee():
    e = empreinte(0)
    e["canvas"] = "erreur: indisponible"
    sans = correlation.empreinte_e(e)
    assert sans and sans != correlation.empreinte_e(empreinte(0))


# --- Lecture dans la base : un jeton, une empreinte -------------------------------------------------------


def _base() -> sqlite3.Connection:
    cx_ = sqlite3.connect(":memory:", isolation_level=None)
    cx_.row_factory = sqlite3.Row
    db.migrer(cx_)
    return cx_


def _arrivee(cx_, monkeypatch, jeton: str, instant: datetime, cookie: str | None = None, emp: dict | None = None):
    """Une arrivée comme l'Arena la voit : requête reconnue (visite), empreinte reçue, hachée. Renvoie le cookie."""
    monkeypatch.setattr(db, "maintenant", lambda: instant.isoformat(timespec="milliseconds"))
    visite_ = visiteurs.reconnaitre(cx_, SECRET, cookie, jeton)
    if emp is not None:
        cx_.execute(
            "INSERT INTO observations_js (session_token, received_at, kind, page, payload)"
            " VALUES (?, ?, 'empreinte', '/lab/', ?)",
            (jeton, db.maintenant(), db.j(emp)),
        )
        correlation.enregistrer_hash(cx_, jeton, emp)
    return visite_.cookie or cookie


def _suspicion(cx_, jeton: str, detecteurs: list[str]) -> list[dict]:
    """La décision du niveau 06 pour ce détecteur : même appel que `/lab/collecte`, composite à 0,5."""
    return gardien.suspicion(cx_, jeton, inclure_js=True, detecteurs=detecteurs, seuil_composite=0.5)


def test_un_jeton_qui_envoie_vingt_empreintes_compte_une_fois(monkeypatch):
    cx_ = _base()
    for n in range(20):
        _arrivee(cx_, monkeypatch, "a", MAINTENANT - timedelta(minutes=10), emp=empreinte(n))
    _arrivee(cx_, monkeypatch, "b", MAINTENANT - timedelta(minutes=5), emp=empreinte(0))
    _arrivee(cx_, monkeypatch, "c", MAINTENANT - timedelta(minutes=4), emp=empreinte(7))
    assert asdict(correlation.evaluer_session(cx_, "b", MAINTENANT)) == {
        "empreinte": correlation.empreinte_e(empreinte(0)),
        "session_neuve": True,
        "sessions_neuves_24h": 2,  # a (première empreinte) et b ; pas les 19 autres empreintes de a
        "debit_60min": 2,
    }
    assert correlation.evaluer_session(cx_, "c", MAINTENANT).sessions_neuves_24h == 1


def test_evaluer_session_ne_voit_que_le_monde_de_la_session(monkeypatch):
    cx_ = _base()
    for n in range(6):  # six sessions neuves sans passage : monde « hors-passage »
        _arrivee(cx_, monkeypatch, f"x{n}", MAINTENANT - timedelta(minutes=30 - n), emp=empreinte(0))
    ailleurs = visiteurs.identifiant_monde(cx_, "ailleurs")
    for n in range(6):  # six autres, de même empreinte, dans un autre monde
        jeton, instant = f"y{n}", MAINTENANT - timedelta(minutes=20 - n)
        cx_.execute(
            "INSERT INTO visites (monde_id, visiteur, session_token, neuve, vue_le) VALUES (?, ?, ?, 1, ?)",
            (ailleurs, f"vy{n}", jeton, instant.isoformat(timespec="milliseconds")),
        )
        cx_.execute(
            "INSERT INTO observations_js (session_token, received_at, kind, page, payload)"
            " VALUES (?, ?, 'empreinte', '/lab/', ?)",
            (jeton, instant.isoformat(timespec="milliseconds"), db.j(empreinte(0))),
        )
    assert correlation.evaluer_session(cx_, "x5", MAINTENANT).sessions_neuves_24h == 6  # pas 12
    assert correlation.evaluer_session(cx_, "y5", MAINTENANT).sessions_neuves_24h == 6


# --- De bout en bout, comme à la collecte --------------------------------------------------------------


def test_humain_qui_revient_dix_fois_n_est_jamais_pris(monkeypatch):
    """Une visite par jour pendant cinq jours, puis cinq dans une soirée, avec le même navigateur (même cookie).

    Règle 1.1 : pris à la 5e session (0,7 × 1,5 au-dessus du seuil composite 0,5). Règle 2.0 : jamais.
    """
    cx_, cookie, pris = _base(), None, []
    instants = [MAINTENANT - timedelta(days=5 - n) for n in range(5)]
    instants += [MAINTENANT + timedelta(minutes=20 * n) for n in range(5)]
    for n, instant in enumerate(instants):
        cookie = _arrivee(cx_, monkeypatch, f"h{n}", instant, cookie, empreinte(0))
        if _suspicion(cx_, f"h{n}", ["correlation-session"]):
            pris.append(n + 1)
    assert pris == []


def test_cookies_jetes_la_cinquieme_session_neuve_est_prise(monkeypatch):
    cx_, pris = _base(), []
    for n in range(10):
        _arrivee(cx_, monkeypatch, f"r{n}", MAINTENANT - timedelta(minutes=50 - 3 * n), None, empreinte(0))
        if _suspicion(cx_, f"r{n}", ["correlation-session"]):
            pris.append(n + 1)
    assert pris == [5, 6, 7, 8, 9, 10]


def test_les_motifs_portent_les_codes_de_la_regle_2(monkeypatch):
    cx_ = _base()
    for n in range(10):
        _arrivee(cx_, monkeypatch, f"r{n}", MAINTENANT - timedelta(minutes=50 - 3 * n), None, empreinte(0))
    motifs = _suspicion(cx_, "r9", ["correlation-session"])
    assert [s["code"] for m in motifs for s in m["signaux"]] == ["empreinte_sans_memoire"]


def _page_sans_ressources(cx_, jeton: str, instant: datetime) -> None:
    cx_.execute(
        "INSERT INTO observations_http (session_token, received_at, method, path, http_version, headers, cookies)"
        " VALUES (?, ?, 'GET', '/lab/vitrine', '1.1', '[]', '[]')",
        (jeton, instant.isoformat(timespec="milliseconds")),
    )


def _codes_comportement(cx_, jeton: str) -> set[str]:
    return {s["code"] for m in _suspicion(cx_, jeton, ["comportement"]) for s in m["signaux"]}


def _ressource(cx_, jeton: str, instant: datetime) -> None:
    cx_.execute(
        "INSERT INTO observations_http (session_token, received_at, method, path, http_version, headers, cookies)"
        " VALUES (?, ?, 'GET', '/lab/static/observateur.js', '1.1', '[]', '[]')",
        (jeton, instant.isoformat(timespec="milliseconds")),
    )


def _visite_ailleurs(cx_, monde: str, visiteur: str, jeton: str, instant: datetime) -> None:
    cx_.execute(
        "INSERT INTO visites (monde_id, visiteur, session_token, neuve, vue_le) VALUES (?, ?, ?, 1, ?)",
        (visiteurs.identifiant_monde(cx_, monde), visiteur, jeton, instant.isoformat(timespec="milliseconds")),
    )


def _visiteur_de(cx_, jeton: str) -> str:
    return cx_.execute("SELECT visiteur FROM visites WHERE session_token = ?", (jeton,)).fetchone()["visiteur"]


def test_visiteur_connu_dont_la_premiere_session_a_charge_les_ressources_aucun_signal(monkeypatch):
    cx_ = _base()
    veille = MAINTENANT - timedelta(days=1)
    cookie = _arrivee(cx_, monkeypatch, "premiere", veille, None, empreinte(0))
    cookie = _arrivee(cx_, monkeypatch, "retour", MAINTENANT, cookie, empreinte(0))
    _page_sans_ressources(cx_, "premiere", veille)
    _ressource(cx_, "premiere", veille)  # le cache du navigateur les gardera
    _page_sans_ressources(cx_, "retour", MAINTENANT)
    assert "sans_ressources" not in _codes_comportement(cx_, "retour")  # un retour a ses scripts en cache


def test_visiteur_connu_sans_session_anterieure_chargeuse_garde_le_signal(monkeypatch):
    """Un robot qui rejoue un seul cookie sans jamais charger les ressources : le cache ne peut pas les contenir."""
    cx_ = _base()
    cookie = _arrivee(cx_, monkeypatch, "s0", MAINTENANT - timedelta(minutes=3), None, empreinte(0))
    cookie = _arrivee(cx_, monkeypatch, "s1", MAINTENANT - timedelta(minutes=2), cookie, empreinte(0))
    cookie = _arrivee(cx_, monkeypatch, "s2", MAINTENANT, cookie, empreinte(0))
    for jeton, instant in (("s0", -3), ("s1", -2), ("s2", 0)):
        _page_sans_ressources(cx_, jeton, MAINTENANT + timedelta(minutes=instant))
    assert correlation.visite_neuve(cx_, "s2") is True
    assert "sans_ressources" in _codes_comportement(cx_, "s2")


def test_ressources_d_une_session_posterieure_ne_dispensent_pas(monkeypatch):
    cx_ = _base()
    cookie = _arrivee(cx_, monkeypatch, "s0", MAINTENANT - timedelta(minutes=3), None, empreinte(0))
    _arrivee(cx_, monkeypatch, "s1", MAINTENANT - timedelta(minutes=2), cookie, empreinte(0))
    _ressource(cx_, "s0", MAINTENANT + timedelta(minutes=5))  # arrivée après : n'existait pas à la visite s1
    _page_sans_ressources(cx_, "s1", MAINTENANT)
    assert "sans_ressources" in _codes_comportement(cx_, "s1")


def test_ressources_d_un_autre_visiteur_ne_dispensent_pas(monkeypatch):
    cx_ = _base()
    _arrivee(cx_, monkeypatch, "autre", MAINTENANT - timedelta(minutes=5), None, empreinte(0))
    _ressource(cx_, "autre", MAINTENANT - timedelta(minutes=5))
    cookie = _arrivee(cx_, monkeypatch, "s0", MAINTENANT - timedelta(minutes=3), None, empreinte(0))
    _arrivee(cx_, monkeypatch, "s1", MAINTENANT, cookie, empreinte(0))
    _page_sans_ressources(cx_, "s1", MAINTENANT)
    assert _visiteur_de(cx_, "autre") != _visiteur_de(cx_, "s1")
    assert "sans_ressources" in _codes_comportement(cx_, "s1")


def test_ressources_d_un_autre_monde_ne_dispensent_pas(monkeypatch):
    cx_ = _base()
    cookie = _arrivee(cx_, monkeypatch, "s0", MAINTENANT - timedelta(minutes=3), None, empreinte(0))
    _arrivee(cx_, monkeypatch, "s1", MAINTENANT, cookie, empreinte(0))
    # Même identifiant de visiteur, mais dans un autre monde : sa session a chargé les ressources là-bas.
    _visite_ailleurs(cx_, "ailleurs", _visiteur_de(cx_, "s1"), "ailleurs-1", MAINTENANT - timedelta(minutes=5))
    _ressource(cx_, "ailleurs-1", MAINTENANT - timedelta(minutes=5))
    _page_sans_ressources(cx_, "s1", MAINTENANT)
    assert "sans_ressources" in _codes_comportement(cx_, "s1")


def test_le_detecteur_comportement_ignore_sans_ressources_pour_un_visiteur_connu():
    http = [{"path": "/lab/vitrine", "method": "GET", "received_at": MAINTENANT.isoformat(), "headers": []}]
    detecteur = registre()["comportement"]
    neuf = detecteur.classer(Observations(http=http, js=[{"kind": "empreinte", "payload": {}}]))
    connu = detecteur.classer(Observations(http=http, js=[{"kind": "empreinte", "payload": {}}], visite_neuve=False))
    assert "sans_ressources" in [s.code for s in neuf.signals]
    assert "sans_ressources" not in [s.code for s in connu.signals]


def test_visite_neuve_lit_la_table_visites(monkeypatch):
    cx_ = _base()
    cookie = _arrivee(cx_, monkeypatch, "a", MAINTENANT - timedelta(minutes=2), None)
    _arrivee(cx_, monkeypatch, "b", MAINTENANT, cookie)
    assert correlation.visite_neuve(cx_, "a") is True
    assert correlation.visite_neuve(cx_, "b") is True  # connu, mais aucune session antérieure n'a chargé de ressources
    _ressource(cx_, "a", MAINTENANT - timedelta(minutes=1))
    assert correlation.visite_neuve(cx_, "b") is False  # une session antérieure du visiteur les a chargées
    assert correlation.visite_neuve(cx_, "inconnue") is True  # sans visite enregistrée : traitée comme neuve


@pytest.fixture
def cx(tmp_path):
    connexion = db.ouvrir(tmp_path / "labo.sqlite3")
    yield connexion
    connexion.close()


# --- Rejeu : les sessions humaines antérieures de leur monde ----------------------------------------------


def _monde(cx_, nom: str) -> int:
    return visiteurs.identifiant_monde(cx_, nom)


def _session_dans(cx_, monde_id: int | None, *, debut: float = 0.0, anciennes: int = 0, apres: int = 0) -> str:
    """Session humaine rejouée, rangée dans le monde `monde_id`, avec `anciennes` visites neuves de même empreinte
    avant elle et `apres` après elle, toutes dans ce monde."""
    jeton = session_labo(cx_, protection="06")
    visite(cx_, jeton)  # observations de la session, empreinte `empreinte()` à t(1)
    if monde_id is not None:
        cx_.execute("UPDATE runs SET monde_id = ? WHERE session_token = ?", (monde_id, jeton))
        cx_.execute(
            "INSERT INTO visites (monde_id, visiteur, session_token, neuve, vue_le) VALUES (?, ?, ?, 1, ?)",
            (monde_id, f"moi-{jeton}", jeton, t(0)),
        )
    for n in range(anciennes + apres):
        autre = f"voisin-{jeton}-{n}"
        instant = t(-600 + 10 * n) if n < anciennes else t(600 + 10 * n)
        cx_.execute(
            "INSERT INTO visites (monde_id, visiteur, session_token, neuve, vue_le) VALUES (?, ?, ?, 1, ?)",
            (monde_id, f"v-{autre}", autre, instant),
        )
        message(cx_, autre, instant, empreinte())
    return jeton


def _historique(cx_, resultat_niveau: str = "06"):
    return niveau(rejeu.rejouer(cx_), resultat_niveau)["correlation_historique"]


def test_rejeu_voit_les_visites_anterieures_de_son_monde(cx):
    _session_dans(cx, _monde(cx, "humains-a"), anciennes=10)
    assert _historique(cx) == {"sessions": 1, "sur": 1}  # 10 neuves avant + elle : seuil 10, automatisé


def test_rejeu_ne_voit_pas_un_autre_monde(cx):
    autre = _monde(cx, "humains-b")
    _session_dans(cx, autre, anciennes=10)  # leurs visites sont dans `humains-b`
    cx.execute("INSERT INTO mondes (nom, cree_le) VALUES ('humains-c', ?)", (t(0),))
    _session_dans(cx, _monde(cx, "humains-c"))  # sans voisins
    resultat = rejeu.rejouer(cx)
    par_jeton = {s["jeton"]: s for s in resultat["detail"]}
    assert [s["correlation_historique"] for s in par_jeton.values()] == [True, False]


def test_rejeu_ne_voit_pas_les_visites_posterieures(cx):
    _session_dans(cx, _monde(cx, "humains-d"), apres=15)
    assert _historique(cx) == {"sessions": 0, "sur": 1}


def test_rejeu_session_sans_monde_non_evaluee(cx):
    """`runs.monde_id` NULL (historique, avant I1) : on ignore à quel monde elle appartenait, donc on ne juge pas
    (`None`), au lieu de la dire seule dans son monde (ce qui affirmerait qu'elle était neuve)."""
    jeton = _session_dans(cx, None)
    resultat = rejeu.rejouer(cx)
    assert next(s for s in resultat["detail"] if s["jeton"] == jeton)["correlation_historique"] is None
    assert niveau(resultat, "06")["correlation_historique"] is None


def test_rejeu_mondes_et_sans_monde_ensemble(cx):
    _session_dans(cx, None)
    _session_dans(cx, _monde(cx, "humains-e"), anciennes=10)
    assert _historique(cx) == {"sessions": 1, "sur": 1}  # compté sur les seules sessions évaluées


def test_rejeu_reste_en_lecture_seule_avec_la_regle_2(cx):
    _session_dans(cx, _monde(cx, "humains-f"), anciennes=10)
    avant = cx.total_changes
    rejeu.rejouer(cx)
    assert cx.total_changes == avant
