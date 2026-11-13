"""Liaison des cookies de défi à l'empreinte TLS : stable à la reprise de session, stricte pour un autre client.

Un vrai Chrome qui reprend sa session TLS 1.3 ajoute l'extension `pre_shared_key` (41) à son ClientHello : le JA4
change, le client non. Les cookies sont donc liés à une empreinte de liaison, le JA4 calculé sans cette extension.
"""

import http.server
import threading
from types import SimpleNamespace

from shadowlab.arena import defis, frontal, tls
from shadowlab.arena import secret as secrets_arena
from shadowlab.site import gardien

JETON = "0123456789abcdef0123456789abcdef"
# Chrome mesuré (campagne 106) : mêmes extensions avec et sans reprise, sauf `pre_shared_key` (0x0029).
EXTENSIONS_CHROME = [
    0x33,
    0x05,
    0x00,
    0xFE0D,
    0xFF01,
    0x23,
    0xCA34,
    0x0B,
    0x0D,
    0x44CD,
    0x10,
    0x17,
    0x0A,
    0x1B,
    0x2D,
    0x12,
    0x2B,
]
CHIFFREMENTS_CHROME = [
    0x1301,
    0x1302,
    0x1303,
    0xC02B,
    0xC02F,
    0xC02C,
    0xC030,
    0xCCA9,
    0xCCA8,
    0xC013,
    0xC014,
    0x9C,
    0x9D,
    0x2F,
    0x35,
]


def _hello(extensions, chiffrements=CHIFFREMENTS_CHROME, signatures=(0x0403, 0x0804, 0x0401)):
    return tls.ClientHello(
        version_legacy=0x0303,
        ciphers=list(chiffrements),
        extensions=list(extensions),
        sni="localhost",
        alpn=["h2", "http/1.1"],
        groupes=[0x11EC, 0x1D, 0x17, 0x18],
        formats_ec=[0],
        signatures=list(signatures),
        versions=[0x0304, 0x0303],
    )


def _liaison(hello):
    return tls.empreinte(hello)["liaison"]


def test_la_liaison_ignore_la_reprise_de_session_mais_pas_le_ja4():
    sans = _hello(EXTENSIONS_CHROME)
    avec = _hello([*reversed(EXTENSIONS_CHROME), 0x29])
    assert tls.ja4(sans) != tls.ja4(avec)  # le JA4 réel reste celui que voient détecteurs et rapports
    assert _liaison(sans) == _liaison(avec)
    assert tls.empreinte(avec)["ja4"] == tls.ja4(avec)


def test_la_liaison_distingue_un_autre_client():
    chrome = _hello(EXTENSIONS_CHROME)
    autres_chiffrements = _hello(EXTENSIONS_CHROME, chiffrements=CHIFFREMENTS_CHROME[:6])
    autres_extensions = _hello([*EXTENSIONS_CHROME, 0x0015])
    autres_signatures = _hello(EXTENSIONS_CHROME, signatures=(0x0403, 0x0503))
    liaisons = {_liaison(h) for h in (chrome, autres_chiffrements, autres_extensions, autres_signatures)}
    assert len(liaisons) == 4


def _entetes(reglages, liaison, profil="05", ja4="ja4-reel"):
    secret = secrets_arena.charger(reglages.dossier_arena)
    return {
        "x-shadowlab-sceau": secrets_arena.signer(secret, "obs", profil, JETON, ja4, liaison),
        "x-shadowlab-obs": "obs",
        "x-shadowlab-profil": profil,
        "x-shadowlab-session": JETON,
        "x-shadowlab-ja4": ja4,
        "x-shadowlab-liaison": liaison,
    }


def _cookies(reglages, liaison):
    secret = secrets_arena.charger(reglages.dossier_arena)
    return {
        nom: defis.creer_cookie(secret, usage, JETON, liaison)
        for usage, nom in (
            ("defi", gardien.COOKIE_DEFI),
            ("turnstile", gardien.COOKIE_TURNSTILE),
            ("recaptcha", gardien.COOKIE_RECAPTCHA),
            ("captcha", gardien.COOKIE_CAPTCHA),
        )
    }


def _poser(client, reglages, liaison):
    for nom, valeur in _cookies(reglages, liaison).items():
        client.cookies.set(nom, valeur)


