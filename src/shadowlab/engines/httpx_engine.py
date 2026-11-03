"""Pilote témoin : client `httpx` brut, sans aucun réglage d'en-têtes. Sert de point de comparaison."""

from __future__ import annotations

import importlib.metadata
from typing import Any

from .http_base import DriverHttp, ReponseBrute


class DriverHttpx(DriverHttp):
    name = "httpx"
    options_permises = {"timeout": (int, float)}

    def configuration(self) -> dict[str, Any]:
        return {**self.options, "tls_non_verifie": True}

    def versions(self) -> dict[str, str]:
        return {"httpx": importlib.metadata.version("httpx")}

    def _ouvrir_client(self) -> None:
        import httpx

        # verify=False : certificat local de l'Arena ; aucune destination n'échappe au périmètre.
        self._client = httpx.Client(follow_redirects=False, timeout=self.options.get("timeout", 30), verify=False)

    def _envoyer(self, methode: str, url: str, donnees: dict[str, str] | None) -> ReponseBrute:
        reponse = self._client.request(methode, url, data=donnees)
        return ReponseBrute(reponse.status_code, {k.lower(): v for k, v in reponse.headers.items()}, reponse.text)

    def close_session(self) -> None:
        if getattr(self, "_client", None) is not None:
            self._client.close()
            self._client = None
