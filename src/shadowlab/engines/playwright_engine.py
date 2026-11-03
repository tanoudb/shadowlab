"""Pilote Playwright (Chromium), configuration standard : aucun réglage d'empreinte.

Périmètre en deux couches :
1. verrou réseau du navigateur (mandataire bloquant, comme pour Selenium) : il couvre aussi les
   redirections, que le filtre `route` de Playwright n'intercepte pas ;
2. filtre `route` : interrompt et compte (`requetes_bloquees`) les requêtes directes hors périmètre.
"""

from __future__ import annotations

import importlib.metadata
import time
from pathlib import Path
from typing import Any

from ..perimetre import est_autorisee
from .base import MANDATAIRE_BLOQUANT, Driver, ResultatNavigation, liste_directe


class DriverPlaywright(Driver):
    name = "playwright"
    runtime = "navigateur"
    executes_javascript = True

    def configuration(self) -> dict[str, Any]:
        return {"browser": "chromium", "headless": True, "trace": False, **self.options}

    def versions(self) -> dict[str, str]:
        versions = {"playwright": importlib.metadata.version("playwright")}
        if getattr(self, "_navigateur", None) is not None:
            versions["chromium"] = self._navigateur.version
        return versions

    def open(self) -> None:
        from playwright.sync_api import sync_playwright

        config = self.configuration()
        self._pw = sync_playwright().start()
        verrou = {"server": MANDATAIRE_BLOQUANT, "bypass": ",".join(liste_directe(self.hotes_autorises))}
        self._navigateur = self._pw.chromium.launch(
            headless=config["headless"], channel=config.get("channel"), proxy=verrou
        )

    def close(self) -> None:
        if getattr(self, "_navigateur", None) is not None:
            self._navigateur.close()
            self._pw.stop()
            self._navigateur = None

    def start_session(self) -> None:
        self.mesures.details["requetes_bloquees"] = 0
        self._contexte = self._navigateur.new_context()
        self._contexte.route("**/*", self._filtrer)
        if self.configuration()["trace"]:
            self._contexte.tracing.start(screenshots=True, snapshots=True)
        self._page = self._contexte.new_page()
        self._page.on("request", lambda _: self._compter("request_count"))
        self._page.on("requestfailed", lambda _: self._compter("error_count"))
        self._texte = ""

    def _compter(self, champ: str) -> None:
        setattr(self.mesures, champ, getattr(self.mesures, champ) + 1)

    def _filtrer(self, route) -> None:
        if est_autorisee(route.request.url, self.hotes_autorises):
            route.continue_()
        else:
            self.mesures.details["requetes_bloquees"] += 1
            route.abort("blockedbyclient")

    def navigate(self, url: str) -> ResultatNavigation:
        self.verifier(url)
        debut = time.perf_counter()
        reponse = self._page.goto(url, wait_until="load")
        duree = (time.perf_counter() - debut) * 1000
        self.mesures.navigation_time += duree
        self._texte = reponse.text() if reponse is not None else ""
        status = reponse.status if reponse is not None else None
        if status is not None and status >= 400:
            self.mesures.error_count += 1
        return ResultatNavigation(status, self._page.url, duree)

    def click(self, selector: str) -> None:
        navigue = self._page.eval_on_selector(
            selector, "e => (e.tagName === 'A' && !!e.href) || (e.type === 'submit' && !!e.form)"
        )
        if navigue:
            with self._page.expect_navigation(wait_until="load"):
                self._page.click(selector)
        else:
            self._page.click(selector)

    def fill(self, selector: str, value: str) -> None:
        self._page.fill(selector, value)

    def select(self, selector: str, value: str) -> None:
        self._page.select_option(selector, value)

    def wait_for_element(self, selector: str, timeout_ms: int = 5000) -> str | None:
        try:
            element = self._page.wait_for_selector(selector, state="attached", timeout=timeout_ms)
        except Exception:  # délai dépassé : l'élément n'est pas apparu
            return None
        return element.text_content() if element is not None else None

    def texts(self, selector: str) -> list[str]:
        return self._page.locator(selector).all_text_contents()

    def content(self) -> str:
        return self._texte

    def capture_screenshot(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._page.screenshot(path=str(path), full_page=True)
        return path

    def export_trace(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._contexte.tracing.stop(path=str(path))
        return path

    def close_session(self) -> None:
        if getattr(self, "_contexte", None) is None:
            return
        try:
            # Quitter la page déclenche `pagehide` : l'observateur envoie alors son relevé de comportement.
            self._page.goto("about:blank")
        except Exception:
            pass
        if self.configuration()["trace"]:
            try:
                self._contexte.tracing.stop()
            except Exception:
                pass
        self._contexte.close()
        self._contexte = None
