"""Visiteurs et mondes (palier 2, I1) : cookie `sl_visiteur`, migration 10, champ `monde` des campagnes."""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from shadowlab import campaigns, passages
from shadowlab import database as db
from shadowlab.arena import visiteurs
from shadowlab.campaigns import Experience
from shadowlab.config import ReglagesPublics
from shadowlab.public import Limites, creer_app_publique

COOKIE = "sl_visiteur"
QUATRE_CENTS_JOURS = 400 * 24 * 3600


def nouvelle_experience(reglages, nom: str, **champs) -> int:
    experience = Experience(
        name=nom, engines=["playwright"], scenarios=["static_html"], repetitions=3, protections=["01"], **champs
    )
    cx = db.ouvrir(reglages.base_donnees)
    try:
        return campaigns.creer(cx, experience, reglages)
    finally:
        cx.close()


def nouveau_passage(reglages, experiment_id: int, repetition: int = 1, monde: str | None = None) -> str:
    cx = db.ouvrir(reglages.base_donnees)
    try:
        moteur = db.engine_id(cx, "playwright", "1", "navigateur", {})
        scenario = db.scenario_id(cx, "static_html", "page statique")
        return passages.demarrer(
            cx, experiment_id, moteur, scenario, repetition, "automatise", "01", monde=monde or f"c{experiment_id}"
        )[1]
    finally:
        cx.close()


def lignes(reglages, requete: str, *parametres) -> list[sqlite3.Row]:
    cx = db.ouvrir(reglages.base_donnees)
    try:
        return cx.execute(requete, parametres).fetchall()
    finally:
        cx.close()


def valeur_cookie(reponse) -> str | None:
    for entete in reponse.headers.get_list("set-cookie"):
        if entete.startswith(f"{COOKIE}="):
            return entete.split(";", 1)[0].split("=", 1)[1]
    return None


# --- Migration 10 ------------------------------------------------------------------------------------------


def test_migration_10_sur_base_neuve(tmp_path):
    cx = db.ouvrir(tmp_path / "neuve.sqlite3")
    assert cx.execute("PRAGMA user_version").fetchone()[0] == 10
    tables = {r["name"] for r in cx.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"mondes", "visites", "bannissements"} <= tables
    assert cx.execute("SELECT COUNT(*) FROM bannissements").fetchone()[0] == 0


def test_migration_10_sur_base_au_schema_9(tmp_path):
    chemin = tmp_path / "ancienne.sqlite3"
    cx = sqlite3.connect(chemin, isolation_level=None)
    for script in db.MIGRATIONS[:9]:
        for instruction in (s.strip() for s in script.split(";")):
            if instruction:
                cx.execute(instruction)
    cx.execute("PRAGMA user_version=9")
    cx.execute(
        "INSERT INTO experiments (id, name, created_at, configuration, status)"
        " VALUES (1, 'avant', '2026-11-01T10:00:00.000+00:00', '{}', 'termine')"
    )
    cx.close()
    cx = db.ouvrir(chemin)
    assert cx.execute("PRAGMA user_version").fetchone()[0] == 10
    assert cx.execute("SELECT name FROM experiments").fetchone()["name"] == "avant"
    tables = {r["name"] for r in cx.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"mondes", "visites", "bannissements"} <= tables


def test_migration_9_inchangee():
    assert len(db.MIGRATIONS) == 10
    assert "orpheline_" in db.MIGRATIONS[8]  # la 9 reste celle de D-68


# --- Cookie posé par le labo -------------------------------------------------------------------------------


def test_cookie_pose_sans_jeton(client):
    r = client.get("/lab/")
    entete = next(e for e in r.headers.get_list("set-cookie") if e.startswith(f"{COOKIE}="))
    assert valeur_cookie(r)
    assert f"Max-Age={QUATRE_CENTS_JOURS}" in entete
    assert "HttpOnly" in entete and "Path=/" in entete


def test_cookie_non_repose_quand_il_est_valable(client):
    client.get("/lab/")
    assert valeur_cookie(client.get("/lab/")) is None


def test_deux_jetons_du_meme_client_un_seul_visiteur(client, reglages):
    exp = nouvelle_experience(reglages, "meme-client")
    a, b = nouveau_passage(reglages, exp, 1), nouveau_passage(reglages, exp, 2)
    client.get(f"/lab/?sl={a}")
    client.get(f"/lab/?sl={b}")
    visites = lignes(reglages, "SELECT visiteur, neuve, session_token FROM visites ORDER BY id")
    assert [v["session_token"] for v in visites] == [a, b]
    assert visites[0]["visiteur"] == visites[1]["visiteur"]
    assert [v["neuve"] for v in visites] == [1, 0]


def test_une_visite_par_session_pas_par_requete(client, reglages):
    exp = nouvelle_experience(reglages, "une-visite")
    a = nouveau_passage(reglages, exp)
    for _ in range(3):
        client.get(f"/lab/?sl={a}")
    assert len(lignes(reglages, "SELECT id FROM visites WHERE session_token = ?", a)) == 1


