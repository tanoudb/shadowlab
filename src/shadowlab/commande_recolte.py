"""Commande `shadowlab recolte <action>` : lancer, reprendre, etat, essayer, noter.

Branchement fin sur `engines/noezia/parcours.py` (le travail) : lecture de la recette, choix du moteur, site du labo
démarré au besoin, affichage, codes de sortie : 0 terminée, 3 arrêtée sur alerte (état gardé), 2 refus avant toute
requête (recette invalide, autorisation absente, robots.txt, verrou…), 1 erreur ou passe interrompue.
Format de la recette et déroulement : `docs/recherche/recolte-generale-2026-11-12.md`.
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import functools
import os
import random
import shlex
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from . import campaigns, notation
from .config import Reglages
from .engines.curl_cffi_engine import DriverCurlCffi
from .engines.noezia import gestionnaire
from .engines.noezia.etat import Etat
from .engines.noezia.identite import IdentiteRefusee, lire_etat
from .engines.noezia.identite import verifier_nom as verifier_nom_identite
from .engines.noezia.lecture import LectureHumaine
from .engines.noezia.navigateur import MoteurNavigateur
from .engines.noezia.parcours import (
    Bilan,
    Moteur,
    MoteurDriver,
    Options,
    Parcours,
    RefusParcours,
    Verrou,
    essayer,
    lignes_alertes,
    nettoyer,
    pages_faites,
)
from .engines.noezia.recettes import Recette, RecetteInvalide, _est_local, lire_texte
from .site import rallye, vitrine

SEUIL = 0.99  # « Récolte » du § 1 du plan : pages, enregistrements et champs, chacun ≥ 99 %
MOTEURS_DISPONIBLES = ("http", "navigateur")
_LOCAUX = {"127.0.0.1", "localhost", "::1"}
# Récolte partagée entre identités (`--identites`, étape 4.2).
EN_FILS = False  # tests : les identités dans des fils au lieu de processus neufs
ATTENTE_FILE_S = gestionnaire.ATTENTE_FILE_S  # rien à prendre : la file est relue après
LECTURE_PARTAGEE = LectureHumaine()  # chaque visite lit comme le scénario `visite` (durées dispersées, retours)


def _err(message: str) -> None:
    print(message, file=sys.stderr)


def _lignes_nettoyees(texte: str) -> str:
    """Une ligne reste une ligne (une faute de recette par ligne) ; ce qui n'est pas imprimable devient « ? »."""
    return "\n".join(nettoyer(ligne) for ligne in str(texte).split("\n"))


def _fermer_la_sortie() -> None:
    """Le lecteur du tube est parti (`… | head`) : la sortie va dans le vide, pour que l'arrêt de Python se taise."""
    with contextlib.suppress(AttributeError, OSError, ValueError):
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())


def _pourcent(valeur: float | None) -> str:
    return "—" if valeur is None else f"{valeur * 100:.1f} %".replace(".", ",")


# ═══ Moteur, site du labo, recette ═════════════════════════════════════════════════════════════


def _moteur_disponible(nom: str) -> str:
    if nom not in MOTEURS_DISPONIBLES:
        raise RefusParcours(f"moteur inconnu : « {nom} » (disponibles : {', '.join(MOTEURS_DISPONIBLES)})")
    return nom


def _controler_identite(nom_moteur: str, identite: str | None) -> None:
    """`--identite` ne va qu'avec le moteur navigateur, et son nom doit être valide : sinon un refus (code 2)."""
    if identite is None:
        return
    if nom_moteur != "navigateur":
        raise RefusParcours(
            "--identite ne va qu'avec le moteur navigateur (`--moteur navigateur`) : un client HTTP n'a pas de profil"
        )
    try:
        verifier_nom_identite(identite)
    except ValueError as erreur:
        raise RefusParcours(str(erreur)) from erreur


def construire_moteur(nom: str, recette: Recette, reglages: Reglages, identite: str | None = None) -> Moteur:
    """Le moteur de la passe. Il se construit avec le périmètre du labo (`SHADOWLAB_HOTES_AUTORISES`).

    `identite` : une identité persistante (§ 5.6), moteur `navigateur` seulement ; le nom est contrôlé avant tout."""
    _moteur_disponible(nom)
    _controler_identite(nom, identite)
    if nom == "navigateur":  # le vrai Chrome en identité native ; rien n'est lancé avant `ouvrir()`
        return MoteurNavigateur.depuis(recette, reglages, identite=identite)
    local = all(_est_local(h) for h in recette.hotes)
    pilote = DriverCurlCffi(
        reglages.hotes_autorises,
        {"impersonate": "chrome", "verifier_tls": not local, "timeout": 30, "suivre_redirections": False},
    )
    return MoteurDriver(pilote, nom)


@contextlib.contextmanager
def site_du_labo(recette: Recette, reglages: Reglages) -> Iterator[None]:
    """Démarre le site du labo s'il ne tourne pas et si la recette part de lui (hôte local, port du labo)."""
    partent_du_labo = any(
        (u := urlsplit(d.url)).hostname in _LOCAUX and u.port == reglages.port for d in recette.depart
    )
    if not partent_du_labo:
        yield
        return
    tournait = campaigns._repond(reglages.hote, reglages.port)
    with campaigns.serveur_local(reglages):
        if not tournait:
            print("Site du labo démarré (il ne tournait pas).", flush=True)
        yield


def _moteur(nom: str, recette: Recette, reglages: Reglages, identite: str | None) -> Moteur:
    """`construire_moteur`, avec l'identité seulement quand il y en a une (le moteur reste appelé comme avant sans)."""
    _controler_identite(nom, identite)
    if identite is None:
        return construire_moteur(nom, recette, reglages)
    return construire_moteur(nom, recette, reglages, identite=identite)


def identite_de_la_passe(passe: dict[str, Any]) -> str | None:
    """L'identité persistante dont la passe s'est servie (gardée dans les options du moteur au lancement), ou None :
    une reprise doit être le même visiteur, pas un nouveau."""
    moteur = passe.get("moteur") or {}
    return (moteur.get("options") or {}).get("identite") or (moteur.get("configuration") or {}).get("identite")


def _lire_recette(chemin: Path) -> tuple[Recette, str]:
    try:
        texte = chemin.read_text(encoding="utf-8")
    except OSError as erreur:
        raise RecetteInvalide(f"recette introuvable ou illisible : {chemin} ({erreur})") from erreur
    return lire_texte(texte, source=str(chemin)), texte


def _dossier(args: argparse.Namespace, reglages: Reglages, nom: str) -> Path:
    return Path(args.sortie) if args.sortie else reglages.sorties / "recoltes" / nom


def _options_reprise(args: argparse.Namespace) -> str:
    """Ce qu'il faut rappeler à `reprendre` pour qu'il retrouve la récolte : `--sortie` quand elle a servi."""
    return f" --sortie {shlex.quote(str(args.sortie))}" if args.sortie else ""


def _tranche(valeurs: list[str]) -> dict[str, str]:
    tranche: dict[str, str] = {}
    for valeur in valeurs:
        nom, egal, contenu = valeur.partition("=")
        if not egal or not nom.strip():
            raise RefusParcours(f"--tranche attend nom=valeur, reçu « {valeur} »")
        tranche[nom.strip()] = contenu.strip()
    return tranche


# ═══ Actions ═══════════════════════════════════════════════════════════════════════════════════


def executer(args: argparse.Namespace, reglages: Reglages) -> int:
    actions = {
        "lancer": _lancer,
        "reprendre": _reprendre,
        "etat": _etat,
        "essayer": _essayer,
        "noter": _noter,
    }
    try:
        return actions[args.action](args, reglages)
    except IdentiteRefusee as erreur:  # bannie, en alerte depuis moins d'une heure, ou prise : un refus, aucune requête
        _err(f"Refus : {_lignes_nettoyees(str(erreur))}")
        return 2
    except (RefusParcours, RecetteInvalide) as erreur:
        texte = _lignes_nettoyees(str(erreur))
        _err(texte if isinstance(erreur, RecetteInvalide) else f"Refus : {texte}")
        return 2
    except BrokenPipeError:  # `recolte etat --pages | head` : le lecteur a fermé le tube, ce n'est pas une erreur
        _fermer_la_sortie()
        return 0
    except Exception as erreur:  # noqa: BLE001
        _err(f"Erreur : {nettoyer(str(erreur))}")
        return 1


