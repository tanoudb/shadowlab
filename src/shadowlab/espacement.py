"""Espacement des visites d'un bras de campagne (palier 2, I7 et I9) : quand commence la visite suivante, combien de
pages.

Un « bras » est une unité de la campagne (une entrée de moteur × une protection). Chaque bras a sa propre `Cadence` :
les bras ne s'attendent jamais entre eux (la campagne les lance en parallèle, voir `Experience.concurrency`). Un bras
peut avoir son propre espacement (champ `espacement` de l'entrée), sinon il prend celui de la campagne.

- `fixe` : `minutes` entre la FIN d'une visite et le DÉBUT de la suivante (comme l'ordonnanceur de D-90) ; la première
  visite part tout de suite. Sert la soirée (§ 6.2 de `docs/recherche/identite-qui-dure-2026-11-12.md`) et les témoins
  de la course de 7 jours.
- `ordonnanceur` : l'ordonnanceur de `engines/noezia/visites.py` (rythme du § 5.4 : plage horaire, écarts log-normaux,
  pages par visite, plafonds), utilisé tel quel. Il dit aussi combien de pages lire. Sert la course de 7 jours (§ 6.3).

**L'état est durable** : la campagne donne à la cadence les visites déjà faites par le bras (lues dans la base, plus
une visite coupée en plein milieu, notée avant d'être effacée), les notes de la cadence (visites manquées, relues dans
`cadence.jsonl`) et le départ de la course (création de l'expérience). Le créneau suivant se recalcule à partir de cet
état seul : un nouvel `Ordonnanceur` par créneau, avec une graine propre au bras et au rang du créneau (visites faites,
notes), qui `rejoue` l'historique et planifie à partir du dernier événement (fin de la dernière visite, visite manquée
constatée, ou départ), pas à partir de l'heure du lancement. Après un arrêt brutal puis `shadowlab reprendre`, l'écart
depuis la dernière fin, les plafonds par heure et par jour et la plage horaire sont donc tenus, et le même créneau est
retrouvé. En mode `fixe`, la reprise garde aussi l'écart depuis la dernière fin.

**Visite manquée** (mode `ordonnanceur`) : un créneau est manqué quand, au moment où le bras peut enfin le prendre (fin
de l'attente : Mac sorti de veille, processus relancé, reprise tardive), son heure de début est dépassée de plus de
`retard_max_min` minutes (10 par défaut), ou que l'heure constatée tombe hors de la plage (dernière heure de début
comprise : fermeture moins `duree_visite_max_min`). Il n'est pas joué. On note l'heure prévue, l'heure constatée et le
motif `retard`, puis l'ordonnanceur replanifie à partir de l'heure constatée, dans la plage. Un créneau hors de la plage
n'est donc jamais joué. Second motif, `infrastructure` (la campagne le donne par `manquer`) : la chaîne de l'Arena ou le
site ne répond pas avant la visite ; elle n'est pas lancée, et le même créneau (mêmes pages) est réessayé 5 minutes plus
tard s'il reste dans la plage, sinon l'ordonnanceur replanifie. Les essais d'un même créneau portent la même clé
`creneau` : une panne de 3 heures fait UNE visite manquée et 36 essais, pas 36 visites manquées.

**Identité en alerte** (§ 5.5 : attente d'une heure ; la campagne le constate avant chaque créneau d'un bras qui a une
identité persistante) : aucune visite avant la fin de l'attente. `reporter_alerte` note une ligne `attente_alerte`
(heure prévue, fin de l'attente, `alerte_le` de l'identité) et le créneau suivant se planifie à partir de cette fin, par
les mêmes règles (mode `fixe` : jamais avant ; `ordonnanceur` : plage, plafonds, échéance). Ce n'est pas une visite
manquée. La note fait partie de l'état durable : une reprise pendant l'attente la relit et ne la réécrit pas.

**Échéance** (`jours`, mode `ordonnanceur`) : départ + `jours`. Un créneau qui commencerait à l'échéance ou après, ou un
réveil après elle, rend un créneau `echeance` : plus aucune visite ne commence, ce n'est ni un échec ni une visite
manquée (la campagne compte les répétitions restantes « non faites (échéance) »).

L'attente se fait par tranches de `PAS_S` secondes au plus, pour que l'arrêt d'urgence (`shadowlab arreter`) reste
écouté. Horloge et sommeil sont injectables (tests en temps simulé). Les heures notées portent leur décalage horaire ;
`au_cadran` les ramène au cadran de l'horloge (naïve et locale par défaut).
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .engines.noezia import visites

PAS_S = 5.0  # une pause ne dépasse jamais cela : l'arrêt est regardé entre deux pauses
RETARD_MAX_MIN = 10.0  # au-delà, un créneau pris en retard est une visite manquée
REESSAI_INFRASTRUCTURE_MIN = 5.0  # après une panne de l'Arena ou du site, le même créneau est réessayé


class Espacement(BaseModel):
    """Champ `espacement` d'une campagne, ou d'une entrée de moteur (il remplace alors celui de la campagne)."""

    model_config = ConfigDict(extra="forbid")
    mode: Literal["fixe", "ordonnanceur"]
    minutes: float | None = Field(default=None, gt=0, le=24 * 60)  # `fixe` : écart entre deux visites d'un même bras
    reglages: dict[str, Any] = Field(default_factory=dict)  # `ordonnanceur` : champs de `visites.Reglages`
    jours: float | None = Field(default=None, gt=0, le=60)  # `ordonnanceur` : durée de la course (échéance)
    retard_max_min: float = Field(default=RETARD_MAX_MIN, gt=0)  # `ordonnanceur` : seuil d'une visite manquée

    @model_validator(mode="after")
    def coherent(self) -> Espacement:
        if self.mode == "fixe":
            if self.minutes is None:
                raise ValueError("espacement fixe : `minutes` est obligatoire")
            if self.reglages:
                raise ValueError("espacement fixe : `reglages` est celui de l'ordonnanceur")
            if self.jours is not None:
                raise ValueError("espacement fixe : `jours` (échéance) est celui de l'ordonnanceur")
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
    """Une visite à faire : son heure de début et le nombre de pages au plus (None : celui de la campagne).
    `echeance` : aucune visite ne commencera plus (la course est finie)."""

    debut: datetime
    pages: int | None = None
    visite: visites.Visite | None = None
    echeance: bool = False


def au_cadran(valeur: datetime | str, reference: datetime) -> datetime:
    """`valeur` (une heure, ou son écriture ISO) ramenée au cadran de `reference` : naïve et locale si `reference` est
    naïve, sinon dans son fuseau. Une heure naïve est lue comme locale."""
    t = datetime.fromisoformat(valeur) if isinstance(valeur, str) else valeur
    if reference.tzinfo is None:
        return t.astimezone().replace(tzinfo=None) if t.tzinfo is not None else t
    return (t if t.tzinfo is not None else t.astimezone()).astimezone(reference.tzinfo)


def _ecrire(t: datetime) -> str:
    """Une heure pour les notes : avec son décalage, pour qu'elle se relise sans ambiguïté."""
    return t.astimezone().isoformat()


