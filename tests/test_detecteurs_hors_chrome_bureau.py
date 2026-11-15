"""Quatre règles du composite ne doivent pas arrêter un humain qui n'est pas sur un Chrome de bureau.

Constat (14/11, deux sessions réelles : Safari 26 et 27 sur iPhone) : rejouées contre l'Arena, elles passent les
niveaux 01 à 03 et sont arrêtées aux niveaux 04 à 07 par le score composite, à cause de quatre signaux faibles qui
supposent « Chrome sur ordinateur » : `vendor_absent`, `hover_none`, `ratio_move_click_faible`, `no_first_paint`.
Un détecteur n'est valide que s'il laisse passer les humains ; la règle reste vraie pour un Chrome de bureau et pour
un relevé incohérent (vendor d'un autre moteur, survol absent sans aucun indice tactile, ratio faible sans toucher).
"""

from __future__ import annotations

import pytest
from test_detection import empreinte as empreinte_chrome
from test_detection import entetes_navigateur, requete
from test_rejeu import (
    COMPORTEMENT_HUMAIN,
    entetes,
    message,
    session_labo,
    t,
    verdict,
)
from test_rejeu import empreinte as empreinte_rejeu
from test_rejeu import requete as requete_rejeu

from shadowlab import database as db
from shadowlab import detection, rejeu
from shadowlab.detection import Observations, classer

UA_SAFARI_IPHONE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/26.0 Mobile/15E148 Safari/604.1"
)
UA_FIREFOX = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:140.0) Gecko/20100101 Firefox/140.0"

CSS_MEDIA_IPHONE = {"hover_hover": False, "hover_none": True, "pointer_fine": False, "pointer_none": False}
CSS_MEDIA_BUREAU = {"hover_hover": True, "hover_none": False, "pointer_fine": True, "pointer_none": False}
EVENEMENTS_TOUCHER = {"click": 2, "keydown": 0, "mousemove": 2, "scroll": 62, "touchstart": 4}
EVENEMENTS_SOURIS_LENTS = {"click": 4, "keydown": 0, "mousemove": 8, "scroll": 10, "touchstart": 0}

SIGNAUX_VISES = {"vendor_absent", "hover_none", "ratio_move_click_faible", "no_first_paint"}


def entetes_safari():
    return [h for h in entetes_navigateur(UA_SAFARI_IPHONE) if not h[0].startswith("sec-ch-ua")]


def observation(*, navigateur="chrome", vendor=None, css_media=None, touch=None, paint=None, evenements=None):
    """Observation d'un navigateur (`chrome` ou `safari`), avec les relevés dont les quatre règles se servent."""
    if navigateur == "safari":
        e = empreinte_chrome(userAgent=UA_SAFARI_IPHONE, userAgentData=None, platform="iPhone")
        http = [requete(entetes_safari())]
        vendor_defaut = "Apple Computer, Inc."
        touch_defaut = 5
    else:
        e = empreinte_chrome()
        http = [requete(entetes_navigateur())]
        vendor_defaut = "Google Inc."
        touch_defaut = 0
    e["payload"]["navigateur"]["maxTouchPoints"] = touch_defaut if touch is None else touch
    e["payload"]["languages_test"] = {
        "language": "fr-FR",
        "languages": ["fr-FR", "fr"],
        "vendor": vendor_defaut if vendor is None else vendor,
    }
    if css_media is not None:
        e["payload"]["css_media"] = css_media
    if paint is not None:
        e["payload"]["paint_timing"] = paint
    js = [e]
    if evenements is not None:
        js.append(
            {
                "kind": "comportement",
                "page": "/lab/statique",
                "payload": {"evenements": evenements, "duree_page_ms": 12000},
            }
        )
    return Observations(http=http, js=js)


def signaux(obs, detecteur):
    (c,) = [c for c in classer(obs) if c.detector_name == detecteur]
    return {s.code for s in c.signals}, c


# --- Aides partagées -------------------------------------------------------------------------------


def test_famille_chromium_par_user_agent_data():
    obs = observation()
    assert detection.famille_navigateur(obs, obs.empreinte_js) == "chromium"


def test_famille_chromium_par_en_tete_sec_ch_ua_seul():
    e = empreinte_chrome(userAgent="Mozilla/5.0 (X11; Linux x86_64)", userAgentData=None)
    obs = Observations(http=[requete(entetes_navigateur("Mozilla/5.0 (X11; Linux x86_64)"))], js=[e])
    assert detection.famille_navigateur(obs, obs.empreinte_js) == "chromium"


def test_famille_webkit_pour_safari_sur_iphone():
    obs = observation(navigateur="safari")
    assert detection.famille_navigateur(obs, obs.empreinte_js) == "webkit"


