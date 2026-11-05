"""API de consultation (et de lancement) des expériences, servie sous `/api`.

Sécurité : en écoute locale, la lecture est libre ; dès que l'interface écoute sur une autre adresse,
chaque appel exige `Authorization: Bearer <SHADOWLAB_JETON>`. Les appels qui écrivent exigent en plus
l'en-tête `X-ShadowLab: 1` (une page web tierce ne peut pas l'ajouter sans autorisation CORS).
"""

from __future__ import annotations

import hmac
import ipaddress
import json
import threading
import time
from pathlib import Path

import yaml
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, StreamingResponse
from pydantic import ValidationError

from . import campaigns, reports
from . import database as db
from .analytics import comparer as comparer_experiences
from .analytics import statistiques
from .arena import profils as module_profils
from .arena.profils import BASELINE
from .config import Reglages
from .detection import registre as registre_detecteurs
from .engines import registre as registre_moteurs
from .scenarios import SCENARIOS

_verrou_campagne = threading.Lock()


def _reglages(request: Request) -> Reglages:
    return request.app.state.reglages


def _local(hote: str) -> bool:
    if hote == "localhost":
        return True
    try:
        return ipaddress.ip_address(hote).is_loopback
    except ValueError:
        return False


def autoriser(request: Request) -> None:
    reglages = _reglages(request)
    if _local(reglages.hote):
        return
    if not reglages.jeton_api:
        raise HTTPException(503, "interface exposée sans SHADOWLAB_JETON : accès refusé")
    fourni = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    if not hmac.compare_digest(fourni, reglages.jeton_api):
        raise HTTPException(401, "jeton invalide")


def ecriture(request: Request) -> None:
    autoriser(request)
    if request.headers.get("x-shadowlab") != "1":
        raise HTTPException(403, "en-tête X-ShadowLab manquant")


routeur = APIRouter(prefix="/api", dependencies=[Depends(autoriser)], tags=["api"])


def _base(request: Request):
    return request.app.state.base()


@routeur.get("/sante")
def sante() -> dict:
    return {"statut": "ok"}


@routeur.get("/moteurs")
def moteurs(request: Request) -> dict:
    with _base(request) as cx:
        enregistres = [
            {
                "id": r["id"],
                "name": r["name"],
                "versions": db.lj(r["version"]),
                "runtime": r["runtime"],
                "configuration": db.lj(r["configuration"]),
            }
            for r in cx.execute("SELECT * FROM engines ORDER BY id")
        ]
    disponibles = [
        {
            "name": nom,
            "runtime": classe.runtime,
            "categorie": classe.categorie,
            "javascript": classe.executes_javascript,
            "description": (classe.__doc__ or "").strip().split("\n")[0],
            "pret": classe.manque() is None,
            "manque": classe.manque(),
        }
        for nom, classe in sorted(registre_moteurs().items())
    ]
    return {"disponibles": disponibles, "enregistres": enregistres}


@routeur.get("/scenarios")
def scenarios() -> list[dict]:
    return [{"name": s.name, "description": s.description, "javascript": s.attend_js} for s in SCENARIOS.values()]


@routeur.get("/detecteurs")
def detecteurs() -> list[dict]:
    return [
        {"name": d.name, "version": d.version, "description": (type(d).__doc__ or "").strip()}
        for d in registre_detecteurs().values()
    ]


@routeur.get("/experiences")
def experiences(request: Request) -> list[dict]:
    with _base(request) as cx:
        return [
            dict(r)
            for r in cx.execute(
                """SELECT e.id, e.name, e.description, e.created_at, e.status, e.seed,
                          COUNT(r.id) AS passages,
                          SUM(r.status = 'reussi') AS reussis,
                          SUM(r.status = 'erreur') AS erreurs
                   FROM experiments e LEFT JOIN runs r ON r.experiment_id = e.id
                   GROUP BY e.id ORDER BY e.id DESC"""
            )
        ]


@routeur.get("/experiences/{experiment_id}/statistiques")
def stats(experiment_id: int, request: Request) -> dict:
    with _base(request) as cx:
        try:
            return statistiques(cx, experiment_id)
        except LookupError as erreur:
            raise HTTPException(404, str(erreur)) from erreur


