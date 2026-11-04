"""Ligne de commande `shadowlab`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import campaigns, reports
from . import database as db
from .arena import pile
from .arena.frontal import Frontal
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
    p = sous.add_parser("arena", help="piloter la pile Docker de l'Anti-Bot Arena")
    p.add_argument("action", choices=["demarrer", "appliquer", "arreter", "etat"])
    p.add_argument("--reconstruire", action="store_true", help="reconstruire l'image du WAF")
    p = sous.add_parser("moteurs", help="installer les moteurs isolés et voir ce qui manque")
    p.add_argument("action", choices=["etat", "installer"])
    p.add_argument("noms", nargs="*", help="environnements à installer (tous par défaut)")
    sous.add_parser("liste", help="lister les expériences")
    p = sous.add_parser("supprimer", help="supprimer une expérience et toutes ses observations")
    p.add_argument("id", type=int)
    p = sous.add_parser("diagnostic", help="diagnostic par signal d'une expérience")
    p.add_argument("id", type=int, nargs="?")
    p.add_argument(
        "--rapport",
        choices=["signaux", "ablation", "configurations", "chaine", "par_protection", "tous"],
        default="tous",
    )
    p.add_argument("--generer-ablation", metavar="NIVEAU", help="générer les profils d'ablation pour un niveau")
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
        Frontal(reglages).demarrer()
        print(f"Entrée de l'Arena : {reglages.url_arena}/lab/", flush=True)
        uvicorn.run(creer_app(reglages), host=reglages.hote, port=reglages.port, log_level=niveau)
        return 0

    if args.commande == "arena":
        if args.action == "etat":
            print(pile.etat(reglages))
        elif args.action == "arreter":
            pile.arreter(reglages)
            print("Arena arrêtée.")
        else:  # `appliquer` régénère les configurations et recrée les conteneurs, comme `demarrer`
            pile.demarrer(reglages, reconstruire=args.reconstruire)
            print(f"Arena prête : {pile.etat(reglages)}")
        return 0

    if args.commande == "moteurs":
        from .engines import registre as registre_moteurs
        from .engines.pont import installer

        if args.action == "installer":
            installer(args.noms)
        for nom, classe in sorted(registre_moteurs().items()):
            print(f"{nom:<26} {classe.runtime:<11} {classe.categorie:<15} {classe.manque() or 'prêt'}")
        return 0

    if args.commande == "valider":
        experience = campaigns.lire(args.fichier, reglages)
        total = len(experience.engines) * len(experience.protections) * len(experience.scenarios)
        total *= experience.repetitions
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
    if args.commande == "diagnostic":
        import json

        from . import diagnostic as diag

        if args.generer_ablation:
            niveau = args.generer_ablation
            chemin = f"configs/arena/profils-ablation-{niveau}.yaml"
            codes = diag.ecrire_profils_ablation(chemin, niveau)
            print(f"Profils d'ablation écrits dans {chemin} :")
            for code, nom in codes.items():
                print(f"  {code} — {nom}")
            print(f"\nLancer l'Arena : SHADOWLAB_PROFILS_EXTRA={chemin} uv run shadowlab arena demarrer")
            return 0
        if args.id is None:
            print("Erreur : id requis (sauf avec --generer-ablation)", file=sys.stderr)
            return 2
        rapports = (
            [args.rapport]
            if args.rapport != "tous"
            else ["signaux", "chaine", "configurations", "ablation", "par_protection"]
        )
        for nom in rapports:
            fn = getattr(diag, nom)
            donnees = fn(cx, args.id)
            print(f"\n{'=' * 60}")
            print(f"  {nom.upper()} — expérience {args.id}")
            print(f"{'=' * 60}")
            if nom == "signaux":
                for m in donnees:
                    print(f"\n  {m['moteur']}:")
                    for s in m["signaux"]:
                        print(f"    [{s['detecteur']}] {s['signal']} — {s['description']}")
            elif nom == "chaine":
                moteur_prec = ""
                for d in donnees:
                    if d["moteur"] != moteur_prec:
                        print(f"\n  {d['moteur']}:")
                        moteur_prec = d["moteur"]
                    motifs_txt = (
                        ", ".join(s.get("code", "?") for m in d["motifs"] for s in m.get("signaux", []))
                        if d["motifs"]
                        else ""
                    )
                    print(f"    {d['protection']} → {d['couche_bloquante']:<16} [{d['issue']}] {motifs_txt}")
            elif nom == "configurations":
                for c in donnees:
                    print(f"\n  {c['moteur']}:")
                    print(f"    UA: {c['user_agent'][:80]}")
                    print(f"    Accept-Language: {c['accept_language'] or '(absent)'}")
                    sf = "oui" if c["sec_fetch"] else "non"
                    ch = "oui" if c["sec_ch_ua"] else "non"
                    print(f"    Sec-Fetch: {sf}  Sec-CH-UA: {ch}")
                    print(f"    HTTP: {c['http_version']}  JA4: {c['ja4'] or '?'}  En-têtes: {c['nb_entetes']}")
                    print(f"    Ordre: {' → '.join(c['ordre_entetes'])}")
            elif nom == "ablation":
                for a in donnees:
                    pct = a["echappes"] / a["total"] * 100 if a["total"] else 0
                    print(f"\n  Sans « {a['regle_exclue']} » : {a['echappes']}/{a['total']} échappés ({pct:.0f}%)")
                    if a["moteurs_echappes"]:
                        print(f"    Moteurs échappés : {', '.join(a['moteurs_echappes'])}")
            elif nom == "par_protection":
                moteur_prec = ""
                for p in donnees:
                    if p["moteur"] != moteur_prec:
                        print(f"\n  {p['moteur']}:")
                        moteur_prec = p["moteur"]
                    excl = f" ({p['erreurs_exclues']} err. exclues)" if p["erreurs_exclues"] else ""
                    print(
                        f"    {p['protection']} : {p['taux_detection']}% bloqué ({p['bloques']}/{p['valides']}){excl}"
                    )
                    for c in p["couches"]:
                        sigs = ", ".join(c["signaux"][:5]) if c["signaux"] else ""
                        print(f"      {c['couche']:<16} bloque={c['bloque']} emis={c['emis']}  {sigs}")
            else:
                print(json.dumps(donnees, ensure_ascii=False, indent=2))
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
