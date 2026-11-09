"""Récupération browserless furtive : fetch HTTP imitant le TLS d'un vrai navigateur + parser adaptatif.

L'équivalent du « StealthyFetcher » de Scrapling, sans navigateur : curl_cffi rejoue la pile TLS/HTTP2
d'un vrai Chrome (`impersonate`), donc on passe la détection au niveau TLS, le tout **sans lancer de
navigateur** → ultra-rapide. Le HTML revient dans un `Analyseur` (css/xpath + extraction adaptative).

Le périmètre est respecté (`verifier_url`) comme pour les moteurs navigateur.
"""

from __future__ import annotations

from ...perimetre import verifier_url
from .analyseur import Analyseur
from .extraction import Signatures

IMPERSONATE_DEFAUT = "chrome"


def recuperer(
    url: str,
    impersonate: str = IMPERSONATE_DEFAUT,
    signatures: Signatures | None = None,
    hotes: tuple[str, ...] = ("*",),
    timeout: float = 30.0,
    verifier_tls: bool = True,
) -> Analyseur:
    """Récupère `url` en HTTP furtif (TLS d'un vrai navigateur, sans JS) et rend un `Analyseur`.

    Lève `DestinationRefusee` si l'URL sort du périmètre. Scraping browserless ultra-rapide avec
    extraction adaptative (le même `Signatures` que le moteur navigateur peut être partagé).

    `verifier_tls` est vrai par défaut (sécurisé) ; ne le passer à faux que pour un cert auto-signé
    connu, comme l'Arena locale.
    """
    verifier_url(url, hotes)
    from curl_cffi import requests

    reponse = requests.get(url, impersonate=impersonate, timeout=timeout, verify=verifier_tls)
    return Analyseur(reponse.text, url=url, signatures=signatures)
