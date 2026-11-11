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
        # options de moteur : liste blanche par moteur, types contrôlés
        ("label: scrapling-defaut}", "label: s, options: {proxy: 'http://10.0.0.1:3128'}}"),
        ("label: scrapling-defaut}", "label: s, options: {follow_redirects: true}}"),
        ("label: scrapling-defaut}", "label: s, options: {impersonate: firefox}}"),
        ("[playwright,", "[{name: playwright, options: {headless: 'non'}},"),
    ],
)
def test_definitions_invalides_refusees(tmp_path, reglages, remplacement):
    with pytest.raises(ValidationError):
        lire(ecrire(tmp_path, VALIDE.replace(*remplacement)), reglages)


def test_url_exterieure_refusee(tmp_path, reglages):
    import dataclasses

    # Mode strict explicite (sans ``*``) : vérifie que la validation refuse une base_url hors périmètre
    # quand le verrou est armé, indépendamment du défaut illimité de la phase interne.
    strict = dataclasses.replace(reglages, hotes_autorises=("127.0.0.1", "localhost"))
    with pytest.raises(DestinationRefusee):
        lire(ecrire(tmp_path, VALIDE + "  base_url: https://example.com\n"), strict)


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
    experience = FichierCampagne.model_validate(brut).experiment
    plan1 = [o for _, o in _plan(experience, experience.engines[0], "01")]
    plan2 = [o for _, o in _plan(experience, experience.engines[0], "01")]
    assert plan1 == plan2


def test_alias_yaml_refuses(tmp_path, reglages):
    import yaml

    texte = VALIDE.replace("repetitions: 3", "repetitions: 3\n  description: &d texte\n  output: [*d]")
    with pytest.raises(yaml.YAMLError):
        lire(ecrire(tmp_path, texte), reglages)


def test_option_de_moteur_hors_liste_refusee_meme_sans_campagne():
    from shadowlab.engines.scrapling_engine import DriverScrapling

    with pytest.raises(ValueError, match="option inconnue"):
        DriverScrapling(("127.0.0.1",), {"follow_redirects": True})
    pilote = DriverScrapling(("127.0.0.1",), {"timeout": 5})
    assert pilote.configuration()["follow_redirects"] is False


def test_unites_randomisees_par_seed():
    from shadowlab.campaigns import FichierCampagne, unites

    brut = {
        "experiment": {
            "name": "rand",
            "engines": ["httpx", "playwright"],
            "protections": ["01", "02", "03"],
            "scenarios": ["static_html"],
            "repetitions": 1,
            "seed": 42,
        }
    }
    exp = FichierCampagne.model_validate(brut).experiment
    u1 = unites(exp)
    u2 = unites(exp)
    assert u1 == u2  # même seed → même ordre


def test_unites_seed_different_ordre_different():
    from shadowlab.campaigns import FichierCampagne, unites

    brut1 = {
        "experiment": {
            "name": "a",
            "engines": ["httpx", "playwright", "selenium"],
            "protections": ["01", "02", "03", "04"],
            "scenarios": ["static_html"],
            "repetitions": 1,
            "seed": 1,
        }
    }
    brut2 = {**brut1, "experiment": {**brut1["experiment"], "seed": 2}}
    exp1 = FichierCampagne.model_validate(brut1).experiment
    exp2 = FichierCampagne.model_validate(brut2).experiment
    u1 = [(m.nom_affiche, p) for m, p in unites(exp1)]
    u2 = [(m.nom_affiche, p) for m, p in unites(exp2)]
    assert u1 != u2  # seeds différents → ordres différents (très probable avec 12 éléments)


# ---------------------------------------------------------------------------
# Arrêt automatique quand l'Arena tombe en cours de campagne
# (campagne 86 : Docker arrêté, 19 passages en panne enregistrés à la suite)
# ---------------------------------------------------------------------------

PANNE = "arena : chaîne de protection injoignable"


