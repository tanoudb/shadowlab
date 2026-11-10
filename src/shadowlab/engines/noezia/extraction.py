"""Extraction adaptative : retrouver un élément quand son sélecteur a cassé.

Idée (inspirée de Scrapling) : à la première extraction réussie, on mémorise une *signature* de
l'élément (balise, classes, id, texte, profondeur). La fois d'après, si le sélecteur exact ne
trouve plus rien (le site a changé), on relocalise l'élément par **ressemblance** à la signature.

La logique de similarité est en Python pur (testable sans navigateur) ; seule la capture des
caractéristiques dans la page se fait en JavaScript (CARAC_UN / CARAC_TOUS).
"""

from __future__ import annotations

import json
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

# JS : caractéristiques d'un élément (reçoit `e`).
CARAC_UN = """e => {
  let p = 0, n = e; while (n.parentElement) { p++; n = n.parentElement; }
  return {
    tag: e.tagName.toLowerCase(),
    classes: Array.from(e.classList),
    id: e.id || "",
    texte: (e.textContent || "").trim().slice(0, 200),
    profondeur: p,
  };
}"""

# JS : caractéristiques de tous les éléments d'un tag (reçoit `els`), filtrés sur une identité utile.
CARAC_TOUS = """els => els.map(e => {
  let p = 0, n = e; while (n.parentElement) { p++; n = n.parentElement; }
  return {
    tag: e.tagName.toLowerCase(),
    classes: Array.from(e.classList),
    id: e.id || "",
    texte: (e.textContent || "").trim().slice(0, 200),
    profondeur: p,
  };
}).filter(c => c.texte || c.id || c.classes.length)"""

SEUIL_RELOCALISATION = 0.50  # score minimal — permet la relocalisation même avec classes 100% mutées


def domaine_de(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def _texte_sim(a: str, b: str) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def score(signature: dict[str, Any], candidat: dict[str, Any]) -> float:
    """Score de ressemblance [0, 1] entre une signature et un candidat. La balise doit coïncider."""
    if signature.get("tag") != candidat.get("tag"):
        return 0.0
    s = 0.0
    cs, cc = set(signature.get("classes") or []), set(candidat.get("classes") or [])
    union = cs | cc
    s += 0.35 * (len(cs & cc) / len(union) if union else 1.0)
    sid, cid = signature.get("id") or "", candidat.get("id") or ""
    if sid and sid == cid:
        s += 0.25
    elif not sid and not cid:
        s += 0.10
    s += 0.25 * _texte_sim(signature.get("texte") or "", candidat.get("texte") or "")
    dp = abs(int(signature.get("profondeur", 0)) - int(candidat.get("profondeur", 0)))
    s += 0.15 * max(0.0, 1.0 - dp / 5.0)
    return round(s, 4)


def meilleur_candidat(
    signature: dict[str, Any], candidats: list[dict[str, Any]]
) -> tuple[dict[str, Any] | None, float]:
    """Meilleur candidat et son score (0 si aucun)."""
    meilleur, best = None, 0.0
    for c in candidats:
        sc = score(signature, c)
        if sc > best:
            meilleur, best = c, sc
    return meilleur, best


class Signatures:
    """Mémoire des signatures, par domaine et clé logique. Fichier JSON si `chemin` donné, sinon mémoire seule."""

    def __init__(self, chemin: Path | None = None) -> None:
        self._chemin = chemin
        self._data: dict[str, dict[str, Any]] = {}
        if chemin is not None:
            try:
                self._data = json.loads(chemin.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                self._data = {}

    @staticmethod
    def _cle(domaine: str, cle: str) -> str:
        return f"{domaine}::{cle}"

    def charger(self, domaine: str, cle: str) -> dict[str, Any] | None:
        return self._data.get(self._cle(domaine, cle))

    def enregistrer(self, domaine: str, cle: str, signature: dict[str, Any]) -> None:
        self._data[self._cle(domaine, cle)] = signature
        if self._chemin is None:
            return
        try:
            self._chemin.parent.mkdir(parents=True, exist_ok=True)
            self._chemin.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass
