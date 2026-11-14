"""Relevé enrichi du site public (D-76) : la nature d'envoi `trace` de `public/static/releve.js`, validée strictement.

Une trace n'est faite que de nombres entiers : quelques nombres seuls, le cadre (sept nombres) et des listes plates
de lignes de largeur fixe. Avant toute écriture, `valider` exige exactement les clés connues, des entiers (jamais un
booléen, un nombre à virgule, `NaN` ou l'infini), des listes de longueur bornée et des valeurs dans des bornes
plausibles ; la sorte d'élément visé n'a que les cinq valeurs de `SORTES`. Tout le reste est refusé : un client
modifié ne peut pas faire stocker de texte. Ce qui est écrit est reconstruit à partir des seules clés du schéma.

Les clés, la largeur des lignes et le nombre de lignes par envoi suivent la table `CLES` du script ; la notice les
décrit une à une (`textes.DONNEES_TRACE`). Un test vérifie que les trois disent la même chose.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

VERSION = 1  # version du format, celle de `VERSION` dans releve.js
ENVOIS_PAR_PAGE = 60  # `ENVOIS_PAR_PAGE` de releve.js : le numéro de morceau va de 0 à 59
# La balise qui charge le script pendant une session (bandeau de la vitrine, gabarit du réseau social).
BALISE = '<script src="/public/static/releve.js" defer></script>'
# Seules pages qui chargent le script : celles des deux sites de démonstration (chemin, jamais de texte libre).
PAGE = re.compile(r"/lab/(?:social|vitrine)(?:/[A-Za-z0-9._~%-]+)*")
TAILLE_MAX_PAGE = 200
# Sorte de l'élément visé par un clic, par code (liste fermée).
SORTES = ("autre", "lien", "bouton", "image", "zone de texte")

Bornes = tuple[int, int]
INSTANT: Bornes = (0, 3 * 3600 * 1000)  # millisecondes depuis l'ouverture de la page (une session dure 2 h au plus)
POSITION: Bornes = (-100_000, 100_000)  # pixels dans la fenêtre, ou différence de deux positions
DIMENSION: Bornes = (0, 100_000)  # largeur ou hauteur de la fenêtre
PAGE_PX: Bornes = (0, 1_000_000)  # largeur ou hauteur de la page
DEFILEMENT: Bornes = (-1_000_000, 1_000_000)  # position verticale de défilement, ou différence de deux positions
PAS: Bornes = (-100_000, 100_000)  # pas de molette cumulés sur un trentième de seconde
OUI_NON: Bornes = (0, 1)


def _entier(valeur: object, bornes: Bornes) -> bool:
    """Un entier JSON dans ses bornes. `type(...) is int` écarte les booléens et les nombres à virgule."""
    return type(valeur) is int and bornes[0] <= valeur <= bornes[1]


@dataclass(frozen=True)
class Nombre:
    bornes: Bornes

    def accepte(self, valeur: object) -> bool:
        return _entier(valeur, self.bornes)


@dataclass(frozen=True)
class Uplet:
    """Une liste de longueur fixe, une borne par position."""

    colonnes: tuple[Bornes, ...]

    def accepte(self, valeur: object) -> bool:
        return (
            type(valeur) is list
            and len(valeur) == len(self.colonnes)
            and all(_entier(n, b) for n, b in zip(valeur, self.colonnes, strict=True))
        )


@dataclass(frozen=True)
class Liste:
    """Liste plate de lignes de largeur fixe (une borne par colonne), `lignes` lignes au plus par envoi."""

    lignes: int
    colonnes: tuple[Bornes, ...]

    @property
    def largeur(self) -> int:
        return len(self.colonnes)

    def accepte(self, valeur: object) -> bool:
        largeur = self.largeur
        return (
            type(valeur) is list
            and len(valeur) % largeur == 0
            and len(valeur) <= self.lignes * largeur
            and all(_entier(n, self.colonnes[i % largeur]) for i, n in enumerate(valeur))
        )


# Même ordre que la table `CLES` de releve.js.
SCHEMA: dict[str, Nombre | Uplet | Liste] = {
    "version": Nombre((VERSION, VERSION)),
    "morceau": Nombre((0, ENVOIS_PAR_PAGE - 1)),
    "raison": Nombre((0, 2)),  # 0 tampon plein, 1 arrière-plan, 2 sortie de la page
    "instant_ms": Nombre(INSTANT),
    # largeur et hauteur de la fenêtre, de la page, défilement vertical, rapport de pixels × 100, pointeur (0 à 2)
    "cadre": Uplet((DIMENSION, DIMENSION, PAGE_PX, PAGE_PX, DEFILEMENT, (1, 10_000), (0, 2))),
    "ecartes": Nombre((0, 100_000_000)),
    "souris": Liste(600, (INSTANT, POSITION, POSITION)),
    # instant, position, bouton, sorte d'élément (SORTES), sorte de pointeur (0 inconnu, 1 souris, 2 stylet, 3 doigt)
    "clics": Liste(100, (INSTANT, POSITION, POSITION, (-1, 15), (0, len(SORTES) - 1), (0, 3))),
    "defilement": Liste(300, (INSTANT, DEFILEMENT)),
    "molette": Liste(300, (INSTANT, PAS, PAS, (0, 2))),  # unité : 0 pixel, 1 ligne, 2 page
    "clavier_appuis": Liste(200, (INSTANT, OUI_NON)),  # zone de texte : 1 oui, 0 non
    "clavier_relaches": Liste(200, (INSTANT,)),
    # instant, position, doigts posés, rayon (-1 : absent), pression × 100 (-1 : absente), phase (début, mouvement,
    # fin, annulé)
    "tactile": Liste(300, (INSTANT, POSITION, POSITION, (0, 20), (-1, 10_000), (-1, 100), (0, 3))),
    "premier_plan": Liste(50, (INSTANT, OUI_NON)),
    "focus": Liste(50, (INSTANT, OUI_NON)),
    "redimensionnements": Liste(50, (INSTANT, DIMENSION, DIMENSION)),
}


def page_valide(page: object) -> bool:
    return isinstance(page, str) and len(page) <= TAILLE_MAX_PAGE and PAGE.fullmatch(page) is not None


def valider(charge: object) -> dict | None:
    """La trace reconstruite à partir des seules clés du schéma, ou None si quoi que ce soit s'en écarte."""
    if not isinstance(charge, dict) or set(charge) != set(SCHEMA):
        return None
    propre: dict = {}
    for cle, regle in SCHEMA.items():
        valeur = charge[cle]
        if not regle.accepte(valeur):
            return None
        propre[cle] = list(valeur) if isinstance(valeur, list) else valeur
    return propre
