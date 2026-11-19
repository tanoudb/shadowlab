"""Campagnes expérimentales : définition YAML validée, exécution reproductible, reprise et arrêt.

Une campagne est une matrice moteurs × protections × scénarios × répétitions. Une « unité » est un couple
(moteur, protection) : elle a son propre navigateur et son propre tirage, dérivé de la graine, ce qui rend son
déroulé indépendant de l'ordre d'exécution. Dans une répétition, les scénarios passent dans un ordre tiré au sort
(évite qu'un scénario profite toujours d'un navigateur « chaud »).

Avec `concurrency: 1`, les unités s'enchaînent dans ce processus. Au-delà, chacune a son processus, et le superviseur
n'en lance une nouvelle que si la mémoire et le CPU le permettent. Les durées mesurées en parallèle ne sont pas
comparables à celles d'une campagne séquentielle : la concurrence est enregistrée avec l'expérience.

Arrêt d'urgence : créer le fichier `<sorties>/ARRET` (commande `shadowlab arreter`) ; la campagne
s'arrête après le passage en cours et peut être reprise.
"""

from __future__ import annotations

import json
import logging
import multiprocessing
import platform
import random
import re
import socket
import subprocess
import sys
import time
import traceback
from collections import deque
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import psutil
import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from . import __version__, passages
from . import database as db
from . import espacement as espacement_mod
from .arena import bannissements, pile, visiteurs
from .arena import comptes as comptes_arena
from .arena import profils as module_profils
from .arena.profils import BASELINE, normaliser
from .config import Reglages
from .detection import registre as registre_detecteurs
from .engines import registre
from .engines.base import FonctionIndisponible, RefusProtection
from .engines.noezia import identite as module_identite
from .engines.noezia.identite import IdentiteRefusee
from .issues import CAUSE_PANNE_ARENA
from .mesures import PIDS_EXCLUS, Echantillonneur
from .perimetre import verifier_url
from .scenarios import PAGES_PAR_VISITE, SCENARIOS, avec_pages
from .site.comptes import COMPTES

journal = logging.getLogger("shadowlab.campagne")

CODE_INTERROMPU = 3
PANNES_ARENA_MAX = 3  # pannes d'Arena de suite avant d'arrêter la campagne

METRIQUES = {
    "detection_rate",
    "false_positive_rate",
    "false_negative_rate",
    "execution_time",
    "memory_usage",
    "cpu_usage",
    "scenario_success",
    "error_rate",
}


class MoteurConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    label: str | None = None  # pour comparer deux configurations du même moteur
    options: dict[str, Any] = Field(default_factory=dict)
    # Nombre de visites (passages) de CE bras, à la place de `repetitions` : la soirée en veut 24, 24, 6 et 4.
    visites: int | None = Field(default=None, ge=1, le=10_000)
    # Témoin de la sentinelle d'identité : avant cette visite, le visiteur du bras est banni dans son monde (le même
    # code que `shadowlab arena bannir`). Réservé à une entrée qui a une identité persistante.
    bannir_avant_visite: int | None = Field(default=None, ge=1)
    # Espacement propre à CE bras (I9) : il remplace celui de la campagne (ex. témoins à intervalle fixe pendant que le
    # sujet suit l'ordonnanceur).
    espacement: espacement_mod.Espacement | None = None
    # Récolte qui dure (I9) : l'état du parcours du scénario `visite` vit dans un dossier durable propre au bras
    # (`<sorties>/campagnes/<n°>/recolte/<libellé>-<protection>/`) ; chaque visite reprend là où la précédente s'est
    # arrêtée, puis commence une passe incrémentale. Faux : chaque visite repart de zéro (la soirée).
    recolte_incrementale: bool = False
    # Compte de test du bras (I10, D-104) : une fixture de `site/comptes.py`. Le scénario `visite` s'y connecte à la
    # première visite de l'identité, puis lit l'espace privé à chaque visite ; `bannir_avant_visite` bannit alors le
    # COMPTE du bras dans son monde, pas son visiteur.
    compte: str | None = None
    # Témoin des comptes (I10) : à partir de la visite `bannir_avant_visite`, les visites sont faites par cette autre
    # identité (un autre navigateur : autre profil Chrome, donc autre visiteur), avec le même compte.
    identite_apres_bannissement: str | None = None

    @field_validator("compte")
    @classmethod
    def compte_connu(cls, compte: str | None) -> str | None:
        if compte is not None and compte not in COMPTES:
            raise ValueError(f"compte inconnu : {compte} (comptes de test : {', '.join(sorted(COMPTES))})")
        return compte

    @field_validator("identite_apres_bannissement")
    @classmethod
    def nom_d_identite(cls, nom: str | None) -> str | None:
        if nom is not None:
            try:
                module_identite.verifier_nom(nom)
            except ValueError as erreur:
                raise ValueError(f"identite_apres_bannissement : {erreur}") from None
        return nom

    @property
    def nom_affiche(self) -> str:
        return self.label or self.name


class Limites(BaseModel):
    """Plafonds du superviseur : aucune nouvelle unité n'est lancée au-delà."""

    model_config = ConfigDict(extra="forbid")
    memoire_disponible_min_mo: int = Field(default=4096, ge=256)
    cpu_max_pct: int = Field(default=85, ge=10, le=100)


