#!/usr/bin/env python3
"""Passe nos moteurs devant les pages publiques de test de détecteurs de robots, et garde ce que ces pages affichent.

Les trois pages sont faites pour cet usage (outils de test pour développeurs d'automatisation) :
  - sannysoft  : https://bot.sannysoft.com/                    (tableau de tests réussis ou échoués)
  - creepjs    : https://abrahamjuliot.github.io/creepjs/       (empreinte, « mensonges » détectés, part de robot)
  - rebrowser  : https://bot-detector.rebrowser.net/            (fuites du protocole CDP et de l'automatisation)

Une visite par page et par moteur, une à la fois, avec une pause : trois sites, quelques visites. Aucun défi n'est résolu
(`resoudre_defis: false`), aucun CAPTCHA n'est touché, aucun compte n'est créé ; le cadre principal ne peut aller que sur
l'hôte de la page demandée (`hotes_navigation`) et l'adresse d'arrivée est contrôlée.

Ce script ne juge rien : il garde, pour chaque visite, une capture de la page entière, le texte affiché et ce que le moteur
a rendu. La lecture (qui réussit quoi) se fait sur ces fichiers, voir `docs/recherche/detecteurs-publics-2026-11-17.md`.

    uv run python scripts/detecteurs-publics.py [--pages sannysoft creepjs rebrowser] [--moteurs noezia-natif ...] [--sortie DOSSIER]

Sortie : `outputs/detecteurs-publics/<horodatage>/<moteur>/<page>.png|.txt` et `resultats.json` (ignorés par git).
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from shadowlab.config import RACINE
from shadowlab.engines import registre

PAGES = {
    # nom : (adresse, secondes d'attente après le chargement pour que la page finisse ses mesures)
    "sannysoft": ("https://bot.sannysoft.com/", 6),
    "creepjs": ("https://abrahamjuliot.github.io/creepjs/", 25),
    "rebrowser": ("https://bot-detector.rebrowser.net/", 10),
}

# libellé -> (pilote, options). Les trois premiers sont des vrais navigateurs avec fenêtre pour `noezia` ; les deux
# derniers sont les témoins sans réglage, comme dans les campagnes.
MOTEURS = {
    "noezia-natif": (
        "noezia",
        {"headless": False, "channel": "chrome", "identite_native": True, "resoudre_defis": False},
    ),
    "noezia-reecrit": ("noezia", {"headless": False, "resoudre_defis": False}),
    "patchright": ("patchright", {}),
    "playwright": ("playwright", {}),
}
PAUSE_ENTRE_VISITES_S = 8


def _hote(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def visiter(libelle: str, pilote_nom: str, options: dict, pages: list[str], dossier: Path) -> list[dict]:
    hotes = tuple(_hote(PAGES[p][0]) for p in pages)
    # Périmètre illimité (les pages chargent des fichiers d'autres hôtes) ; seul le cadre principal est borné.
    pilote = registre()[pilote_nom](("*",), options)
    if hasattr(pilote, "hotes_navigation"):
        pilote.hotes_navigation = hotes
    resultats: list[dict] = []
    pilote.open()
    try:
        for page in pages:
            adresse, attente = PAGES[page]
            ligne: dict = {"moteur": libelle, "page": page, "adresse": adresse, "debut": datetime.now(UTC).isoformat()}
            try:
                pilote.start_session()
                navigation = pilote.navigate(adresse)
                ligne.update(
                    statut=navigation.status, adresse_finale=navigation.url, duree_ms=round(navigation.duration_ms)
                )
                if _hote(navigation.url) not in hotes:
                    raise RuntimeError(f"arrivé hors de la liste : {_hote(navigation.url)}")
                time.sleep(attente)  # la page calcule encore (CreepJS surtout)
                base = dossier / libelle / page
                pilote.capture_screenshot(base.with_suffix(".png"))
                texte = "\n".join(pilote.texts("body"))
                base.with_suffix(".txt").write_text(texte, encoding="utf-8")
                ligne.update(
                    texte_octets=len(texte.encode()), capture=str(base.with_suffix(".png").relative_to(RACINE))
                )
            except Exception as exc:  # noqa: BLE001 — un moteur ou une page qui échoue est un résultat
                ligne["erreur"] = f"{type(exc).__name__}: {str(exc)[:300]}"
            finally:
                try:
                    pilote.close_session()
                except Exception:  # noqa: BLE001
                    pass
            ligne["fin"] = datetime.now(UTC).isoformat()
            resultats.append(ligne)
            print(f"[{libelle}] {page} : {ligne.get('statut', 'erreur')} {ligne.get('erreur', '')}", flush=True)
            time.sleep(PAUSE_ENTRE_VISITES_S)
        meta = {"configuration": pilote.configuration(), "versions": pilote.versions()}
    finally:
        pilote.close()
    for ligne in resultats:
        ligne.update(meta)
    return resultats


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--pages", nargs="+", choices=sorted(PAGES), default=sorted(PAGES))
    p.add_argument("--moteurs", nargs="+", choices=sorted(MOTEURS), default=list(MOTEURS))
    p.add_argument("--sortie", type=Path)
    args = p.parse_args()

    dossier = args.sortie or RACINE / "outputs" / "detecteurs-publics" / datetime.now(UTC).strftime("%Y-%m-%d-%H%M%S")
    dossier = dossier.resolve()  # chemin absolu : `relative_to(RACINE)` plus bas échoue sur un chemin relatif
    dossier.mkdir(parents=True, exist_ok=True)
    tout: list[dict] = []
    for libelle in args.moteurs:
        pilote_nom, options = MOTEURS[libelle]
        tout.extend(visiter(libelle, pilote_nom, options, args.pages, dossier))
        (dossier / "resultats.json").write_text(json.dumps(tout, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Résultats : {dossier}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
