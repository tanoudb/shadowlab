"""Messages du formulaire de contact : un petit fichier SQLite à part, à côté de la base publique (D-57).

À part pour deux raisons : la base des sessions garde le schéma du laboratoire sans rien y ajouter, et elle
peut être copiée vers le labo pour le rejeu sans emporter des messages où un visiteur a pu écrire son nom
ou son adresse. Un message n'est que son texte et sa date : ni adresse IP, ni session, ni navigateur.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

FICHIER = "messages.sqlite3"
SCHEMA = """CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,  -- jamais réutilisé : un numéro cité ne désigne pas un autre message
    recu_le TEXT NOT NULL,
    texte TEXT NOT NULL
)"""


def chemin(base_publique: Path) -> Path:
    return base_publique.with_name(FICHIER)


def connexion(fichier: Path) -> sqlite3.Connection:
    """Ouvre la boîte (créée au besoin, droits 600) ; ce qui est effacé est écrasé sur le disque."""
    fichier.parent.mkdir(parents=True, exist_ok=True)
    nouveau = not fichier.exists()
    cx = sqlite3.connect(fichier, timeout=30, check_same_thread=False, isolation_level=None)
    cx.row_factory = sqlite3.Row
    cx.execute("PRAGMA secure_delete=ON")
    cx.execute(SCHEMA)
    if nouveau:
        os.chmod(fichier, 0o600)
    return cx


def _instant(moment: datetime | None = None) -> str:
    return (moment or datetime.now(UTC)).isoformat(timespec="milliseconds")


def nettoyer(texte: str) -> str:
    """Fins de ligne unifiées ; aucun caractère de contrôle ni de mise en forme invisible (séquences de
    terminal, sens d'écriture forcé), pour que le texte s'affiche sans risque dans un terminal."""
    texte = texte.replace("\r\n", "\n").replace("\r", "\n")
    return "".join(c for c in texte if c in "\n\t" or c.isprintable()).strip()


def ajouter(cx: sqlite3.Connection, texte: str) -> int:
    return int(cx.execute("INSERT INTO messages (recu_le, texte) VALUES (?, ?)", (_instant(), texte)).lastrowid)


def lister(cx: sqlite3.Connection) -> list[sqlite3.Row]:
    return cx.execute("SELECT id, recu_le, texte FROM messages ORDER BY id").fetchall()


def nombre(cx: sqlite3.Connection) -> int:
    return int(cx.execute("SELECT COUNT(*) FROM messages").fetchone()[0])


def du_jour(cx: sqlite3.Connection) -> int:
    minuit = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    return int(cx.execute("SELECT COUNT(*) FROM messages WHERE recu_le >= ?", (_instant(minuit),)).fetchone()[0])


def effacer(cx: sqlite3.Connection, numero: int) -> bool:
    return cx.execute("DELETE FROM messages WHERE id = ?", (numero,)).rowcount > 0


def purger(cx: sqlite3.Connection, jours: int, maintenant: datetime | None = None) -> int:
    """Efface les messages reçus il y a plus de `jours` jours. Renvoie leur nombre."""
    limite = _instant((maintenant or datetime.now(UTC)) - timedelta(days=jours))
    return cx.execute("DELETE FROM messages WHERE recu_le < ?", (limite,)).rowcount
