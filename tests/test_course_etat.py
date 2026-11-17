"""Palier 2, I9 : `shadowlab course etat`, l'état de la course de 7 jours d'un coup d'oeil (contrôle d'une fois par jour).

Lu dans la base (SQLite en lecture seule), dans `cadence.jsonl` et dans l'état des identités ; aucune requête vers
l'Arena, rien n'est écrit. Codes de sortie : 0 en cours sans anomalie ou finie à l'échéance, 1 arrêtée, 2 retard anormal
ou blocage, 3 course ou campagne introuvable. La note `prevue` (heure de la prochaine visite) est écrite par la cadence au
moment où elle choisit le créneau, avant l'attente. Données fabriquées (aucune donnée de visiteur réelle).
"""

# ruff: noqa: E501  (requêtes SQL et données en ligne)
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from test_course_bilan import DEPART, ENGINS, JOUR, heure, visite_course
from test_espacement import Horloge, campagne
from test_soiree import monde

from shadowlab import campaigns, course_etat, espacement, passages
from shadowlab import database as db
from shadowlab.cli import main

RACINE = Path(__file__).resolve().parent.parent
JOUR2 = DEPART + timedelta(days=1, hours=2)  # jour 2 de la course, 10 h 30


@pytest.fixture
def base(tmp_path, reglages):
    experience = campagne(
        tmp_path, reglages, engines=ENGINS, extra="  espacement: {mode: ordonnanceur, jours: 7}\n  concurrency: 4\n"
    )
    cx = db.ouvrir(reglages.base_donnees)
    experiment_id = campaigns.creer(cx, experience, reglages)
    cx.execute(
        "UPDATE experiments SET created_at = ?, status = 'en_cours' WHERE id = ?", (DEPART.isoformat(), experiment_id)
    )
    yield cx, experiment_id
    cx.close()


def depuis(minutes: float, *, quand: datetime = JOUR2) -> str:
    return (quand - timedelta(minutes=minutes)).isoformat(timespec="seconds")


def note(reglages, x, **champs):
    campaigns.ecrire_note(reglages, x, {"bras": "sujet", "protection": "endurance", **champs})


def prevue(reglages, x, *, dans_min, ecrite_il_y_a=60, bras="sujet", quand=JOUR2):
    """La note `prevue` de la cadence : visite prévue dans `dans_min` minutes (négatif : déjà dépassée)."""
    note(
        reglages,
        x,
        bras=bras,
        genre="prevue",
        prevue=(quand + timedelta(minutes=dans_min)).isoformat(timespec="seconds"),
        ecrite=depuis(ecrite_il_y_a, quand=quand),
    )


def en_cours(cx, x, label, rang, depuis_min, *, quand=JOUR2):
    """Un passage `en_cours` commencé il y a `depuis_min` minutes."""
    moteur = db.engine_id(cx, "noezia", "{}", "navigateur", {"label": label})
    scenario = db.scenario_id(cx, "visite", "visite")
    run_id, _ = passages.demarrer(cx, x, moteur, scenario, rang, "automatise", "endurance", monde=monde(x, label))
    cx.execute("UPDATE runs SET started_at = ? WHERE id = ?", (depuis(depuis_min, quand=quand), run_id))


def fait(cx, x, label, rang, depuis_min, **champs):
    """Une visite finie, commencée il y a `depuis_min` minutes."""
    secondes = (depuis_min * 60) if depuis_min else 0
    visite_course(cx, x, label, rang, (JOUR2 - DEPART).total_seconds() - secondes, **champs)


def etat(cx, x, reglages, *, maintenant=JOUR2, session="vivante"):
    return course_etat.etat(cx, x, campaigns.dossier_campagne(reglages, x), maintenant=maintenant, session=session)


def bras(rapport, label="sujet"):
    return next(b for b in rapport["bras"] if b["label"] == label)


# ── Les cas de l'état ───────────────────────────────────────────────────────────────────────────


