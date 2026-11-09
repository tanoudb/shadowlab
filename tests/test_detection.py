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
