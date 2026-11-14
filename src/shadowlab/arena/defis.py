"""Défi JavaScript (preuve de travail), CAPTCHA de démonstration, Turnstile et reCAPTCHA v2 (test mode).

Tout est sans état côté serveur : défis et cookies sont signés avec le secret local. Le CAPTCHA est une
démonstration : il mesure ce qui se passe quand une personne doit intervenir, pas la robustesse d'une image.
Le laboratoire ne contient aucun solveur : pour un robot, un CAPTCHA reste un challenge non validé.

Turnstile en mode test utilise les clés publiques Cloudflare (always-pass / always-block). Un résultat
réussi est étiqueté `captcha_test` (D-16) — ce n'est pas un contournement de CAPTCHA.
"""

from __future__ import annotations

import hashlib
import io
import random
import secrets as aleatoire
import time

import httpx

from . import secret as secrets_arena

DUREE_DEFI_S = 120
DUREE_COOKIE_S = 3600
ALPHABET_CAPTCHA = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # sans caractères ambigus (I, L, O, 0, 1)
LONGUEUR_CAPTCHA = 5


def creer_defi(secret: bytes, jeton: str, difficulte: int) -> str:
    alea, expiration = aleatoire.token_hex(8), int(time.time()) + DUREE_DEFI_S
    signature = secrets_arena.signer(secret, "defi", jeton, alea, expiration, difficulte)
    return f"{alea}.{expiration}.{difficulte}.{signature}"


def bits_nuls(empreinte: bytes) -> int:
    total = 0
    for octet in empreinte:
        if octet == 0:
            total += 8
            continue
        return total + (8 - octet.bit_length())
    return total


def verifier_defi(secret: bytes, jeton: str, defi: str, nonce: object) -> str | None:
    """None si la preuve est bonne, sinon le motif du refus."""
    try:
        alea, expiration, difficulte, signature = defi.split(".")
        expiration_n, difficulte_n = int(expiration), int(difficulte)
    except ValueError:
        return "defi_illisible"
    if not secrets_arena.verifier(secret, signature, "defi", jeton, alea, expiration_n, difficulte_n):
        return "signature_invalide"
    if expiration_n < time.time():
        return "defi_expire"
    if bits_nuls(hashlib.sha256(f"{defi}:{nonce}".encode()).digest()) < difficulte_n:
        return "preuve_insuffisante"
    return None


def creer_cookie(secret: bytes, usage: str, jeton: str, ja4: str = "", *, duree_s: int = DUREE_COOKIE_S) -> str:
    """Cookie de réussite, lié à la session et, si `ja4` est fourni, à l'empreinte TLS du client.

    `duree_s` : durée de vie signée dans la valeur (réglage `duree_cookie_s` du profil ; 3 600 s par défaut).
    """
    expiration = int(time.time()) + duree_s
    return f"{expiration}.{secrets_arena.signer(secret, usage, jeton, ja4, expiration)}"


def cookie_valide(secret: bytes, usage: str, valeur: str | None, jeton: str, ja4: str = "") -> bool:
    if not valeur or "." not in valeur:
        return False
    expiration, signature = valeur.split(".", 1)
    try:
        expiration_n = int(expiration)
    except ValueError:
        return False
    return expiration_n >= time.time() and secrets_arena.verifier(secret, signature, usage, jeton, ja4, expiration_n)


def creer_captcha(secret: bytes, jeton: str) -> str:
    alea, expiration = aleatoire.token_hex(8), int(time.time()) + DUREE_DEFI_S
    return f"{alea}.{expiration}.{secrets_arena.signer(secret, 'captcha', jeton, alea, expiration)}"


def _reponse(secret: bytes, alea: str) -> str:
    graine = hashlib.sha256(secret + b"captcha" + alea.encode()).digest()
    return "".join(ALPHABET_CAPTCHA[o % len(ALPHABET_CAPTCHA)] for o in graine[:LONGUEUR_CAPTCHA])


def verifier_captcha(secret: bytes, jeton: str, captcha: str, code: str) -> str | None:
    try:
        alea, expiration, signature = captcha.split(".")
        expiration_n = int(expiration)
    except ValueError:
        return "captcha_illisible"
    if not secrets_arena.verifier(secret, signature, "captcha", jeton, alea, expiration_n):
        return "signature_invalide"
    if expiration_n < time.time():
        return "captcha_expire"
    if code.strip().upper() != _reponse(secret, alea):
        return "code_faux"
    return None


