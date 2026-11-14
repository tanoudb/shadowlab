"""D-79 : la page obtenue après un défi reçoit l'interaction humaine (sans navigateur : doubles qui notent l'ordre)."""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

from shadowlab.engines.noezia.moteur import DriverNoezia


class _PageDouble:
    url = "http://127.0.0.1:8770/lab/vitrine"

    def __init__(self, journal: list[str]) -> None:
        self._journal = journal

    def eval_on_selector(self, selecteur, script):
        return True

    @contextmanager
    def expect_navigation(self, wait_until="load"):
        yield

    def click(self, selecteur):
        self._journal.append("clic")


def _moteur(journal: list[str], defis: int, options: dict | None = None) -> DriverNoezia:
    """Moteur sans navigateur : `defis` défis sont traversés par `_resoudre_defis`."""
    opts = {"eviter_pieges": False}
    opts.update(options or {})
    m = DriverNoezia(("127.0.0.1",), opts)
    m._page = _PageDouble(journal)
    m.mesures.details["defis_resolus"] = []
    m._naviguer_avec_essais = lambda url, attente: SimpleNamespace(status=200)
    m._interaction_post_chargement = lambda: journal.append("interaction")
    m._interaction_post_clic_navigation = lambda: journal.append("interaction_clic")

    def resoudre() -> None:
        journal.append("defis")
        for i in range(defis):
            m.mesures.details["defis_resolus"].append(f"defi{i}")

    m._resoudre_defis = resoudre
    return m


def test_navigation_a_travers_des_defis_interagit_sur_la_page_finale():
    journal: list[str] = []
    _moteur(journal, defis=3).navigate("http://127.0.0.1:8770/lab/vitrine")
    assert journal[-1] == "interaction"
    assert journal.index("defis") < len(journal) - 1


def test_navigation_sans_defi_une_seule_interaction():
    journal: list[str] = []
    _moteur(journal, defis=0).navigate("http://127.0.0.1:8770/lab/vitrine")
    assert journal.count("interaction") == 1
    assert journal == ["interaction", "defis"]


def test_navigation_a_travers_des_defis_sans_interaction_si_option_coupee():
    journal: list[str] = []
    _moteur(journal, defis=2, options={"interaction_post_page": False}).navigate("http://127.0.0.1:8770/lab/vitrine")
    assert journal == ["defis"]


def test_clic_vers_une_page_protegee_interagit_sur_la_page_finale():
    journal: list[str] = []
    _moteur(journal, defis=2).click("a.suite")
    assert journal[-1] in ("interaction", "interaction_clic")
    assert journal.index("defis") < len(journal) - 1


def test_clic_sans_defi_une_seule_interaction():
    journal: list[str] = []
    _moteur(journal, defis=0).click("a.suite")
    assert journal == ["clic", "interaction_clic", "defis"]


def test_clic_a_travers_des_defis_sans_interaction_si_option_coupee():
    journal: list[str] = []
    _moteur(journal, defis=2, options={"interaction_post_page": False}).click("a.suite")
    assert journal == ["clic", "defis"]
