"""Tests du hachage et de la table `empreintes_vues` (la règle de décision est testée dans test_correlation_v2)."""

import sqlite3

from shadowlab import database as db
from shadowlab.correlation import enregistrer_hash, hash_session

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
