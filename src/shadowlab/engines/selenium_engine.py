"""Pilote Selenium (Chrome installé, mode sans tête standard), piloté par Selenium Manager.

Périmètre : Selenium ne filtre pas les requêtes du navigateur. On l'impose au niveau réseau de Chrome
(`MANDATAIRE_BLOQUANT`) : seules les adresses de la liste passent en direct, tout le reste échoue.
"""

from __future__ import annotations

import importlib.metadata
import time
from pathlib import Path
from typing import Any

from .base import (
    MANDATAIRE_BLOQUANT,
    Driver,
    FonctionIndisponible,
    ResultatNavigation,
    liste_directe,
    perimetre_illimite,
)

SCRIPT_NAVIGUE = "const e = arguments[0]; return (e.tagName === 'A' && !!e.href) || (e.type === 'submit' && !!e.form);"


class DriverSelenium(Driver):
    name = "selenium"
    runtime = "navigateur"
    executes_javascript = True
    options_permises = {"headless": bool}

    def configuration(self) -> dict[str, Any]:
        return {"browser": "chrome", "headless": True, "tls_non_verifie": True, **self.options}

    def versions(self) -> dict[str, str]:
        versions = {"selenium": importlib.metadata.version("selenium")}
        if getattr(self, "_pilote", None) is not None:
            capacites = self._pilote.capabilities
            versions["chrome"] = capacites.get("browserVersion", "unknown")
            versions["chromedriver"] = capacites.get("chrome", {}).get("chromedriverVersion", "unknown").split()[0]
        return versions

    def open(self) -> None:
        from selenium import webdriver

        options = webdriver.ChromeOptions()
        if self.configuration()["headless"]:
            options.add_argument("--headless=new")
        if not perimetre_illimite(self.hotes_autorises):  # pas de verrou réseau en illimité
            contournement = ";".join(liste_directe(self.hotes_autorises))
            options.add_argument(f"--proxy-server={MANDATAIRE_BLOQUANT}")
            options.add_argument(f"--proxy-bypass-list={contournement}")
        options.add_argument("--ignore-certificate-errors")  # certificat local de l'Arena
        self._pilote = webdriver.Chrome(options=options)
        self._pilote.set_page_load_timeout(30)

    def close(self) -> None:
        if getattr(self, "_pilote", None) is not None:
            self._pilote.quit()
            self._pilote = None

    def start_session(self) -> None:
        # Pas de contexte isolé dans WebDriver : on vide cookies, cache et stockage entre deux passages.
        self._pilote.execute_cdp_cmd("Network.clearBrowserCookies", {})
        self._pilote.execute_cdp_cmd("Network.clearBrowserCache", {})
        try:
            self._pilote.execute_cdp_cmd(
                "Storage.clearDataForOrigin",
                {"origin": self._pilote.current_url or "*", "storageTypes": "all"},
            )
        except Exception:
            pass
        self.mesures.details["requetes_bloquees"] = "non mesuré"

    def _apres_chargement(self) -> int | None:
        etat = self._pilote.execute_script(
            "const n = performance.getEntriesByType('navigation')[0];"
            "return {status: n ? n.responseStatus : null, ressources: performance.getEntriesByType('resource').length};"
        )
        self.mesures.request_count += 1 + (etat.get("ressources") or 0)
        status = etat.get("status")
        if status and status >= 400:
            self.mesures.error_count += 1
        return status

    def navigate(self, url: str) -> ResultatNavigation:
        self.verifier(url)
        debut = time.perf_counter()
        self._pilote.get(url)
        duree = (time.perf_counter() - debut) * 1000
        self.mesures.navigation_time += duree
        return ResultatNavigation(self._apres_chargement(), self._pilote.current_url, duree)

    def _element(self, selector: str):
        from selenium.webdriver.common.by import By

        return self._pilote.find_element(By.CSS_SELECTOR, selector)

    def click(self, selector: str) -> None:
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions as ec
        from selenium.webdriver.support.ui import WebDriverWait

        element = self._element(selector)
        if self._pilote.execute_script(SCRIPT_NAVIGUE, element):
            ancienne = self._pilote.find_element(By.TAG_NAME, "html")
            element.click()
            WebDriverWait(self._pilote, 30).until(ec.staleness_of(ancienne))
            WebDriverWait(self._pilote, 30).until(
                lambda p: p.execute_script("return document.readyState") == "complete"
            )
            self._apres_chargement()
        else:
            element.click()

    def fill(self, selector: str, value: str) -> None:
        element = self._element(selector)
        element.clear()
        element.send_keys(value)

    def select(self, selector: str, value: str) -> None:
        from selenium.webdriver.support.ui import Select

        Select(self._element(selector)).select_by_value(value)

    def wait_for_element(self, selector: str, timeout_ms: int = 5000) -> str | None:
        from selenium.common.exceptions import TimeoutException
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions as ec
        from selenium.webdriver.support.ui import WebDriverWait

        try:
            element = WebDriverWait(self._pilote, timeout_ms / 1000, poll_frequency=0.05).until(
                ec.presence_of_element_located((By.CSS_SELECTOR, selector))
            )
        except TimeoutException:
            return None
        return element.get_attribute("textContent")

    def texts(self, selector: str) -> list[str]:
        from selenium.webdriver.common.by import By

        return [e.get_attribute("textContent") for e in self._pilote.find_elements(By.CSS_SELECTOR, selector)]

    def content(self) -> str:
        # WebDriver ne donne pas le corps brut de la réponse : texte affiché pour un JSON, DOM sinon.
        if self._pilote.execute_script("return document.contentType") == "application/json":
            return self._pilote.execute_script("return document.body.innerText")
        return self._pilote.page_source

    def dom(self) -> str:
        return self._pilote.page_source

    def attendre_chargement(self) -> None:
        from selenium.webdriver.support.ui import WebDriverWait

        WebDriverWait(self._pilote, 30, poll_frequency=0.05).until(
            lambda p: p.execute_script("return document.readyState") == "complete"
        )

    def deplacer_souris(self, x: int, y: int) -> None:
        from selenium.webdriver import ActionChains

        ActionChains(self._pilote).move_to_location(x, y).perform()

    def defiler(self, hauteur: int) -> None:
        from selenium.webdriver import ActionChains

        ActionChains(self._pilote).scroll_by_amount(0, hauteur).perform()

    def capture_screenshot(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._pilote.save_screenshot(str(path))
        return path

    def export_trace(self, path: Path) -> Path:
        raise FonctionIndisponible("selenium : pas de trace exportable")

    def close_session(self) -> None:
        try:
            self._pilote.get("about:blank")  # déclenche `pagehide` sur la page de test
        except Exception:
            pass
