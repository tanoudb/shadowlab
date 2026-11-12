"""Tests de la corrélation cross-session."""

import json
import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from shadowlab import database as db
from shadowlab.correlation import correlation_session, enregistrer_hash, hash_session
from shadowlab.detection import Classement, DetecteurCorrelationSession, Observations

T0 = datetime(2026, 11, 12, 8, 0, tzinfo=UTC)
TYPES = ("profil_complet", "canvas")


def _empreinte(ua: str = "Chrome/131", hwc: int = 8, canvas: str = "a1b2c3d4e5f60718", largeur: int = 1920) -> dict:
    """Même forme que `collecter()` dans `site/static/observateur.js` : écran et canvas au premier niveau."""
    return {
        "navigateur": {
            "userAgent": ua,
            "platform": "MacIntel",
            "hardwareConcurrency": hwc,
            "languages": ["fr"],
            "userAgentData": None,
        },
        "ecran": {"width": largeur, "height": 1080, "devicePixelRatio": 2},
        "canvas": canvas,
    }


def _base_memoire() -> sqlite3.Connection:
    cx = sqlite3.connect(":memory:")
    cx.row_factory = sqlite3.Row
    db.migrer(cx)
    return cx


def _classer(correlation: dict | None) -> Classement:
    return DetecteurCorrelationSession().classer(Observations(http=[], js=[], correlation=correlation))


def _codes(c: Classement) -> list[str]:
    return [s.code for s in c.signals]


def _horloge(monkeypatch, instant: datetime) -> None:
    """Fixe l'heure de la base : `enregistrer_hash` et `correlation_session` lisent `db.maintenant()`."""
    monkeypatch.setattr(db, "maintenant", lambda: instant.isoformat(timespec="milliseconds"))


def _sessions(cx, monkeypatch, instants: list[datetime]) -> None:
    """Une session par instant, vue comme par `/lab/collecte` : empreinte rangée dans observations_js, puis hachée."""
    emp = _empreinte()
    for n, instant in enumerate(instants):
        _horloge(monkeypatch, instant)
        cx.execute(
            "INSERT INTO observations_js (session_token, received_at, kind, page, payload) VALUES (?, ?, ?, ?, ?)",
            (f"s{n}", db.maintenant(), "empreinte", "/lab/vitrine", json.dumps(emp)),
        )
        enregistrer_hash(cx, f"s{n}", emp)


def _lire(cx, monkeypatch, instant: datetime) -> tuple[dict, Classement]:
    """Débit de chaque hash de l'empreinte de test lu à `instant` (compte, exact), et classement du détecteur."""
    _horloge(monkeypatch, instant)
    donnees = correlation_session(cx, _empreinte())
    debit = {t: (d["sessions_derniere_heure"], d["derniere_heure_exacte"]) for t, d in donnees.items()}
    return debit, _classer(donnees)


def _signaux(profil: dict | None = None, canvas: dict | None = None) -> dict[str, tuple[str, float]]:
    """Signaux du détecteur pour des données de corrélation (chaque hash vu une fois par défaut)."""

    def donnees(champs: dict | None) -> dict:
        return {"nb_sessions": 1, "sessions_derniere_heure": 1, "derniere_heure_exacte": True} | (champs or {})

    c = _classer({"profil_complet": donnees(profil), "canvas": donnees(canvas)})
    return {s.code: (s.description, s.poids) for s in c.signals}


def test_hash_session_stable():
    emp = _empreinte()
    h1 = hash_session(emp)
    h2 = hash_session(emp)
    assert h1 == h2
    assert "profil_complet" in h1
    assert "canvas" in h1


def test_hash_profil_change_avec_l_ecran():
    """L'écran fait partie du profil : deux écrans différents donnent deux profils différents."""
    h1 = hash_session(_empreinte(largeur=1920))
    h2 = hash_session(_empreinte(largeur=1440))
    assert h1["profil_complet"] != h2["profil_complet"]


def test_hash_canvas_change_avec_le_canvas():
    h1 = hash_session(_empreinte(canvas="a1b2c3d4e5f60718"))
    h2 = hash_session(_empreinte(canvas="0011223344556677"))
    assert h1["canvas"] != h2["canvas"]