def test_en_cours_normal_code_0(base, reglages):
    cx, x = base
    fait(cx, x, "sujet", 1, 90)
    fait(cx, x, "sujet", 2, 40, reussie=False)
    prevue(reglages, x, dans_min=25, ecrite_il_y_a=10)  # écrite après la fin de la visite 2
    rapport = etat(cx, x, reglages)
    assert rapport["etat"] == "en cours" and rapport["code"] == 0
    assert rapport["jour"] == 2 and rapport["jours"] == 7
    assert rapport["echeance"].startswith("2026-11-24T08:30")
    sujet = bras(rapport)
    assert (sujet["faites"], sujet["reussies"]) == (2, 1)
    assert sujet["prochaine"].startswith("2026-11-18T10:55") and sujet["retard_min"] is None
    assert sujet["en_cours"] is None


def test_la_derniere_activite_est_la_plus_recente_du_passage_et_de_la_note(base, reglages):
    cx, x = base
    fait(cx, x, "sujet", 1, 90)  # fini à -88 min
    note(
        reglages,
        x,
        genre="manquee",
        motif="retard",
        prevue=depuis(80),
        constatee=depuis(15),
        creneau=depuis(80),
        essai=1,
    )
    rapport = etat(cx, x, reglages)
    assert rapport["derniere_activite"].startswith(depuis(15)[:16])
    assert rapport["depuis_min"] == pytest.approx(15, abs=0.1)


def test_processus_absent_avant_l_echeance_code_1(base, reglages):
    cx, x = base
    fait(cx, x, "sujet", 1, 90)
    prevue(reglages, x, dans_min=25)
    rapport = etat(cx, x, reglages, session="absente")
    assert rapport["etat"] == "arrêtée" and rapport["code"] == 1
    assert "absente" in " ".join(rapport["raisons"])


def test_campagne_finie_avant_l_echeance_sujet_banni_code_1(base, reglages):
    cx, x = base
    cx.execute("UPDATE experiments SET status = 'termine' WHERE id = ?", (x,))
    note(reglages, x, genre="bannie", identite="course-sujet-1", constatee=depuis(300), repetition=9, restantes=192)
    rapport = etat(cx, x, reglages, session="absente")
    assert rapport["etat"] == "arrêtée" and rapport["code"] == 1
    assert "banni" in " ".join(rapport["raisons"])
    assert bras(rapport)["prochaine"] is None


def test_une_identite_bannie_arrete_la_course_meme_avant_la_note(base, reglages, tmp_path):
    cx, x = base
    dossier = tmp_path / "identites" / "course-sujet-1"
    dossier.mkdir(parents=True)
    (dossier / "identite.json").write_text(json.dumps({"etat": "banni", "banni_le": depuis(5)}), encoding="utf-8")
    rapport = etat(cx, x, reglages)
    assert rapport["code"] == 1 and bras(rapport)["identite"]["etat"] == "banni"


def test_finie_a_l_echeance_code_0(base, reglages):
    cx, x = base
    cx.execute("UPDATE experiments SET status = 'termine' WHERE id = ?", (x,))
    fin = DEPART + timedelta(days=7, minutes=3)
    note(
        reglages,
        x,
        genre="echeance",
        echeance=(DEPART + timedelta(days=7)).isoformat(),
        constatee=fin.isoformat(),
        repetition=60,
        restantes=140,
    )
    rapport = etat(cx, x, reglages, maintenant=fin + timedelta(hours=2), session="absente")
    assert rapport["etat"] == "finie" and rapport["code"] == 0
    assert rapport["jour"] == 7


def test_prochaine_visite_depassee_de_31_minutes_code_2(base, reglages):
    cx, x = base
    fait(cx, x, "sujet", 1, 150)
    prevue(reglages, x, dans_min=-31)
    rapport = etat(cx, x, reglages)
    assert rapport["etat"] == "en cours" and rapport["code"] == 2
    assert bras(rapport)["retard_min"] == pytest.approx(31, abs=0.1)
    assert "retard" in " ".join(rapport["raisons"])