def image_captcha(secret: bytes, jeton: str, captcha: str) -> bytes | None:
    """Image PNG du code : lettres tournées et traits parasites. None si le jeton n'est pas valable."""
    from PIL import Image, ImageDraw, ImageFont

    try:
        alea, expiration, signature = captcha.split(".")
        expiration_n = int(expiration)
    except ValueError:
        return None
    if not secrets_arena.verifier(secret, signature, "captcha", jeton, alea, expiration_n):
        return None
    code = _reponse(secret, alea)
    tirage = random.Random(alea)  # noqa: S311 — un dessin, pas de la cryptographie
    largeur, hauteur = 220, 80
    image = Image.new("RGB", (largeur, hauteur), (244, 244, 240))
    police = ImageFont.load_default(size=40)
    for rang, lettre in enumerate(code):
        calque = Image.new("RGBA", (56, 64), (0, 0, 0, 0))
        ImageDraw.Draw(calque).text((10, 6), lettre, font=police, fill=(30, 40, 70, 255))
        calque = calque.rotate(tirage.uniform(-28, 28), resample=Image.Resampling.BICUBIC)
        image.paste(calque, (10 + rang * 40, tirage.randint(2, 14)), calque)
    dessin = ImageDraw.Draw(image)
    for _ in range(7):
        depart = (tirage.randint(0, largeur), tirage.randint(0, hauteur))
        arrivee = (tirage.randint(0, largeur), tirage.randint(0, hauteur))
        dessin.line([depart, arrivee], fill=(120, 130, 150), width=1)
    sortie = io.BytesIO()
    image.save(sortie, format="PNG")
    return sortie.getvalue()


# --- Turnstile (Cloudflare, mode test) -----------------------------------------------------------
# Clés publiques documentées par Cloudflare : https://developers.cloudflare.com/turnstile/testing/
TURNSTILE_SITE_PASS = "1x00000000000000000000AA"
TURNSTILE_SECRET_PASS = "1x0000000000000000000000000000000AA"
TURNSTILE_SITE_BLOCK = "2x00000000000000000000AB"
TURNSTILE_SECRET_BLOCK = "2x0000000000000000000000000000000AB"
TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


def turnstile_site_key(mode: str = "pass") -> str:
    return TURNSTILE_SITE_PASS if mode == "pass" else TURNSTILE_SITE_BLOCK


def verifier_turnstile(token: str, mode: str = "pass") -> dict:
    """Vérifie un token Turnstile via l'API Cloudflare. Retourne le JSON de réponse."""
    secret = TURNSTILE_SECRET_PASS if mode == "pass" else TURNSTILE_SECRET_BLOCK
    try:
        r = httpx.post(TURNSTILE_VERIFY_URL, data={"secret": secret, "response": token}, timeout=10)
        return r.json()
    except Exception:
        return {"success": False, "error-codes": ["network_error"]}


# --- reCAPTCHA v2 (Google, mode test) --------------------------------------------------------------
# Clés publiques documentées par Google : https://developers.google.com/recaptcha/docs/faq
RECAPTCHA_SITE_KEY = "6LeIxAcTAAAAAJcZVRqyHh71UMIEGNQ_MXjiZKhI"
RECAPTCHA_SECRET_KEY = "6LeIxAcTAAAAAGG-vFI1TnRWxMZNFuojJ4WifJWe"
RECAPTCHA_VERIFY_URL = "https://www.google.com/recaptcha/api/siteverify"


def recaptcha_site_key() -> str:
    return RECAPTCHA_SITE_KEY


def verifier_recaptcha(token: str) -> dict:
    """Vérifie un token reCAPTCHA v2 via l'API Google. Retourne le JSON de réponse."""
    try:
        r = httpx.post(RECAPTCHA_VERIFY_URL, data={"secret": RECAPTCHA_SECRET_KEY, "response": token}, timeout=10)
        return r.json()
    except Exception:
        return {"success": False, "error-codes": ["network_error"]}
