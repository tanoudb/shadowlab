"""Rythme d'une récolte : combien de temps on laisse entre deux pages (§ 5 du document de conception).

`libre` (nos sites : aucun délai), `prudent` (sites tiers) ou le détail écrit dans la recette. Le délai compte
depuis le DÉBUT de la page précédente : le temps déjà passé par le moteur est déduit, pour ne pas doubler les
pauses. Le `Crawl-delay` du robots.txt s'applique s'il est plus long que le délai tiré.
"""

from __future__ import annotations

import math
import random
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .recettes import Recette, RecetteInvalide, _est_local


@dataclass(frozen=True)
class Rythme:
    delai_s: tuple[float, float, float] = (0, 0, 0)  # minimum, médiane, maximum (tirage log-normal)
    pages_par_heure_max: int | None = None
    pause_minutes: tuple[float, float] | None = None  # durée d'une pause longue
    pause_toutes_les: tuple[int, int] | None = None  # une pause longue toutes les n à m pages


PRUDENT = Rythme((3, 8, 30), 300, (2, 5), (40, 80))
_CLES = {"delai_s", "pages_par_heure_max", "pause_longue", "comportement"}


def _faute(message: str) -> RecetteInvalide:
    return RecetteInvalide(f"recette fautive : rythme : {message}")


def _intervalle(valeur: Any, nom: str, n: int, entier: bool = False) -> tuple[Any, ...]:
    if not isinstance(valeur, list) or len(valeur) != n or any(isinstance(v, bool) for v in valeur):
        raise _faute(f"{nom} : une liste de {n} nombres")
    nombres = tuple(valeur)
    types = (int,) if entier else (int, float)
    if not all(isinstance(v, types) for v in nombres) or any(v < 0 for v in nombres):
        raise _faute(f"{nom} : des nombres{' entiers' if entier else ''} positifs ou nuls")
    if list(nombres) != sorted(nombres):
        raise _faute(f"{nom} : dans l'ordre croissant")
    return nombres


def rythme_de(recette: Recette) -> Rythme:
    """Le rythme de la recette. Par défaut : libre si tous les hôtes sont locaux, prudent sinon."""
    brut = recette.rythme
    if brut is None:
        return Rythme() if all(_est_local(h) for h in recette.hotes) else PRUDENT
    if brut == "libre":
        return Rythme()
    if brut == "prudent":
        return PRUDENT
    assert isinstance(brut, dict)
    inconnues = sorted(set(brut) - _CLES)
    if inconnues:
        raise _faute(f"clé inconnue « {inconnues[0]} » (admises : {', '.join(sorted(_CLES))})")
    delai: tuple[float, float, float] = (0, 0, 0)
    if "delai_s" in brut:
        delai = _intervalle(brut["delai_s"], "delai_s", 3)  # type: ignore[assignment]
    par_heure = brut.get("pages_par_heure_max")
    if par_heure is not None and (isinstance(par_heure, bool) or not isinstance(par_heure, int) or par_heure < 1):
        raise _faute("pages_par_heure_max : un entier d'au moins 1")
    minutes = toutes_les = None
    if "pause_longue" in brut:
        pause = brut["pause_longue"]
        if not isinstance(pause, dict) or set(pause) != {"minutes", "toutes_les"}:
            raise _faute("pause_longue : minutes et toutes_les, tous deux nécessaires")
        minutes = _intervalle(pause["minutes"], "pause_longue.minutes", 2)
        toutes_les = _intervalle(pause["toutes_les"], "pause_longue.toutes_les", 2, entier=True)
        if toutes_les[0] < 1:
            raise _faute("pause_longue.toutes_les : au moins 1 page")
    return Rythme(delai, par_heure, minutes, toutes_les)  # type: ignore[arg-type]


class Cadence:
    """Fait attendre ce qu'il faut avant chaque page. Horloge et sommeil sont injectables (tests)."""

    def __init__(
        self,
        rythme: Rythme,
        alea: random.Random | None = None,
        horloge: Callable[[], float] = time.monotonic,
        dormir: Callable[[float], None] = time.sleep,
    ) -> None:
        self.rythme = rythme
        self._alea = alea or random.Random()
        self._horloge = horloge
        self._dormir = dormir
        self._debut_precedent: float | None = None
        self._debuts: deque[float] = deque(maxlen=rythme.pages_par_heure_max or 1)
        self._depuis_pause = 0
        self._prochaine_pause = self._tirer_pause()

    def _tirer_pause(self) -> int | None:
        return None if self.rythme.pause_toutes_les is None else self._alea.randint(*self.rythme.pause_toutes_les)

    def _tirer_delai(self) -> float:
        minimum, mediane, maximum = self.rythme.delai_s
        if maximum <= 0:
            return 0.0
        sigma = math.log(maximum / mediane) / 2 if mediane > 0 and maximum > mediane else 0.5
        valeur = mediane * math.exp(sigma * self._alea.gauss(0, 1))
        return min(max(valeur, minimum), maximum)

    def attendre(self, crawl_delay: float | None = None) -> float:
        """Dort le temps voulu avant la prochaine page ; rend la durée dormie."""
        maintenant = self._horloge()
        attente = 0.0
        if self._debut_precedent is not None:
            delai = max(self._tirer_delai(), crawl_delay or 0.0)
            attente = max(0.0, delai - (maintenant - self._debut_precedent))
            plafond = self.rythme.pages_par_heure_max
            if plafond and len(self._debuts) >= plafond:
                attente = max(attente, 3600 - (maintenant - self._debuts[0]))
        if self._prochaine_pause is not None and self._depuis_pause >= self._prochaine_pause:
            attente += self._alea.uniform(*self.rythme.pause_minutes) * 60  # type: ignore[misc]
            self._depuis_pause = 0
            self._prochaine_pause = self._tirer_pause()
        if attente > 0:
            self._dormir(attente)
        self._debut_precedent = self._horloge()
        if self.rythme.pages_par_heure_max:
            self._debuts.append(self._debut_precedent)
        self._depuis_pause += 1
        return attente
