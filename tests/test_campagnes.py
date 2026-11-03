import textwrap

import pytest
from pydantic import ValidationError

from shadowlab.campaigns import FichierCampagne, lire
from shadowlab.perimetre import DestinationRefusee


def ecrire(tmp_path, texte):
    chemin = tmp_path / "c.yaml"
    chemin.write_text(textwrap.dedent(texte), encoding="utf-8")
    return chemin


VALIDE = """
experiment:
  name: essai
  engines: [playwright, {name: scrapling, label: scrapling-defaut}]
  scenarios: [static_html, api_json]
  repetitions: 3
"""


def test_fichier_valide_et_graine_tiree(tmp_path, reglages):
    experience = lire(ecrire(tmp_path, VALIDE), reglages)
    assert [m.nom_affiche for m in experience.engines] == ["playwright", "scrapling-defaut"]
    assert isinstance(experience.seed, int)


@pytest.mark.parametrize(
    "remplacement",
    [
        ("[playwright, {name: scrapling, label: scrapling-defaut}]", "[moteur-inconnu]"),
        ("[static_html, api_json]", "[scenario_inconnu]"),
        ("repetitions: 3", "repetitions: 0"),
        ("name: essai", "name: Essai Majuscule"),
        ("repetitions: 3", "repetitions: 3\n  environment: production"),
        ("repetitions: 3", "repetitions: 3\n  champ_inconnu: 1"),
        ("repetitions: 3", "repetitions: 3\n  metrics: [vitesse_lumiere]"),
    ],
)
def test_definitions_invalides_refusees(tmp_path, reglages, remplacement):
    with pytest.raises(ValidationError):
        lire(ecrire(tmp_path, VALIDE.replace(*remplacement)), reglages)


def test_url_exterieure_refusee(tmp_path, reglages):
    with pytest.raises(DestinationRefusee):
        lire(ecrire(tmp_path, VALIDE + "  base_url: https://example.com\n"), reglages)


def test_meme_graine_meme_ordre():
    from shadowlab.campaigns import _plan

    brut = {
        "experiment": {
            "name": "a",
            "engines": ["httpx"],
            "scenarios": ["static_html", "api_json", "pagination"],
            "repetitions": 5,
            "seed": 3,
        }
    }
    plan1 = [o for _, _, o in _plan(FichierCampagne.model_validate(brut).experiment)]
    plan2 = [o for _, _, o in _plan(FichierCampagne.model_validate(brut).experiment)]
    assert plan1 == plan2