def test_prochaine_visite_depassee_de_20_minutes_code_0(base, reglages):
    cx, x = base
    fait(cx, x, "sujet", 1, 150)
    prevue(reglages, x, dans_min=-20)
    rapport = etat(cx, x, reglages)
    assert rapport["code"] == 0
    assert bras(rapport)["retard_min"] == pytest.approx(20, abs=0.1)


def test_un_retard_avec_une_note_plus_recente_n_est_pas_anormal(base, reglages):
    cx, x = base
    prevue(reglages, x, dans_min=-45)
    note(
        reglages,
        x,
        genre="manquee",
        motif="infrastructure",
        prevue=depuis(45),
        constatee=depuis(5),
        creneau=depuis(45),
        essai=2,
    )
    assert etat(cx, x, reglages)["code"] == 0


def test_un_retard_avec_un_passage_en_cours_n_est_pas_un_retard(base, reglages):
    cx, x = base
    prevue(reglages, x, dans_min=-45)
    en_cours(cx, x, "sujet", 1, 40)
    rapport = etat(cx, x, reglages)
    assert rapport["code"] == 0 and bras(rapport)["retard_min"] is None
    assert bras(rapport)["en_cours"]["minutes"] == pytest.approx(40, abs=0.1)


def test_passage_en_cours_depuis_61_minutes_code_2(base, reglages):
    cx, x = base
    en_cours(cx, x, "sujet", 1, 61)
    rapport = etat(cx, x, reglages)
    assert rapport["code"] == 2 and "blocage" in " ".join(rapport["raisons"])
    assert bras(rapport)["en_cours"]["minutes"] == pytest.approx(61, abs=0.1)


def test_passage_en_cours_depuis_59_minutes_code_0(base, reglages):
    cx, x = base
    en_cours(cx, x, "sujet", 1, 59)
    assert etat(cx, x, reglages)["code"] == 0


def test_hors_plage_la_prochaine_visite_est_demain_matin_pas_un_retard(base, reglages):
    cx, x = base
    nuit = DEPART + timedelta(days=1, hours=13)  # 21 h 30 UTC, fermeture à 23 h : la visite suivante est à 8 h
    fait(
        cx,
        x,
        "sujet",
        1,
        30,
    )
    note(
        reglages, x, genre="prevue", prevue=(DEPART + timedelta(days=2, minutes=12)).isoformat(timespec="seconds"),
        ecrite=(nuit - timedelta(minutes=20)).isoformat(timespec="seconds"),
    )  # fmt: skip
    rapport = etat(cx, x, reglages, maintenant=nuit + timedelta(hours=3))
    assert rapport["code"] == 0 and bras(rapport)["retard_min"] is None
    assert bras(rapport)["prochaine"].startswith("2026-11-19T08:42")


def test_identite_en_alerte_affichee_avec_sa_fin(base, reglages, tmp_path):
    cx, x = base
    dossier = tmp_path / "identites" / "course-sujet-1"
    dossier.mkdir(parents=True)
    alerte = JOUR2 - timedelta(minutes=20)
    (dossier / "identite.json").write_text(
        json.dumps({"etat": "alerte", "alerte_le": alerte.isoformat(), "raison": "refus"}), encoding="utf-8"
    )
    rapport = etat(cx, x, reglages)
    identite = bras(rapport)["identite"]
    assert identite["etat"] == "alerte" and identite["nom"] == "course-sujet-1"
    assert identite["jusqu_a"].startswith((alerte + timedelta(hours=1)).isoformat()[:16])
    assert "alerte jusqu'à" in course_etat.texte(rapport)
    assert bras(rapport, "temoin-classique")["identite"] is None


def test_un_bras_fini_n_a_pas_de_prochaine_visite_ni_de_retard(base, reglages):
    cx, x = base
    for rang in range(1, 5):
        fait(cx, x, "temoin-classique", rang, 600 - rang)
    note(reglages, x, bras="temoin-classique", genre="prevue", prevue=depuis(300), ecrite=depuis(400))
    rapport = etat(cx, x, reglages)
    classique = bras(rapport, "temoin-classique")
    assert classique["etat"] == "complet" and classique["prochaine"] is None and rapport["code"] == 0


