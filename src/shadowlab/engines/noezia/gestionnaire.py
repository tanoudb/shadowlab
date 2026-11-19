"""Gestionnaire d'identités (étape 4.2 du plan) : plusieurs identités persistantes se partagent une récolte.

Ce module tient ce qui est commun à la commande (`shadowlab recolte lancer --identites a,b,c`) et à la campagne
(bras d'une même `recolte_partagee`) :
- le **verrou de travail** d'une identité dans une récolte (`verrou_travailleur`, `travailleur_vivant`) : tenu par le
  processus qui travaille pour elle, toute sa vie ; libre, ses pages en cours sont orphelines et reviennent en file
  (`Etat.liberer_orphelines`) ;
- **rien de partagé** (`controler_identites`, au lancement, avant toute requête) : ni profil Chrome (chemin réel,
  inode, et marqueur écrit dans le profil : une copie porte le nom de l'autre), ni proxy (même serveur et même
  utilisateur, D-99), ni graine ; plusieurs identités sans proxy sur un site qui n'est pas local sont refusées (elles
  sortiraient par la même adresse) ;
- la **graine** de chaque identité (`preparer_identite`) : tirée une fois du hasard du système (`secrets`), écrite dans
  son `identite.json`, jamais dérivée d'une graine commune (graine de campagne, `random.seed`). Elle nourrit ses tirages
  (rythme des visites, lecture d'une page) : deux identités ne tirent jamais la même suite.
"""

from __future__ import annotations

import fcntl
import json
import os
import secrets
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import IO

from .identite import IdentiteRefusee, lire_proxy, ouvrir, racine_identites, verifier_nom
from .parcours import RefusParcours
from .proxy_identite import ProxyIdentite, ProxyInvalide
from .recettes import Recette, _est_local

DOSSIER_TRAVAILLEURS = "travailleurs"
ATTENTE_VERROU_S = 5.0  # un autre processus peut tenir ce verrou une fraction de seconde : il le teste
# Écrit dans le dossier de profil Chrome de l'identité, au premier passage par le gestionnaire : un profil copié dans
# une autre identité porte encore le nom de la première. Chrome ignore ce fichier.
MARQUEUR_PROFIL = ".identite-recolte.json"


class PartageRefuse(RefusParcours):
    """Deux identités partageraient quelque chose (profil, proxy, graine, adresse), ou une identité ne peut pas servir :
    refus avant toute requête (code 2 de la commande)."""


@dataclass(frozen=True)
class IdentiteDeRecolte:
    """Une identité prête pour une récolte partagée : son nom, sa graine, son proxy (ou None)."""

    nom: str
    graine: int
    proxy: ProxyIdentite | None = None

    @property
    def proxy_masque(self) -> str | None:
        return None if self.proxy is None else self.proxy.masque()


