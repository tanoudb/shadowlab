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
