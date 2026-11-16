"""Palier 2, I7 : le bilan de la soirée (§ 6.2), lu dans la base, sur une base fabriquée.

Chaque critère est donné `tenu`, `non tenu` ou `non mesuré` : un bras qui n'a rien fait (identité déjà bannie, Arena
absente) ne vaut jamais « tenu ». Les données sont celles que la campagne laisse : `runs` (drapeaux, détails du
scénario), `visites`, `observations_js` (empreinte E), `decisions`, `observations_http`, `bannissements`.
"""

# ruff: noqa: E501  (requêtes SQL et configurations YAML en ligne)
from __future__ import annotations

import json

import pytest
from test_espacement import campagne

from shadowlab import campaigns, passages, soiree
from shadowlab import database as db
from shadowlab.arena import visiteurs
from shadowlab.cli import main

AVANT = "2026-11-16T20:00:00.000+00:00"
BLOCAGE = "2026-11-16T21:00:00.000+00:00"
APRES = "2026-11-16T21:00:05.000+00:00"
BRAS = ("sujet", "temoin-negatif", "temoin-sentinelle", "temoin-classique")


@pytest.fixture
def base(tmp_path, reglages):
    experience = campagne(tmp_path, reglages)
    cx = db.ouvrir(reglages.base_donnees)
    experiment_id = campaigns.creer(cx, experience, reglages)
    yield cx, experiment_id
    cx.close()


def monde(experiment_id, label):
    return f"c{experiment_id}:{label}:endurance"


def visite(cx, experiment_id, label, rang, *, reussie=True, visiteur="v1", e="E1", defi=0, identite="ok", arret=False,
           bloque=False, pages_apres=0, erreur=False):  # fmt: skip
    """Une visite (un passage) du bras `label`, avec tout ce que l'Arena et le scénario en ont laissé."""
    nom_monde = monde(experiment_id, label)
    moteur = db.engine_id(cx, "noezia", "{}", "navigateur", {"label": label})
    scenario = db.scenario_id(cx, "visite", "visite")
    run_id, jeton = passages.demarrer(
        cx, experiment_id, moteur, scenario, rang, "automatise", "endurance", monde=nom_monde
    )
    details = {"identite": {"nom": label, "etat": identite} if identite else None}
    if arret:
        details["arret"] = {"signe": "statut", "statut": 403}
    drapeaux = {"challenges_emis": defi, "details_scenario": details}
    cx.execute(
        "UPDATE runs SET status = ?, success = ?, issue = ?, drapeaux = ?, completed_at = ? WHERE id = ?",
        (
            "erreur" if erreur else ("reussi" if reussie else "echec"),
            int(reussie),
            "x",
            json.dumps(drapeaux),
            AVANT,
            run_id,
        ),
    )
    if visiteur:
        cx.execute(
            "INSERT INTO visites (monde_id, visiteur, session_token, neuve, vue_le) VALUES (?, ?, ?, ?, ?)",
            (visiteurs.identifiant_monde(cx, nom_monde), visiteur, jeton, int(rang == 1), AVANT),
        )
    if e:
        cx.execute(
            "INSERT INTO observations_js (session_token, received_at, kind, page, payload) VALUES (?, ?, 'empreinte', '/', ?)",
            (jeton, AVANT, json.dumps({"navigateur": {"userAgent": e}})),
        )
    cx.execute(
        "INSERT INTO observations_http (session_token, received_at, method, path, headers, cookies, status)"
        " VALUES (?, ?, 'GET', '/lab/vitrine/annonces', '{}', '{}', ?)",
        (jeton, AVANT, 403 if bloque else 200),
    )
    if bloque:
        cx.execute(
            "INSERT INTO decisions (session_token, created_at, couche, decision, chemin, motifs)"
            " VALUES (?, ?, 'bannissement', 'bloque', '/lab/vitrine/annonces', '[]')",
            (jeton, BLOCAGE),
        )
    for n in range(pages_apres):
        cx.execute(
            "INSERT INTO observations_http (session_token, received_at, method, path, headers, cookies, status)"
            " VALUES (?, ?, 'GET', ?, '{}', '{}', 403)",
            (jeton, APRES, f"/lab/vitrine/annonces/AN-00000{n}"),
        )
    return jeton


