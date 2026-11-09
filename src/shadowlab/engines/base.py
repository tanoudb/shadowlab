"""Interface commune des moteurs. Chaque pilote rend des résultats normalisés.

Cycle : `open()` une fois par campagne (lance le navigateur), puis pour chaque passage
`start_session()` … `close_session()` (contexte neuf : cookies et stockage vides), enfin `close()`.
Toute URL est contrôlée par le périmètre avant d'être demandée, redirections comprises.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..perimetre import ILLIMITE, verifier_url

# Verrou réseau des navigateurs : toute destination hors liste est envoyée vers ce mandataire, une adresse
# locale fermée (port « discard »), et échoue. Il sert uniquement à bloquer, jamais à faire sortir du trafic.
MANDATAIRE_BLOQUANT = "http://127.0.0.1:9"


def liste_directe(hotes_autorises: tuple[str, ...]) -> list[str]:
    """Hôtes joints en direct (hors mandataire bloquant), au format des règles de Chrome.

    En mode illimité (``*`` dans la liste), tout passe en direct : ``["*"]`` lève le verrou réseau
    pour tous les moteurs d'un seul point. Le durcissement final retire ``*`` et le verrou revient.
    """
    if ILLIMITE in hotes_autorises:
        return ["*"]
    return [f"[{h}]" if ":" in h else h for h in hotes_autorises]


class FonctionIndisponible(RuntimeError):
    """Le moteur ne sait pas faire cette action (ex. capture d'écran pour un client HTTP)."""


class RefusProtection(RuntimeError):
    """Une page de protection de l'Arena reste affichée à la place de la page demandée."""


@dataclass
class ResultatNavigation:
    status: int | None
    url: str
    duration_ms: float


@dataclass
class MesuresSession:
    request_count: int = 0
    error_count: int = 0
    navigation_time: float = 0.0  # cumul des navigations, en ms
    details: dict[str, Any] = field(default_factory=dict)


class Driver(ABC):
    name: str = "abstrait"
    runtime: str = "inconnu"  # "navigateur" ou "http"
    executes_javascript: bool = False
    # standard : outil généraliste ; anti_detection : conçu pour échapper aux détecteurs (voir D-15)
    categorie: str = "standard"
    # Options qu'une campagne peut régler, avec leur type. Tout le reste est refusé : une option libre pourrait
    # faire suivre les redirections sans contrôle, ajouter un mandataire ou modifier l'empreinte.
    options_permises: dict[str, type | tuple[type, ...]] = {}

    def __init__(self, hotes_autorises: tuple[str, ...], options: dict[str, Any] | None = None) -> None:
        self.controler_options(options or {})
        self.hotes_autorises = hotes_autorises
        self.options = options or {}
        self.mesures = MesuresSession()

    @classmethod
    def controler_options(cls, options: dict[str, Any]) -> None:
        for cle, valeur in options.items():
            if cle not in cls.options_permises:
                permises = ", ".join(sorted(cls.options_permises)) or "aucune"
                raise ValueError(f"option inconnue pour {cls.name} : {cle} (permises : {permises})")
            attendu = cls.options_permises[cle]
            types = attendu if isinstance(attendu, tuple) else (attendu,)
            if (isinstance(valeur, bool) and bool not in types) or not isinstance(valeur, types):
                raise ValueError(f"option {cls.name}.{cle} : valeur de type {type(valeur).__name__} refusée")

    @classmethod
    def manque(cls) -> str | None:
        """Ce qui manque pour lancer ce moteur (paquet absent, navigateur à télécharger), ou None."""
        return None

    def verifier(self, url: str) -> str:
        return verifier_url(url, self.hotes_autorises)

    def configuration(self) -> dict[str, Any]:
        """Configuration effective, enregistrée avec les résultats."""
        return dict(self.options)

    @abstractmethod
    def versions(self) -> dict[str, str]: ...

    def open(self) -> None:  # noqa: B027 — rien à lancer pour un client HTTP
        """Prépare le moteur (une fois par campagne)."""

    def close(self) -> None:  # noqa: B027
        """Libère le moteur."""

    @abstractmethod
    def start_session(self) -> None: ...

    @abstractmethod
    def navigate(self, url: str) -> ResultatNavigation: ...

    @abstractmethod
    def click(self, selector: str) -> None: ...

    @abstractmethod
    def fill(self, selector: str, value: str) -> None: ...

    @abstractmethod
    def select(self, selector: str, value: str) -> None:
        """Choisit une valeur dans une liste déroulante."""

    @abstractmethod
    def wait_for_element(self, selector: str, timeout_ms: int = 5000) -> str | None:
        """Texte de l'élément s'il apparaît avant le délai, sinon None."""

    @abstractmethod
    def content(self) -> str:
        """Texte brut de la dernière réponse (HTML ou JSON)."""

    def texts(self, selector: str) -> list[str]:
        """Textes de tous les éléments qui correspondent au sélecteur."""
        raise FonctionIndisponible(f"{self.name} : texts")

    def dom(self) -> str:
        """HTML de la page telle qu'elle est maintenant (après JavaScript pour un navigateur)."""
        return self.content()

    def attendre_chargement(self) -> None:  # noqa: B027 — rien à attendre pour un client HTTP
        """Attend la fin du chargement du document courant."""

    def deplacer_souris(self, x: int, y: int) -> None:
        raise FonctionIndisponible(f"{self.name} : pas de souris")

    def defiler(self, hauteur: int) -> None:
        raise FonctionIndisponible(f"{self.name} : pas de défilement")

    def collect_metrics(self) -> MesuresSession:
        return self.mesures

    def capture_screenshot(self, path: Path) -> Path:
        raise FonctionIndisponible(f"{self.name} ne fait pas de capture d'écran")

    def export_trace(self, path: Path) -> Path:
        raise FonctionIndisponible(f"{self.name} n'exporte pas de trace")

    @abstractmethod
    def close_session(self) -> None: ...

    def scenario_natif(self, nom: str, base: str, jeton: str) -> dict[str, Any] | None:
        """Pour un moteur qui ne se pilote pas action par action (crawler, agent) : exécute lui-même le scénario et
        renvoie `{"success": bool, "details": {...}}`. None : le scénario commun s'applique."""
        return None
