"""Secret local de l'Arena : signe les cookies de défi et les en-têtes internes du frontal."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from pathlib import Path


def charger(dossier_arena: Path) -> bytes:
    """Lit le secret, ou le crée au premier appel (fichier lisible par son seul propriétaire, jamais versionné)."""
    chemin = dossier_arena / "secret"
    if not chemin.exists():
        dossier_arena.mkdir(parents=True, exist_ok=True)
        chemin.touch(mode=0o600)
        chemin.write_text(secrets.token_hex(32), encoding="ascii")
    return chemin.read_text(encoding="ascii").strip().encode()


def signer(secret: bytes, *parties: object) -> str:
    message = "\x1f".join(str(p) for p in parties).encode()
    return hmac.new(secret, message, hashlib.sha256).hexdigest()


def verifier(secret: bytes, signature: str, *parties: object) -> bool:
    return hmac.compare_digest(signature, signer(secret, *parties))
