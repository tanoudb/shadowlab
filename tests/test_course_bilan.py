"""Palier 2, I9 : le bilan de la course de 7 jours (§ 6.3), lu dans la base et dans `cadence.jsonl`, sur des données
fabriquées (aucune donnée de visiteur réelle).

Chaque critère vaut `tenu`, `non tenu` ou `non mesuré` ; même code de sortie que la soirée (0 tout tenu, 1 sinon, 2
campagne inconnue). Sujet : aucun bannissement, aucune alerte, toutes les visites faites abouties, même visiteur et même
empreinte E, porte revenue seulement après sa durée (tolérance de 60 s), au moins 99 % des annonces et des champs exacts
à la fin, visites manquées comptées à part (nombre, motifs). Témoins : les critères de la soirée, et le premier jour.
"""

# ruff: noqa: E501  (requêtes SQL et configurations YAML en ligne)
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from test_espacement import campagne
from test_soiree import bannir, visite

from shadowlab import campaigns, course
from shadowlab import database as db
from shadowlab.cli import main
from shadowlab.engines.noezia.parcours import TOLERANCE_PORTE_S

DEPART = datetime(2026, 11, 17, 8, 30, tzinfo=UTC)
JOUR = 86400

ENGINS = """
    - name: noezia
      label: sujet
      visites: 200
      recolte_incrementale: true
      options: {headless: false, channel: chrome, identite_native: true, identite: course-sujet-1}
    - name: noezia
      label: temoin-negatif
      visites: 6
      espacement: {mode: fixe, minutes: 10}
      options: {headless: false, channel: chrome, identite_native: true}
    - name: noezia
      label: temoin-sentinelle
      visites: 6
      bannir_avant_visite: 3
      espacement: {mode: fixe, minutes: 10}
      options: {headless: false, channel: chrome, identite_native: true, identite: course-sentinelle-1}
    - name: playwright
      label: temoin-classique
      visites: 4
      espacement: {mode: fixe, minutes: 10}
"""


@pytest.fixture
def base(tmp_path, reglages):
    experience = campagne(
        tmp_path, reglages, engines=ENGINS, extra="  espacement: {mode: ordonnanceur, jours: 7}\n  concurrency: 4\n"
    )
    cx = db.ouvrir(reglages.base_donnees)
    experiment_id = campaigns.creer(cx, experience, reglages)
    cx.execute("UPDATE experiments SET created_at = ? WHERE id = ?", (DEPART.isoformat(), experiment_id))
    yield cx, experiment_id
    cx.close()


def heure(secondes: float) -> str:
    return (DEPART + timedelta(seconds=secondes)).isoformat(timespec="milliseconds")


def visite_course(cx, x, label, rang, quand_s, *, emis=(), recolte=None, duree=JOUR, **champs):
    """Une visite du bras : celle de la soirée (`test_soiree.visite`), plus son heure, les défis émis par l'Arena (à
    `quand_s + e` secondes du départ), le profil gardé avec le passage et la récolte notée par le scénario."""
    jeton = visite(cx, x, label, rang, defi=len(emis), **champs)
    drapeaux = json.loads(cx.execute("SELECT drapeaux FROM runs WHERE session_token = ?", (jeton,)).fetchone()[0])
    if recolte is not None:
        drapeaux["details_scenario"]["recolte"] = recolte
    cx.execute(
        "UPDATE runs SET started_at = ?, completed_at = ?, drapeaux = ?, protection_config = ? WHERE session_token = ?",
        (
            heure(quand_s),
            heure(quand_s + 120),
            json.dumps(drapeaux),
            json.dumps({"profil": {"duree_cookie_s": duree}}),
            jeton,
        ),
    )
    for e in emis:
        cx.execute(
            "INSERT INTO decisions (session_token, created_at, couche, decision, chemin, motifs)"
            " VALUES (?, ?, 'defi-js', 'emis', '/lab/vitrine/annonces', '[]')",
            (jeton, heure(quand_s + e)),
        )
    return jeton


