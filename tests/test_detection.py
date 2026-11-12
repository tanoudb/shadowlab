import random
import pytest

from shadowlab.detection import Observations, classer

UA_CHROME = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/156.0.0.0 Safari/537.36"
)


def requete(entetes, chemin="/lab/statique", cookies=()):
    return {"path": chemin, "http_version": "1.1", "headers": entetes, "cookies": list(cookies), "method": "GET"}


def entetes_navigateur(ua=UA_CHROME):
    return [
        ["host", "127.0.0.1:8770"],
        ["sec-ch-ua", '"Chromium";v="156", "Google Chrome";v="156"'],
        ["sec-ch-ua-platform", '"macOS"'],
        ["user-agent", ua],
        ["accept", "text/html,application/xhtml+xml"],
        ["sec-fetch-site", "none"],
        ["sec-fetch-mode", "navigate"],
        ["accept-language", "fr-FR,fr;q=0.9"],
    ]


def empreinte(**surcharges):
    nav = {
        "userAgent": UA_CHROME,
        "language": "fr-FR",
        "languages": ["fr-FR", "fr"],
        "webdriver": False,
        "plugins": 5,
        "userAgentData": {"brands": [{"brand": "Google Chrome"}], "platform": "macOS"},
    }
    nav.update(surcharges)
    return {
        "kind": "empreinte",
        "page": "/lab/statique",
        "payload": {
            "navigateur": nav,
            "fenetre": {"outerWidth": 1280, "outerHeight": 800},
            "permissions": {"notification": "default", "query": "prompt"},
            "webgl": {"renderer": "Apple M5 Pro"},
            "botd": {"bot": False},
        },
    }


def verdicts(obs):
    return {c.detector_name: c.classification for c in classer(obs)}


def regles_http(obs):
    return next(c for c in classer(obs) if c.detector_name == "regles-http")


def test_headless_dans_une_requete_tardive_classe_automatise():
    """Campagne 94 : la première page a une identité réécrite, 16 % des requêtes suivantes disent « HeadlessChrome »."""
    envoi = [
        ["host", "127.0.0.1:8770"],
        ["user-agent", UA_CHROME.replace("Chrome/", "HeadlessChrome/")],
        ["content-type", "application/json"],
    ]
    obs = Observations(http=[requete(entetes_navigateur()), requete(envoi, "/lab/collecte")], js=[empreinte()])
    verdict = regles_http(obs)
    assert verdict.classification == "automatise"
    assert [s.code for s in verdict.signals] == ["headless_dans_une_requete"]
    assert "1 requête(s) sur 2" in verdict.signals[0].description

    marque = [
        e if e[0] != "sec-ch-ua" else ["sec-ch-ua", '"Chromium";v="156", "HeadlessChrome";v="156"']
        for e in entetes_navigateur()
    ]
    obs = Observations(http=[requete(entetes_navigateur()), requete(marque, "/lab/catalogue")], js=[empreinte()])
    assert regles_http(obs).classification == "automatise", "le mot dans sec-ch-ua suffit, User-Agent réécrit ou non"


def test_headless_des_la_premiere_page_n_est_pas_compte_deux_fois():
    entetes = entetes_navigateur(UA_CHROME.replace("Chrome/", "HeadlessChrome/"))
    obs = Observations(http=[requete(entetes), requete(entetes, "/lab/static/a.js")], js=[])
    codes = [s.code for s in regles_http(obs).signals]
    assert "ua_headless" in codes and "headless_dans_une_requete" not in codes


def test_navigateur_ordinaire_sur_plusieurs_requetes_reste_humain():
    entetes = entetes_navigateur()
    http = [requete(entetes), requete(entetes, "/lab/static/a.js"), requete(entetes, "/lab/collecte")]
    assert regles_http(Observations(http=http, js=[empreinte()])).classification == "humain"


def test_navigateur_ordinaire_classe_humain():
    obs = Observations(http=[requete(entetes_navigateur())], js=[empreinte()])
    v = verdicts(obs)
    assert {k: v[k] for k in ("botd", "regles-http", "regles-js", "coherence")} == dict.fromkeys(
        ("botd", "regles-http", "regles-js", "coherence"), "humain"
    )
    assert v["tls"] == "indetermine"  # hors Arena, TLS n'est pas observé


def test_webdriver_classe_automatise():
    obs = Observations(http=[requete(entetes_navigateur())], js=[empreinte(webdriver=True)])
    assert verdicts(obs)["regles-js"] == "automatise"


def test_client_sans_javascript():
    obs = Observations(http=[requete([["host", "x"], ["user-agent", "python-httpx/0.28.1"], ["accept", "*/*"]])], js=[])
    v = verdicts(obs)
    assert v["regles-http"] == "automatise"
    assert v["regles-js"] == "automatise"
    assert v["botd"] == "indetermine"
    assert v["coherence"] == "indetermine"


def test_demande_h2c_trahit_un_client_non_navigateur():
    entetes = [e for e in entetes_navigateur() if e[0] != "host"] + [
        ["host", "127.0.0.1:8770"],
        ["upgrade", "h2c"],
        ["connection", "Upgrade, HTTP2-Settings"],
    ]
    classement = next(
        c for c in classer(Observations(http=[requete(entetes)], js=[])) if c.detector_name == "regles-http"
    )
    assert classement.classification == "automatise"
    assert {s.code for s in classement.signals} >= {"h2c", "host_tardif"}