class Experience(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    description: str = ""
    environment: Literal["local"] = "local"
    engines: list[MoteurConfig]
    protections: list[str] = Field(default_factory=lambda: [BASELINE], min_length=1)
    scenarios: list[str]
    repetitions: int = Field(ge=1, le=10_000)
    detectors: list[str] | None = None
    metrics: list[str] = Field(default_factory=lambda: sorted(METRIQUES))
    output: list[Literal["json", "csv", "html"]] = Field(default_factory=lambda: ["json", "csv", "html"])
    seed: int | None = None
    warmup: int = Field(default=0, ge=0)
    concurrency: int = Field(default=1, ge=1)
    limites: Limites = Field(default_factory=Limites)
    monde: Literal["passage", "serie", "campagne"] = "campagne"  # portée du monde de l'Arena (arena/visiteurs.py)
    # Espacement des visites d'un bras (I7) : sans lui, les passages s'enchaînent comme avant.
    espacement: espacement_mod.Espacement | None = None
    pages_par_visite: int = Field(default=PAGES_PAR_VISITE, ge=1, le=500)  # scénario `visite` : pages lues au plus
    base_url: str | None = None
    screenshots_on_failure: bool = True

    @field_validator("engines", mode="before")
    @classmethod
    def moteurs_courts(cls, valeur: Any) -> Any:
        return [{"name": v} if isinstance(v, str) else v for v in valeur]

    @field_validator("engines")
    @classmethod
    def moteurs_connus(cls, moteurs: list[MoteurConfig]) -> list[MoteurConfig]:
        connus = registre()
        for m in moteurs:
            if m.name not in connus:
                raise ValueError(f"moteur inconnu : {m.name} (disponibles : {', '.join(sorted(connus))})")
            connus[m.name].controler_options(m.options)
        libelles = [m.nom_affiche for m in moteurs]
        if len(set(libelles)) != len(libelles):
            raise ValueError("deux moteurs ont le même libellé : ajoutez `label`")
        return moteurs

    @field_validator("protections", mode="before")
    @classmethod
    def normaliser_protections(cls, protections: list[str]) -> list[str]:
        return [normaliser(p) for p in protections]

    @field_validator("protections")
    @classmethod
    def protections_connues(cls, protections: list[str]) -> list[str]:
        profils = module_profils.charger()
        for p in protections:
            if p not in profils:
                raise ValueError(f"protection inconnue : {p} (disponibles : {', '.join(profils.codes)})")
        if len(set(protections)) != len(protections):
            raise ValueError("protection en double")
        return protections

    @field_validator("scenarios")
    @classmethod
    def scenarios_connus(cls, scenarios: list[str]) -> list[str]:
        for s in scenarios:
            if s not in SCENARIOS:
                raise ValueError(f"scénario inconnu : {s} (disponibles : {', '.join(SCENARIOS)})")
        return scenarios

    @field_validator("detectors")
    @classmethod
    def detecteurs_connus(cls, detecteurs: list[str] | None) -> list[str] | None:
        connus = registre_detecteurs()
        for d in detecteurs or []:
            if d not in connus:
                raise ValueError(f"détecteur inconnu : {d} (disponibles : {', '.join(connus)})")
        return detecteurs

    @field_validator("metrics")
    @classmethod
    def metriques_connues(cls, metriques: list[str]) -> list[str]:
        inconnues = set(metriques) - METRIQUES
        if inconnues:
            raise ValueError(f"métriques inconnues : {', '.join(sorted(inconnues))}")
        return metriques

    @model_validator(mode="after")
    def visites_et_espacement(self) -> Experience:
        nb_unites = len(self.engines) * len(self.protections)
        if self.espacement is not None or any(m.espacement is not None for m in self.engines):
            if self.scenarios != ["visite"]:
                raise ValueError("espacement : une visite est un passage, `scenarios` doit être [visite]")
            if self.concurrency < nb_unites:
                raise ValueError(
                    f"espacement : `concurrency` doit couvrir tous les bras ({nb_unites}), sinon ils tourneraient "
                    f"l'un après l'autre (reçu {self.concurrency})"
                )
        if any(m.recolte_incrementale for m in self.engines) and self.scenarios != ["visite"]:
            raise ValueError(
                "recolte_incrementale : c'est le scénario `visite` qui récolte, `scenarios` doit être [visite]"
            )
        if any(m.compte for m in self.engines) and self.scenarios != ["visite"]:
            raise ValueError("compte : c'est le scénario `visite` qui se connecte, `scenarios` doit être [visite]")
        for moteur in self.engines:
            if moteur.identite_apres_bannissement is not None:
                champ = f"identite_apres_bannissement ({moteur.nom_affiche})"
                if moteur.bannir_avant_visite is None or moteur.compte is None:
                    raise ValueError(
                        f"{champ} : il faut `compte` et `bannir_avant_visite` (le compte banni, puis la visite "
                        "suivante par une autre identité avec le même compte)"
                    )
                if moteur.identite_apres_bannissement == moteur.options.get("identite"):
                    raise ValueError(f"{champ} : il faut une autre identité que `identite`")
            if moteur.bannir_avant_visite is None:
                continue
            if "identite" not in moteur.options:
                raise ValueError(f"bannir_avant_visite ({moteur.nom_affiche}) : il faut l'option `identite`")
            if self.monde != "serie":
                raise ValueError(
                    "bannir_avant_visite : le monde doit être `serie` (un monde par bras, le même à chaque visite)"
                )
            if moteur.bannir_avant_visite > (moteur.visites or self.repetitions):
                raise ValueError(
                    f"bannir_avant_visite ({moteur.nom_affiche}) : visite {moteur.bannir_avant_visite} non prévue"
                )
        return self

    def visites_de(self, moteur: MoteurConfig) -> int:
        return moteur.visites or self.repetitions

    def total_passages(self) -> int:
        return sum(self.visites_de(m) for m in self.engines) * len(self.protections) * len(self.scenarios)


class FichierCampagne(BaseModel):
    model_config = ConfigDict(extra="forbid")
    experiment: Experience

    @model_validator(mode="after")
    def graine(self) -> FichierCampagne:
        if self.experiment.seed is None:
            self.experiment.seed = random.SystemRandom().randrange(2**31)
        return self


class _ChargeurSansAlias(yaml.SafeLoader):
    """Chargeur sûr qui refuse les alias (`*nom`) : un petit fichier ne peut pas s'étendre en un objet énorme."""

    def compose_node(self, parent, index):
        if self.check_event(yaml.AliasEvent):
            raise yaml.YAMLError("alias YAML (*nom) refusés dans une définition de campagne")
        return super().compose_node(parent, index)


def charger_yaml(source: Any) -> Any:
    return yaml.load(source, Loader=_ChargeurSansAlias)


def lire(chemin: Path, reglages: Reglages) -> Experience:
    """Lit et valide un fichier YAML. Les URL sont contrôlées par le périmètre."""
    with chemin.open(encoding="utf-8") as f:
        brut = charger_yaml(f)
    experience = FichierCampagne.model_validate(brut).experiment
    if experience.base_url:
        verifier_url(experience.base_url, reglages.hotes_autorises)
    if experience.concurrency > reglages.concurrence_max:
        raise ValueError(
            f"concurrence {experience.concurrency} > plafond {reglages.concurrence_max} (SHADOWLAB_CONCURRENCE_MAX)"
        )
    return experience


def environnement(reglages: Reglages | None = None) -> dict[str, Any]:
    env: dict[str, Any] = {
        "shadowlab": __version__,
        "python": sys.version.split()[0],
        "systeme": platform.platform(),
        "machine": platform.machine(),
        "processeurs": __import__("os").cpu_count(),
        "profils_arena": module_profils.charger().model_dump(),
    }
    if reglages is not None:
        env["arena_versions"] = pile.versions(reglages)
    return env


# --- Serveur local ------------------------------------------------------------------------------------


def _repond(hote: str, port: int) -> bool:
    try:
        with socket.create_connection((hote, port), timeout=0.5):
            return True
    except OSError:
        return False


def _identite_site(reglages: Reglages) -> bool:
    """Vérifie que le serveur sur le port est bien le site ShadowLab (signature `/lab/sante`).

    Une simple connexion TCP ne suffit pas (défaut #3) : n'importe quel service sur
    le port serait pris pour le site, et la campagne mesurerait contre le mauvais serveur.
    """
    import json
    import urllib.request

    try:
        with urllib.request.urlopen(f"{reglages.url_site}/lab/sante", timeout=1.0) as reponse:
            if reponse.status != 200:
                return False
            corps = json.loads(reponse.read().decode("utf-8"))
        return corps.get("service") == "shadowlab-site"
    except (OSError, ValueError):
        return False


@contextmanager
def serveur_local(reglages: Reglages) -> Iterator[None]:
    """Démarre le site de test dans un processus à part si rien n'écoute déjà sur le port configuré.

    Processus séparé : sa consommation CPU et mémoire n'entre pas dans la mesure des moteurs.
    Refuse de réutiliser un serveur dont l'identité n'est pas celle du site ShadowLab.
    """
    if _repond(reglages.hote, reglages.port):
        if _identite_site(reglages):
            journal.info("site de test déjà démarré sur %s", reglages.url_site)
            yield
            return
        raise RuntimeError(
            f"un service étranger répond sur {reglages.url_site} (signature /lab/sante absente ou "
            "incorrecte) : refus de lancer la campagne contre un serveur non identifié"
        )
    reglages.sorties.mkdir(parents=True, exist_ok=True)
    sortie = (reglages.sorties / "logs").joinpath("site.log")
    sortie.parent.mkdir(parents=True, exist_ok=True)
    with sortie.open("ab") as flux:
        processus = subprocess.Popen(
            [sys.executable, "-m", "shadowlab.cli", "site", "--silencieux"], stdout=flux, stderr=flux
        )
    PIDS_EXCLUS.add(processus.pid)
    try:
        for _ in range(200):
            if _identite_site(reglages):
                break
            if processus.poll() is not None:
                raise RuntimeError(f"le site de test s'est arrêté au démarrage (voir {sortie})")
            time.sleep(0.05)
        else:
            raise RuntimeError("le site de test n'a pas démarré (signature /lab/sante non obtenue)")
        yield
    finally:
        processus.terminate()
        try:
            processus.wait(timeout=5)
        except subprocess.TimeoutExpired:
            processus.kill()
        PIDS_EXCLUS.discard(processus.pid)


# --- Exécution ----------------------------------------------------------------------------------------


def fichier_arret(reglages: Reglages) -> Path:
    return reglages.sorties / "ARRET"


def creer(cx, experience: Experience, reglages: Reglages | None = None) -> int:
    curseur = cx.execute(
        "INSERT INTO experiments (id, name, description, created_at, configuration,"
        " status, seed, environment, schema_version)"
        f" VALUES ({db.PROCHAIN_ID_EXPERIENCE}, ?, ?, ?, ?, 'creee', ?, ?, ?)",
        (
            experience.name,
            experience.description,
            db.maintenant(),
            experience.model_dump_json(),
            experience.seed,
            db.j(environnement(reglages)),
            db.SCHEMA_VERSION,
        ),
    )
    return int(curseur.lastrowid)


def unites(experience: Experience) -> list[tuple[MoteurConfig, str]]:
    """Produit les unités moteur × protection, en ordre randomisé reproductible si un seed existe."""
    liste = [(moteur, protection) for moteur in experience.engines for protection in experience.protections]
    if experience.seed is not None:
        random.Random(f"{experience.seed}:unites").shuffle(liste)
    return liste


def _plan(experience: Experience, moteur: MoteurConfig, protection: str) -> Iterator[tuple[int, list[str]]]:
    rng = random.Random(f"{experience.seed}:{moteur.nom_affiche}:{protection}")
    for repetition in range(1, experience.visites_de(moteur) + 1):
        ordre = list(experience.scenarios)
        rng.shuffle(ordre)
        yield repetition, ordre


def _deja_faits(cx, experiment_id: int) -> set[tuple[str, str, str, int]]:
    return {
        (r["engine_label"], r["protection"], r["scenario"], r["repetition"])
        for r in cx.execute(
            "SELECT json_extract(e.configuration, '$.label') AS engine_label, r.protection, s.name AS scenario,"
            " r.repetition FROM runs r JOIN engines e ON e.id = r.engine_id JOIN scenarios s ON s.id = r.scenario_id"
            " WHERE r.experiment_id = ? AND r.status IN ('reussi', 'echec', 'erreur')",
            (experiment_id,),
        )
    }


def _controler_arena(reglages: Reglages, experience: Experience) -> None:
    if any(p != BASELINE for p in experience.protections) and not pile.sante(reglages):
        raise pile.ArenaIndisponible("Arena injoignable : lancez `uv run shadowlab arena demarrer`")


def _arena_en_panne(cx, experiment_id: int) -> bool:
    """Vrai si les derniers passages sous Arena de la campagne sont tous des pannes d'Arena.

    L'Arena n'est contrôlée qu'au lancement : si Docker s'arrête ensuite, chaque passage est
    enregistré en panne jusqu'à la fin (campagne 86 : 19 passages sur 24). Les passages du
    niveau de base ne traversent pas l'Arena et ne disent rien de son état.
    """
    causes = [
        ligne["cause"]
        for ligne in cx.execute(
            "SELECT cause FROM runs WHERE experiment_id = ? AND protection != ? AND status != 'en_cours'"
            " ORDER BY id DESC LIMIT ?",
            (experiment_id, BASELINE, PANNES_ARENA_MAX),
        )
    ]
    return len(causes) == PANNES_ARENA_MAX and all(cause == CAUSE_PANNE_ARENA for cause in causes)


def _degrader_si_moteur_absent(cx, experiment_id: int, statut: str) -> str:
    """Rétrograde « termine » en « termine_incomplet » si un moteur n'a pas démarré.

    Un moteur qui ne démarre pas est enregistré en erreur « démarrage impossible »
    pour chacun de ses passages (défaut #6) : la campagne ne doit pas se déclarer
    « termine » sans le signaler, car tous les passages du moteur sont absents.
    """
    if statut != "termine":
        return statut
    n = cx.execute(
        "SELECT COUNT(*) FROM runs WHERE experiment_id = ? AND status = 'erreur'"
        " AND error LIKE 'démarrage impossible%'",
        (experiment_id,),
    ).fetchone()[0]
    return "termine_incomplet" if n else "termine"


FICHIER_CADENCE = "cadence.jsonl"


def dossier_campagne(reglages: Reglages, experiment_id: int) -> Path:
    """Les sorties durables d'une campagne (I9) : notes de la cadence (`cadence.jsonl`), état des récoltes par bras."""
    return reglages.sorties / "campagnes" / str(experiment_id)


def ecrire_note(reglages: Reglages, experiment_id: int, ligne: dict[str, Any]) -> None:
    """Ajoute une ligne à `cadence.jsonl` (une seule écriture, en ajout : plusieurs bras peuvent écrire à la fois).

    Genres : `manquee` (visite manquée : motif `retard` ou `infrastructure`, heure prévue, heure constatée, clé du
    créneau, essai), `interrompue` (visite coupée en plein milieu par un arrêt brutal : début, dernière requête vue par
    l'Arena, pages), `echeance` (la course est finie pour le bras : répétitions restantes, non faites),
    `attente_alerte` (identité du bras en alerte : heure prévue, fin de l'attente, `alerte_le` ; aucune visite avant),
    `bannie` (identité du bras bannie : plus aucune visite, répétitions restantes, non faites), `prevue` (prochaine
    visite choisie par la cadence : heure prévue, heure d'écriture ; un relevé pour `course etat`, jamais un état)."""
    fichier = dossier_campagne(reglages, experiment_id) / FICHIER_CADENCE
    fichier.parent.mkdir(parents=True, exist_ok=True)
    with fichier.open("a", encoding="utf-8") as flux:
        flux.write(json.dumps(ligne, ensure_ascii=False) + "\n")


def lire_notes(reglages: Reglages, experiment_id: int) -> list[dict[str, Any]]:
    """Les lignes de `cadence.jsonl` (vide si le fichier n'existe pas ; une ligne illisible est ignorée)."""
    fichier = dossier_campagne(reglages, experiment_id) / FICHIER_CADENCE
    if not fichier.exists():
        return []
    notes = []
    for ligne in fichier.read_text(encoding="utf-8").splitlines():
        try:
            notes.append(json.loads(ligne))
        except ValueError:
            continue
    return notes


def _avec_espacement(experience: Experience) -> bool:
    return experience.espacement is not None or any(m.espacement is not None for m in experience.engines)


def preparer_reprise(cx, reglages: Reglages, experiment_id: int) -> None:
    """Un passage resté « en cours » (coupure) est rejoué : on retire sa trace incomplète.

    Dans une campagne espacée (I9), une visite coupée en plein milieu a pourtant eu lieu côté Arena : avant d'effacer,
    elle est notée dans `cadence.jsonl` (genre `interrompue` : début, dernière requête vue par l'Arena, pages au sens de
    D-78). La cadence la rejoue : l'écart et les plafonds par heure et par jour en tiennent compte."""
    ligne = cx.execute("SELECT configuration FROM experiments WHERE id = ?", (experiment_id,)).fetchone()
    if ligne is not None and _avec_espacement(Experience.model_validate_json(ligne["configuration"])):
        coupees = cx.execute(
            "SELECT r.session_token, r.started_at, r.repetition, r.protection,"
            " json_extract(e.configuration, '$.label') AS label FROM runs r JOIN engines e ON e.id = r.engine_id"
            " WHERE r.experiment_id = ? AND r.status = 'en_cours' ORDER BY r.id",
            (experiment_id,),
        ).fetchall()
        pages_sql = f"COALESCE(SUM(CASE WHEN {bannissements.clause_pages()} THEN 1 ELSE 0 END), 0)"
        for r in coupees:
            derniere, pages = cx.execute(
                f"SELECT MAX(h.received_at), {pages_sql} FROM observations_http h WHERE h.session_token = ?",
                (r["session_token"],),
            ).fetchone()
            ecrire_note(
                reglages,
                experiment_id,
                {
                    "genre": "interrompue",
                    "bras": r["label"],
                    "protection": r["protection"],
                    "repetition": r["repetition"],
                    "debut": r["started_at"],
                    "fin": derniere or r["started_at"],
                    "pages": int(pages or 0),
                },
            )
    cx.execute("DELETE FROM runs WHERE experiment_id = ? AND status = 'en_cours'", (experiment_id,))


def _pages_de_la_visite(details: dict[str, Any]) -> int:
    """Pages demandées par une visite (relectures comprises), telles que le scénario `visite` les note."""
    if details.get("pages_visite") is not None:
        return int(details["pages_visite"])
    return int(details.get("pages_faites") or 0) + int(details.get("relectures") or 0)


def _visites_du_bras(cx, reglages: Reglages, experiment_id: int, label: str, protection: str) -> list[tuple]:
    """Les visites déjà faites par le bras (début, fin, pages lues) : ses passages finis dans la base, plus ses visites
    coupées en plein milieu (`cadence.jsonl`). Heures telles qu'écrites (la cadence les ramène à son cadran)."""
    faites: list[tuple] = []
    for r in cx.execute(
        "SELECT r.started_at, r.completed_at, r.drapeaux FROM runs r JOIN engines e ON e.id = r.engine_id"
        " WHERE r.experiment_id = ? AND json_extract(e.configuration, '$.label') = ? AND r.protection = ?"
        " AND r.status IN ('reussi', 'echec', 'erreur') ORDER BY r.id",
        (experiment_id, label, protection),
    ):
        try:
            details = (json.loads(r["drapeaux"] or "{}") or {}).get("details_scenario") or {}
        except ValueError:
            details = {}
        details = details if isinstance(details, dict) else {}
        faites.append((r["started_at"], r["completed_at"] or r["started_at"], _pages_de_la_visite(details)))
    for note in lire_notes(reglages, experiment_id):
        if note.get("genre") == "interrompue" and note.get("bras") == label and note.get("protection") == protection:
            faites.append((note["debut"], note["fin"], int(note.get("pages") or 0)))
    return faites


def _panne_infrastructure(reglages: Reglages, protection: str) -> str | None:
    """Avant une visite espacée : la chaîne de l'Arena (`arena.pile.sante`, hors niveau de base) et le site du labo
    (`/lab/sante`) répondent-ils ? Rend la panne (texte), ou None. Une panne n'est pas une alerte : la visite n'est pas
    lancée, l'identité ne change pas (la sentinelle, elle, prend un 503 pour une alerte, PENDANT une visite)."""
    if protection != BASELINE and not pile.sante(reglages):
        return "chaîne de l'Arena injoignable (arena.pile.sante)"
    if not _identite_site(reglages):
        return "site du labo injoignable (/lab/sante)"
    return None


def executer(reglages: Reglages, experiment_id: int) -> str:
    """Exécute (ou reprend) une campagne. Renvoie son état final."""
    cx = db.ouvrir(reglages.base_donnees)
    ligne = cx.execute("SELECT * FROM experiments WHERE id = ?", (experiment_id,)).fetchone()
    if ligne is None:
        raise LookupError(f"expérience {experiment_id} introuvable")
    experience = Experience.model_validate_json(ligne["configuration"])
    verifier_url(experience.base_url or reglages.url_site, reglages.hotes_autorises)
    if experience.protections != [BASELINE]:
        verifier_url(reglages.url_arena, reglages.hotes_autorises)
    preparer_reprise(cx, reglages, experiment_id)
    cx.execute("UPDATE experiments SET status = 'en_cours' WHERE id = ?", (experiment_id,))
    ordre = unites(experience)
    journal.info("Ordre d'exécution : %d unités, seed %s", len(ordre), experience.seed)
    fichier_arret(reglages).unlink(missing_ok=True)
    statut = "interrompu"
    try:
        with serveur_local(reglages):
            _controler_arena(reglages, experience)
            if experience.concurrency == 1:
                statut = "termine"
                for rang in range(len(unites(experience))):
                    if executer_unite(reglages, experiment_id, rang) != "termine":
                        statut = "interrompu"
                        break
            else:
                statut = _superviser(reglages, experience, experiment_id)
    except KeyboardInterrupt:
        statut = "interrompu"
    finally:
        statut = _degrader_si_moteur_absent(cx, experiment_id, statut)
        cx.execute("UPDATE experiments SET status = ? WHERE id = ?", (statut, experiment_id))
        cx.close()
    return statut


def _ressources_disponibles(limites: Limites) -> bool:
    disponible_mo = psutil.virtual_memory().available / 1024 / 1024
    return (
        disponible_mo >= limites.memoire_disponible_min_mo and psutil.cpu_percent(interval=None) <= limites.cpu_max_pct
    )


def _travailleur(reglages: Reglages, experiment_id: int, rang: int) -> None:
    sys.exit(0 if executer_unite(reglages, experiment_id, rang) == "termine" else CODE_INTERROMPU)


def _superviser(reglages: Reglages, experience: Experience, experiment_id: int) -> str:
    """Lance les unités en parallèle, sans dépasser la concurrence ni les plafonds de ressources."""
    contexte = multiprocessing.get_context("spawn")  # processus neufs : Playwright et Chrome n'aiment pas `fork`
    en_attente = deque(range(len(unites(experience))))
    actifs: dict[int, Any] = {}
    statut = "termine"
    arret = fichier_arret(reglages)
    psutil.cpu_percent(interval=None)  # le premier appel sert de point de départ
    try:
        while en_attente or actifs:
            for rang, processus in list(actifs.items()):
                if not processus.is_alive():
                    processus.join()
                    del actifs[rang]
                    if processus.exitcode != 0:
                        statut = "interrompu"
                        journal.warning("unité %d arrêtée (code %s)", rang, processus.exitcode)
            if arret.exists():
                en_attente.clear()
                statut = "interrompu"
            # Toujours au moins une unité active : des plafonds trop serrés ralentissent, sans bloquer.
            libre = len(actifs) < experience.concurrency and (not actifs or _ressources_disponibles(experience.limites))
            if en_attente and libre:
                rang = en_attente.popleft()
                actifs[rang] = contexte.Process(target=_travailleur, args=(reglages, experiment_id, rang))
                actifs[rang].start()
            time.sleep(0.25)
    except BaseException:
        arret.parent.mkdir(parents=True, exist_ok=True)
        arret.touch()  # les travailleurs s'arrêtent proprement après leur passage en cours
        for processus in actifs.values():
            processus.join(timeout=60)
        raise
    return statut


def _moteur_indisponible(cx, experiment_id, experience, moteur_cfg, protection, faits, classe, cause: str) -> None:
    """Un moteur qui ne démarre pas est un résultat : chacun de ses passages est enregistré en erreur, avec la cause."""
    config = {**moteur_cfg.options, "label": moteur_cfg.nom_affiche}
    engine_id = db.engine_id(cx, moteur_cfg.name, db.j({"erreur": "non démarré"}), classe.runtime, config)
    for repetition, ordre in _plan(experience, moteur_cfg, protection):
        for nom_scenario in ordre:
            if (moteur_cfg.nom_affiche, protection, nom_scenario, repetition) in faits:
                continue
            scenario = SCENARIOS[nom_scenario]
            scenario_id = db.scenario_id(cx, scenario.name, scenario.description)
            run_id, jeton = passages.demarrer(
                cx, experiment_id, engine_id, scenario_id, repetition, "automatise", protection
            )
            passages.finaliser(
                cx, run_id, jeton, status="erreur", success=False, duration_ms=None, error=cause,
                attend_js=scenario.attend_js, detecteurs=experience.detectors,
            )  # fmt: skip


def _bannir_avant_visite(cx, monde: str, label: str, visite: int, compte: str | None = None) -> bool:
    """Bannit le visiteur du bras dans son monde, avant sa visite `visite` (témoin de la sentinelle d'identité) ; ou,
    pour un bras qui a un `compte` (témoin des comptes, I10), le compte dans ce monde.

    Même code que `shadowlab arena bannir` (`--visiteur` ou `--compte`). Faux (et rien d'écrit) si aucun visiteur
    n'est connu dans le monde, ou si le compte ne s'y est jamais connecté : la campagne s'arrête alors sur ce bras
    plutôt que de continuer sans le témoin. Un compte déjà banni (reprise) n'arrête rien.
    """
    if compte is not None:
        try:
            ecrit = comptes_arena.bannir_compte_connu(cx, monde, compte)
        except bannissements.BannissementRefuse as erreur:
            journal.error("%s : %s, impossible de bannir le compte avant la visite %d", label, erreur, visite)
            return False
        etat = "banni" if ecrit else "déjà banni"
        journal.info("%s : compte %s %s dans le monde %s avant la visite %d", label, compte, etat, monde, visite)
        return True
    visiteur = bannissements.dernier_visiteur(cx, monde)
    if visiteur is None:
        journal.error(
            "%s : aucun visiteur connu dans le monde %s, impossible de le bannir avant la visite %d",
            label,
            monde,
            visite,
        )
        return False
    bannissements.bannir_visiteur_connu(cx, monde, visiteur)
    journal.info("%s : visiteur %s banni dans le monde %s avant la visite %d", label, visiteur, monde, visite)
    return True


def _reglages_visite(
    reglages: Reglages, experiment_id: int, moteur_cfg: MoteurConfig, protection: str
) -> dict[str, Any]:
    """Ce que le scénario `visite` reçoit de la campagne : la durée de la porte, tirée du profil (`duree_cookie_s`
    d'un profil dont la porte est liée au visiteur, `defi_js.par_visiteur` ; sinon aucune règle de durée, la porte
    revient à chaque session), et le dossier durable de la récolte du bras (`recolte_incrementale`)."""
    profil = module_profils.charger().de(protection)
    duree = profil.duree_cookie_s if profil is not None and profil.defi_js.par_visiteur else None
    dossier = None
    if moteur_cfg.recolte_incrementale:
        nom = re.sub(r"[^a-z0-9_-]+", "-", f"{moteur_cfg.nom_affiche}-{protection}".lower()).strip("-")
        dossier = dossier_campagne(reglages, experiment_id) / "recolte" / nom
    return {"duree_porte_s": duree, "dossier_recolte": dossier, "compte": moteur_cfg.compte}


def _options_de_la_visite(moteur_cfg: MoteurConfig, repetition: int) -> dict[str, Any]:
    """Les options du pilote pour la visite `repetition` : celles du bras, sauf pour le témoin des comptes (I10) qui,
    à partir de la visite de son bannissement, prend l'autre identité (`identite_apres_bannissement`)."""
    autre = moteur_cfg.identite_apres_bannissement
    if autre and moteur_cfg.bannir_avant_visite and repetition >= moteur_cfg.bannir_avant_visite:
        return {**moteur_cfg.options, "identite": autre}
    return moteur_cfg.options


def _noteur(reglages: Reglages, experiment_id: int, label: str, protection: str) -> Callable[[dict[str, Any]], None]:
    """Écrit les notes de la cadence d'un bras. Le fichier existe dès le départ du bras (le bilan distingue « aucune
    visite manquée » de « aucune note lue »)."""
    fichier = dossier_campagne(reglages, experiment_id) / FICHIER_CADENCE
    fichier.parent.mkdir(parents=True, exist_ok=True)
    fichier.touch()

    def noter(ligne: dict[str, Any]) -> None:
        ecrire_note(reglages, experiment_id, {"bras": label, "protection": protection, **ligne})

    return noter


def _fin_de_course(noter, cadence, horloge, experience: Experience, moteur_cfg: MoteurConfig, repetition: int) -> str:
    """L'échéance est passée : plus aucune visite ne commence. Les répétitions restantes ne sont ni des échecs ni des
    visites manquées : « non faites (échéance) », notées une fois. Le bras est fini (`termine`)."""
    restantes = experience.visites_de(moteur_cfg) - repetition + 1
    echeance = cadence.echeance
    noter(
        {
            "genre": "echeance",
            "echeance": echeance.astimezone().isoformat(timespec="seconds") if echeance else None,
            "constatee": (horloge or datetime.now)().astimezone().isoformat(timespec="seconds"),
            "repetition": repetition,
            "restantes": restantes,
        }
    )
    journal.info("%s : échéance passée, %d visite(s) non faite(s)", moteur_cfg.nom_affiche, restantes)
    return "termine"


def _premiere_a_faire(experience: Experience, moteur_cfg: MoteurConfig, protection: str, faits) -> int | None:
    """La première répétition du bras qui n'est pas encore dans la base (None : tout est fait)."""
    for repetition, ordre in _plan(experience, moteur_cfg, protection):
        if any((moteur_cfg.nom_affiche, protection, nom, repetition) not in faits for nom in ordre):
            return repetition
    return None


def _identite_avant_creneau(
    nom: str, cadence, noter, horloge, experience: Experience, moteur_cfg: MoteurConfig, repetition: int
) -> str | None:
    """Avant chaque créneau d'un bras espacé qui a une identité persistante (I9, § 5.5) : l'état noté de l'identité,
    lu sans verrou. Rend `bannie` (plus aucune visite : une note avec les répétitions restantes, non faites, comme à
    l'échéance), `alerte` (aucune visite avant la fin de l'attente : la cadence le note et planifie à partir de cette
    fin, dans la plage) ou None (la visite peut avoir lieu). Aucune requête, aucun passage en base."""
    donnees = module_identite.lire_etat(nom)
    if not donnees:
        return None
    maintenant = (horloge or datetime.now)()
    if donnees.get("etat") == "banni":
        restantes = experience.visites_de(moteur_cfg) - repetition + 1
        noter(
            {
                "genre": "bannie",
                "identite": nom,
                "banni_le": donnees.get("banni_le"),
                "raison": donnees.get("raison"),
                "constatee": maintenant.astimezone().isoformat(timespec="seconds"),
                "repetition": repetition,
                "restantes": restantes,
            }
        )
        # warning : une identité déjà bannie au lancement (suffixe réutilisé) ne laisse plus aucune ligne d'erreur
        journal.warning("%s : identité %s bannie, %d visite(s) non faite(s)", moteur_cfg.nom_affiche, nom, restantes)
        return "bannie"
    fin = module_identite.fin_d_alerte(donnees, maintenant.astimezone())
    if fin is None or espacement_mod.au_cadran(fin, maintenant) <= maintenant:
        return None
    details = {"identite": nom, "alerte_le": donnees.get("alerte_le"), "raison": donnees.get("raison")}
    cadence.reporter_alerte(fin, {**details, "repetition": repetition})
    journal.info("%s : identité %s en alerte, aucune visite avant %s", moteur_cfg.nom_affiche, nom, fin.isoformat())
    return "alerte"


def executer_unite(
    reglages: Reglages,
    experiment_id: int,
    rang: int,
    *,
    horloge: Callable[[], datetime] | None = None,
    dormir: Callable[[float], None] | None = None,
) -> str:
    """Exécute un couple (moteur, protection). Renvoie `termine` ou `interrompu`.

    `horloge` et `dormir` ne servent qu'à l'espacement des visites (champ `espacement`) : injectables pour les tests."""
    cx = db.ouvrir(reglages.base_donnees)
    try:
        ligne = cx.execute(
            "SELECT configuration, created_at FROM experiments WHERE id = ?", (experiment_id,)
        ).fetchone()
        experience = Experience.model_validate_json(ligne["configuration"])
        moteur_cfg, protection = unites(experience)[rang]
        faits = _deja_faits(cx, experiment_id)
        classe = registre()[moteur_cfg.name]
        base = experience.base_url or reglages.url_site
        if protection != BASELINE:
            base = reglages.url_arena
        dossier_artefacts = reglages.sorties / "artefacts" / str(experiment_id)
        arret = fichier_arret(reglages)
        label = moteur_cfg.nom_affiche
        reglages_visite = _reglages_visite(reglages, experiment_id, moteur_cfg, protection)
        reglage_espacement = moteur_cfg.espacement or experience.espacement
        cadence = noter = None
        if reglage_espacement is not None:
            noter = _noteur(reglages, experiment_id, label, protection)
            cadence = espacement_mod.Cadence(
                reglage_espacement,
                horloge=horloge,
                dormir=dormir,
                graine=f"{experience.seed}:{label}:{protection}",
                depart=datetime.fromisoformat(ligne["created_at"]),
                faites=_visites_du_bras(cx, reglages, experiment_id, label, protection),
                notes=[
                    n
                    for n in lire_notes(reglages, experiment_id)
                    if n.get("bras") == label and n.get("protection") == protection
                ],
                noter=noter,
            )
        # Identité persistante d'un bras espacé (I9) : son état est lu avant chaque créneau. Avant d'ouvrir le pilote
        # aussi : le moteur refuse de s'ouvrir sur une identité bannie ou en alerte, et ce refus écrivait toutes les
        # répétitions restantes en erreur (« démarrage impossible »). En alerte, on attend donc la fin de l'attente (le
        # premier créneau est pris avant l'ouverture) ; bannie, le bras est fini sans rien écrire dans `runs`.
        a_faire = (
            _premiere_a_faire(experience, moteur_cfg, protection, faits)
            if cadence is not None and moteur_cfg.options.get("identite")
            else None
        )
        options_pilote = _options_de_la_visite(moteur_cfg, a_faire or 1)  # reprise après le bannissement : l'autre
        nom_identite = options_pilote.get("identite") if cadence is not None else None
        premier = None
        if nom_identite and a_faire is not None:
            etat = _identite_avant_creneau(nom_identite, cadence, noter, horloge, experience, moteur_cfg, a_faire)
            if etat == "bannie":
                return "termine"
            if etat == "alerte":
                premier = cadence.attendre(interrompre=arret.exists)
                if premier is None:
                    return "interrompu"
                if premier.echeance:
                    return _fin_de_course(noter, cadence, horloge, experience, moteur_cfg, a_faire)
        pilote = classe(reglages.hotes_autorises, options_pilote)
        try:
            pilote.open()
        except Exception as exc:  # noqa: BLE001 — un moteur qui ne démarre pas ne doit pas arrêter la campagne
            cause = f"démarrage impossible : {type(exc).__name__}: {str(exc)[:300]}"
            journal.error("%s : %s", moteur_cfg.nom_affiche, cause)
            _moteur_indisponible(cx, experiment_id, experience, moteur_cfg, protection, faits, classe, cause)
            return "termine"
        try:
            config = {**pilote.configuration(), "label": moteur_cfg.nom_affiche}
            versions = pilote.versions()
            engine_id = db.engine_id(cx, moteur_cfg.name, db.j(versions), pilote.runtime, config)
            journal.info("moteur %s (%s) %s", moteur_cfg.nom_affiche, protection, versions)
            for repetition, ordre in _plan(experience, moteur_cfg, protection):
                for nom_scenario in ordre:
                    if (moteur_cfg.nom_affiche, protection, nom_scenario, repetition) in faits:
                        continue
                    if arret.exists():
                        return "interrompu"
                    scenario = SCENARIOS[nom_scenario]
                    creneau = None
                    if cadence is not None and noter is not None:  # une visite = un passage ; scénario `visite` seul
                        while True:
                            if premier is not None:  # attendu avant l'ouverture du pilote (identité en alerte)
                                creneau, premier = premier, None
                            else:
                                if nom_identite and (
                                    _identite_avant_creneau(
                                        nom_identite, cadence, noter, horloge, experience, moteur_cfg, repetition
                                    )
                                    == "bannie"
                                ):
                                    return "termine"
                                creneau = cadence.attendre(interrompre=arret.exists)  # en alerte : pas avant la fin
                                if creneau is None:
                                    return "interrompu"
                                if creneau.echeance:
                                    return _fin_de_course(noter, cadence, horloge, experience, moteur_cfg, repetition)
                            panne = _panne_infrastructure(reglages, protection)
                            if panne is None:
                                break
                            journal.warning("%s : visite non lancée, %s ; nouvel essai dans 5 min", label, panne)
                            cadence.manquer(creneau, "infrastructure", panne)
                        scenario = avec_pages(creneau.pages or experience.pages_par_visite, **reglages_visite)
                    elif nom_scenario == "visite":
                        scenario = avec_pages(experience.pages_par_visite, **reglages_visite)
                    scenario_id = db.scenario_id(cx, scenario.name, scenario.description)
                    graine = f"{experience.seed}:{moteur_cfg.nom_affiche}:{protection}:{nom_scenario}:{repetition}"
                    monde = visiteurs.nom_monde(
                        experience.monde, experiment_id, moteur_cfg.nom_affiche, protection, nom_scenario, repetition
                    )
                    if moteur_cfg.bannir_avant_visite == repetition:
                        if not _bannir_avant_visite(cx, monde, label, repetition, moteur_cfg.compte):
                            return "interrompu"
                        options = _options_de_la_visite(moteur_cfg, repetition)
                        if options != options_pilote:  # témoin des comptes : la suite par l'autre identité (I10)
                            pilote.close()
                            pilote, options_pilote = classe(reglages.hotes_autorises, options), options
                            try:
                                pilote.open()
                            except Exception as exc:  # noqa: BLE001 — même règle qu'au premier démarrage
                                journal.error("%s : autre identité, démarrage impossible : %s", label, exc)
                                return "interrompu"
                            config = {**pilote.configuration(), "label": label}
                            versions = pilote.versions()
                            engine_id = db.engine_id(cx, moteur_cfg.name, db.j(versions), pilote.runtime, config)
                            nom_identite = options.get("identite") if cadence is not None else None
                            journal.info("%s : visites suivantes par l'identité %s", label, nom_identite)
                    details = _passage(
                        cx,
                        reglages,
                        experience,
                        experiment_id,
                        pilote,
                        engine_id,
                        scenario,
                        scenario_id,
                        repetition,
                        protection,
                        base,
                        random.Random(graine),
                        dossier_artefacts,
                        engine_version=db.j(versions),
                        monde=monde,
                    )
                    if cadence is not None and creneau is not None:
                        cadence.terminer(creneau, _pages_de_la_visite(details or {}))
                    if protection != BASELINE and _arena_en_panne(cx, experiment_id):
                        journal.error(
                            "Arena injoignable sur %d passages de suite : campagne arrêtée. "
                            "Relancez l'Arena puis `shadowlab reprendre %d`.",
                            PANNES_ARENA_MAX,
                            experiment_id,
                        )
                        arret.parent.mkdir(parents=True, exist_ok=True)
                        arret.touch()  # les autres unités s'arrêtent après leur passage en cours
                        return "interrompu"
        except (KeyboardInterrupt, MemoryError) as erreur:
            journal.error("arrêt : %s", erreur)
            return "interrompu"
        finally:
            pilote.close()
        return "termine"
    finally:
        cx.close()


def _resultat_passage(
    erreur: str | None, succes: bool | None, depassement: bool, plafond_mo: float | None
) -> tuple[str, str | None, bool]:
    """Calcule (statut, erreur_finale, succes_final) pour un passage.

    Un dépassement du plafond mémoire est une erreur technique : il doit être
    intégré *avant* le calcul du statut, faute de quoi un passage réussi mais
    hors budget mémoire serait étiqueté « reussi » (défaut #4).
    """
    if depassement:
        erreur = (erreur or "") + f" plafond mémoire dépassé ({plafond_mo} Mo)"
    statut = "erreur" if erreur else ("reussi" if succes else "echec")
    succes_final = bool(succes) if not erreur else False
    return statut, erreur, succes_final


def _passage(
    cx,
    reglages,
    experience,
    experiment_id,
    pilote,
    engine_id,
    scenario,
    scenario_id,
    repetition,
    protection,
    base,
    rng,
    dossier_artefacts,
    engine_version: str = "",
    monde: str | None = None,
) -> dict[str, Any]:
    """Un passage ; rend les détails du scénario (la cadence en lit les pages lues)."""
    profil = module_profils.charger().de(protection)
    protection_config = (
        db.j(
            {
                "profil": profil.model_dump(),
                "detecteurs": {n: d.version for n, d in registre_detecteurs().items()},
            }
        )
        if profil
        else None
    )
    run_id, jeton = passages.demarrer(
        cx,
        experiment_id,
        engine_id,
        scenario_id,
        repetition,
        "automatise",
        protection,
        protection_config=protection_config,
        is_warmup=repetition <= experience.warmup,
        engine_version=engine_version,
        monde=monde,
    )
    pilote.mesures = type(pilote.mesures)()
    erreur: str | None = None
    succes: bool | None = None
    details: dict[str, Any] = {}
    with Echantillonneur(reglages.memoire_max_mo) as echantillon:
        debut = time.perf_counter()
        try:
            pilote.start_session()
            natif = pilote.scenario_natif(scenario.name, base, jeton)
            if natif is not None:
                succes, details = natif["success"], natif.get("details", {})
            else:
                issue = scenario.executer(pilote, base, jeton, rng)
                succes, details = issue.success, issue.details
            # Une page de refus ne porte pas l'observateur : rien à attendre.
            if scenario.attend_js and pilote.executes_javascript and not pilote.texts("body[data-arena]"):
                pilote.wait_for_element("#observation-envoyee", timeout_ms=5000)
        except FonctionIndisponible as exc:  # une limite du moteur, pas une panne
            succes, details = False, {"fonction_indisponible": str(exc)}
        except (
            IdentiteRefusee
        ) as exc:  # l'identité ne peut plus servir (bannie, alerte récente) : zéro requête, un résultat
            succes, details = False, {"identite_refusee": str(exc), "pages_faites": 0}
        except RefusProtection as exc:  # les décisions enregistrées disent quelle couche a refusé
            succes, details = False, {"refus": str(exc)}
        except Exception as exc:  # une erreur de moteur est un résultat, pas une panne de la campagne
            erreur = f"{type(exc).__name__}: {exc}"
            journal.debug("passage %s : %s", run_id, traceback.format_exc())
        duree = (time.perf_counter() - debut) * 1000
        if experience.screenshots_on_failure and pilote.runtime == "navigateur" and (erreur or not succes):
            try:
                chemin = pilote.capture_screenshot(dossier_artefacts / f"run-{run_id}.png")
                cx.execute(
                    "INSERT INTO artifacts (run_id, artifact_type, file_path, created_at)"
                    " VALUES (?, 'screenshot', ?, ?)",
                    (run_id, str(chemin), db.maintenant()),
                )
            except Exception:
                pass
        try:
            pilote.close_session()
        except Exception as exc:
            erreur = erreur or f"fermeture : {type(exc).__name__}: {exc}"
    time.sleep(0.05)  # laisse arriver la balise de fin de page envoyée à la fermeture
    mesures = pilote.collect_metrics()
    if mesures.details:
        details = {**details, **mesures.details}
    metriques = {
        **echantillon.resultat(),
        "navigation_time": round(mesures.navigation_time, 1),
        "request_count": mesures.request_count,
        "error_count": mesures.error_count,
    }
    statut, erreur, succes_final = _resultat_passage(erreur, succes, echantillon.depassement, reglages.memoire_max_mo)
    passages.finaliser(
        cx,
        run_id,
        jeton,
        status=statut,
        success=succes_final,
        duration_ms=round(duree, 1),
        error=erreur or (db.j(details) if not succes else None),
        motif_echec=db.j(details) if details else None,
        attend_js=scenario.attend_js,
        detecteurs=experience.detectors,
        metriques=metriques,
    )
    journal.info("%s · %s · rép. %d : %s (%.0f ms)", pilote.name, scenario.name, repetition, statut, duree)
    if echantillon.depassement:
        raise MemoryError(f"plafond mémoire dépassé ({reglages.memoire_max_mo} Mo)")
    return details
