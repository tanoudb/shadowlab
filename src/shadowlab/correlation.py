"""Corrélation cross-session : détecte le recyclage de fingerprints entre sessions.

Un bot qui réutilise le même profil navigateur produit des hash identiques (canvas, profil,
audio). Ce module enregistre les hash observés et signale les sessions dont l'empreinte
a déjà été vue trop souvent.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime

from . import database as db


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
    """Retourne les données de corrélation pour une empreinte."""
    hashes = hash_session(empreinte_js)
    resultats: dict[str, dict] = {}
    for type_hash, valeur in hashes.items():
        row = cx.execute(
            "SELECT nb_sessions, premiere_vue, derniere_vue FROM empreintes_vues WHERE type = ? AND hash = ?",
            (type_hash, valeur),
        ).fetchone()
        if row:
            premiere = datetime.fromisoformat(row["premiere_vue"])
            derniere = datetime.fromisoformat(row["derniere_vue"])
            duree_minutes = max((derniere - premiere).total_seconds() / 60.0, 0.001)
            resultats[type_hash] = {
                "nb_sessions": row["nb_sessions"],
                "premiere_vue": row["premiere_vue"],
                "derniere_vue": row["derniere_vue"],
                "sessions_par_heure": round(row["nb_sessions"] / (duree_minutes / 60.0), 1) if duree_minutes > 1 else 0,
            }
    return resultats