def manquee(reglages, x, creneau_il_y_a, motif="infrastructure", essais=1):
    """Un créneau manqué du sujet (créneau prévu il y a `creneau_il_y_a` minutes), noté `essais` fois."""
    for essai in range(1, essais + 1):
        note(
            reglages, x, genre="manquee", motif=motif, prevue=depuis(creneau_il_y_a), creneau=depuis(creneau_il_y_a),
            constatee=depuis(creneau_il_y_a - 5 * essai), essai=essai,
        )  # fmt: skip


def test_deux_visites_manquees_de_suite_code_2_avec_motif_et_heure_de_la_premiere(base, reglages):
    cx, x = base
    fait(cx, x, "sujet", 1, 400)
    manquee(reglages, x, 200, "infrastructure", essais=3)  # trois essais d'un même créneau : un seul créneau manqué
    manquee(reglages, x, 100, "retard")
    prevue(reglages, x, dans_min=20, ecrite_il_y_a=5)
    rapport = etat(cx, x, reglages)
    assert rapport["code"] == 2 and bras(rapport)["manquees_de_suite"] == 2
    message = " ".join(rapport["raisons"])
    assert "manquées de suite" in message and "infrastructure" in message and "07:10" in message  # 10 h 30 - 200 min


def test_une_seule_visite_manquee_code_0(base, reglages):
    cx, x = base
    fait(cx, x, "sujet", 1, 400)
    manquee(reglages, x, 100, essais=4)  # une panne longue sur un seul créneau reste un seul créneau manqué
    prevue(reglages, x, dans_min=20, ecrite_il_y_a=5)
    rapport = etat(cx, x, reglages)
    assert rapport["code"] == 0 and bras(rapport)["manquees_de_suite"] == 1


def test_manquee_visite_faite_manquee_code_0(base, reglages):
    cx, x = base
    fait(cx, x, "sujet", 1, 500)
    manquee(reglages, x, 300)
    fait(cx, x, "sujet", 2, 200)  # une visite faite entre les deux : la série repart de zéro
    manquee(reglages, x, 100, "retard")
    prevue(reglages, x, dans_min=20, ecrite_il_y_a=5)
    rapport = etat(cx, x, reglages)
    assert rapport["code"] == 0 and bras(rapport)["manquees_de_suite"] == 1


def test_visites_manquees_comptees_par_bras(base, reglages):
    cx, x = base
    note(
        reglages,
        x,
        genre="manquee",
        motif="retard",
        prevue=depuis(80),
        constatee=depuis(70),
        creneau=depuis(80),
        essai=1,
    )
    assert bras(etat(cx, x, reglages))["manquees"] == 1


def test_sujet_sans_visite_a_faire_avant_l_echeance_est_arrete_meme_si_un_temoin_est_actif(base, reglages):
    """« Démarrage impossible » écrit toutes les répétitions restantes en erreur : le sujet est `complet`, sans note
    d'échéance, alors qu'un témoin tourne encore."""
    cx, x = base
    configuration = json.loads(cx.execute("SELECT configuration FROM experiments WHERE id = ?", (x,)).fetchone()[0])
    configuration["engines"][0]["visites"] = 2
    cx.execute("UPDATE experiments SET configuration = ? WHERE id = ?", (json.dumps(configuration), x))
    fait(cx, x, "sujet", 1, 90)
    fait(cx, x, "sujet", 2, 60, reussie=False)
    rapport = etat(cx, x, reglages)
    assert bras(rapport)["etat"] == "complet" and bras(rapport, "temoin-negatif")["etat"] == "actif"
    assert rapport["etat"] == "arrêtée" and rapport["code"] == 1


def test_configuration_illisible_code_3_pas_1(base, reglages, capsys):
    cx, x = base
    cx.execute('UPDATE experiments SET configuration = \'{"name": "x"}\' WHERE id = ?', (x,))
    assert main(["course", "etat", str(x)]) == 3
    assert "Erreur" in capsys.readouterr().err


def test_campagne_inconnue_code_3(base, reglages, capsys):
    cx, x = base
    with pytest.raises(LookupError):
        etat(cx, x + 40, reglages)
    assert main(["course", "etat", str(x + 40)]) == 3
    assert "introuvable" in capsys.readouterr().err


