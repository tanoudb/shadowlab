"""Palier 2, I9 : une identité en alerte ne fait aucune visite avant la fin de son attente ; bannie, plus aucune.

Ce que la répétition de la course a montré (16/11) : une fois l'identité du sujet en `alerte` (attente d'une heure,
§ 5.5 de la conception), la cadence a lancé 23 « visites » qui ont échoué aussitôt (`IdentiteRefusee … attendre encore
58 min`). La conception dit : aucune visite avant la fin de l'attente.

Temps simulé, aucun navigateur, aucune Arena : le passage est remplacé par une fonction qui écrit la ligne `runs` comme
la campagne, aux heures de l'horloge factice, et note l'identité comme la sentinelle le ferait. Ce que ces tests
établissent, pour un bras espacé qui a une identité persistante :
1. identité en alerte : aucune visite avant la fin de l'attente ; une ligne `attente_alerte` dans `cadence.jsonl`
   (heure prévue, fin de l'attente) ; aucun passage en base ; la visite suivante reste dans la plage ;
2. identité bannie : plus aucune visite ; une ligne `bannie` (répétitions restantes, non faites) ; le bras est fini ;
3. à la reprise (`shadowlab reprendre`), même règle AVANT d'ouvrir le pilote : le vrai pilote refuse de s'ouvrir sur une
   identité en alerte ou bannie, ce qui écrivait toutes les répétitions restantes en erreur (« démarrage impossible »).
"""

# ruff: noqa: E501  (requêtes SQL et configurations YAML en ligne)
from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest
from test_course_cadence import iso
from test_espacement import Horloge, campagne, faux_pilote, rang_de, visite_du_visiteur

from shadowlab import campaigns
from shadowlab import database as db
from shadowlab.engines.noezia import identite as ident

T0 = datetime(2026, 11, 17, 10, 0, 0)  # un mardi matin, dans la plage 8 h - 23 h
UNE_HEURE = timedelta(seconds=ident.ATTENTE_ALERTE_S)
FIXE = "  espacement: {mode: fixe, minutes: 1}\n  concurrency: 4\n"
ORDONNANCEUR_COURT = (
    "  espacement: {mode: ordonnanceur, jours: 7, reglages: {ecart_min_min: 45, ecart_med_min: 46, ecart_max_min: 47}}\n"
    "  concurrency: 4\n"
)


@pytest.fixture(autouse=True)
def identites(tmp_path, monkeypatch):
    monkeypatch.setenv("SHADOWLAB_IDENTITES", str(tmp_path / "identites"))
    monkeypatch.setattr(campaigns, "_panne_infrastructure", lambda reglages, protection: None)


def noter_identite(nom: str, verdict: str, quand: datetime) -> None:
    """Ce que la sentinelle écrit à la fin d'une visite arrêtée (`Identite.marquer`), à l'heure de l'horloge factice."""
    ouverte = ident.ouvrir(nom, maintenant=True)
    try:
        ouverte.marquer(verdict, "statut : statut 403", quand=quand.astimezone())
    finally:
        ouverte.liberer()


class PassagesIdentite:
    """Remplace `campaigns._passage` : écrit la ligne `runs` (début, fin) aux heures de l'horloge factice ; à la fin de
    la visite `rang` de `marquer`, l'identité `nom` reçoit le verdict (comme la sentinelle)."""

    def __init__(self, horloge, nom, marquer=None, duree_s=120, ecrire_visite=None):
        self.horloge, self.nom, self.marquer, self.duree_s = horloge, nom, marquer or {}, duree_s
        self.ecrire_visite = ecrire_visite
        self.quand: list[tuple[int, datetime]] = []

    def __call__(self, cx, reglages, experience, experiment_id, pilote, engine_id, scenario, scenario_id, repetition,
                 protection, base, rng, dossier_artefacts, engine_version="", monde=None):  # fmt: skip
        debut = self.horloge.now()
        self.quand.append((repetition, debut))
        if self.ecrire_visite:
            self.ecrire_visite(cx, monde, repetition)
        self.horloge.avancer(self.duree_s)
        verdict = self.marquer.get(repetition)
        if verdict:
            noter_identite(self.nom, verdict, self.horloge.now())
        cx.execute(
            "INSERT INTO runs (experiment_id, engine_id, scenario_id, repetition, session_token, truth, started_at,"
            " completed_at, status, success, protection, drapeaux) VALUES (?, ?, ?, ?, ?, 'automatise', ?, ?, ?, ?, ?, ?)",
            (experiment_id, engine_id, scenario_id, repetition, f"t-{engine_id}-{repetition}", iso(debut),
             iso(self.horloge.now()), "echec" if verdict else "reussi", int(not verdict), protection,
             json.dumps({"details_scenario": {"pages_visite": 3}})),
        )  # fmt: skip
        return {"pages_faites": 3, "pages_visite": 3}


