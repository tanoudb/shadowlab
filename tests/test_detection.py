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
