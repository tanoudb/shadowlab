"""Tests réels : chaque moteur sur le site local (navigateurs compris). Plus lents (~30 s)."""

import pytest

from shadowlab import campaigns
from shadowlab import database as db
from shadowlab.engines import registre
from shadowlab.perimetre import DestinationRefusee

pytestmark = pytest.mark.integration
MOTEURS = ["playwright", "selenium", "scrapling", "httpx"]


@pytest.mark.parametrize("moteur", MOTEURS)
def test_moteur_refuse_une_redirection_hors_perimetre(reglages, moteur):
    with campaigns.serveur_local(reglages):
        pilote = registre()[moteur](reglages.hotes_autorises)
        pilote.open()
        try:
            pilote.start_session()
            with pytest.raises(DestinationRefusee):
                pilote.navigate("https://example.com/")
            sortie_bloquee = False
            try:
                resultat = pilote.navigate(f"{reglages.url_site}/lab/sortie")
                sortie_bloquee = "example.com" not in resultat.url
            except Exception:
                sortie_bloquee = True  # la navigation vers l'extérieur a échoué : c'est l'effet voulu
            assert sortie_bloquee
            pilote.close_session()
        finally:
            pilote.close()


def test_campagne_complete_tous_moteurs(reglages, tmp_path):
    chemin = tmp_path / "c.yaml"
    chemin.write_text(
        "experiment:\n  name: integration\n  engines: [playwright, selenium, scrapling, httpx]\n"
        "  scenarios: [static_html, javascript_content, form_interaction, api_json]\n  repetitions: 1\n  seed: 1\n",
        encoding="utf-8",
    )
    experience = campaigns.lire(chemin, reglages)
    cx = db.ouvrir(reglages.base_donnees)
    experiment_id = campaigns.creer(cx, experience)
    assert campaigns.executer(reglages, experiment_id) == "termine"
    lignes = cx.execute(
        "SELECT e.name AS moteur, s.name AS scenario, r.status FROM runs r JOIN engines e ON e.id = r.engine_id"
        " JOIN scenarios s ON s.id = r.scenario_id WHERE r.experiment_id = ?",
        (experiment_id,),
    ).fetchall()
    statuts = {(r["moteur"], r["scenario"]): r["status"] for r in lignes}
    assert len(statuts) == 16
    for moteur in ("playwright", "selenium"):
        assert all(statuts[(moteur, s)] == "reussi" for s in experience.scenarios)
    for moteur in ("scrapling", "httpx"):
        assert statuts[(moteur, "javascript_content")] == "echec"  # sans JavaScript : attendu
        assert statuts[(moteur, "static_html")] == "reussi"
    nb_detecteurs = len(__import__("shadowlab.detection", fromlist=["registre"]).registre())
    assert cx.execute("SELECT COUNT(*) FROM detections").fetchone()[0] == 16 * nb_detecteurs
    assert cx.execute("SELECT COUNT(*) FROM metrics WHERE cpu_time_ms IS NOT NULL").fetchone()[0] == 16


def test_reproductibilite_bout_en_bout(reglages, tmp_path):
    """E6 réel : deux campagnes identiques (même seed, moteur déterministe httpx)
    produisent le même plan ET les mêmes résultats, bout en bout sur le site réel."""
    config = (
        "experiment:\n  name: {nom}\n  engines: [httpx]\n"
        "  scenarios: [static_html, api_json, session_cookies]\n  repetitions: 3\n  seed: 7\n"
    )

    def lancer(nom):
        chemin = tmp_path / f"{nom}.yaml"
        chemin.write_text(config.format(nom=nom), encoding="utf-8")
        experience = campaigns.lire(chemin, reglages)
        cx = db.ouvrir(reglages.base_donnees)
        experiment_id = campaigns.creer(cx, experience)
        statut = campaigns.executer(reglages, experiment_id)
        sequence = cx.execute(
            "SELECT s.name AS scenario, r.repetition, r.status, r.success"
            " FROM runs r JOIN scenarios s ON s.id = r.scenario_id"
            " WHERE r.experiment_id = ? ORDER BY r.id",
            (experiment_id,),
        ).fetchall()
        return statut, [(r["scenario"], r["repetition"], r["status"], r["success"]) for r in sequence]

    with campaigns.serveur_local(reglages):
        statut_a, seq_a = lancer("repro-a")
        statut_b, seq_b = lancer("repro-b")

    assert statut_a == "termine" and statut_b == "termine"
    assert len(seq_a) == 9  # 3 scénarios × 3 répétitions
    # Même plan (ordre scénario×répétition) ET mêmes résultats : reproductibilité réelle.
    assert seq_a == seq_b, f"résultats non reproductibles :\n{seq_a}\n{seq_b}"
