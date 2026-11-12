"""Base SQLite du laboratoire : schéma versionné, migrations et accès courants.

Le site de test (qui reçoit les observations) et le lanceur de campagnes (qui écrit les passages)
partagent le même fichier : mode WAL et délai d'attente pour les écritures concurrentes.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Chaque migration est appliquée une fois, dans l'ordre ; `PRAGMA user_version` garde le numéro atteint.
MIGRATIONS: list[str] = [
    # 1 — schéma initial
    """
    CREATE TABLE experiments (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        configuration TEXT NOT NULL,
        status TEXT NOT NULL,
        seed INTEGER,
        environment TEXT NOT NULL DEFAULT '{}'
    );
    CREATE TABLE engines (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        version TEXT NOT NULL,
        runtime TEXT NOT NULL,
        configuration TEXT NOT NULL,
        UNIQUE (name, version, configuration)
    );
    CREATE TABLE scenarios (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL UNIQUE,
        description TEXT NOT NULL DEFAULT ''
    );
    CREATE TABLE runs (
        id INTEGER PRIMARY KEY,
        experiment_id INTEGER NOT NULL REFERENCES experiments(id) ON DELETE CASCADE,
        engine_id INTEGER NOT NULL REFERENCES engines(id),
        scenario_id INTEGER NOT NULL REFERENCES scenarios(id),
        repetition INTEGER NOT NULL,
        session_token TEXT NOT NULL UNIQUE,
        truth TEXT NOT NULL CHECK (truth IN ('automatise', 'humain')),
        started_at TEXT NOT NULL,
        completed_at TEXT,
        status TEXT NOT NULL,
        duration_ms REAL,
        success INTEGER,
        error TEXT
    );
    CREATE INDEX runs_experiment ON runs(experiment_id);
    CREATE TABLE observations_http (
        id INTEGER PRIMARY KEY,
        session_token TEXT NOT NULL,
        received_at TEXT NOT NULL,
        method TEXT NOT NULL,
        path TEXT NOT NULL,
        http_version TEXT,
        headers TEXT NOT NULL,
        cookies TEXT NOT NULL
    );
    CREATE INDEX observations_http_session ON observations_http(session_token);
    CREATE TABLE observations_js (
        id INTEGER PRIMARY KEY,
        session_token TEXT NOT NULL,
        received_at TEXT NOT NULL,
        kind TEXT NOT NULL,
        page TEXT NOT NULL,
        payload TEXT NOT NULL
    );
    CREATE INDEX observations_js_session ON observations_js(session_token);
    CREATE TABLE fingerprints (
        id INTEGER PRIMARY KEY,
        run_id INTEGER NOT NULL UNIQUE REFERENCES runs(id) ON DELETE CASCADE,
        browser_properties TEXT NOT NULL,
        http_properties TEXT NOT NULL,
        tls_properties TEXT NOT NULL,
        session_properties TEXT NOT NULL
    );
    CREATE TABLE detections (
        id INTEGER PRIMARY KEY,
        run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
        detector_name TEXT NOT NULL,
        detector_version TEXT NOT NULL,
        classification TEXT NOT NULL CHECK (classification IN ('automatise', 'humain', 'indetermine')),
        confidence REAL NOT NULL,
        signals TEXT NOT NULL
    );
    CREATE INDEX detections_run ON detections(run_id);
    CREATE TABLE metrics (
        id INTEGER PRIMARY KEY,
        run_id INTEGER NOT NULL UNIQUE REFERENCES runs(id) ON DELETE CASCADE,
        cpu_usage REAL,
        memory_usage REAL,
        memory_mean REAL,
        navigation_time REAL,
        request_count INTEGER,
        error_count INTEGER
    );
    CREATE TABLE artifacts (
        id INTEGER PRIMARY KEY,
        run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
        artifact_type TEXT NOT NULL,
        file_path TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    """,
    # 2 — temps CPU absolu : un pourcentage seul trompe sur des passages de quelques millisecondes
    """
    ALTER TABLE metrics ADD COLUMN cpu_time_ms REAL;
    """,
    # 3 — Arena : protection du passage, issue détaillée, empreintes TLS, décisions de chaque couche
    """
    ALTER TABLE runs ADD COLUMN protection TEXT NOT NULL DEFAULT 'aucune';
    ALTER TABLE runs ADD COLUMN issue TEXT;
    ALTER TABLE runs ADD COLUMN cause TEXT;
    ALTER TABLE runs ADD COLUMN drapeaux TEXT;
    ALTER TABLE experiments ADD COLUMN serie TEXT;
    ALTER TABLE observations_http ADD COLUMN tls_id INTEGER;
    ALTER TABLE observations_http ADD COLUMN status INTEGER;
    ALTER TABLE observations_http ADD COLUMN source TEXT NOT NULL DEFAULT 'site';
    CREATE TABLE observations_tls (
        id INTEGER PRIMARY KEY,
        received_at TEXT NOT NULL,
        ja3 TEXT NOT NULL,
        ja3_hash TEXT NOT NULL,
        ja4 TEXT NOT NULL,
        details TEXT NOT NULL
    );
    CREATE TABLE decisions (
        id INTEGER PRIMARY KEY,
        session_token TEXT NOT NULL,
        created_at TEXT NOT NULL,
        couche TEXT NOT NULL,
        decision TEXT NOT NULL,
        chemin TEXT NOT NULL DEFAULT '',
        motifs TEXT NOT NULL DEFAULT '[]'
    );
    CREATE INDEX decisions_session ON decisions(session_token);
    CREATE INDEX runs_protection ON runs(experiment_id, protection);
    """,
    # 4 — v0.5 : configuration de protection complète par passage, empreinte SHA-256
    """
    ALTER TABLE runs ADD COLUMN protection_config TEXT;
    ALTER TABLE runs ADD COLUMN config_hash TEXT;
    """,
    # 5 — v0.6 : consentement explicite pour les sessions humaines de référence
    """
    ALTER TABLE runs ADD COLUMN consent_at TEXT;
    """,
    # 6 — v0.6 : marquage des passages de préchauffage (warm-up), exclus des statistiques
    """
    ALTER TABLE runs ADD COLUMN is_warmup INTEGER NOT NULL DEFAULT 0;
    """,
    # 7 — v0.7 : version du moteur sur chaque passage, version du schéma sur chaque expérience
    """
    ALTER TABLE runs ADD COLUMN engine_version TEXT NOT NULL DEFAULT '';
    ALTER TABLE experiments ADD COLUMN schema_version INTEGER;
    """,
    # 8 — corrélation cross-session : hash d'empreinte pour détecter recyclage de fingerprint
    """
    CREATE TABLE empreintes_vues (
        id INTEGER PRIMARY KEY,
        type TEXT NOT NULL,
        hash TEXT NOT NULL,
        premiere_vue TEXT NOT NULL,
        derniere_vue TEXT NOT NULL,
        nb_sessions INTEGER NOT NULL DEFAULT 1,
        sessions TEXT NOT NULL DEFAULT '[]',
        UNIQUE (type, hash)
    );
    CREATE INDEX empreintes_vues_hash ON empreintes_vues(type, hash);
    CREATE INDEX empreintes_vues_nb ON empreintes_vues(nb_sessions DESC);
    """,
    # 9 — passages orphelins : chaque numéro d'expérience porté par des passages reçoit une expérience
    """
    INSERT INTO experiments (id, name, description, created_at, configuration, status, schema_version)
    SELECT experiment_id,
           'orpheline_' || experiment_id,
           'Passages sans campagne retrouvés dans la base. Expérience de remplacement créée par la migration 9 :'
           || ' aucun passage supprimé, la campagne d origine est perdue.',
           MIN(started_at),
           '{"orpheline": true}',
           CASE WHEN SUM(status = 'en_cours') > 0 THEN 'interrompu' ELSE 'termine_incomplet' END,
           9
    FROM runs
    WHERE experiment_id NOT IN (SELECT id FROM experiments)
    GROUP BY experiment_id
    """,
]


SCHEMA_VERSION = len(MIGRATIONS)


# Numéro d'une nouvelle expérience : au-dessus des expériences ET des passages déjà rattachés à un numéro,
# pour qu'un passage orphelin (campagne supprimée hors du lanceur) ne soit jamais hérité par la suivante.
# À placer dans le VALUES d'un INSERT INTO experiments (id, ...) : une seule instruction, donc atomique.
PROCHAIN_ID_EXPERIENCE = (
    "(SELECT MAX(COALESCE((SELECT MAX(id) FROM experiments), 0),"
    " COALESCE((SELECT MAX(experiment_id) FROM runs), 0)) + 1)"
)


def maintenant() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def ouvrir(chemin: Path) -> sqlite3.Connection:
    """Ouvre la base, applique les migrations manquantes, renvoie une connexion prête."""
    chemin.parent.mkdir(parents=True, exist_ok=True)
    connexion = sqlite3.connect(chemin, timeout=30, check_same_thread=False, isolation_level=None)
    connexion.row_factory = sqlite3.Row
    connexion.execute("PRAGMA journal_mode=WAL")
    connexion.execute("PRAGMA foreign_keys=ON")
    connexion.execute("PRAGMA busy_timeout=30000")
    migrer(connexion)
    return connexion


def migrer(connexion: sqlite3.Connection) -> int:
    version = connexion.execute("PRAGMA user_version").fetchone()[0]
    for numero, script in enumerate(MIGRATIONS[version:], start=version + 1):
        with transaction(connexion):
            for instruction in (s.strip() for s in script.split(";")):
                if instruction:
                    connexion.execute(instruction)
            connexion.execute(f"PRAGMA user_version={numero}")
    return len(MIGRATIONS)


@contextmanager
def transaction(connexion: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    connexion.execute("BEGIN IMMEDIATE")
    try:
        yield connexion
    except BaseException:
        connexion.execute("ROLLBACK")
        raise
    connexion.execute("COMMIT")


def j(valeur: Any) -> str:
    return json.dumps(valeur, ensure_ascii=False, sort_keys=True, default=str)


def lj(texte: str | None) -> Any:
    return json.loads(texte) if texte else None


def engine_id(connexion: sqlite3.Connection, name: str, version: str, runtime: str, configuration: dict) -> int:
    cfg = j(configuration)
    connexion.execute(
        "INSERT OR IGNORE INTO engines (name, version, runtime, configuration) VALUES (?, ?, ?, ?)",
        (name, version, runtime, cfg),
    )
    ligne = connexion.execute(
        "SELECT id FROM engines WHERE name = ? AND version = ? AND configuration = ?", (name, version, cfg)
    ).fetchone()
    return int(ligne["id"])


def scenario_id(connexion: sqlite3.Connection, name: str, description: str) -> int:
    connexion.execute(
        "INSERT INTO scenarios (name, description) VALUES (?, ?) "
        "ON CONFLICT(name) DO UPDATE SET description = excluded.description",
        (name, description),
    )
    return int(connexion.execute("SELECT id FROM scenarios WHERE name = ?", (name,)).fetchone()["id"])


def observations(connexion: sqlite3.Connection, jeton: str) -> tuple[list[dict], list[dict]]:
    """Observations HTTP et JavaScript reçues pour une session, dans l'ordre d'arrivée."""
    http = [
        {
            "received_at": r["received_at"],
            "method": r["method"],
            "path": r["path"],
            "http_version": r["http_version"],
            "headers": lj(r["headers"]),
            "cookies": lj(r["cookies"]),
        }
        for r in connexion.execute("SELECT * FROM observations_http WHERE session_token = ? ORDER BY id", (jeton,))
    ]
    js = [
        {"received_at": r["received_at"], "kind": r["kind"], "page": r["page"], "payload": lj(r["payload"])}
        for r in connexion.execute("SELECT * FROM observations_js WHERE session_token = ? ORDER BY id", (jeton,))
    ]
    return http, js


def tls_session(connexion: sqlite3.Connection, jeton: str) -> dict | None:
    """Première empreinte TLS vue pour une session, ou None si elle n'est pas passée par le frontal."""
    ligne = connexion.execute(
        "SELECT t.ja3, t.ja3_hash, t.ja4, t.details FROM observations_http h"
        " JOIN observations_tls t ON t.id = h.tls_id WHERE h.session_token = ? ORDER BY h.id LIMIT 1",
        (jeton,),
    ).fetchone()
    if ligne is None:
        return None
    return {"ja3": ligne["ja3"], "ja3_hash": ligne["ja3_hash"], "ja4": ligne["ja4"], **lj(ligne["details"])}


def decisions_session(connexion: sqlite3.Connection, jeton: str) -> list[dict]:
    return [
        {
            "created_at": r["created_at"],
            "couche": r["couche"],
            "decision": r["decision"],
            "chemin": r["chemin"],
            "motifs": lj(r["motifs"]),
        }
        for r in connexion.execute("SELECT * FROM decisions WHERE session_token = ? ORDER BY id", (jeton,))
    ]


def enregistrer_decision(
    connexion: sqlite3.Connection, jeton: str, couche: str, decision: str, chemin: str = "", motifs: Any = ()
) -> None:
    """Une décision d'une couche de protection, avec ses motifs."""
    connexion.execute(
        "INSERT INTO decisions (session_token, created_at, couche, decision, chemin, motifs) VALUES (?, ?, ?, ?, ?, ?)",
        (jeton, maintenant(), couche, decision, chemin, j(list(motifs))),
    )
