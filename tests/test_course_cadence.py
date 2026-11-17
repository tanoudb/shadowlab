"""Palier 2, I9 (course de 7 jours) : la cadence survit à une coupure, les visites manquées, les pannes, l'échéance.

Temps simulé (horloge et sommeil injectés), aucun navigateur, aucune Arena : le passage est remplacé par une fonction
qui écrit la ligne `runs` comme la campagne le ferait, aux heures de l'horloge factice. Ce que ces tests établissent :
1. la cadence reprend les visites déjà faites par le bras (base, et visite coupée en plein milieu) par
   `Ordonnanceur.rejouer` : écart, plafonds et plage tenus après un arrêt brutal ;
2. un créneau pris trop tard (Mac endormi, processus arrêté, reprise tardive) est manqué, noté, jamais joué ;
3. une panne de la chaîne de l'Arena ou du site n'est pas une alerte : la visite n'est pas lancée, réessai 5 min après ;
4. après l'échéance (`jours`), plus aucune visite ne commence.
"""

# ruff: noqa: E501  (requêtes SQL et configurations YAML en ligne)
from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest
from test_espacement import BRAS, Horloge, campagne, faux_pilote, rang_de

from shadowlab import campaigns, espacement
from shadowlab import database as db
from shadowlab.engines.noezia import visites

T0 = datetime(2026, 11, 17, 10, 0, 0)  # un mardi matin, dans la plage 8 h - 23 h
# Écart de 45 à 47 min (plafonds et plage inchangés) : rend l'heure d'un créneau prévisible à 2 min près.
ECART_COURT = {"ecart_min_min": 45, "ecart_med_min": 46, "ecart_max_min": 47}


def iso(t: datetime) -> str:
    """Une heure de l'horloge locale (naïve) écrite comme la base l'écrit (avec son décalage)."""
    return t.astimezone().isoformat(timespec="milliseconds")


class Notes(list):
    """Les notes durables écrites par la cadence, sans la note `prevue` (heure de la prochaine visite : un relevé, pas un
    état ; elle est testée dans `test_course_etat.py`)."""

    def append(self, ligne):
        if ligne.get("genre") != "prevue":
            super().append(ligne)


def cadence(horloge, *, faites=(), notes=(), depart=None, noter=None, graine=7, **champs):
    reglage = espacement.Espacement(mode="ordonnanceur", **champs)
    return espacement.Cadence(
        reglage, horloge=horloge.now, dormir=horloge.dormir, graine=graine, depart=depart, faites=faites,
        notes=notes, noter=noter,
    )  # fmt: skip


# ── 1. La cadence reprend les visites faites (Ordonnanceur.rejouer) ─────────────────────────────


def test_la_cadence_rejoue_les_visites_faites_par_l_ordonnanceur(monkeypatch):
    appels = []
    original = visites.Ordonnanceur.rejouer

    def espion(self, faites):
        appels.append(sorted(faites))
        return original(self, faites)

    monkeypatch.setattr(visites.Ordonnanceur, "rejouer", espion)
    horloge = Horloge(T0)
    faites = [(T0 - timedelta(minutes=12), T0 - timedelta(minutes=10), 15)]
    creneau = cadence(horloge, faites=faites).attendre()
    assert appels and appels[-1] == faites
    # l'écart de 45 min au moins se compte depuis la fin de la visite d'avant, pas depuis le lancement
    assert creneau.debut >= T0 - timedelta(minutes=10) + timedelta(minutes=45)
    assert horloge.now() == creneau.debut


def test_apres_une_reprise_les_plafonds_par_heure_et_par_jour_tiennent():
    """110 pages lues dans l'heure : la visite suivante en lit au plus 10 ; 200 dans la journée : elle passe à demain."""
    horloge = Horloge(T0)
    heure = [(T0 - timedelta(minutes=30), T0 - timedelta(minutes=10), 110)]
    creneau = cadence(horloge, faites=heure, reglages=ECART_COURT).attendre()
    assert creneau.pages <= 10
    horloge = Horloge(T0)
    jour = [(T0 - timedelta(hours=h + 2), T0 - timedelta(hours=h + 1, minutes=50), 40) for h in range(5)]
    creneau = cadence(horloge, faites=jour).attendre()
    assert creneau.debut.date() == T0.date() + timedelta(days=1) and 8 <= creneau.debut.hour <= 9