def _lancer(args: argparse.Namespace, reglages: Reglages) -> int:
    chemin = Path(args.cible)
    recette, texte = _lire_recette(chemin)
    if args.pages_max is not None and args.pages_max < 1:
        raise RefusParcours("--pages-max : au moins 1")
    if args.identites is not None:
        return _lancer_partage(args, reglages, chemin, recette, texte)
    _sans_identites(args)
    nom_moteur = _moteur_disponible(args.moteur or recette.moteur)
    options = Options(
        tranche=_tranche(args.tranche),
        pages_max=args.pages_max,
        sans=tuple(t.strip() for t in args.sans.split(",") if t.strip()),
        tout_refaire=args.tout_refaire,
        ignorer_robots=args.ignorer_robots,
    )
    dossier = _dossier(args, reglages, recette.nom)
    moteur = _moteur(nom_moteur, recette, reglages, args.identite)  # ne touche pas au réseau
    parcours = Parcours(
        recette, texte, str(chemin.resolve()), moteur, dossier, options, options_reprise=_options_reprise(args)
    )
    parcours.verifier_avant_lancer()  # tous les refus qui n'ont pas besoin du site, avant de le démarrer
    with site_du_labo(recette, reglages):
        return parcours.lancer().code


def _sans_identites(args: argparse.Namespace) -> None:
    """Les réglages du rythme d'une identité ne vont qu'avec `--identites` : sans, un refus (rien d'ignoré)."""
    for option, valeur in (("--pages-visite", args.pages_visite), ("--ecart", args.ecart), ("--plage", args.plage)):
        if valeur is not None:
            raise RefusParcours(f"{option} ne va qu'avec `--identites` (récolte partagée entre identités)")


def _noms_identites(valeur: str) -> list[str]:
    return [nom.strip() for nom in valeur.split(",") if nom.strip()]


def _rythme(args: argparse.Namespace) -> gestionnaire.Rythme:
    """Le rythme des identités : l'ordonnanceur de D-90 par défaut ; `--pages-visite`, `--ecart` (minutes) et `--plage`
    (heures « 8-23 », « 0-24 » : à toute heure) le fixent pour un essai. Les plafonds par heure et par jour restent."""
    if args.pages_visite is not None and args.pages_visite < 1:
        raise RefusParcours("--pages-visite : au moins 1")
    if args.ecart is not None and args.ecart < 0:
        raise RefusParcours("--ecart : un nombre de minutes, positif")
    plage = None
    if args.plage is not None:
        debut, tiret, fin = args.plage.partition("-")
        try:
            plage = (int(debut), int(fin))
        except ValueError:
            plage = None
        if not tiret or plage is None or not 0 <= plage[0] < plage[1] <= 24:
            raise RefusParcours(f"--plage attend deux heures « A-B » (0 ≤ A < B ≤ 24), reçu « {args.plage} »")
    return gestionnaire.Rythme(pages=args.pages_visite, ecart_min=args.ecart, plage=plage)


def _refus_partage(args: argparse.Namespace, nom_moteur: str) -> None:
    if args.identite is not None:
        raise RefusParcours("--identite (une seule identité) et --identites (récolte partagée) ne vont pas ensemble")
    if nom_moteur != "navigateur":
        raise RefusParcours(
            "--identites ne va qu'avec le moteur navigateur (`--moteur navigateur`) : chaque identité est un profil "
            "Chrome à elle"
        )
    if args.pages_max is not None:
        raise RefusParcours(
            "--pages-max ne va pas avec --identites : `--pages-visite N` borne une visite, `bornes.pages_max` de la "
            "recette borne toute la récolte"
        )


def _lancer_partage(args: argparse.Namespace, reglages: Reglages, chemin: Path, recette: Recette, texte: str) -> int:
    """`recolte lancer <recette> --moteur navigateur --identites a,b,c` : une passe neuve, partagée par les identités,
    chacune dans son processus, à son rythme, jusqu'à la fin de la récolte. Tous les refus avant toute requête."""
    _refus_partage(args, args.moteur or recette.moteur)
    rythme = _rythme(args)
    identites, _ = gestionnaire.controler_identites(_noms_identites(args.identites), recette)
    options = Options(
        tranche=_tranche(args.tranche),
        sans=tuple(t.strip() for t in args.sans.split(",") if t.strip()),
        tout_refaire=args.tout_refaire,
        ignorer_robots=args.ignorer_robots,
        lecture=LECTURE_PARTAGEE,
    )
    dossier = _dossier(args, reglages, recette.nom)
    modele = Parcours(
        recette,
        texte,
        str(chemin.resolve()),
        construire_moteur("navigateur", recette, reglages),  # sa seule description : rien n'est lancé
        dossier,
        options,
        options_reprise=_options_reprise(args),
    )
    verrou = modele.ouvrir_passe_partagee({i.nom: i.proxy_masque for i in identites})
    return _faire_vivre(modele, verrou, identites, rythme, reglages, args)


