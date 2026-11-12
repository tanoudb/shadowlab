"""Secret local de l'Arena : signe les cookies de défi et les en-têtes internes du frontal."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from pathlib import Path


def charger(dossier_arena: Path) -> bytes:
    """Lit le secret, ou le crée au premier appel (fichier lisible par son seul propriétaire, jamais versionné).

    Une clé vide rendrait toutes les signatures forgeables : elle est refusée. La création est atomique (un
    autre processus ne voit jamais le fichier vide entre sa création et son écriture).
    """
    chemin = dossier_arena / "secret"
    if not chemin.exists():
        dossier_arena.mkdir(parents=True, exist_ok=True)
        provisoire = dossier_arena / f".secret-{secrets.token_hex(8)}"
        descripteur = os.open(provisoire, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descripteur, "w", encoding="ascii") as fichier:
                fichier.write(secrets.token_hex(32))
            try:
                os.link(provisoire, chemin)  # échoue si un autre processus l'a créé entre-temps : on lit le sien
            except FileExistsError:
                pass
        finally:
            provisoire.unlink(missing_ok=True)
    cle = chemin.read_text(encoding="ascii").strip().encode()
    if not cle:
        raise ValueError(f"Le secret {chemin} est vide : supprimez ce fichier pour qu'il soit recréé.")
    return cle


def signer(secret: bytes, *parties: object) -> str:
    message = "\x1f".join(str(p) for p in parties).encode()
    return hmac.new(secret, message, hashlib.sha256).hexdigest()


def verifier(secret: bytes, signature: str, *parties: object) -> bool:
    return hmac.compare_digest(signature, signer(secret, *parties))
