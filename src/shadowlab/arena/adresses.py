"""Adresses IP simulées de l'Arena (palier 4, étape 4.1, D-105).

Le frontal de l'Arena n'a, derrière la boucle locale, qu'une adresse de pair : 127.0.0.1, toujours. Pour qu'une
identité arrive « d'ailleurs », il accepte l'en-tête du protocole PROXY (v1 texte et v2 binaire) **d'un pair en boucle
locale seulement, et seulement si le réglage `proxy_protocole` est vrai** (éteint par défaut). L'adresse déclarée
descend vers le site dans `X-ShadowLab-Adresse`, signée par `X-ShadowLab-Adresse-Sceau` (liée à l'observation et
au jeton de la requête) : le site ne croit que cette adresse signée. Un client ne peut rien forger : le frontal retire
tous les en-têtes d'adresse du client (`X-ShadowLab-*`, `X-Forwarded-For`, `X-Real-IP`, `Forwarded`) et en pose
lui-même.

Refus : un en-tête PROXY qu'on n'accepte pas (réglage éteint, pair non local, mal formé) **coupe la connexion**. On ne
peut pas « l'ignorer » : il faut le lire pour retrouver le début de la poignée de main TLS, et deviner la fin d'un
en-tête mal formé reviendrait à croire un octet de plus que le client n'avait le droit d'envoyer. Couper est aussi ce
que fait le frontal d'avant devant un premier octet qui n'est pas du TLS : rien ne change quand le réglage est éteint.
"""

from __future__ import annotations

import ipaddress
import socket

from . import secret as secrets_arena

ENTETE = "X-ShadowLab-Adresse"
ENTETE_SCEAU = "X-ShadowLab-Adresse-Sceau"
USAGE = "adresse"
SIGNATURE_V2 = b"\r\n\r\n\x00\r\nQUIT\n"
# Ligne v1 la plus longue permise par la spécification (« PROXY TCP6 », deux adresses de 39 caractères, fin de ligne).
TAILLE_MAX_V1 = 107
TAILLE_MAX_V2 = 536  # 16 octets d'en-tête et jusqu'à 520 d'adresses et de TLV : plus, ce n'est pas un proxy
FAMILLES_V1 = {"TCP4": ipaddress.IPv4Address, "TCP6": ipaddress.IPv6Address}


class ProxyRefuse(ValueError):
    """Un en-tête PROXY qu'on ne croit pas : la connexion est coupée."""


def est_local(pair: str) -> bool:
    """Le pair est-il en boucle locale (127.0.0.0/8, ::1, ou ::ffff:127.x) ? Un texte illisible n'est pas local."""
    try:
        adresse = ipaddress.ip_address(pair)
    except ValueError:
        return False
    if isinstance(adresse, ipaddress.IPv6Address) and adresse.ipv4_mapped is not None:
        adresse = adresse.ipv4_mapped
    return adresse.is_loopback


def normaliser(texte: str) -> str | None:
    """L'adresse sous sa seule forme canonique, ou None si ce n'est pas l'adresse d'un visiteur.

    Une adresse IPv4 écrite en IPv6 (`::ffff:a.b.c.d`) devient `a.b.c.d`. Non spécifiée (`0.0.0.0`, `::`) et multicast :
    refusées. Pas d'espace ni de saut de ligne autour : un texte qui n'est pas exactement une adresse n'en est pas
    une."""
    if not isinstance(texte, str) or texte != texte.strip():
        return None
    try:
        adresse = ipaddress.ip_address(texte)
    except ValueError:
        return None
    if isinstance(adresse, ipaddress.IPv6Address) and adresse.ipv4_mapped is not None:
        adresse = adresse.ipv4_mapped
    if adresse.is_unspecified or adresse.is_multicast:
        return None
    return str(adresse)


def signer(secret: bytes, observation: str, jeton: str, adresse: str) -> str:
    """Le sceau de l'adresse : lié à l'observation et au jeton, donc rejouable sur aucune autre requête."""
    return secrets_arena.signer(secret, USAGE, observation, jeton, adresse)


def verifier(secret: bytes, signature: str, observation: str, jeton: str, adresse: str) -> bool:
    return secrets_arena.verifier(secret, signature, USAGE, observation, jeton, adresse)


# --- Lecture de l'en-tête PROXY ------------------------------------------------------------------------------


def _exactement(prise: socket.socket, nombre: int) -> bytes:
    """Lit exactement `nombre` octets : ni plus (le ClientHello qui suit reste intact), ni moins."""
    morceaux = bytearray()
    while len(morceaux) < nombre:
        try:
            recu = prise.recv(nombre - len(morceaux))
        except (TimeoutError, OSError):
            raise ProxyRefuse("en-tête PROXY incomplet") from None
        if not recu:
            raise ProxyRefuse("en-tête PROXY incomplet")
        morceaux += recu
    return bytes(morceaux)


