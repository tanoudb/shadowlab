"""Résolution du défi JavaScript proof-of-work.

Le défi demande de trouver un nonce tel que SHA-256(défi:nonce) commence par
N bits nuls. On attend que le script côté client le résolve (il est conçu
pour tourner dans le navigateur), puis on suit la redirection.
"""

from __future__ import annotations

import logging
import time

log = logging.getLogger(__name__)

TIMEOUT_POW_S = 30.0


def attendre_resolution(page, timeout: float = TIMEOUT_POW_S) -> bool:
    """Attend que le défi PoW soit résolu et la redirection effectuée.

    Le script defi.js résout le PoW et appelle location.replace(retour).
    On attend que l'URL change (plus sur /lab/defi).
    """
    debut = time.monotonic()
    url_defi = page.url

    while time.monotonic() - debut < timeout:
        url_actuelle = page.url
        if "/lab/defi" not in url_actuelle and url_actuelle != url_defi:
            log.debug("PoW résolu en %.1fs", time.monotonic() - debut)
            return True
        time.sleep(0.2)

    log.warning("PoW non résolu en %.0fs", timeout)
    return False
