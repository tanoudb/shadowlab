"""Lecteur de robots.txt (RFC 9309), sans dépendance.

Règles retenues :
- groupes par agent : le groupe qui cite notre agent (comparaison sans casse) ; à défaut, le groupe `*` ;
  plusieurs groupes du même agent se cumulent ; aucun groupe correspondant = tout est permis ;
- `Allow` / `Disallow` : motif comparé au début de « chemin + ?requête » ; `*` = n'importe quelle suite de
  caractères, `$` final = fin de l'adresse ; le motif le plus long l'emporte, à longueur égale `Allow` ;
  un `Disallow:` vide ne bloque rien ; comparaison en temps linéaire, sans expression régulière (le fichier
  vient du site visé : un motif à nombreuses `*` ferait exploser une expression régulière) ;
- bornes contre un fichier hostile : 500 Kio lus au plus (RFC 9309), ligne de plus de 2 000 caractères ignorée,
  1 000 règles gardées par groupe (un vrai fichier en a quelques dizaines ; au-delà c'est du bourrage) ;
  ce qui est ignoré est compté et rendu par `resume` ;
- `Crawl-delay` : nombre de secondes positif du groupe retenu (hors RFC, d'usage courant) ;
- fichier absent (4xx, sauf 429) = tout permis ; erreur serveur (5xx), 429 ou pas de réponse = rien de permis
  pour cette passe.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import quote

_NON_RESERVES = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")
_RE_POURCENT = re.compile(r"%([0-9A-Fa-f]{2})")


def _normaliser(texte: str) -> str:
    """Écriture canonique : `%XX` en majuscules, caractères non réservés décodés, non-ASCII en UTF-8 encodé."""
    texte = quote(texte, safe="/?&=:@!$'()*+,;%[]#~-._")  # encode le non-ASCII, garde le reste tel quel

    def remplacer(m: re.Match[str]) -> str:
        caractere = chr(int(m.group(1), 16))
        return caractere if caractere in _NON_RESERVES else f"%{m.group(1).upper()}"

    return _RE_POURCENT.sub(remplacer, texte)


TAILLE_MAX_OCTETS = 500 * 1024
LIGNE_MAX = 2000
REGLES_MAX_PAR_GROUPE = 1000


def _compacter(motif: str) -> str:
    """Réduit les `*` consécutifs à un seul."""
    while "**" in motif:
        motif = motif.replace("**", "*")
    return motif


def _correspond(motif: str, cible: str) -> bool:
    """Le motif (`*`, `$` final) correspond-il au début de `cible` ? Temps linéaire : aucune expression régulière."""
    ancre = motif.endswith("$")
    morceaux = (motif[:-1] if ancre else motif).split("*")
    if len(morceaux) == 1:
        return cible == morceaux[0] if ancre else cible.startswith(morceaux[0])
    premier, dernier = morceaux[0], morceaux[-1]
    if not cible.startswith(premier):
        return False
    position = len(premier)
    for morceau in morceaux[1:-1]:
        trouve = cible.find(morceau, position)
        if trouve < 0:
            return False
        position = trouve + len(morceau)
    if ancre:
        return cible.endswith(dernier) and len(cible) - len(dernier) >= position
    return cible.find(dernier, position) >= 0


@dataclass(frozen=True)
class _Regle:
    autorise: bool
    motif: str


@dataclass
class _Ignore:
    """Ce que les bornes ont écarté."""

    fichier_tronque: bool = False
    lignes_trop_longues: int = 0
    regles_en_trop: int = 0


@dataclass
class _Groupe:
    agents: list[str] = field(default_factory=list)
    regles: list[_Regle] = field(default_factory=list)
    crawl_delay: float | None = None


def _groupes(texte: str, ignore: _Ignore) -> list[_Groupe]:
    octets = texte.encode("utf-8", errors="replace")
    if len(octets) > TAILLE_MAX_OCTETS:
        ignore.fichier_tronque = True
        texte = octets[:TAILLE_MAX_OCTETS].decode("utf-8", errors="ignore")
    groupes: list[_Groupe] = []
    courant: _Groupe | None = None
    dernier_etait_agent = False
    for brute in texte.lstrip("﻿").splitlines():
        if len(brute) > LIGNE_MAX:
            ignore.lignes_trop_longues += 1
            continue
        ligne = brute.split("#", 1)[0].strip()
        if ":" not in ligne:
            continue
        nom, _, valeur = ligne.partition(":")
        nom, valeur = nom.strip().lower(), valeur.strip()
        if nom == "user-agent":
            if courant is None or not dernier_etait_agent:
                courant = _Groupe()
                groupes.append(courant)
            courant.agents.append(valeur.lower())
            dernier_etait_agent = True
            continue
        dernier_etait_agent = False
        if courant is None:
            continue  # règle avant tout User-agent : ignorée
        if nom in ("allow", "disallow"):
            if valeur:  # `Disallow:` vide : rien n'est bloqué ; `Allow:` vide : sans effet
                if len(courant.regles) >= REGLES_MAX_PAR_GROUPE:
                    ignore.regles_en_trop += 1
                else:
                    courant.regles.append(_Regle(nom == "allow", _compacter(_normaliser(valeur))))
        elif nom == "crawl-delay" and courant.crawl_delay is None:
            try:
                delai = float(valeur)
            except ValueError:
                continue
            if delai > 0:
                courant.crawl_delay = delai
    return groupes


class Robots:
    """Les permissions d'un robots.txt pour un agent. Construire avec `depuis_reponse` ou `inaccessible`."""

    def __init__(
        self,
        agent: str,
        etat: str,
        statut: int | None,
        regles: list[_Regle],
        groupe: str | None,
        crawl_delay: float | None,
        ignore: _Ignore | None = None,
    ) -> None:
        self.agent = agent
        self.etat = etat  # « lu », « absent » (tout permis) ou « inaccessible » (rien de permis)
        self.statut = statut
        self._regles = regles
        self.groupe = groupe  # l'agent ou « * » : le groupe retenu, None s'il n'y en a pas
        self.crawl_delay = crawl_delay
        self.ignore = ignore or _Ignore()

    @classmethod
    def inaccessible(cls, agent: str = "noezia", statut: int | None = None) -> Robots:
        return cls(agent, "inaccessible", statut, [], None, None)

    @classmethod
    def depuis_reponse(cls, statut: int, texte: str, agent: str) -> Robots:
        if statut == 429 or statut >= 500:
            return cls.inaccessible(agent, statut)
        if 400 <= statut < 500 or not 200 <= statut < 300:
            return cls(agent, "absent", statut, [], None, None)
        ignore = _Ignore()
        groupes = _groupes(texte, ignore)
        nom = agent.lower()
        retenus = [g for g in groupes if nom in g.agents]
        groupe = agent if retenus else None
        if not retenus:
            retenus = [g for g in groupes if "*" in g.agents]
            groupe = "*" if retenus else None
        regles = [r for g in retenus for r in g.regles]
        delais = [g.crawl_delay for g in retenus if g.crawl_delay is not None]
        return cls(agent, "lu", statut, regles, groupe, delais[0] if delais else None, ignore)

    def permis(self, chemin_et_requete: str) -> bool:
        """`chemin_et_requete` : `/chemin?parametres` (sans hôte)."""
        if self.etat == "inaccessible":
            return False
        cible = _normaliser(chemin_et_requete)
        meilleure: _Regle | None = None
        for regle in self._regles:
            if not _correspond(regle.motif, cible):
                continue
            if (
                meilleure is None
                or len(regle.motif) > len(meilleure.motif)
                or (len(regle.motif) == len(meilleure.motif) and regle.autorise and not meilleure.autorise)
            ):
                meilleure = regle
        return meilleure is None or meilleure.autorise

    def resume(self, adresse: str) -> dict[str, object]:
        """Ce que `resume.json` garde du robots.txt de cette passe."""
        return {
            "respecte": True,
            "agent": self.agent,
            "adresse": adresse,
            "statut": self.statut,
            "etat": self.etat,
            "groupe": self.groupe,
            "crawl_delay": self.crawl_delay,
            "ignore": {
                "fichier_tronque": self.ignore.fichier_tronque,
                "lignes_trop_longues": self.ignore.lignes_trop_longues,
                "regles_en_trop": self.ignore.regles_en_trop,
            },
        }