RECOLTE_OK = {
    "annonces_attendues": 300,
    "annonces_retrouvees": 300,
    "annonces": 1.0,
    "champs_attendus": 4200,
    "champs_exacts": 4190,
    "champs": 4190 / 4200,
}


def notes(reglages, x, lignes):
    for ligne in lignes:
        campaigns.ecrire_note(reglages, x, ligne)


NOTES_OK = [
    {
        "genre": "manquee",
        "bras": "sujet",
        "protection": "endurance",
        "motif": "retard",
        "prevue": heure(2 * JOUR),
        "constatee": heure(2 * JOUR + 7200),
        "creneau": heure(2 * JOUR),
        "essai": 1,
    },
    *[
        {
            "genre": "manquee",
            "bras": "sujet",
            "protection": "endurance",
            "motif": "infrastructure",
            "prevue": heure(3 * JOUR + 300 * k),
            "constatee": heure(3 * JOUR + 300 * k),
            "creneau": heure(3 * JOUR),
            "essai": k + 1,
        }
        for k in range(3)
    ],
    {
        "genre": "echeance",
        "bras": "sujet",
        "protection": "endurance",
        "echeance": heure(7 * JOUR),
        "constatee": heure(7 * JOUR),
        "repetition": 13,
        "restantes": 188,
    },
]


def course_tenue(cx, x, reglages):
    """12 visites du sujet sur 7 jours (porte revenue chaque fois plus de 24 h après la précédente), 188 non faites
    (échéance), témoins le 1er jour."""
    moments = (
        [3600 * h for h in (0.5, 2.5, 5)]
        + [JOUR + 3600 * h for h in (1, 3, 6)]
        + [2 * JOUR + 3600 * h for h in (2, 5)]
        + [3 * JOUR + 3600 * 4, 4 * JOUR + 3600 * 5, 5 * JOUR + 3600 * 6, 6 * JOUR + 3600 * 10]
    )
    for rang, quand in enumerate(moments, start=1):
        emis = (5,) if rang in (1, 4, 7, 9, 10, 11, 12) else ()
        visite_course(cx, x, "sujet", rang, quand, emis=emis, recolte=RECOLTE_OK if rang == len(moments) else None)
    for n in range(1, 7):
        visite_course(cx, x, "temoin-negatif", n, 600 * n, visiteur=f"n{n}", reussie=n < 5, bloque=n >= 5)
    bannir(cx, x, "temoin-negatif", visiteur="n5", empreinte="e1", motif="detecte:correlation-session")
    visite_course(cx, x, "temoin-sentinelle", 1, 600, visiteur="s1", e="E3")
    visite_course(cx, x, "temoin-sentinelle", 2, 1200, visiteur="s1", e="E3")
    bannir(cx, x, "temoin-sentinelle", visiteur="s1")
    visite_course(
        cx,
        x,
        "temoin-sentinelle",
        3,
        1800,
        visiteur="s1",
        e="E3",
        reussie=False,
        bloque=True,
        arret=True,
        identite="banni",
    )
    for n in (4, 5, 6):
        visite_course(
            cx, x, "temoin-sentinelle", n, 1800 + 600 * n, visiteur=None, e=None, reussie=False, identite=None
        )
    for n in range(1, 5):
        visite_course(
            cx,
            x,
            "temoin-classique",
            n,
            600 * n,
            visiteur=f"p{n}",
            e="E4",
            reussie=False,
            bloque=True,
            arret=True,
            identite=None,
        )
    notes(reglages, x, NOTES_OK)


def statuts(rapport, bras):
    return {nom: c["statut"] for nom, c in rapport["bras"][bras]["criteres"].items()}


def dossier(reglages, x):
    return campaigns.dossier_campagne(reglages, x)