def test_le_meme_creneau_est_recalcule_apres_un_redemarrage():
    """L'état durable (visites faites, notes, départ) suffit à retrouver le créneau prévu : il ne vit pas en mémoire."""
    faites = [(T0 - timedelta(minutes=12), T0 - timedelta(minutes=10), 15)]
    premier = cadence(Horloge(T0), faites=faites)._prochain()
    plus_tard = Horloge(T0 + timedelta(minutes=20))  # redémarré avant l'heure prévue
    assert cadence(plus_tard, faites=faites)._prochain() == premier
    assert cadence(plus_tard, faites=faites).attendre().debut == premier.debut


def test_en_mode_fixe_une_reprise_garde_l_ecart_depuis_la_derniere_fin():
    horloge = Horloge(T0)
    reglage = espacement.Espacement(mode="fixe", minutes=10)
    c = espacement.Cadence(
        reglage,
        horloge=horloge.now,
        dormir=horloge.dormir,
        faites=[(T0 - timedelta(minutes=5), T0 - timedelta(minutes=4), 3)],
    )
    assert c.attendre().debut == T0 + timedelta(minutes=6)


# ── 2. Visite manquée ──────────────────────────────────────────────────────────────────────────


class MacQuiDort(Horloge):
    """Le Mac s'endort pendant la première pause longue de `apres_s` secondes : l'horloge saute de `duree_s`."""

    def __init__(self, depart, duree_s, apres_s=0.0):
        super().__init__(depart)
        self.duree_s, self.apres_s, self.endormi = duree_s, apres_s, False

    def dormir(self, secondes):
        super().dormir(secondes)
        if not self.endormi and sum(self.pauses) >= self.apres_s:
            self.endormi = True
            self.t += timedelta(seconds=self.duree_s)


def test_un_creneau_pris_trop_tard_est_manque_note_puis_replanifie_depuis_maintenant():
    horloge = MacQuiDort(T0, duree_s=4 * 3600)
    notes = Notes()
    faites = [(T0 - timedelta(minutes=12), T0 - timedelta(minutes=10), 15)]
    c = cadence(horloge, faites=faites, noter=notes.append)
    prevu = c._prochain().debut
    creneau = c.attendre()
    assert len(notes) == 1
    note = notes[0]
    assert note["genre"] == "manquee" and note["motif"] == "retard"
    assert datetime.fromisoformat(note["prevue"]).replace(tzinfo=None) == prevu
    constatee = datetime.fromisoformat(note["constatee"]).replace(tzinfo=None)
    assert constatee - prevu > timedelta(minutes=10)
    # replanifié depuis maintenant : l'écart depuis la dernière fin est passé depuis longtemps, la visite part tout de suite
    assert creneau.debut == constatee and horloge.now() == constatee and 8 <= creneau.debut.hour < 23


def test_un_retard_sous_le_seuil_n_est_pas_une_visite_manquee():
    horloge = MacQuiDort(T0, duree_s=5 * 60)  # 5 minutes de veille juste avant l'heure : sous les 10 minutes
    notes = Notes()
    faites = [(T0 - timedelta(minutes=12), T0 - timedelta(minutes=10), 15)]
    c = cadence(horloge, faites=faites, noter=notes.append)
    prevu = c._prochain().debut
    horloge.apres_s = (prevu - T0).total_seconds() - 1
    assert c.attendre().debut == prevu and notes == []
    assert horloge.now() - prevu > timedelta(minutes=4)


def test_un_creneau_qui_tomberait_hors_de_la_plage_n_est_jamais_joue():
    """Seuil de retard très large : la visite n'est pas en retard au sens du seuil, mais l'heure constatée est passée
    au-delà de la dernière heure de début (23 h moins 30 min) : manquée, et la suivante est demain matin."""
    soir = datetime(2026, 11, 17, 21, 0)
    horloge = MacQuiDort(soir, duree_s=2 * 3600)  # créneau vers 21 h 45, réveil vers 23 h 45
    notes = Notes()
    faites = [(soir - timedelta(minutes=2), soir, 15)]
    c = cadence(horloge, faites=faites, noter=notes.append, retard_max_min=600, reglages=ECART_COURT)
    creneau = c.attendre()
    assert [n["motif"] for n in notes] == ["retard"]
    assert creneau.debut.date() == soir.date() + timedelta(days=1) and 8 <= creneau.debut.hour <= 9


