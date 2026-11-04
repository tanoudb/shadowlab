"""Diagnostic par signal, tests d'ablation et comparaison des configurations moteurs.

Cinq rapports extraits de la base après une campagne :
1. `signaux` — valeurs HTTP reçues, règle déclenchée, poids, par moteur.
2. `ablation` — recalcul des verdicts en désactivant chaque règle une par une.
3. `configurations` — en-têtes HTTP et TLS observés côte à côte.
4. `chaine` — premier motif de blocage par moteur et niveau de protection.
5. `par_protection` — taux de détection indépendant de chaque couche, erreurs techniques exclues.
"""

from __future__ import annotations

import copy
import json
import sqlite3
from collections import defaultdict
from typing import Any

from .detection import SEUIL_AUTOMATISE, Observations, registre

# ---------------------------------------------------------------------------
# 1. Diagnostic par signal
# ---------------------------------------------------------------------------


def signaux(cx: sqlite3.Connection, experiment_id: int) -> list[dict[str, Any]]:
    """Pour chaque moteur, liste les signaux de fingerprinting déclenchés et leur détecteur."""
    rows = cx.execute(
        """
        SELECT DISTINCT eng.name, d.motifs
        FROM decisions d
        JOIN runs r ON d.session_token = r.session_token
        JOIN engines eng ON r.engine_id = eng.id
        WHERE r.experiment_id = ? AND d.couche = 'fingerprinting'
          AND d.decision IN ('bloque', 'suspect')
        """,
        (experiment_id,),
    ).fetchall()
    par_moteur: dict[str, list[dict]] = defaultdict(list)
    vus: dict[str, set] = defaultdict(set)
    for eng_name, motifs_str in rows:
        for m in json.loads(motifs_str) if motifs_str else []:
            det = m.get("detecteur", "")
            for s in m.get("signaux", []):
                code = s.get("code", "")
                if code not in vus[eng_name]:
                    vus[eng_name].add(code)
                    par_moteur[eng_name].append(
                        {"detecteur": det, "signal": code, "description": s.get("description", "")}
                    )
    return [{"moteur": m, "signaux": par_moteur[m]} for m in sorted(par_moteur)]


# ---------------------------------------------------------------------------
# 2. Tests d'ablation
# ---------------------------------------------------------------------------


def ablation(cx: sqlite3.Connection, experiment_id: int) -> list[dict[str, Any]]:
    """Pour chaque règle, recalcule combien de moteurs seraient encore détectés sans elle."""
    from . import database as db

    detecteurs = registre()
    regle_noms = list(detecteurs.keys())

    # Collect all sessions from this experiment with their fingerprinting decisions
    sessions = cx.execute(
        """
        SELECT DISTINCT r.session_token, eng.name, r.protection
        FROM runs r
        JOIN engines eng ON r.engine_id = eng.id
        WHERE r.experiment_id = ?
        """,
        (experiment_id,),
    ).fetchall()

    # For each session, recompute detection with each rule removed
    resultats: list[dict[str, Any]] = []
    for regle_exclue in regle_noms:
        autres = [n for n in regle_noms if n != regle_exclue]
        detectes = 0
        echappes = 0
        moteurs_echappes: set[str] = set()
        total = 0
        for token, eng_name, _protection in sessions:
            http, js = db.observations(cx, token)
            tls = db.tls_session(cx, token)
            obs = Observations(http=http, js=js, tls=tls)
            score = 0.0
            for nom in autres:
                classement = detecteurs[nom].classer(obs)
                if classement.classification == "automatise":
                    score += sum(s.poids for s in classement.signals)
            total += 1
            if score >= SEUIL_AUTOMATISE:
                detectes += 1
            else:
                echappes += 1
                moteurs_echappes.add(eng_name)
        resultats.append(
            {
                "regle_exclue": regle_exclue,
                "total": total,
                "detectes": detectes,
                "echappes": echappes,
                "moteurs_echappes": sorted(moteurs_echappes),
            }
        )
    return resultats


# ---------------------------------------------------------------------------
# 3. Comparaison des configurations
# ---------------------------------------------------------------------------