def test_une_course_tenue_tient_tous_les_criteres(base, reglages):
    cx, x = base
    course_tenue(cx, x, reglages)
    rapport = course.bilan(cx, x, dossier(reglages, x))
    assert statuts(rapport, "sujet") == {
        "aucun_bannissement": "tenu",
        "aucune_alerte": "tenu",
        "visites_faites_abouties": "tenu",
        "meme_visiteur": "tenu",
        "meme_empreinte": "tenu",
        "porte_apres_sa_duree": "tenu",
        "recolte_99": "tenu",
        "visites_manquees_a_part": "tenu",
    }
    sujet = rapport["bras"]["sujet"]
    assert sujet["visites_faites"] == 12 and sujet["visites_non_faites_echeance"] == 188
    assert sujet["visites_manquees"] == {"nombre": 2, "par_motif": {"retard": 1, "infrastructure": 1}, "essais": 4}
    assert "2 visite(s) manquée(s)" in sujet["criteres"]["visites_manquees_a_part"]["detail"]
    for role in ("temoin-negatif", "temoin-sentinelle", "temoin-classique"):
        assert set(statuts(rapport, role).values()) == {"tenu"}, (role, rapport["bras"][role]["criteres"])
    assert "pendant_le_premier_jour" in statuts(rapport, "temoin-negatif")
    assert "pendant_le_premier_jour" in statuts(rapport, "temoin-sentinelle")
    assert rapport["verdict"] == "tenu"
    assert sujet["criteres"]["porte_apres_sa_duree"]["detail"].startswith("7 passage(s)")
    assert course.texte(rapport).splitlines()[0] == f"Course, campagne {x} : TENU"


@pytest.mark.parametrize(
    ("defaut", "critere"),
    [
        ("bannissement", "aucun_bannissement"),
        ("alerte", "aucune_alerte"),
        ("echec", "visites_faites_abouties"),
        ("visiteur", "meme_visiteur"),
        ("porte_2h", "porte_apres_sa_duree"),
        ("porte_hors_tolerance", "porte_apres_sa_duree"),
        ("recolte_98", "recolte_99"),
        ("champs_98", "recolte_99"),
    ],
)
def test_chaque_critere_du_sujet_peut_ne_pas_etre_tenu(base, reglages, defaut, critere):
    cx, x = base
    notes(reglages, x, NOTES_OK)
    for rang in range(1, 4):
        reglages_visite = {}
        if defaut == "alerte" and rang == 2:
            reglages_visite = {"identite": "alerte", "arret": True}
        if defaut == "echec" and rang == 2:
            reglages_visite = {"reussie": False}
        if defaut == "visiteur" and rang == 3:
            reglages_visite = {"visiteur": "v2"}
        emis = (5,) if rang == 1 else ()
        if rang == 2 and defaut == "porte_2h":
            emis = (5,)
        if rang == 3 and defaut == "porte_hors_tolerance":
            emis = (5,)
        quand = {1: 0, 2: 7200, 3: JOUR - 2 * TOLERANCE_PORTE_S}[rang]
        recolte = None
        if rang == 3:
            recolte = dict(RECOLTE_OK)
            if defaut == "recolte_98":
                recolte.update(annonces_retrouvees=294, annonces=0.98)
            if defaut == "champs_98":
                recolte.update(champs_exacts=4100, champs=4100 / 4200)
        visite_course(cx, x, "sujet", rang, quand, emis=emis, recolte=recolte, **reglages_visite)
    if defaut == "bannissement":
        bannir(cx, x, "sujet", visiteur="v1", empreinte="e1", motif="detecte:comportement")
    rapport = course.bilan(cx, x, dossier(reglages, x))
    assert statuts(rapport, "sujet")[critere] == "non tenu", rapport["bras"]["sujet"]["criteres"][critere]
    assert rapport["verdict"] == "non tenu"


