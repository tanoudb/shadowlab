"""Export des données d'une récolte : un JSON Lines et un CSV par collection, écrits depuis l'état.

L'état (`etat.sqlite3`) fait foi ; ces fichiers sont réécrits en entier à chaque arrêt de passe (fin, alerte,
Ctrl-C, limite). Ils contiennent tout ce qui est connu (toutes les passes). Écriture atomique (fichier temporaire
puis renommage) : une coupure ne laisse jamais un fichier à moitié écrit.

CSV (RFC 4180, UTF-8, virgule) : une liste ou un objet est écrit en JSON, un booléen en `true`/`false`, une valeur
absente en cellule vide. Le contenu vient du site visé : une cellule de texte qu'un tableur lirait comme une
formule est neutralisée (apostrophe devant). Le JSON Lines garde la valeur exacte.
"""

from __future__ import annotations

import csv
import json
import os
import re
from pathlib import Path
from typing import Any

from .etat import Etat

# `+` ou `-` suivi seulement de chiffres, espaces et ponctuation de nombre ou de téléphone : pas une formule.
_RE_NOMBRE_OU_TELEPHONE = re.compile(r"[+-][\d\s().,-]+")
_DEBUTS_DE_FORMULE = ("=", "@", "\t", "\r", "+", "-")


def neutraliser(texte: str) -> str:
    """Préfixe d'une apostrophe un texte que Excel ou LibreOffice exécuterait comme une formule."""
    if not texte.startswith(_DEBUTS_DE_FORMULE):
        return texte
    if texte[0] in "+-" and _RE_NOMBRE_OU_TELEPHONE.fullmatch(texte):
        return texte
    return "'" + texte


def _cellule(valeur: Any) -> str:
    if valeur is None:
        return ""
    if isinstance(valeur, bool):
        return "true" if valeur else "false"
    if isinstance(valeur, str):
        return neutraliser(valeur)
    if isinstance(valeur, int | float):
        return str(valeur)
    return json.dumps(valeur, ensure_ascii=False)


def _ecrire_atomique(chemin: Path, ecrire: Any) -> None:
    temporaire = chemin.with_name(chemin.name + ".tmp")
    with temporaire.open("w", encoding="utf-8", newline="") as flux:
        ecrire(flux)
    os.replace(temporaire, chemin)


def ecrire_exports(etat: Etat, dossier: Path) -> list[str]:
    """Écrit `<collection>.jsonl` et `<collection>.csv` pour chaque collection ; rend les noms de fichiers, triés."""
    dossier.mkdir(parents=True, exist_ok=True)
    fichiers: list[str] = []
    for collection in etat.collections():
        enregistrements = etat.enregistrements(collection)

        def jsonl(flux: Any, lignes: list[dict[str, Any]] = enregistrements) -> None:
            for ligne in lignes:
                flux.write(json.dumps(ligne, ensure_ascii=False) + "\n")

        colonnes: list[str] = []
        for ligne in enregistrements:
            colonnes += [c for c in ligne if c not in colonnes]

        def tableau(flux: Any, lignes: list[dict[str, Any]] = enregistrements, cols: list[str] = colonnes) -> None:
            ecrivain = csv.writer(flux, lineterminator="\r\n")
            ecrivain.writerow(cols)
            for ligne in lignes:
                ecrivain.writerow([_cellule(ligne.get(c)) for c in cols])

        _ecrire_atomique(dossier / f"{collection}.jsonl", jsonl)
        _ecrire_atomique(dossier / f"{collection}.csv", tableau)
        fichiers += [f"{collection}.jsonl", f"{collection}.csv"]
    return sorted(fichiers)
