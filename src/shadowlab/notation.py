"""Notation d'une récolte contre la vérité du site vitrine : complétude et exactitude.

- complétude = annonces attendues retrouvées (par référence) / annonces attendues ;
- exactitude = champs exacts / champs attendus, sur les annonces retrouvées seulement.
Comparaison stricte, après suppression des espaces de début et de fin ; les nombres se comparent en nombres.
"""

from __future__ import annotations

from typing import Any

MAX_MANQUANTES = 20


def _nombre(valeur: Any) -> float | None:
    if isinstance(valeur, bool):
        return None
    if isinstance(valeur, int | float):
        return float(valeur)
    if isinstance(valeur, str):
        try:
            return float(valeur.strip())
        except ValueError:
            return None
    return None


def _egal(attendu: Any, obtenu: Any) -> bool:
    if obtenu is None:
        return False
    if isinstance(attendu, int | float) and not isinstance(attendu, bool):
        n = _nombre(obtenu)
        return n is not None and n == attendu
    if isinstance(attendu, str):
        return isinstance(obtenu, str) and obtenu.strip() == attendu.strip()
    return obtenu == attendu


def noter_recolte(recolte: list[dict], verite: dict) -> dict[str, Any]:
    """Note une récolte (une annonce par dictionnaire, clé `reference`) contre `vitrine.verite()`."""
    attendues = {a["reference"]: a for a in verite["annonces"]}
    retrouvees: dict[str, dict] = {}
    en_trop: set[str] = set()
    for i, annonce in enumerate(recolte):
        reference = annonce.get("reference")
        reference = reference.strip() if isinstance(reference, str) else None
        if reference in attendues:
            retrouvees.setdefault(reference, annonce)  # un doublon ne compte qu'une fois
        else:
            en_trop.add(reference if reference else f"#{i}")
    champs_attendus = 0
    champs_exacts = 0
    erreurs: dict[str, int] = {}
    for reference, annonce in retrouvees.items():
        for champ, attendu in attendues[reference].items():
            champs_attendus += 1
            if _egal(attendu, annonce.get(champ)):
                champs_exacts += 1
            else:
                erreurs[champ] = erreurs.get(champ, 0) + 1
    manquantes = [r for r in attendues if r not in retrouvees]
    return {
        "completude": len(retrouvees) / len(attendues) if attendues else 0.0,
        "exactitude": champs_exacts / champs_attendus if champs_attendus else None,
        "annonces_attendues": len(attendues),
        "annonces_retrouvees": len(retrouvees),
        "champs_attendus": champs_attendus,
        "champs_exacts": champs_exacts,
        "references_manquantes": manquantes[:MAX_MANQUANTES],
        "annonces_en_trop": len(en_trop),
        "erreurs_par_champ": dict(sorted(erreurs.items())),
    }