def test_une_reprise_tardive_retrouve_le_creneau_et_le_compte_manque():
    """Processus arrêté puis relancé une heure après l'heure prévue : le créneau recalculé est en retard, il est noté."""
    faites = [(T0 - timedelta(minutes=12), T0 - timedelta(minutes=10), 15)]
    prevu = cadence(Horloge(T0), faites=faites)._prochain().debut
    notes = Notes()
    relance = Horloge(prevu + timedelta(hours=1))
    c = cadence(relance, faites=faites, noter=notes.append)
    creneau = c.attendre()
    assert [n["motif"] for n in notes] == ["retard"]
    assert datetime.fromisoformat(notes[0]["prevue"]).replace(tzinfo=None) == prevu
    assert creneau.debut == relance.now()


def test_la_premiere_visite_se_planifie_depuis_le_depart_durable_de_la_course():
    """Sans visite faite, la référence est le départ de la course (création de l'expérience) : une relance tardive
    avant toute visite est aussi une visite manquée."""
    notes = Notes()
    depart = T0 - timedelta(hours=2)
    c = cadence(Horloge(T0), depart=depart, noter=notes.append)
    creneau = c.attendre()
    assert [n["motif"] for n in notes] == ["retard"]
    assert datetime.fromisoformat(notes[0]["prevue"]).replace(tzinfo=None) == depart
    assert creneau.debut == T0


def test_les_notes_relues_font_partie_de_l_etat():
    """Une visite manquée déjà notée (fichier relu à la reprise) n'est pas notée deux fois : le créneau suivant se
    planifie depuis l'heure où elle a été constatée."""
    faites = [(T0 - timedelta(hours=4), T0 - timedelta(hours=3, minutes=58), 15)]
    deja = {
        "genre": "manquee",
        "motif": "retard",
        "prevue": iso(T0 - timedelta(hours=1)),
        "constatee": iso(T0 - timedelta(minutes=2)),
    }
    notes = Notes()
    c = cadence(Horloge(T0), faites=faites, notes=[deja], noter=notes.append)
    creneau = c.attendre()
    assert notes == [] and creneau.debut <= T0


# ── 3. Panne d'infrastructure ───────────────────────────────────────────────────────────────────


def test_une_panne_n_est_pas_jouee_on_reessaie_5_minutes_apres_et_une_seule_visite_manquee_est_comptee():
    horloge = Horloge(T0)
    notes = Notes()
    faites = [(T0 - timedelta(minutes=12), T0 - timedelta(minutes=10), 15)]
    c = cadence(horloge, faites=faites, noter=notes.append)
    premier = c.attendre()
    c.manquer(premier, "infrastructure", "Arena injoignable")
    second = c.attendre()
    assert second.debut == premier.debut + timedelta(minutes=5)
    c.manquer(second, "infrastructure", "Arena injoignable")
    troisieme = c.attendre()
    assert troisieme.debut == premier.debut + timedelta(minutes=10)
    assert [n["motif"] for n in notes] == ["infrastructure", "infrastructure"]
    assert {n["creneau"] for n in notes} == {notes[0]["creneau"]}  # un seul créneau manqué, deux essais
    assert [n["essai"] for n in notes] == [1, 2]


def test_un_reessai_qui_tomberait_hors_de_la_plage_part_a_la_prochaine_ouverture():
    soir = datetime(2026, 11, 17, 21, 42)
    horloge = Horloge(soir)
    faites = [(soir - timedelta(minutes=2), soir, 15)]  # créneau vers 22 h 28, réessai vers 22 h 33 : hors plage
    c = cadence(horloge, faites=faites, noter=lambda _: None, reglages=ECART_COURT)
    premier = c.attendre()
    assert premier.debut.hour == 22 and premier.debut.minute < 30
    c.manquer(premier, "infrastructure", "site injoignable")
    suivant = c.attendre()
    assert suivant.debut.date() == soir.date() + timedelta(days=1) and 8 <= suivant.debut.hour <= 9


# ── 4. Échéance ─────────────────────────────────────────────────────────────────────────────────


def test_apres_l_echeance_plus_aucune_visite_ne_commence():
    depart = T0 - timedelta(hours=6)
    faites = [(T0 - timedelta(minutes=12), T0 - timedelta(minutes=10), 15)]  # la suivante, 45 min au moins après
    horloge = Horloge(T0)
    c = cadence(horloge, faites=faites, depart=depart, jours=6.5 / 24)  # échéance à T0 + 30 min
    creneau = c.attendre()
    assert creneau.echeance is True and horloge.pauses == []  # rien à attendre : aucune visite ne commencera