def test_user_agent_divergent_entre_http_et_javascript():
    obs = Observations(http=[requete(entetes_navigateur())], js=[empreinte(userAgent=UA_CHROME.replace("156", "120"))])
    assert verdicts(obs)["coherence"] == "automatise"


def test_scenario_sans_page_html_reste_indetermine_cote_js():
    obs = Observations(http=[requete(entetes_navigateur(), "/lab/api/articles")], js=[], attend_js=False)
    v = verdicts(obs)
    assert v["botd"] == v["regles-js"] == v["coherence"] == "indetermine"


def _comportement(**kw):
    base = {
        "evenements": {"mousemove": 30, "click": 5, "keydown": 0, "scroll": 3, "touchstart": 0},
        "premiere_interaction_ms": 120,
        "duree_page_ms": 5000,
        "delais_souris_ms": [],
        "angles_segments": [],
    }
    base.update(kw)
    return {"kind": "comportement", "page": "/lab/statique", "payload": base}


def test_entropie_trajectoire_lineaire_detectee():
    """Angles proches de 0 = trajectoire en ligne droite → détection."""
    angles = [0.01] * 15
    delais = [float(i * 20 + 5) for i in range(20)]
    obs = Observations(
        http=[requete(entetes_navigateur())],
        js=[empreinte(), _comportement(delais_souris_ms=delais, angles_segments=angles)],
    )
    v = verdicts(obs)
    assert v["entropie-interaction"] == "automatise"


def test_entropie_trajectoire_humaine_passe():
    """Angles variés = trajectoire courbe → humain."""
    import random

    rng = random.Random(42)
    angles = [rng.uniform(0.1, 0.8) for _ in range(20)]
    delais = [rng.uniform(10, 600) for _ in range(25)]
    obs = Observations(
        http=[requete(entetes_navigateur())],
        js=[empreinte(), _comportement(delais_souris_ms=delais, angles_segments=angles)],
    )
    v = verdicts(obs)
    assert v["entropie-interaction"] == "humain"


def test_entropie_frappe_reguliere_detectee():
    """Délais clavier quasi-identiques = bot."""
    delais_souris = [float(i * 30 + 10) for i in range(20)]
    delais_clavier = [100.0] * 12  # CV = 0
    obs = Observations(
        http=[requete(entetes_navigateur())],
        js=[
            empreinte(),
            _comportement(
                delais_souris_ms=delais_souris,
                delais_clavier_ms=delais_clavier,
            ),
        ],
    )
    v = verdicts(obs)
    assert v["entropie-interaction"] == "automatise"


def test_entropie_frappe_humaine_passe():
    """Délais clavier variés = humain."""
    import random

    rng = random.Random(99)
    delais_souris = [rng.uniform(10, 600) for _ in range(20)]
    delais_clavier = [rng.uniform(60, 300) for _ in range(15)]
    obs = Observations(
        http=[requete(entetes_navigateur())],
        js=[
            empreinte(),
            _comportement(
                delais_souris_ms=delais_souris,
                delais_clavier_ms=delais_clavier,
            ),
        ],
    )
    v = verdicts(obs)
    assert v["entropie-interaction"] == "humain"


# --- Règles `pas_de_scroll` et `pas_de_pause` justes envers les humains (12/11/2026, campagne 94) ---


def _signaux(obs, detecteur):
    """Signaux d'un détecteur : code → poids."""
    return {s.code: s.poids for s in next(c for c in classer(obs) if c.detector_name == detecteur).signals}


def _session(*pages):
    return Observations(http=[requete(entetes_navigateur())], js=[empreinte(), *pages])


def _page_sans_defilement(**kw):
    """Relevé d'une page où la souris bouge (30 mouvements) sans aucun événement `scroll`."""
    return _comportement(evenements={"mousemove": 30, "click": 1, "keydown": 0, "scroll": 0, "touchstart": 0}, **kw)


def _geste_continu(n=50):
    """Délais d'un geste de souris continu : de 8 à 70 ms, aucun au-delà de 80 ms."""
    rng = random.Random(7)
    return [round(rng.uniform(8, 70), 2) for _ in range(n)]


def test_pas_de_scroll_ignore_les_pages_plus_courtes_que_la_fenetre():
    """`/lab/catalogue` (campagne 94) : la molette tourne mais la page, plus courte que la fenêtre, n'émet aucun
    `scroll`. Un humain y serait classé de même : seules les pages qui pouvaient défiler comptent."""
    courte = _page_sans_defilement(page_defilable=False, wheel_deltas=[100.0, 120.0, 100.0, 80.0, 100.0])
    assert "pas_de_scroll" not in _signaux(_session(courte, courte), "comportement")
    # Une page qui pouvait défiler et une page courte : une seule page comptée, il en faut deux.
    defilable = _page_sans_defilement(page_defilable=True)
    assert "pas_de_scroll" not in _signaux(_session(defilable, courte), "comportement")


def test_pas_de_scroll_deux_pages_defilables_sans_defilement():
    defilable = _page_sans_defilement(page_defilable=True)
    assert _signaux(_session(defilable, defilable), "comportement").get("pas_de_scroll") == 0.35


