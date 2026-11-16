"""Pile Docker de l'Arena : un projet Compose par dossier (course de 7 jours isolée du dossier principal)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from shadowlab import config
from shadowlab.arena import pile

RACINE = Path(__file__).resolve().parent.parent
VARIABLES = (
    "SHADOWLAB_ARENA_PROJET",
    "SHADOWLAB_ARENA_IMAGE",
    "SHADOWLAB_PORT",
    "SHADOWLAB_PORT_AVAL",
    "SHADOWLAB_SORTIES",
)


@pytest.fixture(autouse=True)
def _sans_variables(monkeypatch):
    for nom in VARIABLES:
        monkeypatch.delenv(nom, raising=False)


@pytest.fixture
def appels(monkeypatch):
    liste: list[tuple[list[str], dict]] = []

    def faux(commande, **options):
        liste.append((commande, options["env"]))
        return subprocess.CompletedProcess(commande, 0, "", "")

    monkeypatch.setattr(pile.subprocess, "run", faux)
    return liste


def test_defaut_projet_arena():
    assert config.charger().projet_arena == "shadowlab-arena"


def test_variable_projet(monkeypatch):
    monkeypatch.setenv("SHADOWLAB_ARENA_PROJET", "shadowlab-course-i9")
    assert config.charger().projet_arena == "shadowlab-course-i9"


def test_sans_variable_comportement_identique(appels):
    pile._compose(config.charger(), "ps")
    commande, env = appels[0]
    assert commande[:3] == ["docker", "compose", "-p"]
    assert commande[3] == "shadowlab-arena"
    assert env["SHADOWLAB_ARENA_PROJET"] == "shadowlab-arena"
    assert env["SHADOWLAB_ARENA_IMAGE"] == "shadowlab-coraza:local"
    assert env["SHADOWLAB_PORT"] == "8770"
    assert env["SHADOWLAB_PORT_AVAL"] == "8781"


def test_avec_variables_projet_image_et_ports(appels, monkeypatch):
    monkeypatch.setenv("SHADOWLAB_ARENA_PROJET", "shadowlab-course-i9")
    monkeypatch.setenv("SHADOWLAB_PORT", "8760")
    monkeypatch.setenv("SHADOWLAB_PORT_AVAL", "8761")
    pile._compose(config.charger(), "up", "-d")
    commande, env = appels[0]
    assert commande[3] == "shadowlab-course-i9"
    assert commande[-2:] == ["up", "-d"]
    assert env["SHADOWLAB_ARENA_IMAGE"] == "shadowlab-coraza:shadowlab-course-i9"
    assert env["SHADOWLAB_PORT"] == "8760"
    assert env["SHADOWLAB_PORT_AVAL"] == "8761"


def test_composition_sans_nom_ni_image_ni_port_en_dur():
    texte = (RACINE / "docker" / "arena" / "docker-compose.yml").read_text(encoding="utf-8")
    assert "name: ${SHADOWLAB_ARENA_PROJET:-shadowlab-arena}" in texte
    assert "image: ${SHADOWLAB_ARENA_IMAGE:-shadowlab-coraza:local}" in texte
    assert 'AMONT_DEFAUT: "${SHADOWLAB_PORT:-8770}"' in texte


def test_fichier_environnement_de_la_course():
    valeurs = {}
    for ligne in (RACINE / "configs" / "courses" / "i9.env").read_text(encoding="utf-8").splitlines():
        if ligne.strip() and not ligne.startswith("#"):
            cle, _, valeur = ligne.partition("=")
            valeurs[cle] = valeur
    assert valeurs["SHADOWLAB_PORT"] == "8760"
    assert valeurs["SHADOWLAB_PORT_ARENA"] == "8753"
    assert valeurs["SHADOWLAB_PORT_AVAL"] == "8761"
    assert valeurs["SHADOWLAB_ARENA_PROJET"] == "shadowlab-course-i9"
    assert "SHADOWLAB_SORTIES" in valeurs and "SHADOWLAB_IDENTITES" in valeurs
    assert valeurs["SHADOWLAB_VITRINE_TAILLE"] == "300"
    assert "SHADOWLAB_PROFILS_EXTRA" not in valeurs  # la vraie course : profil endurance, porte de 24 h


def test_fichier_environnement_de_la_repetition():
    valeurs = {}
    for ligne in (RACINE / "configs" / "courses" / "i9-repetition.env").read_text(encoding="utf-8").splitlines():
        if ligne.strip() and not ligne.startswith("#"):
            cle, _, valeur = ligne.partition("=")
            valeurs[cle] = valeur
    assert valeurs == {
        "SHADOWLAB_PROFILS_EXTRA": "configs/arena/profils-endurance-court.yaml",
        "SHADOWLAB_VITRINE_TAILLE": "30",
    }
    assert (RACINE / valeurs["SHADOWLAB_PROFILS_EXTRA"]).exists()


def test_course_sh_syntaxe():
    chemin = RACINE / "scripts" / "course.sh"
    assert subprocess.run(["bash", "-n", str(chemin)]).returncode == 0
    texte = chemin.read_text(encoding="utf-8")
    assert "rm -rf" not in texte
    assert "sudo" not in texte


def test_course_sh_preparer_refuse_un_dossier_existant(tmp_path):
    depot = tmp_path / "depot"
    (depot / "scripts").mkdir(parents=True)
    (depot / ".courses" / "i9").mkdir(parents=True)
    script = depot / "scripts" / "course.sh"
    script.write_text((RACINE / "scripts" / "course.sh").read_text(encoding="utf-8"), encoding="utf-8")
    r = subprocess.run(["bash", str(script), "preparer", "v1"], capture_output=True, text=True, env=os.environ)
    assert r.returncode != 0
    assert "existe déjà" in r.stderr