def test_un_reveil_apres_l_echeance_n_est_ni_une_visite_ni_une_visite_manquee():
    depart = T0 - timedelta(hours=6)
    faites = [(T0 - timedelta(minutes=12), T0 - timedelta(minutes=10), 15)]
    horloge = MacQuiDort(T0, duree_s=6 * 3600)
    notes = Notes()
    c = cadence(
        horloge, faites=faites, depart=depart, jours=8 / 24, noter=notes.append, reglages=ECART_COURT
    )  # échéance T0 + 2 h
    assert c._prochain().debut < depart + timedelta(hours=8)
    creneau = c.attendre()
    assert creneau.echeance is True and notes == []


@pytest.mark.parametrize(
    "champs",
    [
        {"mode": "fixe", "minutes": 10, "jours": 7},  # l'échéance est celle de l'ordonnanceur
        {"mode": "ordonnanceur", "jours": 0},
        {"mode": "ordonnanceur", "retard_max_min": 0},
    ],
)
def test_reglages_de_la_course_invalides(champs):
    with pytest.raises(ValueError):
        espacement.Espacement(**champs)


def test_reglages_de_la_course_valides():
    e = espacement.Espacement(mode="ordonnanceur", jours=7)
    assert e.jours == 7 and e.retard_max_min == 10


# ── Dans la campagne : base, visite coupée, panne, échéance, espacement par bras ─────────────────


class PassagesDates:
    """Remplace `campaigns._passage` : écrit la ligne `runs` aux heures de l'horloge factice (début, fin), comme la
    campagne, avec les pages lues par la visite. `duree_s` : durée d'une visite."""

    def __init__(self, horloge, pages=15, duree_s=120):
        self.horloge, self.pages, self.duree_s = horloge, pages, duree_s
        self.quand: list[datetime] = []
        self.creneaux: list[int] = []

    def __call__(self, cx, reglages, experience, experiment_id, pilote, engine_id, scenario, scenario_id, repetition,
                 protection, base, rng, dossier_artefacts, engine_version="", monde=None):  # fmt: skip
        debut = self.horloge.now()
        self.quand.append(debut)
        self.creneaux.append(
            scenario.executer.keywords.get("pages") if hasattr(scenario.executer, "keywords") else None
        )
        self.horloge.avancer(self.duree_s)
        cx.execute(
            "INSERT INTO runs (experiment_id, engine_id, scenario_id, repetition, session_token, truth, started_at,"
            " completed_at, status, success, protection, drapeaux) VALUES (?, ?, ?, ?, ?, 'automatise', ?, ?, 'reussi', 1, ?, ?)",
            (experiment_id, engine_id, scenario_id, repetition, f"t-{engine_id}-{repetition}", iso(debut),
             iso(self.horloge.now()), protection, json.dumps({"details_scenario": {"pages_visite": self.pages}})),
        )  # fmt: skip
        return {"pages_faites": self.pages, "pages_visite": self.pages}


ORDONNANCEUR = "  espacement: {mode: ordonnanceur, jours: 7}\n  concurrency: 4\n"


@pytest.fixture
def campagne_ordonnanceur(tmp_path, reglages, monkeypatch):
    experience = campagne(tmp_path, reglages, extra=ORDONNANCEUR)
    cx = db.ouvrir(reglages.base_donnees)
    experiment_id = campaigns.creer(cx, experience, reglages)
    cx.execute("UPDATE experiments SET created_at = ? WHERE id = ?", (iso(T0 - timedelta(minutes=1)), experiment_id))
    pilote = faux_pilote()
    monkeypatch.setattr(campaigns, "registre", lambda: {"noezia": pilote, "playwright": pilote})
    monkeypatch.setattr(campaigns, "_panne_infrastructure", lambda reglages, protection: None)
    yield experience, cx, experiment_id
    cx.close()


def notes_du_fichier(reglages, experiment_id):
    fichier = campaigns.dossier_campagne(reglages, experiment_id) / campaigns.FICHIER_CADENCE
    return [json.loads(ligne) for ligne in fichier.read_text(encoding="utf-8").splitlines() if ligne.strip()]


