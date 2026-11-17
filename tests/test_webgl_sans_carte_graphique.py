"""WebGL en identité native avec interface sur Linux sans carte graphique (D-102).

Voir `docs/recherche/webgl-linux-sans-gpu-2026-11-17.md`. Mesuré le 17/11 dans le conteneur amd64 (Chrome 158, Xvfb,
Mesa 25.2) : un Chrome lancé par Patchright sans argument n'a PAS de WebGL (la liste de blocage des cartes graphiques écarte llvmpipe, et le
repli sur SwiftShader n'existe plus). `--ignore-gpu-blocklist` donne un WebGL `ANGLE (Mesa, llvmpipe …, OpenGL 4.5)`
mais active aussi le canvas 2D accéléré, dont la lecture devient instable (10 essais sur 10) ;
`--disable-accelerated-2d-canvas` le rend stable. Les deux arguments ne s'ajoutent que sur Linux sans carte graphique,
en identité native avec interface. Ici : la règle de ce choix, sans navigateur (les mesures sont dans la note).
"""

from __future__ import annotations

import types

import pytest

from shadowlab.engines import registre
from shadowlab.engines.noezia import moteur

OPTIONS_NATIVES = {"headless": False, "channel": "chrome", "identite_native": True}


@pytest.fixture(autouse=True)
def _identites(tmp_path, monkeypatch):
    monkeypatch.setenv("SHADOWLAB_IDENTITES", str(tmp_path / "identites"))
    monkeypatch.delenv("SHADOWLAB_PROXY", raising=False)


def _pilote(options: dict):
    return registre()["noezia"](("*",), {"interaction_post_page": False, "resoudre_defis": False, **options})


def test_les_deux_arguments_choisis():
    assert moteur.ARGUMENTS_WEBGL_SANS_GPU == ("--ignore-gpu-blocklist", "--disable-accelerated-2d-canvas")


# ── Qu'est-ce qu'un Linux sans carte graphique ─────────────────────────────


@pytest.mark.parametrize(
    ("entrees", "attendu"),
    [
        ([], True),  # ni nœud de rendu, ni pilote NVIDIA : aucune carte
        (["/dev/dri/card0"], False),  # un nœud DRM : une carte, même virtuelle
        (["/dev/dri/renderD128"], False),
        (["/dev/nvidia0"], False),
        (["/dev/nvidiactl"], False),
    ],
)
def test_sans_carte_graphique_sur_linux(monkeypatch, entrees, attendu):
    monkeypatch.setattr(moteur.glob, "glob", lambda motif: [e for e in entrees if e.startswith(motif.rstrip("*"))])
    assert moteur.sans_carte_graphique("linux") is attendu


@pytest.mark.parametrize("systeme", ["macos", "windows"])
def test_jamais_sans_carte_graphique_hors_linux(monkeypatch, systeme):
    # Même sans aucun nœud `/dev/dri` : hors Linux, la question ne se pose pas.
    monkeypatch.setattr(moteur.glob, "glob", lambda motif: [])
    assert moteur.sans_carte_graphique(systeme) is False


# ── Les arguments imposés en identité native ───────────────────────────────


def test_linux_sans_carte_avec_interface_ajoute_les_deux_arguments():
    arguments = moteur.arguments_natifs(headless=False, hote_os="linux", sans_gpu=True)
    assert arguments == [moteur.ARGUMENT_STOCKAGE_TIERS_PARTITIONNE, *moteur.ARGUMENTS_WEBGL_SANS_GPU]


def test_macos_ne_change_pas():
    """Rien de nouveau sur macOS : seulement le partitionnement du stockage tiers (D-101), comme avant ce réglage."""
    for sans_gpu in (False, True):  # même si la question était mal posée : hors Linux, rien ne s'ajoute
        assert moteur.arguments_natifs(headless=False, hote_os="macos", sans_gpu=sans_gpu) == [
            moteur.ARGUMENT_STOCKAGE_TIERS_PARTITIONNE
        ]


def test_linux_avec_carte_graphique_ne_change_pas():
    arguments = moteur.arguments_natifs(headless=False, hote_os="linux", sans_gpu=False)
    assert arguments == [moteur.ARGUMENT_STOCKAGE_TIERS_PARTITIONNE]


def test_sans_interface_ne_change_pas():
    """Chrome sans interface a déjà un WebGL (SwiftShader du « headless shell ») : on n'y touche pas."""
    arguments = moteur.arguments_natifs(headless=True, hote_os="linux", sans_gpu=True)
    assert arguments == [moteur.ARGUMENT_STOCKAGE_TIERS_PARTITIONNE]


# ── Déclaré dans configuration() ───────────────────────────────────────────


def _situation(monkeypatch, hote_os: str, sans_gpu: bool) -> None:
    monkeypatch.setattr(moteur, "_HOTE_OS", hote_os)
    monkeypatch.setattr(moteur, "sans_carte_graphique", lambda *_: sans_gpu and hote_os == "linux")