def pilote_comme_noezia(horloge):
    """Pilote factice qui s'ouvre comme `DriverNoezia` en mode identité : `identite.ouvrir` refuse une identité
    bannie, ou en alerte depuis moins d'une heure (à l'heure de l'horloge factice)."""

    class Pilote(faux_pilote()):
        def __init__(self, hotes, options=None):
            super().__init__(hotes, options)
            self._nom = (options or {}).get("identite")
            self._ouverte = None

        def open(self):
            if self._nom:
                self._ouverte = ident.ouvrir(self._nom, horloge=lambda: horloge.now().astimezone())

        def close(self):
            if self._ouverte is not None:
                self._ouverte.liberer()
                self._ouverte = None

    return Pilote


def preparer(tmp_path, reglages, monkeypatch, *, extra=FIXE, repetitions=None, depart=T0, pilote=None):
    experience = campagne(tmp_path, reglages, extra=extra)
    if repetitions is not None:
        experience = experience.model_copy(update={"repetitions": repetitions})
    cx = db.ouvrir(reglages.base_donnees)
    experiment_id = campaigns.creer(cx, experience, reglages)
    cx.execute(
        "UPDATE experiments SET configuration = ?, created_at = ? WHERE id = ?",
        (experience.model_dump_json(), iso(depart - timedelta(minutes=1)), experiment_id),
    )
    classe = pilote or faux_pilote()
    monkeypatch.setattr(campaigns, "registre", lambda: {"noezia": classe, "playwright": classe})
    return experience, cx, experiment_id


def notes_du_bras(reglages, experiment_id, label, genre=None):
    fichier = campaigns.dossier_campagne(reglages, experiment_id) / campaigns.FICHIER_CADENCE
    if not fichier.exists():
        return []
    lignes = [json.loads(x) for x in fichier.read_text(encoding="utf-8").splitlines() if x.strip()]
    return [n for n in lignes if n.get("bras") == label and (genre is None or n.get("genre") == genre)]


def heure(texte: str) -> datetime:
    return datetime.fromisoformat(texte).astimezone().replace(tzinfo=None)


def runs(cx, experiment_id):
    return cx.execute(
        "SELECT repetition, status, error FROM runs WHERE experiment_id = ? ORDER BY id", (experiment_id,)
    ).fetchall()


def executer(reglages, experiment_id, rang, horloge):
    return campaigns.executer_unite(reglages, experiment_id, rang, horloge=horloge.now, dormir=horloge.dormir)


# ── 1. En alerte : aucune visite avant la fin de l'attente ─────────────────────────────────────────────


def test_une_identite_en_alerte_ne_fait_aucune_visite_avant_la_fin_de_son_attente(tmp_path, reglages, monkeypatch):
    experience, cx, x = preparer(tmp_path, reglages, monkeypatch, repetitions=4)
    horloge = Horloge(T0)
    passages = PassagesIdentite(horloge, "soiree-sujet", marquer={2: "alerte"})
    monkeypatch.setattr(campaigns, "_passage", passages)
    assert executer(reglages, x, rang_de(experience, "sujet"), horloge) == "termine"

    alerte_le = T0 + timedelta(minutes=5)  # fin de la 2e visite (début T0 + 3 min, 2 min de visite)
    fin = alerte_le + UNE_HEURE
    assert [r for r, _ in passages.quand] == [1, 2, 3, 4]  # toutes les visites faites, aucune perdue
    assert passages.quand[2][1] == fin  # la 3e visite part à la fin de l'attente, pas avant
    assert all(q >= fin for _, q in passages.quand[2:])
    [note] = notes_du_bras(reglages, x, "sujet", "attente_alerte")
    assert heure(note["prevue"]) == alerte_le + timedelta(minutes=1)  # le créneau qui aurait été joué
    assert heure(note["fin"]) == fin and note["identite"] == "soiree-sujet" and note["repetition"] == 3
    assert notes_du_bras(reglages, x, "sujet", "manquee") == []  # ce n'est pas une visite manquée
    assert [r["status"] for r in runs(cx, x)] == ["reussi", "echec", "reussi", "reussi"]  # aucun passage en plus