def test_canvas_en_erreur_ne_produit_pas_de_hash():
    """`empreinteCanvas()` renvoie « erreur: … » quand le canvas échoue : ce n'est pas une empreinte.

    Sinon tous les navigateurs qui bloquent le canvas partageraient le même hash et seraient
    pris pour une seule empreinte recyclée.
    """
    assert "canvas" not in hash_session(_empreinte(canvas="erreur: SecurityError"))


def test_hash_session_change_avec_ua():
    h1 = hash_session(_empreinte(ua="Chrome/131"))
    h2 = hash_session(_empreinte(ua="Firefox/130"))
    assert h1["profil_complet"] != h2["profil_complet"]


def test_hash_session_deux_types_seulement():
    """Les types enregistrés restent ceux d'avant : l'historique de `empreintes_vues` garde son sens."""
    assert set(hash_session(_empreinte())) == set(TYPES)


def test_enregistrer_hash_incremente():
    cx = _base_memoire()
    emp = _empreinte()
    enregistrer_hash(cx, "session-1", emp)
    enregistrer_hash(cx, "session-2", emp)
    enregistrer_hash(cx, "session-3", emp)
    row = cx.execute("SELECT nb_sessions FROM empreintes_vues WHERE type = 'profil_complet'").fetchone()
    assert row["nb_sessions"] == 3


def test_enregistrer_hash_idempotent():
    cx = _base_memoire()
    emp = _empreinte()
    enregistrer_hash(cx, "session-1", emp)
    enregistrer_hash(cx, "session-1", emp)
    row = cx.execute("SELECT nb_sessions FROM empreintes_vues WHERE type = 'profil_complet'").fetchone()
    assert row["nb_sessions"] == 1


def test_correlation_session_premiere_visite():
    cx = _base_memoire()
    emp = _empreinte()
    result = correlation_session(cx, emp)
    assert result == {}


def test_correlation_session_apres_enregistrement():
    cx = _base_memoire()
    emp = _empreinte()
    enregistrer_hash(cx, "s1", emp)
    enregistrer_hash(cx, "s2", emp)
    enregistrer_hash(cx, "s3", emp)
    result = correlation_session(cx, emp)
    assert list(result) == list(TYPES)
    assert result["profil_complet"]["nb_sessions"] == 3
    assert result["canvas"]["nb_sessions"] == 3


def test_detecteur_correlation_sans_donnees():
    det = DetecteurCorrelationSession()
    obs = Observations(http=[], js=[], correlation=None)
    c = det.classer(obs)
    assert c.classification == "indetermine"


def test_detecteur_correlation_avec_recyclage():
    det = DetecteurCorrelationSession()
    obs = Observations(
        http=[],
        js=[],
        correlation={
            "profil_complet": {
                "nb_sessions": 12,
                "premiere_vue": "2026-01-01T00:00:00+00:00",
                "derniere_vue": "2026-01-01T01:00:00+00:00",
                "sessions_derniere_heure": 35,
                "derniere_heure_exacte": True,
            },
        },
    )
    c = det.classer(obs)
    assert c.classification == "automatise"
    assert any("recycling" in s.code for s in c.signals)


def test_detecteur_correlation_sous_seuil():
    det = DetecteurCorrelationSession()
    obs = Observations(
        http=[],
        js=[],
        correlation={
            "profil_complet": {
                "nb_sessions": 2,
                "premiere_vue": "2026-01-01T00:00:00+00:00",
                "derniere_vue": "2026-01-01T01:00:00+00:00",
                "sessions_derniere_heure": 2,
                "derniere_heure_exacte": True,
            },
        },
    )
    c = det.classer(obs)
    assert c.classification != "automatise"


# --- Un fait, un signal : le plus grand des deux comptes --------------------------------------------------