def _reprendre_partage(args: argparse.Namespace, reglages: Reglages, dossier: Path, passe: dict[str, Any]) -> int:
    """`recolte reprendre <nom>` d'une passe partagée : avec les identités de la passe (ou `--identites`), sans les
    bannies, qui ne resservent jamais."""
    _refus_partage(args, "navigateur")
    rythme = _rythme(args)
    recette, texte = _recette_de_la_passe(passe)
    if args.identites is not None:
        noms = _noms_identites(args.identites)
    else:
        etat = Etat(dossier / "etat.sqlite3")
        try:
            noms = [i["nom"] for i in etat.identites(passe["numero"])]
        finally:
            etat.fermer()
    identites, ecartees = gestionnaire.controler_identites(noms, recette, ecarter_bannies=True)
    if not identites:
        raise RefusParcours(
            f"toutes les identités sont bannies ({', '.join(ecartees)}) : une identité bannie ne resservira jamais ; "
            f"`uv run shadowlab recolte reprendre {passe['recette']}{_options_reprise(args)} --identites <nouvelles>`"
        )
    gardees = passe["options"] or {}
    options = Options(
        tranche=dict(gardees.get("tranche", {})),
        sans=tuple(gardees.get("sans", ())),
        ignorer_robots=bool(gardees.get("ignorer_robots", False)),
        tout_refaire=bool(gardees.get("tout_refaire", False)),
        lecture=LECTURE_PARTAGEE,
    )
    modele = Parcours(
        recette,
        texte,
        passe["chemin_recette"],
        construire_moteur("navigateur", recette, reglages),
        dossier,
        options,
        options_reprise=_options_reprise(args),
    )
    verrou = modele.reprendre_passe_partagee({i.nom: i.proxy_masque for i in identites})
    for nom in ecartees:
        print(f"Identité {nom} écartée : bannie, elle ne resservira jamais.", flush=True)
    return _faire_vivre(modele, verrou, identites, rythme, reglages, args)


def _faire_vivre(
    modele: Parcours,
    verrou: Verrou,
    identites: list[gestionnaire.IdentiteDeRecolte],
    rythme: gestionnaire.Rythme,
    reglages: Reglages,
    args: argparse.Namespace,
) -> int:
    """Chaque identité dans son processus (`gestionnaire.superviser`), le verrou de la récolte tenu jusqu'au bout ;
    puis la passe est close (pages encore tenues remises en file, exports, `resume.json`)."""
    try:
        with site_du_labo(modele.recette, reglages):
            taches = {
                i.nom: functools.partial(
                    _travailleur_identite,
                    modele.chemin_recette,
                    modele.texte_recette,
                    str(modele.dossier),
                    modele.options,
                    i.nom,
                    i.graine,
                    rythme,
                    ATTENTE_FILE_S,
                    reglages,
                    _options_reprise(args),
                )
                for i in identites
            }
            print(
                f"Récolte partagée : {len(identites)} identité(s) ({', '.join(taches)}), une file commune, une page à "
                "une seule identité à la fois.",
                flush=True,
            )
            try:
                fins = gestionnaire.superviser(taches, en_fils=EN_FILS)
            except KeyboardInterrupt:
                fins = {nom: "interrompue" for nom in taches}
        return modele.cloturer_partage(fins).code
    finally:
        verrou.liberer()


def _travailleur_identite(
    chemin_recette: str,
    texte: str,
    dossier: str,
    options: Options,
    nom: str,
    graine: int,
    rythme: gestionnaire.Rythme,
    attente_file_s: float,
    reglages: Reglages,
    options_reprise: str,
) -> str:
    """La vie d'une identité (dans son processus) : chaque visite construit SON moteur (son profil Chrome, son proxy) et
    lit la file commune ; ses hasards viennent de SA graine."""
    recette = lire_texte(texte, source=chemin_recette)

    def ecran(message: str) -> None:
        print(f"[{nom}] {message}", flush=True)

    def visiter(pages: int, alea: random.Random) -> Bilan:
        moteur = construire_moteur("navigateur", recette, reglages, identite=nom)
        parcours = Parcours(
            recette,
            texte,
            chemin_recette,
            moteur,
            Path(dossier),
            dataclasses.replace(options),
            ecran=ecran,
            alea=alea,
            options_reprise=options_reprise,
        )
        return parcours.visiter_partage(nom, pages)

    return gestionnaire.vie_d_une_identite(nom, graine, visiter, rythme, attente_file_s=attente_file_s, ecran=ecran)


