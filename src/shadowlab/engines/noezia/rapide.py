"""Récupération browserless furtive : fetch HTTP imitant le TLS d'un vrai navigateur + parser adaptatif.

L'équivalent du « StealthyFetcher » de Scrapling, sans navigateur : curl_cffi rejoue la pile TLS/HTTP2
d'un vrai Chrome (`impersonate`), donc on passe la détection au niveau TLS, le tout **sans lancer de
navigateur** → ultra-rapide. Le HTML revient dans un `Analyseur` (css/xpath + extraction adaptative).

Le périmètre est respecté comme pour les moteurs navigateur : chaque saut (y compris les redirections)
est contrôlé par `verifier_url`, jamais suivi à l'aveugle (cf. piège D-07).
"""

from __future__ import annotations

from urllib.parse import urljoin

from ...config import charger
from ...perimetre import verifier_url
from .analyseur import Analyseur
from .extraction import Signatures

IMPERSONATE_DEFAUT = "chrome"
REDIRECTIONS_MAX = 10


def recuperer(
    url: str,
    impersonate: str = IMPERSONATE_DEFAUT,
    signatures: Signatures | None = None,
    hotes: tuple[str, ...] | None = None,
    timeout: float = 30.0,
    verifier_tls: bool = True,
) -> Analyseur:
    """Récupère `url` en HTTP furtif (TLS d'un vrai navigateur, sans JS) et rend un `Analyseur`.

    Les redirections sont suivies **à la main**, chacune re-contrôlée par le périmètre : une URL
    autorisée ne peut pas rediriger hors périmètre sans être refusée. Lève `DestinationRefusee` si une
    destination sort du périmètre, `RuntimeError` au-delà de `REDIRECTIONS_MAX` sauts.

    `hotes` par défaut = le périmètre **configuré** (`SHADOWLAB_HOTES_AUTORISES`), pour se durcir avec
    la config. `verifier_tls` est vrai par défaut (sécurisé) ; ne le passer à faux que pour un cert
    auto-signé connu, comme l'Arena locale.
    """
    if hotes is None:
        hotes = charger().hotes_autorises
    from curl_cffi import requests

    finale, reponse = url, None
    for _ in range(REDIRECTIONS_MAX + 1):
        verifier_url(finale, hotes)
        reponse = requests.get(
            finale, impersonate=impersonate, timeout=timeout, verify=verifier_tls, allow_redirects=False
        )
        cible = reponse.headers.get("location")
        if reponse.status_code in (301, 302, 303, 307, 308) and cible:
            finale = urljoin(finale, cible)
            continue
        break
    else:
        raise RuntimeError(f"trop de redirections ({finale})")
    return Analyseur(reponse.text, url=finale, signatures=signatures)