def dans_la_plage(reglages: visites.Reglages, t: datetime) -> bool:
    """Vrai si une visite peut commencer à `t` : entre l'ouverture et la fermeture moins `duree_visite_max_min` (la
    même règle que l'ordonnanceur, relue ici sans y toucher)."""
    ouverture, fermeture = reglages.plage
    jour = t.replace(hour=0, minute=0, second=0, microsecond=0)
    derniere = jour + timedelta(hours=fermeture, minutes=-reglages.duree_visite_max_min)
    return jour + timedelta(hours=ouverture) <= t <= derniere


@dataclass
class _Note:
    motif: str
    prevue: datetime
    constatee: datetime
    creneau: str
    essai: int
    pages: int | None
    jusqu_a: datetime | None = None  # motif `alerte` : fin de l'attente de l'identité

    @property
    def reprise(self) -> datetime:
        """D'où se replanifie le créneau suivant."""
        if self.motif == "infrastructure":
            return self.constatee + timedelta(minutes=REESSAI_INFRASTRUCTURE_MIN)
        if self.motif == "alerte" and self.jusqu_a is not None:
            return self.jusqu_a
        return self.constatee


class Cadence:
    def __init__(
        self,
        espacement: Espacement,
        *,
        horloge: Callable[[], datetime] | None = None,
        dormir: Callable[[float], None] | None = None,
        graine: object = None,
        pas_s: float = PAS_S,
        depart: datetime | None = None,
        faites: Iterable[tuple[datetime, datetime, int]] = (),
        notes: Iterable[Mapping[str, Any]] = (),
        noter: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        """`graine` : celle du bras (un créneau = une graine dérivée, recalculable) ; `depart` : départ durable de la
        course ; `faites` : visites déjà faites (début, fin, pages lues) ; `notes` : lignes de `cadence.jsonl` du bras
        (les visites manquées et les attentes d'alerte comptent dans l'état) ; `noter` : écrit une note durable."""
        self._espacement = espacement
        self._horloge = horloge or datetime.now
        self._dormir = dormir or time.sleep
        self._pas_s = pas_s
        self._graine = random.SystemRandom().randrange(2**63) if graine is None else graine
        self._noter = noter or (lambda _ligne: None)
        reference = self._horloge()
        self._depart = au_cadran(depart, reference) if depart is not None else None
        self._faites = sorted((au_cadran(d, reference), au_cadran(f, reference), int(p)) for d, f, p in faites)
        notes = list(notes)
        self._notes = [self._lire_note(n, reference) for n in notes if n.get("genre") in ("manquee", "attente_alerte")]
        self._alertes_notees = {str(n.get("alerte_le")) for n in notes if n.get("genre") == "attente_alerte"}
        self._ordonnancer = espacement.mode == "ordonnanceur"
        self._reglages = espacement.reglages_ordonnanceur() if self._ordonnancer else None
        self._echeance = (
            self._depart + timedelta(days=espacement.jours)
            if self._ordonnancer and espacement.jours is not None and self._depart is not None
            else None
        )

    @staticmethod
    def _lire_note(ligne: Mapping[str, Any], reference: datetime) -> _Note:
        prevue = au_cadran(ligne["prevue"], reference)
        alerte = ligne.get("genre") == "attente_alerte"
        return _Note(
            motif="alerte" if alerte else str(ligne.get("motif")),
            prevue=prevue,
            constatee=au_cadran(ligne["constatee"], reference),
            creneau=str(ligne.get("creneau") or _ecrire(prevue)),
            essai=int(ligne.get("essai") or 1),
            pages=ligne.get("pages"),
            jusqu_a=au_cadran(ligne["fin"], reference) if alerte else None,
        )

    @property
    def echeance(self) -> datetime | None:
        return self._echeance

    # ── Planning ────────────────────────────────────────────────────────
    def _derniere_fin(self) -> datetime | None:
        return max((fin for _, fin, _ in self._faites), default=None)

    def _note_en_cours(self) -> _Note | None:
        """La dernière note, si aucune visite n'a été faite depuis (sinon elle ne dit plus rien du créneau suivant)."""
        if not self._notes:
            return None
        note, fin = self._notes[-1], self._derniere_fin()
        return note if fin is None or note.constatee >= fin else None

    def _prochain(self) -> Creneau:
        """Le prochain créneau, recalculé à partir de l'état seul (ne dort pas, n'écrit rien)."""
        note = self._note_en_cours()
        if not self._ordonnancer:
            fin = self._derniere_fin()
            debut = self._horloge() if fin is None else fin + timedelta(minutes=self._espacement.minutes or 0)
            if note is not None:
                debut = max(debut, note.reprise)
            return Creneau(debut)
        assert self._reglages is not None
        if note is not None and note.motif == "infrastructure" and dans_la_plage(self._reglages, note.reprise):
            return Creneau(
                note.reprise, note.pages, visites.Visite(note.reprise, note.pages or self._reglages.pages_min)
            )
        reperes = [fin for _, fin, _ in self._faites] + [n.reprise for n in self._notes]
        if self._depart is not None:
            reperes.append(self._depart)
        reference = max(reperes) if reperes else self._horloge()
        alea = random.Random(f"{self._graine}:{len(self._faites)}:{len(self._notes)}")
        ordonnanceur = visites.Ordonnanceur(self._reglages, alea, horloge=lambda: reference, dormir=self._dormir)
        ordonnanceur.rejouer(self._faites)
        visite = ordonnanceur.prochaine()
        return Creneau(visite.debut, visite.pages, visite)

    def attendre(self, interrompre: Callable[[], bool] = lambda: False) -> Creneau | None:
        """Dort jusqu'à la prochaine visite et la rend ; None si `interrompre()` devient vrai pendant l'attente. Un
        créneau manqué est noté et remplacé ; à l'échéance, rend un créneau `echeance` sans attendre."""
        while True:
            creneau = self._prochain()
            if self._echeance is not None and creneau.debut >= self._echeance:
                return Creneau(creneau.debut, echeance=True)
            self._annoncer(creneau)
            while (reste := (creneau.debut - self._horloge()).total_seconds()) > 0:
                if interrompre():
                    return None
                self._dormir(min(reste, self._pas_s))
            maintenant = self._horloge()
            if self._echeance is not None and maintenant >= self._echeance:
                return Creneau(creneau.debut, echeance=True)
            if not self._ordonnancer or not self._manque(creneau, maintenant):
                return creneau
            self._ajouter_note(creneau, maintenant, "retard", "")

    def _annoncer(self, creneau: Creneau) -> None:
        """Note durable de la prochaine visite (genre `prevue` : heure prévue, heure d'écriture), écrite quand le
        créneau est choisi, AVANT l'attente : `shadowlab course etat` y lit l'heure prévue et le retard. Ni la
        cadence, ni la reprise, ni le bilan ne la comptent : ce n'est ni une visite, ni une visite manquée."""
        self._noter({"genre": "prevue", "prevue": _ecrire(creneau.debut), "ecrite": _ecrire(self._horloge())})

    def _manque(self, creneau: Creneau, maintenant: datetime) -> bool:
        assert self._reglages is not None
        retard = maintenant - creneau.debut
        return retard > timedelta(minutes=self._espacement.retard_max_min) or not dans_la_plage(
            self._reglages, maintenant
        )

    def manquer(self, creneau: Creneau, motif: str, detail: str = "") -> None:
        """La visite de `creneau` n'a pas été lancée (motif `infrastructure` : l'Arena ou le site ne répond pas) : une
        note durable, puis le créneau est réessayé `REESSAI_INFRASTRUCTURE_MIN` minutes plus tard (dans la plage)."""
        self._ajouter_note(creneau, self._horloge(), motif, detail)

    def reporter_alerte(self, fin: datetime, details: Mapping[str, Any]) -> None:
        """L'identité du bras est en alerte jusqu'à `fin` : le prochain créneau n'est pas lancé. Note durable (genre
        `attente_alerte` : heure prévue, heure constatée, fin de l'attente, puis `details`, dont `alerte_le`) ; le
        créneau suivant se planifie à partir de `fin` (`attendre` dort jusque-là au moins). Une alerte déjà notée (même
        `alerte_le`, relue à la reprise) ne l'est pas deux fois."""
        cle = str(details.get("alerte_le"))
        if cle in self._alertes_notees:
            return
        maintenant = self._horloge()
        fin = au_cadran(fin, maintenant)
        prevue = self._prochain().debut
        self._notes.append(
            _Note(motif="alerte", prevue=prevue, constatee=maintenant, creneau=_ecrire(prevue), essai=1, pages=None,
                  jusqu_a=fin)
        )  # fmt: skip
        self._alertes_notees.add(cle)
        self._noter(
            {
                "genre": "attente_alerte",
                "prevue": _ecrire(prevue),
                "constatee": _ecrire(maintenant),
                "fin": _ecrire(fin),
                **details,
            }
        )

    def _ajouter_note(self, creneau: Creneau, constatee: datetime, motif: str, detail: str) -> None:
        precedente = self._note_en_cours()
        meme = precedente is not None and precedente.motif == motif == "infrastructure"
        note = _Note(
            motif=motif,
            prevue=creneau.debut,
            constatee=constatee,
            creneau=precedente.creneau if meme and precedente else _ecrire(creneau.debut),
            essai=precedente.essai + 1 if meme and precedente else 1,
            pages=creneau.pages,
        )
        self._notes.append(note)
        self._noter(
            {
                "genre": "manquee",
                "motif": motif,
                "prevue": _ecrire(note.prevue),
                "constatee": _ecrire(note.constatee),
                "creneau": note.creneau,
                "essai": note.essai,
                "pages": note.pages,
                "detail": detail,
            }
        )

    def terminer(self, creneau: Creneau, pages_lues: int) -> None:
        """Note la fin de la visite : l'écart suivant se compte depuis maintenant."""
        self._faites.append((creneau.debut, max(self._horloge(), creneau.debut), max(0, int(pages_lues))))
        self._faites.sort()
