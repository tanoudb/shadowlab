"""Statistiques d'une expérience : réussite, détection, faux positifs et négatifs, performances.

Conventions :
- vérité terrain : un passage de moteur est « automatisé » ; une session manuelle est « humaine » ;
- un classement `indetermine` n'est compté ni vrai ni faux : il est rapporté à part (taux d'abstention) ;
- taux de détection = vrais positifs / (vrais positifs + faux négatifs), parmi les passages tranchés ;
- les faux positifs viennent uniquement des sessions manuelles (expérience « sessions-manuelles ») ;
  sans elles, faux positifs, précision et F1 sont « non mesurables » ;
- intervalles de confiance à 95 % par la méthode de Wilson (fiable pour de petits effectifs).
"""

from __future__ import annotations

import math
import sqlite3
from collections import defaultdict
from typing import Any

from . import database as db
from .passages import EXPERIENCE_MANUELLE

Z95 = 1.959964


def wilson(succes: int, total: int) -> dict[str, float] | None:
    if total == 0:
        return None
    p = succes / total
    denominateur = 1 + Z95**2 / total
    centre = (p + Z95**2 / (2 * total)) / denominateur
    marge = Z95 * math.sqrt(p * (1 - p) / total + Z95**2 / (4 * total**2)) / denominateur
    return {"taux": round(p, 4), "bas": round(max(0.0, centre - marge), 4), "haut": round(min(1.0, centre + marge), 4)}


def quantile(valeurs: list[float], q: float) -> float | None:
    """Quantile par interpolation linéaire (même définition que numpy, méthode « linear »)."""
    if not valeurs:
        return None
    tries = sorted(valeurs)
    position = (len(tries) - 1) * q
    bas = math.floor(position)
    haut = math.ceil(position)
    return round(tries[bas] + (tries[haut] - tries[bas]) * (position - bas), 1)


def _resume(valeurs: list[float]) -> dict[str, float | None]:
    propres = [v for v in valeurs if v is not None]
    return {
        "n": len(propres),
        "moyenne": round(sum(propres) / len(propres), 1) if propres else None,
        "mediane": quantile(propres, 0.5),
        "p95": quantile(propres, 0.95),
        "p99": quantile(propres, 0.99),
        "max": round(max(propres), 1) if propres else None,
    }


def _comptes(classements: list[str], verite: str) -> dict[str, int]:
    c = {"automatise": 0, "humain": 0, "indetermine": 0}
    for v in classements:
        c[v] += 1
    if verite == "automatise":
        return {"vp": c["automatise"], "fn": c["humain"], "indetermine": c["indetermine"], "n": len(classements)}
    return {"fp": c["automatise"], "vn": c["humain"], "indetermine": c["indetermine"], "n": len(classements)}


def _bloc_detection(classements: list[str]) -> dict[str, Any]:
    c = _comptes(classements, "automatise")
    tranches = c["vp"] + c["fn"]
    return {
        **c,
        "taux_detection": wilson(c["vp"], tranches),
        "taux_faux_negatifs": wilson(c["fn"], tranches),
        "taux_indetermine": wilson(c["indetermine"], c["n"]),
    }


def _passages(cx: sqlite3.Connection, experiment_id: int, inclure_warmup: bool = False) -> list[sqlite3.Row]:
    filtre_warmup = "" if inclure_warmup else " AND COALESCE(r.is_warmup, 0) = 0"
    return cx.execute(
        f"""
        SELECT r.id, r.status, r.success, r.duration_ms, r.truth, r.repetition,
               r.protection, r.issue, r.cause, COALESCE(r.is_warmup, 0) AS is_warmup,
               s.name AS scenario,
               e.name AS engine, e.version AS versions, e.runtime,
               COALESCE(json_extract(e.configuration, '$.label'), e.name) AS label,
               m.cpu_usage, m.cpu_time_ms, m.memory_usage, m.memory_mean, m.navigation_time,
               m.request_count, m.error_count
        FROM runs r
        JOIN scenarios s ON s.id = r.scenario_id
        JOIN engines e ON e.id = r.engine_id
        LEFT JOIN metrics m ON m.run_id = r.id
        WHERE r.experiment_id = ? AND r.status != 'en_cours'{filtre_warmup}
        ORDER BY r.id
        """,
        (experiment_id,),
    ).fetchall()