@routeur.get("/experiences/{experiment_id}/passages")
def liste_passages(
    experiment_id: int,
    request: Request,
    limite: int = 100,
    decalage: int = 0,
    moteur: str | None = None,
    scenario: str | None = None,
) -> list[dict]:
    limite = max(1, min(limite, 1000))
    with _base(request) as cx:
        return [
            dict(r)
            for r in cx.execute(
                """SELECT r.id, COALESCE(json_extract(e.configuration, '$.label'), e.name) AS moteur,
                          e.name AS engine, s.name AS scenario, r.repetition, r.status, r.duration_ms, r.error,
                          m.cpu_usage, m.cpu_time_ms, m.memory_usage, m.request_count,
                          (SELECT COUNT(*) FROM detections d WHERE d.run_id = r.id
                             AND d.classification = 'automatise') AS detections
                   FROM runs r JOIN engines e ON e.id = r.engine_id JOIN scenarios s ON s.id = r.scenario_id
                   LEFT JOIN metrics m ON m.run_id = r.id
                   WHERE r.experiment_id = :experience
                     AND (:moteur IS NULL OR COALESCE(json_extract(e.configuration, '$.label'), e.name) = :moteur)
                     AND (:scenario IS NULL OR s.name = :scenario)
                   ORDER BY r.id LIMIT :limite OFFSET :decalage""",
                {
                    "experience": experiment_id,
                    "moteur": moteur,
                    "scenario": scenario,
                    "limite": limite,
                    "decalage": decalage,
                },
            )
        ]


@routeur.get("/passages/{run_id}")
def passage(run_id: int, request: Request) -> dict:
    with _base(request) as cx:
        run = cx.execute(
            """SELECT r.*, s.name AS scenario, e.name AS engine,
                      COALESCE(json_extract(e.configuration, '$.label'), e.name) AS moteur
               FROM runs r JOIN engines e ON e.id = r.engine_id JOIN scenarios s ON s.id = r.scenario_id
               WHERE r.id = ?""",
            (run_id,),
        ).fetchone()
        if run is None:
            raise HTTPException(404, "passage introuvable")
        empreinte = cx.execute("SELECT * FROM fingerprints WHERE run_id = ?", (run_id,)).fetchone()
        mesures = cx.execute("SELECT * FROM metrics WHERE run_id = ?", (run_id,)).fetchone()
        jeton = run["session_token"]
        decisions_couches = [
            {"couche": d["couche"], "decision": d["decision"], "chemin": d["chemin"], "motifs": db.lj(d["motifs"])}
            for d in cx.execute(
                "SELECT couche, decision, chemin, motifs FROM decisions WHERE session_token = ? ORDER BY id",
                (jeton,),
            )
        ]
        requetes = [
            {
                "received_at": o["received_at"],
                "method": o["method"],
                "path": o["path"],
                "http_version": o["http_version"],
                "status": o["status"],
                "source": o["source"],
                "nb_entetes": len(db.lj(o["headers"]) or []),
            }
            for o in cx.execute(
                "SELECT received_at, method, path, http_version, status, source, headers FROM observations_http"
                " WHERE session_token = ? ORDER BY id LIMIT 200",
                (jeton,),
            )
        ]
        return {
            "passage": {k: run[k] for k in run.keys() if k != "session_token"},
            "empreinte": {
                k: db.lj(empreinte[k])
                for k in ("browser_properties", "http_properties", "tls_properties", "session_properties")
            }
            if empreinte
            else None,
            "detections": [
                {**dict(d), "signals": db.lj(d["signals"])}
                for d in cx.execute(
                    "SELECT detector_name, detector_version, classification, confidence, signals"
                    " FROM detections WHERE run_id = ?",
                    (run_id,),
                )
            ],
            "mesures": dict(mesures) if mesures else None,
            "artefacts": [
                {
                    "id": a["id"],
                    "type": a["artifact_type"],
                    "url": f"/api/artefacts/{a['id']}",
                    "created_at": a["created_at"],
                }
                for a in cx.execute("SELECT id, artifact_type, created_at FROM artifacts WHERE run_id = ?", (run_id,))
            ],
            "decisions_couches": decisions_couches,
            "requetes": requetes,
        }


@routeur.get("/experiences/{experiment_id}/export.{format}")
def export(experiment_id: int, format: str, request: Request):
    with _base(request) as cx:
        try:
            if format == "json":
                return statistiques(cx, experiment_id)
            if format == "csv":
                return PlainTextResponse(
                    reports.lignes_csv(cx, experiment_id),
                    media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="experience-{experiment_id}.csv"'},
                )
            if format == "html":
                return HTMLResponse(reports.rapport_html(statistiques(cx, experiment_id)))
        except LookupError as erreur:
            raise HTTPException(404, str(erreur)) from erreur
    raise HTTPException(404, "format inconnu (json, csv, html)")