def configurations(cx: sqlite3.Connection, experiment_id: int) -> list[dict[str, Any]]:
    """En-têtes HTTP et TLS observés pour chaque moteur (premier passage, niveau 01)."""
    rows = cx.execute(
        """
        SELECT eng.name, oh.headers, oh.http_version, ot.ja4
        FROM observations_http oh
        JOIN runs r ON oh.session_token = r.session_token
        JOIN engines eng ON r.engine_id = eng.id
        LEFT JOIN observations_tls ot ON oh.tls_id = ot.id
        WHERE r.experiment_id = ? AND r.protection = '01' AND oh.path LIKE '/lab/%'
        GROUP BY eng.name
        ORDER BY eng.name
        """,
        (experiment_id,),
    ).fetchall()
    resultats = []
    for eng_name, headers_str, http_version, ja4 in rows:
        headers = json.loads(headers_str) if headers_str else []
        entetes = {k: v for k, v in headers}
        resultats.append(
            {
                "moteur": eng_name,
                "user_agent": entetes.get("user-agent", entetes.get("User-Agent", "")),
                "accept_language": entetes.get("accept-language", entetes.get("Accept-Language", "")),
                "sec_fetch": any(k.lower().startswith("sec-fetch-") for k, _ in headers),
                "sec_ch_ua": any(k.lower().startswith("sec-ch-ua") for k, _ in headers),
                "http_version": http_version or "",
                "ja4": ja4 or "",
                "nb_entetes": len(headers),
                "ordre_entetes": [k for k, _ in headers[:8]],
            }
        )
    return resultats


# ---------------------------------------------------------------------------
# 4. Chaîne de décisions (premier motif de blocage)
# ---------------------------------------------------------------------------


def chaine(cx: sqlite3.Connection, experiment_id: int) -> list[dict[str, Any]]:
    """Pour chaque moteur et niveau, la première couche qui bloque ou émet un défi non résolu."""
    rows = cx.execute(
        """
        SELECT eng.name, r.protection, r.issue, r.cause,
               d.couche, d.decision, d.motifs, d.created_at
        FROM runs r
        JOIN engines eng ON r.engine_id = eng.id
        JOIN decisions d ON d.session_token = r.session_token
        WHERE r.experiment_id = ?
          AND d.decision IN ('bloque', 'emis')
        ORDER BY eng.name, r.protection, d.created_at
        """,
        (experiment_id,),
    ).fetchall()
    # Group and keep only last blocking decision per (engine, protection)
    par_moteur_prot: dict[tuple[str, str], dict] = {}
    emis_par_session: dict[tuple[str, str], list] = defaultdict(list)
    for eng, prot, issue, _cause, couche, decision, motifs_str, _ts in rows:
        key = (eng, prot)
        motifs = json.loads(motifs_str) if motifs_str else []
        if decision == "bloque" and key not in par_moteur_prot:
            par_moteur_prot[key] = {
                "moteur": eng,
                "protection": prot,
                "issue": issue,
                "couche_bloquante": couche,
                "motifs": motifs,
            }
        elif decision == "emis":
            emis_par_session[key].append({"couche": couche, "motifs": motifs})

    # For non-blocked but failed runs, find what was emitted (challenge not solved)
    runs_failed = cx.execute(
        """
        SELECT eng.name, r.protection, r.issue, r.cause
        FROM runs r
        JOIN engines eng ON r.engine_id = eng.id
        WHERE r.experiment_id = ? AND r.success = 0 AND r.issue != 'extraction_reussie'
        GROUP BY eng.name, r.protection
        """,
        (experiment_id,),
    ).fetchall()
    for eng, prot, issue, cause in runs_failed:
        key = (eng, prot)
        if key not in par_moteur_prot:
            emis = emis_par_session.get(key, [])
            # The last emitted challenge that wasn't solved is the blocker
            dernier = emis[-1] if emis else {}
            par_moteur_prot[key] = {
                "moteur": eng,
                "protection": prot,
                "issue": issue,
                "couche_bloquante": dernier.get("couche", cause or ""),
                "motifs": dernier.get("motifs", []),
            }

    return sorted(par_moteur_prot.values(), key=lambda d: (d["moteur"], d["protection"]))


# ---------------------------------------------------------------------------
# 5. Diagnostic indépendant par protection (niveaux 05-06)
# ---------------------------------------------------------------------------


