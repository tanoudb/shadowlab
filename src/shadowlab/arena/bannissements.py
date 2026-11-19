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
- **Par adresse** (D-105) : l'adresse signée par le frontal pour la requête (`X-ShadowLab-Adresse`, `site/gardien.py`).
  Une ligne qui ne porte que `adresse`. Elle est lue **avant** tout le reste, même pour un navigateur neuf dont on ne
  sait encore rien (première requête, ni cookie ni empreinte). À la main (`arena bannir --ip`, motif `manuel`) elle
  refuse tout le monde derrière cette adresse dans ce monde. Automatique (règle ci-dessous, motif `visiteurs_bannis_…`,
  24 h) elle épargne le visiteur dont une visite DANS CE MONDE est plus ancienne que le bannissement : un humain qui
  revient avec son cookie derrière une adresse partagée n'est pas refusé parce que d'autres visiteurs de cette adresse
  l'ont été (même raison que la règle de l'empreinte E). Un navigateur refusé ne devient pas un habitué : la visite
  écrite à son refus est postérieure au bannissement, il reste refusé avec le cookie reçu. Aucune cascade : une adresse
  bannie ne bannit ni visiteur ni empreinte ; l'adresse du pair non simulé (127.0.0.1, `::1`) ne déclenche jamais la
  règle automatique, tous les clients d'un poste la portent.
- **Par compte** (I10, D-104) : une ligne peut viser un compte (colonne `compte`) ; elle ne touche que la connexion et
  l'espace privé (`arena/comptes.py`), jamais les autres pages du visiteur. Un visiteur banni alors qu'il est connecté
  à un compte (connexion encore valable, `appareils.connecte_jusqu_au`) fait bannir ce compte, dans le même monde
  (motif `visiteur_banni:<motif>`) ; rien de tel dans les mondes partagés ci-dessus.

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
from . import adresses, visiteurs
from .profils import Bannissement

HEURE = timedelta(hours=1)
JOUR = timedelta(hours=24)
MONDES_SANS_BANNISSEMENT_AUTO = frozenset({visiteurs.MONDE_MANUEL, visiteurs.MONDE_HORS_PASSAGE})
MOTIF_MANUEL = "manuel"
MOTIF_VISITEUR_BANNI = "visiteur_banni"  # préfixe du motif d'un compte banni parce que son visiteur connecté l'a été
# Règle automatique des adresses (D-105) : au moins `SEUIL_ADRESSE` visiteurs DISTINCTS bannis en 24 h dans le monde,
# dont une visite est venue de la même adresse déclarée, bannissent cette adresse pour 24 h.
SEUIL_ADRESSE = 3
DUREE_ADRESSE = JOUR
MOTIF_ADRESSE = "visiteurs_bannis_meme_adresse"


@dataclass(frozen=True)
class Verdict:
    monde: str
    visiteur: str | None
    motif: str  # `manuel`, `detecte:<détecteurs>`, `debit:pages_par_heure`, `debit:pages_par_jour`…
    par: str  # `visiteur`, `empreinte`, `adresse`, `debit` ou `compte`
    compte: str | None = None  # le compte refusé (`par` = `compte`)


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
    " AND (b.visiteur = :visiteur OR (:empreinte IS NOT NULL AND b.empreinte = :empreinte)"
    f" OR (:adresse IS NOT NULL AND b.adresse = :adresse AND (b.motif = '{MOTIF_MANUEL}' OR NOT EXISTS ("
    " SELECT 1 FROM visites vv WHERE vv.monde_id = b.monde_id AND vv.visiteur = :visiteur AND vv.vue_le < b.cree_le))))"
    " ORDER BY b.id LIMIT 1"
)  # sans bannissement, la jointure rend quand même une ligne, vide : les compteurs sortent toujours
_LIRE_BAN = (
    "SELECT b.motif AS motif, b.visiteur AS vise, b.adresse AS adr, 0 AS jour, 0 AS heure FROM (SELECT 1) c"
    + _JOINTURE_BAN
)
_LIRE_BAN_ET_COMPTES = (
    "SELECT b.motif AS motif, b.visiteur AS vise, b.adresse AS adr, c.jour AS jour, c.heure AS heure"
    f" FROM ({_COMPTE}) c" + _JOINTURE_BAN
)


