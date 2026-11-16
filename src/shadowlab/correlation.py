"""Corrélation cross-session : même empreinte portée par beaucoup de visiteurs neufs, ou à un débit qu'aucune
personne ne tient (règle `correlation-session` 2.0, palier 2 I2 ; conception : `docs/recherche/identite-qui-dure`
§ 4.3).

Une empreinte stable n'est pas suspecte (un humain qui revient garde la sienne) : la règle compte des **visites**
(`visites`, I1) dans un **monde**, et ne reproche une empreinte qu'aux sessions neuves, celles dont la première requête
n'apportait pas de visiteur connu. `evaluer` est une fonction pure ; `evaluer_session` et `correlation_historique` la
nourrissent depuis la base.

`hash_session` et `enregistrer_hash` (table `empreintes_vues`, règle 1.1) restent appelés à la collecte mais ne
décident plus rien.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from . import database as db

FENETRE_DEBIT = timedelta(minutes=60)
FENETRE_NEUVES = timedelta(hours=24)


def hash_session(empreinte_js: dict) -> dict[str, str]:
    """Calcule les hash de corrélation à partir de l'empreinte JS collectée.

    La forme lue est celle de `collecter()` dans `site/static/observateur.js` : `navigateur`,
    `ecran` et `canvas` sont au premier niveau.
    """
    nav = empreinte_js.get("navigateur") or {}
    ecran = empreinte_js.get("ecran") or {}

    profil_data = json.dumps(
        {
            "ua": nav.get("userAgent", ""),
            "platform": (nav.get("userAgentData") or {}).get("platform", nav.get("platform", "")),
            "screen": {
                "w": ecran.get("width", ecran.get("w")),
                "h": ecran.get("height", ecran.get("h")),
            },
            "hwc": nav.get("hardwareConcurrency"),
            "dpr": ecran.get("devicePixelRatio", ecran.get("dpr")),
            "languages": nav.get("languages", []),
        },
        sort_keys=True,
    )

    canvas = str(empreinte_js.get("canvas") or "")

    result: dict[str, str] = {}
    result["profil_complet"] = hashlib.sha256(profil_data.encode()).hexdigest()[:16]
    # Un canvas en échec renvoie « erreur: … » : ce texte commun n'est pas une empreinte.
    if canvas and not canvas.startswith("erreur"):
        result["canvas"] = hashlib.sha256(canvas.encode()).hexdigest()[:16]
    return result


def enregistrer_hash(cx: sqlite3.Connection, jeton: str, empreinte_js: dict) -> None:
    """Enregistre les hash d'une session dans la table empreintes_vues."""
    hashes = hash_session(empreinte_js)
    maintenant = db.maintenant()
    for type_hash, valeur in hashes.items():
        row = cx.execute(
            "SELECT id, nb_sessions, sessions FROM empreintes_vues WHERE type = ? AND hash = ?",
            (type_hash, valeur),
        ).fetchone()
        if row:
            sessions = json.loads(row["sessions"])
            if jeton not in sessions:
                sessions = (sessions + [jeton])[-10:]
                cx.execute(
                    "UPDATE empreintes_vues SET derniere_vue = ?, nb_sessions = nb_sessions + 1, "
                    "sessions = ? WHERE id = ?",
                    (maintenant, json.dumps(sessions), row["id"]),
                )
        else:
            cx.execute(
                "INSERT INTO empreintes_vues (type, hash, premiere_vue, derniere_vue, nb_sessions, sessions) "
                "VALUES (?, ?, ?, ?, 1, ?)",
                (type_hash, valeur, maintenant, maintenant, json.dumps([jeton])),
            )


# --- Règle 2.0 ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class VisiteObservee:
    """Une visite d'un monde : une session (un jeton), son visiteur, son heure de début, son empreinte E."""

    session: str
    visiteur: str
    neuve: bool
    debut: datetime
    empreinte: str | None  # E de la première empreinte reçue ; None tant qu'aucune n'est arrivée


@dataclass(frozen=True)
class Correlation:
    """Ce que la règle 2.0 lit pour une session : les comptes de son empreinte E dans son monde."""

    empreinte: str | None
    session_neuve: bool
    sessions_neuves_24h: int  # sessions neuves portant E commencées dans les 24 dernières heures, celle-ci comprise
    debit_60min: int  # sessions portant E commencées dans les 60 dernières minutes, celle-ci comprise