def _passe_de(args: argparse.Namespace, reglages: Reglages) -> tuple[Path, dict[str, Any]]:
    """Dossier et dernière passe de la récolte nommée, ou refus."""
    dossier = _dossier(args, reglages, args.cible)
    if not (dossier / "etat.sqlite3").is_file():
        raise RefusParcours(f"aucune récolte « {args.cible} » dans {dossier}")
    etat = Etat(dossier / "etat.sqlite3")
    try:
        passe = etat.derniere_passe()
    finally:
        etat.fermer()
    if passe is None:
        raise RefusParcours(f"aucune passe dans l'état de « {args.cible} »")
    return dossier, passe


def _recette_de_la_passe(passe: dict[str, Any]) -> tuple[Recette, str]:
    chemin = Path(passe["chemin_recette"])
    if chemin.is_file():
        return _lire_recette(chemin)
    print(f"Recette d'origine absente ({chemin}) : copie gardée au début de la passe.", flush=True)
    texte = passe["texte_recette"]
    return lire_texte(texte, source="copie de la passe"), texte


def _reprendre(args: argparse.Namespace, reglages: Reglages) -> int:
    dossier, passe = _passe_de(args, reglages)
    if (passe["options"] or {}).get("partagee"):
        return _reprendre_partage(args, reglages, dossier, passe)
    if args.identites is not None:
        raise RefusParcours(
            f"--identites : la passe {passe['numero']} n'est pas partagée entre identités (lancée sans `--identites`)"
        )
    _sans_identites(args)
    recette, texte = _recette_de_la_passe(passe)
    moteur = _moteur(
        passe["moteur"]["nom"], recette, reglages, identite_de_la_passe(passe)
    )  # la passe garde son identité
    parcours = Parcours(
        recette, texte, passe["chemin_recette"], moteur, dossier, options_reprise=_options_reprise(args)
    )
    parcours.verifier_avant_reprendre(maintenant=args.maintenant, recette_modifiee=args.recette_modifiee)
    with site_du_labo(recette, reglages):
        bilan = parcours.reprendre(
            maintenant=args.maintenant, recette_modifiee=args.recette_modifiee, pages_max=args.pages_max
        )
    return bilan.code


def _etat(args: argparse.Namespace, reglages: Reglages) -> int:
    dossier, passe = _passe_de(args, reglages)
    etat = Etat(dossier / "etat.sqlite3")
    try:
        numero = passe["numero"]
        c = etat.compteurs(numero)
        par_type = ", ".join(f"{n} {t}" for t, n in etat.faites_par_type(numero).items())
        enregistrements = ", ".join(f"{n} {nom}" for nom, n in etat.nb_enregistrements().items()) or "aucun"
        tourne = Verrou(dossier / "verrou").pris()
        print(f"Récolte {passe['recette']} · dossier {dossier}")
        print(
            f"passe {numero} · {passe['statut']} · début {passe['debut']}"
            + (f" · fin {passe['fin']}" if passe["fin"] else "")
            + (" · une passe tourne en ce moment (verrou pris)" if tourne else "")
        )
        print(
            f"  {pages_faites(c['faites'])} ({par_type or 'aucune'}), {c['a_faire']} à faire, {c['echecs']} échec(s), "
            f"{c['interdites_robots']} interdite(s) par robots.txt, {c['anormales']} anormale(s), "
            f"{c['introuvables']} introuvable(s), {c['hors_site']} lien(s) hors site"
        )
        base = etat.passe_de_base(numero)
        if numero > base and not passe["options"].get("tout_refaire"):  # passe incrémentale
            relues = etat.pages_relues(numero, base)
            print(
                f"  incrémentale : {c['lues']} lue(s) ({relues} relue(s), {c['lues'] - relues} neuve(s)), "
                f"{c['evitees']} évitée(s) car déjà lues"
            )
        print(f"  enregistrements : {enregistrements}")
        defis = [e["detail"] for e in etat.evenements(numero) if e["genre"] == "porte_repassage"]
        if defis:  # option `porte_entree.repassages_max` : un défi d'une rafale ne compte pas comme repassage
            faits = sum(1 for d in defis if d.get("franchie") and not d.get("rafale"))
            print(f"  porte repassée en cours de passe : {faits} fois ({len(defis)} défi(s) vu(s), voir resume.json)")
        for ligne in lignes_alertes(etat.alertes_lecture(numero)):
            print(f"  {ligne}")
        if passe["arret"]:
            a = passe["arret"]
            print(nettoyer(f"  arrêt : signe d'alerte ({a['detail']}) sur {a['adresse']} à {a['quand']}"))
        if (passe["options"] or {}).get("partagee"):
            _etat_partage(etat, numero, dossier)
        if args.pages:
            print("\nJournal des pages (n°, heure, statut, type, durées, enregistrements, liens neufs, décision) :")
            for ligne in etat.lignes_pages(numero):
                print(
                    nettoyer(
                        f"{ligne['rang_lecture']:>5} {ligne['lu_le']} {ligne['statut']} {ligne['type']:<10} "
                        f"{ligne['duree_chargement_ms'] or 0:>7.0f} ms {ligne['duree_totale_ms'] or 0:>7.0f} ms "
                        f"{ligne['enregistrements']:>3} enreg. {ligne['liens_neufs']:>3} liens {ligne['decision']:<11} "
                        f"{ligne['adresse']}"
                    )
                )
    finally:
        etat.fermer()
    return 0