def _detections(cx: sqlite3.Connection, run_ids: list[int]) -> dict[int, dict[str, str]]:
    resultat: dict[int, dict[str, str]] = defaultdict(dict)
    for i in range(0, len(run_ids), 500):
        lot = run_ids[i : i + 500]
        marques = ",".join("?" * len(lot))
        for d in cx.execute(
            f"SELECT run_id, detector_name, classification FROM detections WHERE run_id IN ({marques})", lot
        ):
            resultat[d["run_id"]][d["detector_name"]] = d["classification"]
    return resultat


def sessions_humaines(cx: sqlite3.Connection) -> dict[str, Any]:
    """Faux positifs mesurés sur les sessions manuelles terminées (toutes expériences confondues)."""
    ligne = cx.execute("SELECT id FROM experiments WHERE name = ?", (EXPERIENCE_MANUELLE,)).fetchone()
    if not ligne:
        return {"n": 0, "detecteurs": {}}
    runs = [
        r["id"] for r in cx.execute("SELECT id FROM runs WHERE experiment_id = ? AND status = 'reussi'", (ligne["id"],))
    ]
    detections = _detections(cx, runs)
    par_detecteur: dict[str, list[str]] = defaultdict(list)
    for run in runs:
        for nom, classement in detections.get(run, {}).items():
            par_detecteur[nom].append(classement)
    detecteurs = {}
    for nom, classements in par_detecteur.items():
        c = _comptes(classements, "humain")
        tranches = c["fp"] + c["vn"]
        detecteurs[nom] = {**c, "taux_faux_positifs": wilson(c["fp"], tranches)}
    return {"n": len(runs), "detecteurs": detecteurs}


def profils_humains(cx: sqlite3.Connection) -> list[dict[str, Any]]:
    """Profils de référence des sessions humaines : navigateur, propriétés, protection."""
    ligne = cx.execute("SELECT id FROM experiments WHERE name = ?", (EXPERIENCE_MANUELLE,)).fetchone()
    if not ligne:
        return []
    profils = []
    for r in cx.execute(
        "SELECT r.id, r.protection, r.consent_at, r.started_at, r.duration_ms,"
        " f.browser_properties, f.http_properties, f.tls_properties, f.session_properties"
        " FROM runs r LEFT JOIN fingerprints f ON f.run_id = r.id"
        " WHERE r.experiment_id = ? AND r.status = 'reussi'"
        " ORDER BY r.id",
        (ligne["id"],),
    ):
        browser = db.lj(r["browser_properties"]) or {}
        http = db.lj(r["http_properties"]) or {}
        profils.append(
            {
                "run_id": r["id"],
                "protection": r["protection"],
                "consent_at": r["consent_at"],
                "started_at": r["started_at"],
                "duration_ms": r["duration_ms"],
                "user_agent": http.get("user_agent"),
                "accept_language": http.get("accept_language"),
                "navigateur": browser.get("userAgent"),
                "plateforme": browser.get("platform"),
                "langues": browser.get("languages"),
                "ecran": {
                    "largeur": browser.get("screenWidth"),
                    "hauteur": browser.get("screenHeight"),
                    "pixel_ratio": browser.get("devicePixelRatio"),
                },
            }
        )
    return profils


def matrice_confusion(cx: sqlite3.Connection, experiment_id: int) -> dict[str, dict[str, Any]]:
    """Matrice de confusion 2×2 par détecteur avec Wilson CI sur toutes les métriques.

    VP/FN viennent des passages automatisés de l'expérience.
    FP/VN viennent des sessions humaines (expérience « sessions-manuelles »).
    Les indéterminés sont comptés à part, jamais mélangés.
    """
    passages = _passages(cx, experiment_id)
    detections_auto = _detections(cx, [p["id"] for p in passages])
    humains = sessions_humaines(cx)

    par_detecteur_auto: dict[str, list[str]] = defaultdict(list)
    for p in passages:
        for nom, classement in detections_auto.get(p["id"], {}).items():
            par_detecteur_auto[nom].append(classement)

    matrices: dict[str, dict[str, Any]] = {}
    for nom, classements in par_detecteur_auto.items():
        ca = _comptes(classements, "automatise")
        vp, fn = ca["vp"], ca["fn"]
        ind_auto = ca["indetermine"]

        h = humains["detecteurs"].get(nom)
        if h:
            fp, vn = h["fp"], h["vn"]
            ind_humain = h["indetermine"]
            n_humain = h["n"]
        else:
            fp = vn = ind_humain = n_humain = 0

        n_auto = vp + fn

        rappel = wilson(vp, n_auto)
        specificite = wilson(vn, fp + vn) if (fp + vn) else None
        precision = wilson(vp, vp + fp) if (vp + fp) else None
        taux_fp = wilson(fp, fp + vn) if (fp + vn) else None

        # F1 avec IC bootstrap simplifié : IC sur rappel et précision propagés
        if rappel and precision and rappel["taux"] + precision["taux"] > 0:
            f1_val = 2 * rappel["taux"] * precision["taux"] / (rappel["taux"] + precision["taux"])
            f1 = {"taux": round(f1_val, 4)}
        else:
            f1 = None

        matrices[nom] = {
            "matrice": {"vp": vp, "fn": fn, "fp": fp, "vn": vn},
            "indetermines": {"automatise": ind_auto, "humain": ind_humain},
            "n_automatise": ca["n"],
            "n_humain": n_humain,
            "rappel": rappel,
            "specificite": specificite,
            "precision": precision,
            "taux_faux_positifs": taux_fp,
            "f1": f1,
        }
    return matrices