def test_apres_une_alerte_la_visite_suivante_reste_dans_la_plage(tmp_path, reglages, monkeypatch):
    """Visite finie à 21 h 42 en alerte : sans elle, la suivante partirait vers 22 h 28 (écart de 45 à 47 min, dernière
    heure de début 22 h 30). L'attente finit à 22 h 42, hors de la plage : la visite part demain matin."""
    soir = datetime(2026, 11, 17, 21, 40)
    experience, cx, x = preparer(tmp_path, reglages, monkeypatch, extra=ORDONNANCEUR_COURT, repetitions=2, depart=soir)
    horloge = Horloge(soir)
    passages = PassagesIdentite(horloge, "soiree-sujet", marquer={1: "alerte"})
    monkeypatch.setattr(campaigns, "_passage", passages)
    assert executer(reglages, x, rang_de(experience, "sujet"), horloge) == "termine"
    assert len(passages.quand) == 2
    suivante = passages.quand[1][1]
    assert suivante.date() == soir.date() + timedelta(days=1) and 8 <= suivante.hour <= 9
    [note] = notes_du_bras(reglages, x, "sujet", "attente_alerte")
    assert heure(note["fin"]) == datetime(2026, 11, 17, 22, 42)
    assert notes_du_bras(reglages, x, "sujet", "manquee") == []


def test_un_bras_sans_identite_ne_lit_aucune_identite(tmp_path, reglages, monkeypatch):
    experience, cx, x = preparer(tmp_path, reglages, monkeypatch, repetitions=2)
    monkeypatch.setattr(ident, "racine_identites", lambda: (_ for _ in ()).throw(AssertionError("lue")))
    horloge = Horloge(T0)
    passages = PassagesIdentite(horloge, "inutile")
    monkeypatch.setattr(campaigns, "_passage", passages)
    assert executer(reglages, x, rang_de(experience, "temoin-negatif"), horloge) == "termine"
    assert len(passages.quand) == 2


# ── 2. Bannie : plus aucune visite ──────────────────────────────────────────────────────────────────────


def test_une_identite_bannie_ne_fait_plus_aucune_visite_et_les_restantes_sont_notees(tmp_path, reglages, monkeypatch):
    """Le témoin de sentinelle : banni par la campagne avant sa 3e visite, identité notée `banni` à la fin de celle-ci.
    Les visites 4 à 6 ne sont pas lancées : aucune ligne `runs`, une ligne `bannie` (3 restantes, non faites)."""
    experience, cx, x = preparer(tmp_path, reglages, monkeypatch)
    horloge = Horloge(T0)
    passages = PassagesIdentite(horloge, "soiree-sentinelle", marquer={3: "banni"}, ecrire_visite=visite_du_visiteur)
    monkeypatch.setattr(campaigns, "_passage", passages)
    assert executer(reglages, x, rang_de(experience, "temoin-sentinelle"), horloge) == "termine"
    assert [r for r, _ in passages.quand] == [1, 2, 3]
    assert [r["repetition"] for r in runs(cx, x)] == [1, 2, 3]
    [note] = notes_du_bras(reglages, x, "temoin-sentinelle", "bannie")
    assert (note["repetition"], note["restantes"], note["identite"]) == (4, 3, "soiree-sentinelle")
    assert note["banni_le"] and note["raison"]


# ── 3. À la reprise : même règle avant d'ouvrir le pilote ───────────────────────────────────────────────


def test_a_la_reprise_une_identite_bannie_n_ecrit_aucune_erreur(tmp_path, reglages, monkeypatch):
    horloge = Horloge(T0)
    experience, cx, x = preparer(tmp_path, reglages, monkeypatch, repetitions=3, pilote=pilote_comme_noezia(horloge))
    noter_identite("soiree-sujet", "banni", T0 - timedelta(days=1))
    passages = PassagesIdentite(horloge, "soiree-sujet")
    monkeypatch.setattr(campaigns, "_passage", passages)
    for _ in range(2):  # `reprendre` deux fois : rien de plus, la même note
        assert executer(reglages, x, rang_de(experience, "sujet"), horloge) == "termine"
    assert passages.quand == [] and runs(cx, x) == []  # zéro ligne : ni erreur, ni échec
    notes = notes_du_bras(reglages, x, "sujet", "bannie")
    assert notes and {(n["repetition"], n["restantes"]) for n in notes} == {(1, 3)}


ECHEANCE_1H = "  espacement: {mode: ordonnanceur, jours: 0.0416667, reglages: {plage: [0, 24], ecart_min_min: 1, ecart_med_min: 2, ecart_max_min: 4}}\n  concurrency: 4\n"