def test_configuration_declare_les_arguments_sur_linux_sans_carte(monkeypatch):
    _situation(monkeypatch, "linux", True)
    conf = _pilote(OPTIONS_NATIVES).configuration()
    assert conf["webgl_sans_carte_graphique_arguments"] == list(moteur.ARGUMENTS_WEBGL_SANS_GPU)


def test_configuration_declare_les_arguments_en_identite_persistante(monkeypatch):
    _situation(monkeypatch, "linux", True)
    conf = _pilote({**OPTIONS_NATIVES, "identite": "webgl"}).configuration()
    assert conf["webgl_sans_carte_graphique_arguments"] == list(moteur.ARGUMENTS_WEBGL_SANS_GPU)


def test_configuration_inchangee_sur_macos(monkeypatch):
    """Sur macOS la configuration enregistrée est exactement celle d'avant : aucune clé de plus."""
    _situation(monkeypatch, "macos", False)
    conf = _pilote(OPTIONS_NATIVES).configuration()
    assert "webgl_sans_carte_graphique_arguments" not in conf
    _situation(monkeypatch, "macos", True)
    assert _pilote(OPTIONS_NATIVES).configuration() == conf


def test_configuration_inchangee_sur_linux_avec_carte(monkeypatch):
    _situation(monkeypatch, "linux", False)
    assert "webgl_sans_carte_graphique_arguments" not in _pilote(OPTIONS_NATIVES).configuration()


def test_configuration_de_l_identite_reecrite_inchangee(monkeypatch):
    _situation(monkeypatch, "linux", True)
    assert "webgl_sans_carte_graphique_arguments" not in _pilote({"headless": False}).configuration()


def test_configuration_native_sans_interface_inchangee(monkeypatch):
    _situation(monkeypatch, "linux", True)
    options = {"headless": True, "identite_native": True}
    assert "webgl_sans_carte_graphique_arguments" not in _pilote(options).configuration()


# ── Ce que Chrome reçoit au lancement (sans navigateur : un faux Playwright) ───


class _FauxChromium:
    def __init__(self) -> None:
        self.appels: list[dict] = []

    def launch(self, **kwargs):
        self.appels.append(kwargs)
        return types.SimpleNamespace(version="faux", close=lambda: None)

    def launch_persistent_context(self, **kwargs):
        self.appels.append(kwargs)
        return types.SimpleNamespace(browser=None)


def _faux_playwright(monkeypatch) -> _FauxChromium:
    chromium = _FauxChromium()
    pw = types.SimpleNamespace(chromium=chromium, stop=lambda: None)
    monkeypatch.setattr("patchright.sync_api.sync_playwright", lambda: types.SimpleNamespace(start=lambda: pw))
    return chromium


@pytest.mark.parametrize(
    ("hote_os", "sans_gpu", "ajoutes"), [("linux", True, True), ("linux", False, False), ("macos", False, False)]
)
def test_le_lancement_natif_recoit_les_arguments(monkeypatch, hote_os, sans_gpu, ajoutes):
    _situation(monkeypatch, hote_os, sans_gpu)
    chromium = _faux_playwright(monkeypatch)
    pilote = _pilote(OPTIONS_NATIVES)
    pilote.open()
    (appel,) = chromium.appels
    attendu = [moteur.ARGUMENT_STOCKAGE_TIERS_PARTITIONNE] + (list(moteur.ARGUMENTS_WEBGL_SANS_GPU) if ajoutes else [])
    assert appel["args"] == attendu


@pytest.mark.parametrize(
    ("hote_os", "sans_gpu", "ajoutes"), [("linux", True, True), ("linux", False, False), ("macos", False, False)]
)
def test_le_lancement_d_une_identite_recoit_les_arguments(monkeypatch, hote_os, sans_gpu, ajoutes):
    _situation(monkeypatch, hote_os, sans_gpu)
    chromium = _faux_playwright(monkeypatch)
    pilote = _pilote({**OPTIONS_NATIVES, "identite": "webgl-lancement"})
    pilote.open()
    try:
        pilote._lancer_identite()
        (appel,) = chromium.appels
        attendu = [moteur.ARGUMENT_STOCKAGE_TIERS_PARTITIONNE] + (
            list(moteur.ARGUMENTS_WEBGL_SANS_GPU) if ajoutes else []
        )
        assert appel["args"] == attendu
    finally:
        pilote.close()


def test_l_identite_reecrite_ne_recoit_pas_ces_arguments(monkeypatch):
    _situation(monkeypatch, "linux", True)
    chromium = _faux_playwright(monkeypatch)
    pilote = _pilote({"headless": False})
    pilote.open()
    (appel,) = chromium.appels
    for argument in moteur.ARGUMENTS_WEBGL_SANS_GPU:
        assert argument not in appel["args"]
