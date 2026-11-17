"""Essai « la porte expire au milieu d'une visite » : profil `enduranceporte150`, campagne à un bras, fichier
d'environnement. Aucun navigateur, aucune Arena. Ce que ces tests établissent :
- le profil ne diffère d'`endurance` que par `duree_cookie_s` (150 s) et `description` ;
- la durée de 150 s sort de la rafale (`RAFALE_PORTE_S`) et reste au-dessus de la limite « trop tôt » (durée moins
  `TOLERANCE_PORTE_S`) : le défi revenu à 150 s est jugé par la durée, sans écart minimal ;
- la campagne se lit avec la variable `SHADOWLAB_PROFILS_EXTRA` et la vitrine de 60 annonces, et la recette du passage
  reçoit la durée du profil ; les repassages possibles couvrent la passe.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

from shadowlab import campaigns, scenarios
from shadowlab.arena import profils as module_profils
from shadowlab.engines.noezia.parcours import RAFALE_PORTE_S, TOLERANCE_PORTE_S
from shadowlab.site import vitrine

RACINE = Path(__file__).resolve().parents[1]
PROFILS = RACINE / "configs" / "arena" / "profils-endurance-essai-porte.yaml"
ESSAI = RACINE / "configs" / "experiments" / "essai-porte-en-visite.yaml"
ENV = RACINE / "configs" / "courses" / "i9-essai-porte.env"


@pytest.fixture
def profil_essai(monkeypatch):
    monkeypatch.setenv("SHADOWLAB_PROFILS_EXTRA", str(PROFILS))
    monkeypatch.setenv("SHADOWLAB_VITRINE_TAILLE", "60")


def test_le_profil_de_l_essai_ne_differe_que_par_la_duree(monkeypatch):
    monkeypatch.setenv("SHADOWLAB_PROFILS_EXTRA", str(PROFILS))
    profils = module_profils.charger()
    essai, long = profils.de("enduranceporte150").model_dump(), profils.de("endurance").model_dump()
    assert essai["duree_cookie_s"] == 150 and long["duree_cookie_s"] == 86400
    for cle in ("duree_cookie_s", "description"):
        essai.pop(cle), long.pop(cle)
    assert essai == long
    assert set(yaml.safe_load(PROFILS.read_text(encoding="utf-8"))) == {"enduranceporte150"}


def test_150_s_est_hors_rafale_et_hors_trop_tot():
    """Un défi revenu à 150 s : pas dans la rafale (< 120 s), pas trop tôt (150 - 60 = 90 s)."""
    assert RAFALE_PORTE_S < 150
    assert 150 - TOLERANCE_PORTE_S > 0  # la limite « trop tôt » est à 90 s


def test_l_essai_se_lit_avec_le_profil_et_la_vitrine_de_60(reglages, profil_essai):
    e = campaigns.lire(ESSAI, reglages)
    assert [m.nom_affiche for m in e.engines] == ["sujet"]
    sujet = e.engines[0]
    assert sujet.name == "noezia" and sujet.recolte_incrementale
    assert sujet.options == {
        "headless": False,
        "channel": "chrome",
        "identite_native": True,
        "identite": "essai-porte-visite-1",
    }
    assert e.protections == ["enduranceporte150"] and e.scenarios == ["visite"] and e.monde == "serie"
    assert e.espacement.mode == "fixe" and e.espacement.minutes == 1
    assert e.visites_de(sujet) == 3 and e.pages_par_visite == 40 and e.concurrency == 1
    assert e.total_passages() == 3
    # la durée de la porte que la campagne donne au scénario vient du profil lu avec la variable
    reglages_visite = campaigns._reglages_visite(reglages, 1, sujet, "enduranceporte150")
    assert reglages_visite["duree_porte_s"] == 150
    recette, _ = scenarios.recette_du_passage("vitrine", "http://127.0.0.1:8770", 150)
    porte = recette.porte_entree
    assert porte is not None and porte.duree_s == 150
    assert porte.repassages_max == scenarios.PORTE_REPASSAGES_PASSAGE


def test_la_vitrine_de_60_donne_63_pages_et_les_repassages_suffisent():
    """63 pages par passe (3 de liste, 60 fiches) ; la porte revient toutes les 150 s au plus : à 8 s par page, une
    passe dure environ 8 minutes, soit 4 repassages au plus ; le maximum de la recette est de 10."""
    assert len(vitrine.pages_attendues(20276150, 60)) == 63
    assert 63 * 8 / 150 < 4 < scenarios.PORTE_REPASSAGES_PASSAGE
    assert 63 * 20 / 150 < scenarios.PORTE_REPASSAGES_PASSAGE  # même à 20 s par page : 8 repassages au plus


def test_fichier_environnement_de_l_essai():
    valeurs = {}
    for ligne in ENV.read_text(encoding="utf-8").splitlines():
        if ligne.strip() and not ligne.startswith("#"):
            cle, _, valeur = ligne.partition("=")
            valeurs[cle] = valeur
    assert valeurs == {
        "SHADOWLAB_PROFILS_EXTRA": "configs/arena/profils-endurance-essai-porte.yaml",
        "SHADOWLAB_VITRINE_TAILLE": "60",
    }
    assert (RACINE / valeurs["SHADOWLAB_PROFILS_EXTRA"]).exists()
    assert subprocess.run(["bash", "-n", str(RACINE / "scripts" / "course.sh")]).returncode == 0
