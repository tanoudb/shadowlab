"""Ligne de commande `shadowlab`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import campaigns, reports
from . import database as db
from .config import charger
from .journal import configurer


def main(argv: list[str] | None = None) -> int:
    parseur = argparse.ArgumentParser(prog="shadowlab", description="Laboratoire local de moteurs de navigation")
    parseur.add_argument("-v", "--verbeux", action="store_true")
    sous = parseur.add_subparsers(dest="commande", required=True)
    p = sous.add_parser("site", help="démarrer le site de test, l'API et le tableau de bord")
    p.add_argument("--silencieux", action="store_true", help="n'afficher que les erreurs du serveur")
    p = sous.add_parser("valider", help="valider un fichier de campagne")
    p.add_argument("fichier", type=Path)
    p = sous.add_parser("campagne", help="créer et exécuter une campagne")
    p.add_argument("fichier", type=Path)
    p = sous.add_parser("reprendre", help="reprendre une campagne interrompue")
    p.add_argument("id", type=int)
    sous.add_parser("arreter", help="arrêt d'urgence de la campagne en cours (après le passage en cours)")
    p = sous.add_parser("rapport", help="exporter les résultats d'une expérience")
    p.add_argument("id", type=int)
    p.add_argument("--formats", default="json,csv,html")
    sous.add_parser("liste", help="lister les expériences")
    p = sous.add_parser("supprimer", help="supprimer une expérience et toutes ses observations")
    p.add_argument("id", type=int)
    args = parseur.parse_args(argv)

    reglages = charger()
    configurer(reglages.sorties, args.verbeux)

    if args.commande == "site":
        import uvicorn

        from .api import _local
        from .site.app import creer_app

        if not _local(reglages.hote) and not reglages.jeton_api:
            print("Refus : écoute hors local sans SHADOWLAB_JETON.", file=sys.stderr)
            return 2
        print(f"Site de test : {reglages.url_site}/lab/   Tableau de bord : {reglages.url_site}/tableau", flush=True)
        niveau = "error" if args.silencieux else "warning"
        uvicorn.run(creer_app(reglages), host=reglages.hote, port=reglages.port, log_level=niveau)
        return 0

    if args.commande == "valider":
        experience = campaigns.lire(args.fichier, reglages)
        total = len(experience.engines) * len(experience.scenarios) * experience.repetitions
        print(f"Valide : {experience.name} — {total} passages, graine {experience.seed}")
        return 0

    if args.commande == "arreter":
        chemin = campaigns.fichier_arret(reglages)
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.touch()
        print(f"Arrêt demandé ({chemin}).")
        return 0

    cx = db.ouvrir(reglages.base_donnees)
    if args.commande == "liste":
        for r in cx.execute(
            "SELECT e.id, e.name, e.status, e.created_at, COUNT(r.id) n FROM experiments e"
            " LEFT JOIN runs r ON r.experiment_id = e.id GROUP BY e.id ORDER BY e.id"
        ):
            print(f"{r['id']:>4}  {r['name']:<28} {r['status']:<11} {r['n']:>6} passages  {r['created_at'][:19]}")
        return 0
    if args.commande == "supprimer":
        n = reports.supprimer(cx, args.id)
        print(f"Expérience {args.id} supprimée ({n} passages).")
        return 0
    if args.commande in ("campagne", "reprendre"):
        if args.commande == "campagne":
            experience = campaigns.lire(args.fichier, reglages)
            experiment_id = campaigns.creer(cx, experience)
            print(f"Expérience {experiment_id} créée (graine {experience.seed}).")
        else:
            experiment_id = args.id
        cx.close()
        statut = campaigns.executer(reglages, experiment_id)
        cx = db.ouvrir(reglages.base_donnees)
        experience = campaigns.Experience.model_validate_json(
            cx.execute("SELECT configuration FROM experiments WHERE id = ?", (experiment_id,)).fetchone()[0]
        )
        fichiers = reports.exporter(
            cx, experiment_id, reglages.sorties / "rapports" / str(experiment_id), experience.output
        )
        print(f"Campagne {experiment_id} : {statut}.")
        for f in fichiers:
            print(f"  {f}")
        return 0 if statut == "termine" else 1
    if args.commande == "rapport":
        fichiers = reports.exporter(cx, args.id, reglages.sorties / "rapports" / str(args.id), args.formats.split(","))
        for f in fichiers:
            print(f)
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
