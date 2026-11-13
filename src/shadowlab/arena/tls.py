"""Lecture du ClientHello TLS et calcul des empreintes JA3 et JA4.

JA3 : https://github.com/salesforce/ja3 — JA4 : https://github.com/FoxIO-LLC/ja4 (spécification technique).
Le ClientHello est lu sans être consommé (`MSG_PEEK`) : la poignée de main TLS se déroule ensuite normalement.
"""

from __future__ import annotations

import hashlib
import socket
import time
from dataclasses import dataclass, field
from typing import Any

VERSIONS_JA4 = {0x0304: "13", 0x0303: "12", 0x0302: "11", 0x0301: "10", 0x0300: "s3", 0x0002: "s2"}
EXT_SNI, EXT_GROUPES, EXT_FORMATS_EC, EXT_SIGNATURES, EXT_ALPN, EXT_VERSIONS = 0, 10, 11, 13, 16, 43
# Ajoutée par un client qui reprend sa session TLS 1.3 : le même client en porte une de plus (mesuré, campagne 106).
EXT_PRE_SHARED_KEY = 41
TAILLE_MAX = 64 * 1024


class TlsIllisible(ValueError):
    """Les octets reçus ne sont pas un ClientHello TLS lisible."""


def est_grease(valeur: int) -> bool:
    """Valeurs GREASE (RFC 8701) : 0x0a0a, 0x1a1a … 0xfafa, envoyées pour tester la tolérance des serveurs."""
    return (valeur & 0x0F0F) == 0x0A0A and (valeur >> 8) == (valeur & 0xFF)


@dataclass
class ClientHello:
    version_legacy: int
    ciphers: list[int] = field(default_factory=list)
    extensions: list[int] = field(default_factory=list)
    sni: str | None = None
    alpn: list[str] = field(default_factory=list)
    groupes: list[int] = field(default_factory=list)
    formats_ec: list[int] = field(default_factory=list)
    signatures: list[int] = field(default_factory=list)
    versions: list[int] = field(default_factory=list)

    @property
    def grease(self) -> bool:
        return any(est_grease(v) for v in (*self.ciphers, *self.extensions, *self.groupes, *self.versions))


class _Lecteur:
    def __init__(self, donnees: bytes) -> None:
        self.donnees, self.position = donnees, 0

    def octets(self, n: int) -> bytes:
        if self.position + n > len(self.donnees):
            raise TlsIllisible("ClientHello tronqué")
        morceau = self.donnees[self.position : self.position + n]
        self.position += n
        return morceau

    def entier(self, n: int) -> int:
        return int.from_bytes(self.octets(n), "big")

    def bloc(self, taille_longueur: int) -> _Lecteur:
        return _Lecteur(self.octets(self.entier(taille_longueur)))

    @property
    def fini(self) -> bool:
        return self.position >= len(self.donnees)

    def entiers16(self) -> list[int]:
        valeurs = []
        while not self.fini:
            valeurs.append(self.entier(2))
        return valeurs


def _extension(hello: ClientHello, type_ext: int, corps: _Lecteur) -> None:
    if type_ext == EXT_SNI:
        noms = corps.bloc(2)
        while not noms.fini:
            type_nom = noms.entier(1)
            nom = noms.bloc(2)
            if type_nom == 0:
                hello.sni = nom.donnees.decode("ascii", "replace")
    elif type_ext == EXT_GROUPES:
        hello.groupes = corps.bloc(2).entiers16()
    elif type_ext == EXT_FORMATS_EC:
        hello.formats_ec = list(corps.bloc(1).donnees)
    elif type_ext == EXT_SIGNATURES:
        hello.signatures = corps.bloc(2).entiers16()
    elif type_ext == EXT_ALPN:
        protocoles = corps.bloc(2)
        while not protocoles.fini:
            hello.alpn.append(protocoles.bloc(1).donnees.decode("ascii", "replace"))
    elif type_ext == EXT_VERSIONS:
        hello.versions = corps.bloc(1).entiers16()


def analyser(enregistrements: bytes) -> ClientHello:
    """Analyse un ou plusieurs enregistrements TLS contenant un ClientHello."""
    charge = bytearray()
    position = 0
    while position + 5 <= len(enregistrements):
        if enregistrements[position] != 22:
            break
        longueur = int.from_bytes(enregistrements[position + 3 : position + 5], "big")
        charge += enregistrements[position + 5 : position + 5 + longueur]
        position += 5 + longueur
    lecteur = _Lecteur(bytes(charge))
    if lecteur.entier(1) != 1:
        raise TlsIllisible("pas un ClientHello")
    corps = lecteur.bloc(3)
    hello = ClientHello(version_legacy=corps.entier(2))
    corps.octets(32)  # aléa du client
    corps.bloc(1)  # identifiant de session
    hello.ciphers = corps.bloc(2).entiers16()
    corps.bloc(1)  # méthodes de compression
    if not corps.fini:
        extensions = corps.bloc(2)
        while not extensions.fini:
            type_ext = extensions.entier(2)
            contenu = extensions.bloc(2)
            hello.extensions.append(type_ext)
            _extension(hello, type_ext, contenu)
    return hello