def _etat_partage(etat: Etat, numero: int, dossier: Path) -> None:
    """Récolte partagée : chaque identité (son état, ses pages, ses visites) et la file commune."""
    identites = etat.identites(numero)
    pages = etat.pages_par_identite(numero)
    tenues = etat.en_cours_par_identite(numero)
    a_faire, en_cours = etat.pages_restantes(numero)
    print(f"  identités : {len(identites)}")
    for i in identites:
        nom = i["nom"]
        lues = pages.get(nom, {"lues": 0, "echecs": 0})
        derniere = i["derniere_visite"]
        ligne = (
            f"    {nom} · {(lire_etat(nom) or {}).get('etat', 'inconnue')} · {lues['lues']} lue(s), "
            f"{lues['echecs']} échec(s), {tenues.get(nom, 0)} en cours · {i['visites']} visite(s)"
        )
        if derniere:
            ligne += f", dernière le {derniere['debut']} ({derniere['statut']}, {derniere['pages']} page(s))"
        if i["proxy"]:
            ligne += f" · proxy {i['proxy']}"
        if gestionnaire.travailleur_vivant(dossier, nom):
            ligne += " · en visite en ce moment"
        print(nettoyer(ligne))
    print(f"  file : {a_faire} à faire, {en_cours} en cours")


def _essayer(args: argparse.Namespace, reglages: Reglages) -> int:
    recette, _ = _lire_recette(Path(args.cible))
    if not args.adresse:
        raise RefusParcours("essayer demande une adresse de page, ou un fichier .html (avec --type et --base)")
    fichier = Path(args.adresse)
    if fichier.is_file():
        if not args.type or not args.base:
            raise RefusParcours("un fichier .html demande --type (type de page) et --base (adresse d'où il vient)")
        essai = essayer(
            recette, None, args.base, type_page=args.type, tranche=_tranche(args.tranche),
            html=fichier.read_text(encoding="utf-8"),
        )  # fmt: skip
    else:
        with site_du_labo(recette, reglages):
            moteur = construire_moteur(_moteur_disponible(args.moteur or recette.moteur), recette, reglages)
            essai = essayer(
                recette, moteur, args.adresse, type_page=args.type, tranche=_tranche(args.tranche),
                ignorer_robots=args.ignorer_robots,
            )  # fmt: skip
    print(nettoyer(f"Page {essai.adresse_finale} · statut {essai.statut or '(fichier)'} · type {essai.type}"))
    if essai.resultat is None:
        raison = "aucune réponse" if essai.statut is None else f"statut {essai.statut} (hors 2xx)"
        _err(f"Page non lue : {raison}.")
        return 1
    resultat = essai.resultat
    if not resultat.conforme:
        _err(nettoyer(f"Page non conforme au type « {essai.type} » : {'; '.join(resultat.alertes)}"))
        return 1
    print(f"Enregistrements ({len(resultat.enregistrements)}) :")
    for e in resultat.enregistrements:
        print(
            nettoyer(
                f"  {e.collection} {list(e.cle)}"
                + (f" · relocalisés : {', '.join(e.relocalises)}" if e.relocalises else "")
            )
        )
        for nom, valeur in e.donnees.items():
            print(nettoyer(f"    {nom}: {valeur!r}"[:200]))
    print(f"Liens à suivre ({len(resultat.liens)}) :")
    for lien in resultat.liens[:20]:
        print(nettoyer(f"  {lien.type:<10} {lien.adresse}"))
    if len(resultat.liens) > 20:
        print(f"  … et {len(resultat.liens) - 20} autres")
    for alerte in resultat.alertes:
        print(nettoyer(f"Alerte : {alerte}"))
    return 0