def empreinte_e(empreinte_js: dict) -> str:
    """E : un seul hachage de `profil_complet` et `canvas` ensemble (un fait, un signal).

    Un canvas en échec n'entre pas : E ne vaut alors que le profil, et ne sépare plus deux configurations de même
    profil. À l'inverse, deux configurations de même canvas mais de profils différents ont deux E (en 1.1, elles
    s'additionnaient par le canvas).
    """
    h = hash_session(empreinte_js)
    return hashlib.sha256(f"{h['profil_complet']}|{h.get('canvas', '')}".encode()).hexdigest()[:16]


def evaluer(visites: list[VisiteObservee], session: str, maintenant: datetime) -> Correlation:
    """Règle 2.0, sans base : `visites` sont celles du monde de `session` (celle-ci comprise), `maintenant` l'heure.

    - une visite postérieure à `maintenant` n'existe pas encore (rejeu) ;
    - une session compte une fois, quel que soit le nombre d'empreintes qu'elle a envoyées (E = la première) ;
    - une visite sans empreinte ne porte aucune E ;
    - une session inconnue de `visites` n'a ni empreinte ni compte.
    """
    parjeton = {x.session: x for x in visites if x.debut <= maintenant}
    propre = parjeton.get(session)
    if propre is None:
        return Correlation(None, True, 0, 0)
    if propre.empreinte is None:
        return Correlation(None, propre.neuve, 0, 0)
    memes = [x for x in parjeton.values() if x.empreinte == propre.empreinte]
    neuves = sum(1 for x in memes if x.neuve and x.debut >= maintenant - FENETRE_NEUVES)
    debit = sum(1 for x in memes if x.debut >= maintenant - FENETRE_DEBIT)
    return Correlation(propre.empreinte, propre.neuve, neuves, debit)


_E_PAR_CONTENU: dict[str, str | None] = {}  # texte de l'empreinte → E : le contenu est la clé, sûr entre bases


def _e_du_texte(payload: str | None) -> str | None:
    if not payload:
        return None
    if payload not in _E_PAR_CONTENU:
        if len(_E_PAR_CONTENU) >= 512:
            _E_PAR_CONTENU.clear()
        try:
            valeur = json.loads(payload)
            _E_PAR_CONTENU[payload] = empreinte_e(valeur) if isinstance(valeur, dict) else None
        except ValueError:
            _E_PAR_CONTENU[payload] = None
    return _E_PAR_CONTENU[payload]


_PREMIERE_EMPREINTE = (
    "(SELECT payload FROM observations_js o WHERE o.session_token = v.session_token AND o.kind = 'empreinte'"
    " ORDER BY o.id LIMIT 1)"
)


def _stamp(instant: datetime) -> str:
    return instant.astimezone(UTC).isoformat(timespec="milliseconds")


def _visites_du_monde(cx: sqlite3.Connection, monde_id: int, maintenant: datetime) -> list[VisiteObservee]:
    """Visites du monde commencées dans les 24 heures qui précèdent `maintenant`, avec leur E (lecture seule)."""
    lignes = cx.execute(
        f"SELECT v.session_token, v.visiteur, v.neuve, v.vue_le, {_PREMIERE_EMPREINTE} AS payload FROM visites v"
        " WHERE v.monde_id = ? AND v.session_token IS NOT NULL AND v.vue_le >= ? AND v.vue_le <= ?",
        (monde_id, _stamp(maintenant - FENETRE_NEUVES), _stamp(maintenant)),
    ).fetchall()
    return [
        VisiteObservee(r["session_token"], r["visiteur"], bool(r["neuve"]), datetime.fromisoformat(r["vue_le"]), e)
        for r in lignes
        if (e := _e_du_texte(r["payload"])) is not None
    ]


def _premiere_empreinte(cx: sqlite3.Connection, jeton: str) -> str | None:
    ligne = cx.execute(
        "SELECT payload FROM observations_js WHERE session_token = ? AND kind = 'empreinte' ORDER BY id LIMIT 1",
        (jeton,),
    ).fetchone()
    return _e_du_texte(ligne["payload"]) if ligne else None


