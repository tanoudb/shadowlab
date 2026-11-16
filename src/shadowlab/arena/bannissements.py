"""Bannissement dans l'Arena (palier 2, I3) : par visiteur, par empreinte E (sessions neuves) et par débit de pages.

Ce module décide une chose : « cette requête vient-elle d'un visiteur banni dans son monde ? ». Le gardien
(`site/gardien.py`) l'appelle **en tête**, et seulement pour un profil dont l'option `bannissement.actif` est vraie
(`endurance`). Aux niveaux 01 à 07 rien de ce module n'est appelé : aucune lecture, aucune écriture.

- **Par visiteur** : un visiteur banni reçoit un 403 dans son monde, avec n'importe quel jeton de session.
- **Par empreinte E** (`correlation.empreinte_e`) : elle ne touche que les **sessions neuves** du monde. Un visiteur
  connu qui porte la même E n'est pas touché : bannir une E pour tout le monde bannirait tous les humains du même
  modèle de machine.
- **Par débit** : plus de `pages_par_heure` pages en une heure glissante, ou de `pages_par_jour` en 24 h, **toutes les
  sessions du visiteur ensemble** (un cookie de visiteur rejoué dans beaucoup de sessions parallèles est compté une
  seule fois, en tout). Une « page » est celle des détecteurs (D-78) : ni photo, ni ressource, ni échange technique.
  Les compteurs se **lisent** dans `observations_http` jointe à `visites` ; ils ne s'écrivent jamais.
- Les mondes `manuel` et `hors-passage` ne sont jamais remis à zéro : aucun bannissement **automatique** n'y est écrit
  (détection ni débit). Un bannissement manuel (`shadowlab arena bannir`) vaut dans tous les mondes.

Coût : une lecture indexée par requête pour une session connue (le bannissement, et les compteurs si c'est une
page, dans la même instruction) ; la fiche de la session (monde, visiteur, neuve ou non, E) est tenue en mémoire
une fois lue. Le cache ne garde jamais « non banni » : la commande `arena bannir` écrit depuis un autre processus
que le site.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from .. import correlation
from ..detection import CHEMINS_TECHNIQUES, RESSOURCES_DE_PAGE
from . import visiteurs
from .profils import Bannissement

HEURE = timedelta(hours=1)
JOUR = timedelta(hours=24)
MONDES_SANS_BANNISSEMENT_AUTO = frozenset({visiteurs.MONDE_MANUEL, visiteurs.MONDE_HORS_PASSAGE})
MOTIF_MANUEL = "manuel"


@dataclass(frozen=True)
class Verdict:
    monde: str
    visiteur: str | None
    motif: str  # `manuel`, `detecte:<détecteurs>`, `debit:pages_par_heure`, `debit:pages_par_jour`…
    par: str  # `visiteur`, `empreinte` ou `debit`


def _stamp(instant: datetime) -> str:
    return instant.astimezone(UTC).isoformat(timespec="milliseconds")


def depassement(pages_heure: int, pages_jour: int, seuils: Bannissement) -> str | None:
    """Le motif du dépassement, ou None. Les comptes comprennent la requête en cours (le frontal l'a déjà notée) :
    bannir à la 241ᵉ page en une heure, à la 2 001ᵉ en 24 h."""
    if pages_heure > seuils.pages_par_heure:
        return "pages_par_heure"
    if pages_jour > seuils.pages_par_jour:
        return "pages_par_jour"
    return None


def clause_pages() -> str:
    """La définition de `Observations.documents` en SQL, construite à partir de ses constantes (jamais recopiée).

    Une requête de page n'est ni un échange technique (`CHEMINS_TECHNIQUES`) ni une ressource de page
    (`RESSOURCES_DE_PAGE`, sauf si le chemin remonte d'un dossier : `..`).
    """

    def commence(chemin: str) -> str:
        return f"substr(h.path, 1, {len(chemin)}) = '{chemin}'"

    technique = " OR ".join(commence(c) for c in CHEMINS_TECHNIQUES)
    ressource = " OR ".join(commence(c) for c in RESSOURCES_DE_PAGE)
    return f"NOT ({technique}) AND NOT (({ressource}) AND instr(h.path, '..') = 0)"


_MONDE = "(SELECT id FROM mondes WHERE nom = :monde)"
_COMPTE = (
    "SELECT COUNT(*) AS jour, COALESCE(SUM(h.received_at >= :heure), 0) AS heure"
    " FROM visites v JOIN observations_http h ON h.session_token = v.session_token"
    f" WHERE v.monde_id = {_MONDE} AND v.visiteur = :visiteur"
    " AND v.vue_le >= :jour AND v.vue_le <= :maintenant AND h.received_at >= :jour AND h.received_at <= :maintenant"
    f" AND {clause_pages()}"
)
_JOINTURE_BAN = (
    f" LEFT JOIN bannissements b ON b.monde_id = {_MONDE} AND (b.expire_le IS NULL OR b.expire_le > :maintenant)"
    " AND (b.visiteur = :visiteur OR (:empreinte IS NOT NULL AND b.empreinte = :empreinte))"
    " ORDER BY b.id LIMIT 1"
)  # sans bannissement, la jointure rend quand même une ligne, vide : les compteurs sortent toujours
_LIRE_BAN = "SELECT b.motif AS motif, b.visiteur AS vise, 0 AS jour, 0 AS heure FROM (SELECT 1) c" + _JOINTURE_BAN
_LIRE_BAN_ET_COMPTES = (
    f"SELECT b.motif AS motif, b.visiteur AS vise, c.jour AS jour, c.heure AS heure FROM ({_COMPTE}) c" + _JOINTURE_BAN
)


def _parametres(monde: str, visiteur: str | None, empreinte: str | None, maintenant: datetime) -> dict:
    return {
        "monde": monde,
        "visiteur": visiteur,
        "empreinte": empreinte,
        "maintenant": _stamp(maintenant),
        "heure": _stamp(maintenant - HEURE),
        "jour": _stamp(maintenant - JOUR),
    }


def compter_pages(cx: sqlite3.Connection, monde: str, visiteur: str, maintenant: datetime) -> tuple[int, int]:
    """(pages dans l'heure, pages dans les 24 h) du visiteur dans son monde, toutes ses sessions ensemble.

    Lecture seule, horloge injectable. Seules comptent les sessions commencées dans les 24 dernières heures :
    une session plus longue que cela n'est pas vue (limite connue).
    """
    ligne = cx.execute(_COMPTE, _parametres(monde, visiteur, None, maintenant)).fetchone()
    return int(ligne["heure"]), int(ligne["jour"])


def bannir(
    cx: sqlite3.Connection,
    monde: str,
    *,
    visiteur: str | None = None,
    empreinte: str | None = None,
    motif: str,
    maintenant: datetime | None = None,
    expire_le: datetime | None = None,
) -> bool:
    """Écrit un bannissement (visiteur, empreinte ou les deux) dans `monde`. Faux si le même est déjà en vigueur."""
    if visiteur is None and empreinte is None:
        raise ValueError("un bannissement vise un visiteur ou une empreinte")
    maintenant = maintenant or datetime.now(UTC)
    cree = cx.execute(
        "INSERT INTO bannissements (monde_id, visiteur, empreinte, motif, cree_le, expire_le)"
        " SELECT ?, ?, ?, ?, ?, ? WHERE NOT EXISTS (SELECT 1 FROM bannissements"
        " WHERE monde_id = ? AND visiteur IS ? AND empreinte IS ? AND (expire_le IS NULL OR expire_le > ?))",
        (
            monde_id := visiteurs.identifiant_monde(cx, monde),
            visiteur,
            empreinte,
            motif,
            _stamp(maintenant),
            _stamp(expire_le) if expire_le else None,
            monde_id,
            visiteur,
            empreinte,
            _stamp(maintenant),
        ),
    )
    return cree.rowcount > 0


class BannissementRefuse(ValueError):
    """Un bannissement manuel que le monde ou le visiteur rend impossible (inconnu : une faute de frappe ne bannit
    personne)."""


def dernier_visiteur(cx: sqlite3.Connection, monde: str) -> str | None:
    """Le visiteur le plus récent vu dans `monde`, ou None (monde inconnu, ou personne n'y est encore venu)."""
    ligne = cx.execute(
        "SELECT v.visiteur FROM visites v JOIN mondes m ON m.id = v.monde_id"
        " WHERE m.nom = ? ORDER BY v.id DESC LIMIT 1",
        (monde,),
    ).fetchone()
    return ligne["visiteur"] if ligne else None


def bannir_visiteur_connu(cx: sqlite3.Connection, monde: str, visiteur: str, *, motif: str = MOTIF_MANUEL) -> bool:
    """Bannissement manuel d'un visiteur DÉJÀ VU dans son monde : `shadowlab arena bannir` et `bannir_avant_visite`
    d'une campagne passent tous deux ici. Refuse (`BannissementRefuse`) un monde ou un visiteur inconnu, sans rien
    créer.
    Vrai si une ligne est écrite, faux si le visiteur était déjà banni."""
    ligne = cx.execute("SELECT id FROM mondes WHERE nom = ?", (monde,)).fetchone()
    if ligne is None:
        raise BannissementRefuse(f"monde inconnu : {monde}")
    vu = cx.execute(
        "SELECT 1 FROM visites WHERE monde_id = ? AND visiteur = ? LIMIT 1", (ligne["id"], visiteur)
    ).fetchone()
    if vu is None:
        raise BannissementRefuse(f"visiteur inconnu dans le monde {monde} : {visiteur}")
    return bannir(cx, monde, visiteur=visiteur, motif=motif)


@dataclass
class _Fiche:
    monde: str
    visiteur: str | None  # None : première requête d'un visiteur sans cookie, il n'a pas encore d'identité
    neuve: bool
    empreinte: str | None = None  # E de la première empreinte reçue, cherchée tant qu'elle n'est pas arrivée


class Surveillance:
    """Ce que l'application retient des sessions qu'elle surveille (une fiche par jeton, bornée).

    La fiche d'une session est celle de sa ligne `visites` (monde, visiteur, neuve) : fixée à sa première requête, donc
    sûre à garder. L'empreinte E d'une session neuve s'y ajoute quand elle arrive. Les bannissements, eux, ne sont
    jamais retenus : ils sont lus à chaque requête.
    """

    def __init__(self, maximum: int = 20000) -> None:
        self.maximum = maximum
        self._sessions: dict[str, _Fiche] = {}

    def _fiche(self, cx: sqlite3.Connection, secret: bytes, valeur_cookie: str | None, jeton: str) -> _Fiche:
        fiche = self._sessions.get(jeton)
        if fiche is not None:
            return fiche
        ligne = cx.execute(
            "SELECT m.nom, v.visiteur, v.neuve FROM visites v JOIN mondes m ON m.id = v.monde_id"
            " WHERE v.session_token = ?",
            (jeton,),
        ).fetchone()
        if ligne is None:
            # Première requête de la session : sa visite n'est écrite qu'après la réponse. Lecture seule : on
            # reconnaît le visiteur comme `visiteurs.reconnaitre` le fera, sans rien écrire.
            monde = visiteurs.monde_de_session(cx, jeton)
            visiteur = visiteurs.lire_cookie(secret, monde, valeur_cookie)
            return _Fiche(monde, visiteur, visiteur is None)
        fiche = _Fiche(ligne["nom"], ligne["visiteur"], bool(ligne["neuve"]))
        if len(self._sessions) >= self.maximum:
            del self._sessions[next(iter(self._sessions))]
        self._sessions[jeton] = fiche
        return fiche

    def visiteur_de(
        self, cx: sqlite3.Connection, secret: bytes, valeur_cookie: str | None, jeton: str
    ) -> tuple[str, str | None]:
        """(monde, visiteur) de la session ; le visiteur est None à la toute première requête d'un navigateur neuf."""
        fiche = self._fiche(cx, secret, valeur_cookie, jeton)
        return fiche.monde, fiche.visiteur

    def juger(
        self,
        cx: sqlite3.Connection,
        secret: bytes,
        valeur_cookie: str | None,
        jeton: str,
        *,
        page: bool,
        seuils: Bannissement,
        maintenant: datetime | None = None,
    ) -> Verdict | None:
        """Le verdict sur cette requête : banni (visiteur, ou empreinte pour une session neuve), ou débit dépassé.

        `page` : la requête est une page (D-78) ; seules les pages font lire les compteurs. Un dépassement écrit le
        bannissement du visiteur (une seule fois). Une seule instruction SQL lit le bannissement et les compteurs.
        """
        maintenant = maintenant or datetime.now(UTC)
        fiche = self._fiche(cx, secret, valeur_cookie, jeton)
        if fiche.neuve and fiche.empreinte is None:
            fiche.empreinte = correlation.empreinte_de_session(cx, jeton)
        empreinte = fiche.empreinte if fiche.neuve else None
        if fiche.visiteur is None and empreinte is None:
            return None  # un navigateur neuf dont on ne sait encore rien : rien à lui reprocher
        compter = page and fiche.visiteur is not None and fiche.monde not in MONDES_SANS_BANNISSEMENT_AUTO
        ligne = cx.execute(
            _LIRE_BAN_ET_COMPTES if compter else _LIRE_BAN,
            _parametres(fiche.monde, fiche.visiteur, empreinte, maintenant),
        ).fetchone()
        if ligne["motif"] is not None:
            direct = fiche.visiteur is not None and ligne["vise"] == fiche.visiteur
            return Verdict(fiche.monde, fiche.visiteur, ligne["motif"], "visiteur" if direct else "empreinte")
        if compter:
            motif = depassement(int(ligne["heure"]), int(ligne["jour"]), seuils)
            if motif:
                bannir(cx, fiche.monde, visiteur=fiche.visiteur, motif=f"debit:{motif}", maintenant=maintenant)
                return Verdict(fiche.monde, fiche.visiteur, f"debit:{motif}", "debit")
        return None

    def bannir_detection(
        self, cx: sqlite3.Connection, secret: bytes, valeur_cookie: str | None, jeton: str, detecteurs: list[str]
    ) -> bool:
        """Le gardien a arrêté cette session pour suspicion : bannit son visiteur et son empreinte E (une ligne).

        Rien dans un monde sans remise à zéro, ni pour une session dont on ne connaît pas encore le visiteur.
        """
        fiche = self._fiche(cx, secret, valeur_cookie, jeton)
        if fiche.monde in MONDES_SANS_BANNISSEMENT_AUTO or fiche.visiteur is None:
            return False
        motif = "detecte:" + ",".join(sorted(set(detecteurs))) if detecteurs else "detecte"
        return bannir(
            cx,
            fiche.monde,
            visiteur=fiche.visiteur,
            empreinte=correlation.empreinte_de_session(cx, jeton),
            motif=motif,
        )

    def bannir_visiteur(
        self, cx: sqlite3.Connection, secret: bytes, valeur_cookie: str | None, jeton: str, motif: str
    ) -> bool:
        """Bannit le visiteur d'une session (même règle des mondes partagés)."""
        fiche = self._fiche(cx, secret, valeur_cookie, jeton)
        if fiche.monde in MONDES_SANS_BANNISSEMENT_AUTO or fiche.visiteur is None:
            return False
        return bannir(cx, fiche.monde, visiteur=fiche.visiteur, motif=motif)
