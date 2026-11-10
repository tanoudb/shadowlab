"""Pilote Zendriver : automatisation Chrome asynchrone par CDP, anti-détection native.

Fork communautaire de nodriver. Intérêt : pilotage Chrome par DevTools Protocol sans WebDriver,
ce qui échappe à la détection `navigator.webdriver`. Tout est async, ponté en sync ici.

Licence : AGPL-3.0 — noté dans les résultats, à vérifier avant usage dans un produit livré.
"""

from __future__ import annotations

import asyncio
import importlib.metadata
import threading
import time
from pathlib import Path
from typing import Any

from ..base import MANDATAIRE_BLOQUANT, Driver, ResultatNavigation, liste_directe, perimetre_illimite


class _Boucle:
    """Event loop dédié dans un thread daemon, partagé par toutes les sessions zendriver du processus."""

    _instance = None
    _verrou = threading.Lock()

    @classmethod
    def obtenir(cls) -> asyncio.AbstractEventLoop:
        with cls._verrou:
            if cls._instance is None or cls._instance.is_closed():
                cls._instance = asyncio.new_event_loop()
                t = threading.Thread(target=cls._instance.run_forever, daemon=True)
                t.start()
            return cls._instance

    @classmethod
    def executer(cls, coro, timeout: float = 60):
        loop = cls.obtenir()
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=timeout)


class DriverZendriver(Driver):
    name = "zendriver"
    runtime = "navigateur"
    executes_javascript = True
    categorie = "anti_detection"
    options_permises: dict[str, type | tuple[type, ...]] = {"headless": bool}

    def configuration(self) -> dict[str, Any]:
        return {"browser": "chrome", "headless": True, "tls_non_verifie": True, **self.options}

    def versions(self) -> dict[str, str]:
        return {"zendriver": importlib.metadata.version("zendriver")}

    def _exec(self, coro, timeout: float = 60):
        return _Boucle.executer(coro, timeout)

    def open(self) -> None:
        import zendriver

        args = ["--ignore-certificate-errors", "--disable-blink-features=AutomationControlled"]
        if not perimetre_illimite(self.hotes_autorises):
            args.append(f"--proxy-server={MANDATAIRE_BLOQUANT}")
            args.append(f"--proxy-bypass-list={';'.join(liste_directe(self.hotes_autorises))}")

        async def _demarrer():
            browser = await zendriver.Browser.create(
                headless=self.configuration()["headless"],
                browser_args=args,
            )
            return browser

        self._navigateur = self._exec(_demarrer())

    def close(self) -> None:
        if getattr(self, "_navigateur", None) is not None:
            try:
                self._exec(asyncio.coroutine(lambda: self._navigateur.stop())() if False else self._sync_stop())
            except Exception:
                pass
            self._navigateur = None

    async def _sync_stop(self):
        self._navigateur.stop()

    def start_session(self) -> None:
        self._reponse_status: int | None = None

        async def _nouvelle_page():
            tab = await self._navigateur.get("about:blank")
            return tab

        self._page = self._exec(_nouvelle_page())

    def navigate(self, url: str) -> ResultatNavigation:
        self.verifier(url)
        debut = time.perf_counter()

        async def _aller():
            tab = await self._page.get(url)
            await tab.wait_for_ready_state("complete", timeout=30)
            return tab

        self._page = self._exec(_aller(), timeout=35)
        duree = (time.perf_counter() - debut) * 1000
        self.mesures.navigation_time += duree
        self.mesures.request_count += 1
        return ResultatNavigation(200, url, duree)

    def click(self, selector: str) -> None:
        async def _cliquer():
            el = await self._page.select(selector, timeout=5)
            if el is None:
                raise LookupError(f"élément introuvable : {selector}")
            await el.click()
            await self._page.wait_for_ready_state("complete", timeout=10)

        self._exec(_cliquer(), timeout=15)

    def fill(self, selector: str, value: str) -> None:
        async def _remplir():
            el = await self._page.select(selector, timeout=5)
            if el is None:
                raise LookupError(f"champ introuvable : {selector}")
            await el.clear_input()
            await el.send_keys(value)

        self._exec(_remplir(), timeout=10)

    def select(self, selector: str, value: str) -> None:
        async def _choisir():
            el = await self._page.select(selector, timeout=5)
            if el is None:
                raise LookupError(f"liste introuvable : {selector}")
            await self._page.evaluate(
                f"document.querySelector('{selector}').value = '{value}'; "
                f"document.querySelector('{selector}').dispatchEvent(new Event('change'))"
            )

        self._exec(_choisir(), timeout=10)

    def wait_for_element(self, selector: str, timeout_ms: int = 5000) -> str | None:
        async def _attendre():
            try:
                el = await self._page.select(selector, timeout=timeout_ms / 1000)
                if el is None:
                    return None
                html = await el.get_html()
                from lxml import html as lhtml

                doc = lhtml.fromstring(html)
                return doc.text_content()
            except Exception:
                return None

        return self._exec(_attendre(), timeout=timeout_ms / 1000 + 5)

    def texts(self, selector: str) -> list[str]:
        async def _textes():
            elements = await self._page.select_all(selector, timeout=5)
            resultats = []
            for el in elements:
                html = await el.get_html()
                from lxml import html as lhtml

                doc = lhtml.fromstring(html)
                resultats.append(doc.text_content())
            return resultats

        return self._exec(_textes(), timeout=15)

    def content(self) -> str:
        return self._exec(self._page.get_content(), timeout=10)

    def dom(self) -> str:
        return self.content()

    def attendre_chargement(self) -> None:
        self._exec(self._page.wait_for_ready_state("complete", timeout=10), timeout=15)

    def deplacer_souris(self, x: int, y: int) -> None:
        self._exec(self._page.mouse_move(x, y, steps=8), timeout=5)

    def defiler(self, hauteur: int) -> None:
        steps = max(1, abs(hauteur) // 100)
        if hauteur > 0:
            self._exec(self._page.scroll_down(amount=steps), timeout=5)
        else:
            self._exec(self._page.scroll_up(amount=steps), timeout=5)

    def capture_screenshot(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)

        async def _capture():
            await self._page.save_screenshot(str(path), format="png", full_page=True)

        self._exec(_capture(), timeout=10)
        return path

    def close_session(self) -> None:
        if getattr(self, "_page", None) is not None:
            try:
                self._exec(self._page.close(), timeout=5)
            except Exception:
                pass
            self._page = None
