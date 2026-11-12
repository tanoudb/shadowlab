"""Outils des tests de récolte : pilote factice branché sur le TestClient du site du labo (sans réseau)."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit

from shadowlab.engines.base import Driver, ResultatNavigation

RACINE = Path(__file__).resolve().parents[1]
RECETTE_VITRINE = RACINE / "configs" / "recettes" / "vitrine.yaml"
GRAINE = 20261112
TAILLE = 45


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
        self.requetes_pages = 0  # demandes de pages (hors robots.txt), échecs compris
        self.robots: tuple[int, str] = (404, "")
        self.reponses: dict[str, tuple[int, str]] = {}  # fragment de chemin -> (statut, texte)
        self.redirections: dict[str, str] = {}  # fragment de chemin -> adresse absolue où l'on atterrit
        self.pannes: dict[str, int] = {}  # fragment de chemin -> nombre d'échecs réseau avant de réussir
        self.coupure_a: int | None = None  # à la n-ième demande de page : `Coupure`
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
        return [d for d in self.demandes if not d.startswith("/robots.txt")]

    def navigate(self, url):
        self.verifier(url)
        morceaux = urlsplit(url)
        chemin = morceaux.path + (f"?{morceaux.query}" if morceaux.query else "")
        if chemin.startswith("/robots.txt"):
            statut, texte = self.robots
            self.demandes.append(chemin)
            self._texte = texte
            return ResultatNavigation(statut, url, 0.1)
        self.requetes_pages += 1
        if self.pendant is not None:
            self.pendant()
        if self.coupure_a == self.requetes_pages:
            raise Coupure
        for fragment, restantes in self.pannes.items():
            if fragment in chemin and restantes > 0:
                self.pannes[fragment] = restantes - 1
                raise ConnectionError("panne simulée")
        final, statut, texte = url, None, None
        for fragment, cible in self.redirections.items():
            if fragment in chemin:
                final, statut, texte = cible, 200, "<html><body>ailleurs</body></html>"
        for fragment, (code, corps) in self.reponses.items():
            if (chemin == fragment[1:]) if fragment.startswith("=") else (fragment in chemin):
                statut, texte = code, corps
        if statut is None:
            reponse = self.client.get(chemin)
            statut, texte = reponse.status_code, reponse.text
        self.demandes.append(chemin)
        self._texte = texte
        return ResultatNavigation(statut, final, 1.0)

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