@pytest.mark.parametrize(
    ("sessions", "seuil", "poids", "classement"), [(5, 5, 0.7, "indetermine"), (10, 10, 1.0, "automatise")]
)
def test_profil_et_canvas_identiques_un_seul_signal(sessions, seuil, poids, classement):
    """Profil et canvas revus ensemble décrivent la même observation : un signal, pas deux (avant : 0,7 + 0,7)."""
    cx = _base_memoire()
    for n in range(sessions):
        enregistrer_hash(cx, f"s{n}", _empreinte())
    c = _classer(correlation_session(cx, _empreinte()))
    description = (
        f"profil vu dans {sessions} sessions et canvas vu dans {sessions} sessions de la base, celle-ci comprise"
        f" (seuil {seuil})"
    )
    assert [(s.code, s.description, s.poids) for s in c.signals] == [("recycling_profil_complet", description, poids)]
    assert c.classification == classement


def test_profil_stable_canvas_change_a_chaque_session():
    """Un canvas bruité différemment à chaque session (navigateurs anti-détection) n'efface pas le profil revu."""
    cx = _base_memoire()
    for n in range(5):
        enregistrer_hash(cx, f"s{n}", _empreinte(canvas=f"{n:016x}"))
    c = _classer(correlation_session(cx, _empreinte(canvas=f"{4:016x}")))
    assert [(s.code, s.description, s.poids) for s in c.signals] == [
        ("recycling_profil_complet", "profil vu dans 5 sessions de la base, celle-ci comprise (seuil 5)", 0.7)
    ]


def test_canvas_stable_profil_change_a_chaque_session():
    """Comportement d'avant, gardé : le canvas revu seul suffit au signal.

    Ce cas classe aussi des humains sur le même matériel : le petit dessin du canvas est le même pour tout Chromium
    156 de ce Mac (docs/recherche/correlation-entre-sessions-2026-11-12.md, R8). À revoir au palier 2, avec la
    mémoire des visiteurs.
    """
    cx = _base_memoire()
    for n in range(5):
        enregistrer_hash(cx, f"s{n}", _empreinte(largeur=1000 + n))
    c = _classer(correlation_session(cx, _empreinte(largeur=1004)))
    assert [(s.code, s.description, s.poids) for s in c.signals] == [
        ("recycling_canvas", "canvas vu dans 5 sessions de la base, celle-ci comprise (seuil 5)", 0.7)
    ]


# --- Libellés : ce que la règle compte ------------------------------------------------------------------


def test_libelles_disent_ce_qui_est_compte():
    """Un signal de comptage et un de débit au plus ; le libellé dit quel hash a franchi le seuil, et combien."""
    debit = "commencées dans les 60 dernières minutes (seuil 30)"
    assert _signaux() == {}
    assert _signaux(profil={"nb_sessions": 4}, canvas={"nb_sessions": 4}) == {}
    assert _signaux(profil={"nb_sessions": 5}) == {
        "recycling_profil_complet": ("profil vu dans 5 sessions de la base, celle-ci comprise (seuil 5)", 0.7)
    }
    assert _signaux(profil={"nb_sessions": 6}, canvas={"nb_sessions": 5}) == {
        "recycling_profil_complet": (
            "profil vu dans 6 sessions et canvas vu dans 5 sessions de la base, celle-ci comprise (seuil 5)",
            0.7,
        )
    }
    # Le plus grand compte fixe le seuil, le poids et le suffixe du code ; seul le hash qui franchit ce seuil est cité.
    assert _signaux(profil={"nb_sessions": 6}, canvas={"nb_sessions": 12}) == {
        "recycling_canvas": ("canvas vu dans 12 sessions de la base, celle-ci comprise (seuil 10)", 1.0)
    }
    assert _signaux(profil={"sessions_derniere_heure": 29}) == {}
    assert _signaux(profil={"sessions_derniere_heure": 31}) == {
        "velocity_profil_complet": (f"31 sessions de même profil {debit}", 0.8)
    }
    assert _signaux(profil={"sessions_derniere_heure": 30}, canvas={"sessions_derniere_heure": 31}) == {
        "velocity_canvas": (f"30 sessions de même profil et 31 sessions de même canvas {debit}", 0.8)
    }
    # Compte incomplet (borne basse) qui atteint quand même le seuil : le libellé le dit.
    assert _signaux(profil={"sessions_derniere_heure": 31, "derniere_heure_exacte": False}) == {
        "velocity_profil_complet": (f"au moins 31 sessions de même profil {debit}", 0.8)
    }
    tous = _signaux(*[{"nb_sessions": 40, "sessions_derniere_heure": 40}] * 2)
    assert sorted(tous) == ["recycling_profil_complet", "velocity_profil_complet"]
    assert "rotation" not in " ".join(description for description, _ in tous.values())


