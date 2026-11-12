"""Pilote curl_cffi : client HTTP capable d'imiter la pile TLS d'un navigateur (`impersonate`), sans JavaScript."""

from __future__ import annotations

import importlib.metadata
from typing import Any

from .http_base import DriverHttp, ReponseBrute


class DriverCurlCffi(DriverHttp):
    name = "curl-cffi"
    categorie = "anti_detection"
    # verifier_tls : faux par défaut (Arena locale, certificat auto-signé) ; vrai pour un site qui n'est pas à nous
    options_permises = {
        "timeout": (int, float),
        "impersonate": str,
        "verifier_tls": bool,
        "suivre_redirections": bool,  # faux : la 3xx est rendue et sa destination gardée (`location`)
    }

    def configuration(self) -> dict[str, Any]:
        return {
            "impersonate": None,
            **self.options,
            "follow_redirects": False,
            "tls_non_verifie": not self.options.get("verifier_tls", False),
        }

    def versions(self) -> dict[str, str]:
        return {"curl_cffi": importlib.metadata.version("curl_cffi")}

    def _ouvrir_client(self) -> None:
        from curl_cffi import requests

        self._client = requests.Session(
            impersonate=self.options.get("impersonate"), verify=self.options.get("verifier_tls", False)
        )

    def _envoyer(self, methode: str, url: str, donnees: dict[str, str] | None) -> ReponseBrute:
        reponse = self._client.request(
            methode, url, data=donnees, allow_redirects=False, timeout=self.options.get("timeout", 30)
        )
        return ReponseBrute(reponse.status_code, {k.lower(): v for k, v in reponse.headers.items()}, reponse.text)

    def close_session(self) -> None:
        if getattr(self, "_client", None) is not None:
            self._client.close()
            self._client = None
