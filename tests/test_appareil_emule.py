"""Option `appareil` du pilote Playwright (et Patchright) : émulation d'un téléphone du registre de Playwright."""

from __future__ import annotations

import pytest

from shadowlab import campaigns
from shadowlab.engines.patchright_engine import DriverPatchright
from shadowlab.engines.playwright_engine import DriverPlaywright

HOTES = ("127.0.0.1", "localhost")


@pytest.mark.parametrize("classe", [DriverPlaywright, DriverPatchright])
def test_option_appareil_acceptee_et_enregistree(classe):
    pilote = classe(HOTES, {"appareil": "Pixel 7"})
    assert pilote.configuration()["appareil"] == "Pixel 7"


@pytest.mark.parametrize("classe", [DriverPlaywright, DriverPatchright])
def test_sans_option_la_configuration_ne_change_pas(classe):
    assert "appareil" not in classe(HOTES).configuration()


def test_appareil_de_mauvais_type_refuse():
    with pytest.raises(ValueError, match="appareil"):
        DriverPlaywright(HOTES, {"appareil": 7})


def test_appareil_inconnu_refuse_avant_tout_lancement_de_navigateur():
    pilote = DriverPlaywright(HOTES, {"appareil": "Telephone Imaginaire 9000"})
    with pytest.raises(ValueError, match="Telephone Imaginaire 9000"):
        pilote.open()
    assert pilote._navigateur is None  # aucun navigateur n'a été lancé


@pytest.mark.integration
def test_pixel_7_se_presente_comme_un_telephone_et_le_temoin_comme_un_ordinateur(reglages):
    sonde = (
        "() => ({ua: navigator.userAgent, touch: navigator.maxTouchPoints,"
        " hover: matchMedia('(hover: none)').matches, pointer: matchMedia('(pointer: coarse)').matches,"
        " mobile: navigator.userAgentData ? navigator.userAgentData.mobile : null,"
        " largeur: innerWidth})"
    )

    def vu_par_la_page(options):
        pilote = DriverPlaywright(HOTES, options)
        pilote.open()
        try:
            pilote.start_session()
            pilote.navigate(f"{reglages.url_site}/lab/statique")
            return pilote._page.evaluate(sonde)
        finally:
            pilote.close_session()
            pilote.close()

    with campaigns.serveur_local(reglages):
        telephone = vu_par_la_page({"appareil": "Pixel 7"})
        ordinateur = vu_par_la_page({})
    print("PIXEL 7 :", telephone)
    print("SANS OPTION :", ordinateur)
    assert telephone["touch"] > 0 and telephone["hover"] is True
    assert "Android" in telephone["ua"] and "Mobile" in telephone["ua"]
    assert ordinateur["touch"] == 0 and ordinateur["hover"] is False
    assert "Mobile" not in ordinateur["ua"]


def test_la_campagne_temoin_mobile_est_valide(reglages):
    from pathlib import Path

    experience = campaigns.lire(
        Path(__file__).resolve().parent.parent / "configs" / "experiments" / "temoin-mobile-emule.yaml", reglages
    )
    options = {m.nom_affiche: m.options for m in experience.engines}
    assert options == {
        "patchright-chrome-interface": {"headless": False, "channel": "chrome"},
        "patchright-chrome-mobile": {"headless": False, "channel": "chrome", "appareil": "Pixel 7"},
    }
    assert experience.protections == ["03", "04", "05", "06scorr"]
    assert experience.scenarios == ["static_html", "javascript_content", "pagination"]
    assert experience.repetitions == 5 and experience.seed == 20261115
