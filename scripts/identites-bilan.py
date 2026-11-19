"""Bilan d'une campagne de récolte partagée entre identités (étape 4.2, D-106), lu dans les bases, en lecture seule.

    SHADOWLAB_VITRINE_TAILLE=<taille de l'essai> uv run python scripts/identites-bilan.py <n° de campagne>
        [--recolte vitrine-partagee] [--protection endurance] [--json]

Ce qu'il lit : la base du labo (`runs`, `visites`, `bannissements`, `observations_http`, `decisions`) et l'état de la
récolte partagée (`<sorties>/campagnes/<n°>/recolte/<récolte>-<protection>/etat.sqlite3`). Ce qu'il dit, par critère :
pages de la vitrine toutes lues, champs exacts, pages par identité, ce qu'une identité bannie a demandé après le
bannissement (documents et ressources, puis après son premier refus), rythme par visiteur (pages comptées par heure,
D-78) et sessions par heure de l'empreinte E. Code de sortie : 0 tout tenu, 1 sinon, 2 campagne ou récolte introuvable.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

from shadowlab import notation
from shadowlab.arena.bannissements import clause_pages
from shadowlab.config import charger
from shadowlab.engines.noezia.etat import Etat
from shadowlab.site import vitrine

PAGES_PAR_HEURE_MAX = 240  # bannissement par débit de l'Arena (D-92)
SESSIONS_PAR_HEURE_E = 30  # règle `debit_empreinte` (D-89)


def _lecture(chemin: Path) -> sqlite3.Connection:
    cx = sqlite3.connect(f"file:{chemin}?mode=ro", uri=True)
    cx.row_factory = sqlite3.Row
    return cx


def _date(texte: str) -> datetime:
    return datetime.fromisoformat(texte)


def _visites(cx: sqlite3.Connection, n: int) -> list[dict]:
    lignes = cx.execute(
        "SELECT json_extract(e.configuration, '$.label') AS bras, r.repetition, r.status, r.success, r.started_at,"
        " r.completed_at, r.session_token, r.drapeaux, v.visiteur FROM runs r JOIN engines e ON e.id = r.engine_id"
        " LEFT JOIN visites v ON v.session_token = r.session_token WHERE r.experiment_id = ? ORDER BY r.id",
        (n,),
    ).fetchall()
    rendues = []
    for r in lignes:
        details = (json.loads(r["drapeaux"] or "{}") or {}).get("details_scenario") or {}
        rendues.append(
            {
                "bras": r["bras"],
                "visite": r["repetition"],
                "statut_passage": r["status"],
                "reussie": bool(r["success"]),
                "debut": r["started_at"],
                "fin": r["completed_at"],
                "jeton": r["session_token"],
                "visiteur": r["visiteur"],
                "statut": details.get("statut"),
                "pages_faites": details.get("pages_faites"),
                "relectures": details.get("relectures"),
                "pages_visite": details.get("pages_visite"),
                "travail_fini": details.get("travail_fini"),
                "rien_a_faire": details.get("rien_a_faire"),
                "identite": (details.get("identite") or {}).get("etat"),
                "refus": details.get("refus"),
            }
        )
    return rendues


def _apres_bannissement(cx: sqlite3.Connection, monde: str) -> list[dict]:
    """Pour chaque visiteur banni dans le monde : ce que ses sessions ont demandé après la ligne de bannissement."""
    pages = clause_pages()
    rendus = []
    for b in cx.execute(
        "SELECT b.visiteur, b.empreinte, b.motif, b.cree_le FROM bannissements b JOIN mondes m ON m.id = b.monde_id"
        " WHERE m.nom = ? ORDER BY b.id",
        (monde,),
    ).fetchall():
        if b["visiteur"] is None:
            rendus.append({"visiteur": None, "empreinte": b["empreinte"], "motif": b["motif"], "cree_le": b["cree_le"]})
            continue
        jetons = [
            r[0]
            for r in cx.execute(
                "SELECT v.session_token FROM visites v JOIN mondes m ON m.id = v.monde_id"
                " WHERE m.nom = ? AND v.visiteur = ?",
                (monde, b["visiteur"]),
            )
        ]
        marques = ",".join("?" * len(jetons)) or "''"
        tout = cx.execute(
            f"SELECT h.received_at, h.path, ({pages}) AS document FROM observations_http h"
            f" WHERE h.session_token IN ({marques}) AND h.received_at > ? ORDER BY h.id",
            (*jetons, b["cree_le"]),
        ).fetchall()
        refus = cx.execute(
            f"SELECT created_at, chemin, couche, decision FROM decisions WHERE session_token IN ({marques})"
            " AND couche = 'bannissement' ORDER BY id",
            tuple(jetons),
        ).fetchall()
        apres_refus = _documents_apres_le_refus(tout, refus[0] if refus else None)
        rendus.append(
            {
                "visiteur": b["visiteur"],
                "motif": b["motif"],
                "cree_le": b["cree_le"],
                "requetes_apres_bannissement": len(tout),
                "documents_apres_bannissement": [r["path"] for r in tout if r["document"]],
                "refus": [dict(r) for r in refus],
                "documents_apres_le_premier_refus": [r["path"] for r in apres_refus],
            }
        )
    return rendus


def _documents_apres_le_refus(requetes: list, refus) -> list:
    """Les documents demandés après le premier refus, sauf le document refusé lui-même : son observation (frontal) et la
    décision du gardien sont écrites à quelques millisecondes l'une de l'autre, dans un ordre qui n'est pas garanti."""
    if refus is None:
        return []
    t_refus = _date(refus["created_at"])
    rendus = []
    for r in requetes:
        if not r["document"] or _date(r["received_at"]) <= t_refus:
            continue
        meme = r["path"].split("?", 1)[0] == refus["chemin"] and abs(_date(r["received_at"]) - t_refus) <= timedelta(
            seconds=2
        )
        if not meme:
            rendus.append(r)
    return rendus