@routeur.get("/comparaison")
def comparaison(ids: str, request: Request) -> dict:
    try:
        identifiants = [int(i) for i in ids.split(",") if i.strip()][:10]
    except ValueError as erreur:
        raise HTTPException(400, "ids : liste d'entiers séparés par des virgules") from erreur
    with _base(request) as cx:
        experiences = []
        for i in identifiants:
            try:
                s = statistiques(cx, i)
            except LookupError:
                continue
            experiences.append({"experience": s["experience"], "moteurs": s["moteurs"]})
        deltas = None
        if len(identifiants) == 2:
            try:
                deltas = comparer_experiences(cx, identifiants[0], identifiants[1])
            except LookupError:
                pass
        return {"experiences": experiences, "deltas": deltas}


@routeur.post("/experiences", dependencies=[Depends(ecriture)], status_code=201)
async def creer(request: Request) -> dict:
    """Crée une expérience à partir d'un YAML (corps de la requête) et la lance en arrière-plan."""
    reglages = _reglages(request)
    texte = (await request.body()).decode("utf-8", "replace")
    if len(texte) > 32_000:
        raise HTTPException(413, "définition trop longue")
    try:
        brut = campaigns.charger_yaml(texte)
        experience = campaigns.FichierCampagne.model_validate(brut).experiment
        if experience.base_url:
            campaigns.verifier_url(experience.base_url, reglages.hotes_autorises)
        if experience.concurrency > reglages.concurrence_max:
            raise ValueError(f"concurrence {experience.concurrency} > plafond {reglages.concurrence_max}")
    except (yaml.YAMLError, ValidationError, ValueError) as erreur:
        raise HTTPException(422, str(erreur)) from erreur
    if not _verrou_campagne.acquire(blocking=False):
        raise HTTPException(409, "une campagne est déjà en cours")

    def travail() -> None:
        try:
            campaigns.executer(reglages, experiment_id)
            with request.app.state.base() as cx:
                reports.exporter(
                    cx, experiment_id, reglages.sorties / "rapports" / str(experiment_id), experience.output
                )
        finally:
            _verrou_campagne.release()

    try:
        with _base(request) as cx:
            experiment_id = campaigns.creer(cx, experience, reglages)
        threading.Thread(target=travail, daemon=True, name=f"campagne-{experiment_id}").start()
    except BaseException:
        _verrou_campagne.release()  # le fil n'a pas démarré : personne d'autre ne libérera le verrou
        raise
    return {"id": experiment_id, "statut": "lancee"}


@routeur.post("/arret", dependencies=[Depends(ecriture)])
def arret(request: Request) -> dict:
    chemin: Path = campaigns.fichier_arret(_reglages(request))
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.touch()
    return {"statut": "arret demande"}


@routeur.get("/reglages")
def reglages_publics(request: Request) -> dict:
    """Réglages sans secret, pour la page « Réglages » du tableau de bord."""
    r = _reglages(request)
    return {
        "hote": r.hote,
        "port": r.port,
        "hotes_autorises": list(r.hotes_autorises),
        "memoire_max_mo": r.memoire_max_mo,
        "concurrence_max": r.concurrence_max,
        "base_donnees": r.base_donnees.name,
        "jeton_configure": bool(r.jeton_api),
        "campagne_en_cours": _verrou_campagne.locked(),
    }


@routeur.get("/experiences/{experiment_id}/decisions")
def decisions(experiment_id: int, request: Request) -> dict:
    """Résumé des décisions de protection pour une expérience : par couche et par type."""
    with _base(request) as cx:
        lignes = cx.execute(
            """SELECT d.couche, d.decision, COUNT(*) AS n
               FROM decisions d JOIN runs r ON r.session_token = d.session_token
               WHERE r.experiment_id = ?
               GROUP BY d.couche, d.decision ORDER BY d.couche, d.decision""",
            (experiment_id,),
        ).fetchall()
        par_couche: dict[str, dict[str, int]] = {}
        for r in lignes:
            par_couche.setdefault(r["couche"], {})[r["decision"]] = r["n"]
        return {"couches": par_couche}