def _base_avec_passages(tmp_path, passages_sous_test):
    """Base avec une campagne dont les passages sont donnés du plus ancien au plus récent.

    Chaque passage est un couple (protection, cause) ; cause `None` = passage sans panne.
    """
    from shadowlab import database as db

    cx = db.ouvrir(tmp_path / "pannes.sqlite3")
    cx.execute(
        "INSERT INTO experiments (id, name, created_at, configuration, status, seed)"
        " VALUES (1, 'pannes', '2026-01-01', '{}', 'en_cours', 1)"
    )
    cx.execute(
        "INSERT INTO engines (id, name, version, runtime, configuration) VALUES (1, 'httpx', '{}', 'python', '{}')"
    )
    cx.execute("INSERT INTO scenarios (id, name) VALUES (1, 'static_html')")
    for rang, (protection, cause) in enumerate(passages_sous_test, start=1):
        cx.execute(
            "INSERT INTO runs (experiment_id, engine_id, scenario_id, repetition, session_token, truth,"
            " started_at, status, success, protection, issue, cause)"
            " VALUES (1, 1, 1, ?, ?, 'automatise', '2026-01-01', ?, ?, ?, ?, ?)",
            (
                rang,
                f"t-{rang}",
                "echec" if cause else "reussi",
                0 if cause else 1,
                protection,
                "erreur_technique" if cause else "extraction_reussie",
                cause,
            ),
        )
    return cx


def test_arena_en_panne_apres_trois_pannes_de_suite(tmp_path):
    from shadowlab.campaigns import _arena_en_panne

    cx = _base_avec_passages(tmp_path, [("03", None), ("03", PANNE), ("03", PANNE), ("03", PANNE)])
    assert _arena_en_panne(cx, 1) is True


def test_arena_pas_en_panne_si_le_dernier_passage_a_abouti(tmp_path):
    from shadowlab.campaigns import _arena_en_panne

    cx = _base_avec_passages(tmp_path, [("03", PANNE), ("03", PANNE), ("03", PANNE), ("03", None)])
    assert _arena_en_panne(cx, 1) is False


def test_arena_pas_en_panne_avant_trois_passages(tmp_path):
    from shadowlab.campaigns import _arena_en_panne

    cx = _base_avec_passages(tmp_path, [("03", PANNE), ("03", PANNE)])
    assert _arena_en_panne(cx, 1) is False


def test_arena_en_panne_ignore_les_passages_sans_arena(tmp_path):
    """Les passages du niveau 01 ne traversent pas l'Arena : leur réussite ne dit rien de son état."""
    from shadowlab.campaigns import _arena_en_panne

    cx = _base_avec_passages(tmp_path, [("03", PANNE), ("01", None), ("04", PANNE), ("01", None), ("03", PANNE)])
    assert _arena_en_panne(cx, 1) is True


def test_une_autre_erreur_technique_ne_compte_pas_comme_panne_arena(tmp_path):
    from shadowlab.campaigns import _arena_en_panne

    cx = _base_avec_passages(tmp_path, [("03", PANNE), ("03", "moteur : TimeoutError"), ("03", PANNE)])
    assert _arena_en_panne(cx, 1) is False


def _pilote_factice():
    """Le vrai pilote httpx, sans ouverture réelle : seule la boucle de l'unité est sous test."""
    from shadowlab.engines import registre

    class PiloteFactice(registre()["httpx"]):
        def open(self):
            pass

        def close(self):
            pass

        def versions(self):
            return {}

    return PiloteFactice


def test_unite_arretee_apres_trois_pannes_arena(tmp_path, reglages, monkeypatch):
    """Trois pannes d'Arena de suite arrêtent l'unité et posent le fichier d'arrêt de la campagne."""
    from shadowlab import campaigns
    from shadowlab import database as db

    experience = lire(
        ecrire(
            tmp_path,
            """
            experiment:
              name: panne
              engines: [httpx]
              protections: ["03"]
              scenarios: [static_html, api_json]
              repetitions: 3
            """,
        ),
        reglages,
    )
    cx = db.ouvrir(reglages.base_donnees)
    experiment_id = campaigns.creer(cx, experience, reglages)

    def passage_en_panne(cx, reglages, experience, experiment_id, pilote, engine_id, scenario, scenario_id,
                         repetition, protection, *args, **kwargs):  # fmt: skip
        cx.execute(
            "INSERT INTO runs (experiment_id, engine_id, scenario_id, repetition, session_token, truth,"
            " started_at, status, success, protection, issue, cause)"
            " VALUES (?, ?, ?, ?, ?, 'automatise', '2026-01-01', 'echec', 0, ?, 'erreur_technique', ?)",
            (experiment_id, engine_id, scenario_id, repetition, f"t-{scenario.name}-{repetition}", protection, PANNE),
        )

    pilote = _pilote_factice()
    monkeypatch.setattr(campaigns, "registre", lambda: {"httpx": pilote})
    monkeypatch.setattr(campaigns, "_passage", passage_en_panne)

    assert campaigns.executer_unite(reglages, experiment_id, 0) == "interrompu"
    assert cx.execute("SELECT COUNT(*) FROM runs WHERE experiment_id = ?", (experiment_id,)).fetchone()[0] == 3
    assert campaigns.fichier_arret(reglages).exists()
