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
    # Mode strict explicite (sans ``*``) : vérifie que le verrou de périmètre tient quand il est armé,
    # indépendamment du défaut illimité de la phase interne.
    with campaigns.serveur_local(reglages):
        pilote = registre()[moteur](("127.0.0.1", "localhost"))
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


def test_recuperer_refuse_une_redirection_hors_perimetre(reglages):
    """Browserless : une URL autorisée qui redirige hors périmètre est refusée (contrôle par saut)."""
    from shadowlab.engines.noezia.rapide import recuperer

    with campaigns.serveur_local(reglages):
        with pytest.raises(DestinationRefusee):
            recuperer(f"{reglages.url_site}/lab/sortie", hotes=("127.0.0.1", "localhost"), verifier_tls=False)


def test_recolte_vitrine_playwright_niveau_01(reglages, tmp_path, monkeypatch):
    """Critère de l'étape 1.5 : un vrai navigateur parcourt tout le site vitrine et retrouve tout, sans faute."""
    import json

    monkeypatch.setenv("SHADOWLAB_VITRINE_TAILLE", "45")
    from shadowlab.config import charger

    reglages = charger()  # relu après le réglage de la taille
    chemin = tmp_path / "recolte.yaml"
    chemin.write_text(
        "experiment:\n  name: recolte\n  engines: [playwright]\n  protections: ['01']\n"
        "  scenarios: [recolte_vitrine]\n  repetitions: 1\n  seed: 20261112\n",
        encoding="utf-8",
    )
    experience = campaigns.lire(chemin, reglages)
    cx = db.ouvrir(reglages.base_donnees)
    experiment_id = campaigns.creer(cx, experience)
    with campaigns.serveur_local(reglages):
        assert campaigns.executer(reglages, experiment_id) == "termine"
    ligne = cx.execute("SELECT status, drapeaux FROM runs WHERE experiment_id = ?", (experiment_id,)).fetchone()
    note = json.loads(ligne["drapeaux"])["details_scenario"]["recolte"]
    assert note["annonces_attendues"] == 45
    assert note["completude"] == 1 and note["exactitude"] == 1
    assert ligne["status"] == "reussi"


def test_noezia_identite_native_une_seule_identite_celle_du_navigateur(reglages, tmp_path):
    """Campagne 94 : deux identités dans la même session. En identité native, une seule, sur toutes les requêtes."""
    import json

    chemin = tmp_path / "native.yaml"
    chemin.write_text(
        "experiment:\n  name: native\n  engines:\n    - name: noezia\n      options: {identite_native: true}\n"
        "  protections: ['01']\n  scenarios: [pagination]\n  repetitions: 1\n  seed: 20261112\n",
        encoding="utf-8",
    )
    experience = campaigns.lire(chemin, reglages)
    cx = db.ouvrir(reglages.base_donnees)
    experiment_id = campaigns.creer(cx, experience)
    with campaigns.serveur_local(reglages):
        assert campaigns.executer(reglages, experiment_id) == "termine"
    passage = cx.execute(
        "SELECT r.session_token, r.status, e.version FROM runs r JOIN engines e ON e.id = r.engine_id"
        " WHERE r.experiment_id = ?",
        (experiment_id,),
    ).fetchone()
    assert passage["status"] == "reussi"
    jeton, reelle = passage["session_token"], json.loads(passage["version"])["chromium"].split(".")[0]

    requetes = [
        {nom.lower(): valeur for nom, valeur in json.loads(ligne["headers"])}
        for ligne in cx.execute("SELECT headers FROM observations_http WHERE session_token = ?", (jeton,))
    ]
    assert len(requetes) > 5, "plusieurs pages, leurs fichiers et leurs envois"
    agents = {h.get("user-agent") for h in requetes}
    assert len(agents) == 1, agents
    assert len({h.get("sec-ch-ua") for h in requetes}) == 1
    agent = agents.pop()
    assert f"/{reelle}." in agent, "la version annoncée est celle du navigateur"
    detailles = {"sec-ch-ua-arch", "sec-ch-ua-bitness", "sec-ch-ua-full-version-list", "sec-ch-ua-model"}
    assert not detailles & set().union(*requetes)

    releve = cx.execute(
        "SELECT payload FROM observations_js WHERE session_token = ? AND kind = 'empreinte' ORDER BY id LIMIT 1",
        (jeton,),
    ).fetchone()
    assert releve is not None, "aucune empreinte relevée pour ce passage"
    navigateur = json.loads(releve["payload"])["navigateur"]
    assert navigateur["userAgent"] == agent
    assert navigateur["webdriver"] is False, "propriété d'origine, ni supprimée ni vraie"