def test_famille_gecko_pour_firefox():
    e = empreinte_chrome(userAgent=UA_FIREFOX, userAgentData=None, platform="MacIntel")
    http = [requete([h for h in entetes_navigateur(UA_FIREFOX) if not h[0].startswith("sec-ch-ua")])]
    obs = Observations(http=http, js=[e])
    assert detection.famille_navigateur(obs, obs.empreinte_js) == "gecko"


def test_famille_inconnue_sans_indice():
    e = empreinte_chrome(userAgent="curl/8.0", userAgentData=None)
    obs = Observations(http=[requete([["user-agent", "curl/8.0"]])], js=[e])
    assert detection.famille_navigateur(obs, obs.empreinte_js) is None


def test_tactile_quand_plusieurs_indices_concordent():
    obs = observation(navigateur="safari", css_media=CSS_MEDIA_IPHONE)
    assert detection.appareil_tactile(obs, obs.empreinte_js) is True


def test_tactile_par_points_de_contact_et_evenements_de_toucher():
    obs = observation(navigateur="safari", evenements=EVENEMENTS_TOUCHER)
    assert detection.appareil_tactile(obs, obs.empreinte_js) is True


def test_un_seul_indice_ne_suffit_pas_pour_etre_tactile():
    # Ordinateur à écran tactile : points de contact, mais pointeur fin et survol présents.
    obs = observation(touch=10, css_media=CSS_MEDIA_BUREAU)
    assert detection.appareil_tactile(obs, obs.empreinte_js) is False
    # Seul le survol est absent (headless) : aucun point de contact.
    obs = observation(touch=0, css_media=CSS_MEDIA_IPHONE)
    assert detection.appareil_tactile(obs, obs.empreinte_js) is False
    # Seuls des événements de toucher sont relevés.
    obs = observation(touch=0, evenements=EVENEMENTS_TOUCHER)
    assert detection.appareil_tactile(obs, obs.empreinte_js) is False


# --- vendor_absent ---------------------------------------------------------------------------------


def test_vendor_apple_sous_safari_n_est_pas_un_signal():
    codes, _ = signaux(observation(navigateur="safari"), "langues")
    assert "vendor_absent" not in codes


def test_vendor_vide_sous_firefox_n_est_pas_un_signal():
    e = empreinte_chrome(userAgent=UA_FIREFOX, userAgentData=None, platform="MacIntel")
    e["payload"]["languages_test"] = {"language": "fr-FR", "languages": ["fr-FR", "fr"], "vendor": ""}
    http = [requete([h for h in entetes_navigateur(UA_FIREFOX) if not h[0].startswith("sec-ch-ua")])]
    codes, _ = signaux(Observations(http=http, js=[e]), "langues")
    assert "vendor_absent" not in codes


def test_vendor_absent_sous_chrome_reste_un_signal():
    codes, _ = signaux(observation(vendor=""), "langues")
    assert "vendor_absent" in codes


def test_vendor_apple_sous_un_chromium_reste_suspect():
    codes, _ = signaux(observation(vendor="Apple Computer, Inc."), "langues")
    assert "vendor_absent" in codes


def test_vendor_google_sous_safari_reste_suspect():
    codes, _ = signaux(observation(navigateur="safari", vendor="Google Inc."), "langues")
    assert "vendor_absent" in codes


def test_vendor_famille_inconnue_garde_le_comportement_d_avant():
    e = empreinte_chrome(userAgent="curl/8.0", userAgentData=None)
    e["payload"]["languages_test"] = {
        "language": "fr-FR",
        "languages": ["fr-FR", "fr"],
        "vendor": "Apple Computer, Inc.",
    }
    codes, _ = signaux(Observations(http=[requete([["user-agent", "curl/8.0"]])], js=[e]), "langues")
    assert "vendor_absent" in codes


# --- hover_none ------------------------------------------------------------------------------------


def test_hover_none_sur_iphone_n_est_pas_un_signal():
    codes, _ = signaux(observation(navigateur="safari", css_media=CSS_MEDIA_IPHONE), "css-media")
    assert "hover_none" not in codes


def test_hover_none_sur_chrome_de_bureau_reste_un_signal():
    codes, _ = signaux(observation(css_media=CSS_MEDIA_IPHONE), "css-media")
    assert "hover_none" in codes


def test_hover_none_sans_aucun_indice_tactile_reste_suspect():
    # Safari qui se dit sans survol mais sans point de contact : rien ne dit « téléphone ».
    codes, _ = signaux(observation(navigateur="safari", touch=0, css_media=CSS_MEDIA_IPHONE), "css-media")
    assert "hover_none" in codes


# --- ratio_move_click_faible -----------------------------------------------------------------------


