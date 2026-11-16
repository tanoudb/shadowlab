"""Espacement des visites d'un bras de campagne (palier 2, I7) : quand commence la prochaine visite, combien de pages.

Un « bras » est une unité de la campagne (une entrée de moteur × une protection). Chaque bras a sa propre `Cadence` :
les bras ne s'attendent jamais entre eux (la campagne les lance en parallèle, voir `Experience.concurrency`).

- `fixe` : `minutes` entre la FIN d'une visite et le DÉBUT de la suivante (comme l'ordonnanceur de D-90) ; la première
  visite part tout de suite. Sert la soirée (§ 6.2 de `docs/recherche/identite-qui-dure-2026-11-12.md`).
- `ordonnanceur` : l'ordonnanceur de `engines/noezia/visites.py` (rythme du § 5.4 : plage horaire, écarts log-normaux,
  pages par visite, plafonds). Il dit aussi combien de pages lire. Sert la course de 7 jours.

L'attente se fait par tranches de `PAS_S` secondes au plus, pour que l'arrêt d'urgence (`shadowlab arreter`) reste
écouté pendant dix minutes d'attente. Horloge et sommeil sont injectables (tests en temps simulé). L'état est en
mémoire : après une reprise de campagne, la première visite repart tout de suite (limite connue).
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .engines.noezia import visites

PAS_S = 5.0  # une pause ne dépasse jamais cela : l'arrêt est regardé entre deux pauses


class Espacement(BaseModel):
    """Champ `espacement` d'une campagne."""

    model_config = ConfigDict(extra="forbid")
    mode: Literal["fixe", "ordonnanceur"]
    minutes: float | None = Field(default=None, gt=0, le=24 * 60)  # `fixe` : écart entre deux visites d'un même bras
    reglages: dict[str, Any] = Field(default_factory=dict)  # `ordonnanceur` : champs de `visites.Reglages`

    @model_validator(mode="after")
    def coherent(self) -> Espacement:
        if self.mode == "fixe":
            if self.minutes is None:
                raise ValueError("espacement fixe : `minutes` est obligatoire")
            if self.reglages:
                raise ValueError("espacement fixe : `reglages` est celui de l'ordonnanceur")
        else:
            if self.minutes is not None:
                raise ValueError("espacement ordonnanceur : `minutes` est celui du mode fixe")
            self.reglages_ordonnanceur()  # refuse un réglage inconnu ou incohérent dès la validation
        return self

    def reglages_ordonnanceur(self) -> visites.Reglages:
        champs = dict(self.reglages)
        if "plage" in champs:
            champs["plage"] = tuple(champs["plage"])
        try:
            return visites.Reglages(**champs)
        except TypeError as erreur:
            raise ValueError(f"espacement ordonnanceur : réglage inconnu ({erreur})") from erreur


@dataclass(frozen=True)
class Creneau:
    """Une visite à faire : son heure de début et le nombre de pages au plus (None : celui de la campagne)."""

    debut: datetime
    pages: int | None = None
    visite: visites.Visite | None = None  # celle de l'ordonnanceur, à lui rendre en fin de visite


class Cadence:
    def __init__(
        self,
        espacement: Espacement,
        *,
        horloge: Callable[[], datetime] | None = None,
        dormir: Callable[[float], None] | None = None,
        alea: random.Random | None = None,
        pas_s: float = PAS_S,
    ) -> None:
        self._espacement = espacement
        self._horloge = horloge or datetime.now
        self._dormir = dormir or time.sleep
        self._pas_s = pas_s
        self._fin: datetime | None = None
        self._ordonnanceur = (
            visites.Ordonnanceur(espacement.reglages_ordonnanceur(), alea, self._horloge, self._dormir)
            if espacement.mode == "ordonnanceur"
            else None
        )

    def attendre(self, interrompre: Callable[[], bool] = lambda: False) -> Creneau | None:
        """Dort jusqu'à la prochaine visite et la rend ; None si `interrompre()` devient vrai pendant l'attente."""
        if self._ordonnanceur is not None:
            visite = self._ordonnanceur.prochaine()
            debut, creneau = visite.debut, Creneau(visite.debut, visite.pages, visite)
        else:
            debut = (
                self._horloge() if self._fin is None else self._fin + timedelta(minutes=self._espacement.minutes or 0)
            )
            creneau = Creneau(debut)
        while (reste := (debut - self._horloge()).total_seconds()) > 0:
            if interrompre():
                return None
            self._dormir(min(reste, self._pas_s))
        return creneau

    def terminer(self, creneau: Creneau, pages_lues: int) -> None:
        """Note la fin de la visite : l'écart suivant se compte depuis maintenant."""
        self._fin = self._horloge()
        if self._ordonnanceur is not None and creneau.visite is not None:
            self._ordonnanceur.terminer(creneau.visite, pages_lues)
