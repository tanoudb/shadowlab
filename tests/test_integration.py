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
