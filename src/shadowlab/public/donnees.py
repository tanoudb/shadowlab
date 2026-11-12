"""Base de l'application publique : sessions humaines consenties, observations, suppression et purge.

Même schéma que le laboratoire (`database.MIGRATIONS`), dans un autre fichier. Une base qui contient une
autre expérience que les sessions publiques est refusée : une purge ne doit jamais toucher une campagne.
"""

from __future__ import annotations

import re
import secrets
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

from .. import database as db

EXPERIENCE = "sessions-publiques"
MOTEUR = ("navigateur-public", "n/a", "humain")
SCENARIO = ("navigation_publique", "Navigation libre sur le site vitrine public, après consentement")
JETON = re.compile(r"[0-9a-f]{32}")

# Liste blanche des en-têtes gardés : ceux que lisent les détecteurs, rien d'autre. Ni adresse IP
# (X-Forwarded-For, CF-Connecting-IP, X-Real-IP, Forwarded, True-Client-IP…), ni cookie, ni pays.
ENTETES_GARDES = (
    "host",
    "user-agent",
    "accept",
    "accept-language",
    "accept-encoding",
    "referer",
    "upgrade-insecure-requests",
    "upgrade",
    "dnt",
    "sec-gpc",
    "priority",
    "cache-control",
    "pragma",
    "connection",
    "te",
    "origin",
    "content-type",
    "content-length",
)
PREFIXES_GARDES = ("sec-ch-", "sec-fetch-")
# Bornes d'une requête notée : au pire ~2,4 Ko par ligne, quels que soient les en-têtes envoyés.
TAILLE_MAX_NOM = 64
TAILLE_MAX_VALEUR = 512
ENTETES_MAX = 40
TAILLE_MAX_ENTETES = 2048  # octets du JSON des en-têtes gardés
TAILLE_MAX_METHODE = 16
TAILLE_MAX_CHEMIN = 200
# Adresse interne d'une extension de navigateur (traces d'erreur) : son identifiant peut désigner une personne.
EXTENSION = re.compile(r"\b([a-z][a-z0-9+.-]*-extension)://[^/\s\"'\\)]+", re.I)


def connexion(chemin: Path) -> sqlite3.Connection:
    """Connexion à la base publique ; ce qui est effacé est écrasé sur le disque, pas seulement délié."""
    cx = db.ouvrir(chemin)
    cx.execute("PRAGMA secure_delete=ON")
    return cx


def verifier_base(cx: sqlite3.Connection, chemin: Path) -> None:
    autre = cx.execute("SELECT name FROM experiments WHERE name != ? LIMIT 1", (EXPERIENCE,)).fetchone()
    if autre:
        raise ValueError(
            f"{chemin} n'est pas une base publique : elle contient l'expérience « {autre['name']} ». "
            "Donner à SHADOWLAB_PUBLIC_BASE un fichier à part, jamais la base du laboratoire."
        )


def ouvrir(chemin: Path) -> sqlite3.Connection:
    """Connexion vérifiée : refuse la base du laboratoire."""
    cx = connexion(chemin)
    try:
        verifier_base(cx, chemin)
    except ValueError:
        cx.close()
        raise
    return cx


def taille(chemin: Path) -> int:
    """Octets occupés par la base et son journal WAL."""
    return sum(p.stat().st_size for p in (chemin, chemin.with_name(chemin.name + "-wal")) if p.exists())


# --- Sessions ----------------------------------------------------------------------------------


def _experience(cx: sqlite3.Connection) -> int:
    ligne = cx.execute("SELECT id FROM experiments WHERE name = ?", (EXPERIENCE,)).fetchone()
    if ligne:
        return int(ligne["id"])
    configuration = db.j({"environment": "public", "truth": "humain"})
    return int(
        cx.execute(
            "INSERT INTO experiments (name, description, created_at, configuration, status) VALUES (?, ?, ?, ?, ?)",
            (
                EXPERIENCE,
                "Sessions humaines consenties sur le site public",
                db.maintenant(),
                configuration,
                "permanente",
            ),
        ).lastrowid
    )


