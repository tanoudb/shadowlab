"""Palier 2, I9 : les deux campagnes de la course, la course de 7 jours et sa répétition d'environ 1 h 30.

Temps simulé, aucun navigateur, aucune Arena. Ce que ces tests établissent :
- la course garde l'ordonnanceur du § 5.4 tel quel (aucun réglage), avec une échéance de 7 jours ; le plafond de 200
  visites du sujet ne borne jamais la course avant l'échéance ; les témoins finissent dans les 24 premières heures ;
- la répétition a le profil `endurancecourt`, la plage 0-24 h, des écarts de 1 à 4 min et les plafonds de pages
  d'origine ; avec sa graine, le sujet fait au moins 10 visites, la 1re de 5 pages et la 2e de 40 (tirées par
  l'ordonnanceur, aucun plafond ne les impose), par le vrai code de la campagne ;
- les identités sont neuves (une identité bannie ne sert plus) et différentes d'une campagne à l'autre.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from test_course_cadence import PassagesDates, iso
from test_espacement import Horloge, faux_pilote, rang_de

from shadowlab import campaigns, espacement
from shadowlab import database as db
from shadowlab.engines.noezia import visites

RACINE = Path(__file__).resolve().parents[1]
COURSE = RACINE / "configs" / "experiments" / "identite-7-jours.yaml"
REPETITION = RACINE / "configs" / "experiments" / "identite-7-jours-repetition.yaml"
PROFILS_COURTS = RACINE / "configs" / "arena" / "profils-endurance-court.yaml"
SOIREES = [RACINE / "configs" / "experiments" / f for f in ("identite-soiree.yaml", "identite-soiree-essai.yaml")]
ROLES = {"sujet", "temoin-negatif", "temoin-sentinelle", "temoin-classique"}
PLAFONDS = ("pages_min", "pages_med", "pages_max", "pages_par_heure", "pages_par_jour", "duree_visite_max_min")


@pytest.fixture
def profil_court(monkeypatch):
    monkeypatch.setenv("SHADOWLAB_PROFILS_EXTRA", str(PROFILS_COURTS))


def bras(experience):
    return {m.nom_affiche: m for m in experience.engines}


def identites(experience):
    return {m.options.get("identite") for m in experience.engines} - {None}


def test_la_course_de_7_jours_garde_l_ordonnanceur_du_paragraphe_5_4(reglages):
    e = campaigns.lire(COURSE, reglages)
    b = bras(e)
    assert set(b) == ROLES and e.protections == ["endurance"] and e.scenarios == ["visite"] and e.monde == "serie"
    assert e.espacement.mode == "ordonnanceur" and e.espacement.jours == 7 and e.espacement.reglages == {}
    assert e.espacement.reglages_ordonnanceur() == visites.Reglages()  # § 5.4, aucune valeur touchée
    sujet = b["sujet"]
    assert sujet.espacement is None and sujet.recolte_incrementale and sujet.options["identite"] == "course-sujet-1"
    assert b["temoin-sentinelle"].options["identite"] == "course-sentinelle-1"
    assert b["temoin-sentinelle"].bannir_avant_visite == 3
    assert e.visites_de(b["temoin-negatif"]) >= 5  # 5 sessions neuves de même empreinte en 24 h : il doit être pris
    for role in ROLES - {"sujet"}:
        m = b[role]
        assert m.espacement.mode == "fixe" and not m.recolte_incrementale
        assert e.visites_de(m) * (m.espacement.minutes + visites.Reglages().duree_visite_max_min) < 24 * 60
    texte = COURSE.read_text(encoding="utf-8")
    assert "SHADOWLAB_VITRINE_TAILLE=300" in texte and "shadowlab course bilan" in texte


def test_le_plafond_de_visites_du_sujet_ne_borne_jamais_la_course_avant_l_echeance(reglages):
    """7 jours d'ordonnanceur en temps simulé (visites de 1 min plus 9 s par page) : bien moins de 200 visites, toutes
    dans la plage, au plus 200 pages par jour ; c'est l'échéance qui finit la course."""
    e = campaigns.lire(COURSE, reglages)
    depart = datetime(2026, 11, 17, 10, 0)
    horloge = Horloge(depart)
    cadence = espacement.Cadence(
        e.espacement, horloge=horloge.now, dormir=horloge.dormir, graine=f"{e.seed}:sujet:endurance", depart=depart,
        faites=[], notes=[], noter=lambda ligne: None, pas_s=3600,
    )  # fmt: skip
    faites = []
    while not (creneau := cadence.attendre()).echeance:
        faites.append((creneau.debut, creneau.pages))
        horloge.avancer(60 + 9 * creneau.pages)
        cadence.terminer(creneau, creneau.pages)
    assert 7 * 5 <= len(faites) < e.visites_de(bras(e)["sujet"])
    assert all(8 <= debut.hour and debut <= debut.replace(hour=22, minute=30) for debut, _ in faites)
    par_jour = {}
    for debut, pages in faites:
        par_jour[debut.date()] = par_jour.get(debut.date(), 0) + pages
    assert max(par_jour.values()) <= 200
    assert faites[-1][0] < depart + timedelta(days=7)


def test_la_repetition_se_lit_avec_le_profil_court(reglages, profil_court):
    e = campaigns.lire(REPETITION, reglages)
    b = bras(e)
    assert set(b) == ROLES and e.protections == ["endurancecourt"] and e.scenarios == ["visite"]
    assert e.espacement.mode == "ordonnanceur" and 0 < e.espacement.jours <= 0.07  # environ 1 h 30
    r = e.espacement.reglages_ordonnanceur()
    assert r.plage == (0, 24) and (r.ecart_min_min, r.ecart_max_min) == (1, 4)
    assert all(getattr(r, champ) == getattr(visites.Reglages(), champ) for champ in PLAFONDS)
    assert b["sujet"].recolte_incrementale and b["temoin-sentinelle"].bannir_avant_visite == 3
    assert e.visites_de(b["temoin-negatif"]) >= 5 and e.pages_par_visite == 3
    assert all(b[role].espacement.mode == "fixe" for role in ROLES - {"sujet"})
    texte = REPETITION.read_text(encoding="utf-8")
    assert "SHADOWLAB_VITRINE_TAILLE=30 " in texte
    assert "SHADOWLAB_PROFILS_EXTRA=configs/arena/profils-endurance-court.yaml" in texte


def test_les_identites_sont_neuves_et_propres_a_chaque_campagne(reglages, profil_court):
    course, repetition = campaigns.lire(COURSE, reglages), campaigns.lire(REPETITION, reglages)
    soirees = set().union(*(identites(campaigns.lire(f, reglages)) for f in SOIREES))
    assert identites(course) == {"course-sujet-1", "course-sentinelle-1"}
    assert len(identites(repetition)) == 2 and not identites(repetition) & (identites(course) | soirees)


class PassagesPrevus(PassagesDates):
    """Chaque visite lit toutes les pages que l'ordonnanceur lui donne (borne haute : les plafonds jouent au plus) et
    dure `fixe_s` plus `par_page_s` par page."""

    def __init__(self, horloge, fixe_s, par_page_s):
        super().__init__(horloge)
        self.fixe_s, self.par_page_s = fixe_s, par_page_s

    def __call__(self, cx, reglages, experience, experiment_id, pilote, engine_id, scenario, *args, **kwargs):
        self.pages = scenario.executer.keywords["pages"]
        self.duree_s = self.fixe_s + self.par_page_s * self.pages
        return super().__call__(cx, reglages, experience, experiment_id, pilote, engine_id, scenario, *args, **kwargs)


@pytest.mark.parametrize(("fixe_s", "par_page_s"), [(60, 15), (90, 20)])
def test_avec_sa_graine_la_repetition_donne_une_visite_de_5_pages_puis_une_de_40(
    reglages, profil_court, monkeypatch, fixe_s, par_page_s
):
    experience = campaigns.lire(REPETITION, reglages)
    cx = db.ouvrir(reglages.base_donnees)
    experiment_id = campaigns.creer(cx, experience, reglages)
    depart = datetime(2026, 11, 17, 14, 0)
    cx.execute("UPDATE experiments SET created_at = ? WHERE id = ?", (iso(depart), experiment_id))
    monkeypatch.setattr(campaigns, "registre", lambda: {"noezia": faux_pilote(), "playwright": faux_pilote()})
    monkeypatch.setattr(campaigns, "_panne_infrastructure", lambda reglages, protection: None)
    horloge = Horloge(depart)
    passages = PassagesPrevus(horloge, fixe_s, par_page_s)
    monkeypatch.setattr(campaigns, "_passage", passages)
    rang = rang_de(experience, "sujet")
    assert (
        campaigns.executer_unite(reglages, experiment_id, rang, horloge=horloge.now, dormir=horloge.dormir) == "termine"
    )
    prevues = passages.creneaux
    assert len(prevues) >= 10 and prevues[:2] == [5, 40], prevues
    echeance = depart + timedelta(days=experience.espacement.jours)
    assert all(q < echeance for q in passages.quand)
    fichier = campaigns.dossier_campagne(reglages, experiment_id) / campaigns.FICHIER_CADENCE
    [fin] = [n for n in map(json.loads, fichier.read_text(encoding="utf-8").splitlines()) if n["genre"] == "echeance"]
    assert fin["restantes"] == experience.visites_de(bras(experience)["sujet"]) - len(prevues)
    cx.close()
