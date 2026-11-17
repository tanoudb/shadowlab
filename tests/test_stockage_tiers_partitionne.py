"""Partitionnement du stockage tiers en identité native (défaut trouvé le 17/11 par rebrowser-bot-detector).

Un vrai Chrome partitionne le stockage d'un cadre tiers : une iframe du site B placée dans une page du site A ne voit
pas le `localStorage` que le site B a écrit quand on l'a visité seul. Playwright (donc Patchright) coupe ce
partitionnement par défaut : son argument de lancement `--disable-features=…` liste `ThirdPartyStoragePartitioning`
(coreBundle.js du pilote, « playwright/issues/32230 »). Un site peut le lire : c'est le test `storagePartitioning` de
rebrowser-bot-detector.

Ici le contrôle est refait SANS cette page : deux sites locaux qui sont deux « sites » pour Chrome (`localhost` et
`127.0.0.1`, deux hôtes) servis par un seul serveur. Étapes : visiter `127.0.0.1/ecrire` (il écrit dans son propre
`localStorage`), puis `localhost/cadre`, qui contient une iframe vers `127.0.0.1/lire` ; l'iframe dit ce qu'elle lit.
Partitionné : `lu=null`. Non partitionné (le défaut) : `lu=valeur-premiere-partie`.

Réglage imposé en identité native seulement (D-101) ; l'identité réécrite (réglage par défaut) ne change pas : un test
le garde, il n'affirme pas que c'est un bien.
"""

from __future__ import annotations

import shutil
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from shadowlab.engines import registre

VALEUR = "valeur-premiere-partie"


class SitesLocaux:
    """Un seul serveur, joignable par `localhost` et par `127.0.0.1` : deux sites pour Chrome."""

    def __init__(self) -> None:
        sites = self

        class Gestion(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                chemin = urlsplit(self.path)
                if chemin.path == "/ecrire":
                    corps = (
                        "<!doctype html><script>"
                        f"localStorage.setItem('cle', '{VALEUR}')</script><div id='ok'>ecrit</div>"
                    )
                elif chemin.path == "/cadre":
                    hote = parse_qs(chemin.query).get("hote", ["127.0.0.1"])[0]
                    corps = (
                        "<!doctype html><body><script>window.addEventListener('message', (e) => {"
                        "document.body.insertAdjacentHTML('beforeend', `<div id=\"resultat\">${e.data}</div>`)"
                        "})</script>"
                        f"<iframe src='http://{hote}:{sites.port}/lire'></iframe></body>"
                    )
                elif chemin.path == "/lire":
                    corps = (
                        "<!doctype html><script>"
                        "parent.postMessage('lu=' + String(localStorage.getItem('cle')), '*')</script>"
                    )
                else:
                    self.send_error(404)
                    return
                donnees = corps.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(donnees)))
                self.end_headers()
                self.wfile.write(donnees)

            def log_message(self, *args) -> None:
                pass

        self._serveur = ThreadingHTTPServer(("127.0.0.1", 0), Gestion)
        self.port = self._serveur.server_address[1]
        threading.Thread(target=self._serveur.serve_forever, daemon=True).start()

    def arreter(self) -> None:
        self._serveur.shutdown()
        self._serveur.server_close()


@pytest.fixture
def sites():
    serveur = SitesLocaux()
    yield serveur
    serveur.arreter()


@pytest.fixture(autouse=True)
def _environnement(tmp_path, monkeypatch):
    monkeypatch.setenv("SHADOWLAB_IDENTITES", str(tmp_path / "identites"))
    monkeypatch.delenv("SHADOWLAB_PROXY", raising=False)


def _chrome_installe() -> bool:
    """Google Chrome (pas le Chromium de Playwright) est-il installé ? Même critère que `tests/test_integration.py`."""
    if sys.platform == "darwin":
        return Path("/Applications/Google Chrome.app").exists()
    return any(shutil.which(nom) for nom in ("google-chrome", "google-chrome-stable"))


def _pilote(options: dict):
    return registre()["noezia"](("*",), {"interaction_post_page": False, "resoudre_defis": False, **options})


def _lu_par_l_iframe(pilote, port: int) -> str:
    """Ce que lit l'iframe `127.0.0.1` posée dans une page `localhost`, après une visite de `127.0.0.1` seul."""
    pilote.start_session()
    try:
        pilote.navigate(f"http://127.0.0.1:{port}/ecrire")
        pilote.navigate(f"http://localhost:{port}/cadre?hote=127.0.0.1")
        lu = pilote.wait_for_element("#resultat", 10000)
    finally:
        pilote.close_session()
    assert lu is not None, "l'iframe n'a rien répondu"
    return lu