def lire_client_hello(prise: socket.socket, delai: float = 5.0) -> bytes:
    """Lit les enregistrements du ClientHello sans les consommer."""
    limite = time.monotonic() + delai
    while True:
        tampon = prise.recv(TAILLE_MAX, socket.MSG_PEEK)
        if not tampon:
            raise TlsIllisible("connexion fermée avant le ClientHello")
        if tampon[0] != 22:
            raise TlsIllisible("pas une poignée de main TLS")
        if _complet(tampon):
            return tampon
        if time.monotonic() > limite or len(tampon) >= TAILLE_MAX:
            raise TlsIllisible("ClientHello incomplet")
        time.sleep(0.002)


def _complet(tampon: bytes) -> bool:
    """Vrai si le message de poignée de main est entièrement arrivé (il peut tenir sur plusieurs enregistrements)."""
    position, charge = 0, 0
    attendu = None
    while position + 5 <= len(tampon):
        longueur = int.from_bytes(tampon[position + 3 : position + 5], "big")
        if position + 5 + longueur > len(tampon):
            return False
        if attendu is None and longueur >= 4:
            attendu = 4 + int.from_bytes(tampon[position + 6 : position + 9], "big")
        charge += longueur
        position += 5 + longueur
        if attendu is not None and charge >= attendu:
            return True
    return False


def ja3(hello: ClientHello) -> str:
    """Chaîne JA3 : version, chiffrements, extensions, groupes, formats (décimal, sans GREASE, ordre d'envoi)."""

    def liste(valeurs: list[int]) -> str:
        return "-".join(str(v) for v in valeurs if not est_grease(v))

    formats = "-".join(str(v) for v in hello.formats_ec)
    return f"{hello.version_legacy},{liste(hello.ciphers)},{liste(hello.extensions)},{liste(hello.groupes)},{formats}"


def _hache12(texte: str) -> str:
    return hashlib.sha256(texte.encode()).hexdigest()[:12] if texte else "000000000000"


def ja4(hello: ClientHello, sans_extensions: frozenset[int] = frozenset()) -> str:
    """Empreinte JA4 du ClientHello (toujours `t` : TLS sur TCP). `sans_extensions` en retire avant le calcul."""
    ciphers = [v for v in hello.ciphers if not est_grease(v)]
    extensions = [v for v in hello.extensions if not est_grease(v) and v not in sans_extensions]
    versions = [v for v in hello.versions if not est_grease(v)]
    version = VERSIONS_JA4.get(max(versions) if versions else hello.version_legacy, "00")
    sni = "d" if EXT_SNI in extensions else "i"
    alpn = "00"
    if hello.alpn and hello.alpn[0]:
        premier = hello.alpn[0]
        if premier[0].isalnum() and premier[-1].isalnum() and premier.isascii():
            alpn = premier[0] + premier[-1]
        else:
            brut = premier.encode("latin-1", "replace").hex()
            alpn = brut[0] + brut[-1]
    partie_a = f"t{version}{sni}{min(len(ciphers), 99):02d}{min(len(extensions), 99):02d}{alpn}"
    partie_b = _hache12(",".join(f"{v:04x}" for v in sorted(ciphers)))
    exts = ",".join(f"{v:04x}" for v in sorted(extensions) if v not in (EXT_SNI, EXT_ALPN))
    signatures = ",".join(f"{v:04x}" for v in hello.signatures if not est_grease(v))
    partie_c = _hache12(f"{exts}_{signatures}" if signatures else exts)
    return f"{partie_a}_{partie_b}_{partie_c}"


def ja4_liaison(hello: ClientHello) -> str:
    """JA4 sans `pre_shared_key` : identique pour un même client avec ou sans reprise de session TLS.

    C'est la valeur à laquelle les cookies de défi sont liés ; le JA4 complet reste celui qui est enregistré."""
    return ja4(hello, frozenset({EXT_PRE_SHARED_KEY}))


def empreinte(hello: ClientHello) -> dict[str, Any]:
    chaine = ja3(hello)
    return {
        "ja3": chaine,
        "ja3_hash": hashlib.md5(chaine.encode(), usedforsecurity=False).hexdigest(),
        "ja4": ja4(hello),
        "liaison": ja4_liaison(hello),
        "details": {
            "version_legacy": hello.version_legacy,
            "versions": [v for v in hello.versions if not est_grease(v)],
            "sni": hello.sni,
            "alpn": hello.alpn,
            "grease": hello.grease,
            "nb_chiffrements": len([v for v in hello.ciphers if not est_grease(v)]),
            "nb_extensions": len([v for v in hello.extensions if not est_grease(v)]),
            "chiffrements": [f"{v:04x}" for v in hello.ciphers if not est_grease(v)],
            "extensions": [f"{v:04x}" for v in hello.extensions if not est_grease(v)],
            "groupes": [f"{v:04x}" for v in hello.groupes if not est_grease(v)],
            "signatures": [f"{v:04x}" for v in hello.signatures if not est_grease(v)],
        },
    }
