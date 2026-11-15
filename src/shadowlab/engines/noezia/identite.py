"""Identité persistante du moteur : un dossier par visiteur (profil Chrome, état, journal des visites, verrou).

Disposition (I4, `docs/recherche/identite-qui-dure-2026-11-12.md` § 5.2) :

    <racine>/<nom>/identite.json   nom, date de création, état (ok, alerte, banni)
                   chrome/         dossier de profil de Chrome (cookies, stockage, cache)
                   visites.jsonl   une ligne par visite
                   verrou          un seul processus à la fois sur une identité

La racine est `outputs/identites` (ignoré par git), ou `SHADOWLAB_IDENTITES` (tests). Ce n'est jamais une
option de campagne : une option ne doit pas pouvoir pointer vers le profil d'une personne.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ...config import RACINE

NOM_VALIDE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
ETATS = ("ok", "alerte", "banni")


class IdentiteRefusee(RuntimeError):
    """L'identité ne peut pas servir maintenant (bannie, ou déjà prise par un autre lancement)."""


def verifier_nom(nom: str) -> str:
    if not isinstance(nom, str) or not NOM_VALIDE.fullmatch(nom):
        raise ValueError(
            f"nom d'identité invalide : {nom!r} (minuscules, chiffres et tirets, 40 caractères au plus, "
            "commence par une lettre ou un chiffre)"
        )
    return nom


def racine_identites() -> Path:
    valeur = os.environ.get("SHADOWLAB_IDENTITES")
    return Path(valeur) if valeur else RACINE / "outputs" / "identites"


def _maintenant() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def age_jours(nom: str) -> int:
    """Âge en jours de l'identité ; 0 si elle n'existe pas encore."""
    fichier = racine_identites() / verifier_nom(nom) / "identite.json"
    try:
        creee = datetime.fromisoformat(json.loads(fichier.read_text(encoding="utf-8"))["creee_le"])
    except (OSError, ValueError, KeyError):
        return 0
    return max(0, (datetime.now(UTC) - creee).days)


class Identite:
    """Une identité ouverte : verrou pris, état vérifié. `liberer()` rend le verrou."""

    def __init__(self, nom: str, dossier: Path, verrou) -> None:
        self.nom = nom
        self.dossier = dossier
        self._verrou = verrou
        self._visite: dict[str, Any] | None = None

    @property
    def dossier_profil(self) -> Path:
        return self.dossier / "chrome"

    @property
    def fichier(self) -> Path:
        return self.dossier / "identite.json"

    def etat(self) -> dict[str, Any]:
        return json.loads(self.fichier.read_text(encoding="utf-8"))

    def debut_visite(self, details: dict[str, Any] | None = None) -> None:
        self._visite = {"debut": _maintenant(), **(details or {})}

    def fin_visite(self, pages: int, statut: str = "ok") -> None:
        if self._visite is None:
            return
        ligne = {**self._visite, "fin": _maintenant(), "pages": pages, "statut": statut}
        self._visite = None
        with (self.dossier / "visites.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(ligne, ensure_ascii=False) + "\n")

    def liberer(self) -> None:
        if self._verrou is not None:
            try:
                fcntl.flock(self._verrou, fcntl.LOCK_UN)
            finally:
                self._verrou.close()
                self._verrou = None


def ouvrir(nom: str) -> Identite:
    """Ouvre (ou crée) l'identité : refuse si elle est bannie ou déjà utilisée par un autre lancement."""
    verifier_nom(nom)
    dossier = racine_identites() / nom
    dossier.mkdir(parents=True, exist_ok=True, mode=0o700)
    dossier.chmod(0o700)
    verrou = (dossier / "verrou").open("a+")
    try:
        fcntl.flock(verrou, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        verrou.close()
        raise IdentiteRefusee(f"identité {nom!r} déjà utilisée par un autre lancement (verrou pris)") from None
    try:
        fichier = dossier / "identite.json"
        if fichier.exists():
            etat = json.loads(fichier.read_text(encoding="utf-8")).get("etat", "ok")
            if etat == "banni":
                raise IdentiteRefusee(f"identité {nom!r} bannie : elle ne sert plus jamais")
        else:
            fichier.write_text(
                json.dumps({"nom": nom, "creee_le": _maintenant(), "etat": "ok"}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        (dossier / "chrome").mkdir(exist_ok=True, mode=0o700)
    except BaseException:
        fcntl.flock(verrou, fcntl.LOCK_UN)
        verrou.close()
        raise
    return Identite(nom, dossier, verrou)
