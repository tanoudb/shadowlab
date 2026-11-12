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
import os
import random
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit

from ...perimetre import DestinationRefusee
from ..base import Driver
from .etat import Etat, Page, canonique
from .extraction import Signatures
from .recettes import Recette, _est_local, chemin_et_parametres, extraire
from .robots import Robots
from .rythme import Cadence, rythme_de
from .sentinelle import FENETRE, Alerte, Sentinelle

NOUVEAUX_ESSAIS = 2  # sur panne réseau, 500, 502, 504 (après le premier essai), attente croissante
STATUTS_A_RETENTER = frozenset({500, 502, 504})
ATTENTE_APRES_ALERTE_S = 3600  # « reprendre » conseille d'attendre 1 h (choix du document, § 5)
PAS_AFFICHAGE = 25
PASSES_NON_FINIES = ("en_cours", "arretee", "interrompue", "limitee")


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


class Moteur(Protocol):
    """Ce que le parcours demande à un moteur : ouvrir, lire une adresse, fermer, se décrire."""

    def ouvrir(self) -> None: ...

    def fermer(self) -> None: ...

    def lire(self, adresse: str) -> Reponse: ...

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
        return Reponse(navigation.status, navigation.url, self.driver.dom(), navigation.duration_ms)

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


def _hote(adresse: str) -> str:
    return (urlsplit(adresse).hostname or "").lower()


def _origine(adresse: str) -> str:
    morceaux = urlsplit(adresse)
    return f"{morceaux.scheme.lower()}://{morceaux.netloc.lower()}"


def _chemin_et_requete(adresse: str) -> str:
    morceaux = urlsplit(adresse)
    return (morceaux.path or "/") + (f"?{morceaux.query}" if morceaux.query else "")


