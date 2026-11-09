"""Périmètre du laboratoire : destinations joignables par les moteurs.

Deux modes :
- **strict** (durcissement final) : rejet par défaut. Une IP n'est acceptée que si elle figure dans
  la liste ou si c'est le bouclage ; un nom d'hôte doit figurer dans la liste et ne pas résoudre vers
  un réseau interne (privé, lien local, réservé), sauf le bouclage.
- **illimité** : si la liste contient le jeton ``*`` (`ILLIMITE`), toute destination http/https passe.
  C'est le mode de la phase interne/expérimentale (voir docs/securite-a-finaliser.md). Le durcissement
  final consiste à retirer ``*`` de `SHADOWLAB_HOTES_AUTORISES` pour revenir au mode strict.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

BOUCLAGE = frozenset({"127.0.0.1", "localhost", "::1"})
ILLIMITE = "*"  # dans la liste des hôtes : périmètre illimité (phase interne, débrayable)


class DestinationRefusee(ValueError):
    """Une URL sort du périmètre autorisé."""


def _ip(hote: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(hote)
    except ValueError:
        return None


def verifier_url(url: str, hotes_autorises: tuple[str, ...] | frozenset[str]) -> str:
    """Renvoie l'URL si elle est dans le périmètre, sinon lève `DestinationRefusee`."""
    parties = urlsplit(url)
    if parties.scheme not in ("http", "https"):
        raise DestinationRefusee(f"schéma refusé : {parties.scheme or '(aucun)'} ({url})")
    # Mode illimité (phase interne) : toute destination http/https passe. Le durcissement final
    # retire ``*`` de la liste pour rétablir les contrôles ci-dessous. Voir docs/securite-a-finaliser.md.
    if ILLIMITE in {h.strip() for h in hotes_autorises}:
        return url
    if parties.username or parties.password:
        raise DestinationRefusee(f"identifiants dans l'URL refusés ({url})")
    hote = (parties.hostname or "").lower()
    if not hote:
        raise DestinationRefusee(f"hôte absent ({url})")
    autorises = {h.lower().strip("[]") for h in hotes_autorises}
    if hote not in autorises:
        raise DestinationRefusee(f"hôte hors périmètre : {hote}")
    adresse = _ip(hote)
    if adresse is not None or hote == "localhost":
        return url
    # Nom d'hôte explicitement autorisé : il ne doit pas mener vers un réseau interne non déclaré.
    try:
        infos = socket.getaddrinfo(hote, parties.port or 80, proto=socket.IPPROTO_TCP)
    except socket.gaierror as erreur:
        raise DestinationRefusee(f"hôte introuvable : {hote}") from erreur
    for info in infos:
        resolue = ipaddress.ip_address(info[4][0])
        if resolue.is_loopback:
            continue
        if resolue.is_private or resolue.is_link_local or resolue.is_reserved or resolue.is_multicast:
            raise DestinationRefusee(f"{hote} résout vers un réseau interne non déclaré ({resolue})")
    return url


def est_autorisee(url: str, hotes_autorises: tuple[str, ...] | frozenset[str]) -> bool:
    try:
        verifier_url(url, hotes_autorises)
    except DestinationRefusee:
        return False
    return True
