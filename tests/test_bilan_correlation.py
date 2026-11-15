"""Bilan d'un passage : `correlation-session` juge la session comme le gardien l'a jugée (palier 2, I2).

Avant : `passages.finaliser` ne donnait pas `correlation` aux observations, le détecteur répondait toujours
« indéterminé / pas_de_correlation », même quand le gardien avait refusé la session pour cette corrélation.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta

from test_rejeu import empreinte

from shadowlab import campaigns, passages
from shadowlab import database as db
from shadowlab.arena import visiteurs
from shadowlab.campaigns import Experience

DEBUT = datetime(2026, 11, 15, 20, 0, tzinfo=UTC)


def _stamp(instant: datetime) -> str:
    return instant.isoformat(timespec="milliseconds")


def _base() -> sqlite3.Connection:
    cx = sqlite3.connect(":memory:", isolation_level=None)
    cx.row_factory = sqlite3.Row
    db.migrer(cx)
    return cx


def _experience(cx) -> tuple[int, int, int]:
    """L'expérience, le moteur et le scénario du banc d'essai (créés une fois par base)."""
    ligne = cx.execute("SELECT id FROM experiments WHERE name = 'bilan'").fetchone()
    if ligne:
        return (
            ligne["id"],
            db.engine_id(cx, "playwright", "1", "navigateur", {}),
            db.scenario_id(cx, "static_html", "p"),
        )
    experience = Experience(
        name="bilan", engines=["playwright"], scenarios=["static_html"], protections=["06"], repetitions=1
    )
    return (
        campaigns.creer(cx, experience),
        db.engine_id(cx, "playwright", "1", "navigateur", {}),
        db.scenario_id(cx, "static_html", "p"),
    )


def _session(cx, monde: str | None, instant: datetime, n_empreinte: int | None = 0, *, passage: bool = True):
    """Une session telle que l'Arena l'a vue : visite dans son monde, empreinte reçue. Renvoie (run_id, jeton)."""
    if passage:
        exp, moteur, scenario = _experience(cx)
        run_id, jeton = passages.demarrer(cx, exp, moteur, scenario, 1, "automatise", "06", monde=monde)
        cx.execute("UPDATE runs SET started_at = ? WHERE id = ?", (_stamp(instant), run_id))
    else:
        run_id, jeton = 0, f"j{len(cx.execute('SELECT 1 FROM visites').fetchall())}"
    if monde:
        cx.execute(
            "INSERT INTO visites (monde_id, visiteur, session_token, neuve, vue_le) VALUES (?, ?, ?, 1, ?)",
            (visiteurs.identifiant_monde(cx, monde), f"v-{jeton}", jeton, _stamp(instant)),
        )
    if n_empreinte is not None:
        cx.execute(
            "INSERT INTO observations_js (session_token, received_at, kind, page, payload)"
            " VALUES (?, ?, 'empreinte', '/lab/', ?)",
            (jeton, _stamp(instant + timedelta(seconds=1)), db.j(empreinte(n_empreinte))),
        )
    return run_id, jeton


def _bilan(cx, run_id: int, jeton: str) -> dict:
    passages.finaliser(
        cx, run_id, jeton, status="reussi", success=True, duration_ms=None, detecteurs=["correlation-session"]
    )
    ligne = cx.execute(
        "SELECT classification, signals FROM detections WHERE run_id = ? AND detector_name = 'correlation-session'",
        (run_id,),
    ).fetchone()
    return {"classification": ligne["classification"], "codes": [s["code"] for s in json.loads(ligne["signals"])]}


def test_quatre_sessions_neuves_anterieures_de_meme_empreinte_donnent_le_signal():
    cx = _base()
    for n in range(4):
        _session(cx, "m", DEBUT - timedelta(minutes=10 - n))
    run_id, jeton = _session(cx, "m", DEBUT)
    assert "empreinte_sans_memoire" in _bilan(cx, run_id, jeton)["codes"]


def test_premiere_session_d_un_monde_ni_indeterminee_ni_signalee():
    cx = _base()
    run_id, jeton = _session(cx, "m", DEBUT)
    assert _bilan(cx, run_id, jeton) == {"classification": "humain", "codes": []}


def test_session_sans_monde_reste_indeterminee():
    cx = _base()
    run_id, jeton = _session(cx, None, DEBUT)
    assert _bilan(cx, run_id, jeton) == {"classification": "indetermine", "codes": ["pas_de_correlation"]}


def test_une_session_commencee_plus_tard_ne_compte_pas_contre_une_session_anterieure():
    cx = _base()
    run_id, jeton = _session(cx, "m", DEBUT)
    for n in range(6):
        _session(cx, "m", DEBUT + timedelta(minutes=1 + n))
    assert _bilan(cx, run_id, jeton)["codes"] == []


def test_un_autre_monde_ne_compte_pas():
    cx = _base()
    for n in range(6):
        _session(cx, "autre", DEBUT - timedelta(minutes=10 - n))
    run_id, jeton = _session(cx, "m", DEBUT)
    assert _bilan(cx, run_id, jeton)["codes"] == []
