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
