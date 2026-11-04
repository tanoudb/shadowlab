"""Cycle de vie d'un passage (une session d'un moteur sur un scénario) dans la base."""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
from typing import Any

from . import database as db
from . import issues
from .detection import Classement, Observations, classer, proprietes

EXPERIENCE_MANUELLE = "sessions-manuelles"


def nouveau_jeton() -> str:
    return secrets.token_hex(16)


def demarrer(
    cx: sqlite3.Connection,
    experiment_id: int,
    engine_id: int,
    scenario_id: int,
    repetition: int,
    truth: str,
    protection: str = "aucune",
    protection_config: str | None = None,
    is_warmup: bool = False,
) -> tuple[int, str]:
    jeton = nouveau_jeton()
    config_hash = hashlib.sha256(protection_config.encode()).hexdigest()[:16] if protection_config else None
    curseur = cx.execute(
        "INSERT INTO runs (experiment_id, engine_id, scenario_id, repetition, session_token, truth, started_at, status,"
        " protection, protection_config, config_hash, is_warmup)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, 'en_cours', ?, ?, ?, ?)",
        (
            experiment_id,
            engine_id,
            scenario_id,
            repetition,
            jeton,
            truth,
            db.maintenant(),
            protection,
            protection_config,
            config_hash,
            int(is_warmup),
        ),
    )
    return int(curseur.lastrowid), jeton


def finaliser(
    cx: sqlite3.Connection,
    run_id: int,
    jeton: str,
    *,
    status: str,
    success: bool | None,
    duration_ms: float | None,
    error: str | None = None,
    motif_echec: str | None = None,
    attend_js: bool = True,
    detecteurs: list[str] | None = None,
    metriques: dict[str, Any] | None = None,
) -> list[Classement]:
    """Classe la session avec les détecteurs, puis enregistre empreinte, verdicts, mesures et fin du passage."""
    http, js = db.observations(cx, jeton)
    decisions = db.decisions_session(cx, jeton)
    obs = Observations(
        http=http,
        js=js,
        attend_js=attend_js,
        tls=db.tls_session(cx, jeton),
        page_remplacee=any(d["decision"] in ("emis", "bloque") for d in decisions),
    )
    classements = classer(obs, detecteurs)
    empreinte = proprietes(obs)
    resultat = issues.evaluer(
        success=success,
        erreur=error if status == "erreur" else None,
        http=http,
        decisions=decisions,
        classements=classements,
        sous_arena=obs.tls is not None,
        motif_echec=motif_echec,
    )
    with db.transaction(cx):
        cx.execute(
            "INSERT OR REPLACE INTO fingerprints (run_id, browser_properties, http_properties, tls_properties,"
            " session_properties) VALUES (?, ?, ?, ?, ?)",
            (
                run_id,
                db.j(empreinte["browser_properties"]),
                db.j(empreinte["http_properties"]),
                db.j(empreinte["tls_properties"]),
                db.j(empreinte["session_properties"]),
            ),
        )
        cx.execute("DELETE FROM detections WHERE run_id = ?", (run_id,))
        for c in classements:
            cx.execute(
                "INSERT INTO detections (run_id, detector_name, detector_version, classification, confidence, signals)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    c.detector_name,
                    c.detector_version,
                    c.classification,
                    c.confidence,
                    db.j([s.en_dict() for s in c.signals]),
                ),
            )
        if metriques is not None:
            cx.execute(
                "INSERT OR REPLACE INTO metrics (run_id, cpu_usage, cpu_time_ms, memory_usage, memory_mean,"
                " navigation_time, request_count, error_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    metriques.get("cpu_usage"),
                    metriques.get("cpu_time_ms"),
                    metriques.get("memory_usage"),
                    metriques.get("memory_mean"),
                    metriques.get("navigation_time"),
                    metriques.get("request_count"),
                    metriques.get("error_count"),
                ),
            )
        cx.execute(
            "UPDATE runs SET completed_at = ?, status = ?, duration_ms = ?, success = ?, error = ?, issue = ?,"
            " cause = ?, drapeaux = ? WHERE id = ?",
            (
                db.maintenant(),
                status,
                duration_ms,
                None if success is None else int(success),
                error,
                resultat.issue,
                resultat.cause,
                db.j(resultat.drapeaux),
                run_id,
            ),
        )
    return classements


def experience_manuelle(cx: sqlite3.Connection) -> int:
    """Expérience permanente qui regroupe les sessions humaines de référence."""
    ligne = cx.execute("SELECT id FROM experiments WHERE name = ?", (EXPERIENCE_MANUELLE,)).fetchone()
    if ligne:
        return int(ligne["id"])
    curseur = cx.execute(
        "INSERT INTO experiments (name, description, created_at, configuration, status) VALUES (?, ?, ?, ?, ?)",
        (
            EXPERIENCE_MANUELLE,
            "Sessions humaines de référence, pour mesurer les faux positifs",
            db.maintenant(),
            db.j({"environment": "local", "truth": "humain"}),
            "permanente",
        ),
    )
    return int(curseur.lastrowid)
