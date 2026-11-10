"""Gestion du challenge Turnstile Cloudflare (test keys).

En mode test (site key 1x00000000000000000000AA), le widget Turnstile
s'auto-valide. On attend que le token apparaisse (via le callback ou le champ
hidden), puis on soumet le formulaire et on vérifie que la page de challenge
a bien disparu.

⚠️ Test keys uniquement. Résultat étiqueté captcha_test (D-16).
"""

from __future__ import annotations

import logging
import time

log = logging.getLogger(__name__)

TIMEOUT_TURNSTILE_S = 30.0
SELECTEUR_FORM = 'form[action*="turnstile/verifier"]'


def _token_pret(page) -> bool:
    """Vérifie si le token Turnstile est prêt par deux signaux (le plus rapide gagne)."""
    try:
        etat = page.evaluate("document.getElementById('turnstile-etat')?.textContent || ''")
        if "reçue" in etat.lower():
            return True
    except Exception:
        pass
    try:
        tokens = page.eval_on_selector_all(
            'input[name="cf-turnstile-response"]',
            "els => els.map(e => e.value).filter(v => v.length > 0)",
        )
        if tokens:
            return True
    except Exception:
        pass
    return False


def resoudre(page, souris=None, timeout: float = TIMEOUT_TURNSTILE_S) -> bool:
    """Attend le widget Turnstile, laisse l'auto-validation se faire, soumet.

    Détection du token par deux signaux (le plus rapide gagne) :

    - ``#turnstile-etat`` contient « reçue » (callback Arena ``turnstileOk``)
    - ``input[name="cf-turnstile-response"]`` a une valeur non vide

    Après soumission, attend la disparition de ``data-arena="turnstile"``
    sur le ``<body>`` — fonctionne que le challenge soit inline ou sur une page
    dédiée (D-44).

    Args:
        page: Page Playwright/Patchright.
        souris: SimulateurSouris optionnel pour un mouvement réaliste vers le submit.
        timeout: Temps maximum d'attente pour le token (défaut 30 s).
    """
    debut = time.monotonic()

    while time.monotonic() - debut < timeout:
        if _token_pret(page):
            log.debug("Token Turnstile reçu en %.1fs", time.monotonic() - debut)
            break
        time.sleep(0.3)
    else:
        log.warning("Token Turnstile non reçu en %.0fs", timeout)
        return False

    time.sleep(0.2 + __import__("random").uniform(0.1, 0.4))
    try:
        selecteur = "#turnstile-envoyer"
        bouton = page.query_selector(selecteur)
        if not bouton:
            selecteur = f'{SELECTEUR_FORM} button[type="submit"]'
            bouton = page.query_selector(selecteur)
        if bouton and souris:
            souris.deplacer_vers_element(selecteur)
            time.sleep(0.05 + __import__("random").uniform(0.02, 0.08))
        if bouton:
            bouton.click()
        else:
            page.eval_on_selector(SELECTEUR_FORM, "f => f.submit()")
    except Exception:
        try:
            page.eval_on_selector(SELECTEUR_FORM, "f => f.submit()")
        except Exception:
            log.warning("Impossible de soumettre le formulaire Turnstile")
            return False

    limite = time.monotonic() + 10.0
    while time.monotonic() < limite:
        try:
            arena = page.evaluate("document.body?.dataset?.arena || ''")
            if arena != "turnstile":
                log.debug("Challenge Turnstile résolu (%.1fs total)", time.monotonic() - debut)
                return True
        except Exception:
            pass
        time.sleep(0.3)

    log.warning("Turnstile : page de challenge toujours présente après soumission")
    return False
