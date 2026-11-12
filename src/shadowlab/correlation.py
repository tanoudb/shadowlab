"""Corrélation cross-session : détecte le recyclage de fingerprints entre sessions.

Un bot qui réutilise le même profil navigateur produit des hash identiques (canvas, profil,
audio). Ce module enregistre les hash observés et signale les sessions dont l'empreinte
a déjà été vue trop souvent.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timedelta

from . import database as db

FENETRE_DEBIT = timedelta(minutes=60)


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


def correlation_session(cx: sqlite3.Connection, empreinte_js: dict) -> dict[str, dict]:
    """Données de corrélation de chaque hash de l'empreinte déjà vu (`profil_complet`, `canvas`).

    `nb_sessions` : jetons distincts vus avec ce hash depuis la création de la ligne, la session courante comprise
    (`/lab/collecte` l'enregistre avant de juger). `sessions_derniere_heure` et `derniere_heure_exacte` : voir
    `_sessions_derniere_heure`.
    """
    maintenant = datetime.fromisoformat(db.maintenant())
    resultats: dict[str, dict] = {}
    for type_hash, valeur in hash_session(empreinte_js).items():
        row = cx.execute(
            "SELECT nb_sessions, premiere_vue, derniere_vue, sessions FROM empreintes_vues WHERE type = ? AND hash = ?",
            (type_hash, valeur),
        ).fetchone()
        if row:
            compte, exact = _sessions_derniere_heure(cx, row, maintenant)
            resultats[type_hash] = {
                "nb_sessions": row["nb_sessions"],
                "premiere_vue": row["premiere_vue"],
                "derniere_vue": row["derniere_vue"],
                "sessions_derniere_heure": compte,
                "derniere_heure_exacte": exact,
            }
    return resultats


def _sessions_derniere_heure(cx: sqlite3.Connection, row: sqlite3.Row, maintenant: datetime) -> tuple[int, bool]:
    """Sessions de ce hash commencées dans les 60 dernières minutes, et si ce compte est exact.

    L'heure d'une session est celle de sa première empreinte (`observations_js`). La ligne ne garde que les
    10 derniers jetons (`sessions`, dans l'ordre d'arrivée). Le compte est exact :
    - si la ligne est née dans la fenêtre : toutes ses sessions y sont, c'est `nb_sessions` ;
    - sinon, si le plus ancien jeton gardé est daté d'avant la fenêtre : les sessions oubliées, plus anciennes
      encore, n'y tombent pas.
    Autrement (les 10 jetons gardés tous dans la fenêtre d'une ligne plus ancienne, ou un jeton sans date parce
    que ses observations ont été effacées), c'est une borne basse : la table ne dit pas combien de sessions
    oubliées tombent dans la fenêtre. Avec 10 jetons gardés, cette borne vaut au plus 10.
    """
    debut = maintenant - FENETRE_DEBIT
    if datetime.fromisoformat(row["premiere_vue"]) >= debut:
        return row["nb_sessions"], True
    jetons = json.loads(row["sessions"])
    marques = ", ".join("?" * len(jetons))
    premieres = {
        r[0]: datetime.fromisoformat(r[1])
        for r in cx.execute(
            "SELECT session_token, MIN(received_at) FROM observations_js "
            f"WHERE kind = 'empreinte' AND session_token IN ({marques}) GROUP BY session_token",
            jetons,
        )
    }
    dates = [premieres.get(jeton) for jeton in jetons]
    compte = sum(1 for d in dates if d is not None and d >= debut)
    exact = bool(dates) and None not in dates and dates[0] < debut
    return compte, exact