def _ecrire_json(chemin: Path, donnees: dict) -> None:
    temporaire = chemin.with_name(f"{chemin.name}.{os.getpid()}.tmp")
    temporaire.write_text(json.dumps(donnees, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporaire, chemin)


def preparer_identite(nom: str, *, accepter_bannie: bool = False) -> IdentiteDeRecolte:
    """Ouvre l'identité un instant (crée son dossier au besoin ; refuse une identité bannie, sauf `accepter_bannie`, ou
    prise par un autre lancement), lui donne sa graine si elle n'en a pas, pose le marqueur de son profil Chrome s'il
    manque, puis la rend. Ne lance rien, ne fait aucune requête."""
    try:
        ouverte = ouvrir(nom, maintenant=True)
    except IdentiteRefusee as erreur:
        if "bannie" in str(erreur):
            raise PartageRefuse(f"identité {nom!r} bannie : elle ne sert plus jamais") from None
        raise PartageRefuse(str(erreur)) from None
    try:
        donnees = ouverte.etat()
        if donnees.get("etat") == "banni" and not accepter_bannie:
            raise PartageRefuse(f"identité {nom!r} bannie : elle ne sert plus jamais")
        graine = donnees.get("graine")
        if not isinstance(graine, int) or isinstance(graine, bool):
            graine = secrets.randbits(63)  # le hasard du système : jamais une graine de campagne ni `random.seed`
            _ecrire_json(ouverte.fichier, {**donnees, "graine": graine})
        marqueur = ouverte.dossier_profil / MARQUEUR_PROFIL
        if not marqueur.exists():
            _ecrire_json(marqueur, {"nom": nom})
    finally:
        ouverte.liberer()
    return IdentiteDeRecolte(nom, graine, None)


def _etat_note(nom: str) -> str | None:
    try:
        donnees = json.loads((racine_identites() / nom / "identite.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return donnees.get("etat") if isinstance(donnees, dict) else None


def controler_identites(
    noms: Sequence[str], recette: Recette, *, ecarter_bannies: bool = False
) -> tuple[list[IdentiteDeRecolte], list[str]]:
    """Les identités d'une récolte partagée, prêtes, et celles écartées parce que bannies (`ecarter_bannies`, une
    reprise : une identité tombée en route ne resservira jamais ; au lancement, une bannie est un refus). Lève
    `PartageRefuse` avant toute requête si quelque chose serait partagé ou si une identité ne peut pas servir."""
    if not noms:
        raise PartageRefuse("aucune identité (`--identites a,b,c`)")
    for nom in noms:
        try:
            verifier_nom(nom)
        except ValueError as erreur:
            raise PartageRefuse(str(erreur)) from None
    doubles = sorted({n for n in noms if list(noms).count(n) > 1})
    if doubles:
        raise PartageRefuse(f"identité nommée deux fois : {', '.join(doubles)}")
    ecartees = [n for n in noms if ecarter_bannies and _etat_note(n) == "banni"]
    gardees = [preparer_identite(n) for n in noms if n not in ecartees]
    _controler_graines(gardees)  # d'abord : une identité copiée en entier a aussi le profil de l'autre
    _controler_profils([i.nom for i in gardees])
    gardees = [IdentiteDeRecolte(i.nom, i.graine, _proxy_de(i.nom)) for i in gardees]
    _controler_proxys(gardees, recette)
    return gardees, ecartees


def _controler_profils(noms: list[str]) -> None:
    vus: dict[tuple, str] = {}
    for nom in noms:
        profil = racine_identites() / nom / "chrome"
        info = profil.stat()
        for cle in (("chemin", str(profil.resolve())), ("inode", info.st_dev, info.st_ino)):
            if cle in vus:
                raise PartageRefuse(f"identités {vus[cle]!r} et {nom!r} : même profil Chrome ({profil.resolve()})")
            vus[cle] = nom
        try:
            proprietaire = json.loads((profil / MARQUEUR_PROFIL).read_text(encoding="utf-8")).get("nom")
        except (OSError, ValueError, AttributeError):
            proprietaire = None
        if proprietaire != nom:
            raise PartageRefuse(
                f"identité {nom!r} : son profil Chrome est celui de l'identité {proprietaire!r} (copié ?) : "
                "deux identités ne partagent jamais un profil (même cookie, même visiteur)"
            )


def _controler_graines(identites: list[IdentiteDeRecolte]) -> None:
    vues: dict[int, str] = {}
    for i in identites:
        if i.graine in vues:
            raise PartageRefuse(
                f"identités {vues[i.graine]!r} et {i.nom!r} : même graine (identité copiée ?) : leurs tirages seraient "
                "les mêmes"
            )
        vues[i.graine] = i.nom


def _proxy_de(nom: str) -> ProxyIdentite | None:
    try:
        return lire_proxy(nom)
    except (ProxyInvalide, OSError) as erreur:
        message = str(erreur) if isinstance(erreur, ProxyInvalide) else "fichier illisible"
        raise PartageRefuse(f"proxy inutilisable : {message}") from None


def _controler_proxys(identites: list[IdentiteDeRecolte], recette: Recette) -> None:
    vus: dict[tuple, str] = {}
    sans = [i.nom for i in identites if i.proxy is None]
    for i in identites:
        if i.proxy is None:
            continue
        cle = (i.proxy.hote.lower(), i.proxy.port, i.proxy.utilisateur)
        if cle in vus:
            raise PartageRefuse(
                f"identités {vus[cle]!r} et {i.nom!r} : même proxy (même serveur et même utilisateur, "
                f"{i.proxy.masque()}) : elles sortiraient par la même adresse"
            )
        vus[cle] = i.nom
    if len(sans) >= 2 and not all(_est_local(h) for h in recette.hotes):
        raise PartageRefuse(
            f"identités sans proxy ({', '.join(sans)}) sur un site qui n'est pas local : elles sortiraient par la même "
            "adresse (celle du poste) ; une identité au plus sans proxy (`proxy.json`, D-99)"
        )


def _chemin_verrou(dossier: Path, nom: str) -> Path:
    return Path(dossier) / DOSSIER_TRAVAILLEURS / f"{verifier_nom(nom)}.verrou"


def verrou_travailleur(dossier: Path, nom: str, attente_s: float = ATTENTE_VERROU_S) -> IO[str]:
    """Prend le verrou de travail de l'identité `nom` dans la récolte `dossier` et le rend ouvert : le processus le
    garde (référence vivante) tant qu'il travaille pour elle ; il disparaît avec lui, même tué. Un autre processus peut
    le tenir un instant pour tester s'il est libre (`travailleur_vivant`) : on réessaie pendant `attente_s`. Pris par un
    autre travailleur au-delà : `BlockingIOError` (une identité ne travaille qu'à un endroit à la fois)."""
    chemin = _chemin_verrou(dossier, nom)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    fichier = chemin.open("a+", encoding="utf-8")
    limite = time.monotonic() + attente_s
    while True:
        try:
            fcntl.flock(fichier, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return fichier
        except OSError:
            if time.monotonic() >= limite:
                fichier.close()
                raise BlockingIOError(
                    f"identité {nom!r} : un autre processus travaille déjà pour elle ({chemin})"
                ) from None
            time.sleep(0.05)


def travailleur_vivant(dossier: Path, nom: str) -> bool:
    """Vrai si un processus tient le verrou de travail de `nom` dans cette récolte (essai non bloquant, aussitôt
    relâché). Faux : personne ne travaille pour elle, ses pages en cours sont orphelines."""
    chemin = _chemin_verrou(dossier, nom)
    if not chemin.exists():
        return False
    with chemin.open("a+", encoding="utf-8") as fichier:
        try:
            fcntl.flock(fichier, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return True
        fcntl.flock(fichier, fcntl.LOCK_UN)
        return False
