"""Export des données d'une récolte : un JSON Lines et un CSV par collection, écrits depuis l'état.

L'état (`etat.sqlite3`) fait foi ; ces fichiers sont réécrits en entier à chaque arrêt de passe (fin, alerte,
Ctrl-C, limite). Ils contiennent tout ce qui est connu (toutes les passes) ; `nouveautes.*` ne contient que ce que la
passe a fait apparaître ou changer. Écriture atomique (fichier temporaire puis renommage) : une coupure ne laisse
jamais un fichier à moitié écrit.

CSV pour Excel en France : UTF-8 avec BOM, séparateur point-virgule, virgule décimale (le format est écrit dans
`resume.json`). Une liste ou un objet est écrit en JSON, un booléen en `true`/`false`, une valeur absente en
cellule vide. Le contenu vient du site visé : une cellule de texte qu'un tableur lirait comme une
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

FORMAT_CSV = {"separateur": ";", "encodage": "utf-8-sig", "decimale": ","}

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
    if isinstance(valeur, float):
        return str(valeur).replace(".", FORMAT_CSV["decimale"])
    if isinstance(valeur, int):
        return str(valeur)
    return json.dumps(valeur, ensure_ascii=False)


def _ecrire_atomique(chemin: Path, ecrire: Any, encodage: str = "utf-8") -> None:
    temporaire = chemin.with_name(chemin.name + ".tmp")
    with temporaire.open("w", encoding=encodage, newline="") as flux:
        ecrire(flux)
    os.replace(temporaire, chemin)


def _ecrire_fichiers(dossier: Path, nom: str, lignes: list[dict[str, Any]], colonnes: list[str]) -> list[str]:
    """Écrit `<nom>.jsonl` et `<nom>.csv` ; `colonnes` donne les premières colonnes du CSV (le reste suit)."""
    colonnes = list(colonnes)
    for ligne in lignes:
        colonnes += [c for c in ligne if c not in colonnes]

    def jsonl(flux: Any) -> None:
        for ligne in lignes:
            flux.write(json.dumps(ligne, ensure_ascii=False) + "\n")

    def tableau(flux: Any) -> None:
        ecrivain = csv.writer(flux, delimiter=FORMAT_CSV["separateur"], lineterminator="\r\n")
        ecrivain.writerow(colonnes)
        for ligne in lignes:
            ecrivain.writerow([_cellule(ligne.get(c)) for c in colonnes])

    _ecrire_atomique(dossier / f"{nom}.jsonl", jsonl)
    _ecrire_atomique(dossier / f"{nom}.csv", tableau, FORMAT_CSV["encodage"])
    return [f"{nom}.jsonl", f"{nom}.csv"]


def ecrire_exports(etat: Etat, dossier: Path, passe: int | None = None) -> list[str]:
    """Écrit `<collection>.jsonl` et `<collection>.csv` pour chaque collection ; rend les noms de fichiers, triés.

    Avec `passe`, écrit aussi `nouveautes.jsonl` et `nouveautes.csv` : ce que cette passe a fait apparaître ou
    changer (`etat.nouveautes`), vides s'il n'y a rien.
    """
    dossier.mkdir(parents=True, exist_ok=True)
    fichiers: list[str] = []
    for collection in etat.collections():
        fichiers += _ecrire_fichiers(dossier, collection, etat.enregistrements(collection), [])
    if passe is not None:
        fichiers += _ecrire_fichiers(dossier, "nouveautes", etat.nouveautes(passe), ["_collection", "_changement"])
    return sorted(fichiers)
