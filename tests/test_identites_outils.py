"""Étape 4.2 : les fichiers de l'essai et de la preuve de 1 000 pages, le guetteur du bannissement, le bilan.

Aucun navigateur, aucune Arena. Ce que ces tests établissent :
- les deux campagnes (`identites-essai.yaml`, `identites-1000.yaml`) se lisent, ont trois identités neuves qui se
  partagent une récolte, et leur rythme reste sous les règles de l'Arena (240 pages comptées par heure et par visiteur,
  30 sessions par heure de la même empreinte) ;
- `scripts/identites-bannir-en-visite.sh` bannit le visiteur de LA visite voulue du bras voulu (pas celui d'une autre
  identité du même monde), une fois, et n'écrit rien si la visite finit avant ;
- `scripts/identites-bilan.py` lit les deux bases et dit, par critère, ce qui est tenu : toutes les pages, champs
  exacts, rien de demandé après le premier refus d'une identité bannie.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml
from outils_identites import PiloteIdentite, parcours_partage
from outils_recolte import GRAINE, creer_client

from shadowlab import campaigns
from shadowlab import database as db
from shadowlab.arena import visiteurs

RACINE = Path(__file__).resolve().parents[1]
EXPERIENCES = RACINE / "configs" / "experiments"
ESSAI = EXPERIENCES / "identites-essai.yaml"
PREUVE = EXPERIENCES / "identites-1000.yaml"
GUETTEUR = RACINE / "scripts" / "identites-bannir-en-visite.sh"
BILAN = RACINE / "scripts" / "identites-bilan.py"
PAGES_COMPTEES_PAR_VISITE = 25  # environ 25 pages comptées par l'Arena pour 15 lues (D-78, consigne de l'étape)
DUREE_VISITE_MIN = 2  # une visite de 15 pages dure environ 2 minutes


@pytest.mark.parametrize("fichier", [ESSAI, PREUVE])
def test_les_campagnes_se_lisent_et_restent_sous_les_regles_de_l_arena(fichier, reglages):
    e = campaigns.lire(fichier, reglages)
    bras = [m for m in e.engines if m.recolte_partagee]
    assert len(bras) == 3 and len({m.recolte_partagee for m in bras}) == 1
    assert len({m.options["identite"] for m in bras}) == 3
    assert e.monde == "campagne" and e.protections == ["endurance"] and e.espacement.mode == "fixe"
    visites_par_heure = 60 / (e.espacement.minutes + DUREE_VISITE_MIN)
    assert visites_par_heure * PAGES_COMPTEES_PAR_VISITE * e.pages_par_visite / 15 < 240
    assert visites_par_heure * len(bras) < 30


def test_les_identites_des_deux_campagnes_sont_neuves(reglages):
    noms = {}
    for fichier in (ESSAI, PREUVE):
        for m in campaigns.lire(fichier, reglages).engines:
            noms[m.options["identite"]] = fichier.name
    assert len(noms) == 6  # aucune identité commune à l'essai et à la preuve
    for autre in EXPERIENCES.glob("*.yaml"):
        if autre in (ESSAI, PREUVE):
            continue
        texte = autre.read_text(encoding="utf-8")
        assert not [n for n in noms if n in texte], autre.name


def test_la_preuve_vise_1000_pages(reglages):
    texte = PREUVE.read_text(encoding="utf-8")
    assert "SHADOWLAB_VITRINE_TAILLE=952" in texte
    from shadowlab.site import vitrine

    assert vitrine.nb_pages(952) + 952 == 1000  # 48 pages de liste et 952 fiches


# ── Le guetteur ──────────────────────────────────────────────────────────────────────────────────


def _campagne(reglages):
    cx = db.ouvrir(reglages.base_donnees)
    experiment_id = campaigns.creer(cx, campaigns.lire(ESSAI, reglages), reglages)
    return cx, experiment_id


def _passage(cx, experiment_id, bras, repetition, visiteur, *, statut="en_cours", depuis_s=120):
    moteur = db.engine_id(cx, "noezia", "1", "navigateur", {"label": bras})
    scenario = db.scenario_id(cx, "visite", "visite")
    jeton = f"jeton-{bras}-{repetition}"
    debut = (datetime.now(UTC) - timedelta(seconds=depuis_s)).isoformat(timespec="milliseconds")
    cx.execute(
        "INSERT INTO runs (experiment_id, engine_id, scenario_id, repetition, session_token, truth, started_at, status,"
        " success, protection) VALUES (?, ?, ?, ?, ?, 'automatise', ?, ?, 0, 'endurance')",
        (experiment_id, moteur, scenario, repetition, jeton, debut, statut),
    )
    monde = visiteurs.identifiant_monde(cx, f"c{experiment_id}")
    cx.execute(
        "INSERT INTO visites (monde_id, visiteur, session_token, neuve, vue_le) VALUES (?, ?, ?, 0, ?)",
        (monde, visiteur, jeton, debut),
    )
    return jeton


def _guetter(reglages, *args):
    env = {**os.environ, "SHADOWLAB_BASE": str(reglages.base_donnees)}
    return subprocess.run(
        [str(GUETTEUR), *map(str, args)], capture_output=True, text=True, env=env, timeout=120, check=False
    )


def test_le_guetteur_bannit_le_visiteur_de_la_visite_voulue_du_bras_voulu(reglages):
    cx, n = _campagne(reglages)
    _passage(cx, n, "ident-a", 2, "visiteur-a")  # même monde, même visite : une autre identité
    _passage(cx, n, "ident-b", 1, "visiteur-b", statut="reussi")
    _passage(cx, n, "ident-b", 2, "visiteur-b")
    resultat = _guetter(reglages, n, "ident-b", 2, 60)
    assert resultat.returncode == 0, resultat.stderr
    lignes = cx.execute("SELECT visiteur, motif FROM bannissements").fetchall()
    assert [tuple(r) for r in lignes] == [("visiteur-b", "manuel")]


def test_le_guetteur_n_ecrit_rien_si_la_campagne_finit_avant(reglages):
    cx, n = _campagne(reglages)
    _passage(cx, n, "ident-b", 2, "visiteur-b", statut="reussi", depuis_s=10)
    cx.execute("UPDATE experiments SET status = 'termine' WHERE id = ?", (n,))
    resultat = _guetter(reglages, n, "ident-b", 2, 60)
    assert resultat.returncode == 1
    assert cx.execute("SELECT COUNT(*) FROM bannissements").fetchone()[0] == 0


def test_le_guetteur_passe_une_visite_trop_courte_et_bannit_la_suivante(reglages):
    """Une visite qui finit avant le délai (visite vide du départ : rien à prendre) n'arrête pas le guetteur : il bannit
    pendant la première visite du bras, à partir de la n-ième, qui dure assez."""
    cx, n = _campagne(reglages)
    cx.execute("UPDATE experiments SET status = 'en_cours' WHERE id = ?", (n,))
    _passage(cx, n, "ident-b", 1, "visiteur-b", statut="echoue", depuis_s=300)  # vide, finie en quelques secondes
    _passage(cx, n, "ident-b", 2, "visiteur-b", depuis_s=90)
    resultat = _guetter(reglages, n, "ident-b", 1, 60)
    assert resultat.returncode == 0, resultat.stderr
    assert [tuple(r) for r in cx.execute("SELECT visiteur, motif FROM bannissements")] == [("visiteur-b", "manuel")]
    assert "visite 2" in resultat.stdout


def test_le_guetteur_refuse_une_campagne_inconnue(reglages):
    db.ouvrir(reglages.base_donnees)
    assert _guetter(reglages, 999, "ident-b", 1, 60).returncode == 2


def test_le_guetteur_refuse_des_arguments_douteux(reglages):
    assert _guetter(reglages, "1;DROP", "ident-b", 2, 60).returncode == 2
    assert _guetter(reglages, 1, "ident-b' OR '1", 2, 60).returncode == 2


# ── Le bilan ─────────────────────────────────────────────────────────────────────────────────────


def _recolte_partagee(reglages, monkeypatch, n, *, bannir_b=True):
    """Deux identités font toute la vitrine (45 annonces) dans le dossier que la campagne n° n lui donnerait ; l'une est
    bannie à sa 3e page si `bannir_b`."""
    dossier = reglages.sorties / "campagnes" / str(n) / "recolte" / "vitrine-partagee-endurance"
    with creer_client(monkeypatch) as site:
        parcours_partage(dossier, PiloteIdentite(site, "partage-a-x")).visiter_partage("partage-a-x", 5)
        if bannir_b:
            pilote = PiloteIdentite(site, "partage-b-x", bannir_a=3)
            parcours_partage(dossier, pilote).visiter_partage("partage-b-x", 10)
        for _ in range(20):
            bilan = parcours_partage(dossier, PiloteIdentite(site, "partage-a-x")).visiter_partage("partage-a-x", 15)
            if bilan.statut == "terminee":
                break
    return dossier


def _bilan(reglages, n):
    env = {
        **os.environ,
        "SHADOWLAB_BASE": str(reglages.base_donnees),
        "SHADOWLAB_SORTIES": str(reglages.sorties),
        "SHADOWLAB_VITRINE_TAILLE": "45",
        "SHADOWLAB_VITRINE_GRAINE": str(GRAINE),
    }
    resultat = subprocess.run(
        [sys.executable, str(BILAN), str(n), "--json"],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
        check=False,
    )
    return resultat.returncode, json.loads(resultat.stdout) if resultat.stdout else None, resultat.stderr


def _observation(cx, jeton, chemin, quand):
    cx.execute(
        "INSERT INTO observations_http (session_token, received_at, method, path, headers, cookies)"
        " VALUES (?, ?, 'GET', ?, '{}', '{}')",
        (jeton, quand, chemin),
    )


def test_le_bilan_dit_ce_qui_est_tenu(reglages, monkeypatch):
    cx, n = _campagne(reglages)
    _recolte_partagee(reglages, monkeypatch, n)
    jeton = _passage(cx, n, "ident-b", 2, "visiteur-b", statut="echec")
    t0 = datetime.now(UTC) - timedelta(seconds=60)  # la décision du refus est écrite « maintenant »
    quand = lambda s: (t0 + timedelta(seconds=s)).isoformat(timespec="milliseconds")  # noqa: E731
    _observation(cx, jeton, "/lab/vitrine/annonces/AN-000001?sl=x", quand(0))
    monde = visiteurs.identifiant_monde(cx, f"c{n}")
    cx.execute(
        "INSERT INTO bannissements (monde_id, visiteur, motif, cree_le) VALUES (?, 'visiteur-b', 'manuel', ?)",
        (monde, quand(1)),
    )
    _observation(cx, jeton, "/lab/vitrine/annonces/AN-000002?sl=x", quand(2))  # la page refusée
    db.enregistrer_decision(cx, jeton, "bannissement", "bloque", "/lab/vitrine/annonces/AN-000002", [])
    code, bilan, erreur = _bilan(reglages, n)
    assert bilan is not None, erreur
    c = bilan["criteres"]
    assert c["toutes_les_pages"] and c["champs_exacts"] and c["passe_terminee"]
    assert c["un_bannissement_au_moins"] and c["rien_apres_le_premier_refus"]
    b = bilan["bannissements"][0]
    assert b["documents_apres_bannissement"] == ["/lab/vitrine/annonces/AN-000002?sl=x"]
    assert b["documents_apres_le_premier_refus"] == []
    assert bilan["recolte"]["pages_par_identite"]["partage-b-x"]["lues"] == 2
    assert [r["identite"] for r in bilan["recolte"]["rendues"]] == ["partage-b-x"]
    assert code == 0
    # une page demandée après le refus : le critère tombe
    _observation(
        cx, jeton, "/lab/vitrine/annonces/AN-000003?sl=x", (datetime.now(UTC) + timedelta(seconds=5)).isoformat()
    )
    code, bilan, _ = _bilan(reglages, n)
    assert code == 1 and bilan["criteres"]["rien_apres_le_premier_refus"] is False


def test_le_bilan_dit_si_les_identites_ont_partage_un_visiteur(reglages, monkeypatch):
    """Rien de partagé, lu dans la base du labo : chaque identité (bras) garde UN visiteur de l'Arena d'une visite à
    l'autre (son profil Chrome, son cookie), et deux identités n'ont jamais le même."""
    cx, n = _campagne(reglages)
    _recolte_partagee(reglages, monkeypatch, n, bannir_b=False)
    _passage(cx, n, "ident-a", 1, "visiteur-a", statut="reussi")
    _passage(cx, n, "ident-a", 2, "visiteur-a", statut="reussi")
    _passage(cx, n, "ident-b", 1, "visiteur-b", statut="reussi")
    _, bilan, erreur = _bilan(reglages, n)
    assert bilan is not None, erreur
    assert bilan["criteres"]["un_visiteur_par_identite"] and bilan["criteres"]["visiteurs_tous_differents"]
    assert bilan["visiteurs_par_bras"] == {"ident-a": ["visiteur-a"], "ident-b": ["visiteur-b"]}
    _passage(cx, n, "ident-c", 1, "visiteur-a", statut="reussi")  # le cookie de ident-a chez ident-c
    _passage(cx, n, "ident-b", 2, "visiteur-b2", statut="reussi")  # ident-b a perdu son visiteur
    code, bilan, _ = _bilan(reglages, n)
    assert code == 1
    assert bilan["criteres"]["un_visiteur_par_identite"] is False
    assert bilan["criteres"]["visiteurs_tous_differents"] is False


def test_le_bilan_sans_recolte_rend_2(reglages):
    _, n = _campagne(reglages)
    code, _, erreur = _bilan(reglages, n)
    assert code == 2 and "récolte introuvable" in erreur


def test_le_fichier_de_l_essai_annonce_le_guetteur_et_le_bilan():
    texte = ESSAI.read_text(encoding="utf-8")
    assert "scripts/identites-bannir-en-visite.sh" in texte and "scripts/identites-bilan" in texte
    brut = yaml.safe_load(texte)["experiment"]
    assert [m["label"] for m in brut["engines"]] == ["ident-a", "ident-b", "ident-c"]