def creer_session(cx: sqlite3.Connection, accord: dict) -> str:
    """Passage humain en cours, consentement daté. `accord` garde la version du texte accepté."""
    jeton = secrets.token_hex(16)
    with db.transaction(cx):
        experience = _experience(cx)
        moteur = db.engine_id(cx, *MOTEUR, {})
        scenario = db.scenario_id(cx, *SCENARIO)
        maintenant = db.maintenant()
        cx.execute(
            "INSERT INTO runs (experiment_id, engine_id, scenario_id, repetition, session_token, truth, started_at,"
            " status, consent_at, protection_config) VALUES (?, ?, ?, 1, ?, 'humain', ?, 'en_cours', ?, ?)",
            (experience, moteur, scenario, jeton, maintenant, maintenant, db.j(accord)),
        )
    return jeton


def session_en_cours(cx: sqlite3.Connection, jeton: str, duree_max_s: int) -> bool:
    """Vrai pour une session publique, humaine, consentie, ni terminée ni plus vieille que `duree_max_s`."""
    debut_min = (datetime.now(UTC) - timedelta(seconds=duree_max_s)).isoformat(timespec="milliseconds")
    ligne = cx.execute(
        "SELECT 1 FROM runs r JOIN experiments e ON e.id = r.experiment_id WHERE r.session_token = ? AND e.name = ?"
        " AND r.truth = 'humain' AND r.status = 'en_cours' AND r.consent_at IS NOT NULL AND r.started_at >= ?",
        (jeton, EXPERIENCE, debut_min),
    ).fetchone()
    return ligne is not None


def session_existe(cx: sqlite3.Connection, jeton: str) -> bool:
    """Vrai tant que la session publique est en base (ni supprimée, ni purgée), terminée ou non."""
    ligne = cx.execute(
        "SELECT 1 FROM runs r JOIN experiments e ON e.id = r.experiment_id WHERE r.session_token = ? AND e.name = ?",
        (jeton, EXPERIENCE),
    ).fetchone()
    return ligne is not None


def clore_session(cx: sqlite3.Connection, jeton: str) -> None:
    ligne = cx.execute(
        "SELECT id, started_at FROM runs WHERE session_token = ? AND status = 'en_cours'", (jeton,)
    ).fetchone()
    if ligne is None:
        return
    fin = datetime.now(UTC)
    duree = (fin - datetime.fromisoformat(ligne["started_at"])).total_seconds() * 1000
    cx.execute(
        "UPDATE runs SET status = 'reussi', success = 1, completed_at = ?, duration_ms = ? WHERE id = ?",
        (fin.isoformat(timespec="milliseconds"), round(duree), ligne["id"]),
    )


def sessions_du_jour(cx: sqlite3.Connection) -> int:
    minuit = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0).isoformat(timespec="milliseconds")
    return int(cx.execute("SELECT COUNT(*) FROM runs WHERE started_at >= ?", (minuit,)).fetchone()[0])


# --- Observations ------------------------------------------------------------------------------


def _referent(valeur: str, hote: str) -> str:
    """Un référent du site lui-même se réduit à son chemin ; un référent extérieur n'est pas gardé."""
    try:
        morceaux = urlsplit(valeur)
    except ValueError:
        return "externe"
    return (morceaux.path or "/") if morceaux.netloc.lower() == hote.lower() else "externe"


def entetes_gardes(paires: list[tuple[str, str]], hote: str) -> list[list[str]]:
    """En-têtes de la liste blanche, dans l'ordre reçu : noms, valeurs, nombre et taille totale bornés."""
    gardes: list[list[str]] = []
    taille = 2  # crochets du JSON
    for nom, valeur in paires:
        cle = nom.lower()
        if len(cle) > TAILLE_MAX_NOM or not (cle in ENTETES_GARDES or cle.startswith(PREFIXES_GARDES)):
            continue
        if cle == "referer":
            valeur = _referent(valeur, hote)
        paire = [nom, valeur[:TAILLE_MAX_VALEUR]]
        poids = len(db.j(paire).encode()) + 2  # séparateur « , » compris
        if len(gardes) >= ENTETES_MAX or taille + poids > TAILLE_MAX_ENTETES:
            break
        gardes.append(paire)
        taille += poids
    return gardes


