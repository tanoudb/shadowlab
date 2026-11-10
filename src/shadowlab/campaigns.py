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

import logging
import multiprocessing
import platform
import random
import socket
import subprocess
import sys
import time
import traceback
from collections import deque
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Literal

import psutil
import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from . import __version__, passages
from . import database as db
from .arena import pile
from .arena import profils as module_profils
from .arena.profils import BASELINE, normaliser
from .config import Reglages
from .detection import registre as registre_detecteurs
from .engines import registre
from .engines.base import FonctionIndisponible, RefusProtection
from .mesures import PIDS_EXCLUS, Echantillonneur
from .perimetre import verifier_url
from .scenarios import SCENARIOS

journal = logging.getLogger("shadowlab.campagne")

CODE_INTERROMPU = 3

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
        "INSERT INTO experiments (name, description, created_at, configuration,"
        " status, seed, environment, schema_version)"
        " VALUES (?, ?, ?, ?, 'creee', ?, ?, ?)",
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
    for repetition in range(1, experience.repetitions + 1):
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
    # Un passage resté « en cours » (coupure) est rejoué : on retire sa trace incomplète.
    cx.execute("DELETE FROM runs WHERE experiment_id = ? AND status = 'en_cours'", (experiment_id,))
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


def executer_unite(reglages: Reglages, experiment_id: int, rang: int) -> str:
    """Exécute un couple (moteur, protection). Renvoie `termine` ou `interrompu`."""
    cx = db.ouvrir(reglages.base_donnees)
    try:
        ligne = cx.execute("SELECT configuration FROM experiments WHERE id = ?", (experiment_id,)).fetchone()
        experience = Experience.model_validate_json(ligne["configuration"])
        moteur_cfg, protection = unites(experience)[rang]
        faits = _deja_faits(cx, experiment_id)
        classe = registre()[moteur_cfg.name]
        base = experience.base_url or reglages.url_site
        if protection != BASELINE:
            base = reglages.url_arena
        dossier_artefacts = reglages.sorties / "artefacts" / str(experiment_id)
        arret = fichier_arret(reglages)
        pilote = classe(reglages.hotes_autorises, moteur_cfg.options)
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
                    scenario_id = db.scenario_id(cx, scenario.name, scenario.description)
                    graine = f"{experience.seed}:{moteur_cfg.nom_affiche}:{protection}:{nom_scenario}:{repetition}"
                    _passage(
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
                    )
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
) -> None:
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
