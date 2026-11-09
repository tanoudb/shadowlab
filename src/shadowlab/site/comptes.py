"""Comptes de TEST du niveau authentifié de l'Arena.

Fixtures publiques et strictement locales — jamais des identifiants réels. Elles ne
servent qu'à mesurer si le moteur sait franchir un login protégé par détection
comportementale, sur notre propre site de test (périmètre D-15/D-16).
"""

from __future__ import annotations

import hmac

# identifiant → mot de passe (fixtures de test, non secrètes).
COMPTES: dict[str, str] = {
    "demo": "arena-demo-2026",
    "analyste": "shadowlab-test",
}


def verifier(identifiant: str, mot_de_passe: str) -> bool:
    """Vrai si le couple identifiant/mot de passe correspond à un compte de test.

    Comparaison à temps constant, par habitude : ces fixtures ne sont pas secrètes,
    mais on n'écrit pas de comparaison de mot de passe naïve dans du code livré.
    """
    attendu = COMPTES.get(identifiant)
    if attendu is None:
        return False
    return hmac.compare_digest(attendu, mot_de_passe)