def _rythme(cx: sqlite3.Connection, n: int, monde: str) -> dict:
    """Pages comptées (D-78) par visiteur sur la pire heure glissante, et sessions de la campagne sur la pire heure."""
    pages = clause_pages()
    par_visiteur: dict[str, int] = {}
    for (visiteur,) in cx.execute(
        "SELECT DISTINCT v.visiteur FROM visites v JOIN mondes m ON m.id = v.monde_id WHERE m.nom = ?", (monde,)
    ):
        heures = [
            _date(r[0])
            for r in cx.execute(
                f"SELECT h.received_at FROM observations_http h JOIN visites v ON v.session_token = h.session_token"
                f" JOIN mondes m ON m.id = v.monde_id WHERE m.nom = ? AND v.visiteur = ? AND ({pages}) ORDER BY h.id",
                (monde, visiteur),
            )
        ]
        par_visiteur[visiteur] = max(
            (sum(1 for t in heures if d <= t < d + timedelta(hours=1)) for d in heures), default=0
        )
    debuts = [_date(r[0]) for r in cx.execute("SELECT started_at FROM runs WHERE experiment_id = ?", (n,))]
    sessions = max((sum(1 for t in debuts if d <= t < d + timedelta(hours=1)) for d in debuts), default=0)
    return {"pages_comptees_pire_heure": par_visiteur, "sessions_pire_heure": sessions}