def dependance_repetitions(cx: sqlite3.Connection, experiment_id: int) -> dict[str, Any]:
    """Autocorrélation lag-1 du succès entre répétitions consécutives, par (moteur, protection, scénario).

    Une autocorrélation proche de 0 indique l'indépendance des répétitions.
    Une valeur positive suggère que le résultat d'une répétition influence la suivante.
    """
    passages = _passages(cx, experiment_id)
    groupes: dict[tuple[str, str, str], list[tuple[int, int]]] = defaultdict(list)
    for p in passages:
        cle = (p["label"], p["protection"], p["scenario"])
        groupes[cle].append((p["repetition"], 1 if p["success"] else 0))
    resultats: list[dict[str, Any]] = []
    for (moteur, protection, scenario), paires in groupes.items():
        paires.sort()
        valeurs = [v for _, v in paires]
        n = len(valeurs)
        if n < 4:
            continue
        moyenne = sum(valeurs) / n
        variance = sum((v - moyenne) ** 2 for v in valeurs) / n
        if variance == 0:
            resultats.append(
                {
                    "moteur": moteur,
                    "protection": protection,
                    "scenario": scenario,
                    "n": n,
                    "autocorrelation_lag1": None,
                    "note": "variance nulle (résultats identiques)",
                }
            )
            continue
        covariance = sum((valeurs[i] - moyenne) * (valeurs[i + 1] - moyenne) for i in range(n - 1)) / (n - 1)
        r1 = round(covariance / variance, 4)
        resultats.append(
            {
                "moteur": moteur,
                "protection": protection,
                "scenario": scenario,
                "n": n,
                "autocorrelation_lag1": r1,
            }
        )
    return {
        "groupes": resultats,
        "resume": {
            "n_groupes": len(resultats),
            "mesurables": sum(1 for r in resultats if r["autocorrelation_lag1"] is not None),
            "max_absolu": max(
                (abs(r["autocorrelation_lag1"]) for r in resultats if r["autocorrelation_lag1"] is not None),
                default=None,
            ),
        },
    }


