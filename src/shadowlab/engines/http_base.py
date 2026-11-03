"""Socle des clients HTTP : pas de JavaScript, formulaires et liens reproduits à partir du HTML reçu."""

from __future__ import annotations

import time
from abc import abstractmethod
from dataclasses import dataclass
from urllib.parse import urlencode, urljoin

from .base import Driver, FonctionIndisponible, ResultatNavigation

REDIRECTIONS_MAX = 5


@dataclass
class ReponseBrute:
    status: int
    headers: dict[str, str]
    texte: str


class DriverHttp(Driver):
    runtime = "http"
    executes_javascript = False

    def start_session(self) -> None:
        self._url = ""
        self._texte = ""
        self._document = None
        self._valeurs: dict[str, str] = {}
        self._ouvrir_client()

    @abstractmethod
    def _ouvrir_client(self) -> None: ...

    @abstractmethod
    def _envoyer(self, methode: str, url: str, donnees: dict[str, str] | None) -> ReponseBrute: ...

    def _demander(self, methode: str, url: str, donnees: dict[str, str] | None = None) -> ResultatNavigation:
        """Envoie la requête et suit les redirections à la main, chacune contrôlée par le périmètre."""
        from lxml import html as lhtml

        debut = time.perf_counter()
        for _ in range(REDIRECTIONS_MAX + 1):
            self.verifier(url)
            self.mesures.request_count += 1
            try:
                reponse = self._envoyer(methode, url, donnees)
            except Exception:
                self.mesures.error_count += 1
                raise
            if reponse.status in (301, 302, 303, 307, 308) and "location" in reponse.headers:
                url = urljoin(url, reponse.headers["location"])
                if reponse.status in (301, 302, 303):
                    methode, donnees = "GET", None
                continue
            break
        else:
            self.mesures.error_count += 1
            raise RuntimeError(f"trop de redirections ({url})")
        if reponse.status >= 400:
            self.mesures.error_count += 1
        duree = (time.perf_counter() - debut) * 1000
        self.mesures.navigation_time += duree
        self._url, self._texte, self._valeurs = url, reponse.texte, {}
        type_contenu = reponse.headers.get("content-type", "")
        self._document = lhtml.fromstring(reponse.texte) if "html" in type_contenu and reponse.texte else None
        return ResultatNavigation(reponse.status, url, duree)

    def navigate(self, url: str) -> ResultatNavigation:
        return self._demander("GET", url)

    def _trouver(self, selector: str):
        if self._document is None:
            return []
        return self._document.cssselect(selector)

    def fill(self, selector: str, value: str) -> None:
        elements = self._trouver(selector)
        if not elements or not elements[0].get("name"):
            raise LookupError(f"champ introuvable : {selector}")
        self._valeurs[elements[0].get("name")] = value

    def select(self, selector: str, value: str) -> None:
        elements = self._trouver(selector)
        if not elements or elements[0].tag != "select":
            raise LookupError(f"liste introuvable : {selector}")
        valeurs = [o.get("value", o.text_content()) for o in elements[0].cssselect("option")]
        if value not in valeurs:
            raise ValueError(f"valeur absente de la liste {selector} : {value}")
        self._valeurs[elements[0].get("name")] = value

    def click(self, selector: str) -> None:
        elements = self._trouver(selector)
        if not elements:
            raise LookupError(f"élément introuvable : {selector}")
        element = elements[0]
        if element.tag == "a" and element.get("href"):
            self.navigate(urljoin(self._url, element.get("href")))
            return
        formulaire = next((a for a in element.iterancestors() if a.tag == "form"), None)
        if formulaire is None:
            raise FonctionIndisponible(f"{self.name} : clic sans effet sans JavaScript ({selector})")
        self._soumettre(formulaire)

    def _soumettre(self, formulaire) -> None:
        valeurs: dict[str, str] = {}
        for champ in formulaire.cssselect("input[name], select[name], textarea[name]"):
            nom = champ.get("name")
            if champ.tag == "select":
                options = champ.cssselect("option")
                choisie = next((o for o in options if o.get("selected") is not None), options[0] if options else None)
                valeurs[nom] = choisie.get("value", choisie.text_content()) if choisie is not None else ""
            else:
                valeurs[nom] = champ.get("value", "")
        valeurs.update(self._valeurs)
        action = urljoin(self._url, formulaire.get("action") or self._url)
        if (formulaire.get("method") or "get").lower() == "post":
            self._demander("POST", action, valeurs)
        else:
            self._demander("GET", f"{action.split('?')[0]}?{urlencode(valeurs)}")

    def wait_for_element(self, selector: str, timeout_ms: int = 5000) -> str | None:
        elements = self._trouver(selector)  # sans JavaScript, la page ne changera pas : pas d'attente
        return elements[0].text_content() if elements else None

    def texts(self, selector: str) -> list[str]:
        return [e.text_content() for e in self._trouver(selector)]

    def content(self) -> str:
        return self._texte