def test_pas_de_scroll_releve_ancien_ne_conclut_pas():
    """Relevé d'avant le 12/11, sans `page_defilable` : on ne sait pas si la page pouvait défiler."""
    ancienne = _page_sans_defilement()
    assert "pas_de_scroll" not in _signaux(_session(ancienne, ancienne), "comportement")


def test_pas_de_pause_juge_la_page_entiere():
    """Campagne 94 : un geste continu remplit les 50 délais gardés (≈ 1,5 s) ; la pause vient plus tard."""
    releve = _comportement(delais_souris_ms=_geste_continu(), delai_souris_max_ms=900.0, duree_page_ms=3200)
    assert "pas_de_pause" not in _signaux(_session(releve), "entropie-interaction")


def test_pas_de_pause_page_entiere_sans_pause():
    delais = _geste_continu()
    releve = _comportement(delais_souris_ms=delais, delai_souris_max_ms=max(delais))
    assert _signaux(_session(releve), "entropie-interaction").get("pas_de_pause") == 0.5


def test_pas_de_pause_releve_ancien_plafonne_ne_conclut_pas():
    """Relevé d'avant le 12/11, sans `delai_souris_max_ms`, liste pleine (50) : la suite de la page est inconnue."""
    releve = _comportement(delais_souris_ms=_geste_continu(50))
    assert "pas_de_pause" not in _signaux(_session(releve), "entropie-interaction")


def test_pas_de_pause_releve_ancien_sous_le_plafond_juge_sa_liste():
    """Sous le plafond, la liste d'un relevé ancien contient tous les délais de la page : la règle reste valable."""
    releve = _comportement(delais_souris_ms=_geste_continu(30))
    assert _signaux(_session(releve), "entropie-interaction").get("pas_de_pause") == 0.5


# --- Détecteur AudioContext ---


def _avec_sonde(cle, **kw):
    """Construit une empreinte avec une sonde supplémentaire dans le payload (pas dans navigateur)."""
    e = empreinte()
    e["payload"][cle] = kw
    return e


def _empreinte_audio(**kw):
    base = {
        "available": True,
        "constructor_natif": True,
        "startRendering_natif": True,
        "createOscillator_natif": True,
        "nonzero": True,
        "stable": True,
        "sum": 124.5,
        "hash": -1234567,
    }
    base.update(kw)
    return _avec_sonde("audio_context", **base)


def test_audio_context_humain():
    obs = Observations(http=[requete(entetes_navigateur())], js=[_empreinte_audio()])
    assert verdicts(obs)["audio-context"] == "humain"


def test_audio_context_patche():
    obs = Observations(
        http=[requete(entetes_navigateur())], js=[_empreinte_audio(constructor_natif=False, startRendering_natif=False)]
    )
    assert verdicts(obs)["audio-context"] == "automatise"


def test_audio_context_zeros():
    obs = Observations(http=[requete(entetes_navigateur())], js=[_empreinte_audio(nonzero=False)])
    v = verdicts(obs)
    assert v["audio-context"] in ("automatise", "indetermine")


def test_audio_context_instable():
    obs = Observations(http=[requete(entetes_navigateur())], js=[_empreinte_audio(stable=False)])
    c = next(c for c in classer(obs) if c.detector_name == "audio-context")
    assert any(s.code == "audio_instable" for s in c.signals)
    assert c.signals[0].poids == 0.8


# --- Détecteur Polices ---


def _empreinte_polices(**kw):
    base = {
        "presentes": ["Arial", "Helvetica", "Menlo", "Helvetica Neue", "Georgia"],
        "absentes": ["Segoe UI", "Calibri"],
        "count": 5,
        "os_declare": "macOS",
        "os_manquantes": [],
        "os_inattendues": [],
    }
    base.update(kw)
    return _avec_sonde("font_fingerprint", **base)


def test_polices_humain():
    obs = Observations(http=[requete(entetes_navigateur())], js=[_empreinte_polices()])
    assert verdicts(obs)["polices"] == "humain"


def test_polices_tres_peu():
    obs = Observations(http=[requete(entetes_navigateur())], js=[_empreinte_polices(count=1, presentes=["Arial"])])
    c = next(c for c in classer(obs) if c.detector_name == "polices")
    assert any(s.code == "tres_peu_polices" for s in c.signals)


def test_polices_os_incoherent():
    obs = Observations(
        http=[requete(entetes_navigateur())],
        js=[_empreinte_polices(os_manquantes=["Menlo", "Helvetica Neue"], os_inattendues=["Segoe UI"])],
    )
    assert verdicts(obs)["polices"] == "automatise"


# --- Détecteur MathConstants ---


def _empreinte_math(**kw):
    base = {"tan": -0.6112, "acos": 1.447, "cos_natif": True, "tan_natif": True, "random_natif": True}
    base.update(kw)
    return _avec_sonde("math_constants", **base)


def test_math_humain():
    obs = Observations(http=[requete(entetes_navigateur())], js=[_empreinte_math()])
    assert verdicts(obs)["math-constants"] == "humain"


def test_math_patche():
    obs = Observations(http=[requete(entetes_navigateur())], js=[_empreinte_math(cos_natif=False, tan_natif=False)])
    assert verdicts(obs)["math-constants"] == "automatise"


# --- Détecteur DOMRect ---


