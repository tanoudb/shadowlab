"""Messages du formulaire de contact : un petit fichier SQLite à part, à côté de la base publique (D-57).

À part pour deux raisons : la base des sessions garde le schéma du laboratoire sans rien y ajouter, et elle
peut être copiée vers le labo pour le rejeu sans emporter des messages où un visiteur a pu écrire son nom
ou son adresse. Un message n'est que son texte et le jour de sa réception : ni adresse IP, ni session, ni
navigateur, ni heure (elle permettrait de le rapprocher des requêtes d'une session en cours).
"""

from __future__ import annotations

import os
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

FICHIER = "messages.sqlite3"
SCHEMA = """CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,  -- jamais réutilisé : un numéro cité ne désigne pas un autre message
    recu_le TEXT NOT NULL,  -- jour UTC, AAAA-MM-JJ
    texte TEXT NOT NULL
)"""
# Caractères invisibles gardés : ils lient les lettres ou les emoji composés et ne changent rien à un terminal.
LIANTS = "\u200c\u200d"


def chemin(base_publique: Path) -> Path:
    """Fichier des messages, à côté de la base des sessions. Refuse une base qui porterait son nom."""
    if base_publique.name == FICHIER:
        raise ValueError(
            f"SHADOWLAB_PUBLIC_BASE ne peut pas s'appeler {FICHIER} : ce nom est réservé aux messages de contact."
        )
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


def _jour(moment: datetime | None = None) -> str:
    return (moment or datetime.now(UTC)).date().isoformat()


def nettoyer(texte: str) -> str:
    """Texte sûr à afficher dans un terminal, par liste blanche : saut de ligne, tabulation, caractères affichables
    (`str.isprintable()`) et les deux liants ; fins de ligne unifiées, espaces particulières (insécables…) changées
    en espaces ordinaires ; tout le reste est retiré (contrôle, mise en forme invisible, sens d'écriture forcé,
    balises, demi-paires, usage privé, non attribué).

    Limite acceptée, prix d'un affichage sûr : un emoji plus récent que la table Unicode de Python (non attribué
    pour elle) disparaît, et un drapeau à balises (Angleterre, Écosse…) perd ses balises et n'est plus qu'un
    drapeau noir. Une liste noire laissait passer d'autres caractères invisibles (U+200B, U+200E, U+FEFF…)."""
    texte = texte.replace("\r\n", "\n").replace("\r", "\n")
    propre = []
    for c in texte:
        if c in "\n\t" or c.isprintable() or c in LIANTS:
            propre.append(c)
        elif c.isspace():
            propre.append(" ")
    return "".join(propre).strip()


def ajouter(cx: sqlite3.Connection, texte: str) -> int:
    return int(cx.execute("INSERT INTO messages (recu_le, texte) VALUES (?, ?)", (_jour(), texte)).lastrowid)


def lister(cx: sqlite3.Connection) -> list[sqlite3.Row]:
    return cx.execute("SELECT id, recu_le, texte FROM messages ORDER BY id").fetchall()


def nombre(cx: sqlite3.Connection) -> int:
    return int(cx.execute("SELECT COUNT(*) FROM messages").fetchone()[0])


def du_jour(cx: sqlite3.Connection) -> int:
    return int(cx.execute("SELECT COUNT(*) FROM messages WHERE recu_le = ?", (_jour(),)).fetchone()[0])


def effacer(cx: sqlite3.Connection, numero: int) -> bool:
    return cx.execute("DELETE FROM messages WHERE id = ?", (numero,)).rowcount > 0


def effacer_tout(cx: sqlite3.Connection) -> int:
    """Vide la boîte (les numéros suivants ne reprennent pas à 1). Renvoie le nombre de messages effacés."""
    return cx.execute("DELETE FROM messages").rowcount


def purger(cx: sqlite3.Connection, jours: int, maintenant: datetime | None = None) -> int:
    """Efface les messages reçus il y a plus de `jours` jours. Renvoie leur nombre."""
    limite = _jour((maintenant or datetime.now(UTC)) - timedelta(days=jours))
    return cx.execute("DELETE FROM messages WHERE recu_le < ?", (limite,)).rowcount
