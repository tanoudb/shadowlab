"""Ligne de commande `shadowlab`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import campaigns, reports
from . import database as db
from .arena import pile
from .arena.frontal import Frontal
from .config import RACINE, charger
from .journal import configurer


def _nettoyer(texte: str) -> str:
    """Retire les caractères de contrôle pour éviter l'injection d'échappement terminal."""
    return "".join(c if c.isprintable() else "?" for c in str(texte))


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
    p.add_argument(
        "--generer-ablation",
        metavar="NIVEAUX",
        help="générer les profils d'ablation (niveaux séparés par virgule, ex: 03,04)",
    )
    p.add_argument(
        "--verifier-profils",
        action="store_true",
        help="vérifier les configs de protection enregistrées pour une expérience",
    )
    sous.add_parser("manuel", help="lister les sessions humaines de référence et leurs profils")
    p = sous.add_parser("comparer", help="comparer deux expériences (Fisher exact + Holm-Bonferroni)")
    p.add_argument("reference", type=int, help="id de l'expérience de référence")
    p.add_argument("nouveau", type=int, help="id de la nouvelle expérience")
    p = sous.add_parser("recolter", help="récupérer une page et extraire des données (HTTP furtif)")
    p.add_argument("url", help="URL à récupérer")
    p.add_argument("selecteur", nargs="?", help="sélecteur CSS pour extraire du texte")
    p.add_argument("--similaires", action="store_true", help="auto-match : trouver tous les éléments similaires")
    p.add_argument("--seuil", type=float, default=0.5, help="seuil de ressemblance pour --similaires (défaut 0.5)")
    p.add_argument("--json", dest="format_json", action="store_true", help="sortie JSON")
    p.add_argument(
        "--insecure", action="store_true", help="désactiver la vérification TLS (cert auto-signé, ex. Arena locale)"
    )
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
        print(f"Laboratoire : {reglages.url_site}/labo   Site de test : {reglages.url_site}/lab/", flush=True)
        if not (RACINE / "frontend" / "dist").is_dir():
            print(
                "  (interface non construite : `npm --prefix frontend install && npm --prefix frontend run build`,"
                " ou `npm --prefix frontend run dev` pour le mode développement)",
                flush=True,
            )
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

    if args.commande == "recolter":
        import json as json_mod

        from .engines.noezia.rapide import recuperer

        try:
            analyseur = recuperer(args.url, verifier_tls=not args.insecure)
        except Exception as exc:  # noqa: BLE001
            print(f"Erreur : {exc}", file=sys.stderr)
            return 1
        if args.selecteur and args.similaires:
            elements = analyseur.similaires(args.selecteur, seuil=args.seuil)
            if args.format_json:
                print(json_mod.dumps([{"texte": e.texte} for e in elements], ensure_ascii=False, indent=2))
            else:
                print(f"{len(elements)} éléments similaires à « {args.selecteur} » :\n")
                for i, e in enumerate(elements, 1):
                    print(f"  {i}. {_nettoyer(e.texte[:120])}")
        elif args.selecteur:
            textes = analyseur.css(args.selecteur)
            if args.format_json:
                print(json_mod.dumps(textes, ensure_ascii=False, indent=2))
            else:
                print(f"{len(textes)} résultat(s) pour « {args.selecteur} » :\n")
                for t in textes:
                    print(f"  {_nettoyer(t[:200])}")
        else:
            texte = analyseur.tout_le_texte()
            if args.format_json:
                print(json_mod.dumps({"texte": texte[:5000]}, ensure_ascii=False, indent=2))
            else:
                print(_nettoyer(texte[:3000]))
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
            experiment_id = campaigns.creer(cx, experience, reglages)
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
            niveaux = [n.strip() for n in args.generer_ablation.split(",") if n.strip()]
            suffixe = "-".join(niveaux)
            chemin = f"configs/arena/profils-ablation-{suffixe}.yaml"
            codes = diag.ecrire_profils_ablation(chemin, niveaux)
            print(f"Profils d'ablation écrits dans {chemin} :")
            for code, nom in codes.items():
                print(f"  {code} — {nom}")
            print(f"\nLancer l'Arena : SHADOWLAB_PROFILS_EXTRA={chemin} uv run shadowlab arena demarrer")
            return 0
        if args.verifier_profils:
            if args.id is None:
                print("Erreur : id requis avec --verifier-profils", file=sys.stderr)
                return 2
            resultats = diag.verifier_profils(cx, args.id)
            for r in resultats:
                etat = "OK" if r["ok"] else f"ERREUR : {r['erreur']}"
                print(f"  {r['protection']} : {etat}")
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
    if args.commande == "manuel":
        from . import analytics

        profils = analytics.profils_humains(cx)
        humains = analytics.sessions_humaines(cx)
        print(f"\nSessions humaines de référence : {humains['n']}")
        if profils:
            for p in profils:
                consent = " [consentement]" if p["consent_at"] else ""
                ecran = p["ecran"]
                res = f"{ecran['largeur']}×{ecran['hauteur']}" if ecran.get("largeur") else "?"
                plateforme = _nettoyer(p["plateforme"] or "?")
                navigateur = _nettoyer((p["navigateur"] or "?")[:60])
                print(f"  #{p['run_id']:>4}  {p['protection']}  {res:<12}  {plateforme:<10}  {navigateur}{consent}")
        else:
            print("  Aucune session enregistrée. Ouvrir /manuel dans un navigateur.")
        if humains["detecteurs"]:
            print(f"\n{'Détecteur':<22} {'FP':>4} {'VN':>4} {'Taux FP':>10}")
            print("-" * 44)
            for nom, d in sorted(humains["detecteurs"].items()):
                tfp = f"{d['taux_faux_positifs']['taux'] * 100:.1f}%" if d["taux_faux_positifs"] else "n. m."
                print(f"  {nom:<20} {d['fp']:>4} {d['vn']:>4} {tfp:>10}")
        return 0
    if args.commande == "comparer":
        from . import analytics

        try:
            resultat = analytics.comparer(cx, args.reference, args.nouveau)
        except LookupError as e:
            print(f"Erreur : {e}", file=sys.stderr)
            return 2
        ref = resultat["reference"]
        nouv = resultat["nouveau"]
        print(f"\nRéférence : {ref['name']} (id {ref['id']}, {ref['passages']} passages)")
        print(f"Nouveau   : {nouv['name']} (id {nouv['id']}, {nouv['passages']} passages)")
        if not resultat.get("comparable", True):
            print(f"\nComparaison refusée : {resultat.get('avertissement', 'designs non équivalents')}")
            for cle, d in resultat.get("differences", {}).items():
                print(f"  {cle} : référence={d.get('reference')} ≠ nouveau={d.get('nouveau')}")
            return 2
        print(f"\n{'Moteur':<22} {'Δ réussite':>12} {'p-value':>10} {'p corrigé':>10} {'Sig.':>6} {'Δ durée':>12}")
        print("-" * 76)
        for m in resultat["moteurs"]:
            label = m["label"]
            if m.get("only_in"):
                print(f"{label:<22} seulement dans {m['only_in']}")
                continue
            d_r = m.get("deltas", {}).get("reussite", {})
            d_d = m.get("deltas", {}).get("duree_ms", {})
            delta = f"{d_r.get('delta', 0) * 100:+.1f}%"
            pv = f"{d_r['p_value']:.4f}" if d_r.get("p_value") is not None else "-"
            pc = f"{d_r['p_value_corrigee']:.4f}" if d_r.get("p_value_corrigee") is not None else "-"
            sig = "OUI" if d_r.get("significatif") else "non"
            duree = f"{d_d['delta']:+.0f}ms" if d_d.get("delta") is not None else "-"
            print(f"{label:<22} {delta:>12} {pv:>10} {pc:>10} {sig:>6} {duree:>12}")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