def _empreinte_domrect(**kw):
    base = {
        "rects": [{"font": "16px monospace", "width": 120.5, "height": 18.0}],
        "getBCR_natif": True,
        "stable": True,
        "has_subpixel": True,
    }
    base.update(kw)
    return _avec_sonde("domrect_fingerprint", **base)


def test_domrect_humain():
    obs = Observations(http=[requete(entetes_navigateur())], js=[_empreinte_domrect()])
    assert verdicts(obs)["domrect"] == "humain"


def test_domrect_patche():
    obs = Observations(http=[requete(entetes_navigateur())], js=[_empreinte_domrect(getBCR_natif=False)])
    c = next(c for c in classer(obs) if c.detector_name == "domrect")
    assert any(s.code == "getBCR_patche" for s in c.signals)


def test_domrect_instable():
    obs = Observations(http=[requete(entetes_navigateur())], js=[_empreinte_domrect(stable=False, getBCR_natif=False)])
    assert verdicts(obs)["domrect"] == "automatise"


# --- Détecteur IframeConsistency ---


def _empreinte_iframe(**kw):
    base = {
        "access": True,
        "ua_match": True,
        "platform_match": True,
        "hwc_match": True,
        "webdriver_match": True,
        "chrome_match": True,
        "own_keys_match": True,
        "screen_match": True,
        "math_tan_match": True,
        "languages_match": True,
    }
    base.update(kw)
    return _avec_sonde("iframe_test", **base)


def test_iframe_humain():
    obs = Observations(http=[requete(entetes_navigateur())], js=[_empreinte_iframe()])
    assert verdicts(obs)["iframe-consistency"] == "humain"


def test_iframe_own_keys_differ():
    obs = Observations(http=[requete(entetes_navigateur())], js=[_empreinte_iframe(own_keys_match=False)])
    c = next(c for c in classer(obs) if c.detector_name == "iframe-consistency")
    assert any(s.code == "iframe_own_keys_diff" for s in c.signals)


def test_iframe_math_patch_non_propage():
    obs = Observations(http=[requete(entetes_navigateur())], js=[_empreinte_iframe(math_tan_match=False)])
    c = next(c for c in classer(obs) if c.detector_name == "iframe-consistency")
    assert any(s.code == "iframe_math_diff" for s in c.signals)
    assert c.signals[0].poids == 0.9


def test_iframe_multiples_differences():
    obs = Observations(
        http=[requete(entetes_navigateur())],
        js=[_empreinte_iframe(ua_match=False, hwc_match=False, chrome_match=False)],
    )
    assert verdicts(obs)["iframe-consistency"] == "automatise"


# --- Deep Proxy ---


def _empreinte_deep_proxy(**kw):
    base = {
        "hwc_natif": True,
        "ua_natif": True,
        "wd_natif": True,
        "platform_natif": True,
        "dm_natif": True,
        "screen_w_natif": True,
        "hwc_illegal_invoc": True,
        "ua_illegal_invoc": True,
        "wd_illegal_invoc": True,
        "platform_illegal_invoc": True,
        "dm_illegal_invoc": True,
        "screen_w_illegal_invoc": True,
        "hwc_desc_match": True,
        "ua_desc_match": True,
        "wd_desc_match": True,
        "platform_desc_match": True,
        "dm_desc_match": True,
        "screen_w_desc_match": True,
        "navigator_proto": True,
        "navigator_constructor": True,
        "toString_natif": True,
        "toString_length": 0,
        "error_stack_lines": 3,
        "error_has_proxy": False,
    }
    base.update(kw)
    return _avec_sonde("deep_proxy", **base)


def test_deep_proxy_humain():
    obs = Observations(http=[requete(entetes_navigateur())], js=[_empreinte_deep_proxy()])
    assert verdicts(obs)["deep-proxy"] == "humain"


def test_deep_proxy_getter_non_natif():
    obs = Observations(
        http=[requete(entetes_navigateur())],
        js=[_empreinte_deep_proxy(hwc_natif=False, ua_natif=False)],
    )
    r = verdicts(obs)
    assert r["deep-proxy"] == "indetermine" or any(
        s.name == "getter_non_natif"
        for c in __import__("shadowlab.detection", fromlist=["classer"]).classer(obs)
        if c.detector_name == "deep-proxy"
        for s in c.signaux
    )


def test_deep_proxy_illegal_invoc_absent():
    obs = Observations(
        http=[requete(entetes_navigateur())],
        js=[_empreinte_deep_proxy(hwc_illegal_invoc=False, ua_illegal_invoc=False)],
    )
    from shadowlab.detection import classer as _classer

    resultats = {c.detector_name: c for c in _classer(obs)}
    dp = resultats["deep-proxy"]
    codes = [s.code for s in dp.signals]
    assert "illegal_invoc_absent" in codes


def test_deep_proxy_toString_patche():
    obs = Observations(
        http=[requete(entetes_navigateur())],
        js=[_empreinte_deep_proxy(toString_natif=False)],
    )
    from shadowlab.detection import classer as _classer

    resultats = {c.detector_name: c for c in _classer(obs)}
    dp = resultats["deep-proxy"]
    codes = [s.code for s in dp.signals]
    assert "toString_patche" in codes
    assert dp.signals[0].poids == 0.9


