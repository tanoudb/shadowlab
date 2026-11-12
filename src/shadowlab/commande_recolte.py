"""Commande `shadowlab recolte <action>` : lancer, reprendre, etat, essayer, noter.

Branchement fin sur `engines/noezia/parcours.py` (le travail) : lecture de la recette, choix du moteur, site du labo
démarré au besoin, affichage, codes de sortie : 0 terminée, 3 arrêtée sur alerte (état gardé), 2 refus avant toute
requête (recette invalide, autorisation absente, robots.txt, verrou…), 1 erreur ou passe interrompue.
Format de la recette et déroulement : `docs/recherche/recolte-generale-2026-11-12.md`.
"""

from __future__ import annotations

import argparse
import contextlib
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from . import campaigns, notation
from .config import Reglages
from .engines.curl_cffi_engine import DriverCurlCffi
from .engines.noezia.etat import Etat
from .engines.noezia.navigateur import MoteurNavigateur
from .engines.noezia.parcours import (
    Moteur,
    MoteurDriver,
    Options,
    Parcours,
    RefusParcours,
    Verrou,
    essayer,
    lignes_alertes,
    nettoyer,
)
from .engines.noezia.recettes import Recette, RecetteInvalide, _est_local, lire_texte
from .site import rallye, vitrine

SEUIL = 0.99  # « Récolte » du § 1 du plan : pages, enregistrements et champs, chacun ≥ 99 %
MOTEURS_DISPONIBLES = ("http", "navigateur")
_LOCAUX = {"127.0.0.1", "localhost", "::1"}


def _err(message: str) -> None:
    print(message, file=sys.stderr)


def _pourcent(valeur: float | None) -> str:
    return "—" if valeur is None else f"{valeur * 100:.1f} %".replace(".", ",")


# ═══ Moteur, site du labo, recette ═════════════════════════════════════════════════════════════


def _moteur_disponible(nom: str) -> str:
    if nom not in MOTEURS_DISPONIBLES:
        raise RefusParcours(f"moteur inconnu : « {nom} » (disponibles : {', '.join(MOTEURS_DISPONIBLES)})")
    return nom


def construire_moteur(nom: str, recette: Recette, reglages: Reglages) -> Moteur:
    """Le moteur de la passe. Il se construit avec le périmètre du labo (`SHADOWLAB_HOTES_AUTORISES`)."""
    _moteur_disponible(nom)
    if nom == "navigateur":  # le vrai Chrome en identité native ; rien n'est lancé avant `ouvrir()`
        return MoteurNavigateur.depuis(recette, reglages)
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


def _lire_recette(chemin: Path) -> tuple[Recette, str]:
    try:
        texte = chemin.read_text(encoding="utf-8")
    except OSError as erreur:
        raise RecetteInvalide(f"recette introuvable ou illisible : {chemin} ({erreur})") from erreur
    return lire_texte(texte, source=str(chemin)), texte


def _dossier(args: argparse.Namespace, reglages: Reglages, nom: str) -> Path:
    return Path(args.sortie) if args.sortie else reglages.sorties / "recoltes" / nom


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
    except (RefusParcours, RecetteInvalide) as erreur:
        _err(nettoyer(str(erreur)) if isinstance(erreur, RecetteInvalide) else f"Refus : {nettoyer(str(erreur))}")
        return 2
    except Exception as erreur:  # noqa: BLE001
        _err(f"Erreur : {nettoyer(str(erreur))}")
        return 1


def _lancer(args: argparse.Namespace, reglages: Reglages) -> int:
    chemin = Path(args.cible)
    recette, texte = _lire_recette(chemin)
    if args.pages_max is not None and args.pages_max < 1:
        raise RefusParcours("--pages-max : au moins 1")
    nom_moteur = _moteur_disponible(args.moteur or recette.moteur)
    options = Options(
        tranche=_tranche(args.tranche),
        pages_max=args.pages_max,
        sans=tuple(t.strip() for t in args.sans.split(",") if t.strip()),
        tout_refaire=args.tout_refaire,
        ignorer_robots=args.ignorer_robots,
    )
    dossier = _dossier(args, reglages, recette.nom)
    moteur = construire_moteur(nom_moteur, recette, reglages)  # ne touche pas au réseau
    parcours = Parcours(recette, texte, str(chemin.resolve()), moteur, dossier, options)
    parcours.verifier_avant_lancer()  # tous les refus qui n'ont pas besoin du site, avant de le démarrer
    with site_du_labo(recette, reglages):
        return parcours.lancer().code


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


def _reprendre(args: argparse.Namespace, reglages: Reglages) -> int:
    dossier, passe = _passe_de(args, reglages)
    chemin = Path(passe["chemin_recette"])
    if chemin.is_file():
        recette, texte = _lire_recette(chemin)
    else:
        print(f"Recette d'origine absente ({chemin}) : copie gardée au début de la passe.", flush=True)
        texte = passe["texte_recette"]
        recette = lire_texte(texte, source="copie de la passe")
    moteur = construire_moteur(passe["moteur"]["nom"], recette, reglages)
    parcours = Parcours(recette, texte, passe["chemin_recette"], moteur, dossier)
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
            f"  {c['faites']} pages faites ({par_type or 'aucune'}), {c['a_faire']} à faire, {c['echecs']} échec(s), "
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
        for ligne in lignes_alertes(etat.alertes_lecture(numero)):
            print(f"  {ligne}")
        if passe["arret"]:
            a = passe["arret"]
            print(nettoyer(f"  arrêt : signe d'alerte ({a['detail']}) sur {a['adresse']} à {a['quand']}"))
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
        print("Rien n'a été lu (statut hors 2xx).")
        return 0
    resultat = essai.resultat
    if not resultat.conforme:
        print(nettoyer(f"Page non conforme au type « {essai.type} » : {'; '.join(resultat.alertes)}"))
        return 0
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
