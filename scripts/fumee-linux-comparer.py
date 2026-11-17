#!/usr/bin/env python3
"""Compare une campagne Linux (étape 3.1) à une campagne du poste : issues, signaux, propriétés brutes.

Bibliothèque standard seulement, bases ouvertes en lecture seule (`immutable=1`) : tourne sur le Mac sans `uv sync`.

    python3 scripts/fumee-linux-comparer.py \
        --linux outputs/shadowlab.sqlite3 --linux-campagne 3 --linux-label noezia-natif \
        --poste ~/dev/noezia-shadowlab/outputs/shadowlab.sqlite3 --poste-campagne 132 --poste-label noezia-natif \
        --protections 04 05 06scorr [--proprietes]

Trois blocs par niveau :
  1. les issues (passages réussis, bloqués…), de chaque côté ;
  2. les signaux (détecteur, code) vus d'un côté seulement, avec le nombre de passages concernés ; un signal dont
     la version du détecteur diffère entre les deux bases n'est pas imputable à Linux, et le tableau le dit ;
  3. avec --proprietes : les propriétés brutes de l'empreinte (première empreinte de chaque passage) dont les
     valeurs diffèrent, y compris celles qu'aucun détecteur ne relève (architecture, carte graphique, écran…).
Un « passage » est compté une fois par signal, quel que soit le nombre de pages.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

# Propriétés trop changeantes d'un passage à l'autre pour être comparées (durées, graines, hachages, compteurs).
BRUIT = (
    "duree_collecte_ms",
    "timing",
    "raf_timing",
    "paint_timing",
    "timing_precision",
    "hash",
    "canvas",
    "sum",
    "rects",
    "debugger_delta_ms",
    "heap_ratio",
    "jsHeap",
    "usedJSHeapSize",
    "totalJSHeapSize",
    "downlink",
    "rtt",
    "screenX",
    "screenY",
    "stack",
    "error_stack_lines",
    "empty_script_tags",
    "cdp_resource_entries",
    "sonde",
)


def ouvrir(chemin: str) -> sqlite3.Connection:
    cx = sqlite3.connect(f"file:{Path(chemin).expanduser()}?immutable=1", uri=True)
    cx.row_factory = sqlite3.Row
    return cx


def passages(cx: sqlite3.Connection, campagne: int, label: str | None, protection: str) -> list[sqlite3.Row]:
    lignes = cx.execute(
        "SELECT r.id, r.session_token, r.success, r.issue, r.cause, g.configuration FROM runs r"
        " JOIN engines g ON g.id = r.engine_id WHERE r.experiment_id = ? AND r.protection = ? ORDER BY r.id",
        (campagne, protection),
    ).fetchall()
    if label is None:
        return lignes
    return [ligne for ligne in lignes if json.loads(ligne["configuration"]).get("label") == label]


def signaux_du_passage(cx: sqlite3.Connection, passage: sqlite3.Row, versions: dict[str, str]) -> set[tuple[str, str]]:
    """Les (détecteur, code) d'un passage ; `versions` reçoit la version de chaque détecteur qui a tourné."""
    vus: set[tuple[str, str]] = set()
    for d in cx.execute(
        "SELECT detector_name, detector_version, signals FROM detections WHERE run_id = ?", (passage["id"],)
    ):
        versions[d["detector_name"]] = d["detector_version"]
        for s in json.loads(d["signals"]):
            vus.add((d["detector_name"], s.get("code", "?")))
    # Un passage arrêté par le gardien n'a pas fait tourner tous les détecteurs : ses motifs sont dans `decisions`.
    for dec in cx.execute(
        "SELECT motifs FROM decisions WHERE session_token = ?"
        " AND couche IN ('fingerprinting', 'fingerprinting-differe')",
        (passage["session_token"],),
    ):
        try:
            motifs = json.loads(dec["motifs"])
        except ValueError:
            continue
        for m in motifs if isinstance(motifs, list) else []:
            for s in m.get("signaux", []) if isinstance(m, dict) else []:
                vus.add((m.get("detecteur", "?"), s.get("code", "?")))
    return vus


def issues(lignes: list[sqlite3.Row]) -> str:
    comptes = Counter((ligne["issue"] or ligne["cause"] or "?") for ligne in lignes)
    reussis = sum(1 for ligne in lignes if ligne["success"])
    detail = ", ".join(f"{n} {nom}" for nom, n in comptes.most_common())
    return f"{reussis} sur {len(lignes)} ({detail})"


def a_plat(valeur, prefixe: str = "") -> dict[str, str]:
    sortie: dict[str, str] = {}
    if isinstance(valeur, dict):
        for k, v in valeur.items():
            sortie.update(a_plat(v, f"{prefixe}{k}."))
    elif isinstance(valeur, list) and valeur and all(isinstance(x, dict) for x in valeur):
        sortie[prefixe.rstrip(".")] = json.dumps(valeur, ensure_ascii=False, sort_keys=True)[:200]
    else:
        sortie[prefixe.rstrip(".")] = json.dumps(valeur, ensure_ascii=False, sort_keys=True)[:200]
    return sortie