# --- Débit : sessions des 60 dernières minutes, pour chaque hash ----------------------------------------


def test_deux_sessions_a_trois_minutes_pas_de_debit(monkeypatch):
    """Régression : la moyenne sur la vie de l'empreinte donnait 2 sessions / 3 min = 40 par heure."""
    cx = _base_memoire()
    _sessions(cx, monkeypatch, [T0, T0 + timedelta(minutes=3)])
    debit, c = _lire(cx, monkeypatch, T0 + timedelta(minutes=3))
    assert debit == dict.fromkeys(TYPES, (2, True))
    assert c.signals == []


@pytest.mark.parametrize(("sessions", "signal"), [(29, False), (30, True)])
def test_trente_sessions_dans_l_heure_declenchent_le_debit(monkeypatch, sessions, signal):
    cx = _base_memoire()
    instants = [T0 + timedelta(minutes=2 * n) for n in range(sessions)]  # une toutes les 2 min : 56 ou 58 min
    _sessions(cx, monkeypatch, instants)
    debit, c = _lire(cx, monkeypatch, instants[-1])
    assert debit == dict.fromkeys(TYPES, (sessions, True))
    vitesse = [code for code in _codes(c) if code.startswith("velocity_")]
    assert vitesse == (["velocity_profil_complet"] if signal else [])  # un seul signal pour les deux hash


def test_trente_sessions_sur_deux_jours_pas_de_debit(monkeypatch):
    cx = _base_memoire()
    instants = [T0 + timedelta(minutes=96 * n) for n in range(30)]  # une toutes les 1 h 36, sur 46 h 24
    _sessions(cx, monkeypatch, instants)
    debit, c = _lire(cx, monkeypatch, instants[-1])
    assert debit == dict.fromkeys(TYPES, (1, True))
    assert not [code for code in _codes(c) if code.startswith("velocity_")]


def test_rafale_sous_la_minute_comptee(monkeypatch):
    """Régression : sous une minute entre la première et la dernière vue, l'ancien calcul rendait 0."""
    cx = _base_memoire()
    instants = [T0 + timedelta(seconds=5 * n) for n in range(10)]  # 10 sessions en 45 s
    _sessions(cx, monkeypatch, instants)
    debit, _ = _lire(cx, monkeypatch, instants[-1])
    assert debit == dict.fromkeys(TYPES, (10, True))


def test_rafale_ancienne_oubliee(monkeypatch):
    """Régression : 100 sessions en 50 min, puis une session près de 3 h plus tard. La moyenne sur la vie de
    l'empreinte donnait 101 / 2 h 50 ≈ 36 par heure ; dans les 60 dernières minutes, il n'y a qu'une session."""
    cx = _base_memoire()
    rafale = [T0 + timedelta(seconds=30 * n) for n in range(100)]
    _sessions(cx, monkeypatch, [*rafale, T0 + timedelta(hours=2, minutes=50)])
    debit, c = _lire(cx, monkeypatch, T0 + timedelta(hours=2, minutes=50))
    assert debit == dict.fromkeys(TYPES, (1, True))
    assert not [code for code in _codes(c) if code.startswith("velocity_")]


def test_vieille_empreinte_debit_en_borne_basse(monkeypatch):
    """Limite : la table ne garde que les 10 derniers jetons d'un hash. S'ils tombent tous dans l'heure et que le
    hash est plus ancien, le nombre de sessions de l'heure n'est pas connu : au moins 10."""
    cx = _base_memoire()
    anciennes = [T0 - timedelta(days=2) + timedelta(minutes=n) for n in range(5)]
    recentes = [T0 + timedelta(minutes=2 * n) for n in range(12)]
    _sessions(cx, monkeypatch, anciennes + recentes)
    debit, c = _lire(cx, monkeypatch, recentes[-1])
    assert debit == dict.fromkeys(TYPES, (10, False))
    assert _codes(c) == ["recycling_profil_complet"]  # 17 sessions : le compte classe déjà