def _ligne_v1(prise: socket.socket) -> bytes:
    """La ligne de l'en-tête v1, lue octet par octet jusqu'à `\\r\\n` : rien du ClientHello n'est consommé."""
    ligne = bytearray(_exactement(prise, 6))
    if bytes(ligne) != b"PROXY ":
        raise ProxyRefuse("en-tête PROXY v1 : début inattendu")
    while not ligne.endswith(b"\r\n"):
        if len(ligne) >= TAILLE_MAX_V1:
            raise ProxyRefuse("en-tête PROXY v1 trop long")
        ligne += _exactement(prise, 1)
    return bytes(ligne[:-2])


def _declaree(source: str, famille) -> str:
    try:
        adresse = famille(source)
    except ValueError:
        raise ProxyRefuse("adresse source de l'en-tête PROXY illisible") from None
    normale = normaliser(str(adresse))
    if normale is None:
        raise ProxyRefuse("adresse source de l'en-tête PROXY refusée")
    return normale


def _lire_v1(prise: socket.socket) -> str | None:
    champs = _ligne_v1(prise).decode("ascii", errors="replace").split(" ")
    if champs[1:2] == ["UNKNOWN"]:
        return None  # le proxy ne sait pas : on garde l'adresse du pair
    if len(champs) != 6 or champs[0] != "PROXY" or champs[1] not in FAMILLES_V1:
        raise ProxyRefuse("en-tête PROXY v1 mal formé")
    famille = FAMILLES_V1[champs[1]]
    _declaree(champs[3], famille)  # la destination doit être de la même famille, lisible aussi
    for port in champs[4:]:
        if not port.isascii() or not port.isdigit() or not 0 <= int(port) <= 65535:
            raise ProxyRefuse("port de l'en-tête PROXY v1 impossible")
    return _declaree(champs[2], famille)


def _lire_v2(prise: socket.socket) -> str | None:
    tete = _exactement(prise, 16)
    if tete[:12] != SIGNATURE_V2:
        raise ProxyRefuse("en-tête PROXY v2 : signature fausse")
    version, commande = tete[12] >> 4, tete[12] & 0x0F
    famille, protocole = tete[13] >> 4, tete[13] & 0x0F
    longueur = int.from_bytes(tete[14:16], "big")
    if version != 2 or commande not in (0, 1) or 16 + longueur > TAILLE_MAX_V2:
        raise ProxyRefuse("en-tête PROXY v2 mal formé")
    corps = _exactement(prise, longueur) if longueur else b""
    if commande == 0 or protocole != 1 or famille not in (1, 2):
        return None  # LOCAL (sonde), ou autre chose que du TCP sur IP : l'adresse du pair reste
    taille = 12 if famille == 1 else 36
    if len(corps) < taille:
        raise ProxyRefuse("en-tête PROXY v2 trop court pour sa famille")
    moitie = 4 if famille == 1 else 16
    type_adresse = ipaddress.IPv4Address if famille == 1 else ipaddress.IPv6Address
    return _declaree(str(type_adresse(corps[:moitie])), type_adresse)


def lire_entete_proxy(prise: socket.socket, pair: str, *, actif: bool) -> str | None:
    """Lit, s'il y en a un, l'en-tête PROXY au début de la connexion ; rend l'adresse déclarée.

    Rend None quand il n'y a pas d'en-tête (le premier octet est celui d'une poignée de main TLS : rien n'est consommé),
    ou quand l'en-tête ne déclare aucune adresse (`UNKNOWN`, `LOCAL`) : l'adresse est alors celle du pair. Lève
    `ProxyRefuse` pour un en-tête qu'on ne croit pas : réglage éteint, pair qui n'est pas en boucle locale, mal formé,
    incomplet (la prise a un délai), trop long. L'appelant coupe alors la connexion.
    """
    try:
        premier = prise.recv(1, socket.MSG_PEEK)
    except (TimeoutError, OSError):
        return None  # rien reçu : la lecture du ClientHello échouera comme avant
    if not premier or premier[0] not in (ord("P"), SIGNATURE_V2[0]):
        return None  # TLS (0x16), ou n'importe quoi d'autre : `tls.lire_client_hello` tranche, comme avant
    if not actif:
        raise ProxyRefuse("en-tête PROXY reçu alors que le réglage est éteint")
    if not est_local(pair):
        raise ProxyRefuse("en-tête PROXY d'un pair qui n'est pas en boucle locale")
    return _lire_v2(prise) if premier[0] == SIGNATURE_V2[0] else _lire_v1(prise)
