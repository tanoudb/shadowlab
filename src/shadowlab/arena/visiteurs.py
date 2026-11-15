"""Visiteurs et mondes de l'Arena (palier 2, I1).

Un **monde** est un nom : les comptes de l'Arena s'y font, un monde neuf remet tout à zéro. Un **visiteur** est
un cookie `sl_visiteur` (valeur aléatoire signée avec le secret de l'Arena, nom du monde inclus dans la
signature), valable 400 jours, posé sur toute réponse `/lab` du laboratoire. Une **visite** est une session
(un jeton) : la première requête d'une session fixe son visiteur, et la visite est neuve si cette requête
n'apportait pas de visiteur valable dans le monde de la session.

Ce module ne juge rien (I2 s'en servira) : il reconnaît et enregistre. Il n'est jamais branché sur
l'application publique (`public/`), tenue à trois cookies.
"""

from __future__ import annotations

import secrets
import sqlite3
from dataclasses import dataclass
from typing import Literal

from .. import database as db
from . import secret as secrets_arena

COOKIE = "sl_visiteur"
DUREE_S = 400 * 24 * 3600  # la durée maximale que Chrome accorde à un cookie
MONDE_MANUEL = "manuel"  # les sessions humaines de /manuel, jamais partagé avec une campagne
MONDE_HORS_PASSAGE = "hors-passage"  # requête sans jeton, ou jeton qui n'appartient à aucun passage
PORTEES = ("passage", "serie", "campagne")
Portee = Literal["passage", "serie", "campagne"]
USAGE = "visiteur"


@dataclass(frozen=True)
class Visite:
    monde: str
    visiteur: str
    neuve: bool
    cookie: str | None  # valeur à poser dans la réponse ; None si le navigateur porte déjà le bon


def nom_monde(portee: str, experiment_id: int, moteur: str, protection: str, scenario: str, repetition: int) -> str:
    """Nom du monde d'un passage : `campagne` (un par campagne), `serie` (par moteur × niveau) ou `passage`."""
    if portee not in PORTEES:
        raise ValueError(f"portée de monde inconnue : {portee} (attendu : {', '.join(PORTEES)})")
    nom = f"c{experiment_id}"
    if portee == "campagne":
        return nom
    nom = f"{nom}:{moteur}:{protection}"
    return nom if portee == "serie" else f"{nom}:{scenario}:{repetition}"


def creer_cookie(secret: bytes, monde: str, visiteur: str) -> str:
    return f"{visiteur}.{secrets_arena.signer(secret, USAGE, monde, visiteur)}"


def lire_cookie(secret: bytes, monde: str, valeur: str | None) -> str | None:
    """Le visiteur du cookie, ou None s'il est absent, mal formé, falsifié ou signé pour un autre monde."""
    if not valeur or valeur.count(".") != 1:
        return None
    visiteur, signature = valeur.split(".")
    if not visiteur or not signature or not secrets_arena.verifier(secret, signature, USAGE, monde, visiteur):
        return None
    return visiteur


def identifiant_monde(cx: sqlite3.Connection, nom: str) -> int:
    cx.execute("INSERT OR IGNORE INTO mondes (nom, cree_le) VALUES (?, ?)", (nom, db.maintenant()))
    return int(cx.execute("SELECT id FROM mondes WHERE nom = ?", (nom,)).fetchone()["id"])


def monde_de_session(cx: sqlite3.Connection, jeton: str) -> str:
    ligne = cx.execute(
        "SELECT m.nom FROM runs r JOIN mondes m ON m.id = r.monde_id WHERE r.session_token = ?", (jeton,)
    ).fetchone()
    return ligne["nom"] if ligne else MONDE_HORS_PASSAGE


def reconnaitre(cx: sqlite3.Connection, secret: bytes, valeur_cookie: str | None, jeton: str) -> Visite:
    """Reconnaît le visiteur d'une requête et enregistre sa visite (une ligne par session, pas par requête)."""
    monde = monde_de_session(cx, jeton) if jeton else MONDE_HORS_PASSAGE
    monde_id = identifiant_monde(cx, monde)
    porte = lire_cookie(secret, monde, valeur_cookie)
    if jeton:
        connue = cx.execute("SELECT visiteur FROM visites WHERE session_token = ?", (jeton,)).fetchone()
        if connue:  # le visiteur d'une session est celui de sa première requête
            visiteur = connue["visiteur"]
            return Visite(monde, visiteur, False, None if porte == visiteur else creer_cookie(secret, monde, visiteur))
    elif porte:
        return Visite(monde, porte, False, None)
    neuve = porte is None
    visiteur = porte or secrets.token_hex(16)
    cx.execute(
        "INSERT OR IGNORE INTO visites (monde_id, visiteur, session_token, neuve, vue_le) VALUES (?, ?, ?, ?, ?)",
        (monde_id, visiteur, jeton or None, int(neuve), db.maintenant()),
    )
    return Visite(monde, visiteur, neuve, creer_cookie(secret, monde, visiteur) if neuve else None)


class Connus:
    """Coquille : cache des sessions déjà enregistrées (le code vient après les tests)."""

    def __init__(self, maximum: int = 20000) -> None:
        self.maximum = maximum

    def retrouver(self, secret: bytes, valeur_cookie: str | None, jeton: str) -> Visite | None:
        return None

    def retenir(self, jeton: str, visite: Visite) -> None:
        return None
