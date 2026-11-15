"""Ordonnanceur des visites d'un visiteur régulier (§ 5.4 de `docs/recherche/identite-qui-dure-2026-11-12.md`).

Une seule source pour la campagne et la commande de récolte : elle dit QUAND la prochaine visite commence et COMBIEN
de pages elle lit au plus. Ce qui se passe DANS la visite reste le rythme `prudent` de `rythme.py`
(`Reglages.rythme_visite`) ; l'ordonnanceur ne lit aucune page et ne fait aucune requête.

Valeurs de départ (§ 5.4), des estimations de ce qu'un humain fait, pas des valeurs réglées sur l'Arena :
- plage horaire 8 h à 23 h, heure du poste (l'horloge donne l'heure locale) ;
- écart entre deux visites de 45 à 180 min (tirage log-normal, médiane 90 min), compté de la FIN de la visite
  précédente au début de la suivante ; jamais à heure fixe ; la première visite du matin est décalée de 0 à 90 min ;
- 5 à 40 pages par visite, médiane 15 ;
- plafonds : 120 pages sur toute heure glissante (une visite finie dans l'heure précédente compte en entier),
  200 par jour. Un plafond réduit le nombre de pages de la visite, ou
  repousse la visite (à la fin de l'heure, au lendemain) s'il en reste moins que le minimum.
Une visite doit finir dans la plage : la dernière heure de début est la fin de plage moins `duree_visite_max_min`
(30 min : 40 pages au rythme `prudent`, pauses comprises). L'ordonnanceur ne coupe pas une visite qui déborde.

L'horloge et le sommeil sont injectables (tests en temps simulé). L'état est en mémoire : après une coupure,
`rejouer` reprend les visites déjà faites (la campagne et la récolte les lisent dans `visites.jsonl`).
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from . import rythme

RYTHME_VISITE = rythme.PRUDENT
OUVERTURE_DECALAGE_MAX_MIN = 90  # la première visite du matin n'est pas à 8 h pile


@dataclass(frozen=True)
class Reglages:
    plage: tuple[int, int] = (8, 23)  # heures du poste : ouverture, fermeture
    ecart_min_min: float = 45
    ecart_med_min: float = 90
    ecart_max_min: float = 180
    pages_min: int = 5
    pages_med: int = 15
    pages_max: int = 40
    pages_par_heure: int = 120
    pages_par_jour: int = 200
    duree_visite_max_min: float = 30
    rythme_visite: rythme.Rythme = field(default=RYTHME_VISITE)

    def __post_init__(self) -> None:
        ouverture, fermeture = self.plage
        if not (0 <= ouverture < fermeture <= 24):
            raise ValueError(f"plage : deux heures croissantes entre 0 et 24, reçu {self.plage}")
        if not (0 < self.ecart_min_min <= self.ecart_med_min <= self.ecart_max_min):
            raise ValueError("écart entre visites : 0 < minimum <= médiane <= maximum")
        if not (1 <= self.pages_min <= self.pages_med <= self.pages_max):
            raise ValueError("pages par visite : 1 <= minimum <= médiane <= maximum")
        if self.pages_par_heure < self.pages_min or self.pages_par_jour < self.pages_min:
            raise ValueError("les plafonds par heure et par jour doivent laisser au moins une visite minimale")
        if not 0 <= self.duree_visite_max_min < (fermeture - ouverture) * 60:
            raise ValueError("duree_visite_max_min : moins que la plage")


@dataclass(frozen=True)
class Visite:
    debut: datetime
    pages: int  # pages lues au plus


class Ordonnanceur:
    def __init__(
        self,
        reglages: Reglages | None = None,
        alea: random.Random | None = None,
        horloge: Callable[[], datetime] = datetime.now,
        dormir: Callable[[float], None] = time.sleep,
    ) -> None:
        self.reglages = reglages or Reglages()
        self._alea = alea or random.Random()
        self._horloge = horloge
        self._dormir = dormir
        self._faites: list[tuple[datetime, datetime, int]] = []  # (début, fin, pages lues)
        self._prevue: Visite | None = None

    # ── Historique ──────────────────────────────────────────────────────
    def rejouer(self, visites: Iterable[tuple[datetime, datetime, int]]) -> None:
        """Reprend les visites déjà faites (début, fin, pages lues) : les plafonds et l'écart en tiennent compte."""
        self._faites = sorted(visites)
        self._prevue = None

    def terminer(self, visite: Visite, pages_lues: int) -> None:
        """Note la visite finie maintenant : le prochain écart se compte depuis cet instant."""
        self._faites.append((visite.debut, max(self._horloge(), visite.debut), max(0, pages_lues)))
        self._prevue = None

    # ── Planning ────────────────────────────────────────────────────────
    def prochaine(self) -> Visite:
        """La prochaine visite (la même tant qu'aucune visite n'est terminée). Ne dort pas."""
        if self._prevue is None:
            self._prevue = self._planifier()
        return self._prevue

    def attendre_prochaine(self) -> Visite:
        """Dort jusqu'à l'heure de la prochaine visite et la rend."""
        visite = self.prochaine()
        attente = (visite.debut - self._horloge()).total_seconds()
        if attente > 0:
            self._dormir(attente)
        return visite

    def _planifier(self) -> Visite:
        r = self.reglages
        maintenant = self._horloge()
        debut = maintenant
        if self._faites:
            ecart = rythme.tirer_lognormal(
                (r.ecart_min_min * 60, r.ecart_med_min * 60, r.ecart_max_min * 60), self._alea
            )
            debut = max(maintenant, max(fin for _, fin, _ in self._faites) + timedelta(seconds=ecart))
        pages = round(rythme.tirer_lognormal((r.pages_min, r.pages_med, r.pages_max), self._alea))
        pages = min(max(pages, r.pages_min), r.pages_max)
        while True:
            debut = self._dans_la_plage(debut)
            reste_jour = r.pages_par_jour - sum(p for d, _, p in self._faites if d.date() == debut.date())
            if reste_jour < r.pages_min:
                debut = self._ouverture(debut.date() + timedelta(days=1))
                continue
            # Toute visite dont la fin est dans l'heure qui précède : ses pages peuvent tomber dans la même heure
            # glissante que celles-ci (prudent : on compte la visite entière).
            fenetre = [(fin, p) for _, fin, p in self._faites if fin > debut - timedelta(hours=1)]
            reste_heure = r.pages_par_heure - sum(p for _, p in fenetre)
            if reste_heure < r.pages_min:
                debut = min(f for f, _ in fenetre) + timedelta(hours=1, seconds=1)
                continue
            return Visite(debut, min(pages, reste_jour, reste_heure))

    def _ouverture(self, jour) -> datetime:
        """Ouverture de la plage ce jour-là, plus un décalage tiré (jamais 8 h pile)."""
        base = datetime.combine(jour, datetime.min.time(), tzinfo=self._horloge().tzinfo)
        decalage = self._alea.uniform(0, OUVERTURE_DECALAGE_MAX_MIN * 60)
        return base + timedelta(hours=self.reglages.plage[0], seconds=decalage)

    def _dans_la_plage(self, t: datetime) -> datetime:
        """`t` s'il tombe dans la plage (avec la marge de fin), sinon la prochaine ouverture."""
        ouverture, fermeture = self.reglages.plage
        jour = t.replace(hour=0, minute=0, second=0, microsecond=0)
        if t < jour + timedelta(hours=ouverture):
            return self._ouverture(t.date())
        if t > jour + timedelta(hours=fermeture, minutes=-self.reglages.duree_visite_max_min):
            return self._ouverture(t.date() + timedelta(days=1))
        return t
