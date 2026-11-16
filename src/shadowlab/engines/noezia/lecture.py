"""Lecture humaine d'une visite : ce que le moteur fait entre deux pages pour ne pas ressembler à une récolte.

Le problème mesuré (campagne 128, profil `endurance`) : l'Arena jugeait le moteur sur deux signaux du détecteur
`comportement`, qui s'additionnent au score composite (seuil 0,5 ; arrêt = bannissement du visiteur, D-92) :
- `duree_pages_reguliere` (0,4) : le coefficient de variation (CV) des durées de page est sous 0,2. L'Arena le relit à
  chaque requête protégée sur ce qu'elle a déjà reçu : il suffit d'un début de visite régulier (à partir de 3 relevés) ;
- `navigation_lineaire` (0,25) : au moins 4 pages (appels de données compris) toutes distinctes, sans retour en arrière.

Ce module ne fait aucune requête. Il décide, pour le parcours (`parcours.Parcours`, option `Options.lecture`) :
1. la durée de chaque page : log-normale (loi à queue lourde d'un lecteur), bornée, **tirée par blocs de trois** pour
   que
   chaque début de visite soit dispersé (tirées une à une, 15 % des visites auraient un début régulier ; par blocs,
   moins de 0,5 %, `tests/test_lecture_humaine.py`). Sous `seuil_leger_s`, la page est parcourue vite : le moteur ne
   fait
   que l'interaction légère (environ 2,8 s au lieu de 7,2 s mesurés dans un vrai Chrome) ; sinon, l'interaction
   complète, puis l'attente du reste de la durée ;
2. l'ordre de lecture : retour obligatoire à la liste après la première fiche (l'Arena voit alors un chemin répété dès
   la
   quatrième requête), puis, au hasard, d'autres retours à la liste et des fiches déjà lues revues. Ces relectures sont
   de vraies requêtes ; elles se prennent sur le budget de pages de la visite, jamais en plus.
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from dataclasses import dataclass
from statistics import NormalDist
from typing import Literal, TypeVar

T = TypeVar("T")
Action = Literal["liste", "revoir"]
BLOC = 3  # pages tirées ensemble : une dans chaque tiers de la loi, dans un ordre mélangé
_NORMALE = NormalDist()


@dataclass(frozen=True)
class LectureHumaine:
    """Réglages de la lecture. `duree_s` : (minimum, médiane, maximum) de la durée d'une page, log-normale bornée.

    Mesuré le 16/11 (vrai Chrome, hors chargement) : interaction complète 7,2 s en moyenne, légère 2,8 s. Médiane de
    4,5 s, bornes 1,5 à 30 s : durée moyenne d'une page d'environ 7,3 s (6,5 s avant, campagne 128)."""

    duree_s: tuple[float, float, float] = (1.5, 4.5, 30.0)
    seuil_leger_s: float = 5.0  # sous cette durée, la page est parcourue vite (interaction légère)
    p_retour: float = 0.2  # après une fiche (la première mise à part) : retour à la liste
    p_revoir: float = 0.08  # après une fiche : une fiche déjà lue est revue


def duree_a_quantile(bornes: tuple[float, float, float], q: float) -> float:
    """Durée log-normale (minimum, médiane, maximum) au quantile `q` (0 < q < 1), bornée. Même loi que
    `rythme.tirer_lognormal` (sigma = ln(maximum / médiane) / 2), lue à un quantile choisi au lieu d'un tirage."""
    minimum, mediane, maximum = bornes
    if maximum <= 0:
        return 0.0
    sigma = math.log(maximum / mediane) / 2 if mediane > 0 and maximum > mediane else 0.5
    valeur = mediane * math.exp(sigma * _NORMALE.inv_cdf(q))
    return min(max(valeur, minimum), maximum)


class PlanDeLecture:
    """Le plan d'UNE visite : durées de page et actions entre deux pages. Le hasard est injecté (tests, graine)."""

    def __init__(self, lecture: LectureHumaine, alea: random.Random | None = None) -> None:
        self.lecture = lecture
        self._alea = alea or random.Random()
        self._quantiles: list[float] = []

    def duree_suivante(self) -> float:
        """Durée voulue de la page suivante, en secondes (0 si les bornes sont nulles : rien à attendre)."""
        if not self._quantiles:
            bloc = [(i + self._alea.random()) / BLOC for i in range(BLOC)]
            self._alea.shuffle(bloc)
            self._quantiles = bloc
        q = min(max(self._quantiles.pop(), 1e-9), 1 - 1e-9)
        return duree_a_quantile(self.lecture.duree_s, q)

    def legere(self, duree: float) -> bool:
        """La page est-elle parcourue vite (interaction légère) ?"""
        return duree < self.lecture.seuil_leger_s

    def action(self, feuilles_lues: int, restant: int | None) -> Action | None:
        """Que faire après la fiche qu'on vient de lire ? `feuilles_lues` la compte ; `restant` : pages encore permises
        par le budget (None : sans limite). Après la première fiche, le retour à la liste est obligatoire."""
        if restant is not None and restant < 1:
            return None
        if feuilles_lues <= 1:
            return "liste"
        tirage = self._alea.random()
        if tirage < self.lecture.p_retour:
            return "liste"
        if tirage < self.lecture.p_retour + self.lecture.p_revoir:
            return "revoir"
        return None

    def feuille_a_revoir(self, lues: Sequence[T]) -> T:
        """Une fiche déjà lue, autre que la dernière."""
        return self._alea.choice(list(lues[:-1]))