def _parametres(
    monde: str,
    visiteur: str | None,
    empreinte: str | None,
    maintenant: datetime,
    adresse: str | None = None,
) -> dict:
    return {
        "monde": monde,
        "visiteur": visiteur,
        "empreinte": empreinte,
        "adresse": adresse,
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
    compte: str | None = None,
    adresse: str | None = None,
    motif: str,
    maintenant: datetime | None = None,
    expire_le: datetime | None = None,
) -> bool:
    """Écrit un bannissement (visiteur, empreinte, compte, adresse) dans `monde`. Faux si le même est déjà en vigueur.

    Un visiteur banni fait bannir les comptes auxquels il est encore connecté dans ce monde (I10), sauf dans les mondes
    partagés (aucun bannissement automatique n'y est écrit) ; et, si assez de visiteurs ont été bannis depuis une même
    adresse, cette adresse (D-105, `regle_adresse`)."""
    if visiteur is None and empreinte is None and compte is None and adresse is None:
        raise ValueError("un bannissement vise un visiteur, une empreinte, un compte ou une adresse")
    if adresse is not None:
        adresse = adresses.normaliser(adresse)
        if adresse is None:
            raise ValueError("adresse illisible : une adresse IP (v4 ou v6) est attendue")
    maintenant = maintenant or datetime.now(UTC)
    cree = cx.execute(
        "INSERT INTO bannissements (monde_id, visiteur, empreinte, compte, adresse, motif, cree_le, expire_le)"
        " SELECT ?, ?, ?, ?, ?, ?, ?, ? WHERE NOT EXISTS (SELECT 1 FROM bannissements WHERE monde_id = ?"
        " AND visiteur IS ? AND empreinte IS ? AND compte IS ? AND adresse IS ?"
        " AND (expire_le IS NULL OR expire_le > ?))",
        (
            monde_id := visiteurs.identifiant_monde(cx, monde),
            visiteur,
            empreinte,
            compte,
            adresse,
            motif,
            _stamp(maintenant),
            _stamp(expire_le) if expire_le else None,
            monde_id,
            visiteur,
            empreinte,
            compte,
            adresse,
            _stamp(maintenant),
        ),
    )
    if visiteur is not None and cree.rowcount > 0 and monde not in MONDES_SANS_BANNISSEMENT_AUTO:
        regle_adresse(cx, monde, monde_id, visiteur, maintenant)
    if visiteur is not None and monde not in MONDES_SANS_BANNISSEMENT_AUTO:
        for (connecte,) in cx.execute(
            "SELECT c.identifiant FROM appareils a JOIN comptes c ON c.id = a.compte_id"
            " WHERE c.monde_id = ? AND a.visiteur = ? AND a.connecte_jusqu_au > ? ORDER BY c.id",
            (monde_id, visiteur, _stamp(maintenant)),
        ).fetchall():
            bannir(cx, monde, compte=connecte, motif=f"{MOTIF_VISITEUR_BANNI}:{motif}", maintenant=maintenant)
    return cree.rowcount > 0


def regle_adresse(cx: sqlite3.Connection, monde: str, monde_id: int, visiteur: str, maintenant: datetime) -> None:
    """Règle automatique des adresses (D-105) : pour chaque adresse déclarée d'où ce visiteur est venu, si au moins
    `SEUIL_ADRESSE` visiteurs distincts dont une visite en est venue ont été bannis dans les dernières 24 h, l'adresse
    est bannie pour 24 h. Les adresses du pair non simulé (boucle locale) n'y entrent jamais.

    Pourquoi 3 : un humain derrière une box ou un réseau d'entreprise n'est pas banni parce qu'un autre l'a été une ou
    deux fois (une fausse détection) ; trois visiteurs différents bannis depuis la même adresse en un jour, c'est une
    adresse d'où l'on fait tourner des identités, ce que l'étape 4.2 va faire. Ce n'est pas une mesure : aucun humain
    derrière une adresse partagée en base."""
    deja_vues = cx.execute(
        "SELECT DISTINCT adresse FROM visites WHERE monde_id = ? AND visiteur = ? AND adresse IS NOT NULL",
        (monde_id, visiteur),
    ).fetchall()
    for ligne in deja_vues:
        adresse = ligne["adresse"]
        if adresses.est_local(adresse):
            continue
        distincts = cx.execute(
            "SELECT COUNT(DISTINCT b.visiteur) FROM bannissements b JOIN visites v"
            " ON v.monde_id = b.monde_id AND v.visiteur = b.visiteur"
            " WHERE b.monde_id = ? AND b.visiteur IS NOT NULL AND b.cree_le >= ? AND v.adresse = ?",
            (monde_id, _stamp(maintenant - JOUR), adresse),
        ).fetchone()[0]
        if distincts >= SEUIL_ADRESSE:
            bannir(
                cx,
                monde,
                adresse=adresse,
                motif=MOTIF_ADRESSE,
                maintenant=maintenant,
                expire_le=maintenant + DUREE_ADRESSE,
            )