@routeur.get("/experiences/{experiment_id}/protections")
def protections(experiment_id: int, request: Request) -> dict:
    """Résultats par niveau de protection : réussite, détection, durée pour chaque combinaison moteur×protection."""
    with _base(request) as cx:
        lignes = cx.execute(
            """SELECT r.protection,
                      COALESCE(json_extract(e.configuration, '$.label'), e.name) AS moteur,
                      e.name AS engine,
                      COUNT(*) AS passages,
                      SUM(r.status = 'reussi') AS reussis,
                      AVG(r.duration_ms) AS duree_moy,
                      r.issue
               FROM runs r JOIN engines e ON e.id = r.engine_id
               WHERE r.experiment_id = ? AND r.status != 'en_cours'
               GROUP BY r.protection, moteur, r.issue
               ORDER BY r.protection, moteur""",
            (experiment_id,),
        ).fetchall()
        resultat: dict[str, list[dict]] = {}
        for r in lignes:
            resultat.setdefault(r["protection"], []).append(
                {
                    "moteur": r["moteur"],
                    "engine": r["engine"],
                    "passages": r["passages"],
                    "reussis": r["reussis"],
                    "duree_moy": round(r["duree_moy"], 1) if r["duree_moy"] else None,
                    "issue": r["issue"],
                }
            )
        return {"protections": resultat}


@routeur.get("/experiences/{experiment_id}/signaux")
def signaux(experiment_id: int, request: Request) -> dict:
    """Fréquence de chaque signal, par moteur et par détecteur : ce qui a fait classer les sessions."""
    compte: dict[tuple[str, str, str], dict] = {}
    passages_par_moteur: dict[str, int] = {}
    with _base(request) as cx:
        for r in cx.execute(
            """SELECT COALESCE(json_extract(e.configuration, '$.label'), e.name) AS moteur, r.id
               FROM runs r JOIN engines e ON e.id = r.engine_id WHERE r.experiment_id = ?""",
            (experiment_id,),
        ):
            passages_par_moteur[r["moteur"]] = passages_par_moteur.get(r["moteur"], 0) + 1
        for d in cx.execute(
            """SELECT COALESCE(json_extract(e.configuration, '$.label'), e.name) AS moteur,
                      d.detector_name, d.signals
               FROM detections d JOIN runs r ON r.id = d.run_id JOIN engines e ON e.id = r.engine_id
               WHERE r.experiment_id = ?""",
            (experiment_id,),
        ):
            for s in db.lj(d["signals"]) or []:
                cle = (d["moteur"], d["detector_name"], s["code"])
                entree = compte.setdefault(cle, {"description": s["description"], "poids": s["poids"], "n": 0})
                entree["n"] += 1
    return {
        "passages": passages_par_moteur,
        "signaux": [
            {"moteur": m, "detecteur": det, "code": code, **v}
            for (m, det, code), v in sorted(compte.items(), key=lambda kv: (kv[0][0], kv[0][1], -kv[1]["n"]))
        ],
    }


# --- Parcours expérimental : catalogue, validation, progression, flux, artefacts -----------------


@routeur.get("/protections")
def catalogue_protections() -> dict:
    """Liste les niveaux de protection de l'Arena et ce que chacun active (constructeur de campagne et doc)."""
    profils = module_profils.charger()
    niveaux = [
        {
            "code": code,
            "nom": p.nom or ("Baseline" if code == BASELINE else code),
            "description": p.description,
            "baseline": code == BASELINE,
            "limitation": {"debit": p.limitation.debit, "rafale": p.limitation.rafale},
            "waf": {"mode": p.waf.mode, "paranoia": p.waf.paranoia, "seuil": p.waf.seuil},
            "defi_js": {"actif": p.defi_js.actif, "difficulte": p.defi_js.difficulte, "lier_tls": p.defi_js.lier_tls},
            "captcha": p.captcha.actif,
            "fingerprinting": {"actif": p.fingerprinting.actif, "bloquer": p.fingerprinting.bloquer},
            "honeypots": p.honeypots.actif,
            "turnstile": p.turnstile.actif,
            "recaptcha": p.recaptcha.actif,
        }
        for code, p in profils.items()
    ]
    return {"protections": niveaux}


def _experience_depuis_corps(texte: str) -> campaigns.Experience:
    if len(texte) > 32_000:
        raise ValueError("définition trop longue")
    brut = campaigns.charger_yaml(texte)  # YAML est un sur-ensemble de JSON : le front envoie du JSON
    return campaigns.FichierCampagne.model_validate(brut).experiment


@routeur.post("/experiences/valider")
async def valider(request: Request) -> dict:
    """Valide une définition d'expérience (JSON) sans la lancer, et renvoie le nombre de passages prévus."""
    reglages = _reglages(request)
    texte = (await request.body()).decode("utf-8", "replace")
    try:
        experience = _experience_depuis_corps(texte)
        if experience.base_url:
            campaigns.verifier_url(experience.base_url, reglages.hotes_autorises)
        if experience.concurrency > reglages.concurrence_max:
            raise ValueError(f"concurrence {experience.concurrency} > plafond {reglages.concurrence_max}")
    except (yaml.YAMLError, ValidationError, ValueError) as erreur:
        return {"valide": False, "erreur": str(erreur)}
    total = len(experience.engines) * len(experience.protections) * len(experience.scenarios) * experience.repetitions
    return {
        "valide": True,
        "nom": experience.name,
        "seed": experience.seed,
        "total": total,
        "moteurs": [m.nom_affiche for m in experience.engines],
        "protections": experience.protections,
        "scenarios": experience.scenarios,
    }


