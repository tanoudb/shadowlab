"""Issue d'un passage : ce qui s'est réellement passé, en séparant les six faits que le protocole distingue.

Chaque fait est un drapeau indépendant (une extraction peut réussir tout en étant classée automatisée). L'issue
principale, elle, est unique : elle sert aux totaux et répond à « pourquoi l'extraction a-t-elle échoué ? ».
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .detection import Classement

REUSSIE = "extraction_reussie"
BLOQUE = "bloque"
CHALLENGE_NON_VALIDE = "challenge_non_valide"
ERREUR = "erreur_technique"
ECHEC = "echec_fonctionnel"
INDETERMINE = "indetermine"
ISSUES = (REUSSIE, BLOQUE, CHALLENGE_NON_VALIDE, ERREUR, ECHEC, INDETERMINE)
COUCHES_CHALLENGE = ("captcha", "turnstile", "recaptcha", "defi-js")


@dataclass
class IssuePassage:
    issue: str
    cause: str | None
    drapeaux: dict[str, Any]


def _description_blocage(decision: dict) -> str:
    couche = decision["couche"]
    if couche == "waf":
        regles = [m for m in decision["motifs"] if "id" in m]
        if regles:
            return f"waf : règle {regles[0]['id']} ({regles[0].get('message', '')})"
        return "waf : requête bloquée"
    if couche == "limitation":
        return "limitation : débit dépassé (429)"
    return f"{couche} : bloqué"


def evaluer(
    *,
    success: bool | None,
    erreur: str | None,
    http: list[dict],
    decisions: list[dict],
    classements: list[Classement],
    sous_arena: bool,
    motif_echec: str | None = None,
) -> IssuePassage:
    blocages = [d for d in decisions if d["decision"] == "bloque"]
    emis = {c: sum(1 for d in decisions if d["couche"] == c and d["decision"] == "emis") for c in COUCHES_CHALLENGE}
    valides = {
        c: sum(1 for d in decisions if d["couche"] == c and d["decision"] in ("valide", "captcha_test"))
        for c in COUCHES_CHALLENGE
    }
    panne_arena = any(d["couche"] == "arena" for d in decisions)
    detecte_par = [c.detector_name for c in classements if c.classification == "automatise"]
    drapeaux = {
        "extraction": bool(success),
        "classe_automatise": bool(detecte_par),
        "detecte_par": detecte_par,
        "abstentions": [c.detector_name for c in classements if c.classification == "indetermine"],
        "challenge_declenche": any(emis.values()),
        "challenges_emis": sum(emis.values()),
        "challenge_valide": any(valides.values()),
        "challenge_detail": {c: {"emis": emis[c], "valides": valides[c]} for c in COUCHES_CHALLENGE if emis[c]},
        "bloque": bool(blocages),
        "blocages": len(blocages),
        "erreur_technique": bool(erreur) or panne_arena,
    }
    if motif_echec:
        try:
            drapeaux["details_scenario"] = json.loads(motif_echec) if isinstance(motif_echec, str) else motif_echec
        except (json.JSONDecodeError, TypeError):
            drapeaux["details_scenario"] = motif_echec

    if success:
        return IssuePassage(REUSSIE, None, drapeaux)
    if panne_arena:
        return IssuePassage(ERREUR, "arena : chaîne de protection injoignable", drapeaux)
    if blocages:
        return IssuePassage(BLOQUE, _description_blocage(blocages[0]), drapeaux)
    for couche in COUCHES_CHALLENGE:
        if emis[couche] and not valides[couche]:
            return IssuePassage(CHALLENGE_NON_VALIDE, f"{couche} : émis, jamais validé", drapeaux)
    if erreur:
        return IssuePassage(ERREUR, f"moteur : {erreur[:300]}", drapeaux)
    if sous_arena and not http:
        return IssuePassage(INDETERMINE, "aucune observation reçue : cause inconnue", drapeaux)
    return IssuePassage(ECHEC, f"scénario : {motif_echec or 'résultat attendu non obtenu'}"[:300], drapeaux)