def bannir(cx, experiment_id, label, *, visiteur="v1", empreinte=None, motif="manuel"):
    cx.execute(
        "INSERT INTO bannissements (monde_id, visiteur, empreinte, motif, cree_le) VALUES (?, ?, ?, ?, ?)",
        (visiteurs.identifiant_monde(cx, monde(experiment_id, label)), visiteur, empreinte, motif, AVANT),
    )


def soiree_reussie(cx, x):
    for n in range(1, 25):
        visite(cx, x, "sujet", n, defi=1 if n == 1 else 0)
    for n in range(1, 25):  # le témoin négatif : cookies jetés, un visiteur neuf à chaque visite, la même empreinte
        visite(cx, x, "temoin-negatif", n, visiteur=f"n{n}", e="E1" if n < 5 else "E1", reussie=n < 5, bloque=n >= 5)
    bannir(cx, x, "temoin-negatif", visiteur="n5", empreinte="e1", motif="detecte:correlation-session")
    visite(cx, x, "temoin-sentinelle", 1, visiteur="s1", e="E3", defi=1)
    visite(cx, x, "temoin-sentinelle", 2, visiteur="s1", e="E3")
    bannir(cx, x, "temoin-sentinelle", visiteur="s1")
    visite(
        cx, x, "temoin-sentinelle", 3, visiteur="s1", e="E3", reussie=False, bloque=True, arret=True, identite="banni"
    )
    for n in (4, 5, 6):  # identité bannie : refusée avant tout lancement de Chrome, aucune requête
        visite(cx, x, "temoin-sentinelle", n, visiteur=None, e=None, reussie=False, identite=None)
    for n in range(1, 5):
        visite(
            cx,
            x,
            "temoin-classique",
            n,
            visiteur=f"p{n}",
            e="E4",
            reussie=False,
            bloque=True,
            arret=True,
            identite=None,
        )


def statuts(rapport, bras):
    return {nom: c["statut"] for nom, c in rapport["bras"][bras]["criteres"].items()}


def test_une_soiree_reussie_tient_tous_les_criteres(base):
    cx, x = base
    soiree_reussie(cx, x)
    rapport = soiree.bilan(cx, x)
    assert statuts(rapport, "sujet") == {
        "visites_reussies": "tenu",
        "meme_visiteur": "tenu",
        "meme_empreinte": "tenu",
        "defi_premiere_visite_seulement": "tenu",
        "aucune_alerte": "tenu",
    }
    assert statuts(rapport, "temoin-negatif") == {"arrete_a_la_visite_5": "tenu", "banni": "tenu"}
    assert statuts(rapport, "temoin-sentinelle") == {
        "bannissement_ecrit": "tenu",
        "refus_a_la_visite_voulue": "tenu",
        "aucune_requete_apres_403": "tenu",
        "identite_bannie": "tenu",
    }
    assert statuts(rapport, "temoin-classique") == {"toujours_arrete": "tenu", "refus_par_l_arena": "tenu"}
    assert rapport["verdict"] == "tenu"
    sujet = rapport["bras"]["sujet"]
    assert (sujet["visites_prevues"], sujet["visites_faites"], sujet["visites_reussies"]) == (24, 24, 24)
    assert rapport["bras"]["temoin-negatif"]["premiere_visite_arretee"] == 5
    assert rapport["bras"]["temoin-sentinelle"]["requetes_apres_403"] == 0
    json.dumps(rapport)  # le bilan s'écrit en JSON


