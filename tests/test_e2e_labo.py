"""Test bout-en-bout de l'interface : pilote le vrai navigateur à travers le parcours complet.

Configurer → Lancer → Suivre jusqu'à la fin → Ouvrir un passage, contre un serveur réel sur base
temporaire. Ignoré si le front n'est pas construit ou si Chromium (Playwright) n'est pas installé.
Marqué « integration » : lance un navigateur réel et une vraie campagne baseline httpx.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.request
from collections.abc import Iterator

import pytest

from shadowlab.labo import DIST

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not (DIST / "index.html").is_file(), reason="front non construit (npm run build)"),
]


def _port_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _attendre(url: str, delai: float = 20.0) -> bool:
    fin = time.time() + delai
    while time.time() < fin:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as r:
                if r.status == 200:
                    return True
        except OSError:
            time.sleep(0.1)
    return False


@pytest.fixture
def serveur(tmp_path) -> Iterator[str]:
    port = _port_libre()
    env = {
        "SHADOWLAB_SORTIES": str(tmp_path / "out"),
        "SHADOWLAB_BASE": str(tmp_path / "out" / "db.sqlite3"),
        "SHADOWLAB_PORT": str(port),
        "PATH": os.environ.get("PATH", ""),
    }
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "shadowlab.site.app:creer_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        env=env,
    )
    try:
        if not _attendre(f"http://127.0.0.1:{port}/api/sante"):
            raise RuntimeError("le serveur du labo n'a pas démarré")
        yield f"http://127.0.0.1:{port}"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_parcours_complet(serveur):
    pw = pytest.importorskip("playwright.sync_api")
    with pw.sync_playwright() as p:
        try:
            navigateur = p.chromium.launch(headless=True)
        except Exception as e:  # noqa: BLE001 — Chromium absent : on saute plutôt que d'échouer
            pytest.skip(f"Chromium indisponible : {e}")
        page = navigateur.new_page()
        try:
            # 1. Configurer : un moteur HTTP, baseline (déjà cochée), un scénario, 1 répétition.
            page.goto(f"{serveur}/labo/configurer")
            page.locator("label.case", has_text="httpx").locator("input").check()
            page.locator("label.case", has_text="static_html").locator("input").check()
            page.get_by_label("Répétitions").fill("1")

            # 2. Lancer (le bouton s'active après validation serveur).
            page.get_by_role("button", name="Lancer la campagne").click(timeout=15000)

            # 3. On bascule sur le suivi.
            page.wait_for_url("**/labo/experiences/*", timeout=15000)

            # 4. La campagne se termine.
            page.wait_for_selector("span.pastille.termine", timeout=60000)

            # 5. Ouvrir un passage et voir son verdict (attendre le chargement de la page).
            page.locator("table.tableau a").first.click()
            page.wait_for_url("**/labo/passages/*", timeout=10000)
            page.wait_for_selector("text=Verdict", timeout=10000)
            assert page.get_by_role("heading", name="Verdict").is_visible()
            assert page.get_by_text("httpx").first.is_visible()
        finally:
            navigateur.close()
