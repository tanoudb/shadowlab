"""Ligne de commande `shadowlab`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import campaigns, reports
from . import database as db
from .arena import pile
from .arena.frontal import Frontal
from .config import RACINE, Reglages, charger
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
    p = sous.add_parser(
        "recolte", help="récolte générale d'un site décrit par une recette (docs/recherche/recolte-generale)"
    )
    p.add_argument("action", choices=["lancer", "reprendre", "etat", "essayer", "noter"])
    p.add_argument("cible", help="lancer, essayer : fichier de recette ; reprendre, etat, noter : nom de la récolte")
    p.add_argument("adresse", nargs="?", help="essayer : adresse de la page, ou fichier .html")
    p.add_argument("--moteur", choices=["http", "navigateur"], help="remplace le moteur de la recette")
    p.add_argument(
        "--tranche", action="append", default=[], metavar="NOM=VALEUR", help="valeur d'une variable de la recette"
    )
    p.add_argument(
        "--pages-max",
        type=int,
        help="arrête la passe après N pages lues (échecs compris) ; avec reprendre : N pages de plus, "
        "sans lui : aucune limite",
    )
    p.add_argument("--sans", default="", help="types de pages à ne pas visiter, séparés par des virgules")
    p.add_argument("--tout-refaire", action="store_true", help="ignore les passes précédentes")
    p.add_argument("--ignorer-robots", action="store_true", help="ne lit pas robots.txt (écrit dans resume.json)")
    p.add_argument("--sortie", type=Path, help="dossier de l'état et des données (défaut : outputs/recoltes/<nom>)")
    p.add_argument("--maintenant", action="store_true", help="reprendre : passer outre l'attente après une alerte")
    p.add_argument("--recette-modifiee", action="store_true", help="reprendre : la recette a changé depuis le début")
    p.add_argument("--pages", action="store_true", help="etat : le journal page par page")
    p.add_argument("--verite", choices=["vitrine", "rallye"], help="noter : la vérité du site du labo")
    p.add_argument(
        "--attendu", action="store_true", help="noter : montre la clé et les champs que la vérité attend, sans noter"
    )
    p.add_argument("--type", help="essayer : type de page imposé (obligatoire pour un fichier .html)")
    p.add_argument("--base", help="essayer : adresse d'où vient le fichier .html")
    p = sous.add_parser(
        "public", help="application publique réduite : vitrine et sessions humaines (docs/site-public.md)"
    )
    p.add_argument(
        "action",
        choices=["servir", "purger", "supprimer", "sessions", "messages", "effacer-message", "frequentation"],
    )
    p.add_argument(
        "identifiant",
        nargs="?",
        help="identifiant de la session (avec `supprimer`), numéro du message ou `tous` (avec `effacer-message`)",
    )
    p = sous.add_parser("rejeu", help="rejouer les sessions humaines contre chaque niveau de l'Arena")
    p.add_argument("--base", type=Path, help="base du site public, lue sans écrire (défaut : base du labo)")
    p.add_argument("--json", dest="format_json", action="store_true", help="sortie JSON")
    args = parseur.parse_args(argv)

    if args.commande == "public":
        return _public(args)

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

    if args.commande == "recolte":
        from . import commande_recolte

        return commande_recolte.executer(args, reglages)

    if args.commande == "rejeu":
        return _rejeu(args, reglages)

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


def _pourcent(valeur: float) -> str:
    return f"{valeur * 100:.0f} %"


def _rejeu(args: argparse.Namespace, reglages: Reglages) -> int:
    """`shadowlab rejeu` : clôt les sessions manuelles abandonnées (labo seulement), puis rejoue."""
    import json

    from . import rejeu

    clos = 0
    if args.base:
        try:
            cx = rejeu.ouvrir_publique(args.base)
        except ValueError as erreur:
            print(f"Refus : {erreur}", file=sys.stderr)
            return 2
        resultat = rejeu.rejouer(cx, publique=True)
    else:
        cx = db.ouvrir(reglages.base_donnees)
        clos = rejeu.clore_inactives(cx)
        resultat = rejeu.rejouer(cx)
    cx.close()
    if args.format_json:
        print(json.dumps({**resultat, "clos": clos}, ensure_ascii=False, indent=2))
        return 0
    s = resultat["sessions"]
    origine = f"base publique {args.base} (lecture seule)" if args.base else f"base du labo ({resultat['experience']})"
    print(f"Rejeu des sessions humaines — {_nettoyer(origine)}")
    if clos:
        minutes = rejeu.DELAI_INACTIVITE_S // 60
        print(f"{clos} session(s) en cours clôturée(s) : aucune activité depuis {minutes} min.")
    if s["inutilisables"]:
        print(f"{s['inutilisables']} session(s) inutilisable(s) (aucune empreinte reçue) : à part, hors de tout taux.")
    if not s["rejouees"]:
        print("Aucune session humaine à rejouer : ouvrir /manuel (labo) ou le site public dans un navigateur.")
        return 0
    ligne = "{:<7} {:<22} {:>8} {:>8} {:>8}  {:<12} {}"
    print("\n" + ligne.format("Niveau", "Nom", "Rejouées", "Arrêtées", "Passées", "Taux d'arrêt", "IC 95 %"))
    for n in resultat["niveaux"]:
        if n["bloque"]:
            w = n["taux_arret"]
            taux, intervalle = _pourcent(w["taux"]), f"[{_pourcent(w['bas'])}, {_pourcent(w['haut'])}]"
        else:
            taux, intervalle = "—", "ne bloque pas" if n["consulte"] else "fingerprinting inactif"
        nom = _nettoyer(n["nom"])[:22]
        print(ligne.format(n["niveau"], nom, n["rejouees"], n["arretees"], n["passees"], taux, intervalle))
    print("\nJalon A : au moins 9 humains sur 10 passent à chaque niveau ; un détecteur gardé classe au plus")
    print("1 humain sur 10 en automatisé. « composite » : signaux faibles cumulés au-delà du seuil du niveau.")
    for n in resultat["niveaux"]:
        if not n["consulte"]:
            continue
        print(f"\nNiveau {n['niveau']} — {_nettoyer(n['nom'])}")
        if n["classes"]:
            print("  Classés « automatisé » (sessions) :")
            for c in n["classes"]:
                part = f"{c['sessions']}/{n['rejouees']}"
                alerte = "au-delà de 1 sur 10" if c["sessions"] * 10 > n["rejouees"] else ""
                codes = ", ".join(f"{_nettoyer(g['code'])} ({g['sessions']})" for g in c["signaux"][:5])
                print(f"    {_nettoyer(c['detecteur']):<24} {part:>7}  {alerte:<19}  {codes}")
        else:
            print("  Classés « automatisé » : aucun.")
        if n["non_evalues"]:
            print("  Non évalués faute de données (écartés du rejeu : effet sur les humains inconnu) :")
            for d in n["non_evalues"]:
                print(f"    {d['detecteur']:<24} {d['sessions']:>3}/{n['rejouees']:<3}  {d['raison']}")
        for r in n["regles_ecartees"]:
            print(f"  Règle écartée : {r['detecteur']}/{r['regle']} ({r['sessions']}/{n['rejouees']}) — {r['raison']}")
        if n["correlation_historique"]:
            h = n["correlation_historique"]
            print(
                f"  correlation-session avec la table actuelle empreintes_vues : {h['sessions']}/{h['sur']}"
                " classée(s) automatisée(s) — dépend de l'historique, hors du taux."
            )
    return 0


def _public(args: argparse.Namespace) -> int:
    """`shadowlab public …` : n'utilise que les réglages `SHADOWLAB_PUBLIC_*`, jamais ceux du laboratoire."""
    from .config import charger_public
    from .public import ROTATION_JOURNAL, creer_app_publique, donnees, messages

    reglages = charger_public()
    configurer(reglages.base_donnees.parent, args.verbeux, rotation=ROTATION_JOURNAL)
    if args.action == "servir":
        import uvicorn

        try:
            app = creer_app_publique(reglages)  # purge au démarrage ; refuse un contact vide ou la base du labo
        except ValueError as erreur:
            print(f"Refus : {erreur}", file=sys.stderr)
            return 2
        print(f"Application publique : http://127.0.0.1:{reglages.port}/ (derrière un mandataire HTTPS)", flush=True)
        boite = messages.connexion(messages.chemin(reglages.base_donnees))
        recus = messages.nombre(boite)
        boite.close()
        if recus:
            print(f"{recus} message(s) de contact à lire : uv run shadowlab public messages", flush=True)
        # Toujours en local : seul le mandataire HTTPS est exposé. Pas de journal d'accès d'uvicorn (il écrirait
        # l'adresse du visiteur et la chaîne de requête, où passe le jeton) ; l'application tient le sien.
        uvicorn.run(
            app,
            host="127.0.0.1",
            port=reglages.port,
            access_log=False,
            proxy_headers=False,
            server_header=False,
            log_level="warning",
        )
        return 0
    try:
        boite = messages.connexion(messages.chemin(reglages.base_donnees))  # refuse une base homonyme
        cx = donnees.ouvrir(reglages.base_donnees)
    except ValueError as erreur:
        print(f"Refus : {erreur}", file=sys.stderr)
        return 2
    if args.action == "purger":
        n = donnees.purger(cx, reglages.conservation_jours)
        m = messages.purger(boite, reglages.conservation_jours)
        print(f"{n} session(s) et {m} message(s) de contact de plus de {reglages.conservation_jours} jours effacé(s).")
        return 0
    if args.action == "frequentation":
        jours = donnees.frequentation(cx)
        if not jours:
            print("Aucune visite comptée pour l'instant.")
            return 0
        print("Fréquentation du site public, par jour UTC (D-75) : chargements de l'accueil, sessions commencées,")
        print("sessions terminées. Rien d'autre n'est compté.\n")
        print(f"{'jour':<12}{'accueil':>10}{'commencées':>12}{'terminées':>11}")
        for jour in jours:
            print(f"{jour['jour']:<12}{jour['accueil']:>10}{jour['commencees']:>12}{jour['terminees']:>11}")
        totaux = [sum(jour[c] for jour in jours) for c in donnees.COMPTES]
        print(f"{'total':<12}{totaux[0]:>10}{totaux[1]:>12}{totaux[2]:>11}")
        return 0
    if args.action == "sessions":
        return _sessions_publiques(cx, reglages.base_donnees)
    if args.action == "messages":
        recus = messages.lister(boite)
        if not recus:
            print("Aucun message de contact.")
            return 0
        print(f"{len(recus)} message(s) de contact (effacer : uv run shadowlab public effacer-message <n°> | tous)")
        for message in recus:
            print(f"\nn° {message['id']} — reçu le {message['recu_le']}")
            for ligne in messages.nettoyer(message["texte"]).splitlines():
                print(f"    {ligne}")
        return 0
    if args.action == "effacer-message":
        numero = (args.identifiant or "").strip()
        if numero.lower() == "tous":
            print(f"{messages.effacer_tout(boite)} message(s) de contact effacé(s).")
            return 0
        if not numero.isdecimal():
            print("Erreur : numéro du message, ou « tous », requis.", file=sys.stderr)
            return 2
        if messages.effacer(boite, int(numero)):
            print("Message effacé.")
            return 0
        print("Aucun message avec ce numéro.", file=sys.stderr)
        return 1
    if not args.identifiant:
        print("Erreur : identifiant de session requis.", file=sys.stderr)
        return 2
    if donnees.effacer_session(cx, args.identifiant.strip().lower()):
        print("Session effacée de toutes les tables.")
        return 0
    print("Aucune session avec cet identifiant.", file=sys.stderr)
    return 1


