"""D-103 : les quatre campagnes de mesure (§ 5 de docs/recherche/course-i9-visite-6-2026-11-18.md) et la requête du
verdict.

Aucun navigateur, aucune Arena. Ce que ces tests établissent :
- chaque campagne se lit (avec la variable de profil quand il en faut une) et a le réglage annoncé dans son en-tête ;
- mesure 1 : la 1re passe de la vitrine de 300 annonces ne finit pas en 21 visites, donc les visites 2 à 21
  reprennent la passe ; mesure 2 : la 1re passe de la vitrine de 30 annonces finit au plus tard à la 3e visite, donc
  au moins 27 visites sont incrémentales ; mesure 4 : l'écart du sujet dépasse la durée de la porte (le défi revient
  sur la liste d'entrée), le bras banni l'est avant une visite reprise ;
- les identités sont neuves : aucune autre campagne ne les utilise ;
- `scripts/mesures-d103.sql` s'exécute sur le schéma de la base et compte les signaux par visite.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from test_visiteurs import nouveau_passage, nouvelle_experience

from shadowlab import campaigns
from shadowlab import database as db
from shadowlab.arena import profils as module_profils
from shadowlab.site import vitrine

RACINE = Path(__file__).resolve().parents[1]
EXPERIENCES = RACINE / "configs" / "experiments"
REPRISES = EXPERIENCES / "d103-visites-reprises.yaml"
INCREMENTALES = EXPERIENCES / "d103-passes-incrementales.yaml"
ENTREE = EXPERIENCES / "d103-entree-par-la-liste.yaml"
BAN_EN_VISITE = EXPERIENCES / "d103-bannissement-en-visite.yaml"
MESURES = (REPRISES, INCREMENTALES, ENTREE, BAN_EN_VISITE)
PROFIL_PORTE = RACINE / "configs" / "arena" / "profils-endurance-essai-porte.yaml"
SQL = RACINE / "scripts" / "mesures-d103.sql"
VERDICT = (
    'sqlite3 -readonly -header -column -cmd ".parameter set @n <n°>" '
    + "outputs/shadowlab.sqlite3 < scripts/mesures-d103.sql"
)
SUJET = {"headless": False, "channel": "chrome", "identite_native": True}


@pytest.fixture
def profil_porte(monkeypatch):
    monkeypatch.setenv("SHADOWLAB_PROFILS_EXTRA", str(PROFIL_PORTE))


def bras(experience):
    return {m.nom_affiche: m for m in experience.engines}


def _sujet_de_la_course(moteur, identite: str) -> None:
    assert moteur.name == "noezia" and moteur.recolte_incrementale
    assert moteur.options == {**SUJET, "identite": identite}


def test_mesure_1_les_visites_2_a_21_reprennent_la_passe(reglages):
    e = campaigns.lire(REPRISES, reglages)
    (sujet,) = e.engines
    _sujet_de_la_course(sujet, "d103-reprise-1")
    assert e.protections == ["endurance"] and e.scenarios == ["visite"] and e.monde == "serie"
    assert e.espacement.mode == "fixe" and e.espacement.minutes == 1 and e.concurrency == 1
    assert e.visites_de(sujet) == 21 and e.pages_par_visite == 15
    # même en lisant 15 pages neuves à chaque visite (sans aucune relecture), la passe de 315 pages n'est pas finie à la
    # fin de la 20e visite : la 21e la reprend encore
    assert (e.visites_de(sujet) - 1) * e.pages_par_visite < len(vitrine.pages_attendues(e.seed, 300)) == 315
    texte = REPRISES.read_text(encoding="utf-8")
    assert "SHADOWLAB_VITRINE_TAILLE=300 caffeinate -i uv run shadowlab campagne" in texte and VERDICT in texte


def test_mesure_2_au_moins_27_visites_sont_incrementales(reglages):
    e = campaigns.lire(INCREMENTALES, reglages)
    (sujet,) = e.engines
    _sujet_de_la_course(sujet, "d103-incrementale-1")
    assert e.protections == ["endurance"] and e.scenarios == ["visite"] and e.monde == "serie"
    assert e.visites_de(sujet) == 30 and e.pages_par_visite == 15 and e.espacement.minutes == 1
    # 32 pages par passe complète ; même avec un quart de relectures, 3 visites de 15 pages la finissent
    assert len(vitrine.pages_attendues(e.seed, 30)) == 32 <= 3 * e.pages_par_visite * 3 // 4
    texte = INCREMENTALES.read_text(encoding="utf-8")
    assert "SHADOWLAB_VITRINE_TAILLE=30 caffeinate -i uv run shadowlab campagne" in texte and VERDICT in texte


def test_mesure_4_la_porte_expire_entre_deux_visites_et_le_banni_l_est_avant_une_visite_reprise(reglages, profil_porte):
    e = campaigns.lire(ENTREE, reglages)
    b = bras(e)
    assert set(b) == {"sujet", "banni"} and e.protections == ["enduranceporte150"] and e.monde == "serie"
    _sujet_de_la_course(b["sujet"], "d103-porte-1")
    _sujet_de_la_course(b["banni"], "d103-banni-1")
    duree_porte = module_profils.charger().de("enduranceporte150").duree_cookie_s
    assert duree_porte == 150
    sujet = b["sujet"]
    assert sujet.espacement.mode == "fixe" and sujet.espacement.minutes * 60 > duree_porte  # porte expirée à l'entrée
    assert campaigns._reglages_visite(reglages, 1, sujet, "enduranceporte150")["duree_porte_s"] == duree_porte
    pages_passe = len(vitrine.pages_attendues(e.seed, 60))
    assert e.visites_de(sujet) == 5 and (e.visites_de(sujet) - 1) * e.pages_par_visite < pages_passe  # toutes reprises
    banni = b["banni"]
    assert banni.bannir_avant_visite == 3 and e.visites_de(banni) == 4
    assert (banni.bannir_avant_visite - 1) * e.pages_par_visite < pages_passe  # la 3e visite reprend la passe
    texte = ENTREE.read_text(encoding="utf-8")
    assert (
        "SHADOWLAB_PROFILS_EXTRA=configs/arena/profils-endurance-essai-porte.yaml uv run shadowlab arena appliquer"
        in texte
    )
    assert "SHADOWLAB_VITRINE_TAILLE=60" in texte and "SANS la variable : uv run shadowlab arena appliquer" in texte


def test_mesure_5_trois_longues_visites_et_le_geste_a_la_main(reglages):
    e = campaigns.lire(BAN_EN_VISITE, reglages)
    (sujet,) = e.engines
    _sujet_de_la_course(sujet, "d103-ban-en-visite-1")
    assert e.protections == ["endurance"] and e.visites_de(sujet) == 3 and e.pages_par_visite == 40
    assert sujet.bannir_avant_visite is None  # le bannissement se fait à la main, pendant la visite 2
    texte = BAN_EN_VISITE.read_text(encoding="utf-8")
    assert "uv run shadowlab arena bannir --visiteur <visiteur> --monde <nom>" in texte and VERDICT in texte


def test_les_identites_des_mesures_sont_neuves():
    def identites(fichier: Path) -> set[str]:
        donnees = yaml.safe_load(fichier.read_text(encoding="utf-8"))
        moteurs = [m for m in donnees["experiment"]["engines"] if isinstance(m, dict)]
        return {m.get("options", {}).get("identite") for m in moteurs} - {None}

    a_nous = [identites(f) for f in MESURES]
    assert sum(len(i) for i in a_nous) == len(set().union(*a_nous)) == 5
    autres = set().union(*(identites(f) for f in EXPERIENCES.glob("*.yaml") if f not in MESURES))
    assert not set().union(*a_nous) & autres


def _requetes(texte: str, n: int) -> list[str]:
    """Les requêtes du fichier, sans les commandes du client `sqlite3` (lignes en `.`) ni les commentaires, le paramètre
    remplacé."""
    sql = "\n".join(ligne for ligne in texte.splitlines() if not ligne.startswith((".", "--")))
    return [r.strip().replace("@n", str(n)) for r in sql.split(";") if r.strip()]


def test_la_requete_du_verdict_compte_les_signaux_par_visite(reglages):
    experience = nouvelle_experience(reglages, "d103")
    monde = f"c{experience}:sujet:endurance"
    jetons = [nouveau_passage(reglages, experience, repetition=k, monde=monde) for k in (1, 2)]
    cx = db.ouvrir(reglages.base_donnees)
    try:
        for jeton, signaux in zip(jetons, (["pas_de_scroll", "navigation_lineaire"], []), strict=True):
            run_id = cx.execute("SELECT id FROM runs WHERE session_token = ?", (jeton,)).fetchone()["id"]
            cx.execute(
                "INSERT INTO detections (run_id, detector_name, detector_version, classification, confidence, signals)"
                " VALUES (?, 'comportement', '1', 'automatise', 0.6, ?)",
                (run_id, json.dumps([{"code": c, "poids": 0.3} for c in signaux])),
            )
            drapeaux = {"details_scenario": {"passe": 1, "recolte": {"annonces_retrouvees": 8 * len(signaux) + 4}}}
            cx.execute("UPDATE runs SET success = 1, drapeaux = ? WHERE id = ?", (json.dumps(drapeaux), run_id))
        cx.commit()
        resultats = [cx.execute(r).fetchall() for r in _requetes(SQL.read_text(encoding="utf-8"), experience)]
    finally:
        cx.close()
    assert len(resultats) == 6 and resultats[5] == []  # aucun refus « bannissement » ici
    visites = {ligne["visite"]: ligne for ligne in resultats[0]}
    assert (visites[1]["pas_de_scroll"], visites[1]["nav_lineaire"], visites[1]["duree_reguliere"]) == (1, 1, 0)
    assert (visites[2]["pas_de_scroll"], visites[2]["nav_lineaire"]) == (0, 0) and visites[1][
        "bras"
    ] == "sujet:endurance"
    (bilan,) = resultats[4]
    assert (bilan["visites"], bilan["reussies"], bilan["pas_de_scroll"], bilan["nav_lineaire"]) == (2, 2, 1, 1)