@pytest.mark.parametrize(
    ("defaut", "bras", "critere"),
    [
        ("visiteur", "sujet", "meme_visiteur"),
        ("empreinte", "sujet", "meme_empreinte"),
        ("echec", "sujet", "visites_reussies"),
        ("defi_tard", "sujet", "defi_premiere_visite_seulement"),
        ("pas_de_defi", "sujet", "defi_premiere_visite_seulement"),
        ("alerte", "sujet", "aucune_alerte"),
        ("banni", "sujet", "aucune_alerte"),
        ("arret_tardif", "temoin-negatif", "arrete_a_la_visite_5"),
        ("jamais_arrete", "temoin-negatif", "arrete_a_la_visite_5"),
        ("pas_banni", "temoin-negatif", "banni"),
        ("requetes_apres", "temoin-sentinelle", "aucune_requete_apres_403"),
        ("pas_de_bannissement", "temoin-sentinelle", "bannissement_ecrit"),
        ("refus_trop_tot", "temoin-sentinelle", "refus_a_la_visite_voulue"),
        ("identite_alerte", "temoin-sentinelle", "identite_bannie"),
        ("classique_passe", "temoin-classique", "toujours_arrete"),
        ("classique_par_l_outil", "temoin-classique", "refus_par_l_arena"),
    ],
)
def test_chaque_critere_peut_ne_pas_etre_tenu(base, defaut, bras, critere):
    cx, x = base
    soiree_reussie(cx, x)
    run = (
        f"(SELECT r.id FROM runs r JOIN engines e ON e.id = r.engine_id WHERE r.experiment_id = {x}"
        " AND json_extract(e.configuration, '$.label') = ? AND r.repetition = ?)"
    )
    jeton = f"(SELECT session_token FROM runs WHERE id = {run})"

    if defaut == "visiteur":  # le sujet change de visiteur à la 7e visite
        cx.execute(f"UPDATE visites SET visiteur = 'autre' WHERE session_token = {jeton}", ("sujet", 7))
    elif defaut == "empreinte":
        cx.execute(
            f"UPDATE observations_js SET payload = ? WHERE session_token = {jeton}",
            (json.dumps({"navigateur": {"userAgent": "X"}}), "sujet", 7),
        )
    elif defaut == "echec":
        cx.execute(f"UPDATE runs SET success = 0, status = 'echec' WHERE id = {run}", ("sujet", 12))
    elif defaut == "defi_tard":
        cx.execute(
            f"UPDATE runs SET drapeaux = json_set(drapeaux, '$.challenges_emis', 1) WHERE id = {run}", ("sujet", 5)
        )
    elif defaut == "pas_de_defi":
        cx.execute(
            f"UPDATE runs SET drapeaux = json_set(drapeaux, '$.challenges_emis', 0) WHERE id = {run}", ("sujet", 1)
        )
    elif defaut == "alerte":
        cx.execute(
            f"UPDATE runs SET drapeaux = json_set(drapeaux, '$.details_scenario.identite.etat', 'alerte') WHERE id = {run}",
            ("sujet", 9),
        )
    elif defaut == "banni":
        bannir(cx, x, "sujet", visiteur="v1", motif="debit:pages_par_heure")
    elif defaut == "arret_tardif":  # arrêté seulement à la 6e visite
        cx.execute(f"UPDATE runs SET success = 1, status = 'reussi' WHERE id = {run}", ("temoin-negatif", 5))
        cx.execute(f"DELETE FROM decisions WHERE session_token = {jeton}", ("temoin-negatif", 5))
    elif defaut == "jamais_arrete":
        cx.execute(
            f"UPDATE runs SET success = 1, status = 'reussi' WHERE experiment_id = {x} AND engine_id IN (SELECT id FROM engines WHERE json_extract(configuration, '$.label') = 'temoin-negatif')"
        )
    elif defaut == "pas_banni":
        cx.execute("DELETE FROM bannissements WHERE motif LIKE 'detecte:%'")
    elif defaut == "requetes_apres":
        cx.execute(
            "INSERT INTO observations_http (session_token, received_at, method, path, headers, cookies, status)"
            f" SELECT session_token, '{APRES}', 'GET', '/lab/vitrine/annonces/AN-000001', '{{}}', '{{}}', 200 FROM runs WHERE id = {run}",
            ("temoin-sentinelle", 3),
        )
    elif defaut == "pas_de_bannissement":
        cx.execute("DELETE FROM bannissements WHERE motif = 'manuel'")
    elif defaut == "refus_trop_tot":  # le refus est vu à la 2e visite, pas à la 3e
        cx.execute(
            f"INSERT INTO decisions (session_token, created_at, couche, decision, chemin, motifs) SELECT session_token, '{AVANT}', 'bannissement', 'bloque', '/', '[]' FROM runs WHERE id = {run}",
            ("temoin-sentinelle", 2),
        )
    elif defaut == "identite_alerte":
        cx.execute(
            f"UPDATE runs SET drapeaux = json_set(drapeaux, '$.details_scenario.identite.etat', 'alerte') WHERE id = {run}",
            ("temoin-sentinelle", 3),
        )
    elif defaut == "classique_passe":
        cx.execute(f"UPDATE runs SET success = 1, status = 'reussi' WHERE id = {run}", ("temoin-classique", 2))
    elif defaut == "classique_par_l_outil":
        cx.execute(
            "DELETE FROM decisions WHERE session_token IN (SELECT session_token FROM runs WHERE engine_id IN (SELECT id FROM engines WHERE json_extract(configuration, '$.label') = 'temoin-classique'))"
        )

    rapport = soiree.bilan(cx, x)
    assert statuts(rapport, bras)[critere] == "non tenu", rapport["bras"][bras]["criteres"][critere]
    assert rapport["verdict"] == "non tenu"


