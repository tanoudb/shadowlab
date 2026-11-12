"""Reprise après une VRAIE coupure : processus réels, SIGKILL, puis `recolte reprendre` (sans navigateur).

Le site du labo et la récolte tournent dans de vrais processus, sur des ports libres (jamais 8770), avec un rythme
qui laisse le temps de couper. On tue la récolte par SIGKILL après quelques pages faites, puis on la reprend.
"""

import os
import re
import signal
import sqlite3
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest
from conftest import port_libre
from outils_recolte import RACINE, RECETTE_VITRINE, TAILLE

pytestmark = pytest.mark.integration

PAGES_AVANT_COUPURE = 15
TOTAL_PAGES = 48  # 3 listes + 45 fiches


def attendre(condition, delai_s: float, message: str):
    fin = time.monotonic() + delai_s
    while time.monotonic() < fin:
        valeur = condition()
        if valeur:
            return valeur
        time.sleep(0.05)
    raise AssertionError(f"délai dépassé : {message}")


@pytest.fixture
def labo(tmp_path):
    """Environnement des processus et site du labo lancé à part, sur des ports libres."""
    port, port_arena = port_libre(), port_libre()
    assert port != 8770
    sorties = tmp_path / "sorties"
    env = {
        **os.environ,
        "PYTHONPATH": str(RACINE / "src"),
        "SHADOWLAB_PORT": str(port),
        "SHADOWLAB_PORT_ARENA": str(port_libre()) if port_arena == port else str(port_arena),
        "SHADOWLAB_SORTIES": str(sorties),
        "SHADOWLAB_BASE": str(sorties / "labo.sqlite3"),
        "SHADOWLAB_VITRINE_TAILLE": str(TAILLE),
    }
    env.pop("SHADOWLAB_HOTES_AUTORISES", None)
    journal = (tmp_path / "site.log").open("wb")
    # Le site du labo sans le frontal TLS, avec le journal d'accès d'uvicorn : c'est lui qui compte les requêtes reçues.
    demarrage = (
        "import uvicorn; from shadowlab.config import charger; from shadowlab.site.app import creer_app; "
        "r = charger(); uvicorn.run(creer_app(r), host=r.hote, port=r.port, log_level='info', access_log=True)"
    )
    site = subprocess.Popen([sys.executable, "-c", demarrage], env=env, stdout=journal, stderr=journal)

    def pret():
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/lab/sante", timeout=1) as r:
                return r.status == 200
        except OSError:
            return False

    try:
        attendre(pret, 20, f"le site du labo ne répond pas (voir {tmp_path / 'site.log'})")
        yield env, port, sorties, tmp_path / "site.log"
    finally:
        site.terminate()
        try:
            site.wait(timeout=5)
        except subprocess.TimeoutExpired:
            site.kill()
        journal.close()


def recette_lente(port: int, destination: Path) -> Path:
    """La recette de la vitrine, sur ce port, avec 0,1 s entre deux pages (45 annonces : environ 5 s en tout)."""
    lignes = []
    for ligne in RECETTE_VITRINE.read_text(encoding="utf-8").splitlines():
        ligne = ligne.replace("8770", str(port))
        if ligne.startswith("rythme:"):
            ligne = "rythme: {delai_s: [0.1, 0.1, 0.1]}"
        lignes.append(ligne)
    destination.write_text("\n".join(lignes) + "\n", encoding="utf-8")
    return destination


def lire_etat(chemin: Path, requete: str):
    try:
        cx = sqlite3.connect(chemin, timeout=5)  # lecture seule en pratique : un select (le mode ro ne lit pas le WAL)
        try:
            return cx.execute(requete).fetchall()
        finally:
            cx.close()
    except sqlite3.Error:
        return []


def test_sigkill_en_pleine_recolte_puis_reprendre(labo, tmp_path):
    env, port, sorties, acces = labo
    recette = recette_lente(port, tmp_path / "vitrine.yaml")
    etat = sorties / "recoltes" / "vitrine-annonces" / "etat.sqlite3"

    def commande(*arguments):
        return [sys.executable, "-m", "shadowlab.cli", "recolte", *arguments]

    debut = time.monotonic()
    recolte = subprocess.Popen(
        commande("lancer", str(recette)), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    try:
        attendre(
            lambda: (
                (lire_etat(etat, "SELECT COUNT(*) FROM pages WHERE etat = 'faite'") or [(0,)])[0][0]
                >= PAGES_AVANT_COUPURE
            ),
            30,
            "la récolte n'a pas avancé",
        )
        os.kill(recolte.pid, signal.SIGKILL)
        recolte.wait(timeout=10)
    finally:
        if recolte.poll() is None:
            recolte.kill()
    assert recolte.returncode == -signal.SIGKILL

    faites = lire_etat(etat, "SELECT COUNT(*) FROM pages WHERE etat = 'faite'")[0][0]
    assert PAGES_AVANT_COUPURE <= faites < TOTAL_PAGES, "la coupure aurait dû tomber en pleine récolte"
    assert lire_etat(etat, "SELECT statut FROM passes") == [("en_cours",)]  # aucune fin propre

    reprise = subprocess.run(
        commande("reprendre", "vitrine-annonces"), env=env, capture_output=True, text=True, timeout=90
    )
    assert reprise.returncode == 0, reprise.stdout + reprise.stderr
    assert "Terminée : 48 pages" in reprise.stdout
    assert lire_etat(etat, "SELECT statut FROM passes") == [("terminee",)]

    # Côté site (journal d'accès d'uvicorn) : chaque fiche une fois, au plus une (celle en route) deux fois.
    vues: dict[str, int] = {}
    for ligne in acces.read_text(encoding="utf-8", errors="replace").splitlines():
        trouve = re.search(r'"GET (/lab/vitrine/annonces\S*) HTTP', ligne)
        if trouve:
            chemin = trouve.group(1).split("?")[0]
            vues[chemin] = vues.get(chemin, 0) + 1
    fiches = {chemin: n for chemin, n in vues.items() if chemin != "/lab/vitrine/annonces"}
    assert len(fiches) == TAILLE and all(n <= 2 for n in fiches.values())
    assert sum(n - 1 for n in fiches.values()) <= 1, (
        f"des fiches demandées deux fois : {[c for c, n in fiches.items() if n > 1]}"
    )
    assert vues["/lab/vitrine/annonces"] in (
        3,
        4,
    )  # les trois pages de liste, plus au plus la page en route à la coupure
    # Côté état : une ligne par page, aucune en double, aucune restée en cours ou à faire.
    assert lire_etat(etat, "SELECT COUNT(*), COUNT(DISTINCT canon) FROM pages") == [(TOTAL_PAGES, TOTAL_PAGES)]
    assert lire_etat(etat, "SELECT COUNT(*) FROM pages WHERE etat != 'faite'") == [(0,)]

    note = subprocess.run(
        commande("noter", "vitrine-annonces", "--verite", "vitrine"),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert note.returncode == 0, note.stdout + note.stderr
    assert "pages 48/48" in note.stdout and "enregistrements 45/45" in note.stdout and "champs 630/630" in note.stdout
    print(f"durée du test de coupure : {time.monotonic() - debut:.1f} s, {faites} pages faites avant le SIGKILL")