def _verite_du_labo(args: argparse.Namespace, reglages: Reglages) -> tuple[Any, Any, dict, dict, list[str]]:
    """Graine, taille, collections {nom: (liste, clé)}, vérité par collection et pages attendues du site factice."""
    if args.verite == "vitrine":
        graine, taille = reglages.vitrine_graine, reglages.vitrine_taille
        verite = vitrine.verite(graine, taille)  # {"annonces": [...]}
        return graine, taille, {"annonces": ("annonces", "reference")}, verite, vitrine.pages_attendues(graine, taille)
    graine, taille = reglages.rallye_graine, reglages.rallye_taille
    complete = rallye.verite(graine, taille)
    collections = {nom: (nom, cle) for nom, cle in complete["cles"].items()}
    return graine, taille, collections, complete["collections"], [p["adresse"] for p in complete["pages"]]


def _montrer_attendu(args: argparse.Namespace, reglages: Reglages) -> int:
    """Ce que la vérité attend, par collection : sa clé et ses champs. Ne lit aucune récolte, ne note rien."""
    graine, taille, collections, verite, _ = _verite_du_labo(args, reglages)
    print(f"Ce que la vérité {args.verite} attend (graine {graine}, taille {taille}) :")
    for nom, (liste, cle) in collections.items():
        champs: list[str] = []
        for e in verite[liste]:
            champs += [c for c in e if c not in champs]
        cles = [cle] if isinstance(cle, str) else list(cle)
        print(f"  {nom} · clé : {', '.join(cles)} · {len(verite[liste])} enregistrements")
        print(f"    champs : {', '.join(champs)}")
    return 0


def _diagnostic(
    nom: str, cle: Any, n: dict[str, Any], recoltes: list[dict], attendus: list[dict], collections: str
) -> str | None:
    """Pourquoi aucun enregistrement n'est retrouvé (rien si au moins un l'est)."""
    cles = (cle,) if isinstance(cle, str) else tuple(cle)
    if n["enregistrements_retrouves"] or not n["enregistrements_attendus"]:
        return None
    if not recoltes:
        return f"aucun enregistrement « {nom} » récolté ; collections récoltées : {collections}."
    if n["cle_absente"]:
        absentes = ", ".join(f"`{c}`" for c in n["cle_absente"])
        return (
            f"la clé attendue est `{', '.join(cles)}` ({absentes} absente des enregistrements) ; "
            f"les enregistrements récoltés ont les champs : {', '.join(n['champs_recoltes'])}."
        )
    recolte = [recoltes[0].get(c) for c in cles]
    attendu = [attendus[0].get(c) for c in cles]
    return (
        f"aucune clé récoltée ne correspond à la vérité (clé `{', '.join(cles)}` : récolté {recolte}, "
        f"attendu par exemple {attendu})."
    )


def evaluer_passe(etat: Etat, numero: int, nom_verite: str, reglages: Reglages) -> dict[str, Any]:
    """Note une passe contre la vérité du site factice (`vitrine` ou `rallye`) : pages, enregistrements, champs.

    Même notation que `recolte noter`, rendue en données (scénarios de campagne). `champs` vaut 0 quand aucun champ
    n'est comparable (rien retrouvé) : ce n'est jamais un succès. `reussi` : les trois mesures atteignent `SEUIL`.
    """
    _, _, collections, verite, attendues = _verite_du_labo(argparse.Namespace(verite=nom_verite), reglages)
    pages = notation.noter_pages(attendues, etat.adresses_couvertes(numero))
    notes = {
        nom: notation.noter_recolte(etat.enregistrements(nom), verite, liste=liste, cle=cle)
        for nom, (liste, cle) in collections.items()
    }
    attendus = sum(n["enregistrements_attendus"] for n in notes.values())
    retrouves = sum(n["enregistrements_retrouves"] for n in notes.values())
    champs_attendus = sum(n["champs_attendus"] for n in notes.values())
    champs_exacts = sum(n["champs_exacts"] for n in notes.values())
    mesures = {
        "pages": pages["completude_pages"],
        "enregistrements": retrouves / attendus if attendus else 0.0,
        "champs": champs_exacts / champs_attendus if champs_attendus else 0.0,
    }
    return {
        **mesures,
        "seuil": SEUIL,
        "reussi": all(v >= SEUIL for v in mesures.values()),
        "pages_lues": pages["pages_lues"],
        "pages_attendues": pages["pages_attendues"],
        "pages_manquantes": pages["pages_manquantes"],
        "enregistrements_retrouves": retrouves,
        "enregistrements_attendus": attendus,
        "champs_exacts": champs_exacts,
        "champs_attendus": champs_attendus,
        "par_collection": {
            nom: {
                "enregistrements": f"{n['enregistrements_retrouves']}/{n['enregistrements_attendus']}",
                "champs": f"{n['champs_exacts']}/{n['champs_attendus']}",
                "erreurs_par_champ": n["erreurs_par_champ"],
            }
            for nom, n in notes.items()
        },
    }


