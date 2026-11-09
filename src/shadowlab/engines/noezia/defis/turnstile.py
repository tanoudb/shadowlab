"""Gestion du challenge Turnstile Cloudflare (test keys).

En mode test (site key 1x00000000000000000000AA), le widget Turnstile
s'auto-valide. On attend son apparition, on lui laisse le temps de résoudre,
et on soumet le formulaire.

⚠️ Test keys uniquement. Résultat étiqueté captcha_test (D-16).
"""

from __future__ import annotations

import logging
import time

log = logging.getLogger(__name__)

TIMEOUT_TURNSTILE_S = 15.0
SELECTEUR_IFRAME = 'iframe[src*="challenges.cloudflare.com"]'
SELECTEUR_FORM = 'form[action*="turnstile/verifier"]'


def resoudre(page, souris=None, timeout: float = TIMEOUT_TURNSTILE_S) -> bool:
    """Attend le widget Turnstile, laisse l'auto-validation se faire, soumet.

    Args:
        page: Page Playwright/Patchright.
        souris: SimulateurSouris optionnel pour un mouvement réaliste vers le submit.
        timeout: Temps maximum d'attente.
    """
    debut = time.monotonic()

    # Attendre que l'iframe Turnstile apparaisse
    try:
        page.wait_for_selector(SELECTEUR_IFRAME, timeout=timeout * 1000)
    except Exception:
        log.warning("Iframe Turnstile non trouvée en %.0fs", timeout)
        return False

    # Attendre que le token soit rempli (champ hidden cf-turnstile-response)
    while time.monotonic() - debut < timeout:
        token = page.eval_on_selector_all(
            'input[name="cf-turnstile-response"]',
            "els => els.map(e => e.value).filter(v => v.length > 0)",
        )
        if token:
            log.debug("Token Turnstile reçu en %.1fs", time.monotonic() - debut)
            break
        time.sleep(0.3)
    else:
        log.warning("Token Turnstile non reçu en %.0fs", timeout)
        return False

    # Soumettre le formulaire
    time.sleep(0.2 + __import__("random").uniform(0.1, 0.4))
    try:
        bouton = page.query_selector(f'{SELECTEUR_FORM} button[type="submit"]')
        if bouton and souris:
            souris.deplacer_vers_element(f'{SELECTEUR_FORM} button[type="submit"]')
            time.sleep(0.05 + __import__("random").uniform(0.02, 0.08))
        page.click(f'{SELECTEUR_FORM} button[type="submit"]')
    except Exception:
        # Fallback : soumettre via JS
        page.eval_on_selector(SELECTEUR_FORM, "f => f.submit()")

    log.debug("Formulaire Turnstile soumis")
    return True
