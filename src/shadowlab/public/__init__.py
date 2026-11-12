"""Application publique réduite (étape 1.6) : le site vitrine, les sessions humaines consenties et leur collecte.

Elle est faite pour être mise en ligne derrière un mandataire HTTPS ; l'application du laboratoire
(`site.app.creer_app`), elle, ne l'est jamais. Mode d'emploi et garanties : `docs/site-public.md`.
"""

from .app import ROTATION_JOURNAL, Limites, creer_app_publique
from .donnees import effacer_session, purger

__all__ = ["ROTATION_JOURNAL", "Limites", "creer_app_publique", "effacer_session", "purger"]