def test_deep_proxy_proxy_dans_stack():
    obs = Observations(
        http=[requete(entetes_navigateur())],
        js=[_empreinte_deep_proxy(error_has_proxy=True)],
    )
    from shadowlab.detection import classer as _classer

    resultats = {c.detector_name: c for c in _classer(obs)}
    dp = resultats["deep-proxy"]
    codes = [s.code for s in dp.signals]
    assert "proxy_dans_stack" in codes


def test_deep_proxy_cumul_automatise():
    obs = Observations(
        http=[requete(entetes_navigateur())],
        js=[_empreinte_deep_proxy(toString_natif=False, error_has_proxy=True, navigator_proto=False)],
    )
    assert verdicts(obs)["deep-proxy"] == "automatise"


# --- Détecteur CDP ---


def _cdp_ordinaire(**kw):
    """Bloc `cdp_detection` d'un navigateur ordinaire : outils de développement fermés, relevé fait environ
    0,2 s après le chargement, donc avant tout clic. L'instruction `debugger` ne coûte que quelques
    microsecondes (0 ms au grain de l'horloge, 0,1 ms) et aucune entrée first-input n'existe encore. Les trois
    moteurs des campagnes 90 à 94 envoient exactement ces valeurs."""
    base = {
        "stack_has_evaluate": False,
        "stack_has_cdp_session": False,
        "debugger_delta_ms": 0,
        "debugger_suspect": True,
        "cdp_resource_entries": 0,
        "empty_script_tags": 0,
        "heap_ratio": 0.012,
        "console_log_natif": True,
        "console_debug_natif": True,
        "trusted_types_available": True,
        "tt_policy_count": 0,
        "has_first_input": False,
    }
    base.update(kw)
    return _avec_sonde("cdp_detection", **base)


def _cdp(**kw):
    obs = Observations(http=[requete(entetes_navigateur())], js=[_cdp_ordinaire(**kw)])
    return next(c for c in classer(obs) if c.detector_name == "cdp")


@pytest.mark.parametrize(
    ("delta", "suspect", "premier_clic"),
    [
        (0, True, False),  # outils fermés, horloge sans tic entre les deux lectures, relevé avant tout clic
        (0.1, False, False),  # même navigateur, un tic d'horloge tombé entre les deux lectures
        (0, True, True),  # une personne qui a déjà cliqué
        (2500.0, False, False),  # outils de développement ouverts : `debugger` met la page en pause
    ],
)
def test_cdp_navigateur_ordinaire_n_est_pas_classe(delta, suspect, premier_clic):
    """Ni la durée de `debugger` ni l'absence d'un premier clic au moment du relevé ne trahissent un pilotage :
    aucun signal, donc rien non plus pour le score composite."""
    c = _cdp(debugger_delta_ms=delta, debugger_suspect=suspect, has_first_input=premier_clic)
    assert c.classification == "humain"
    assert c.signals == []


@pytest.mark.parametrize(
    ("releve", "code", "poids"),
    [
        ({"stack_has_evaluate": True}, "cdp_evaluate", 1.0),
        ({"stack_has_cdp_session": True}, "cdp_session", 1.0),
        ({"cdp_resource_entries": 2}, "cdp_resources", 0.8),
        ({"empty_script_tags": 1}, "scripts_injectes", 0.5),
        ({"console_log_natif": False}, "console_patche", 0.5),
    ],
)
def test_cdp_signal_garde_son_effet(releve, code, poids):
    c = _cdp(**releve)
    assert [(s.code, s.poids) for s in c.signals] == [(code, poids)]
    assert c.classification == ("automatise" if poids >= 1.0 else "indetermine")


def test_cdp_signaux_moyens_cumules():
    c = _cdp(empty_script_tags=1, console_log_natif=False)
    assert c.classification == "automatise"
    assert {s.code for s in c.signals} == {"scripts_injectes", "console_patche"}


# --- Détecteur TLS v2 ---

UA_FIREFOX = "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"
UA_EDGE = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/156.0.0.0 Safari/537.36 Edg/156.0.0.0"
)
UA_SAFARI = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Safari/605.1.15"
)

_CHIFFREMENTS_CHROME = [
    "1301",
    "1302",
    "1303",
    "c02b",
    "c02f",
    "c02c",
    "c030",
    "cca9",
    "cca8",
    "c013",
    "c014",
    "009c",
    "009d",
    "002f",
    "0035",
]
_EXTENSIONS_CHROME = [
    "0000",
    "0017",
    "ff01",
    "000a",
    "000b",
    "0023",
    "0010",
    "0005",
    "000d",
    "0012",
    "002b",
    "002d",
    "0033",
    "001b",
    "4469",
]
_GROUPES_CHROME = ["001d", "0017", "0018"]
_SIGNATURES_CHROME = ["0403", "0503", "0603", "0807", "0808", "0809", "0401", "0501", "0601"]


def _tls_chrome(**surcharges):
    base = {
        "ja3": "placeholder",
        "ja3_hash": "00000000000000000000000000000000",
        "ja4": "t13d150900_placeholder",
        "version_legacy": 771,
        "versions": [772, 771],
        "sni": "127.0.0.1",
        "alpn": ["h2", "http/1.1"],
        "grease": True,
        "nb_chiffrements": 15,
        "nb_extensions": 15,
        "chiffrements": list(_CHIFFREMENTS_CHROME),
        "extensions": list(_EXTENSIONS_CHROME),
        "groupes": list(_GROUPES_CHROME),
        "signatures": list(_SIGNATURES_CHROME),
    }
    base.update(surcharges)
    return base