def test_aucune_base_code_3(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SHADOWLAB_SORTIES", str(tmp_path / "vide"))
    monkeypatch.setenv("SHADOWLAB_BASE", str(tmp_path / "vide" / "rien.sqlite3"))
    assert main(["course", "etat"]) == 3
    assert not (tmp_path / "vide" / "rien.sqlite3").exists()  # lecture seule : rien n'est créé
    assert "introuvable" in capsys.readouterr().err


# ── La ligne de commande ────────────────────────────────────────────────────────────────────────


def test_sans_numero_la_derniere_campagne_est_prise(base, reglages, capsys):
    cx, x = base
    cx.execute("UPDATE experiments SET status = 'termine' WHERE id = ?", (x,))
    note(reglages, x, genre="bannie", identite="course-sujet-1", constatee=depuis(300), repetition=9, restantes=192)
    cx.close()
    assert main(["course", "etat", "--session", "vivante"]) == 1
    sortie = capsys.readouterr().out
    assert sortie.splitlines()[0].startswith("arrêtée") and f"campagne {x}" in sortie
    assert main(["course", "etat", str(x), "--session", "absente", "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["campagne"] == x


def test_la_commande_n_ecrit_rien_et_ouvre_la_base_en_lecture_seule(base, reglages):
    cx, x = base
    avant = cx.execute("SELECT COUNT(*) FROM runs").fetchone()[0], os.path.getsize(reglages.base_donnees)
    prevue(reglages, x, dans_min=25)
    fichier = campaigns.dossier_campagne(reglages, x) / campaigns.FICHIER_CADENCE
    texte = fichier.read_text(encoding="utf-8")
    etat(cx, x, reglages)
    assert fichier.read_text(encoding="utf-8") == texte
    ro = course_etat.ouvrir_en_lecture(reglages.base_donnees)
    with pytest.raises(Exception, match="readonly"):
        ro.execute("DELETE FROM runs")
    ro.close()
    assert (cx.execute("SELECT COUNT(*) FROM runs").fetchone()[0], os.path.getsize(reglages.base_donnees)) == avant


# ── La note `prevue` de la cadence ──────────────────────────────────────────────────────────────


def cadence_notee(horloge, mode, *, depart=None, faites=(), **champs):
    notes: list[dict] = []
    c = espacement.Cadence(
        espacement.Espacement(mode=mode, **champs), horloge=horloge.now, dormir=horloge.dormir, graine=3,
        depart=depart or horloge.now(), faites=faites, noter=notes.append,
    )  # fmt: skip
    return c, notes


def test_la_cadence_ecrit_la_note_prevue_avant_d_attendre_en_mode_ordonnanceur():
    horloge = Horloge(datetime(2026, 11, 17, 9, 0))
    c, notes = cadence_notee(horloge, "ordonnanceur", jours=7)
    creneau = c.attendre()
    prevues = [n for n in notes if n["genre"] == "prevue"]
    assert len(prevues) == 1
    assert espacement.au_cadran(prevues[0]["prevue"], horloge.now()) == creneau.debut
    assert espacement.au_cadran(prevues[0]["ecrite"], horloge.now()) <= creneau.debut
    # écrite AVANT l'attente : à l'écriture l'horloge n'avait pas encore avancé
    assert espacement.au_cadran(prevues[0]["ecrite"], horloge.now()) == datetime(2026, 11, 17, 9, 0)


def test_hors_plage_la_cadence_ecrit_le_soir_une_note_qui_vise_le_lendemain_matin():
    """Vraie cadence, horloge factice : après la dernière heure de début (fermeture à 23 h), le créneau est le lendemain
    à 8 h au plus tôt ; la note est écrite à 22 h 45, avant l'attente de la nuit."""
    soir = datetime(2026, 11, 17, 22, 45)
    horloge = Horloge(soir)
    faites = [(soir - timedelta(minutes=30), soir - timedelta(minutes=20), 15)]
    c, notes = cadence_notee(horloge, "ordonnanceur", depart=soir - timedelta(days=1), faites=faites, jours=7)
    creneau = c.attendre()
    prevue = next(n for n in notes if n["genre"] == "prevue")
    ecrite = espacement.au_cadran(prevue["ecrite"], soir)
    prochaine = espacement.au_cadran(prevue["prevue"], soir)
    assert ecrite == soir and prochaine == creneau.debut
    assert prochaine.date() == datetime(2026, 11, 18).date() and prochaine.hour >= 8


def test_la_cadence_ecrit_la_note_prevue_en_mode_fixe():
    horloge = Horloge(datetime(2026, 11, 17, 9, 0))
    c, notes = cadence_notee(horloge, "fixe", minutes=10)
    premier = c.attendre()
    horloge.avancer(120)
    c.terminer(premier, 15)
    fin = horloge.now()
    c.attendre()
    prevues = [n for n in notes if n["genre"] == "prevue"]
    assert len(prevues) == 2
    assert espacement.au_cadran(prevues[1]["prevue"], fin) == fin + timedelta(minutes=10)


def test_aucune_note_prevue_a_l_echeance():
    horloge = Horloge(datetime(2026, 11, 17, 9, 0))
    depart = horloge.now() - timedelta(hours=6)
    faites = [
        (horloge.now() - timedelta(minutes=12), horloge.now() - timedelta(minutes=10), 15)
    ]  # la suivante, 45 min après
    c, notes = cadence_notee(
        horloge, "ordonnanceur", depart=depart, faites=faites, jours=6.5 / 24
    )  # échéance dans 30 min
    assert c.attendre().echeance
    assert [n for n in notes if n["genre"] == "prevue"] == []


def test_les_lecteurs_de_cadence_jsonl_ignorent_le_genre_prevue(base, reglages):
    """La cadence (état durable), la reprise (`_visites_du_bras`) et le bilan (`course.bilan`) ne comptent pas `prevue`."""
    cx, x = base
    fait(cx, x, "sujet", 1, 600)
    sans = [
        {"bras": "sujet", "protection": "endurance", "genre": "manquee", "motif": "retard", "prevue": heure(3 * JOUR), "constatee": heure(3 * JOUR + 7200), "creneau": heure(3 * JOUR), "essai": 1},
        {"bras": "sujet", "protection": "endurance", "genre": "interrompue", "debut": heure(100), "fin": heure(200), "pages": 3},
    ]  # fmt: skip
    avec = [
        *sans,
        {
            "bras": "sujet",
            "protection": "endurance",
            "genre": "prevue",
            "prevue": heure(4 * JOUR),
            "ecrite": heure(4 * JOUR - 60),
        },
    ]
    dossier = campaigns.dossier_campagne(reglages, x)

    def lecture(lignes):
        for ligne in lignes:
            campaigns.ecrire_note(reglages, x, ligne)
        from shadowlab import course

        faites = campaigns._visites_du_bras(cx, reglages, x, "sujet", "endurance")
        notes_bras = [n for n in campaigns.lire_notes(reglages, x) if n.get("bras") == "sujet"]
        reference = datetime(2026, 11, 20, 12, 0)
        cadence = espacement.Cadence(
            espacement.Espacement(mode="ordonnanceur", jours=7), horloge=lambda: reference, graine=1,
            depart=DEPART, faites=faites, notes=notes_bras,
        )  # fmt: skip
        creneau = cadence._prochain()
        rapport = course.bilan(cx, x, dossier)
        return faites, creneau.debut, len(cadence._notes), rapport  # le bilan ENTIER : aucun critère ne bouge

    sans_prevue = lecture(sans)
    (dossier / campaigns.FICHIER_CADENCE).unlink()
    assert lecture(avec) == sans_prevue


def test_la_ligne_prevue_ecrite_par_la_campagne_porte_le_bras_et_la_protection(base, reglages):
    cx, x = base
    horloge = Horloge(datetime(2026, 11, 17, 9, 0))
    noter = campaigns._noteur(reglages, x, "sujet", "endurance")
    c = espacement.Cadence(
        espacement.Espacement(mode="ordonnanceur", jours=7), horloge=horloge.now, dormir=horloge.dormir, graine=3,
        depart=horloge.now(), noter=noter,
    )  # fmt: skip
    c.attendre()
    ligne = next(n for n in campaigns.lire_notes(reglages, x) if n["genre"] == "prevue")
    assert ligne["bras"] == "sujet" and ligne["protection"] == "endurance" and ligne["prevue"] and ligne["ecrite"]


# ── scripts/course.sh etat ──────────────────────────────────────────────────────────────────────


@pytest.fixture
def depot_factice(tmp_path):
    """Un dépôt temporaire avec le vrai `course.sh` et des commandes factices : `uv` (rend le code voulu pour le
    résumé, note ses arguments), `tmux` (session absente), `docker` (rien). Aucun Docker, aucune campagne."""
    depot = tmp_path / "depot"
    (depot / "scripts").mkdir(parents=True)
    (depot / "configs" / "courses").mkdir(parents=True)
    (depot / ".courses" / "i9").mkdir(parents=True)
    (depot / "configs" / "courses" / "i9.env").write_text(
        f"SHADOWLAB_SORTIES={tmp_path / 'sorties'}\n", encoding="utf-8"
    )
    script = depot / "scripts" / "course.sh"
    script.write_text((RACINE / "scripts" / "course.sh").read_text(encoding="utf-8"), encoding="utf-8")
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    journal = tmp_path / "appels.txt"
    (bin_ / "uv").write_text(
        f'#!/bin/bash\necho "$@" >> {journal}\n'
        'case "$*" in *"course etat"*) echo "RESUME $*"; exit "${CODE_RESUME:-0}" ;; *) echo "autre $*"; exit 0 ;; esac\n',
        encoding="utf-8",
    )
    (bin_ / "tmux").write_text("#!/bin/bash\nexit 1\n", encoding="utf-8")
    (bin_ / "docker").write_text("#!/bin/bash\necho conteneurs\n", encoding="utf-8")
    for f in bin_.iterdir():
        f.chmod(0o755)
    return script, bin_, journal


@pytest.mark.parametrize("code", [0, 1, 2, 3])
def test_course_sh_etat_affiche_le_resume_d_abord_et_sort_avec_son_code(depot_factice, code):
    script, bin_, journal = depot_factice
    env = {**os.environ, "PATH": f"{bin_}:{os.environ['PATH']}", "CODE_RESUME": str(code)}
    r = subprocess.run(["bash", str(script), "etat", "7"], capture_output=True, text=True, env=env)
    assert r.returncode == code
    lignes = r.stdout.splitlines()
    assert lignes[0].startswith("RESUME") and "course etat 7" in lignes[0] and "--session absente" in lignes[0]
    assert "conteneurs" in r.stdout and "autre run shadowlab arena etat" in r.stdout  # la suite est toujours affichée
    assert r.stdout.index("RESUME") < r.stdout.index("conteneurs")


def test_course_sh_etat_sans_numero_et_numero_invalide(depot_factice):
    script, bin_, _ = depot_factice
    env = {**os.environ, "PATH": f"{bin_}:{os.environ['PATH']}"}
    r = subprocess.run(["bash", str(script), "etat"], capture_output=True, text=True, env=env)
    assert r.returncode == 0 and "course etat --session absente" in r.stdout
    r = subprocess.run(["bash", str(script), "etat", "x"], capture_output=True, text=True, env=env)
    assert r.returncode == 3 and "entier" in r.stderr  # une erreur d'usage n'est jamais lue « arrêtée » (1)


def test_course_sh_etat_rend_3_si_la_course_n_est_pas_preparee(depot_factice):
    script, bin_, _ = depot_factice
    (script.parent.parent / ".courses" / "i9").rmdir()
    env = {**os.environ, "PATH": f"{bin_}:{os.environ['PATH']}"}
    r = subprocess.run(["bash", str(script), "etat"], capture_output=True, text=True, env=env)
    assert r.returncode == 3 and "absent" in r.stderr
