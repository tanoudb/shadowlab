"""Pont vers les moteurs isolés : le pilote réel tourne dans son propre environnement Python, dans un processus enfant.

Protocole : une ligne JSON par appel sur l'entrée standard de l'enfant, une ligne JSON par réponse. L'enfant descend du
lanceur : CPU et mémoire restent mesurés, avec en plus le petit processus Python du pont (voir `docs/architecture.md`).
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
from importlib import import_module
from pathlib import Path
from typing import Any

from ..config import RACINE
from ..perimetre import DestinationRefusee
from .base import Driver, FonctionIndisponible, MesuresSession, RefusProtection, ResultatNavigation

DOSSIER = RACINE / "moteurs_isoles"
DELAI_APPEL_S = 180
ERREURS = {
    "DestinationRefusee": DestinationRefusee,
    "FonctionIndisponible": FonctionIndisponible,
    "RefusProtection": RefusProtection,
}
# nom du moteur → (dossier de l'environnement, module:classe du pilote réel)
ISOLES = {
    "camoufox": ("camoufox", "shadowlab.engines.isoles.moteur_camoufox:DriverCamoufox"),
    "seleniumbase": ("seleniumbase", "shadowlab.engines.isoles.moteur_seleniumbase:DriverSeleniumBase"),
    "seleniumbase-uc": ("seleniumbase", "shadowlab.engines.isoles.moteur_seleniumbase:DriverSeleniumBaseUc"),
    "undetected-chromedriver": (
        "undetected-chromedriver",
        "shadowlab.engines.isoles.moteur_uc:DriverUndetectedChromedriver",
    ),
}


class DriverIsole(Driver):
    projet = ""
    cible = ""

    @classmethod
    def python(cls) -> Path:
        return DOSSIER / cls.projet / ".venv" / "bin" / "python"

    @classmethod
    def manque(cls) -> str | None:
        if cls.python().exists():
            return None
        return f"environnement absent : lancez `uv run shadowlab moteurs installer {cls.projet}`"

    def open(self) -> None:
        manque = self.manque()
        if manque:
            raise RuntimeError(manque)
        environnement = {**os.environ, "PYTHONPATH": str(RACINE / "src"), "PYTHONUNBUFFERED": "1"}
        self._enfant = subprocess.Popen(
            [str(self.python()), "-m", "shadowlab.engines.pont_serveur", self.cible],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=environnement,
            text=True,
            bufsize=1,
        )
        self._reponses: queue.Queue[str | None] = queue.Queue()
        threading.Thread(target=self._lire, daemon=True).start()
        self._appel("creer", list(self.hotes_autorises), self.options)
        self._appel("open")

    def _lire(self) -> None:
        for ligne in self._enfant.stdout:
            self._reponses.put(ligne)
        self._reponses.put(None)

    def _appel(self, methode: str, *arguments: Any) -> Any:
        enfant = getattr(self, "_enfant", None)
        if enfant is None or enfant.poll() is not None:
            raise RuntimeError(f"{self.name} : processus du moteur arrêté")
        enfant.stdin.write(json.dumps({"m": methode, "a": arguments}) + "\n")
        enfant.stdin.flush()
        try:
            ligne = self._reponses.get(timeout=DELAI_APPEL_S)
        except queue.Empty as erreur:
            enfant.kill()
            raise TimeoutError(f"{self.name} : aucune réponse à {methode} en {DELAI_APPEL_S} s") from erreur
        if ligne is None:
            raise RuntimeError(f"{self.name} : le processus du moteur s'est arrêté pendant {methode}")
        message = json.loads(ligne)
        if "e" in message:
            classe = ERREURS.get(message["e"])
            if classe is not None:
                raise classe(message["t"])
            raise RuntimeError(f"{message['e']}: {message['t']}")
        return message.get("r")

    def close(self) -> None:
        enfant = getattr(self, "_enfant", None)
        if enfant is None:
            return
        try:
            if enfant.poll() is None:
                self._appel("close")
        except (RuntimeError, TimeoutError, OSError):
            pass
        finally:
            try:
                enfant.stdin.close()
                enfant.wait(timeout=10)
            except (OSError, subprocess.TimeoutExpired):
                enfant.kill()
            self._enfant = None

    def configuration(self) -> dict[str, Any]:
        return self._appel("configuration") if getattr(self, "_enfant", None) else dict(self.options)

    def versions(self) -> dict[str, str]:
        return self._appel("versions")

    def start_session(self) -> None:
        self._appel("start_session")

    def navigate(self, url: str) -> ResultatNavigation:
        return ResultatNavigation(**self._appel("navigate", url))

    def click(self, selector: str) -> None:
        self._appel("click", selector)

    def fill(self, selector: str, value: str) -> None:
        self._appel("fill", selector, value)

    def select(self, selector: str, value: str) -> None:
        self._appel("select", selector, value)

    def wait_for_element(self, selector: str, timeout_ms: int = 5000) -> str | None:
        return self._appel("wait_for_element", selector, timeout_ms)

    def content(self) -> str:
        return self._appel("content")

    def dom(self) -> str:
        return self._appel("dom")

    def attendre_chargement(self) -> None:
        self._appel("attendre_chargement")

    def texts(self, selector: str) -> list[str]:
        return self._appel("texts", selector)

    def deplacer_souris(self, x: int, y: int) -> None:
        self._appel("deplacer_souris", x, y)

    def defiler(self, hauteur: int) -> None:
        self._appel("defiler", hauteur)

    def collect_metrics(self) -> MesuresSession:
        return MesuresSession(**self._appel("collect_metrics"))

    def capture_screenshot(self, path: Path) -> Path:
        return Path(self._appel("capture_screenshot", str(path)))

    def close_session(self) -> None:
        self._appel("close_session")

    def scenario_natif(self, nom: str, base: str, jeton: str) -> dict[str, Any] | None:
        return self._appel("scenario_natif", nom, base, jeton)


def _classe_reelle(cible: str) -> type[Driver]:
    module, _, nom = cible.partition(":")
    return getattr(import_module(module), nom)


def moteurs_isoles() -> dict[str, type[Driver]]:
    """Une classe mandataire par moteur isolé, qui reprend les caractéristiques déclarées par le pilote réel."""
    moteurs: dict[str, type[Driver]] = {}
    for nom, (projet, cible) in ISOLES.items():
        reelle = _classe_reelle(cible)
        moteurs[nom] = type(
            f"Pont{reelle.__name__}",
            (DriverIsole,),
            {
                "__doc__": reelle.__doc__,
                "name": nom,
                "projet": projet,
                "cible": cible,
                "runtime": reelle.runtime,
                "executes_javascript": reelle.executes_javascript,
                "categorie": reelle.categorie,
                "options_permises": reelle.options_permises,
            },
        )
    return moteurs


# Téléchargements à faire une fois l'environnement créé (navigateur modifié de Camoufox).
APRES_INSTALLATION = {"camoufox": ["-m", "camoufox", "fetch"]}


def installer(noms: list[str]) -> None:
    """Crée les environnements demandés (tous par défaut), avec les versions figées par leur `uv.lock`."""
    projets = noms or sorted({projet for projet, _ in ISOLES.values()})
    for projet in projets:
        dossier = DOSSIER / projet
        if not (dossier / "pyproject.toml").exists():
            raise ValueError(f"environnement inconnu : {projet}")
        subprocess.run(["uv", "sync", "--project", str(dossier)], check=True)
        if projet in APRES_INSTALLATION:
            subprocess.run([str(dossier / ".venv" / "bin" / "python"), *APRES_INSTALLATION[projet]], check=True)
