"""Parcours d'un site par requêtes HTTP : file, ordre, dédoublonnage, reprise, rythme, robots.txt, arrêt sur alerte.

Ce que fait `Parcours` pour une recette : partir des adresses de départ, lire chaque page (le moteur), en tirer
enregistrements et liens (`recettes.extraire`), mettre les liens neufs en file, écrire le tout page par page dans
l'état (`etat.Etat`, SQLite). Profondeur d'abord : les fiches d'une liste avant la page suivante.

Le moteur est derrière une interface simple (`Moteur.lire`) : l'étape 4 y branche le navigateur sans toucher au
parcours. La décision d'arrêt est dans `sentinelle.Sentinelle`, que l'étape 4 complète.
Format et déroulement : `docs/recherche/recolte-generale-2026-11-12.md` § 3 et § 5.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import logging
import os
import random
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urldefrag, urljoin, urlsplit

from ...perimetre import DestinationRefusee
from ..base import Driver
from .etat import Etat, Page, canonique
from .export import FORMAT_CSV, ecrire_exports
from .extraction import Signatures
from .recettes import Recette, Resultat, _est_local, chemin_et_parametres, extraire
from .robots import Robots
from .rythme import Cadence, rythme_de
from .sentinelle import FENETRE, STATUTS_ALERTE, Alerte, Sentinelle, detecter_defi

NOUVEAUX_ESSAIS = 2  # sur panne réseau, 500, 502, 504 (après le premier essai), attente croissante
STATUTS_A_RETENTER = frozenset({500, 502, 504})
ATTENTE_APRES_ALERTE_S = 3600  # « reprendre » conseille d'attendre 1 h (choix du document, § 5)
PAS_AFFICHAGE = 25
PAS_ATTENTE_PORTE_S = 1.0  # la porte d'entrée relit la page toutes les secondes, sans rien faire d'autre
# Repasser la porte en cours de passe : une protection pose parfois plusieurs laissez-passer à quelques secondes d'écart
# (l'Arena : défi, Turnstile, reCAPTCHA, CAPTCHA), qui expirent de même. Les défis vus moins de RAFALE_PORTE_S après le
# premier passage d'une porte, RAFALE_PORTE_MAX au plus ce premier compris, font partie de ce passage : ils ne comptent
# pas comme repassages et ne sont pas soumis à `ecart_min_s`.
RAFALE_PORTE_S = 120.0
RAFALE_PORTE_MAX = 4
REDIRECTIONS = frozenset({301, 302, 303, 307, 308})
REDIRECTIONS_MAX = 5  # sauts suivis un à un, chacun contrôlé avant d'être demandé
PASSES_NON_FINIES = ("en_cours", "arretee", "interrompue", "limitee")


class _SautRefuse(Exception):
    """Une redirection mène à un endroit qu'on ne demandera pas (alerte, ou interdit par robots.txt)."""

    def __init__(self, alerte: Alerte | None) -> None:
        super().__init__(alerte.detail if alerte else "interdit par robots.txt")
        self.alerte = alerte


class RefusParcours(Exception):
    """Refus avant toute page lue (recette, autorisation, robots.txt, verrou, passe non finie) : code de sortie 2."""


# ═══ Verrou ════════════════════════════════════════════════════════════════════════════════════


