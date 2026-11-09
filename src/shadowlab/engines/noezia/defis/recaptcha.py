"""Gestion du challenge reCAPTCHA v2 Google (test keys).

En mode test (site key 6LeIxAcTAAAAAJcZVRqyHh71UMIEGNQ_MXjiZKhI), la checkbox
"I'm not a robot" se valide au clic sans puzzle d'image.

⚠️ Test keys uniquement. Résultat étiqueté captcha_test (D-16).
"""

from __future__ import annotations

import logging
import time

log = logging.getLogger(__name__)

TIMEOUT_RECAPTCHA_S = 15.0
SELECTEUR_IFRAME = 'iframe[src*="recaptcha"]'
SELECTEUR_FORM = 'form[action*="recaptcha/verifier"]'


def resoudre(page, souris=None, timeout: float = TIMEOUT_RECAPTCHA_S) -> bool:
    """Clique sur la checkbox reCAPTCHA, attend la validation, soumet.

    Args:
        page: Page Playwright/Patchright.
        souris: SimulateurSouris optionnel.
        timeout: Temps maximum d'attente.
    """
    debut = time.monotonic()

    # Attendre l'iframe reCAPTCHA
    try:
        page.wait_for_selector(SELECTEUR_IFRAME, timeout=timeout * 1000)
    except Exception:
        log.warning("Iframe reCAPTCHA non trouvée en %.0fs", timeout)
        return False

    time.sleep(0.3 + __import__("random").uniform(0.1, 0.5))

    # Trouver et cliquer la checkbox dans l'iframe
    frames = page.frames
    recaptcha_frame = None
    for f in frames:
        if "recaptcha" in (f.url or ""):
            recaptcha_frame = f
            break

    if recaptcha_frame is None:
        log.warning("Frame reCAPTCHA non trouvée")
        return False

    try:
        checkbox = recaptcha_frame.wait_for_selector(
            ".recaptcha-checkbox-border, #recaptcha-anchor",
            timeout=5000,
        )
        if checkbox:
            # Mouvement vers la checkbox si on a le simulateur
            if souris:
                box = checkbox.bounding_box()
                if box:
                    cx = box["x"] + box["width"] / 2
                    cy = box["y"] + box["height"] / 2
                    souris.deplacer_vers(cx, cy, largeur_cible=box["width"])
                    time.sleep(0.05 + __import__("random").uniform(0.02, 0.08))
            checkbox.click()
            log.debug("Checkbox reCAPTCHA cliquée")
    except Exception as e:
        log.warning("Clic checkbox reCAPTCHA échoué : %s", e)
        return False

    # Attendre que le token apparaisse
    while time.monotonic() - debut < timeout:
        token = page.eval_on_selector_all(
            'textarea[name="g-recaptcha-response"]',
            "els => els.map(e => e.value).filter(v => v.length > 0)",
        )
        if token:
            log.debug("Token reCAPTCHA reçu en %.1fs", time.monotonic() - debut)
            break
        time.sleep(0.3)
    else:
        log.warning("Token reCAPTCHA non reçu")
        return False

    # Soumettre
    time.sleep(0.2 + __import__("random").uniform(0.1, 0.3))
    try:
        if souris:
            souris.deplacer_vers_element(f'{SELECTEUR_FORM} button[type="submit"]')
        page.click(f'{SELECTEUR_FORM} button[type="submit"]')
    except Exception:
        page.eval_on_selector(SELECTEUR_FORM, "f => f.submit()")

    log.debug("Formulaire reCAPTCHA soumis")
    return True