def test_un_arret_brutal_pendant_une_visite_puis_une_reprise_garde_l_ecart_et_les_plafonds(
    campagne_ordonnanceur, reglages, monkeypatch
):
    """La visite coupée en plein milieu (ligne `en_cours`, 118 pages vues par l'Arena) est notée avant d'être effacée,
    puis rejouée : la visite suivante attend la fin de l'heure (plafond de 120 pages) et 45 min au moins."""
    experience, cx, experiment_id = campagne_ordonnanceur
    rang = rang_de(experience, "sujet")
    moteur = db.engine_id(cx, "noezia", "{}", "navigateur", {"label": "sujet"})
    scenario = db.scenario_id(cx, "visite", "visite")
    debut, derniere = T0 - timedelta(minutes=20), T0 - timedelta(minutes=2)
    cx.execute(
        "INSERT INTO runs (experiment_id, engine_id, scenario_id, repetition, session_token, truth, started_at, status,"
        " protection) VALUES (?, ?, ?, 1, 'coupee', 'automatise', ?, 'en_cours', 'endurance')",
        (experiment_id, moteur, scenario, iso(debut)),
    )
    for n in range(118):
        cx.execute(
            "INSERT INTO observations_http (session_token, received_at, method, path, headers, cookies, status)"
            " VALUES ('coupee', ?, 'GET', ?, '{}', '{}', 200)",
            (iso(debut + (derniere - debut) * n / 117), f"/lab/vitrine/annonces/AN-{n:06d}"),
        )
    campaigns.preparer_reprise(cx, reglages, experiment_id)
    assert cx.execute("SELECT COUNT(*) FROM runs WHERE session_token = 'coupee'").fetchone()[0] == 0
    [coupee] = [n for n in notes_du_fichier(reglages, experiment_id) if n["genre"] == "interrompue"]
    assert coupee["bras"] == "sujet" and coupee["pages"] == 118
    horloge = Horloge(T0)
    passages = PassagesDates(horloge)
    monkeypatch.setattr(campaigns, "_passage", passages)
    experience_courte = experience.model_copy(update={"repetitions": 1})
    cx.execute(
        "UPDATE experiments SET configuration = ? WHERE id = ?", (experience_courte.model_dump_json(), experiment_id)
    )
    assert (
        campaigns.executer_unite(reglages, experiment_id, rang, horloge=horloge.now, dormir=horloge.dormir) == "termine"
    )
    assert len(passages.quand) == 1
    assert passages.quand[0] >= derniere + timedelta(hours=1)  # 118 pages dans l'heure : moins des 5 pages minimales


def test_dans_la_campagne_les_visites_faites_sont_relues_dans_la_base(campagne_ordonnanceur, reglages, monkeypatch):
    experience, cx, experiment_id = campagne_ordonnanceur
    rang = rang_de(experience, "sujet")
    horloge = Horloge(T0)
    passages = PassagesDates(horloge)
    monkeypatch.setattr(campaigns, "_passage", passages)
    deux = experience.model_copy(update={"repetitions": 2})
    cx.execute("UPDATE experiments SET configuration = ? WHERE id = ?", (deux.model_dump_json(), experiment_id))
    assert (
        campaigns.executer_unite(reglages, experiment_id, rang, horloge=horloge.now, dormir=horloge.dormir) == "termine"
    )
    trois = experience.model_copy(update={"repetitions": 3})
    cx.execute("UPDATE experiments SET configuration = ? WHERE id = ?", (trois.model_dump_json(), experiment_id))
    fin_deuxieme = passages.quand[1] + timedelta(seconds=passages.duree_s)
    assert (
        campaigns.executer_unite(reglages, experiment_id, rang, horloge=horloge.now, dormir=horloge.dormir) == "termine"
    )
    assert len(passages.quand) == 3
    assert passages.quand[2] - fin_deuxieme >= timedelta(minutes=45)  # la reprise ne repart pas tout de suite