def test_une_campagne_vide_n_est_pas_tenue(base):
    cx, x = base
    rapport = soiree.bilan(cx, x)
    assert rapport["verdict"] == "non mesuré"
    for bras in BRAS:
        assert {c["statut"] for c in rapport["bras"][bras]["criteres"].values()} == {"non mesuré"}


def test_une_identite_deja_bannie_donne_zero_requete_et_ce_n_est_pas_tenu(base):
    """« Démarrage impossible » partout : 0 requête après le 403, mais rien n'a été refusé par l'Arena."""
    cx, x = base
    for n in range(1, 7):
        visite(cx, x, "temoin-sentinelle", n, visiteur=None, e=None, reussie=False, identite=None, erreur=True)
    rapport = soiree.bilan(cx, x)
    assert statuts(rapport, "temoin-sentinelle") == {
        "bannissement_ecrit": "non tenu",
        "refus_a_la_visite_voulue": "non mesuré",
        "aucune_requete_apres_403": "non mesuré",
        "identite_bannie": "non mesuré",
    }
    assert rapport["verdict"] != "tenu"


def test_le_sujet_arrete_avant_la_fin_n_a_pas_toutes_ses_visites(base):
    cx, x = base
    for n in range(1, 11):
        visite(cx, x, "sujet", n, defi=1 if n == 1 else 0)
    rapport = soiree.bilan(cx, x)
    assert statuts(rapport, "sujet")["visites_reussies"] == "non tenu"  # 10 visites sur 24 prévues
    assert rapport["bras"]["sujet"]["visites_faites"] == 10


def test_les_roles_se_lisent_par_libelle(base):
    cx, x = base
    rapport = soiree.bilan(cx, x, roles={"sujet": "autre-libelle"})
    assert rapport["bras"]["sujet"]["label"] == "autre-libelle"
    assert rapport["bras"]["sujet"]["visites_faites"] == 0


def test_sous_commande_soiree_bilan(base, capsys, reglages):
    cx, x = base
    soiree_reussie(cx, x)
    cx.close()
    assert main(["soiree", "bilan", str(x)]) == 0
    sortie = capsys.readouterr().out
    assert "sujet" in sortie and "tenu" in sortie and "24" in sortie
    assert main(["soiree", "bilan", str(x), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["verdict"] == "tenu"


def test_sous_commande_soiree_bilan_code_1_si_non_tenu_et_2_si_inconnue(base, capsys):
    cx, x = base
    cx.close()
    assert main(["soiree", "bilan", str(x)]) == 1
    assert main(["soiree", "bilan", "9999"]) == 2
    assert "introuvable" in capsys.readouterr().err