def compte_banni(cx: sqlite3.Connection, monde: str, compte: str, maintenant: datetime | None = None) -> str | None:
    """Le motif du bannissement en vigueur du compte dans `monde`, ou None. Lecture seule."""
    ligne = cx.execute(
        "SELECT b.motif FROM bannissements b JOIN mondes m ON m.id = b.monde_id WHERE m.nom = ? AND b.compte = ?"
        " AND (b.expire_le IS NULL OR b.expire_le > ?) ORDER BY b.id LIMIT 1",
        (monde, compte, _stamp(maintenant or datetime.now(UTC))),
    ).fetchone()
    return ligne["motif"] if ligne else None


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


def derniere_adresse(cx: sqlite3.Connection, monde: str) -> str | None:
    """La dernière adresse déclarée vue dans `monde` (visite la plus récente qui en porte une), ou None."""
    ligne = cx.execute(
        "SELECT v.adresse FROM visites v JOIN mondes m ON m.id = v.monde_id"
        " WHERE m.nom = ? AND v.adresse IS NOT NULL ORDER BY v.id DESC LIMIT 1",
        (monde,),
    ).fetchone()
    return ligne["adresse"] if ligne else None


def bannir_adresse_connue(cx: sqlite3.Connection, monde: str, adresse: str, *, motif: str = MOTIF_MANUEL) -> bool:
    """Bannissement manuel d'une adresse dans un monde EXISTANT : `shadowlab arena bannir --ip` et `bannir_adresse`
    d'une campagne passent tous deux ici. Refuse (`BannissementRefuse`) un monde inconnu ou une adresse illisible, sans
    rien créer. Une adresse jamais vue dans ce monde est permise (on peut la bannir avant qu'elle n'arrive). Vrai si
    une ligne est écrite, faux si l'adresse était déjà bannie."""
    if cx.execute("SELECT 1 FROM mondes WHERE nom = ?", (monde,)).fetchone() is None:
        raise BannissementRefuse(f"monde inconnu : {monde}")
    normale = adresses.normaliser(adresse)
    if normale is None:
        raise BannissementRefuse(f"adresse illisible : {adresse!r} (une adresse IP v4 ou v6 est attendue)")
    return bannir(cx, monde, adresse=normale, motif=motif)


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
        adresse: str | None = None,
    ) -> Verdict | None:
        """Le verdict sur cette requête : banni (visiteur, empreinte ou adresse), ou débit dépassé.

        `adresse` : l'adresse signée par le frontal pour CETTE requête (jamais retenue dans la fiche : elle peut
        changer d'une requête à l'autre d'une session). Elle est jugée même si on ne sait encore rien du visiteur.

        `page` : la requête est une page (D-78) ; seules les pages font lire les compteurs. Un dépassement écrit le
        bannissement du visiteur (une seule fois). Une seule instruction SQL lit le bannissement et les compteurs.
        """
        maintenant = maintenant or datetime.now(UTC)
        fiche = self._fiche(cx, secret, valeur_cookie, jeton)
        if fiche.neuve and fiche.empreinte is None:
            fiche.empreinte = correlation.empreinte_de_session(cx, jeton)
        empreinte = fiche.empreinte if fiche.neuve else None
        if fiche.visiteur is None and empreinte is None and adresse is None:
            return None  # un navigateur neuf dont on ne sait encore rien : rien à lui reprocher
        compter = page and fiche.visiteur is not None and fiche.monde not in MONDES_SANS_BANNISSEMENT_AUTO
        ligne = cx.execute(
            _LIRE_BAN_ET_COMPTES if compter else _LIRE_BAN,
            _parametres(fiche.monde, fiche.visiteur, empreinte, maintenant, adresse),
        ).fetchone()
        if ligne["motif"] is not None:
            direct = fiche.visiteur is not None and ligne["vise"] == fiche.visiteur
            par = "visiteur" if direct else "adresse" if ligne["adr"] is not None else "empreinte"
            return Verdict(fiche.monde, fiche.visiteur, ligne["motif"], par)
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