def test_cookie_obtenu_sans_reprise_accepte_avec_reprise(client, reglages):
    sans = _liaison(_hello(EXTENSIONS_CHROME))
    avec = _liaison(_hello([*EXTENSIONS_CHROME, 0x29]))
    _poser(client, reglages, sans)
    # JA4 réel différent d'une connexion à l'autre, liaison identique.
    r = client.get(
        f"/lab/vitrine?sl={JETON}",
        headers=_entetes(reglages, avec, ja4="t13d1518h2_8daaf6152771_e2d80978ab2e"),
    )
    assert r.status_code == 200, r.text


def test_cookie_refuse_pour_un_client_d_empreinte_differente(client, reglages):
    chrome = _liaison(_hello(EXTENSIONS_CHROME))
    autre = _liaison(_hello(EXTENSIONS_CHROME, chiffrements=CHIFFREMENTS_CHROME[:6]))
    _poser(client, reglages, chrome)
    r = client.get(
        f"/lab/vitrine?sl={JETON}",
        headers=_entetes(reglages, autre),
    )
    assert r.status_code == 403 and r.json()["bloque_par"] == "defi-js"


def test_sans_liaison_demandee_rien_ne_change(client, reglages):
    # Niveau 04 : lier_tls est faux, le cookie n'est lié à rien, quelle que soit la valeur transmise.
    _poser(client, reglages, "")
    r = client.get(
        f"/lab/vitrine?sl={JETON}",
        headers=_entetes(reglages, "une-liaison-quelconque", profil="04"),
    )
    assert r.status_code == 200, r.text


def test_le_sceau_couvre_la_liaison(client, reglages):
    liaison = _liaison(_hello(EXTENSIONS_CHROME))
    entetes = _entetes(reglages, liaison)
    _poser(client, reglages, liaison)
    assert client.get(f"/lab/vitrine?sl={JETON}", headers=entetes).status_code == 200
    # Liaison modifiée en chemin, sceau inchangé : le sceau tombe, la requête est traitée comme venue d'ailleurs.
    falsifie = {**entetes, "x-shadowlab-liaison": "autre"}
    secret = secrets_arena.charger(reglages.dossier_arena)
    from starlette.requests import Request

    requete = Request(
        {"type": "http", "headers": [(k.encode(), v.encode()) for k, v in falsifie.items()]},
    )
    assert gardien.lire_sceau(requete, secret) is None
    intact = Request({"type": "http", "headers": [(k.encode(), v.encode()) for k, v in entetes.items()]})
    sceau = gardien.lire_sceau(intact, secret)
    assert sceau is not None and gardien.empreinte_liee(sceau) == liaison


class _Amont(http.server.BaseHTTPRequestHandler):
    recus: list[dict[str, str]] = []

    def do_GET(self):
        type(self).recus.append({k.lower(): v for k, v in self.headers.items()})
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *args):
        pass


def test_le_frontal_ecarte_les_en_tetes_internes_envoyes_par_le_client(reglages):
    _Amont.recus = []
    amont = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Amont)
    threading.Thread(target=amont.serve_forever, daemon=True).start()
    try:
        secret = b"secret-de-test"
        serveur = SimpleNamespace(reglages=reglages, secret=secret, port_aval=amont.server_address[1])
        hello = _hello(EXTENSIONS_CHROME)
        cx = frontal._Connexion.__new__(frontal._Connexion)
        cx.serveur, cx.empreinte, cx.adresse, cx.cx = serveur, tls.empreinte(hello), "127.0.0.1", None
        entetes = [
            ("Host", "localhost"),
            ("X-ShadowLab-Liaison", "forgee"),
            ("x-shadowlab-ja4", "forge"),
            ("X-SHADOWLAB-Sceau", "forge"),
            ("X-ShadowLab-Profil", "01"),
        ]
        statut, _, _ = cx._relayer("GET", "/lab/x", entetes, b"", "", "faible", None, "/lab/x")
    finally:
        amont.shutdown()
    assert statut == 200
    recu = _Amont.recus[0]
    assert recu["x-shadowlab-liaison"] == tls.empreinte(hello)["liaison"]
    assert recu["x-shadowlab-ja4"] == tls.empreinte(hello)["ja4"]
    assert recu["x-shadowlab-profil"] == "faible"
    assert secrets_arena.verifier(
        secret, recu["x-shadowlab-sceau"], "0", "faible", "", recu["x-shadowlab-ja4"], recu["x-shadowlab-liaison"]
    )
