"""Pilote Scrapling : client HTTP `FetcherSession` (curl_cffi) dans sa configuration par défaut.

Seuls deux réglages s'écartent du défaut, pour les besoins du laboratoire : pas de redirection suivie par
la bibliothèque (le périmètre contrôle chaque étape) et une seule tentative (les erreurs sont comptées,
pas masquées). `StealthyFetcher` n'est pas intégré : c'est un navigateur modifié pour échapper aux
détecteurs, hors du périmètre de ce laboratoire.
"""

from __future__ import annotations

import importlib.metadata
from typing import Any

from .http_base import DriverHttp, ReponseBrute


class DriverScrapling(DriverHttp):
    name = "scrapling"

    def configuration(self) -> dict[str, Any]:
        return {"fetcher": "FetcherSession", "follow_redirects": False, "retries": 1, **self.options}

    def versions(self) -> dict[str, str]:
        return {
            "scrapling": importlib.metadata.version("scrapling"),
            "curl_cffi": importlib.metadata.version("curl_cffi"),
        }

    def _ouvrir_client(self) -> None:
        from scrapling.fetchers import FetcherSession

        reglages = {"follow_redirects": False, "retries": 1, **self.options}
        self._gestionnaire = FetcherSession(**reglages)
        self._client = self._gestionnaire.__enter__()

    def _envoyer(self, methode: str, url: str, donnees: dict[str, str] | None) -> ReponseBrute:
        if methode == "POST":
            reponse = self._client.post(url, data=donnees)
        else:
            reponse = self._client.get(url)
        entetes = {k.lower(): v for k, v in dict(reponse.headers).items()}
        return ReponseBrute(reponse.status, entetes, reponse.body.decode("utf-8", "replace"))

    def close_session(self) -> None:
        if getattr(self, "_gestionnaire", None) is not None:
            self._gestionnaire.__exit__(None, None, None)
            self._gestionnaire = None