def _tls_firefox(**surcharges):
    base = _tls_chrome(
        grease=False,
        extensions=[
            "0000",
            "0017",
            "ff01",
            "000a",
            "000b",
            "0023",
            "0010",
            "0005",
            "000d",
            "0012",
            "002b",
            "002d",
            "0033",
            "001c",
            "0022",
        ],
        groupes=["001d", "0017", "0100"],
        nb_extensions=15,
        chiffrements=[
            "1301",
            "1302",
            "1303",
            "c02b",
            "c02f",
            "c02c",
            "c030",
            "cca9",
            "cca8",
            "c009",
            "c00a",
            "c013",
            "c014",
            "009c",
            "009d",
            "002f",
            "0035",
        ],
        nb_chiffrements=17,
    )
    base.update(surcharges)
    return base


def _tls_verdict(ua, tls_data):
    obs = Observations(
        http=[requete(entetes_navigateur(ua=ua))],
        js=[empreinte()],
        tls=tls_data,
    )
    return next(c for c in classer(obs) if c.detector_name == "tls")


def _tls_signaux(ua, tls_data):
    return {s.code for s in _tls_verdict(ua, tls_data).signals}


def test_tls_chrome_authentique_humain():
    c = _tls_verdict(UA_CHROME, _tls_chrome())
    assert c.classification == "humain"


def test_tls_firefox_authentique_humain():
    c = _tls_verdict(UA_FIREFOX, _tls_firefox())
    assert c.classification == "humain"


def test_tls_chrome_sans_grease():
    s = _tls_signaux(UA_CHROME, _tls_chrome(grease=False))
    assert "chrome_sans_grease" in s


def test_tls_edge_sans_grease():
    s = _tls_signaux(UA_EDGE, _tls_chrome(grease=False))
    assert "chrome_sans_grease" in s


def test_tls_firefox_avec_grease():
    s = _tls_signaux(UA_FIREFOX, _tls_firefox(grease=True))
    assert "firefox_avec_grease" in s


def test_tls_navigateur_sans_h2():
    s = _tls_signaux(UA_CHROME, _tls_chrome(alpn=["http/1.1"]))
    assert "navigateur_sans_h2" in s


def test_tls_pile_non_navigateur():
    tls = _tls_chrome(grease=False, alpn=["http/1.1"])
    obs = Observations(
        http=[requete([["host", "x"], ["user-agent", "python-httpx/0.28.1"], ["accept", "*/*"]])],
        js=[],
        tls=tls,
    )
    c = next(c for c in classer(obs) if c.detector_name == "tls")
    assert "pile_non_navigateur" in {s.code for s in c.signals}


def test_tls_peu_de_chiffrements():
    s = _tls_signaux(UA_CHROME, _tls_chrome(chiffrements=["1301", "c02b"], nb_chiffrements=2))
    assert "peu_de_chiffrements" in s


def test_tls_chiffrements_insuffisants_navigateur():
    s = _tls_signaux(UA_CHROME, _tls_chrome(chiffrements=_CHIFFREMENTS_CHROME[:8], nb_chiffrements=8))
    assert "chiffrements_insuffisants" in s


def test_tls_peu_d_extensions():
    s = _tls_signaux(UA_CHROME, _tls_chrome(extensions=["0000", "000a"], nb_extensions=2))
    assert "peu_d_extensions" in s


def test_tls_sans_tls13_suites():
    s = _tls_signaux(UA_CHROME, _tls_chrome(chiffrements=["c02b", "c02f", "c02c", "c030"] * 4, nb_chiffrements=16))
    assert "sans_tls13_suites" in s


def test_tls_tls13_pas_en_tete():
    ciphers = ["c02b"] + _CHIFFREMENTS_CHROME
    s = _tls_signaux(UA_CHROME, _tls_chrome(chiffrements=ciphers, nb_chiffrements=len(ciphers)))
    assert "tls13_pas_en_tete" in s


def test_tls_chrome_sans_compress_certificate():
    ext_sans_cc = [e for e in _EXTENSIONS_CHROME if e != "001b"]
    s = _tls_signaux(UA_CHROME, _tls_chrome(extensions=ext_sans_cc, nb_extensions=len(ext_sans_cc)))
    assert "chrome_ext_manquantes" in s


def test_tls_chrome_sans_alps():
    ext_sans_alps = [e for e in _EXTENSIONS_CHROME if e != "4469"]
    s = _tls_signaux(UA_CHROME, _tls_chrome(extensions=ext_sans_alps, nb_extensions=len(ext_sans_alps)))
    assert "chrome_sans_alps" in s


def test_tls_chrome_alps_nouveau_numero():
    """Chrome récent annonce ALPS sous le numéro 17613 (44cd), plus sous 17513 (4469) : ce n'est pas un Chrome
    sans ALPS. Relevé sur les 180 ClientHello de la campagne 93 (Chromium 156) : 44cd partout, 4469 nulle part."""
    exts = ["44cd" if e == "4469" else e for e in _EXTENSIONS_CHROME]
    s = _tls_signaux(UA_CHROME, _tls_chrome(extensions=exts))
    assert "chrome_sans_alps" not in s