def test_ratio_faible_au_toucher_n_est_pas_un_signal():
    obs = observation(navigateur="safari", css_media=CSS_MEDIA_IPHONE, evenements=EVENEMENTS_TOUCHER)
    codes, _ = signaux(obs, "comportement")
    assert "ratio_move_click_faible" not in codes


def test_ratio_faible_a_la_souris_reste_un_signal():
    obs = observation(css_media=CSS_MEDIA_BUREAU, evenements={**EVENEMENTS_TOUCHER, "touchstart": 0})
    codes, _ = signaux(obs, "comportement")
    assert "ratio_move_click_faible" in codes


def test_ratio_faible_sans_toucher_reste_suspect_meme_sur_safari():
    obs = observation(navigateur="safari", css_media=CSS_MEDIA_IPHONE, evenements=EVENEMENTS_SOURIS_LENTS)
    codes, _ = signaux(obs, "comportement")
    assert "ratio_move_click_faible" in codes


def test_ratio_faible_avec_toucher_sur_ordinateur_reste_suspect():
    # Des « touchstart » seuls, sur un Chrome de bureau (pointeur fin, survol, aucun point de contact).
    obs = observation(css_media=CSS_MEDIA_BUREAU, evenements=EVENEMENTS_TOUCHER)
    codes, _ = signaux(obs, "comportement")
    assert "ratio_move_click_faible" in codes


# --- no_first_paint --------------------------------------------------------------------------------

PAINT_SANS_FIRST_PAINT = {"count": 1, "has_first_paint": False, "has_first_contentful_paint": True}


def test_pas_de_first_paint_sous_safari_n_est_pas_un_signal():
    codes, _ = signaux(observation(navigateur="safari", paint=PAINT_SANS_FIRST_PAINT), "paint-timing")
    assert codes == set()


def test_pas_de_first_paint_sous_chrome_reste_un_signal():
    codes, _ = signaux(observation(paint=PAINT_SANS_FIRST_PAINT), "paint-timing")
    assert "no_first_paint" in codes


def test_safari_sans_first_contentful_paint_reste_suspect():
    paint = {"count": 1, "has_first_paint": False, "has_first_contentful_paint": False}
    codes, _ = signaux(observation(navigateur="safari", paint=paint), "paint-timing")
    assert codes == {"no_fcp"}


# --- Versions --------------------------------------------------------------------------------------


@pytest.mark.parametrize("detecteur", ["langues", "css-media", "comportement", "paint-timing"])
def test_versions_revisees(detecteur):
    _, c = signaux(
        observation(navigateur="safari", css_media=CSS_MEDIA_IPHONE, evenements=EVENEMENTS_TOUCHER), detecteur
    )
    assert (
        c.detector_version
        == {"langues": "1.1", "css-media": "1.1", "comportement": "2.3", "paint-timing": "1.1"}[detecteur]
    )


# --- Le rejeu --------------------------------------------------------------------------------------


def test_rejeu_session_humaine_safari_iphone_n_est_plus_arretee_par_les_quatre_signaux(tmp_path):
    cx = db.ouvrir(tmp_path / "labo.sqlite3")
    jeton = session_labo(cx)
    e = empreinte_rejeu()
    e["navigateur"] = {
        **e["navigateur"],
        "userAgent": UA_SAFARI_IPHONE,
        "userAgentData": None,
        "platform": "iPhone",
        "maxTouchPoints": 5,
    }
    e["languages_test"] = {**e["languages_test"], "vendor": "Apple Computer, Inc."}
    e["css_media"] = CSS_MEDIA_IPHONE
    e["paint_timing"] = PAINT_SANS_FIRST_PAINT
    sans_hints = [h for h in entetes() if not h[0].startswith("sec-ch-ua")]
    sans_hints = [["user-agent", UA_SAFARI_IPHONE] if h[0] == "user-agent" else h for h in sans_hints]
    requete_rejeu(cx, jeton, t(0), "/lab/vitrine", cookies=(), en_tetes=sans_hints)
    requete_rejeu(cx, jeton, t(0.2), "/lab/static/observateur.js", en_tetes=sans_hints)
    message(cx, jeton, t(1), e)
    message(cx, jeton, t(10), {**COMPORTEMENT_HUMAIN, "evenements": EVENEMENTS_TOUCHER}, kind="comportement")
    requete_rejeu(cx, jeton, t(11), "/lab/vitrine/annonces", en_tetes=sans_hints)
    resultat = rejeu.rejouer(cx)
    for code in ("04", "05", "06", "07"):
        trouves = {s["code"] for m in verdict(resultat, jeton, code)["motifs"] for s in m["signaux"]}
        assert not trouves & SIGNAUX_VISES, code
