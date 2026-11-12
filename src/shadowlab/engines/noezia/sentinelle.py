"""Sentinelle : arrêt au premier signe d'alerte (première version, les signes qui se voient en HTTP).

Signes retenus (§ 5 du document de conception) :
1. statut 401, 403, 407, 429 ou 503 ;
3. adresse finale hors des hôtes de la recette, ou hors du motif `url` du type de page attendu ;
4. sélecteur `requis` absent sur 3 pages de suite d'un même type ;
5. plus de 5 échecs (réseau, 500, 502, 504) sur les 20 dernières pages.
Pas encore là (étape 4) : pages de défi (Arena, Cloudflare, reCAPTCHA…), porte d'entrée, mesures du navigateur.

La sentinelle ne fait aucune requête et ne décide que d'une chose : y a-t-il une alerte ? Le parcours s'arrête alors,
sans aucun nouvel essai (réessayer aggrave).
"""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from urllib.parse import urlsplit

STATUTS_ALERTE = frozenset({401, 403, 407, 429, 503})
FENETRE = 20
ECHECS_MAX = 5
NON_CONFORMES_MAX = 3


@dataclass(frozen=True)
class Alerte:
    signe: str  # statut | hors_site | hors_motif | page_non_conforme | echecs
    detail: str
    adresse: str
    statut: int | None = None

    def message(self) -> str:
        return f"signe d'alerte ({self.detail}) sur {self.adresse}"


class Sentinelle:
    def __init__(self, hotes: Iterable[str]) -> None:
        self._hotes = {h.lower() for h in hotes}
        self._recentes: deque[str] = deque(maxlen=FENETRE)  # décisions des dernières pages lues
        self._non_conformes: dict[str, int] = defaultdict(int)  # par type : pages de suite sans `requis`

    def examiner(
        self, *, type_page: str, adresse: str, statut: int | None, adresse_finale: str, dans_le_motif: bool
    ) -> Alerte | None:
        """Signes 1 et 3, avant de lire le contenu."""
        if statut in STATUTS_ALERTE:
            return Alerte("statut", f"statut {statut}", adresse, statut)
        hote = (urlsplit(adresse_finale).hostname or "").lower()
        if hote not in self._hotes:
            return Alerte("hors_site", f"redirection vers un autre hôte : {hote or adresse_finale}", adresse, statut)
        if not dans_le_motif:
            return Alerte(
                "hors_motif", f"adresse finale {adresse_finale} hors du motif du type « {type_page} »", adresse, statut
            )
        return None

    def noter(self, type_page: str, decision: str, adresse: str = "") -> Alerte | None:
        """Signes 4 et 5, une fois la page lue. `decision` : ok, introuvable, anormale ou echec."""
        self._recentes.append(decision)
        if decision == "anormale":
            self._non_conformes[type_page] += 1
            if self._non_conformes[type_page] >= NON_CONFORMES_MAX:
                return Alerte(
                    "page_non_conforme",
                    f"{NON_CONFORMES_MAX} pages « {type_page} » de suite sans leur sélecteur requis",
                    adresse,
                )
        elif decision == "ok":
            self._non_conformes[type_page] = 0
        if sum(1 for d in self._recentes if d == "echec") > ECHECS_MAX:
            return Alerte("echecs", f"plus de {ECHECS_MAX} échecs sur les {FENETRE} dernières pages", adresse)
        return None

    def rejouer(self, lignes: Iterable[Mapping[str, object]]) -> None:
        """Reprend l'historique (pages déjà lues, dans l'ordre) : la reprise ne repart pas de zéro."""
        for ligne in lignes:
            self.noter(str(ligne["type"]), str(ligne["decision"]))