OPTIONS_NATIVES = {"headless": False, "channel": "chrome", "identite_native": True}


# ── Rapides : le réglage est déclaré ───────────────────────────────────────


def test_configuration_declare_le_partitionnement_en_identite_native():
    assert _pilote(OPTIONS_NATIVES).configuration()["stockage_tiers_partitionne"] is True


def test_configuration_declare_le_partitionnement_en_identite_native_persistante():
    options = {**OPTIONS_NATIVES, "identite": "partition"}
    assert _pilote(options).configuration()["stockage_tiers_partitionne"] is True


def test_configuration_de_l_identite_reecrite_dit_que_rien_n_a_change():
    # Réglage par défaut de Patchright : le partitionnement reste coupé (un seul réglage change, en identité native).
    assert _pilote({"headless": True}).configuration()["stockage_tiers_partitionne"] is False


# ── Chrome réel ────────────────────────────────────────────────────────────

chrome_requis = pytest.mark.skipif(not _chrome_installe(), reason="Google Chrome n'est pas installé (channel: chrome)")


@pytest.mark.integration
@chrome_requis
def test_vrai_chrome_natif_partitionne_le_stockage_d_une_iframe_tierce(sites):
    pilote = _pilote(OPTIONS_NATIVES)
    pilote.open()
    try:
        assert _lu_par_l_iframe(pilote, sites.port) == "lu=null", (
            "l'iframe de 127.0.0.1 dans une page de localhost lit le stockage de 127.0.0.1 : partitionnement coupé"
        )
    finally:
        pilote.close()


@pytest.mark.integration
@chrome_requis
def test_vrai_chrome_en_identite_persistante_partitionne_le_stockage_d_une_iframe_tierce(sites):
    pilote = _pilote({**OPTIONS_NATIVES, "identite": "partition"})
    pilote.open()
    try:
        assert _lu_par_l_iframe(pilote, sites.port) == "lu=null", (
            "l'iframe de 127.0.0.1 dans une page de localhost lit le stockage de 127.0.0.1 : partitionnement coupé"
        )
    finally:
        pilote.close()


@pytest.mark.integration
def test_identite_reecrite_garde_son_reglage_par_defaut(sites):
    """Garde : le réglage par défaut (identité réécrite, Chromium de Patchright) ne change pas dans cette étape. Si un
    jour on le change, ce test se change exprès : il ne dit pas que le partitionnement coupé est un bien."""
    pilote = _pilote({"headless": True})
    pilote.open()
    try:
        assert _lu_par_l_iframe(pilote, sites.port) == f"lu={VALEUR}"
    finally:
        pilote.close()


def test_la_liste_copiee_est_celle_de_patchright_moins_le_partitionnement():
    """Le correctif repasse `--disable-features=…` (le dernier gagne) : il copie la liste de Playwright, moins
    `ThirdPartyStoragePartitioning`. Une mise à jour de Patchright qui change cette liste (par exemple un nouveau
    contournement d'un défaut de Chromium) doit échouer ICI, pas se perdre en silence : mettre alors la liste à jour."""
    import re

    import patchright

    from shadowlab.engines.noezia.moteur import (
        ARGUMENT_STOCKAGE_TIERS_PARTITIONNE,
        FONCTIONS_COUPEES_SANS_PARTITIONNEMENT,
    )

    pilote = Path(patchright.__file__).parent / "driver" / "package" / "lib" / "coreBundle.js"
    bloc = re.search(r"disabledFeatures = \[(.*?)\]\.filter\(", pilote.read_text(encoding="utf-8"), re.S)
    assert bloc is not None, "la liste des fonctions coupées n'est plus où on la cherche : relire coreBundle.js"
    noms = re.findall(r'^\s*"([A-Za-z0-9]+)",?\s*$', bloc.group(1), re.M)
    # Patchright retire `MediaRouter` de la liste (`.filter(... !== "MediaRouter")`) ; le correctif retire
    # le partitionnement.
    attendu = [nom for nom in noms if nom not in ("MediaRouter", "ThirdPartyStoragePartitioning")]
    assert "ThirdPartyStoragePartitioning" in noms, (
        "Patchright ne coupe plus le partitionnement : le correctif est inutile"
    )
    assert list(FONCTIONS_COUPEES_SANS_PARTITIONNEMENT) == attendu
    assert ARGUMENT_STOCKAGE_TIERS_PARTITIONNE == "--disable-features=" + ",".join(attendu)