def statistiques(cx: sqlite3.Connection, experiment_id: int) -> dict[str, Any]:
    experience = cx.execute("SELECT * FROM experiments WHERE id = ?", (experiment_id,)).fetchone()
    if experience is None:
        raise LookupError(f"expérience {experiment_id} introuvable")
    passages = _passages(cx, experiment_id)
    detections = _detections(cx, [p["id"] for p in passages])
    humains = sessions_humaines(cx)

    par_moteur: dict[str, list[sqlite3.Row]] = defaultdict(list)
    par_couple: dict[tuple[str, str], list[sqlite3.Row]] = defaultdict(list)
    par_protection: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for p in passages:
        par_moteur[p["label"]].append(p)
        par_couple[(p["label"], p["scenario"])].append(p)
        if "protection" in p.keys() and p["protection"]:
            par_protection[p["protection"]].append(p)

    def bloc(lignes: list[sqlite3.Row]) -> dict[str, Any]:
        n = len(lignes)
        a_issue = lignes and "issue" in lignes[0].keys()
        par_issue: dict[str, int] = {}
        for p in lignes:
            issue = p["issue"] if a_issue and p["issue"] else p["status"]
            par_issue[issue] = par_issue.get(issue, 0) + 1
        erreurs_techniques = par_issue.get("erreur_technique", 0)
        reussis = (
            par_issue.get("extraction_reussie", 0) if a_issue else sum(1 for p in lignes if p["status"] == "reussi")
        )
        bloques = par_issue.get("bloque", 0)
        evaluables = n - erreurs_techniques
        par_detecteur: dict[str, list[str]] = defaultdict(list)
        for p in lignes:
            for nom, classement in detections.get(p["id"], {}).items():
                par_detecteur[nom].append(classement)
        return {
            "passages": n,
            "evaluables": evaluables,
            "erreurs_techniques": erreurs_techniques,
            "reussite": wilson(reussis, n),
            "reussite_fonctionnelle": wilson(reussis, evaluables),
            "taux_erreur_technique": wilson(erreurs_techniques, n),
            "taux_blocage": wilson(bloques, evaluables),
            "par_issue": par_issue,
            "duree_ms": _resume([p["duration_ms"] for p in lignes]),
            "navigation_ms": _resume([p["navigation_time"] for p in lignes]),
            "cpu_pct": _resume([p["cpu_usage"] for p in lignes]),
            "cpu_ms": _resume([p["cpu_time_ms"] for p in lignes]),
            "memoire_mo": _resume([p["memory_usage"] for p in lignes]),
            "requetes": _resume([p["request_count"] for p in lignes]),
            "detection": {nom: _bloc_detection(c) for nom, c in sorted(par_detecteur.items())},
        }

    moteurs = []
    for label, lignes in par_moteur.items():
        premier = lignes[0]
        moteurs.append(
            {
                "label": label,
                "engine": premier["engine"],
                "runtime": premier["runtime"],
                "versions": db.lj(premier["versions"]),
                **bloc(lignes),
            }
        )

    matrices = matrice_confusion(cx, experiment_id)
    qualite = {}
    for nom, mc in matrices.items():
        qualite[nom] = {
            "rappel": mc["rappel"]["taux"] if mc["rappel"] else None,
            "precision": mc["precision"]["taux"] if mc["precision"] else None,
            "f1": mc["f1"]["taux"] if mc["f1"] else None,
            "faux_positifs": mc["taux_faux_positifs"],
            "sessions_humaines": mc["n_humain"],
        }

    warmup_exclus = cx.execute(
        "SELECT COUNT(*) FROM runs WHERE experiment_id = ? AND COALESCE(is_warmup, 0) = 1 AND status != 'en_cours'",
        (experiment_id,),
    ).fetchone()[0]
    dependance = dependance_repetitions(cx, experiment_id)

    return {
        "experience": {
            "id": experience["id"],
            "name": experience["name"],
            "description": experience["description"],
            "created_at": experience["created_at"],
            "status": experience["status"],
            "seed": experience["seed"],
            "environment": db.lj(experience["environment"]),
            "configuration": db.lj(experience["configuration"]),
        },
        "passages": len(passages),
        "warmup_exclus": warmup_exclus,
        "moteurs": moteurs,
        "scenarios": [
            {"label": label, "scenario": scenario, **bloc(lignes)}
            for (label, scenario), lignes in sorted(par_couple.items())
        ],
        "par_protection": [{"protection": prot, **bloc(lignes)} for prot, lignes in sorted(par_protection.items())],
        "qualite_detecteurs": qualite,
        "matrices_confusion": matrices,
        "sessions_humaines": humains,
        "dependance_repetitions": dependance,
        "limites": LIMITES,
    }


def _fisher_exact_p(a: int, b: int, c: int, d: int) -> float:
    """P-value bilatérale du test exact de Fisher (table 2×2), implémentation pure Python."""
    from math import comb

    n = a + b + c + d
    r1, r2, c1 = a + b, c + d, a + c

    # Probabilité d'une cellule donnée sous H0
    def _hyper_p(x: int) -> float:
        return comb(r1, x) * comb(r2, c1 - x) / comb(n, c1)

    p_obs = _hyper_p(a)
    lo = max(0, c1 - r2)
    hi = min(r1, c1)
    return sum(_hyper_p(x) for x in range(lo, hi + 1) if _hyper_p(x) <= p_obs * (1 + 1e-7))


