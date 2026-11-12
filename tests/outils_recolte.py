"""Outils des tests de récolte : pilote factice branché sur le TestClient du site du labo (sans réseau)."""

from __future__ import annotations

import json
import random
from pathlib import Path
from urllib.parse import urlsplit

from shadowlab import notation
from shadowlab.engines.base import Driver, ResultatNavigation
from shadowlab.engines.noezia.parcours import MoteurDriver, Options, Parcours
from shadowlab.engines.noezia.recettes import lire_texte

RACINE = Path(__file__).resolve().parents[1]
RECETTE_VITRINE = RACINE / "configs" / "recettes" / "vitrine.yaml"
GRAINE = 20261112
TAILLE = 45
QUAND = "2026-11-12T10:00:00+00:00"


class Coupure(BaseException):
    """Simule une coupure franche (panne, Mac qui s'endort) : le code testé ne doit pas pouvoir la rattraper."""


class PiloteFactice(Driver):
    """Pilote minimal : lit les pages du site en mémoire et sait jouer les incidents (robots.txt, statuts, coupure)."""

    name = "factice"
    runtime = "http"

    def __init__(self, client, hotes: tuple[str, ...] = ("*",)):
        super().__init__(hotes)
        self.client = client
        self.demandes: list[str] = []  # chemins dont une réponse a été rendue, robots.txt compris
        self.urls: list[str] = []  # toutes les adresses réellement demandées (hôte compris), robots.txt compris
        self.location: str | None = None  # en-tête Location de la dernière réponse 3xx (le pilote ne suit rien)
        self.statuts: list[int] = []  # statut de chaque réponse de `demandes`
        self.requetes_pages = 0  # demandes de pages (hors robots.txt), échecs compris
        self.robots: tuple[int, str] = (404, "")
        self.reponses: dict[str, tuple[int, str]] = {}  # fragment de chemin -> (statut, texte)
        self.redirections: dict[str, str] = {}  # fragment de chemin -> adresse absolue où l'on atterrit
        self.pannes: dict[str, int] = {}  # fragment de chemin -> nombre d'échecs réseau avant de réussir
        self.coupure_a: int | None = None  # à la n-ième demande de page : `Coupure`
        self.interruption_a: int | None = None  # à la n-ième demande de page : Ctrl-C (`KeyboardInterrupt`)
        self.pendant = None  # appelé à chaque demande de page (ex. lancer une seconde passe)
        self.ouvert = False
        self.sessions = 0
        self._texte = ""

    def versions(self):
        return {"factice": "0"}

    def open(self):
        self.ouvert = True

    def close(self):
        self.ouvert = False

    def start_session(self):
        self.sessions += 1

    def close_session(self):
        pass

    def pages_lues(self) -> list[str]:
        """Pages dont le contenu a été rendu (statut 2xx) ; une page refusée (403, 429…) n'est pas « lue »."""
        return [
            d
            for d, statut in zip(self.demandes, self.statuts, strict=True)
            if statut < 300 and not d.startswith("/robots.txt")
        ]

    def navigate(self, url):
        self.verifier(url)
        self.urls.append(url)
        self.location = None
        morceaux = urlsplit(url)
        chemin = morceaux.path + (f"?{morceaux.query}" if morceaux.query else "")
        if chemin.startswith("/robots.txt"):
            statut, texte = self.robots
            self.demandes.append(chemin)
            self.statuts.append(statut)
            self._texte = texte
            return ResultatNavigation(statut, url, 0.1)
        self.requetes_pages += 1
        if self.pendant is not None:
            self.pendant()
        if self.coupure_a == self.requetes_pages:
            raise Coupure
        if self.interruption_a == self.requetes_pages:
            raise KeyboardInterrupt
        for fragment, restantes in self.pannes.items():
            if fragment in chemin and restantes > 0:
                self.pannes[fragment] = restantes - 1
                raise ConnectionError("panne simulée")
        statut, texte = None, None
        for fragment, cible in self.redirections.items():
            if fragment in chemin:  # comme un vrai pilote réglé pour ne rien suivre : 302 et Location
                self.location = cible
                statut, texte = 302, ""
        for fragment, (code, corps) in self.reponses.items():
            if statut == 302:
                break
            if (chemin == fragment[1:]) if fragment.startswith("=") else (fragment in chemin):
                statut, texte = code, corps
        if statut is None:
            reponse = self.client.get(chemin)
            statut, texte = reponse.status_code, reponse.text
        self.demandes.append(chemin)
        self.statuts.append(statut)
        self._texte = texte
        return ResultatNavigation(statut, url, 1.0)

    def content(self):
        return self._texte

    def click(self, selector):
        raise NotImplementedError

    def fill(self, selector, value):
        raise NotImplementedError

    def select(self, selector, value):
        raise NotImplementedError

    def wait_for_element(self, selector, timeout_ms=5000):
        raise NotImplementedError


def creer_client(monkeypatch, taille: int = TAILLE):
    """`TestClient` du site du labo, vitrine à `taille` annonces (graine fixe)."""
    from fastapi.testclient import TestClient

    from shadowlab.config import charger
    from shadowlab.site.app import creer_app

    monkeypatch.setenv("SHADOWLAB_VITRINE_TAILLE", str(taille))
    monkeypatch.setenv("SHADOWLAB_VITRINE_GRAINE", str(GRAINE))
    return TestClient(creer_app(charger()), base_url="http://127.0.0.1")


class Horloge:
    """Horloge factice : `dormir` fait avancer le temps sans attendre."""

    def __init__(self):
        self.t = 1000.0
        self.pauses: list[float] = []

    def __call__(self):
        return self.t

    def dormir(self, secondes):
        self.pauses.append(secondes)
        self.t += secondes


def fabriquer(dossier, pilote, recette=None, texte=None, options=None, horloge=None, horodatage=None):
    """Un `Parcours` sur le pilote factice, horloge factice, gigue déterministe ; `ecran` est recueilli."""
    horloge = horloge or Horloge()
    texte = texte if texte is not None else RECETTE_VITRINE.read_text(encoding="utf-8")
    recette = recette or lire_texte(texte)
    ecran: list[str] = []
    p = Parcours(
        recette,
        texte,
        str(RECETTE_VITRINE),
        MoteurDriver(pilote, "http"),
        dossier,
        options or Options(),
        ecran=ecran.append,
        horloge=horloge,
        dormir=horloge.dormir,
        alea=random.Random(1),
        horodatage=horodatage or (lambda: QUAND),
    )
    p.sortie_ecran = ecran
    p.horloge_factice = horloge
    return p


def chemin_sans_jeton(chemin: str) -> str:
    return notation._adresse(chemin)


def lu(dossier, passe=1):
    return json.loads((dossier / f"passe-{passe:03d}" / "resume.json").read_text(encoding="utf-8"))
