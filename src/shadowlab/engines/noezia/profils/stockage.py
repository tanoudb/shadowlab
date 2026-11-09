"""Persistance des profils navigateur en JSON.

Un profil persisté garde le même canvas_seed et audio_seed entre les sessions,
ce qui évite que le même "navigateur" change d'empreinte à chaque exécution
(détectable par corrélation temporelle).
"""

from __future__ import annotations

import json
from pathlib import Path

from .generateur import ProfilNavigateur, generer_profil

DOSSIER_DEFAUT = Path("configs/profils")


def charger(nom: str, dossier: Path = DOSSIER_DEFAUT) -> ProfilNavigateur | None:
    """Charge un profil depuis son fichier JSON. None s'il n'existe pas."""
    chemin = dossier / f"{nom}.json"
    if not chemin.exists():
        return None
    donnees = json.loads(chemin.read_text(encoding="utf-8"))
    return ProfilNavigateur.de_dict(donnees)


def sauvegarder(profil: ProfilNavigateur, dossier: Path = DOSSIER_DEFAUT) -> Path:
    """Persiste le profil en JSON. Retourne le chemin du fichier."""
    dossier.mkdir(parents=True, exist_ok=True)
    chemin = dossier / f"{profil.nom}.json"
    chemin.write_text(json.dumps(profil.en_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    return chemin


def charger_ou_creer(nom: str, dossier: Path = DOSSIER_DEFAUT, **kwargs) -> ProfilNavigateur:
    """Charge un profil existant ou en génère un nouveau et le persiste."""
    existant = charger(nom, dossier)
    if existant is not None:
        return existant
    profil = generer_profil(nom=nom, **kwargs)
    sauvegarder(profil, dossier)
    return profil


def lister(dossier: Path = DOSSIER_DEFAUT) -> list[str]:
    """Liste les noms de profils disponibles."""
    if not dossier.exists():
        return []
    return sorted(p.stem for p in dossier.glob("*.json"))
