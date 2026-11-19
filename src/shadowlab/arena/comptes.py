"""Comptes dans l'Arena (palier 2, I10, D-104) : ce que l'Arena retient d'un compte de test, dans un monde.

Les comptes eux-mêmes restent des fixtures locales (`site/comptes.py`). Ce module retient, par monde :

- **les appareils** d'un compte (table `appareils`) : un appareil est un visiteur (`sl_visiteur`) qui s'est connecté au
  compte. Le premier n'est pas un « nouvel appareil » ; tout visiteur jamais vu sur ce compte en est un, et la ligne le
  note (`nouvel_appareil`). Le même visiteur qui se reconnecte reste le même appareil : la même identité du moteur
  n'est un nouvel appareil qu'à sa toute première connexion, et encore, seulement si le compte en avait déjà un ;
- **la règle « nouvel appareil »** : au plus `appareils_par_jour` (4) appareils distincts connectés au compte dans les
  24 dernières heures ; le suivant est refusé et le compte banni (motif `appareils_par_jour`). Un humain sur son
  ordinateur, son téléphone et sa tablette n'est jamais pris ; aucun bannissement automatique dans les mondes partagés
  (`manuel`, `hors-passage`) ;
- **le bannissement d'un compte** : une ligne `bannissements` dont la colonne `compte` est remplie, à la main
  (`shadowlab arena bannir --compte`), par la règle ci-dessus, ou quand un visiteur connecté au compte est banni
  (`bannissements.bannir`). Il refuse la connexion et l'espace privé, avec le refus de D-92 ;
- **la connexion durable** : le cookie de connexion est lié au monde, au visiteur et au compte (et au TLS si le niveau
  lie ses cookies), posé avec une durée (`duree_connexion_s`, 30 jours) : la connexion survit à la fermeture du
  navigateur, comme la case « rester connecté » d'un site ordinaire.

Rien de ce module n'est appelé si le profil ne bannit pas (`bannissement.actif`, seul `endurance` l'active) : aux
niveaux 01 à 07, la connexion reste liée au jeton de session, sans durée, et rien n'est lu ni écrit.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from . import bannissements, defis, visiteurs
from .profils import Bannissement

USAGE_COOKIE = "connexion-visiteur"
JOUR = timedelta(hours=24)
MOTIF_APPAREILS = "appareils_par_jour"


@dataclass(frozen=True)
class Connexion:
    nouvel_appareil: bool  # ce visiteur n'avait jamais été vu sur ce compte, et le compte avait déjà un appareil
    appareils_24h: int  # appareils distincts connectés au compte dans les 24 dernières heures, celui-ci compris
    banni: str | None  # le motif du bannissement que cette connexion vient de déclencher, ou None


def _stamp(instant: datetime) -> str:
    return instant.astimezone(UTC).isoformat(timespec="milliseconds")


def _cle(monde: str, visiteur: str, compte: str) -> str:
    return f"{monde}:{visiteur}:{compte}"


def creer_cookie(secret: bytes, monde: str, visiteur: str, compte: str, lie: str = "", *, duree_s: int) -> str:
    """Valeur du cookie de connexion durable : `<compte>.<expiration>.<signature>`, signée pour ce monde, ce visiteur et
    ce compte (et l'empreinte TLS de liaison `lie` si le niveau en a une). Une fixture n'a pas de point dans son nom."""
    if "." in compte or not compte:
        raise ValueError(f"identifiant de compte inattendu : {compte!r}")
    return f"{compte}.{defis.creer_cookie(secret, USAGE_COOKIE, _cle(monde, visiteur, compte), lie, duree_s=duree_s)}"


def lire_cookie(secret: bytes, monde: str, visiteur: str, valeur: str | None, lie: str = "") -> str | None:
    """Le compte du cookie de connexion, ou None : absent, mal formé, expiré, falsifié, ou signé pour un autre monde,
    un autre visiteur ou un autre compte."""
    if not valeur or valeur.count(".") != 2:
        return None
    compte, reste = valeur.split(".", 1)
    if not compte or not defis.cookie_valide(secret, USAGE_COOKIE, reste, _cle(monde, visiteur, compte), lie):
        return None
    return compte


def _identifiant_compte(cx: sqlite3.Connection, monde: str, compte: str, maintenant: datetime) -> int:
    monde_id = visiteurs.identifiant_monde(cx, monde)
    ligne = cx.execute("SELECT id FROM comptes WHERE monde_id = ? AND identifiant = ?", (monde_id, compte)).fetchone()
    if ligne is None:
        cx.execute(
            "INSERT OR IGNORE INTO comptes (monde_id, identifiant, cree_le) VALUES (?, ?, ?)",
            (monde_id, compte, _stamp(maintenant)),
        )
        ligne = cx.execute(
            "SELECT id FROM comptes WHERE monde_id = ? AND identifiant = ?", (monde_id, compte)
        ).fetchone()
    return int(ligne["id"])


def motif_bannissement(
    cx: sqlite3.Connection, monde: str, compte: str, maintenant: datetime | None = None
) -> str | None:
    """Le motif du bannissement en vigueur du compte dans `monde`, ou None."""
    return bannissements.compte_banni(cx, monde, compte, maintenant)


def connecter(
    cx: sqlite3.Connection,
    monde: str,
    visiteur: str,
    compte: str,
    seuils: Bannissement,
    maintenant: datetime | None = None,
) -> Connexion:
    """Une connexion réussie (identifiants justes, compte non banni) de `visiteur` à `compte` dans `monde`.

    Note l'appareil (nouveau ou non) ; puis la règle « nouvel appareil » : plus de `seuils.appareils_par_jour`
    appareils distincts connectés dans les 24 dernières heures, celui-ci compris, et le compte est banni (sauf dans un
    monde partagé). Une connexion refusée ainsi garde sa ligne d'appareil, sans durée de connexion. Horloge injectable.
    """
    maintenant = maintenant or datetime.now(UTC)
    compte_id = _identifiant_compte(cx, monde, compte, maintenant)
    connu = cx.execute(
        "SELECT id FROM appareils WHERE compte_id = ? AND visiteur = ?", (compte_id, visiteur)
    ).fetchone()
    autres = cx.execute(
        "SELECT COUNT(*) FROM appareils WHERE compte_id = ? AND visiteur != ?", (compte_id, visiteur)
    ).fetchone()[0]
    recents = cx.execute(
        "SELECT COUNT(*) FROM appareils WHERE compte_id = ? AND visiteur != ? AND derniere_connexion_le > ?",
        (compte_id, visiteur, _stamp(maintenant - JOUR)),
    ).fetchone()[0]
    appareils_24h = recents + 1
    motif = MOTIF_APPAREILS if appareils_24h > seuils.appareils_par_jour else None
    if motif and monde in bannissements.MONDES_SANS_BANNISSEMENT_AUTO:
        motif = None
    jusqu_au = None if motif else _stamp(maintenant + timedelta(seconds=seuils.duree_connexion_s))
    if connu is None:
        cx.execute(
            "INSERT INTO appareils (compte_id, visiteur, nouvel_appareil, premiere_connexion_le, derniere_connexion_le,"
            " connecte_jusqu_au) VALUES (?, ?, ?, ?, ?, ?)",
            (compte_id, visiteur, int(autres > 0), _stamp(maintenant), _stamp(maintenant), jusqu_au),
        )
    else:
        cx.execute(
            "UPDATE appareils SET derniere_connexion_le = ?, connecte_jusqu_au = ? WHERE id = ?",
            (_stamp(maintenant), jusqu_au, connu["id"]),
        )
    if motif:
        bannissements.bannir(cx, monde, compte=compte, motif=motif, maintenant=maintenant)
    return Connexion(connu is None and autres > 0, appareils_24h, motif)


def deconnecter(
    cx: sqlite3.Connection, monde: str, visiteur: str, compte: str, maintenant: datetime | None = None
) -> None:
    """Le visiteur se déconnecte du compte : sa connexion ne vaut plus (un bannissement de ce visiteur ne touchera plus
    le compte)."""
    cx.execute(
        "UPDATE appareils SET connecte_jusqu_au = ? WHERE visiteur = ? AND compte_id ="
        " (SELECT c.id FROM comptes c JOIN mondes m ON m.id = c.monde_id WHERE m.nom = ? AND c.identifiant = ?)",
        (_stamp(maintenant or datetime.now(UTC)), visiteur, monde, compte),
    )


def bannir_compte_connu(
    cx: sqlite3.Connection, monde: str, compte: str, *, motif: str = bannissements.MOTIF_MANUEL
) -> bool:
    """Bannissement manuel d'un compte DÉJÀ CONNECTÉ au moins une fois dans `monde` : `shadowlab arena bannir --compte`
    et `bannir_avant_visite` d'une campagne dont le bras a un compte. Refuse (`BannissementRefuse`) un monde inconnu ou
    un compte jamais vu dans ce monde, sans rien créer. Vrai si une ligne est écrite, faux s'il était déjà banni."""
    ligne = cx.execute("SELECT id FROM mondes WHERE nom = ?", (monde,)).fetchone()
    if ligne is None:
        raise bannissements.BannissementRefuse(f"monde inconnu : {monde}")
    vu = cx.execute("SELECT 1 FROM comptes WHERE monde_id = ? AND identifiant = ?", (ligne["id"], compte)).fetchone()
    if vu is None:
        raise bannissements.BannissementRefuse(f"compte inconnu dans le monde {monde} : {compte}")
    return bannissements.bannir(cx, monde, compte=compte, motif=motif)