def par_protection(cx: sqlite3.Connection, experiment_id: int) -> list[dict[str, Any]]:
    """Pour chaque couche de protection, taux de blocage par moteur (erreurs techniques exclues).

    Répond à : « Quelle couche a bloqué tel moteur, avec quels signaux ? »
    Les passages en erreur_technique sont exclus du dénominateur.
    """
    rows = cx.execute(
        """
        SELECT eng.name AS moteur, r.protection, r.issue, r.session_token,
               d.couche, d.decision, d.motifs
        FROM runs r
        JOIN engines eng ON r.engine_id = eng.id
        LEFT JOIN decisions d ON d.session_token = r.session_token
        WHERE r.experiment_id = ?
        ORDER BY eng.name, r.protection
        """,
        (experiment_id,),
    ).fetchall()

    # Structures : par (moteur, protection) → {couche → {bloque, emis, total}}
    par_mp: dict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {"total": 0, "erreurs": 0, "reussi": 0, "couches": defaultdict(lambda: {"bloque": 0, "emis": 0})}
    )
    sessions_vues: dict[tuple[str, str], set] = defaultdict(set)
    signaux_couche: dict[tuple[str, str, str], list] = defaultdict(list)

    for moteur, prot, issue, token, couche, decision, motifs_str in rows:
        key = (moteur, prot)
        if token not in sessions_vues[key]:
            sessions_vues[key].add(token)
            par_mp[key]["total"] += 1
            if issue == "erreur_technique":
                par_mp[key]["erreurs"] += 1
            elif issue == "extraction_reussie":
                par_mp[key]["reussi"] += 1
        if couche and decision in ("bloque", "emis"):
            par_mp[key]["couches"][couche][decision] += 1
            motifs = json.loads(motifs_str) if motifs_str else []
            for m in motifs:
                for s in m.get("signaux", []):
                    signaux_couche[(moteur, prot, couche)].append(s.get("code", ""))

    resultats = []
    for (moteur, prot), stats in sorted(par_mp.items()):
        valides = stats["total"] - stats["erreurs"]
        if valides == 0:
            continue
        bloques = valides - stats["reussi"]
        couches_detail = []
        for couche, compteurs in sorted(stats["couches"].items()):
            sigs = signaux_couche.get((moteur, prot, couche), [])
            sigs_uniques = sorted(set(sigs))
            couches_detail.append(
                {
                    "couche": couche,
                    "bloque": compteurs["bloque"],
                    "emis": compteurs["emis"],
                    "signaux": sigs_uniques,
                }
            )
        resultats.append(
            {
                "moteur": moteur,
                "protection": prot,
                "total": stats["total"],
                "erreurs_exclues": stats["erreurs"],
                "valides": valides,
                "bloques": bloques,
                "reussi": stats["reussi"],
                "taux_detection": round(bloques / valides * 100, 1) if valides else 0,
                "couches": couches_detail,
            }
        )
    return resultats


# ---------------------------------------------------------------------------
# 6. Génération de profils d'ablation pour campagne réelle
# ---------------------------------------------------------------------------

REGLES_FINGERPRINTING = ("regles-http", "tls", "botd", "regles-js", "coherence", "comportement")


def generer_profils_ablation(niveau_base: str = "03") -> dict[str, dict]:
    """Génère un dictionnaire de profils Arena pour campagne d'ablation réelle.

    Pour chaque règle de fingerprinting, crée une variante du niveau de base
    avec cette règle exclue. Inclut aussi le profil de référence (toutes les règles).
    """
    from .arena.profils import charger

    profils = charger()
    base = profils.de(niveau_base)
    if base is None:
        raise ValueError(f"niveau {niveau_base} introuvable")
    base_dict = base.model_dump()
    resultat = {niveau_base: copy.deepcopy(base_dict)}
    for regle in REGLES_FINGERPRINTING:
        code = f"{niveau_base}s{regle.replace('-', '')}"
        variante = copy.deepcopy(base_dict)
        variante["fingerprinting"]["exclure"] = [regle]
        variante["nom"] = f"Ablation : sans {regle}"
        variante["description"] = f"Niveau {niveau_base} sans la règle {regle}"
        resultat[code] = variante
    return resultat


def ecrire_profils_ablation(chemin: str, niveau_base: str = "03") -> dict[str, str]:
    """Écrit les profils d'ablation dans un fichier YAML et renvoie les codes générés."""
    import yaml

    profils = generer_profils_ablation(niveau_base)
    from pathlib import Path

    p = Path(chemin)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(profils, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return {code: prof.get("nom", code) for code, prof in profils.items()}