def test_tls_firefox_avec_alps_nouveau_numero():
    exts = _tls_firefox()["extensions"] + ["44cd"]
    s = _tls_signaux(UA_FIREFOX, _tls_firefox(extensions=exts, nb_extensions=len(exts)))
    assert "firefox_ext_chrome" in s


def test_tls_firefox_sans_record_size():
    ext_sans_rs = [e for e in _tls_firefox()["extensions"] if e != "001c"]
    s = _tls_signaux(UA_FIREFOX, _tls_firefox(extensions=ext_sans_rs, nb_extensions=len(ext_sans_rs)))
    assert "firefox_sans_record_size" in s


def test_tls_firefox_avec_compress_certificate():
    exts = _tls_firefox()["extensions"] + ["001b"]
    s = _tls_signaux(UA_FIREFOX, _tls_firefox(extensions=exts, nb_extensions=len(exts)))
    assert "firefox_avec_compress_cert" in s


def test_tls_firefox_ext_chrome():
    exts = _tls_firefox()["extensions"] + ["001b", "4469"]
    s = _tls_signaux(UA_FIREFOX, _tls_firefox(extensions=exts, nb_extensions=len(exts)))
    assert "firefox_ext_chrome" in s


def test_tls_sans_x25519():
    s = _tls_signaux(UA_CHROME, _tls_chrome(groupes=["0017", "0018"]))
    assert "sans_x25519" in s


def test_tls_chrome_avec_ffdhe():
    s = _tls_signaux(UA_CHROME, _tls_chrome(groupes=["001d", "0017", "0100"]))
    assert "chrome_avec_ffdhe" in s


def test_tls_firefox_sans_ffdhe():
    s = _tls_signaux(UA_FIREFOX, _tls_firefox(groupes=["001d", "0017"]))
    assert "firefox_sans_ffdhe" in s


def test_tls_groupes_desordre():
    s = _tls_signaux(UA_CHROME, _tls_chrome(groupes=["0017", "001d", "0018"]))
    assert "groupes_desordre" in s


def test_tls_extensions_std_manquantes():
    s = _tls_signaux(UA_CHROME, _tls_chrome(extensions=["0000", "001b", "4469"], nb_extensions=3))
    assert "extensions_std_manquantes" in s


def test_tls_sans_supported_versions():
    ext_sans_sv = [e for e in _EXTENSIONS_CHROME if e != "002b"]
    s = _tls_signaux(UA_CHROME, _tls_chrome(extensions=ext_sans_sv, nb_extensions=len(ext_sans_sv)))
    assert "sans_supported_versions" in s


def test_tls_sans_signatures():
    s = _tls_signaux(UA_CHROME, _tls_chrome(signatures=[]))
    assert "sans_signatures" in s


def test_tls_peu_de_signatures():
    s = _tls_signaux(UA_CHROME, _tls_chrome(signatures=["0403", "0503"]))
    assert "peu_de_signatures" in s


def test_tls_pas_tls13_version():
    s = _tls_signaux(UA_CHROME, _tls_chrome(versions=[771]))
    assert "pas_tls13_version" in s


def test_tls_pile_openssl():
    tls = _tls_chrome(grease=False, alpn=["http/1.1"], chiffrements=["1302", "1301", "c02f", "c030"] * 3)
    obs = Observations(
        http=[requete([["host", "x"], ["user-agent", "python-httpx/0.28.1"], ["accept", "*/*"]])],
        js=[],
        tls=tls,
    )
    c = next(c for c in classer(obs) if c.detector_name == "tls")
    assert "pile_openssl" in {s.code for s in c.signals}


def test_tls_cumul_signaux_automatise():
    """Plusieurs signaux TLS faibles doivent cumuler en « automatisé »."""
    tls = _tls_chrome(
        grease=False,
        alpn=["http/1.1"],
        chiffrements=["c02b", "c02f"],
        nb_chiffrements=2,
    )
    c = _tls_verdict(UA_CHROME, tls)
    assert c.classification == "automatise"
    assert len(c.signals) >= 3


# ─────────────────────────────────────────────────────────────
# Détecteur HTTP/2 (h2)
# ─────────────────────────────────────────────────────────────


def _h2_chrome_data():
    return {
        "settings": [[1, 65536], [2, 0], [3, 1000], [4, 6291456], [6, 262144]],
        "window_update": 15663105,
        "priorites": [],
        "empreinte": "S[1:65536;2:0;3:1000;4:6291456;6:262144]|WU[15663105]",
    }


def _h2_firefox_data():
    return {
        "settings": [[1, 65536], [4, 131072]],
        "window_update": 12517377,
        "priorites": [],
        "empreinte": "S[1:65536;4:131072]|WU[12517377]",
    }


def _h2_verdict(ua, h2_data, tls_base=None):
    tls = (tls_base or _tls_chrome()).copy()
    tls["h2"] = h2_data
    obs = Observations(http=[requete(entetes_navigateur(ua=ua))], js=[empreinte()], tls=tls)
    return next(c for c in classer(obs) if c.detector_name == "h2")


def _h2_signaux(ua, h2_data, tls_base=None):
    return {s.code for s in _h2_verdict(ua, h2_data, tls_base).signals}


def test_h2_chrome_authentique_humain():
    c = _h2_verdict(UA_CHROME, _h2_chrome_data())
    assert c.classification == "humain"


