"""Allègement d'I1 : une requête d'une session déjà connue, avec un cookie valable, n'écrit rien dans la base.

La campagne 118 avait mesuré des durées 4 à 17 % plus longues que la 115 (cause non établie) ; chaque requête `/lab`
ouvrait une connexion et tentait deux `INSERT OR IGNORE` (`mondes`, `visites`).
"""

from __future__ import annotations

import sqlite3

from test_visiteurs import nouveau_passage, nouvelle_experience

from shadowlab import database as db
from shadowlab.arena import visiteurs

SECRET = b"secret-d-essai"


def _base() -> sqlite3.Connection:
    cx = sqlite3.connect(":memory:", isolation_level=None)
    cx.row_factory = sqlite3.Row
    db.migrer(cx)
    return cx


def _ecritures(cx: sqlite3.Connection, appel) -> list[str]:
    """Instructions d'écriture exécutées pendant `appel()`."""
    vues: list[str] = []
    cx.set_trace_callback(vues.append)
    try:
        appel()
    finally:
        cx.set_trace_callback(None)
    return [v for v in vues if v.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE", "REPLACE"))]


# --- Fonction : lire d'abord ----------------------------------------------------------------------------


def test_premiere_requete_ecrit_la_visite():
    cx = _base()
    ecrites = _ecritures(cx, lambda: visiteurs.reconnaitre(cx, SECRET, None, "jeton-a"))
    assert any("visites" in e for e in ecrites)


def test_session_connue_avec_cookie_valable_n_ecrit_rien():
    cx = _base()
    cookie = visiteurs.reconnaitre(cx, SECRET, None, "jeton-a").cookie
    avant = cx.total_changes
    ecrites = _ecritures(cx, lambda: visiteurs.reconnaitre(cx, SECRET, cookie, "jeton-a"))
    assert ecrites == []
    assert cx.total_changes == avant


def test_session_connue_sans_cookie_ne_cree_pas_de_visite_mais_repose_le_cookie():
    cx = _base()
    premiere = visiteurs.reconnaitre(cx, SECRET, None, "jeton-a")
    ecrites = _ecritures(cx, lambda: visiteurs.reconnaitre(cx, SECRET, None, "jeton-a"))
    suivante = visiteurs.reconnaitre(cx, SECRET, None, "jeton-a")
    assert ecrites == []
    assert suivante.cookie == premiere.cookie and suivante.neuve is False
    assert cx.execute("SELECT COUNT(*) FROM visites").fetchone()[0] == 1


def test_requete_sans_jeton_avec_cookie_valable_n_ecrit_rien():
    cx = _base()
    cookie = visiteurs.reconnaitre(cx, SECRET, None, "").cookie
    assert _ecritures(cx, lambda: visiteurs.reconnaitre(cx, SECRET, cookie, "")) == []


# --- Cache de l'application : pas même une connexion ----------------------------------------------------


def test_cache_retrouve_une_session_retenue():
    connus = visiteurs.Connus()
    visite = visiteurs.Visite("monde", "v" * 32, False, None)
    cookie = visiteurs.creer_cookie(SECRET, "monde", "v" * 32)
    connus.retenir("jeton-a", visite)
    assert connus.retrouver(SECRET, cookie, "jeton-a") == visite
    assert connus.retrouver(SECRET, None, "jeton-a") is None  # sans cookie : la base dit quoi poser
    assert connus.retrouver(SECRET, visiteurs.creer_cookie(SECRET, "monde", "w" * 32), "jeton-a") is None
    assert connus.retrouver(SECRET, cookie, "jeton-b") is None
    assert connus.retrouver(SECRET, cookie, "") is None


def test_cache_borne():
    connus = visiteurs.Connus(maximum=3)
    for n in range(10):
        connus.retenir(f"j{n}", visiteurs.Visite("m", "v", False, None))
    cookie = visiteurs.creer_cookie(SECRET, "m", "v")
    gardes = [n for n in range(10) if connus.retrouver(SECRET, cookie, f"j{n}")]
    assert 1 <= len(gardes) <= 3 and 9 in gardes  # les plus récents restent


def test_requete_suivante_d_une_session_connue_n_atteint_pas_la_base(client, reglages, monkeypatch):
    jeton = nouveau_passage(reglages, nouvelle_experience(reglages, "allegement"))
    appels: list[str] = []
    vrai = visiteurs.reconnaitre

    def espion(cx, secret, valeur, jeton_):
        appels.append(jeton_)
        return vrai(cx, secret, valeur, jeton_)

    monkeypatch.setattr(visiteurs, "reconnaitre", espion)
    assert client.get(f"/lab/?sl={jeton}").status_code == 200
    assert appels == [jeton]  # la première requête passe par la base
    for _ in range(3):
        assert client.get(f"/lab/?sl={jeton}").status_code == 200
    assert appels == [jeton]  # les suivantes, avec le cookie valable, non


def test_le_cache_n_empeche_pas_de_reposer_un_cookie_perdu(client, reglages):
    jeton = nouveau_passage(reglages, nouvelle_experience(reglages, "cookie-perdu"))
    client.get(f"/lab/?sl={jeton}")
    client.cookies.delete("sl_visiteur")
    r = client.get(f"/lab/?sl={jeton}")
    assert any(e.startswith("sl_visiteur=") for e in r.headers.get_list("set-cookie"))
