"""Passages orphelins : numéros d'expérience jamais réutilisés, migration d'adoption des orphelins."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from shadowlab import campaigns, passages
from shadowlab import database as db
from shadowlab.campaigns import Experience

VERSION_AVANT = 8  # dernière migration avant l'adoption des orphelins


def base_ancienne(chemin: Path, experiences: list[int], orphelins: dict[int, list[str]]) -> None:
    """Fabrique une base à la version 8 avec des expériences et des passages orphelins.

    Connexion sans clés étrangères (le réglage par défaut de SQLite) : c'est ainsi qu'un passage peut rester
    sans campagne. `orphelins` associe un numéro d'expérience absente aux statuts de ses passages.
    """
    cx = sqlite3.connect(chemin)
    for script in db.MIGRATIONS[:VERSION_AVANT]:
        for instruction in (s.strip() for s in script.split(";")):
            if instruction:
                cx.execute(instruction)
    cx.execute(f"PRAGMA user_version={VERSION_AVANT}")
    for i in experiences:
        cx.execute(
            "INSERT INTO experiments (id, name, created_at, configuration, status)"
            " VALUES (?, ?, '2026-11-01T10:00:00.000+00:00', '{}', 'termine')",
            (i, f"campagne_{i}"),
        )
    cx.execute(
        "INSERT INTO engines (id, name, version, runtime, configuration) VALUES (1, 'playwright', '1', 'py', '{}')"
    )
    cx.execute("INSERT INTO scenarios (id, name) VALUES (1, 'static_html')")
    n = 0
    for numero, statuts in orphelins.items():
        for k, statut in enumerate(statuts):
            n += 1
            cx.execute(
                "INSERT INTO runs (experiment_id, engine_id, scenario_id, repetition, session_token, truth,"
                " started_at, status, protection) VALUES (?, 1, 1, ?, ?, 'automatise', ?, ?, '05')",
                (numero, k, f"jeton-{n}", f"2026-11-08T18:3{k}:00.000+00:00", statut),
            )
    cx.commit()
    cx.close()


def experience(nom: str = "nouvelle") -> Experience:
    return Experience(name=nom, engines=["httpx"], scenarios=["static_html"], repetitions=1, detectors=[], seed=1)


def test_orphelins_adoptes_sans_rien_supprimer(tmp_path):
    chemin = tmp_path / "b.sqlite3"
    base_ancienne(chemin, [1, 2, 3], {99: ["en_cours", "en_cours", "reussi"]})
    cx = db.ouvrir(chemin)
    assert cx.execute("SELECT COUNT(*) FROM runs WHERE experiment_id = 99").fetchone()[0] == 3
    ligne = cx.execute("SELECT * FROM experiments WHERE id = 99").fetchone()
    assert ligne["name"] == "orpheline_99"
    assert ligne["status"] == "interrompu"
    assert ligne["created_at"] == "2026-11-08T18:30:00.000+00:00"
    assert "sans campagne" in ligne["description"]
    assert (
        cx.execute("SELECT COUNT(*) FROM runs WHERE experiment_id NOT IN (SELECT id FROM experiments)").fetchone()[0]
        == 0
    )
    assert cx.execute("SELECT COUNT(*) FROM experiments").fetchone()[0] == 4
    assert cx.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION


def test_campagne_suivante_prend_un_numero_neuf(tmp_path):
    chemin = tmp_path / "b.sqlite3"
    base_ancienne(chemin, [1, 2, 3], {99: ["en_cours"]})
    cx = db.ouvrir(chemin)
    nouveau = campaigns.creer(cx, experience())
    assert nouveau == 100
    assert cx.execute("SELECT COUNT(*) FROM runs WHERE experiment_id = ?", (nouveau,)).fetchone()[0] == 0


def test_numero_neuf_meme_sans_migration(tmp_path):
    """Un orphelin apparu après la migration ne se laisse pas hériter non plus."""
    cx = db.ouvrir(tmp_path / "b.sqlite3")
    campaigns.creer(cx, experience("premiere"))
    cx.execute("PRAGMA foreign_keys=OFF")
    cx.execute("DELETE FROM experiments WHERE id = 1")
    cx.execute("INSERT INTO engines (id, name, version, runtime, configuration) VALUES (1, 'httpx', '1', 'py', '{}')")
    cx.execute("INSERT INTO scenarios (id, name) VALUES (1, 'static_html')")
    cx.execute(
        "INSERT INTO runs (experiment_id, engine_id, scenario_id, repetition, session_token, truth, started_at,"
        " status) VALUES (7, 1, 1, 0, 'x', 'automatise', '2026-11-08T18:30:00.000+00:00', 'en_cours')"
    )
    assert campaigns.creer(cx, experience("seconde")) == 8
    assert passages.experience_manuelle(cx) == 9


def test_base_sans_orphelin_inchangee(tmp_path):
    chemin = tmp_path / "b.sqlite3"
    base_ancienne(chemin, [1, 2, 3], {})
    cx = db.ouvrir(chemin)
    assert [r["id"] for r in cx.execute("SELECT id FROM experiments ORDER BY id")] == [1, 2, 3]
    assert cx.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0