def test_h2_firefox_authentique_humain():
    c = _h2_verdict(UA_FIREFOX, _h2_firefox_data(), _tls_firefox())
    assert c.classification == "humain"


def test_h2_sans_tls():
    obs = Observations(http=[requete(entetes_navigateur())], js=[empreinte()], tls=None)
    c = next(c for c in classer(obs) if c.detector_name == "h2")
    assert c.classification == "indetermine"


def test_h2_sans_donnees_h2():
    obs = Observations(http=[requete(entetes_navigateur())], js=[empreinte()], tls=_tls_chrome())
    c = next(c for c in classer(obs) if c.detector_name == "h2")
    assert c.classification == "indetermine"


def test_h2_pas_de_settings():
    h2 = _h2_chrome_data()
    h2["settings"] = []
    assert "h2_pas_de_settings" in _h2_signaux(UA_CHROME, h2)


def test_h2_peu_de_settings():
    h2 = _h2_chrome_data()
    h2["settings"] = [[4, 6291456]]
    assert "h2_peu_de_settings" in _h2_signaux(UA_CHROME, h2)


def test_h2_chrome_iws_incorrect():
    h2 = _h2_chrome_data()
    h2["settings"] = [[1, 65536], [2, 0], [3, 1000], [4, 65535], [6, 262144]]
    assert "h2_chrome_iws" in _h2_signaux(UA_CHROME, h2)


def test_h2_firefox_iws_incorrect():
    h2 = _h2_firefox_data()
    h2["settings"] = [[1, 65536], [4, 65535]]
    assert "h2_firefox_iws" in _h2_signaux(UA_FIREFOX, h2, _tls_firefox())


def test_h2_chrome_sans_enable_push():
    h2 = _h2_chrome_data()
    h2["settings"] = [[1, 65536], [3, 1000], [4, 6291456], [6, 262144]]
    assert "h2_chrome_sans_push" in _h2_signaux(UA_CHROME, h2)


def test_h2_chrome_mcs_incorrect():
    h2 = _h2_chrome_data()
    h2["settings"] = [[1, 65536], [2, 0], [3, 100], [4, 6291456], [6, 262144]]
    assert "h2_chrome_mcs" in _h2_signaux(UA_CHROME, h2)


def test_h2_chrome_wu_incorrect():
    h2 = _h2_chrome_data()
    h2["window_update"] = 65535
    assert "h2_chrome_wu" in _h2_signaux(UA_CHROME, h2)


def test_h2_firefox_wu_incorrect():
    h2 = _h2_firefox_data()
    h2["window_update"] = 65535
    assert "h2_firefox_wu" in _h2_signaux(UA_FIREFOX, h2, _tls_firefox())


def test_h2_navigateur_sans_wu():
    h2 = _h2_chrome_data()
    h2["window_update"] = None
    assert "h2_sans_wu" in _h2_signaux(UA_CHROME, h2)


def test_h2_pile_minimale():
    h2 = {"settings": [], "window_update": None, "priorites": [], "empreinte": "S[]"}
    ua = "python-httpx/0.24"
    tls = _tls_chrome(grease=False, alpn=["h2", "http/1.1"])
    tls["h2"] = h2
    obs = Observations(http=[requete(entetes_navigateur(ua=ua))], js=[empreinte()], tls=tls)
    c = next(c for c in classer(obs) if c.detector_name == "h2")
    assert "h2_pile_minimale" in {s.code for s in c.signals}


def test_h2_hts_inattendu():
    h2 = _h2_chrome_data()
    h2["settings"] = [[1, 4096], [2, 0], [3, 1000], [4, 6291456], [6, 262144]]
    assert "h2_hts_inattendu" in _h2_signaux(UA_CHROME, h2)


def test_h2_cumul_signaux_automatise():
    """Profil h2 incohérent avec Chrome → cumul → automatisé."""
    h2 = {
        "settings": [[4, 65535]],
        "window_update": None,
        "priorites": [],
        "empreinte": "S[4:65535]",
    }
    c = _h2_verdict(UA_CHROME, h2)
    assert c.classification == "automatise"
    assert len(c.signals) >= 3


def _codes_coherence_profonde(**navigateur):
    from shadowlab.detection import DetecteurCoherenceProfonde

    obs = Observations(http=[requete(entetes_navigateur())], js=[empreinte(**navigateur)])
    return {s.code for s in DetecteurCoherenceProfonde().classer(obs).signals}


def test_device_memory_16_go_accepte():
    """Chrome 2026 annonce 16 hors Android : un humain sur 16 Go ne doit pas être signalé."""
    assert "device_memory_invalide" not in _codes_coherence_profonde(deviceMemory=16)


def test_device_memory_32_go_accepte():
    """Le Chromium 156 des témoins annonce 32 sur une machine de 64 Go (campagne 94)."""
    assert "device_memory_invalide" not in _codes_coherence_profonde(deviceMemory=32)


def test_device_memory_anciens_paliers_toujours_acceptes():
    for valeur in (0.25, 0.5, 1, 2, 4, 8):
        assert "device_memory_invalide" not in _codes_coherence_profonde(deviceMemory=valeur), valeur


def test_device_memory_valeur_inconnue_des_navigateurs_signalee():
    for valeur in (3, 12, 64):
        assert "device_memory_invalide" in _codes_coherence_profonde(deviceMemory=valeur), valeur