def test_la_porte_revenue_dans_la_tolerance_est_tenue(base, reglages):
    cx, x = base
    visite_course(cx, x, "sujet", 1, 0, emis=(5, 8))  # deux émissions d'un même passage (rafale) : un seul passage
    visite_course(cx, x, "sujet", 2, JOUR - TOLERANCE_PORTE_S // 2, emis=(5,))
    visite_course(cx, x, "sujet", 3, 2 * JOUR + 3600, emis=(5,), duree=JOUR)
    critere = course.bilan(cx, x, dossier(reglages, x))["bras"]["sujet"]["criteres"]["porte_apres_sa_duree"]
    assert critere["statut"] == "tenu", critere
    assert "3 passage(s)" in critere["detail"]


def test_la_porte_courte_de_la_repetition_est_lue_dans_le_profil_garde_avec_le_passage(base, reglages):
    cx, x = base
    for rang, quand in enumerate((0, 400, 700, 1300), start=1):
        visite_course(cx, x, "sujet", rang, quand, emis=(5,) if rang in (1, 3, 4) else (), duree=600)
    critere = course.bilan(cx, x, dossier(reglages, x))["bras"]["sujet"]["criteres"]["porte_apres_sa_duree"]
    assert critere["statut"] == "tenu" and "600" in critere["detail"], critere


def test_sans_donnee_un_critere_est_non_mesure(base, reglages):
    cx, x = base
    visite_course(cx, x, "sujet", 1, 0)  # aucun défi émis, aucune récolte notée, aucun fichier de notes
    rapport = course.bilan(cx, x, dossier(reglages, x))
    s = statuts(rapport, "sujet")
    assert s["porte_apres_sa_duree"] == s["recolte_99"] == s["visites_manquees_a_part"] == "non mesuré"
    assert rapport["verdict"] in ("non mesuré", "non tenu")


def test_une_campagne_vide_n_est_pas_tenue(base, reglages):
    cx, x = base
    rapport = course.bilan(cx, x, dossier(reglages, x))
    assert rapport["verdict"] != "tenu"
    assert set(statuts(rapport, "sujet").values()) == {"non mesuré"}


def test_un_temoin_qui_tourne_apres_le_premier_jour_n_est_pas_tenu(base, reglages):
    cx, x = base
    course_tenue(cx, x, reglages)
    visite_course(cx, x, "temoin-negatif", 7, JOUR + 3600, visiteur="n7", reussie=False, bloque=True)
    rapport = course.bilan(cx, x, dossier(reglages, x))
    assert statuts(rapport, "temoin-negatif")["pendant_le_premier_jour"] == "non tenu"


def test_les_visites_interrompues_sont_dites(base, reglages):
    cx, x = base
    course_tenue(cx, x, reglages)
    notes(
        reglages,
        x,
        [
            {
                "genre": "interrompue",
                "bras": "sujet",
                "protection": "endurance",
                "repetition": 5,
                "debut": heure(JOUR),
                "fin": heure(JOUR + 60),
                "pages": 7,
            }
        ],
    )
    assert course.bilan(cx, x, dossier(reglages, x))["bras"]["sujet"]["visites_interrompues"] == 1


def test_une_reprise_apres_l_echeance_ne_double_pas_les_visites_non_faites(base, reglages):
    """`reprendre` après l'échéance réécrit une note `echeance` (mêmes répétitions restantes) : comptée une fois."""
    cx, x = base
    course_tenue(cx, x, reglages)
    notes(reglages, x, [{**NOTES_OK[-1], "constatee": heure(7 * JOUR + 3600)}])
    sujet = course.bilan(cx, x, dossier(reglages, x))["bras"]["sujet"]
    assert sujet["visites_non_faites_echeance"] == 188
    assert "188 non faite(s)" in sujet["criteres"]["visites_manquees_a_part"]["detail"]


def test_sous_commande_course_bilan(base, reglages, capsys):
    cx, x = base
    course_tenue(cx, x, reglages)
    assert main(["course", "bilan", str(x)]) == 0
    assert "TENU" in capsys.readouterr().out
    assert main(["course", "bilan", str(x), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["verdict"] == "tenu"
    bannir(cx, x, "sujet", visiteur="v1", empreinte="e1", motif="detecte:comportement")
    assert main(["course", "bilan", str(x)]) == 1
    assert main(["course", "bilan", "999999"]) == 2