def test_dans_la_campagne_une_panne_ne_lance_pas_la_visite(campagne_ordonnanceur, reglages, monkeypatch):
    experience, cx, experiment_id = campagne_ordonnanceur
    rang = rang_de(experience, "sujet")
    horloge = Horloge(T0)
    passages = PassagesDates(horloge)
    monkeypatch.setattr(campaigns, "_passage", passages)
    pannes = iter(["chaîne de l'Arena injoignable", "site du labo injoignable", None])
    sondes = []

    def sante(reglages, protection):
        sondes.append(horloge.now())
        return next(pannes, None)

    monkeypatch.setattr(campaigns, "_panne_infrastructure", sante)
    une = experience.model_copy(update={"repetitions": 1})
    cx.execute("UPDATE experiments SET configuration = ? WHERE id = ?", (une.model_dump_json(), experiment_id))
    assert (
        campaigns.executer_unite(reglages, experiment_id, rang, horloge=horloge.now, dormir=horloge.dormir) == "termine"
    )
    assert len(passages.quand) == 1 and passages.quand[0] == sondes[2]  # lancée au 3e essai seulement
    assert [b - a for a, b in zip(sondes, sondes[1:], strict=False)] == [timedelta(minutes=5)] * 2
    manquees = [n for n in notes_du_fichier(reglages, experiment_id) if n["genre"] == "manquee"]
    assert [(n["motif"], n["essai"], n["bras"]) for n in manquees] == [
        ("infrastructure", 1, "sujet"),
        ("infrastructure", 2, "sujet"),
    ]


def test_dans_la_campagne_l_echeance_arrete_le_bras_sans_echec(campagne_ordonnanceur, reglages, monkeypatch):
    experience, cx, experiment_id = campagne_ordonnanceur
    rang = rang_de(experience, "sujet")
    horloge = Horloge(T0)
    passages = PassagesDates(horloge)
    monkeypatch.setattr(campaigns, "_passage", passages)
    # échéance 4 h après le départ : la plage du jour en permet une poignée, sur 24 répétitions prévues
    courte = experience.model_copy(update={"espacement": espacement.Espacement(mode="ordonnanceur", jours=4 / 24)})
    cx.execute("UPDATE experiments SET configuration = ? WHERE id = ?", (courte.model_dump_json(), experiment_id))
    assert (
        campaigns.executer_unite(reglages, experiment_id, rang, horloge=horloge.now, dormir=horloge.dormir) == "termine"
    )
    echeance = T0 - timedelta(minutes=1) + timedelta(hours=4)
    assert 1 <= len(passages.quand) < 24 and all(q < echeance for q in passages.quand)
    statuts = {r[0] for r in cx.execute("SELECT status FROM runs WHERE experiment_id = ?", (experiment_id,))}
    assert statuts == {"reussi"}  # aucune répétition restante écrite en échec
    [fin] = [n for n in notes_du_fichier(reglages, experiment_id) if n["genre"] == "echeance"]
    assert fin["bras"] == "sujet" and fin["restantes"] == 24 - len(passages.quand)


TEMOINS_FIXES = BRAS.replace(
    "      label: temoin-classique\n      visites: 4\n",
    "      label: temoin-classique\n      visites: 4\n      espacement: {mode: fixe, minutes: 10}\n",
)


def test_un_bras_peut_avoir_son_propre_espacement(tmp_path, reglages, monkeypatch):
    """Le sujet suit l'ordonnanceur de la campagne ; un témoin a son espacement fixe (il finit le premier jour)."""
    experience = campagne(tmp_path, reglages, engines=TEMOINS_FIXES, extra=ORDONNANCEUR)
    temoin = next(m for m in experience.engines if m.nom_affiche == "temoin-classique")
    assert temoin.espacement.mode == "fixe" and experience.espacement.mode == "ordonnanceur"
    cx = db.ouvrir(reglages.base_donnees)
    experiment_id = campaigns.creer(cx, experience, reglages)
    monkeypatch.setattr(campaigns, "registre", lambda: {"noezia": faux_pilote(), "playwright": faux_pilote()})
    monkeypatch.setattr(campaigns, "_panne_infrastructure", lambda reglages, protection: None)
    horloge = Horloge(T0)
    passages = PassagesDates(horloge)
    monkeypatch.setattr(campaigns, "_passage", passages)
    rang = rang_de(experience, "temoin-classique")
    assert (
        campaigns.executer_unite(reglages, experiment_id, rang, horloge=horloge.now, dormir=horloge.dormir) == "termine"
    )
    assert [(b - a).total_seconds() for a, b in zip(passages.quand, passages.quand[1:], strict=False)] == [720.0] * 3


def test_un_espacement_de_bras_exige_le_scenario_visite(tmp_path, reglages):
    from test_campagnes import ecrire

    texte = ecrire(
        tmp_path,
        """
experiment:
  name: x
  engines:
    - {name: playwright, espacement: {mode: fixe, minutes: 1}}
  scenarios: [static_html]
  repetitions: 2
""",
    )
    with pytest.raises(ValueError, match="visite"):
        campaigns.lire(texte, reglages)