def test_une_alerte_qui_finit_apres_l_echeance_finit_le_bras_sans_attendre(tmp_path, reglages, monkeypatch):
    """Répétition (échéance courte) : l'alerte de la 1re visite finit après l'échéance (départ + 1 h). Le bras est fini
    tout de suite : une ligne `attente_alerte`, une ligne `echeance`, aucune heure d'attente, aucun passage de plus."""
    experience, cx, x = preparer(tmp_path, reglages, monkeypatch, extra=ECHEANCE_1H, repetitions=5)
    horloge = Horloge(T0)
    passages = PassagesIdentite(horloge, "soiree-sujet", marquer={1: "alerte"})
    monkeypatch.setattr(campaigns, "_passage", passages)
    assert executer(reglages, x, rang_de(experience, "sujet"), horloge) == "termine"
    assert len(passages.quand) == 1 and len(runs(cx, x)) == 1
    assert horloge.pauses == []
    assert len(notes_du_bras(reglages, x, "sujet", "attente_alerte")) == 1
    [fin] = notes_du_bras(reglages, x, "sujet", "echeance")
    assert fin["restantes"] == 4


def test_a_la_reprise_une_alerte_qui_finit_apres_l_echeance_n_ouvre_pas_le_pilote(tmp_path, reglages, monkeypatch):
    horloge = Horloge(T0)
    experience, cx, x = preparer(
        tmp_path, reglages, monkeypatch, extra=ECHEANCE_1H, repetitions=3, pilote=pilote_comme_noezia(horloge)
    )
    noter_identite("soiree-sujet", "alerte", T0)  # fin de l'attente à T0 + 60 min ; échéance à T0 + 59 min
    passages = PassagesIdentite(horloge, "soiree-sujet")
    monkeypatch.setattr(campaigns, "_passage", passages)
    assert executer(reglages, x, rang_de(experience, "sujet"), horloge) == "termine"
    assert passages.quand == [] and runs(cx, x) == [] and horloge.pauses == []
    assert len(notes_du_bras(reglages, x, "sujet", "attente_alerte")) == 1
    [fin] = notes_du_bras(reglages, x, "sujet", "echeance")
    assert fin["restantes"] == 3


def test_a_la_reprise_pendant_une_alerte_le_bras_attend_puis_visite(tmp_path, reglages, monkeypatch):
    horloge = Horloge(T0)
    experience, cx, x = preparer(tmp_path, reglages, monkeypatch, repetitions=2, pilote=pilote_comme_noezia(horloge))
    alerte_le = T0 - timedelta(minutes=10)
    noter_identite("soiree-sujet", "alerte", alerte_le)
    passages = PassagesIdentite(horloge, "soiree-sujet")
    monkeypatch.setattr(campaigns, "_passage", passages)
    assert executer(reglages, x, rang_de(experience, "sujet"), horloge) == "termine"
    assert [r["status"] for r in runs(cx, x)] == ["reussi", "reussi"]  # aucune erreur « démarrage impossible »
    assert passages.quand[0][1] >= alerte_le + UNE_HEURE
    [note] = notes_du_bras(reglages, x, "sujet", "attente_alerte")
    assert heure(note["fin"]) == alerte_le + UNE_HEURE and note["repetition"] == 1


def test_une_reprise_pendant_l_attente_ne_note_pas_deux_fois_la_meme_alerte(tmp_path, reglages, monkeypatch):
    """L'arrêt (`shadowlab arreter`) tombe pendant l'attente ; `reprendre` relit la note : pas de seconde ligne."""
    horloge = Horloge(T0)
    experience, cx, x = preparer(tmp_path, reglages, monkeypatch, repetitions=1, pilote=pilote_comme_noezia(horloge))
    noter_identite("soiree-sujet", "alerte", T0 - timedelta(minutes=10))
    passages = PassagesIdentite(horloge, "soiree-sujet")
    monkeypatch.setattr(campaigns, "_passage", passages)
    arret = campaigns.fichier_arret(reglages)
    arret.parent.mkdir(parents=True, exist_ok=True)
    arret.touch()
    assert executer(reglages, x, rang_de(experience, "sujet"), horloge) == "interrompu"
    arret.unlink()
    assert executer(reglages, x, rang_de(experience, "sujet"), horloge) == "termine"
    assert len(notes_du_bras(reglages, x, "sujet", "attente_alerte")) == 1 and len(passages.quand) == 1
