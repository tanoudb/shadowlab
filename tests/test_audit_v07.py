"""Audit adversarial v0.7 — reproduction et non-régression des défauts confirmés.

Chaque classe cible un défaut précis identifié par l'audit. Les tests encodent
le comportement *correct* attendu ; ils échouent sur le code défectueux et
passent une fois la cause racine corrigée.
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Défaut #4 — statut du passage calculé avant l'intégration du dépassement mémoire
# ---------------------------------------------------------------------------


class TestStatutDepassementMemoire:
    def test_depassement_avec_succes_nest_pas_reussi(self):
        """Un passage fonctionnellement réussi qui dépasse le plafond mémoire
        est une erreur technique, jamais 'reussi'."""
        from shadowlab.campaigns import _resultat_passage

        statut, erreur, succes = _resultat_passage(
            erreur=None, succes=True, depassement=True, plafond_mo=512
        )
        assert statut == "erreur", f"statut incohérent : {statut!r} avec dépassement mémoire"
        assert succes is False
        assert "plafond mémoire" in erreur

    def test_depassement_sans_erreur_prealable(self):
        from shadowlab.campaigns import _resultat_passage

        statut, erreur, succes = _resultat_passage(
            erreur=None, succes=False, depassement=True, plafond_mo=256
        )
        assert statut == "erreur"
        assert succes is False

    def test_sans_depassement_succes_reste_reussi(self):
        from shadowlab.campaigns import _resultat_passage

        statut, erreur, succes = _resultat_passage(
            erreur=None, succes=True, depassement=False, plafond_mo=512
        )
        assert statut == "reussi"
        assert succes is True
        assert erreur is None

    def test_erreur_prealable_prime(self):
        from shadowlab.campaigns import _resultat_passage

        statut, erreur, succes = _resultat_passage(
            erreur="TimeoutError: x", succes=None, depassement=False, plafond_mo=512
        )
        assert statut == "erreur"
        assert succes is False
        assert erreur == "TimeoutError: x"