def _progression(cx, experiment_id: int) -> dict:
    """État d'avancement d'une campagne : total prévu (depuis la config), passages faits, par statut et par issue."""
    ligne = cx.execute("SELECT configuration, status FROM experiments WHERE id = ?", (experiment_id,)).fetchone()
    if ligne is None:
        raise LookupError(f"expérience {experiment_id} introuvable")
    experience = campaigns.Experience.model_validate_json(ligne["configuration"])
    total = len(experience.engines) * len(experience.protections) * len(experience.scenarios) * experience.repetitions
    par_statut = {
        r["status"]: r["n"]
        for r in cx.execute(
            "SELECT status, COUNT(*) n FROM runs WHERE experiment_id = ? AND is_warmup = 0 GROUP BY status",
            (experiment_id,),
        )
    }
    par_issue = {
        r["issue"]: r["n"]
        for r in cx.execute(
            "SELECT COALESCE(issue, 'inconnue') issue, COUNT(*) n FROM runs"
            " WHERE experiment_id = ? AND is_warmup = 0 AND status IN ('reussi', 'echec', 'erreur') GROUP BY issue",
            (experiment_id,),
        )
    }
    faits = sum(par_statut.get(s, 0) for s in ("reussi", "echec", "erreur"))
    moyenne = cx.execute(
        "SELECT AVG(duration_ms) m FROM runs WHERE experiment_id = ? AND is_warmup = 0 AND duration_ms IS NOT NULL",
        (experiment_id,),
    ).fetchone()["m"]
    restant = max(0, total - faits)
    eta = round(moyenne * restant / max(1, experience.concurrency) / 1000, 1) if (moyenne and restant) else None
    return {
        "experience": experiment_id,
        "etat": ligne["status"],
        "total": total,
        "faits": faits,
        "restant": restant,
        "pourcentage": round(faits / total * 100, 1) if total else 0.0,
        "en_cours": par_statut.get("en_cours", 0),
        "par_statut": par_statut,
        "par_issue": par_issue,
        "duree_moyenne_ms": round(moyenne, 1) if moyenne else None,
        "eta_secondes": eta,
    }


@routeur.get("/experiences/{experiment_id}/progression")
def progression(experiment_id: int, request: Request) -> dict:
    with _base(request) as cx:
        try:
            return _progression(cx, experiment_id)
        except LookupError as erreur:
            raise HTTPException(404, str(erreur)) from erreur


@routeur.get("/experiences/{experiment_id}/flux")
def flux(experiment_id: int, request: Request) -> StreamingResponse:
    """Flux SSE : émet la progression chaque seconde tant que la campagne tourne, puis se ferme."""
    base = request.app.state.base
    with base() as cx:
        try:
            initial = _progression(cx, experiment_id)
        except LookupError as erreur:
            raise HTTPException(404, str(erreur)) from erreur

    def evenements():
        progres = initial
        for _ in range(3600):  # plafond d'une heure : jamais de fil infini
            yield f"data: {json.dumps(progres, ensure_ascii=False)}\n\n"
            if progres["etat"] not in ("creee", "en_cours"):
                break
            time.sleep(1.0)
            with base() as cx:
                try:
                    progres = _progression(cx, experiment_id)
                except LookupError:
                    break

    return StreamingResponse(
        evenements(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


@routeur.get("/artefacts/{artifact_id}")
def artefact(artifact_id: int, request: Request) -> FileResponse:
    """Sert un artefact (capture d'écran) en vérifiant qu'il reste sous le dossier des sorties (anti-traversée)."""
    reglages = _reglages(request)
    with _base(request) as cx:
        ligne = cx.execute("SELECT file_path FROM artifacts WHERE id = ?", (artifact_id,)).fetchone()
    if ligne is None:
        raise HTTPException(404, "artefact introuvable")
    chemin = Path(ligne["file_path"]).resolve()
    racine = (reglages.sorties / "artefacts").resolve()
    if not chemin.is_file() or not chemin.is_relative_to(racine):
        raise HTTPException(404, "artefact introuvable")
    media = "image/png" if chemin.suffix.lower() == ".png" else "application/octet-stream"
    return FileResponse(chemin, media_type=media, headers={"Cache-Control": "no-store"})