def _sessions_publiques(cx, base: Path) -> int:
    """`shadowlab public sessions` : chaque session, la plus grosse d'abord, et la place occupée par la base, pour
    repérer une session abusive et la supprimer (`shadowlab public supprimer <identifiant>`)."""
    from .public import Limites, donnees

    plafond = Limites().taille_max_base
    print(
        f"Base : {donnees.occupation(base) / 1e6:.1f} Mo occupés sur {plafond / 1e6:.0f} Mo permis"
        f" (fichiers : {donnees.taille(base) / 1e6:.1f} Mo)."
    )
    liste = donnees.lister_sessions(cx, Limites().duree_session_s)
    if not liste:
        print("Aucune session.")
        return 0
    print(f"{len(liste)} session(s), la plus grosse d'abord (octets ; « total » : envois et requêtes notées).")
    print("Supprimer une session : uv run shadowlab public supprimer <identifiant>\n")
    print(f"{'identifiant':<34}{'début (UTC)':<18}{'état':<10}{'requêtes':>9}{'envois':>8}{'volume':>11}{'total':>11}")
    for s in liste:
        debut = f"{s['debut'][:10]} {s['debut'][11:16]}"
        print(
            f"{s['jeton']:<34}{debut:<18}{s['etat']:<10}{s['requetes']:>9}{s['envois']:>8}{s['volume']:>11}"
            f"{s['total']:>11}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