def test_cookie_falsifie_donne_un_visiteur_neuf(client, reglages):
    exp = nouvelle_experience(reglages, "falsifie")
    a, b = nouveau_passage(reglages, exp, 1), nouveau_passage(reglages, exp, 2)
    client.get(f"/lab/?sl={a}")
    vrai = client.cookies.get(COOKIE)
    client.cookies.set(COOKIE, vrai[:-4] + "0000" if vrai[-4:] != "0000" else vrai[:-4] + "1111")
    r = client.get(f"/lab/?sl={b}")
    assert valeur_cookie(r) and valeur_cookie(r) != vrai
    assert [v["neuve"] for v in lignes(reglages, "SELECT neuve FROM visites ORDER BY id")] == [1, 1]


def test_cookie_d_un_autre_monde_donne_un_visiteur_neuf(client, reglages):
    a = nouveau_passage(reglages, nouvelle_experience(reglages, "monde-a"))
    b = nouveau_passage(reglages, nouvelle_experience(reglages, "monde-b"))
    client.get(f"/lab/?sl={a}")
    cookie_a = client.cookies.get(COOKIE)
    r = client.get(f"/lab/?sl={b}")
    assert valeur_cookie(r) and valeur_cookie(r) != cookie_a
    visites = lignes(reglages, "SELECT visiteur, neuve, monde_id FROM visites ORDER BY id")
    assert visites[0]["visiteur"] != visites[1]["visiteur"]
    assert visites[1]["neuve"] == 1 and visites[0]["monde_id"] != visites[1]["monde_id"]


def test_la_signature_porte_le_nom_du_monde():
    secret = b"secret-d-essai"
    cookie = visiteurs.creer_cookie(secret, "monde-a", "abcdef0123456789abcdef0123456789")
    assert visiteurs.lire_cookie(secret, "monde-a", cookie) == "abcdef0123456789abcdef0123456789"
    assert visiteurs.lire_cookie(secret, "monde-b", cookie) is None
    assert visiteurs.lire_cookie(b"autre-secret", "monde-a", cookie) is None
    for mauvais in (None, "", "sans-point", ".", "a.b", cookie + "x"):
        assert visiteurs.lire_cookie(secret, "monde-a", mauvais) is None


def test_duree_du_cookie():
    assert visiteurs.DUREE_S == QUATRE_CENTS_JOURS


# --- Mondes ------------------------------------------------------------------------------------------------


def test_champ_monde_enregistre_avec_la_configuration(reglages):
    exp = nouvelle_experience(reglages, "avec-monde", monde="serie")
    config = lignes(reglages, "SELECT configuration FROM experiments WHERE id = ?", exp)[0]["configuration"]
    assert Experience.model_validate_json(config).monde == "serie"
    assert Experience(name="x", engines=["playwright"], scenarios=["static_html"], repetitions=1).monde == "campagne"
    with pytest.raises(ValueError):
        Experience(name="x", engines=["playwright"], scenarios=["static_html"], repetitions=1, monde="inconnu")


def test_noms_de_monde_par_portee():
    assert visiteurs.nom_monde("campagne", 7, "m", "05", "s", 2) == "c7"
    assert visiteurs.nom_monde("serie", 7, "m", "05", "s", 2) == "c7:m:05"
    assert visiteurs.nom_monde("passage", 7, "m", "05", "s", 2) == "c7:m:05:s:2"


def test_le_passage_enregistre_son_monde(reglages):
    exp = nouvelle_experience(reglages, "monde-passage")
    nouveau_passage(reglages, exp, monde="c1:playwright:01")
    ligne = lignes(reglages, "SELECT m.nom FROM runs r JOIN mondes m ON m.id = r.monde_id")[0]
    assert ligne["nom"] == "c1:playwright:01"


def test_manuel_a_son_monde_a_part(client, reglages):
    r = client.post("/manuel/commencer", content="protection=01&consentement=oui")
    assert r.status_code in (200, 303)
    nom = lignes(reglages, "SELECT m.nom FROM runs r JOIN mondes m ON m.id = r.monde_id WHERE r.truth = 'humain'")
    assert [n["nom"] for n in nom] == [visiteurs.MONDE_MANUEL]


# --- L'application publique n'en pose pas ------------------------------------------------------------------


def test_application_publique_sans_cookie_visiteur(tmp_path):
    reglages = ReglagesPublics(
        hotes=("vitrine.test",),
        contact="Responsable de test",
        conservation_jours=90,
        https=True,
        port=8771,
        base_donnees=tmp_path / "public" / "public.sqlite3",
        entete_ip="X-Forwarded-For",
        vitrine_graine=20261111,
        vitrine_taille=45,
        vitrine=True,
    )
    app = creer_app_publique(reglages, replace(Limites()))
    with TestClient(app, base_url="https://vitrine.test") as c:
        for chemin in ("/fr", "/en", "/lab/social/", "/lab/vitrine/"):
            r = c.get(chemin, follow_redirects=True)
            assert COOKIE not in "".join(r.headers.get_list("set-cookie")), chemin
        assert COOKIE not in c.cookies
    assert Path(reglages.base_donnees).exists()