def _noter(args: argparse.Namespace, reglages: Reglages) -> int:
    if not args.verite:
        raise RefusParcours("noter demande --verite vitrine|rallye")
    if args.attendu:
        return _montrer_attendu(args, reglages)
    dossier, passe = _passe_de(args, reglages)
    etat = Etat(dossier / "etat.sqlite3")
    try:
        graine, taille, collections, verite, attendues = _verite_du_labo(args, reglages)
        pages = notation.noter_pages(attendues, etat.adresses_couvertes(passe["numero"]))
        brut = {nom: etat.enregistrements(nom) for nom in collections}
        notes = {
            nom: notation.noter_recolte(brut[nom], verite, liste=liste, cle=cle)
            for nom, (liste, cle) in collections.items()
        }
        recoltees = etat.collections()
    finally:
        etat.fermer()
    attendus = sum(n["enregistrements_attendus"] for n in notes.values())
    retrouves = sum(n["enregistrements_retrouves"] for n in notes.values())
    champs_attendus = sum(n["champs_attendus"] for n in notes.values())
    champs_exacts = sum(n["champs_exacts"] for n in notes.values())
    completude = retrouves / attendus if attendus else 0.0
    exactitude = champs_exacts / champs_attendus if champs_attendus else None
    print(
        f"Notation de {passe['recette']} (passe {passe['numero']}) contre la vérité {args.verite} : "
        f"graine {graine}, taille {taille}"
    )
    print(f"  pages {pages['pages_lues']}/{pages['pages_attendues']} ({_pourcent(pages['completude_pages'])})")
    print(f"  enregistrements {retrouves}/{attendus} ({_pourcent(completude)})")
    for nom, n in notes.items():
        print(
            f"    {nom} {n['enregistrements_retrouves']}/{n['enregistrements_attendus']}"
            f" · champs {n['champs_exacts']}/{n['champs_attendus']}"
            + (" (rien à comparer)" if not n["champs_attendus"] else "")
            + (f" · erreurs {n['erreurs_par_champ']}" if n["erreurs_par_champ"] else "")
        )
    if exactitude is None:
        print(f"  champs {champs_exacts}/{champs_attendus} : rien à comparer, ce n'est pas un succès")
    else:
        print(f"  champs {champs_exacts}/{champs_attendus} ({_pourcent(exactitude)})")
    for nom, (_, cle) in collections.items():
        n = notes[nom]
        pourquoi = _diagnostic(nom, cle, n, brut[nom], verite[collections[nom][0]], ", ".join(recoltees) or "aucune")
        if pourquoi:
            print(nettoyer(f"  ATTENTION {nom} : {pourquoi}"))
        if n["champs_en_plus"]:
            print(nettoyer(
                f"  {nom} : champs produits mais absents de la vérité (non notés) : {', '.join(n['champs_en_plus'])}"
            ))  # fmt: skip
    if pages["pages_manquantes"]:
        print(nettoyer(f"  pages manquantes (début) : {', '.join(pages['pages_manquantes'][:5])}"))
    mesures = {"pages": pages["completude_pages"], "enregistrements": completude, "champs": exactitude or 0.0}
    sous_le_seuil = [nom for nom, valeur in mesures.items() if valeur < SEUIL]
    if sous_le_seuil:
        print(f"Sous le seuil de {SEUIL * 100:.0f} % : {', '.join(sous_le_seuil)}.")
        return 1
    print(f"Seuil de {SEUIL * 100:.0f} % atteint sur les pages, les enregistrements et les champs.")
    return 0