def empreinte_de_session(cx: sqlite3.Connection, jeton: str) -> str | None:
    """E de la première empreinte reçue de cette session (une lecture indexée), ou None si elle n'est pas arrivée."""
    return _premiere_empreinte(cx, jeton)


def _evaluer_dans(
    cx: sqlite3.Connection, jeton: str, monde_id: int, propre: VisiteObservee, maintenant: datetime
) -> Correlation:
    # La visite de la session est ajoutée à part : elle peut dater de plus de 24 h (session longue).
    voisines = [x for x in _visites_du_monde(cx, monde_id, maintenant) if x.session != jeton]
    return evaluer([*voisines, propre], jeton, maintenant)


def evaluer_session(cx: sqlite3.Connection, jeton: str, maintenant: datetime | None = None) -> Correlation:
    """La règle 2.0 pour une session en cours : son monde et sa visite viennent de la table `visites`.

    Une session sans visite enregistrée (aucune requête `/lab` reconnue) n'a pas de monde : rien n'est compté.
    """
    maintenant = maintenant or datetime.fromisoformat(db.maintenant())
    ligne = cx.execute(
        "SELECT monde_id, visiteur, neuve, vue_le FROM visites WHERE session_token = ?", (jeton,)
    ).fetchone()
    if ligne is None:
        return evaluer([], jeton, maintenant)
    propre = VisiteObservee(
        jeton, ligne["visiteur"], bool(ligne["neuve"]), datetime.fromisoformat(ligne["vue_le"]),
        _premiere_empreinte(cx, jeton),
    )  # fmt: skip
    return _evaluer_dans(cx, jeton, ligne["monde_id"], propre, maintenant)


def correlation_historique(
    cx: sqlite3.Connection, jeton: str, monde_id: int | None, debut: datetime
) -> Correlation | None:
    """La règle 2.0 telle qu'elle aurait jugé cette session à son début (rejeu, lecture seule).

    Ne voit que les visites antérieures de `monde_id` (celui de la session dans `runs`). Sans monde (`None` :
    sessions d'avant I1), on ignore à quel monde la session appartenait : rien n'est jugé, la réponse est `None`.
    `debut` sert quand la session n'a pas de ligne `visites` ; elle est alors comptée comme neuve.
    """
    if monde_id is None:
        return None
    ligne = cx.execute("SELECT visiteur, neuve, vue_le FROM visites WHERE session_token = ?", (jeton,)).fetchone()
    if ligne:
        propre = VisiteObservee(
            jeton, ligne["visiteur"], bool(ligne["neuve"]), datetime.fromisoformat(ligne["vue_le"]),
            _premiere_empreinte(cx, jeton),
        )  # fmt: skip
    else:
        propre = VisiteObservee(jeton, "", True, debut, _premiere_empreinte(cx, jeton))
    return _evaluer_dans(cx, jeton, monde_id, propre, propre.debut)


def visite_neuve(cx: sqlite3.Connection, jeton: str) -> bool:
    """`sans_ressources` doit-il juger cette session comme une première visite ?

    Oui pour une session neuve, ou sans visite enregistrée. Un visiteur connu n'en est dispensé que si une session
    antérieure du même visiteur, dans le même monde, avait chargé les ressources (`/lab/static`) avant le début de
    celle-ci : sans cela son cache ne peut pas les contenir, et un robot qui rejoue un seul cookie sans jamais les
    charger resterait signalé. Une seule lecture indexée, et seulement pour une session connue ; elle est faite
    là où le gardien (et le rejeu) construisent leurs observations, pas à chaque requête.
    """
    ligne = cx.execute(
        "SELECT monde_id, visiteur, neuve, vue_le FROM visites WHERE session_token = ?", (jeton,)
    ).fetchone()
    if ligne is None or ligne["neuve"]:
        return True
    cache = cx.execute(
        "SELECT 1 FROM visites w WHERE w.monde_id = ? AND w.visiteur = ? AND w.session_token != ? AND w.vue_le < ?"
        " AND EXISTS (SELECT 1 FROM observations_http h WHERE h.session_token = w.session_token"
        " AND h.path LIKE '/lab/static%' AND h.received_at <= ?) LIMIT 1",
        (ligne["monde_id"], ligne["visiteur"], jeton, ligne["vue_le"], ligne["vue_le"]),
    ).fetchone()
    return cache is None
