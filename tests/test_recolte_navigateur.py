"""Récolte de la vitrine par le moteur `navigateur` (vrai Google Chrome, identité native) : intégration.

NON exécuté par l'auteur (aucun navigateur autorisé à ce moment-là) : à lancer par la coordination, quand l'écran de la
machine est libre (Chrome s'ouvre en fenêtre visible, environ 6 minutes pour 48 pages) :

    uv run pytest tests/test_recolte_navigateur.py -m integration -q

Ports libres choisis par la fixture `reglages` ; jamais 8770 ni la base du dépôt principal. Niveau 01 : le site du
labo sans frontal ni protection.
"""

from __future__ import annotations

import json

import pytest
from outils_recolte import GRAINE, RECETTE_VITRINE, TAILLE

from shadowlab.cli import main

pytestmark = pytest.mark.integration
SEUIL = 0.99


def test_vitrine_a_45_annonces_par_le_navigateur_niveau_01(reglages, monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("SHADOWLAB_VITRINE_TAILLE", str(TAILLE))
    monkeypatch.setenv("SHADOWLAB_VITRINE_GRAINE", str(GRAINE))
    assert reglages.port != 8770, "le test ne doit jamais viser le port du labo habituel"
    texte = RECETTE_VITRINE.read_text(encoding="utf-8").replace(":8770", f":{reglages.port}")
    recette = tmp_path / "vitrine-navigateur.yaml"
    recette.write_text(texte, encoding="utf-8")
    sortie = tmp_path / "recolte"

    code = main(["recolte", "lancer", str(recette), "--moteur", "navigateur", "--sortie", str(sortie)])
    affichage = capsys.readouterr().out
    assert code == 0, affichage

    resume = json.loads((sortie / "passe-001" / "resume.json").read_text(encoding="utf-8"))
    assert resume["statut"] == "terminee" and resume["arret"] is None
    assert resume["moteur"]["nom"] == "navigateur" and resume["moteur"]["pilote"] == "noezia"
    configuration = resume["moteur"]["configuration"]
    assert configuration["identite_native"] is True and configuration["headless"] is False
    assert configuration["channel"] == "chrome"
    attendues = 3 + TAILLE  # 3 listes de 20 + 45 fiches
    assert resume["pages"]["faites"] / attendues >= SEUIL
    assert resume["enregistrements"]["annonces"] / TAILLE >= SEUIL

    # Notation contre la vérité de la vitrine : pages, enregistrements et champs, chacun à 99 % ou plus (code 0).
    assert main(["recolte", "noter", "vitrine-annonces", "--verite", "vitrine", "--sortie", str(sortie)]) == 0