def _maintenant() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


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
    ) -> None:
        self.recette = recette
        self.texte_recette = texte_recette
        self.chemin_recette = chemin_recette
        self.empreinte = _empreinte(texte_recette)
        self.moteur = moteur
        self.dossier = dossier
        self.options = options or Options()
        self._ecran = ecran
        self._horloge = horloge
        self._dormir = dormir
        self._alea = alea or random.Random()
        self._horodatage = horodatage
        self._robots: dict[str, Robots] = {}
        self._robots_resume: dict[str, dict[str, Any]] = {}
        self._courante: Page | None = None

    # ── Entrées ─────────────────────────────────────────────────────────
    def lancer(self) -> Bilan:
        """Nouvelle passe. Refuse (`RefusParcours`) avant toute page si quelque chose ne va pas."""
        self._controles()
        verrou = Verrou(self.dossier / "verrou")
        verrou.prendre()
        etat = Etat(self.dossier / "etat.sqlite3")
        try:
            derniere = etat.derniere_passe()
            if derniere and derniere["statut"] in PASSES_NON_FINIES and not self.options.tout_refaire:
                raise RefusParcours(
                    f"la passe {derniere['numero']} n'est pas finie ({derniere['statut']}) : "
                    f"`recolte reprendre {self.recette.nom}`, ou `lancer … --tout-refaire` pour tout recommencer"
                )
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
            etat.evenement(passe, "debut", {"moteur": self.moteur.description()["nom"]}, self._horodatage())
            return self._executer(etat, passe, reprise=False)
        finally:
            etat.fermer()
            self.moteur.fermer()
            verrou.liberer()

    def reprendre(
        self, *, maintenant: bool = False, recette_modifiee: bool = False, pages_max: int | None = None
    ) -> Bilan:
        """Continue la dernière passe (coupée, arrêtée ou limitée), avec ses options de départ."""
        self._controles(reprise=True)
        verrou = Verrou(self.dossier / "verrou")
        verrou.prendre()
        etat = Etat(self.dossier / "etat.sqlite3")
        try:
            passe = etat.derniere_passe()
            if passe is None:
                raise RefusParcours(f"aucune passe à reprendre pour « {self.recette.nom} »")
            if passe["statut"] not in PASSES_NON_FINIES:
                raise RefusParcours(f"la passe {passe['numero']} est {passe['statut']} : rien à reprendre")
            if passe["empreinte"] != self.empreinte and not recette_modifiee:
                raise RefusParcours(
                    f"la recette a changé depuis le début de la passe {passe['numero']} : "
                    "`reprendre … --recette-modifiee` pour continuer avec la nouvelle"
                )
            if passe["statut"] == "arretee" and not maintenant and passe["fin"]:
                ecoule = (
                    datetime.fromisoformat(self._horodatage()) - datetime.fromisoformat(passe["fin"])
                ).total_seconds()
                if ecoule < ATTENTE_APRES_ALERTE_S:
                    raise RefusParcours(
                        f"la passe {passe['numero']} s'est arrêtée sur alerte il y a {int(ecoule // 60)} min : "
                        f"attendre {ATTENTE_APRES_ALERTE_S // 3600} h, ou `reprendre … --maintenant`"
                    )
            gardees = passe["options"]
            self.options = Options(
                tranche=dict(gardees.get("tranche", {})),
                pages_max=pages_max if pages_max is not None else gardees.get("pages_max"),
                sans=tuple(gardees.get("sans", ())),
                ignorer_robots=bool(gardees.get("ignorer_robots", False)),
            )
            self._controles(reprise=True)
            self.moteur.ouvrir()
            self._verifier_le_depart(reprise=True)
            remises = etat.reprendre_passe(passe["numero"])
            if recette_modifiee and passe["empreinte"] != self.empreinte:
                etat.changer_recette(passe["numero"], self.empreinte, self.texte_recette)
            etat.evenement(passe["numero"], "reprise", {"pages_remises_en_file": remises}, self._horodatage())
            return self._executer(etat, passe["numero"], reprise=True)
        finally:
            etat.fermer()
            self.moteur.fermer()
            verrou.liberer()

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
        }

    def _pages_max(self) -> int | None:
        bornes = [b for b in (self.options.pages_max, self.recette.bornes.pages_max) if b is not None]
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
        self._plafonds = recette.bornes.par_type
        self._ignores = recette.parametres_ignores
        self._sans = set(self.options.sans)
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
            etat.evenement(passe, "arret", arret, self._horodatage())
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
        except Exception as erreur:  # noqa: BLE001 — panne réseau qui dure : échec noté, la passe continue
            etat.terminer_page(page, etat="echec", decision="echec", quand=quand())
            etat.evenement(self._passe, "echec", {"adresse": page.adresse, "erreur": str(erreur)}, quand())
            return self._sentinelle.noter(page.type, "echec", page.adresse), 1

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

    def _lire_la_page(self, page: Page, reponse: Reponse, total_ms: Callable[[], float]) -> str:
        etat = self._etat
        resultat = extraire(
            self.recette, reponse.html, reponse.adresse_finale, page.type, self.options.tranche, self._signatures
        )
        if resultat.alertes:
            etat.evenement(
                self._passe, "extraction", {"adresse": page.adresse, "alertes": resultat.alertes}, self._horodatage()
            )
        if not resultat.conforme:
            etat.terminer_page(
                page, etat="faite", statut=reponse.statut, decision="anormale", quand=self._horodatage(),
                duree_chargement_ms=reponse.duree_ms, duree_totale_ms=total_ms(),
            )  # fmt: skip
            return "anormale"
        hotes = set(self.recette.hotes)
        liens: list[tuple[str, str]] = []
        hors_site = exclus = 0
        for lien in resultat.liens:
            if _hote(lien.adresse) not in hotes:
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
        """Une lecture, avec 2 nouveaux essais (attente croissante) sur panne réseau, 500, 502 ou 504."""
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
        self._ecran(f"  pages lues {lues} · {enregistrements} · échecs {c['echecs']} · à faire {c['a_faire']}")

    def _conclure(self, etat: Etat, passe: int, statut: str, arret: dict[str, Any] | None) -> Bilan:
        c = etat.compteurs(passe)
        enregistrements = etat.nb_enregistrements()
        duree = self._horloge() - self._debut
        dossier_passe = self.dossier / f"passe-{passe:03d}"
        resume = self._resume(etat, passe, statut, arret)
        self._ecrire_sorties(etat, passe, dossier_passe, resume)
        par_type = ", ".join(f"{n} {t}" for t, n in etat.faites_par_type(passe).items())
        lignes = ", ".join(f"{n} {nom}" for nom, n in enregistrements.items()) or "aucun enregistrement"
        if statut == "terminee":
            self._ecran(
                f"Terminée : {c['faites']} pages ({par_type}), {lignes}, {c['echecs']} échec(s), "
                f"{c['relocalisations']} relocalisation(s), {c['interdites_robots']} interdite(s) par robots.txt, "
                f"durée {duree:.1f} s"
            )
        elif statut == "limitee":
            self._ecran(
                f"Limite atteinte ({self._pages_max()} pages lues) : {c['faites']} pages faites, {lignes}, "
                f"{c['a_faire']} à faire. Suite : uv run shadowlab recolte reprendre {self.recette.nom} --pages-max <N>"
            )
        elif statut == "arretee" and arret:
            self._ecran(f"ARRÊT : signe d'alerte ({arret['detail']}) sur {arret['adresse']} à {arret['quand']}.")
            self._ecran(f"Aucun nouvel essai. État gardé : {c['faites']} pages faites, {c['a_faire']} à faire.")
            self._ecran(
                f"Reprise conseillée après {ATTENTE_APRES_ALERTE_S // 3600} h : "
                f"uv run shadowlab recolte reprendre {self.recette.nom}"
            )
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
                "a_faire": c["a_faire"],
                "par_type": etat.faites_par_type(passe),
            },
            "enregistrements": etat.nb_enregistrements(),
            "relocalisations": c["relocalisations"],
            "arret": arret,
        }
        if len(origines) > 1:
            resume["robots_origines"] = origines
        return resume

    def _ecrire_sorties(self, etat: Etat, passe: int, dossier_passe: Path, resume: Mapping[str, Any]) -> None:
        dossier_passe.mkdir(parents=True, exist_ok=True)
        (dossier_passe / "resume.json").write_text(
            json.dumps(resume, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )


__all__ = ["Bilan", "Moteur", "MoteurDriver", "Options", "Parcours", "RefusParcours", "Verrou", "canonique"]