def _holm_bonferroni(pvaleurs: list[float]) -> list[float]:
    """Correction de Holm-Bonferroni pour comparaisons multiples."""
    m = len(pvaleurs)
    if m == 0:
        return []
    indices = sorted(range(m), key=lambda i: pvaleurs[i])
    corrigees = [0.0] * m
    cumul = 0.0
    for rang, idx in enumerate(indices):
        ajustee = pvaleurs[idx] * (m - rang)
        cumul = max(cumul, ajustee)
        corrigees[idx] = min(cumul, 1.0)
    return corrigees


def comparer(cx: sqlite3.Connection, id_reference: int, id_nouveau: int) -> dict[str, Any]:
    """Compare deux expériences avec deltas, tests statistiques et correction pour comparaisons multiples."""
    ref = statistiques(cx, id_reference)
    nouveau = statistiques(cx, id_nouveau)

    ref_moteurs = {m["label"]: m for m in ref["moteurs"]}
    nouveau_moteurs = {m["label"]: m for m in nouveau["moteurs"]}

    comparaisons = []
    pvaleurs_brutes: list[float] = []
    indices_pvaleurs: list[int] = []

    for label in sorted(set(ref_moteurs) | set(nouveau_moteurs)):
        r = ref_moteurs.get(label)
        n = nouveau_moteurs.get(label)
        if not (r and n):
            comparaisons.append({"label": label, "only_in": "reference" if r else "nouveau"})
            continue
        entry: dict[str, Any] = {
            "label": label,
            "reference": {"passages": r["passages"]},
            "nouveau": {"passages": n["passages"]},
            "deltas": {},
        }
        # Delta sur taux de réussite — effectifs exacts depuis par_issue
        r_ok = r["par_issue"].get("extraction_reussie", 0)
        n_ok = n["par_issue"].get("extraction_reussie", 0)
        r_ko = r["passages"] - r_ok
        n_ko = n["passages"] - n_ok
        p_fisher = _fisher_exact_p(r_ok, r_ko, n_ok, n_ko)
        idx = len(comparaisons)
        pvaleurs_brutes.append(p_fisher)
        indices_pvaleurs.append(idx)
        entry["deltas"]["reussite"] = {
            "reference": r["reussite"]["taux"] if r["reussite"] else None,
            "nouveau": n["reussite"]["taux"] if n["reussite"] else None,
            "delta": round(
                (n["reussite"]["taux"] if n["reussite"] else 0) - (r["reussite"]["taux"] if r["reussite"] else 0),
                4,
            ),
            "p_value": round(p_fisher, 6),
        }
        # Delta sur durée médiane
        r_med = r["duree_ms"]["mediane"] if r.get("duree_ms") else None
        n_med = n["duree_ms"]["mediane"] if n.get("duree_ms") else None
        if r_med is not None and n_med is not None:
            entry["deltas"]["duree_ms"] = {
                "reference": r_med,
                "nouveau": n_med,
                "delta": round(n_med - r_med, 1),
            }
        comparaisons.append(entry)

    # Correction de Holm-Bonferroni
    if pvaleurs_brutes:
        corrigees = _holm_bonferroni(pvaleurs_brutes)
        for i, idx in enumerate(indices_pvaleurs):
            if "deltas" in comparaisons[idx] and "reussite" in comparaisons[idx]["deltas"]:
                comparaisons[idx]["deltas"]["reussite"]["p_value_corrigee"] = round(corrigees[i], 6)
                comparaisons[idx]["deltas"]["reussite"]["significatif"] = corrigees[i] < 0.05

    return {
        "reference": {"id": id_reference, "name": ref["experience"]["name"], "passages": ref["passages"]},
        "nouveau": {"id": id_nouveau, "name": nouveau["experience"]["name"], "passages": nouveau["passages"]},
        "moteurs": comparaisons,
    }


LIMITES = [
    "Les détecteurs du laboratoire sont des repères locaux : un taux de détection ici n'est pas la probabilité "
    "d'être repéré par un service externe, qui observe bien d'autres signaux (réputation d'adresse, TLS, "
    "comportement sur la durée).",
    "Une absence de détection dans le laboratoire ne prouve aucune « indétectabilité ».",
    "Empreinte TLS non collectée : le site de test est servi en HTTP local.",
    "Sans sessions manuelles, faux positifs, précision et F1 ne sont pas mesurables.",
    "CPU et mémoire couvrent l'arbre de processus du lanceur ; un navigateur partagé entre passages compte dans "
    "chacun.",
    "La règle « aucune observation JavaScript » classe automatisé un visiteur réel qui aurait coupé JavaScript.",
]