def _recolte(dossier: Path, graine: int, taille: int) -> dict:
    etat = Etat(dossier / "etat.sqlite3")
    try:
        passe = etat.derniere_passe()
        if passe is None:
            return {"passe": None}
        n = passe["numero"]
        evenements = etat.evenements(n)
        attendues = vitrine.pages_attendues(graine, taille)
        return {
            "passe": n,
            "statut": passe["statut"],
            "compteurs": etat.compteurs(n),
            "pages_par_identite": etat.pages_par_identite(n),
            "identites": etat.identites(n),
            "rendues": [e["detail"] | {"quand": e["quand"]} for e in evenements if e["genre"] == "rendue"],
            "orphelines": [e["detail"] | {"quand": e["quand"]} for e in evenements if e["genre"] == "orphelines"],
            "pages": notation.noter_pages(attendues, etat.adresses_couvertes(n)),
            "notation": notation.noter_recolte(etat.enregistrements("annonces"), vitrine.verite(graine, taille)),
        }
    finally:
        etat.fermer()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("campagne", type=int)
    parser.add_argument("--recolte", default="vitrine-partagee")
    parser.add_argument("--protection", default="endurance")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    reglages = charger()
    cx = _lecture(reglages.base_donnees)
    if cx.execute("SELECT 1 FROM experiments WHERE id = ?", (args.campagne,)).fetchone() is None:
        print(f"campagne {args.campagne} introuvable", file=sys.stderr)
        return 2
    dossier = reglages.sorties / "campagnes" / str(args.campagne) / "recolte" / f"{args.recolte}-{args.protection}"
    if not (dossier / "etat.sqlite3").exists():
        print(f"récolte introuvable : {dossier}", file=sys.stderr)
        return 2
    monde = f"c{args.campagne}"
    bilan = {
        "campagne": args.campagne,
        "vitrine": {"graine": reglages.vitrine_graine, "taille": reglages.vitrine_taille},
        "visites": _visites(cx, args.campagne),
        "bannissements": _apres_bannissement(cx, monde),
        "rythme": _rythme(cx, args.campagne, monde),
        "recolte": _recolte(dossier, reglages.vitrine_graine, reglages.vitrine_taille),
    }
    r = bilan["recolte"]
    bannis = [b for b in bilan["bannissements"] if b.get("visiteur")]
    criteres = {
        "toutes_les_pages": r.get("pages", {}).get("completude_pages") == 1.0,
        "champs_exacts": r.get("notation", {}).get("completude") == 1.0
        and r.get("notation", {}).get("exactitude") == 1.0,
        "passe_terminee": r.get("statut") == "terminee",
        "un_bannissement_au_moins": bool(bannis),
        "rien_apres_le_premier_refus": all(not b["documents_apres_le_premier_refus"] for b in bannis),
        "sous_240_pages_par_heure": all(
            v <= PAGES_PAR_HEURE_MAX for v in bilan["rythme"]["pages_comptees_pire_heure"].values()
        ),
        "sous_30_sessions_par_heure": bilan["rythme"]["sessions_pire_heure"] < SESSIONS_PAR_HEURE_E,
    }
    bilan["criteres"] = criteres
    if args.json:
        print(json.dumps(bilan, ensure_ascii=False, indent=2))
    else:
        print(f"== Campagne {args.campagne}, vitrine {bilan['vitrine']}")
        print("== Visites")
        for v in bilan["visites"]:
            print(
                f"  {v['bras']:<8} visite {v['visite']:>2} {v['statut_passage']:<7} réussie={v['reussie']!s:<5}"
                f" statut={v['statut']} pages={v['pages_faites']} relectures={v['relectures']}"
                f" fini={v['travail_fini']} vide={v['rien_a_faire']} identité={v['identite']}"
                f" visiteur={(v['visiteur'] or '')[:12]} {v['debut'][11:19]}→{(v['fin'] or '')[11:19]}"
                + (f" refus={v['refus']}" if v["refus"] else "")
            )
        print("== Bannissements et ce qui a été demandé après")
        for b in bilan["bannissements"]:
            print(f"  {json.dumps(b, ensure_ascii=False)}")
        print(f"== Rythme : {bilan['rythme']}")
        print(f"== Récolte : passe {r.get('passe')} {r.get('statut')}, compteurs {r.get('compteurs')}")
        print(f"   pages par identité : {r.get('pages_par_identite')}")
        print(f"   pages rendues : {r.get('rendues')}")
        print(f"   orphelines : {r.get('orphelines')}")
        pages, note = r.get("pages", {}), r.get("notation", {})
        print(
            f"   pages : {pages.get('pages_lues')}/{pages.get('pages_attendues')} ; annonces :"
            f" {note.get('enregistrements_retrouves')}/{note.get('enregistrements_attendus')} ; champs exacts :"
            f" {note.get('champs_exacts')}/{note.get('champs_attendus')}"
        )
        print("== Critères")
        for nom, tenu in criteres.items():
            print(f"  {'TENU ' if tenu else 'NON  '} {nom}")
    return 0 if all(criteres.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
