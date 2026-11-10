"""Pilote Crawlee : client HTTP avec headers réalistes de navigateur (impit) et gestion de sessions.

Crawlee est un framework de crawling async. Son intérêt ici : empreinte HTTP crédible par défaut
(TLS, headers, User-Agent) sans configuration. Le driver utilise le client HTTP impit de crawlee
(pas le crawler complet) et ponte async→sync pour respecter l'interface Driver.
"""

from __future__ import annotations

import asyncio
import importlib.metadata
from typing import Any

from ..http_base import DriverHttp, ReponseBrute


def _run(coro):
    """Exécute une coroutine dans un event loop dédié (pont async→sync)."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, coro).result(timeout=30)
    except RuntimeError:
        pass
    return asyncio.run(coro)


class DriverCrawlee(DriverHttp):
    name = "crawlee"
    categorie = "standard"
    options_permises: dict[str, type | tuple[type, ...]] = {}

    def configuration(self) -> dict[str, Any]:
        return {"client": "impit", "tls_non_verifie": True, **self.options}

    def versions(self) -> dict[str, str]:
        return {"crawlee": importlib.metadata.version("crawlee")}

    def _ouvrir_client(self) -> None:
        from crawlee.http_clients._impit import ImpitHttpClient

        self._client = ImpitHttpClient()

    def _envoyer(self, methode: str, url: str, donnees: dict[str, str] | None = None) -> ReponseBrute:
        from urllib.parse import urlencode

        async def _faire():
            kwargs: dict[str, Any] = {"method": methode}
            if donnees is not None and methode.upper() == "POST":
                kwargs["headers"] = {"content-type": "application/x-www-form-urlencoded"}
                kwargs["payload"] = urlencode(donnees).encode()
            resp = await self._client.send_request(url, **kwargs)
            body = await resp.read()
            headers = {k.lower(): v for k, v in resp.headers.items()}
            return ReponseBrute(resp.status_code, headers, body.decode("utf-8", errors="replace"))

        return _run(_faire())

    def close_session(self) -> None:
        if getattr(self, "_client", None) is not None:
            _run(self._client.cleanup())
            self._client = None