def proprietes(cx: sqlite3.Connection, lignes: list[sqlite3.Row], tout: bool = False) -> dict[str, Counter]:
    valeurs: dict[str, Counter] = defaultdict(Counter)
    for ligne in lignes:
        brut = cx.execute("SELECT browser_properties FROM fingerprints WHERE run_id = ?", (ligne["id"],)).fetchone()
        if brut is None:
            continue
        for cle, valeur in a_plat(json.loads(brut[0])).items():
            if tout or not any(b in cle for b in BRUIT):
                valeurs[cle][valeur] += 1
    return valeurs


def comparer_proprietes(linux: dict[str, Counter], poste: dict[str, Counter]) -> list[str]:
    sortie = []
    for cle in sorted(set(linux) | set(poste)):
        a, b = linux.get(cle, Counter()), poste.get(cle, Counter())
        if set(a) == set(b) or (len(a) > 8 or len(b) > 8):
            continue
        sortie.append(f"| `{cle}` | {dict(a) or '—'} | {dict(b) or '—'} |")
    return sortie


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--linux", required=True)
    p.add_argument("--linux-campagne", type=int, required=True)
    p.add_argument("--linux-label")
    p.add_argument("--poste", required=True)
    p.add_argument("--poste-campagne", type=int, required=True)
    p.add_argument("--poste-label")
    p.add_argument("--protections", nargs="+", required=True)
    p.add_argument("--proprietes", action="store_true", help="comparer aussi les propriétés brutes de l'empreinte")
    p.add_argument(
        "--sonde",
        nargs="+",
        metavar="CHEMIN",
        help="au lieu de comparer : valeurs de ces propriétés (ex. webgl.disponible ecran.width), par niveau",
    )
    args = p.parse_args()

    cx_l, cx_p = ouvrir(args.linux), ouvrir(args.poste)
    print(f"# Linux : base {args.linux}, campagne {args.linux_campagne} ({args.linux_label or 'tous moteurs'})")
    print(f"# Poste : base {args.poste}, campagne {args.poste_campagne} ({args.poste_label or 'tous moteurs'})\n")
    for protection in args.protections:
        lin = passages(cx_l, args.linux_campagne, args.linux_label, protection)
        pos = passages(cx_p, args.poste_campagne, args.poste_label, protection)
        print(f"## Niveau {protection}\n")
        if args.sonde:
            vl, vp = proprietes(cx_l, lin, tout=True), proprietes(cx_p, pos, tout=True)
            print("| Propriété | Linux | Poste |\n|---|---|---|")
            for chemin in args.sonde:
                print(f"| `{chemin}` | {dict(vl.get(chemin, {})) or '—'} | {dict(vp.get(chemin, {})) or '—'} |")
            print()
            continue
        print(f"- Linux : {issues(lin)}")
        print(f"- Poste : {issues(pos)}\n")
        if not lin or not pos:
            print("_Une des deux séries est vide : rien à comparer._\n")
            continue
        comptes_l: Counter = Counter()
        comptes_p: Counter = Counter()
        versions_l: dict[str, str] = {}
        versions_p: dict[str, str] = {}
        for ligne in lin:
            for cle in signaux_du_passage(cx_l, ligne, versions_l):
                comptes_l[cle] += 1
        for ligne in pos:
            for cle in signaux_du_passage(cx_p, ligne, versions_p):
                comptes_p[cle] += 1
        print("| Signal (détecteur, code) | Linux | Poste | Versions (Linux / poste) |")
        print("|---|---|---|---|")
        lignes_signaux = 0
        for cle in sorted(set(comptes_l) | set(comptes_p), key=lambda c: -(comptes_l[c] - comptes_p[c])):
            n_l, n_p = comptes_l[cle], comptes_p[cle]
            # Écart de proportion d'au moins 20 points : on laisse de côté ce qui se ressemble.
            if abs(n_l / len(lin) - n_p / len(pos)) < 0.2:
                continue
            v_l, v_p = versions_l.get(cle[0], "?"), versions_p.get(cle[0], "?")
            drapeau = " ⚠ détecteur de version différente : écart non imputable à Linux" if v_l != v_p else ""
            print(f"| `{cle[0]}` / `{cle[1]}` | {n_l}/{len(lin)} | {n_p}/{len(pos)} | {v_l} / {v_p}{drapeau} |")
            lignes_signaux += 1
        if lignes_signaux == 0:
            print("| _aucun écart d'au moins 20 points_ | | | |")
        print()
        if args.proprietes:
            diff = comparer_proprietes(proprietes(cx_l, lin), proprietes(cx_p, pos))
            print(f"Propriétés brutes différentes ({len(diff)}) :\n")
            print("| Propriété | Linux | Poste |\n|---|---|---|")
            print("\n".join(diff) if diff else "| _aucune_ | | |")
            print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