def noter_requete(
    cx: sqlite3.Connection, jeton: str, methode: str, chemin: str, version: str | None, entetes: list, plafond: int
) -> None:
    """Une requête de la session, sans cookie ni chaîne de requête. Au-delà du plafond, plus rien n'est noté."""
    deja = cx.execute("SELECT COUNT(*) FROM observations_http WHERE session_token = ?", (jeton,)).fetchone()[0]
    if deja >= plafond:
        return
    cx.execute(
        "INSERT INTO observations_http (session_token, received_at, method, path, http_version, headers, cookies)"
        " VALUES (?, ?, ?, ?, ?, ?, '[]')",
        (
            jeton,
            db.maintenant(),
            methode[:TAILLE_MAX_METHODE],
            chemin[:TAILLE_MAX_CHEMIN],
            version[:8] if version else None,
            db.j(entetes),
        ),
    )


def masquer_extensions(texte: str) -> str:
    """`chrome-extension://<id>/…` → `chrome-extension://masque/…` (et `moz-`, `safari-web-`… de même)."""
    return EXTENSION.sub(lambda m: f"{m.group(1)}://masque", texte)


def usage(cx: sqlite3.Connection, jeton: str) -> tuple[int, int]:
    """Nombre d'envois JavaScript de la session et leur volume en octets."""
    n, volume = cx.execute(
        "SELECT COUNT(*), COALESCE(SUM(LENGTH(CAST(payload AS BLOB))), 0) FROM observations_js WHERE session_token = ?",
        (jeton,),
    ).fetchone()
    return int(n), int(volume)


def noter_collecte(cx: sqlite3.Connection, jeton: str, kind: str, page: str, charge: str) -> None:
    cx.execute(
        "INSERT INTO observations_js (session_token, received_at, kind, page, payload) VALUES (?, ?, ?, ?, ?)",
        (jeton, db.maintenant(), kind, page, charge),
    )


# --- Suppression et purge ----------------------------------------------------------------------


def effacer_session(cx: sqlite3.Connection, jeton: str) -> bool:
    """Efface la session dans toutes les tables du schéma. Faux si elle n'existait pas."""
    if not JETON.fullmatch(jeton):
        return False
    with db.transaction(cx):
        runs = [(r["id"],) for r in cx.execute("SELECT id FROM runs WHERE session_token = ?", (jeton,))]
        cx.execute(
            "DELETE FROM observations_tls WHERE id IN"
            " (SELECT tls_id FROM observations_http WHERE session_token = ? AND tls_id IS NOT NULL)",
            (jeton,),
        )
        for table in ("observations_http", "observations_js", "decisions"):
            cx.execute(f"DELETE FROM {table} WHERE session_token = ?", (jeton,))
        cx.execute("DELETE FROM empreintes_vues WHERE sessions LIKE ?", (f'%"{jeton}"%',))  # jeton en hexadécimal
        for table in ("fingerprints", "detections", "metrics", "artifacts"):
            cx.executemany(f"DELETE FROM {table} WHERE run_id = ?", runs)
        cx.execute("DELETE FROM runs WHERE session_token = ?", (jeton,))
    return bool(runs)


def purger(cx: sqlite3.Connection, jours: int, maintenant: datetime | None = None) -> int:
    """Efface les sessions publiques commencées il y a plus de `jours` jours. Renvoie leur nombre."""
    limite = ((maintenant or datetime.now(UTC)) - timedelta(days=jours)).isoformat(timespec="milliseconds")
    jetons = [
        r["session_token"]
        for r in cx.execute(
            "SELECT r.session_token FROM runs r JOIN experiments e ON e.id = r.experiment_id"
            " WHERE e.name = ? AND r.started_at < ?",
            (EXPERIENCE, limite),
        )
    ]
    for jeton in jetons:
        effacer_session(cx, jeton)
    return len(jetons)