class Verrou:
    """Empêche deux passes en même temps sur la même recette (verrou de fichier : il disparaît avec le processus)."""

    def __init__(self, chemin: Path) -> None:
        self.chemin = chemin
        self._fichier: Any = None

    def prendre(self) -> None:
        self.chemin.parent.mkdir(parents=True, exist_ok=True)
        fichier = self.chemin.open("a+")
        try:
            fcntl.flock(fichier, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            fichier.seek(0)
            pid = fichier.read().strip()
            fichier.close()
            raise RefusParcours(
                f"verrou pris : une passe tourne déjà sur cette recette{f' (processus {pid})' if pid else ''}"
                f" ({self.chemin})"
            ) from None
        fichier.seek(0)
        fichier.truncate()
        fichier.write(str(os.getpid()))
        fichier.flush()
        self._fichier = fichier

    def liberer(self) -> None:
        if self._fichier is not None:
            fcntl.flock(self._fichier, fcntl.LOCK_UN)
            self._fichier.close()
            self._fichier = None

    def pris(self) -> bool:
        """Vrai si quelqu'un d'autre tient le verrou (essai non bloquant, aussitôt relâché)."""
        if not self.chemin.exists():
            return False
        with self.chemin.open("a+") as fichier:
            try:
                fcntl.flock(fichier, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                return True
            fcntl.flock(fichier, fcntl.LOCK_UN)
            return False


# ═══ Moteur ════════════════════════════════════════════════════════════════════════════════════


@dataclass
class Reponse:
    statut: int | None
    adresse_finale: str
    html: str
    duree_ms: float
    location: str | None = None  # destination d'une redirection que le moteur n'a pas suivie
    entetes: dict[str, str] = field(
        default_factory=dict
    )  # en-têtes de la réponse (clés en minuscules), si le moteur les donne


class Moteur(Protocol):
    """Ce que le parcours demande à un moteur : ouvrir, lire une adresse, fermer, se décrire."""

    def ouvrir(self) -> None: ...

    def fermer(self) -> None: ...

    def lire(self, adresse: str) -> Reponse: ...

    def relire(self) -> Reponse | None:
        """La page courante telle qu'elle est maintenant, SANS nouvelle requête ; None si le moteur ne peut pas
        (pas de JavaScript : la page ne change pas seule). Sert à la porte (entrée et repassages)."""
        ...

    def description(self) -> dict[str, Any]: ...


class MoteurDriver:
    """Un `engines.base.Driver` vu comme un `Moteur`. `verifier` (périmètre) est appelé avant chaque requête."""

    def __init__(self, driver: Driver, nom: str) -> None:
        self.driver = driver
        self.nom = nom
        self._session = False

    def ouvrir(self) -> None:
        self.driver.open()
        self.driver.start_session()  # une seule session : les cookies passent d'une page à l'autre
        self._session = True

    def fermer(self) -> None:
        try:
            if self._session:
                self.driver.close_session()
        finally:
            self._session = False
            self.driver.close()

    def lire(self, adresse: str) -> Reponse:
        self.driver.verifier(adresse)
        navigation = self.driver.navigate(adresse)
        etat_page = getattr(self.driver, "etat_page", None)
        return Reponse(
            navigation.status,
            navigation.url,
            self.driver.dom(),
            navigation.duration_ms,
            getattr(self.driver, "location", None),
            dict(etat_page()[2]) if etat_page is not None else {},
        )

    def relire(self) -> Reponse | None:
        etat_page = getattr(self.driver, "etat_page", None)
        if etat_page is None or not self.driver.executes_javascript:
            return None
        statut, adresse, entetes = etat_page()
        return Reponse(statut, adresse, self.driver.dom(), 0.0, None, dict(entetes))

    def description(self) -> dict[str, Any]:
        return {
            "nom": self.nom,
            "pilote": self.driver.name,
            "configuration": self.driver.configuration(),
            "versions": self.driver.versions(),
        }


# ═══ Parcours ══════════════════════════════════════════════════════════════════════════════════


@dataclass
class Options:
    tranche: dict[str, str] = field(default_factory=dict)
    pages_max: int | None = None
    sans: tuple[str, ...] = ()
    tout_refaire: bool = False
    ignorer_robots: bool = False


@dataclass
class Bilan:
    code: int  # 0 terminée (ou limite atteinte) ; 3 arrêtée sur alerte ; 1 interrompue
    statut: str  # terminee, limitee, arretee, interrompue
    passe: int
    arret: dict[str, Any] | None
    resume: dict[str, Any]
    dossier_passe: Path


def _empreinte(texte: str) -> str:
    return "sha256:" + hashlib.sha256(texte.encode("utf-8")).hexdigest()


def pages_faites(n: int) -> str:
    """« 0 page faite », « 1 page faite », « 2 pages faites » (le pluriel français commence à 2)."""
    return f"{n} page faite" if n < 2 else f"{n} pages faites"


def nettoyer(texte: str) -> str:
    """Retire les caractères de contrôle (une adresse ou un texte du site ne doit pas piloter le terminal)."""
    return "".join(c if c.isprintable() else "?" for c in str(texte))


def _hote(adresse: str) -> str:
    return (urlsplit(adresse).hostname or "").lower()


def _origine(adresse: str) -> str:
    morceaux = urlsplit(adresse)
    return f"{morceaux.scheme.lower()}://{morceaux.netloc.lower()}"


def _chemin_et_requete(adresse: str) -> str:
    morceaux = urlsplit(adresse)
    return (morceaux.path or "/") + (f"?{morceaux.query}" if morceaux.query else "")


_JOURNAL = logging.getLogger("shadowlab.recolte")


def lignes_alertes(alertes: Mapping[str, Any]) -> list[str]:
    """Les alertes de lecture d'une passe, prêtes à afficher : le total, puis les plus fréquentes avec un exemple."""
    total, groupes = alertes["total"], alertes["groupes"]
    if not total:
        return ["Alertes de lecture : aucune."]
    lignes = [f"Alertes de lecture : {total} au total, {len(groupes)} sorte(s) parmi les plus fréquentes :"]
    for g in groupes:
        lignes.append(nettoyer(f"  {g['nb']} × {g['type']} · {g['exemple_message']} (ex. {g['exemple_adresse']})"))
    return lignes


def _maintenant() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _secondes(depuis: str, jusqu_a: str) -> float:
    """Secondes entre deux horodatages ISO (l'horloge de la porte : elle survit à une reprise, comme l'état)."""
    return (datetime.fromisoformat(jusqu_a) - datetime.fromisoformat(depuis)).total_seconds()


def _page_ordinaire(reponse: Reponse | None) -> bool:
    """Vrai si la page relue est en 2xx et sans défi : la vraie page est là."""
    return (
        reponse is not None
        and reponse.statut is not None
        and 200 <= reponse.statut < 300
        and detecter_defi(reponse.html, reponse.entetes) is None
    )


class Parcours:
    def __init__(
        self,
        recette: Recette,
        texte_recette: str,
        chemin_recette: str,
        moteur: Moteur,
        dossier: Path,
        options: Options | None = None,
        *,
        ecran: Callable[[str], None] = print,
        horloge: Callable[[], float] = time.monotonic,
        dormir: Callable[[float], None] = time.sleep,
        alea: random.Random | None = None,
        horodatage: Callable[[], str] = _maintenant,
        options_reprise: str = "",
    ) -> None:
        """`options_reprise` : les options (`--sortie …`) à rappeler dans la commande `reprendre` conseillée."""
        self.recette = recette
        self.texte_recette = texte_recette
        self.chemin_recette = chemin_recette
        self.empreinte = _empreinte(texte_recette)
        self.moteur = moteur
        self.dossier = dossier
        self.options = options or Options()
        self._ecran = lambda message: ecran(nettoyer(message))
        self._horloge = horloge
        self._dormir = dormir
        self._alea = alea or random.Random()
        self._horodatage = horodatage
        self._robots: dict[str, Robots] = {}
        self._robots_resume: dict[str, dict[str, Any]] = {}
        self._courante: Page | None = None
        self._options_reprise = options_reprise
        self._decalage = 0  # pages déjà lues au début d'une reprise : `--pages-max N` en lit N de plus

    def _commande_reprendre(self, *options: str) -> str:
        """La commande qui retrouve CETTE récolte (`--sortie` compris s'il a servi), avec les `options` en plus."""
        return " ".join(
            ["uv run shadowlab recolte reprendre", self.recette.nom + self._options_reprise, *options]
        ).strip()

    # ── Entrées ─────────────────────────────────────────────────────────
    def lancer(self) -> Bilan:
        """Nouvelle passe. Refuse (`RefusParcours`) avant toute page si quelque chose ne va pas."""
        self._controles()
        verrou = Verrou(self.dossier / "verrou")
        verrou.prendre()
        etat = Etat(self.dossier / "etat.sqlite3")
        try:
            derniere = self._refus_lancer(etat)
            self.moteur.ouvrir()
            self._verifier_le_depart()
            if self.options.tout_refaire and derniere:
                if derniere["statut"] in PASSES_NON_FINIES:
                    etat.terminer_passe(derniere["numero"], "abandonnee", derniere["arret"], self._horodatage())
                etat.effacer_enregistrements()
            passe = etat.ouvrir_passe(
                self.recette.nom,
                self.empreinte,
                self.texte_recette,
                self.chemin_recette,
                self.moteur.description(),
                self._options_gardees(),
                self._horodatage(),
            )
            etat.empiler(
                passe,
                [(d.url, d.type) for d in self.recette.depart],
                self.recette.parametres_ignores,
                self.recette.bornes.par_type,
            )
            self._evenement(etat, passe, "debut", {"moteur": self.moteur.description()["nom"]})
            return self._executer(etat, passe, reprise=False)
        finally:
            etat.fermer()
            self.moteur.fermer()
            verrou.liberer()

    def reprendre(
        self, *, maintenant: bool = False, recette_modifiee: bool = False, pages_max: int | None = None
    ) -> Bilan:
        """Continue la dernière passe (coupée, arrêtée ou limitée), avec ses options de départ, sauf la limite de
        pages : elle valait pour le lancement. Sans `pages_max`, la reprise va jusqu'au bout ; avec, elle lit
        `pages_max` pages de plus."""
        self._controles(reprise=True)
        verrou = Verrou(self.dossier / "verrou")
        verrou.prendre()
        etat = Etat(self.dossier / "etat.sqlite3")
        try:
            passe = self._refus_reprendre(etat, maintenant, recette_modifiee)
            gardees = passe["options"]
            self.options = Options(
                tranche=dict(gardees.get("tranche", {})),
                pages_max=pages_max,
                sans=tuple(gardees.get("sans", ())),
                ignorer_robots=bool(gardees.get("ignorer_robots", False)),
                tout_refaire=bool(gardees.get("tout_refaire", False)),  # une passe « tout refaire » reste complète
            )
            self._controles(reprise=True)
            self.moteur.ouvrir()
            self._verifier_le_depart(reprise=True)
            remises = etat.reprendre_passe(passe["numero"])
            if recette_modifiee and passe["empreinte"] != self.empreinte:
                etat.changer_recette(passe["numero"], self.empreinte, self.texte_recette)
            self._evenement(etat, passe["numero"], "reprise", {"pages_remises_en_file": remises})
            return self._executer(etat, passe["numero"], reprise=True)
        finally:
            etat.fermer()
            self.moteur.fermer()
            verrou.liberer()

    def _evenement(self, etat: Etat, passe: int, genre: str, detail: Mapping[str, Any]) -> None:
        """Un événement de la passe : dans l'état, et dans le journal du labo (niveau DEBUG, fichier seulement)."""
        etat.evenement(passe, genre, detail, self._horodatage())
        _JOURNAL.debug(
            "récolte %s passe %s : %s %s", self.recette.nom, passe, genre, json.dumps(detail, ensure_ascii=False)
        )

    # ── Refus qui ne demandent aucune requête ───────────────────────────
    def _refus_lancer(self, etat: Etat) -> dict[str, Any] | None:
        derniere = etat.derniere_passe()
        if derniere and derniere["statut"] in PASSES_NON_FINIES and not self.options.tout_refaire:
            raise RefusParcours(
                f"la passe {derniere['numero']} n'est pas finie ({derniere['statut']}) : "
                f"`{self._commande_reprendre()}`, ou `lancer … --tout-refaire` pour tout recommencer"
            )
        return derniere

    def _refus_reprendre(self, etat: Etat, maintenant: bool, recette_modifiee: bool) -> dict[str, Any]:
        passe = etat.derniere_passe()
        if passe is None:
            raise RefusParcours(f"aucune passe à reprendre pour « {self.recette.nom} »")
        if passe["statut"] not in PASSES_NON_FINIES:
            raise RefusParcours(f"la passe {passe['numero']} est {passe['statut']} : rien à reprendre")
        if passe["empreinte"] != self.empreinte and not recette_modifiee:
            raise RefusParcours(
                f"la recette a changé depuis le début de la passe {passe['numero']} : "
                f"`{self._commande_reprendre('--recette-modifiee')}` pour continuer avec la nouvelle"
            )
        if passe["statut"] == "arretee" and not maintenant and passe["fin"]:
            ecoule = (datetime.fromisoformat(self._horodatage()) - datetime.fromisoformat(passe["fin"])).total_seconds()
            if ecoule < ATTENTE_APRES_ALERTE_S:
                raise RefusParcours(
                    f"la passe {passe['numero']} s'est arrêtée sur alerte il y a {int(ecoule // 60)} min : "
                    f"attendre {ATTENTE_APRES_ALERTE_S // 3600} h, ou `{self._commande_reprendre('--maintenant')}`"
                )
        return passe

    def _avec_etat(self, controle: Callable[[Etat], object]) -> None:
        verrou = Verrou(self.dossier / "verrou")
        verrou.prendre()
        etat = Etat(self.dossier / "etat.sqlite3")
        try:
            controle(etat)
        finally:
            etat.fermer()
            verrou.liberer()

    def verifier_avant_lancer(self) -> None:
        """Tous les refus de `lancer` qui ne demandent aucune requête (recette, autorisation, tranche, verrou, passe
        non finie) : à appeler AVANT de démarrer quoi que ce soit (site du labo). Seul robots.txt, qu'il faut lire,
        est contrôlé plus tard."""
        self._controles()
        self._avec_etat(self._refus_lancer)

    def verifier_avant_reprendre(self, *, maintenant: bool = False, recette_modifiee: bool = False) -> None:
        """Idem pour `reprendre` (rien à reprendre, recette changée, attente après alerte, verrou)."""
        self._controles(reprise=True)
        self._avec_etat(lambda etat: self._refus_reprendre(etat, maintenant, recette_modifiee))

    # ── Contrôles de départ ─────────────────────────────────────────────
    def _controles(self, reprise: bool = False) -> None:
        recette = self.recette
        if not recette.autorisation and not all(_est_local(h) for h in recette.hotes):
            raise RefusParcours("autorisation obligatoire : la recette vise un site qui n'est pas local (D-30)")
        for nom in self.options.tranche:
            if nom not in recette.variables:
                raise RefusParcours(
                    f"variable inconnue : « {nom} » (déclarées : {', '.join(recette.variables) or 'aucune'})"
                )
        for type_page in self.options.sans:
            if type_page not in recette.pages:
                raise RefusParcours(
                    f"--sans : type de page inconnu « {type_page} » (connus : {', '.join(recette.pages)})"
                )
        try:
            rythme_de(recette)
        except ValueError as erreur:
            raise RefusParcours(str(erreur)) from erreur

    def _options_gardees(self) -> dict[str, Any]:
        o = self.options
        return {
            "tranche": o.tranche,
            "pages_max": o.pages_max,
            "sans": list(o.sans),
            "ignorer_robots": o.ignorer_robots,
            "tout_refaire": o.tout_refaire,
        }

    def _pages_max(self) -> int | None:
        """Le nombre de pages lues (échecs compris) où la passe s'arrête, en comptant depuis le début de la passe."""
        option = None if self.options.pages_max is None else self._decalage + self.options.pages_max
        bornes = [b for b in (option, self.recette.bornes.pages_max) if b is not None]
        return min(bornes) if bornes else None

    # ── robots.txt ──────────────────────────────────────────────────────
    def _robots_de(self, adresse: str) -> Robots:
        """robots.txt de l'origine de l'adresse, lu une fois par passe. Inaccessible = rien de permis."""
        origine = _origine(adresse)
        if origine not in self._robots:
            url = f"{origine}/robots.txt"
            agent = self.recette.robots.agent
            try:
                reponse = self.moteur.lire(url)
                robots = Robots.depuis_reponse(reponse.statut or 0, reponse.html, agent)
            except DestinationRefusee:
                raise
            except Exception:  # noqa: BLE001 — pas de réponse : rien n'est permis pour cette passe
                robots = Robots.inaccessible(agent)
            self._robots[origine] = robots
            self._robots_resume[origine] = robots.resume(url)
        return self._robots[origine]

    def _verifier_le_depart(self, reprise: bool = False) -> None:
        """Refuse avant toute page si robots.txt est inaccessible, ou (nouvelle passe) interdit le départ."""
        if self.options.ignorer_robots:
            return
        for depart in self.recette.depart:
            robots = self._robots_de(depart.url)
            if robots.etat == "inaccessible":
                raise RefusParcours(
                    f"robots.txt inaccessible (statut {robots.statut}) pour {_origine(depart.url)} : "
                    "rien n'est permis pour cette passe (`--ignorer-robots` pour passer outre)"
                )
            if not reprise and not robots.permis(_chemin_et_requete(depart.url)):
                raise RefusParcours(f"robots.txt interdit le départ : {depart.url}")

    # ── Boucle ──────────────────────────────────────────────────────────
    def _executer(self, etat: Etat, passe: int, reprise: bool) -> Bilan:
        recette = self.recette
        self._debut = self._horloge()
        self._etat = etat
        self._passe = passe
        self._sentinelle = Sentinelle(recette.hotes)
        self._sentinelle.rejouer(etat.dernieres_lues(passe, FENETRE))
        self._cadence = Cadence(rythme_de(recette), self._alea, self._horloge, self._dormir)
        self._signatures = Signatures(self.dossier / "signatures.json")
        self._decalage = etat.compteurs(passe)["lues"] if reprise else 0
        self._plafonds = recette.bornes.par_type
        self._ignores = recette.parametres_ignores
        self._sans = set(self.options.sans)
        self._hotes = set(recette.hotes)
        # Récolte incrémentale : les pages lues par les passes d'avant (depuis le dernier --tout-refaire) ne sont
        # redemandées que si la recette le dit (`revisiter`). Aucune passe d'avant, ou --tout-refaire : tout est lu.
        self._base = etat.passe_de_base()
        self._incrementale = not self.options.tout_refaire and passe > self._base
        self._premiere_page = not reprise and etat.compteurs(passe)["lues"] == 0  # la porte d'entrée n'y est que là
        self._porte: dict[str, Any] | None = None
        # Repasser la porte en cours de passe (option `porte_entree.repassages_max`) : passages tracés, heure du
        # dernier passage franchi, rafale en cours (heure de son premier passage, nombre de défis).
        porte = recette.porte_entree
        self._repasser = porte is not None and porte.repassages_max > 0
        self._repassages: list[dict[str, Any]] = []
        self._dernier_passage = ""
        self._rafale: tuple[str, int] | None = None
        if self._repasser:
            self._relire_les_passages(etat, passe)
        self._annoncer(etat, passe, reprise)
        statut, arret = "terminee", None
        try:
            statut, arret = self._boucle()
        except KeyboardInterrupt:
            if self._courante is not None:
                etat.rendre(self._courante)
            statut = "interrompue"
            self._ecran("INTERROMPU : état gardé, la passe peut être reprise.")
        etat.terminer_passe(passe, statut, arret, self._horodatage())
        if arret:
            self._evenement(etat, passe, "arret", arret)
        return self._conclure(etat, passe, statut, arret)

    def _annoncer(self, etat: Etat, passe: int, reprise: bool) -> None:
        recette = self.recette
        moteur = self.moteur.description()["nom"]
        autorisation = recette.autorisation or "aucune (hôtes locaux)"
        self._ecran(f"Recette {recette.nom} · moteur {moteur} · autorisation : {autorisation}")
        if self.options.ignorer_robots:
            agent = recette.robots.agent
            for depart in recette.depart:
                self._robots_resume[_origine(depart.url)] = {
                    "respecte": False,
                    "agent": agent,
                    "ignore_par": "--ignorer-robots",
                }
            self._ecran("ATTENTION : robots.txt IGNORÉ (--ignorer-robots), écrit dans resume.json.")
        else:
            for depart in recette.depart:
                self._robots_de(depart.url)
            for resume in self._robots_resume.values():
                regles = {
                    "absent": "aucune règle (tout est permis)",
                    "lu": f"lu, groupe {resume['groupe'] or 'aucun'} (le reste est permis)",
                    "inaccessible": "inaccessible (rien n'est permis)",
                }[resume["etat"]]
                self._ecran(f"robots.txt : {resume['adresse']} → {resume['statut']}, {regles}")
        etat.enregistrer_robots(passe, self._robots_resume)
        self._ecran(f"{'Reprise de la passe' if reprise else 'Passe'} {passe} · état : {etat.chemin}")

    def _boucle(self) -> tuple[str, dict[str, Any] | None]:
        etat, passe = self._etat, self._passe
        limite = self._pages_max()
        lues = etat.compteurs(passe)["lues"]
        while True:
            if limite is not None and lues >= limite:
                return "limitee", None
            page = etat.prochaine(passe)
            if page is None:
                return "terminee", None
            self._courante = page
            alerte, lue = self._traiter(page)
            self._courante = None
            lues += lue
            if alerte is not None:
                return "arretee", self._arret(alerte)
            if lue and lues % PAS_AFFICHAGE == 0:
                self._progression(lues)

    def _arret(self, alerte: Alerte) -> dict[str, Any]:
        return {
            "signe": alerte.signe,
            "detail": alerte.detail,
            "adresse": alerte.adresse,
            "statut": alerte.statut,
            "quand": self._horodatage(),
        }

    def _traiter(self, page: Page) -> tuple[Alerte | None, int]:
        """Lit une page. Rend (alerte éventuelle, 1 si une requête a été faite et la page notée)."""
        etat, recette = self._etat, self.recette
        quand = self._horodatage
        if _hote(page.adresse) not in self._hotes:  # défense en profondeur : jamais d'hôte hors recette
            etat.terminer_page(page, etat="interdite", decision="hors_hotes", quand=quand())
            return None, 0
        if self._incrementale and not self._a_revisiter(page):
            etat.terminer_page(page, etat="evitee", decision="deja_lue", quand=quand())
            return None, 0
        if not self.options.ignorer_robots:
            robots = self._robots_de(page.adresse)
            if not robots.permis(_chemin_et_requete(page.adresse)):
                etat.terminer_page(page, etat="interdite", decision="interdite", quand=quand())
                return None, 0
            crawl_delay = robots.crawl_delay
        else:
            crawl_delay = None
        self._cadence.attendre(crawl_delay)
        debut = self._horloge()
        try:
            reponse = self._lire(page.adresse)
        except DestinationRefusee as erreur:
            etat.rendre(page)
            return Alerte("hors_site", f"hors périmètre : {erreur}", page.adresse), 0
        except _SautRefuse as refus:
            if refus.alerte is not None:
                etat.rendre(page)  # rien n'a été lu : la page reste à faire
                return refus.alerte, 0
            etat.terminer_page(page, etat="interdite", decision="interdite", quand=quand())
            return None, 0
        except Exception as erreur:  # noqa: BLE001 — panne réseau qui dure : échec noté, la passe continue
            etat.terminer_page(page, etat="echec", decision="echec", quand=quand())
            self._evenement(etat, self._passe, "echec", {"adresse": page.adresse, "erreur": str(erreur)})
            return self._sentinelle.noter(page.type, "echec", page.adresse), 1

        if self._premiere_page:
            self._premiere_page = False
            reponse, alerte = self._porte_d_entree(page, reponse)
            if alerte is not None:
                etat.rendre(page)
                return alerte, 0
            if self._repasser and self._porte is not None and self._porte["franchie"]:
                self._dernier_passage = self._horodatage()  # l'entrée compte comme un passage de la porte
                self._rafale = (self._dernier_passage, 1)
        elif self._repasser:
            reponse, alerte = self._porte_en_cours(page, reponse)
            if alerte is not None:
                etat.rendre(page)
                return alerte, 0
        reussie = reponse.statut is not None and 200 <= reponse.statut < 300
        dans_le_motif = True
        if reussie:
            cible = chemin_et_parametres(reponse.adresse_finale, self._ignores)
            dans_le_motif = re.search(recette.pages[page.type].url, cible) is not None  # regex-recette
        alerte = self._sentinelle.examiner(
            type_page=page.type,
            adresse=page.adresse,
            statut=reponse.statut,
            adresse_finale=reponse.adresse_finale,
            dans_le_motif=dans_le_motif,
            html=reponse.html,
            entetes=reponse.entetes,
        )
        if alerte is not None:
            etat.rendre(page)  # la page n'a pas été lue : elle reste à faire
            return alerte, 0

        total_ms = lambda: (self._horloge() - debut) * 1000  # noqa: E731
        if reponse.statut in (404, 410):
            decision = "introuvable"
            etat.terminer_page(
                page, etat="faite", statut=reponse.statut, decision=decision, quand=quand(),
                duree_chargement_ms=reponse.duree_ms, duree_totale_ms=total_ms(),
            )  # fmt: skip
        elif not reussie:
            decision = "echec"
            etat.terminer_page(
                page, etat="echec", statut=reponse.statut, decision=decision, quand=quand(),
                duree_chargement_ms=reponse.duree_ms, duree_totale_ms=total_ms(),
            )  # fmt: skip
        else:
            decision = self._lire_la_page(page, reponse, total_ms)
        return self._sentinelle.noter(page.type, decision, page.adresse), 1

    def _a_revisiter(self, page: Page) -> bool:
        """Vrai si la page doit être demandée dans cette passe : jamais lue (réussie) avant, ou `revisiter` de son
        type la rend due (`toujours`, ou `<n>j` : dernière lecture plus vieille que n jours)."""
        derniere = self._etat.derniere_lecture(page.canon, self._base, self._passe)
        if derniere is None:
            return True
        regle = self.recette.pages[page.type].revisiter
        if regle == "toujours":
            return True
        if regle == "jamais":
            return False
        age = datetime.fromisoformat(self._horodatage()) - datetime.fromisoformat(derniere)
        return age.total_seconds() >= int(regle[:-1]) * 86400

    def _porte_d_entree(self, page: Page, reponse: Reponse) -> tuple[Reponse, Alerte | None]:
        """Première page de la passe, `porte_entree` déclarée : un défi qui se valide seul est attendu SANS AUCUNE
        action (ni clic, ni rechargement, ni résolution), `attendre_s` secondes au plus. Il passe : la page lue est
        celle qui est apparue, la porte est comptée à part dans `resume.json`. Il ne passe pas : alerte, arrêt.
        Un défi qui arrive plus tard dans la passe : `_porte_en_cours` si la recette permet de repasser la porte
        (`repassages_max`), sinon `Sentinelle.examiner` l'arrête sans attendre."""
        porte = self.recette.porte_entree
        defi = detecter_defi(reponse.html, reponse.entetes)
        if porte is not None and defi is None and reponse.statut in STATUTS_ALERTE:
            return self._porte_deja_franchie(reponse), None
        if porte is None or defi is None:
            return reponse, None
        courante, attendu = self._attendre_sans_action()
        if courante is not None:
            courante.duree_ms = reponse.duree_ms
            self._porte = {"defi": defi, "franchie": True, "attente_s": attendu}
            self._evenement(self._etat, self._passe, "porte_entree", self._porte)
            self._ecran(f"Porte d'entrée : défi ({defi}) validé seul après {attendu:g} s, sans action.")
            return courante, None
        self._porte = {"defi": defi, "franchie": False, "attente_s": attendu}
        self._evenement(self._etat, self._passe, "porte_entree", self._porte)
        detail = f"page de défi ({defi}) toujours là après {attendu:g} s d'attente sans action"
        return reponse, Alerte("defi", detail, page.adresse, reponse.statut)

    def _porte_deja_franchie(self, reponse: Reponse) -> Reponse:
        """Statut d'alerte à la première page, aucun défi dans le DOM lu : le défi a pu se valider PENDANT la lecture
        (le statut est alors celui de la page de défi, périmé). On regarde la page sur place, sans requête ni attente.
        État actuel en 2xx et sans défi : la porte est franchie, la page lue est l'état actuel. Sinon la réponse
        reste telle quelle et la sentinelle arrête sur le statut. La nature du défi n'est plus connue : `defi` porte
        le statut périmé (« statut 403 »)."""
        courante = self.moteur.relire()  # None : un moteur sans JavaScript, rien n'a pu changer
        if courante is None or not _page_ordinaire(courante):
            return reponse
        courante.duree_ms = reponse.duree_ms
        self._porte = {"defi": f"statut {reponse.statut}", "franchie": True, "attente_s": 0.0}
        self._evenement(self._etat, self._passe, "porte_entree", self._porte)
        self._ecran(
            f"Porte d'entrée : déjà franchie pendant la lecture (premier statut {reponse.statut}), sans action."
        )
        return courante

    def _attendre_sans_action(self, premiere: Reponse | None = None) -> tuple[Reponse | None, float]:
        """Regarde la page sur place (`premiere`, sinon une relecture), puis après chaque seconde, `attendre_s` au plus,
        SANS AUCUNE action (ni clic, ni rechargement, ni résolution). Rend la page apparue sans défi (None : le défi
        est toujours là, ou le moteur ne sait pas relire) et le temps attendu."""
        porte = self.recette.porte_entree
        assert porte is not None
        attendu = 0.0
        courante = premiere if premiere is not None else self.moteur.relire()
        while courante is not None:  # None : un moteur sans JavaScript, rien ne changera tout seul
            if detecter_defi(courante.html, courante.entetes) is None:
                return courante, attendu
            if attendu >= porte.attendre_s:
                break
            pas = min(PAS_ATTENTE_PORTE_S, porte.attendre_s - attendu)
            self._dormir(pas)
            attendu += pas
            courante = self.moteur.relire()
        return None, attendu

    # ── Repasser la porte en cours de passe (option `repassages_max`) ───
    def _porte_en_cours(self, page: Page, reponse: Reponse) -> tuple[Reponse, Alerte | None]:
        """En cours de passe, la recette permettant de repasser la porte : un défi qui revient (le laissez-passer a
        expiré) est traité comme à l'entrée, SANS AUCUNE action : attente sur place (`attendre_s`), ou statut d'alerte
        périmé d'un défi franchi pendant la lecture (aucun défi dans la page, page actuelle en 2xx et sans défi).
        Borné : au plus `repassages_max` repassages, jamais moins de `ecart_min_s` après le passage précédent
        (entrée comprise) ; les défis d'une même rafale (`RAFALE_PORTE_S`, `RAFALE_PORTE_MAX`) font un seul passage.
        Hors des bornes, ou avec un moteur sans JavaScript, la réponse est rendue telle quelle : la sentinelle arrête
        avec la même alerte que sans l'option. Un défi qui ne se lève pas : alerte, arrêt. Chaque défi vu ici est tracé
        (événement `porte_repassage`, `resume.json`)."""
        defi = detecter_defi(reponse.html, reponse.entetes)
        if defi is None and reponse.statut not in STATUTS_ALERTE:
            return reponse, None  # une page ordinaire
        courante = self.moteur.relire()
        if courante is None:
            return reponse, None  # un moteur sans JavaScript : rien ne changera tout seul
        if defi is None and not _page_ordinaire(courante):
            return reponse, None  # un vrai refus, pas une porte : la sentinelle arrête sur le statut
        porte = self.recette.porte_entree
        assert porte is not None
        vu = self._horodatage()
        rafale = self._rafale
        en_rafale = rafale is not None and _secondes(rafale[0], vu) < RAFALE_PORTE_S and rafale[1] < RAFALE_PORTE_MAX
        trace: dict[str, Any] = {
            "adresse": page.adresse,
            "rang": self._etat.compteurs(self._passe)["lues"] + 1,  # le rang de lecture qu'aura la page
            "defi": defi or f"statut {reponse.statut}",
            "franchie": False,
            "attente_s": 0.0,
            "ecart_s": _secondes(self._dernier_passage, vu),  # depuis le passage précédent, ou le début de la passe
            "rafale": en_rafale,
        }
        refus = None if en_rafale else self._refus_repassage(trace["ecart_s"])
        if refus is not None:
            trace["refus"], raison = refus
            self._tracer_repassage(trace)
            self._ecran(f"Porte : défi ({trace['defi']}) en page {trace['rang']}, pas de nouveau passage : {raison}.")
            return reponse, None
        if defi is not None:
            apparue, attendu = self._attendre_sans_action(courante)
            trace["attente_s"] = attendu
            if apparue is None:
                self._tracer_repassage(trace)
                detail = f"page de défi ({defi}) toujours là après {attendu:g} s d'attente sans action"
                return reponse, Alerte("defi", detail, page.adresse, reponse.statut)
            if not _page_ordinaire(apparue):  # le défi a disparu sur un statut d'alerte : la sentinelle en juge
                self._tracer_repassage(trace)
                return reponse, None
            courante = apparue
        courante.duree_ms = reponse.duree_ms
        trace["franchie"] = True
        self._tracer_repassage(trace)
        self._dernier_passage = self._horodatage()
        self._rafale = (rafale[0], rafale[1] + 1) if en_rafale and rafale else (self._dernier_passage, 1)
        quel = (
            "même passage que le précédent"
            if en_rafale
            else f"repassage {self._nombre_repassages()} sur {porte.repassages_max} au plus"
        )
        self._ecran(
            f"Porte repassée en page {trace['rang']} ({quel}) : défi ({trace['defi']}) levé seul après "
            f"{trace['attente_s']:g} s, sans action, {trace['ecart_s']:g} s après le passage précédent."
        )
        return courante, None

    def _refus_repassage(self, ecart: float) -> tuple[str, str] | None:
        """(borne, raison) si la porte ne doit pas être repassée : maximum atteint, ou défi revenu trop tôt."""
        porte = self.recette.porte_entree
        assert porte is not None
        faits = self._nombre_repassages()
        if faits >= porte.repassages_max:
            return "repassages_max", f"déjà {faits} repassage(s), le maximum de la recette ({porte.repassages_max})"
        if ecart < porte.ecart_min_s:
            return "ecart_min_s", (
                f"défi revenu {ecart:g} s après le passage précédent, moins que les {porte.ecart_min_s:g} s exigées"
            )
        return None

    def _tracer_repassage(self, trace: dict[str, Any]) -> None:
        self._repassages.append(trace)
        self._evenement(self._etat, self._passe, "porte_repassage", trace)

    def _nombre_repassages(self) -> int:
        """Repassages franchis ; un défi d'une rafale ne compte pas (il fait partie du passage en cours)."""
        return sum(1 for p in self._repassages if p["franchie"] and not p["rafale"])

    def _relire_les_passages(self, etat: Etat, passe: int) -> None:
        """Compte et horloge de la porte d'après les événements de la passe (une reprise les retrouve) : les défis déjà
        tracés en cours de passe, et l'heure du dernier passage franchi (entrée comprise), ou du début de la passe s'il
        n'y en a pas eu. Une reprise ouvre une session neuve : aucune rafale ne se prolonge au-delà."""
        self._dernier_passage = etat.passe(passe)["debut"]
        for evenement in etat.evenements(passe):
            if evenement["genre"] == "porte_repassage":
                self._repassages.append(evenement["detail"])
            if evenement["genre"] in ("porte_entree", "porte_repassage") and evenement["detail"].get("franchie"):
                self._dernier_passage = evenement["quand"]

    def _bilan_repassages(self) -> dict[str, Any] | None:
        """Le bloc `porte_repassages` de `resume.json` (None : la recette ne permet pas de repasser la porte)."""
        porte = self.recette.porte_entree
        if not self._repasser or porte is None:
            return None
        return {
            "repassages_max": porte.repassages_max,
            "ecart_min_s": porte.ecart_min_s,
            "nombre": self._nombre_repassages(),
            "passages": list(self._repassages),
        }

    def _lire_la_page(self, page: Page, reponse: Reponse, total_ms: Callable[[], float]) -> str:
        etat = self._etat
        resultat = extraire(
            self.recette, reponse.html, reponse.adresse_finale, page.type, self.options.tranche, self._signatures
        )
        if resultat.alertes:
            self._evenement(etat, self._passe, "extraction", {"adresse": page.adresse, "alertes": resultat.alertes})
        if not resultat.conforme:
            etat.terminer_page(
                page, etat="faite", statut=reponse.statut, decision="anormale", quand=self._horodatage(),
                duree_chargement_ms=reponse.duree_ms, duree_totale_ms=total_ms(),
            )  # fmt: skip
            return "anormale"
        if resultat.alertes:  # alertes de lecture d'une page conforme (une page anormale a déjà son compteur)
            etat.noter_alertes(self._passe, page.type, reponse.adresse_finale, resultat.alertes)
        liens: list[tuple[str, str]] = []
        hors_site, exclus = resultat.hors_site, 0  # l'extraction écarte déjà les liens hors de `hotes` et les compte
        for lien in resultat.liens:
            if _hote(lien.adresse) not in self._hotes:  # défense en profondeur : un lien passé autrement
                hors_site += 1
            elif lien.type in self._sans:
                exclus += 1
            else:
                liens.append((lien.adresse, lien.type))
        etat.terminer_page(
            page,
            etat="faite",
            statut=reponse.statut,
            decision="ok",
            quand=self._horodatage(),
            duree_chargement_ms=reponse.duree_ms,
            duree_totale_ms=total_ms(),
            enregistrements=resultat.enregistrements,
            liens=liens,
            ignores=self._ignores,
            plafonds=self._plafonds,
            hors_site=hors_site,
            exclus=exclus,
        )
        return "ok"

    def _lire(self, adresse: str) -> Reponse:
        """Lit une page. Les redirections sont suivies une à une, chacune contrôlée AVANT d'être demandée."""
        courante = adresse
        for saut in range(REDIRECTIONS_MAX + 1):
            reponse = self._lire_une(courante)
            if reponse.statut not in REDIRECTIONS or not reponse.location:
                reponse.adresse_finale = courante
                return reponse
            if saut == REDIRECTIONS_MAX:
                raise _SautRefuse(Alerte("hors_motif", f"plus de {REDIRECTIONS_MAX} redirections de suite", adresse))
            courante = self._autoriser_saut(urldefrag(urljoin(courante, reponse.location))[0], adresse)
        raise AssertionError("inatteignable")  # pragma: no cover

    def _autoriser_saut(self, cible: str, adresse: str) -> str:
        """Hôte dans la recette, puis robots.txt de l'origine ; le périmètre est vérifié par le moteur à la demande."""
        morceaux = urlsplit(cible)
        if morceaux.scheme not in ("http", "https") or _hote(cible) not in self._hotes:
            hote = _hote(cible) or cible
            raise _SautRefuse(Alerte("hors_site", f"redirection vers un autre hôte : {hote}", adresse))
        if not self.options.ignorer_robots and not self._robots_de(cible).permis(_chemin_et_requete(cible)):
            raise _SautRefuse(None)
        return cible

    def _lire_une(self, adresse: str) -> Reponse:
        """Une requête, avec 2 nouveaux essais (attente croissante) sur panne réseau, 500, 502 ou 504."""
        essai = 0
        while True:
            try:
                reponse = self.moteur.lire(adresse)
            except DestinationRefusee:
                raise
            except Exception:
                if essai >= NOUVEAUX_ESSAIS:
                    raise
            else:
                if reponse.statut not in STATUTS_A_RETENTER or essai >= NOUVEAUX_ESSAIS:
                    return reponse
            self._dormir(min(0.5 * 2**essai, 8.0) + self._alea.uniform(0, 0.3))
            essai += 1

    # ── Fin de passe ────────────────────────────────────────────────────
    def _progression(self, lues: int) -> None:
        c = self._etat.compteurs(self._passe)
        enregistrements = ", ".join(f"{n} {nom}" for nom, n in self._etat.nb_enregistrements().items()) or "0"
        alertes = self._etat.alertes_lecture(self._passe, 0)["total"]
        self._ecran(
            f"  pages lues {lues} · {enregistrements} · échecs {c['echecs']} · à faire {c['a_faire']}"
            f" · alertes de lecture {alertes}"
        )

    def _conclure(self, etat: Etat, passe: int, statut: str, arret: dict[str, Any] | None) -> Bilan:
        c = etat.compteurs(passe)
        enregistrements = etat.nb_enregistrements()
        duree = self._horloge() - self._debut
        dossier_passe = self.dossier / f"passe-{passe:03d}"
        resume = self._resume(etat, passe, statut, arret)
        resume["fichiers"] = ecrire_exports(etat, dossier_passe, passe)
        resume["csv"] = FORMAT_CSV
        self._ecrire_sorties(dossier_passe, resume)
        par_type = ", ".join(f"{n} {t}" for t, n in etat.faites_par_type(passe).items())
        lignes = ", ".join(f"{n} {nom}" for nom, n in enregistrements.items()) or "aucun enregistrement"
        if statut == "terminee":
            self._ecran(
                f"Terminée : {c['faites']} page{'s' if c['faites'] > 1 else ''} ({par_type}), {lignes}, "
                f"{c['echecs']} échec(s), "
                f"{c['relocalisations']} relocalisation(s), {c['interdites_robots']} interdite(s) par robots.txt, "
                f"durée {duree:.1f} s"
            )
        elif statut == "limitee":
            limite = self._pages_max()
            if self.recette.bornes.pages_max == limite:  # la limite est celle de la recette : seule elle la lève
                relancer = self._commande_reprendre("--recette-modifiee")
                suite = f"relever `bornes.pages_max` dans la recette, puis `{relancer}`"
            else:
                suite = (
                    f"`{self._commande_reprendre()}` (sans limite) "
                    f"ou `{self._commande_reprendre('--pages-max <N>')}` (N pages de plus)"
                )
            self._ecran(
                f"Limite atteinte ({limite} pages lues, échecs compris) : {pages_faites(c['faites'])}, {lignes}, "
                f"{c['a_faire']} à faire. Suite : {suite}"
            )
        elif statut == "arretee" and arret:
            self._ecran(f"ARRÊT : signe d'alerte ({arret['detail']}) sur {arret['adresse']} à {arret['quand']}.")
            self._ecran(f"Aucun nouvel essai. État gardé : {pages_faites(c['faites'])}, {c['a_faire']} à faire.")
            self._ecran(f"Reprise conseillée après {ATTENTE_APRES_ALERTE_S // 3600} h : {self._commande_reprendre()}")
        incr = resume["incrementale"]
        if incr["active"]:
            self._ecran(
                f"Incrémental : {incr['pages_relues']} page(s) relue(s), {incr['pages_evitees']} évitée(s), "
                f"{incr['pages_nouvelles']} page(s) neuve(s) · {incr['nouveautes']} nouveauté(s), "
                f"{incr['modifies']} modifié(s)"
            )
        for ligne in lignes_alertes(resume["alertes_lecture"]):
            self._ecran(ligne)
        self._ecran(f"Données : {dossier_passe}")
        code = {"terminee": 0, "limitee": 0, "arretee": 3}.get(statut, 1)
        return Bilan(code, statut, passe, arret, resume, dossier_passe)

    def _resume(self, etat: Etat, passe: int, statut: str, arret: dict[str, Any] | None) -> dict[str, Any]:
        ligne = etat.passe(passe)
        c = etat.compteurs(passe)
        origines = ligne["robots"] or {}
        premiere = next(iter(origines.values()), None)
        resume: dict[str, Any] = {
            "recette": self.recette.nom,
            "recette_empreinte": ligne["empreinte"],
            "passe": passe,
            "statut": statut,
            "debut": ligne["debut"],
            "fin": ligne["fin"],
            "moteur": ligne["moteur"],
            "autorisation": self.recette.autorisation or "aucune (hôtes locaux)",
            "robots": premiere,
            "tranche": self.options.tranche,
            "bornes": {"pages_max": self._pages_max(), "par_type": self.recette.bornes.par_type},
            "sans": list(self.options.sans),
            "pages": {
                "faites": c["faites"],
                "echecs": c["echecs"],
                "interdites_robots": c["interdites_robots"],
                "hors_site": c["hors_site"],
                "anormales": c["anormales"],
                "introuvables": c["introuvables"],
                "liens_exclus": c["liens_exclus"],
                "evitees": c["evitees"],
                "a_faire": c["a_faire"],
                "par_type": etat.faites_par_type(passe),
            },
            "enregistrements": etat.nb_enregistrements(),
            "incrementale": self._bilan_incremental(etat, passe, c["lues"]),
            "relocalisations": c["relocalisations"],
            "porte_entree": self._porte,
            "porte_repassages": self._bilan_repassages(),
            "alertes_lecture": etat.alertes_lecture(passe),
            "arret": arret,
        }
        if len(origines) > 1:
            resume["robots_origines"] = origines
        return resume

    def _bilan_incremental(self, etat: Etat, passe: int, lues: int) -> dict[str, Any]:
        """Ce que la passe a relu, évité, trouvé de neuf ou de changé (`active` : la passe s'appuie sur les
        précédentes ; faux à la première passe et avec --tout-refaire)."""
        relues = etat.pages_relues(passe, self._base)
        nouveautes = etat.nouveautes(passe)
        return {
            "active": self._incrementale,
            "pages_relues": relues,
            "pages_evitees": etat.compteurs(passe)["evitees"],
            "pages_nouvelles": lues - relues,
            "nouveautes": sum(1 for n in nouveautes if n["_changement"] == "nouveau"),
            "modifies": sum(1 for n in nouveautes if n["_changement"] == "modifie"),
        }

    def _ecrire_sorties(self, dossier_passe: Path, resume: Mapping[str, Any]) -> None:
        dossier_passe.mkdir(parents=True, exist_ok=True)
        (dossier_passe / "resume.json").write_text(
            json.dumps(resume, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )


@dataclass
class Essai:
    """Une page lue pour voir : rien n'est écrit, aucune file."""

    adresse: str
    type: str
    statut: int | None
    adresse_finale: str
    resultat: Resultat | None  # None : statut hors 2xx, rien n'a été lu


def type_de_page(recette: Recette, adresse: str) -> str:
    """Le premier type de page dont le motif `url` correspond à l'adresse."""
    cible = chemin_et_parametres(adresse, recette.parametres_ignores)
    for nom, page in recette.pages.items():
        if re.search(page.url, cible):  # regex-recette
            return nom
    raise RefusParcours(
        f"aucun type de page de la recette « {recette.nom} » ne correspond à {cible} (`--type` pour en imposer un)"
    )


def essayer(
    recette: Recette,
    moteur: Moteur | None,
    adresse: str,
    *,
    type_page: str | None = None,
    tranche: Mapping[str, str] | None = None,
    ignorer_robots: bool = False,
    html: str | None = None,
) -> Essai:
    """Lit UNE page (par le moteur, ou le `html` donné) et rend ce que la recette y trouve. N'écrit rien."""
    type_page = type_page or type_de_page(recette, adresse)
    if type_page not in recette.pages:
        raise RefusParcours(f"type de page inconnu : « {type_page} » (connus : {', '.join(recette.pages)})")
    if html is not None:
        return Essai(adresse, type_page, None, adresse, extraire(recette, html, adresse, type_page, tranche))
    assert moteur is not None
    moteur.ouvrir()
    try:
        if not ignorer_robots:
            url = f"{_origine(adresse)}/robots.txt"
            try:
                reponse = moteur.lire(url)
                robots = Robots.depuis_reponse(reponse.statut or 0, reponse.html, recette.robots.agent)
            except DestinationRefusee:
                raise
            except Exception:  # noqa: BLE001
                robots = Robots.inaccessible(recette.robots.agent)
            if robots.etat == "inaccessible" or not robots.permis(_chemin_et_requete(adresse)):
                raise RefusParcours(
                    f"robots.txt ne permet pas cette page : {adresse} (`--ignorer-robots` pour passer outre)"
                )
        reponse = moteur.lire(adresse)
    finally:
        moteur.fermer()
    if reponse.statut is None or not 200 <= reponse.statut < 300:
        return Essai(adresse, type_page, reponse.statut, reponse.adresse_finale, None)
    resultat = extraire(recette, reponse.html, reponse.adresse_finale, type_page, tranche)
    return Essai(adresse, type_page, reponse.statut, reponse.adresse_finale, resultat)


__all__ = [
    "Bilan",
    "Essai",
    "Moteur",
    "MoteurDriver",
    "Options",
    "Parcours",
    "RefusParcours",
    "Verrou",
    "canonique",
    "essayer",
    "lignes_alertes",
    "nettoyer",
    "pages_faites",
    "type_de_page",
]
