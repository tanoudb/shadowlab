"""Palier 4, étape 4.1 (D-105) : adresses IP simulées dans l'Arena et bannissement par adresse.

Le frontal accepte l'en-tête du protocole PROXY (v1 et v2) seulement d'un pair en boucle locale et seulement si le réglage
`proxy_protocole` est vrai ; l'adresse déclarée descend vers le site dans `X-ShadowLab-Adresse`, signée par
`X-ShadowLab-Adresse-Sceau` (liée à l'observation et au jeton). Le site ne croit que cette adresse : `X-Forwarded-For`,
`X-Real-IP`, `Forwarded` ou une adresse non signée envoyés par un client ne servent à rien. La migration 13 note
l'adresse sur la visite et sur le bannissement ; le bannissement par adresse n'est lu qu'au profil `endurance`.

Pièges de test : comme dans `test_bannissement.py`, derrière le frontal (sceau valide) l'application n'écrit pas
`observations_http` ; les tests insèrent leurs lignes. Les adresses sont celles des plages de documentation
(RFC 5737 : 192.0.2.0/24, 198.51.100.0/24, 203.0.113.0/24).
"""

from __future__ import annotations

import http.server
import itertools
import socket
import ssl
import threading
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from test_bannissement import AUTRE_MONDE, MONDE, PAGE, Navigateur, _bans, _entetes
from test_visiteurs import nouveau_passage, nouvelle_experience

from shadowlab import cli, config
from shadowlab import database as db
from shadowlab.arena import adresses, bannissements, frontal, profils, tls, visiteurs
from shadowlab.arena import secret as secrets_arena
from shadowlab.site import gardien

A1, A2, A3, A4 = "198.51.100.11", "198.51.100.22", "203.0.113.33", "192.0.2.44"
JETON = "0123456789abcdef0123456789abcdef"
MAINTENANT = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)
JOUR = timedelta(hours=24)
V1_SIGNATURE_V2 = b"\r\n\r\n\x00\r\nQUIT\n"


# --- Outils ------------------------------------------------------------------------------------------------


@pytest.fixture
def experience(reglages) -> int:
    return nouvelle_experience(reglages, "endurance")


@pytest.fixture
def nouvelle_session(reglages, experience):
    compteur = itertools.count(1)

    def creer(monde: str = MONDE) -> str:
        return nouveau_passage(reglages, experience, repetition=next(compteur), monde=monde)

    return creer


@pytest.fixture
def cx(reglages):
    connexion = db.ouvrir(reglages.base_donnees)
    yield connexion
    connexion.close()


@pytest.fixture
def sans_suspicion(monkeypatch):
    monkeypatch.setattr(gardien, "suspicion", lambda *a, **k: [])


def entetes_adresse(reglages, jeton: str, adresse: str, observation: str = "obs") -> dict[str, str]:
    secret = secrets_arena.charger(reglages.dossier_arena)
    return {
        "x-shadowlab-adresse": adresse,
        "x-shadowlab-adresse-sceau": adresses.signer(secret, observation, jeton, adresse),
    }


class NavigateurIp(Navigateur):
    """Un navigateur dont le frontal (simulé) a signé l'adresse `adresse` ; `extra` ajoute des en-têtes de client."""

    def __init__(self, client, reglages, adresse: str | None, profil: str = "endurance") -> None:
        super().__init__(client, reglages, profil)
        self.adresse = adresse

    def _entetes_ip(self, jeton: str, extra: dict[str, str] | None) -> dict[str, str]:
        entetes = _entetes(self.reglages, self.profil, jeton)
        if self.adresse:
            entetes.update(entetes_adresse(self.reglages, jeton, self.adresse))
        return {**entetes, **(extra or {})}

    def aller(self, jeton: str, chemin: str = PAGE, extra: dict[str, str] | None = None):
        self._preparer()
        reponse = self.client.get(f"{chemin}?sl={jeton}", headers=self._entetes_ip(jeton, extra))
        self._poser(reponse)
        return reponse

    def poster(self, jeton: str, chemin: str, extra: dict[str, str] | None = None, **corps):
        self._preparer()
        reponse = self.client.post(f"{chemin}?sl={jeton}", headers=self._entetes_ip(jeton, extra), **corps)
        self._poser(reponse)
        return reponse


def _stamp(instant: datetime) -> str:
    return instant.astimezone(UTC).isoformat(timespec="milliseconds")


def _visite_ip(cx, monde: str, visiteur: str, jeton: str, adresse: str | None, quand: datetime = MAINTENANT) -> None:
    cx.execute(
        "INSERT INTO visites (monde_id, visiteur, session_token, neuve, vue_le, adresse) VALUES (?, ?, ?, 1, ?, ?)",
        (visiteurs.identifiant_monde(cx, monde), visiteur, jeton, _stamp(quand), adresse),
    )


def _lignes(cx, requete: str, *parametres):
    return cx.execute(requete, parametres).fetchall()


def _adresses_de_visites(cx) -> list:
    return [r["adresse"] for r in _lignes(cx, "SELECT adresse FROM visites ORDER BY id")]


# --- L'en-tête PROXY : lecture et refus ---------------------------------------------------------------------


def _paire(octets: bytes) -> socket.socket:
    """Un côté lisible dont l'autre côté a déjà envoyé `octets` (le serveur ne voit que ce que le client a écrit)."""
    serveur, client = socket.socketpair()
    client.sendall(octets)
    serveur.settimeout(2)
    return serveur


def v2(famille: int, adresses: bytes, commande: int = 1, protocole: int = 1) -> bytes:
    return V1_SIGNATURE_V2 + bytes([0x20 | commande, (famille << 4) | protocole]) + len(adresses).to_bytes(2, "big") + adresses


def v2_tcp4(source: str, destination: str = "127.0.0.1", ports=(40000, 8749)) -> bytes:
    corps = socket.inet_aton(source) + socket.inet_aton(destination) + b"".join(p.to_bytes(2, "big") for p in ports)
    return v2(1, corps)


def v2_tcp6(source: str, destination: str = "::1", ports=(40000, 8749)) -> bytes:
    corps = (
        socket.inet_pton(socket.AF_INET6, source)
        + socket.inet_pton(socket.AF_INET6, destination)
        + b"".join(p.to_bytes(2, "big") for p in ports)
    )
    return v2(2, corps)


@pytest.mark.parametrize(
    ("octets", "attendu"),
    [
        (b"PROXY TCP4 198.51.100.11 127.0.0.1 40000 8749\r\n", "198.51.100.11"),
        (b"PROXY TCP6 2001:db8::7 ::1 40000 8749\r\n", "2001:db8::7"),
        (b"PROXY TCP6 ::ffff:198.51.100.11 ::1 40000 8749\r\n", "198.51.100.11"),  # v4 écrit en v6 : une seule forme
        (b"PROXY UNKNOWN\r\n", None),  # le pair ne dit rien : l'adresse du pair reste
        (b"PROXY UNKNOWN ff ff 0 0\r\n", None),
        (v2_tcp4("198.51.100.11"), "198.51.100.11"),
        (v2_tcp6("2001:db8::7"), "2001:db8::7"),
        (v2(0, b"", commande=0), None),  # commande LOCAL (sonde de santé) : rien à croire
    ],
)
def test_un_en_tete_proxy_valide_donne_l_adresse_declaree(octets, attendu):
    prise = _paire(octets)
    assert adresses.lire_entete_proxy(prise, "127.0.0.1", actif=True) == attendu


@pytest.mark.parametrize(
    "octets",
    [
        b"PROXY TCP4 999.1.1.1 127.0.0.1 1 2\r\n",  # adresse impossible
        b"PROXY TCP4 198.51.100.11 127.0.0.1 99999 2\r\n",  # port impossible
        b"PROXY TCP4 198.51.100.11 127.0.0.1 1\r\n",  # champ manquant
        b"PROXY TCP4 198.51.100.11 127.0.0.1 1 2 3\r\n",  # champ en trop
        b"PROXY TCP4 2001:db8::7 ::1 1 2\r\n",  # famille qui ne correspond pas
        b"PROXY TCP4 0.0.0.0 127.0.0.1 1 2\r\n",  # adresse non spécifiée
        b"PROXY TCP4 224.0.0.1 127.0.0.1 1 2\r\n",  # multicast
        b"PROXY TCP4 198.51.100.11 127.0.0.1 1 2\n",  # fin de ligne sans retour chariot
        b"PROXY SCTP4 198.51.100.11 127.0.0.1 1 2\r\n",  # protocole inconnu
        b"PROXY " + b"x" * 200 + b"\r\n",  # plus de 107 octets sans fin de ligne
        b"PROXY",  # coupé net, rien ne suit
        b"PROXYTCP4 198.51.100.11 127.0.0.1 1 2\r\n",
        V1_SIGNATURE_V2[:6] + b"zzzzzz",  # début de signature v2 faux
        V1_SIGNATURE_V2 + b"\x11\x11\x00\x0c" + b"\x00" * 12,  # version 1 dans la forme binaire
        v2(1, b"\x00" * 4),  # TCP4 trop court
        v2_tcp4("0.0.0.0"),
        v2(1, b"\x00" * 12 + b"\x00" * 600),  # longueur déraisonnable
    ],
)
def test_un_en_tete_proxy_mal_forme_est_refuse(octets):
    prise = _paire(octets)
    prise.settimeout(0.3)  # `PROXY` coupé net : on attend la suite jusqu'au délai de la prise, puis on refuse
    with pytest.raises(adresses.ProxyRefuse):
        adresses.lire_entete_proxy(prise, "127.0.0.1", actif=True)


def test_un_en_tete_proxy_est_refuse_si_le_reglage_est_eteint():
    prise = _paire(b"PROXY TCP4 198.51.100.11 127.0.0.1 1 2\r\n")
    with pytest.raises(adresses.ProxyRefuse):
        adresses.lire_entete_proxy(prise, "127.0.0.1", actif=False)


@pytest.mark.parametrize("pair", ["198.51.100.99", "10.0.0.5", "::2", "pas-une-adresse"])
def test_un_en_tete_proxy_d_un_pair_qui_n_est_pas_local_est_refuse(pair):
    prise = _paire(b"PROXY TCP4 198.51.100.11 127.0.0.1 1 2\r\n")
    with pytest.raises(adresses.ProxyRefuse):
        adresses.lire_entete_proxy(prise, pair, actif=True)


@pytest.mark.parametrize("pair", ["127.0.0.1", "127.8.9.10", "::1", "::ffff:127.0.0.1"])
def test_le_pair_local_est_reconnu(pair):
    assert adresses.est_local(pair)


@pytest.mark.parametrize("pair", ["198.51.100.1", "0.0.0.0", "10.0.0.1", "", "abc"])
def test_le_pair_non_local_est_reconnu(pair):
    assert not adresses.est_local(pair)


def test_une_poignee_de_main_tls_n_est_pas_consommee_et_donne_le_pair():
    clienthello = b"\x16\x03\x01\x00\x05hello"
    prise = _paire(clienthello)
    assert adresses.lire_entete_proxy(prise, "127.0.0.1", actif=True) is None
    assert prise.recv(100) == clienthello  # rien n'a été lu en trop


def test_l_en_tete_proxy_est_lu_exactement_sans_toucher_au_client_hello_qui_suit():
    clienthello = b"\x16\x03\x01\x00\x05hello"
    for en_tete in (b"PROXY TCP4 198.51.100.11 127.0.0.1 1 2\r\n", v2_tcp4("198.51.100.11")):
        prise = _paire(en_tete + clienthello)  # tout dans le même segment TCP
        assert adresses.lire_entete_proxy(prise, "127.0.0.1", actif=True) == "198.51.100.11"
        assert prise.recv(100) == clienthello


def test_un_pair_muet_ne_bloque_pas_au_dela_du_delai_de_la_prise():
    serveur, _client = socket.socketpair()
    serveur.settimeout(0.2)
    with pytest.raises((adresses.ProxyRefuse, TimeoutError)):
        adresses.lire_entete_proxy(serveur, "127.0.0.1", actif=True)


@pytest.mark.parametrize("texte", ["198.51.100.11", "2001:db8::7", "::ffff:198.51.100.11"])
def test_normaliser_donne_une_seule_forme(texte):
    assert adresses.normaliser(texte) in {"198.51.100.11", "2001:db8::7"}


@pytest.mark.parametrize("texte", ["", "x", "1.2.3", "0.0.0.0", "::", "224.0.0.1", "ff02::1", "1.2.3.4 ", "1.2.3.4\n"])
def test_normaliser_refuse_ce_qui_n_est_pas_une_adresse_de_visiteur(texte):
    assert adresses.normaliser(texte) is None


def test_la_signature_de_l_adresse_est_liee_a_l_observation_au_jeton_et_a_l_adresse():
    secret = b"secret-de-test"
    s = adresses.signer(secret, "7", JETON, A1)
    assert adresses.verifier(secret, s, "7", JETON, A1)
    assert not adresses.verifier(secret, s, "8", JETON, A1)
    assert not adresses.verifier(secret, s, "7", "f" * 32, A1)
    assert not adresses.verifier(secret, s, "7", JETON, A2)
    assert not adresses.verifier(b"autre", s, "7", JETON, A1)


# --- Le frontal --------------------------------------------------------------------------------------------


class _Amont(http.server.BaseHTTPRequestHandler):
    recus: list[dict[str, str]] = []

    def do_GET(self):
        type(self).recus.append({k.lower(): v for k, v in self.headers.items()})
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *args):
        pass


@pytest.fixture
def amont():
    _Amont.recus = []
    serveur = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Amont)
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    yield serveur
    serveur.shutdown()


def _relayer(reglages, amont, adresse: str, entetes: list[tuple[str, str]]):
    serveur = SimpleNamespace(reglages=reglages, secret=b"secret-de-test", port_aval=amont.server_address[1])
    hello = tls.ClientHello(version_legacy=0x0303, ciphers=[0x1301], extensions=[0x2B], sni="localhost")
    cx = frontal._Connexion.__new__(frontal._Connexion)
    cx.serveur, cx.empreinte, cx.adresse, cx.cx = serveur, tls.empreinte(hello), adresse, None
    return cx._relayer("GET", "/lab/x", entetes, b"", JETON, "endurance", 7, "/lab/x")


def test_le_frontal_pose_l_adresse_signee_et_ecarte_les_adresses_forgees(reglages, amont):
    forges = [
        ("Host", "localhost"),
        ("X-Forwarded-For", "192.0.2.66"),
        ("X-Real-IP", "192.0.2.67"),
        ("Forwarded", "for=192.0.2.68"),
        ("X-ShadowLab-Adresse", "192.0.2.69"),
        ("X-ShadowLab-Adresse-Sceau", "forge"),
    ]
    statut, _, _ = _relayer(reglages, amont, A1, forges)
    assert statut == 200
    recu = _Amont.recus[0]
    assert recu["x-shadowlab-adresse"] == A1
    assert adresses.verifier(b"secret-de-test", recu["x-shadowlab-adresse-sceau"], "7", JETON, A1)
    assert recu["x-forwarded-for"] == A1
    assert "x-real-ip" not in recu and "forwarded" not in recu
    assert "192.0.2.6" not in " ".join(recu.values())


def test_sans_en_tete_proxy_l_adresse_est_celle_du_pair(reglages, amont):
    statut, _, _ = _relayer(reglages, amont, "127.0.0.1", [("Host", "localhost"), ("X-Forwarded-For", "192.0.2.66")])
    assert statut == 200
    assert _Amont.recus[0]["x-shadowlab-adresse"] == "127.0.0.1"
    assert _Amont.recus[0]["x-forwarded-for"] == "127.0.0.1"


def test_le_reglage_est_eteint_par_defaut(reglages):
    assert reglages.proxy_protocole is False


def test_le_reglage_se_lit_dans_l_environnement(reglages, monkeypatch):
    monkeypatch.setenv("SHADOWLAB_ARENA_PROXY_PROTOCOLE", "1")
    assert config.charger().proxy_protocole is True
    monkeypatch.setenv("SHADOWLAB_ARENA_PROXY_PROTOCOLE", "non")
    assert config.charger().proxy_protocole is False


def _requete_tls(port: int, avant: bytes, chemin: str = "/lab/x") -> int | None:
    """Ouvre une connexion, envoie `avant` (en clair), fait la poignée de main TLS, demande `chemin`. None : refusé."""
    contexte = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    contexte.check_hostname = False
    contexte.verify_mode = ssl.CERT_NONE
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=5) as brut:
            if avant:
                brut.sendall(avant)
            with contexte.wrap_socket(brut, server_hostname="localhost") as flux:
                flux.sendall(
                    f"GET {chemin}?sl={JETON} HTTP/1.1\r\nHost: localhost\r\nX-Forwarded-For: 192.0.2.66\r\n"
                    "Connection: close\r\n\r\n".encode()
                )
                debut = flux.recv(64)
                return int(debut.split()[1])
    except (OSError, ssl.SSLError, ValueError, IndexError):
        return None


@pytest.fixture
def frontal_vivant(reglages, amont):
    lance: list[frontal.Frontal] = []

    def demarrer(actif: bool) -> int:
        regle = replace(reglages, proxy_protocole=actif)
        f = frontal.Frontal(regle, port_aval=amont.server_address[1])
        f.demarrer()
        lance.append(f)
        return regle.port_arena

    yield demarrer
    for f in lance:
        f.arreter()


def test_frontal_de_bout_en_bout_l_adresse_du_proxy_descend_signee(frontal_vivant):
    port = frontal_vivant(True)
    assert _requete_tls(port, b"PROXY TCP4 198.51.100.11 127.0.0.1 40000 8749\r\n") == 200
    assert _requete_tls(port, v2_tcp4("198.51.100.22")) == 200
    assert _requete_tls(port, b"") == 200  # sans en-tête : l'adresse du pair
    recus = [r["x-shadowlab-adresse"] for r in _Amont.recus]
    assert recus == ["198.51.100.11", "198.51.100.22", "127.0.0.1"]
    assert all(r["x-forwarded-for"] == r["x-shadowlab-adresse"] for r in _Amont.recus)


def test_frontal_de_bout_en_bout_un_en_tete_proxy_refuse_coupe_la_connexion(frontal_vivant):
    port = frontal_vivant(True)
    assert _requete_tls(port, b"PROXY TCP4 999.1.1.1 127.0.0.1 1 2\r\n") is None
    assert _requete_tls(port, b"PROXY TCP4 198.51.100.11 127.0.0.1 1\r\n") is None
    assert _Amont.recus == []
    assert _requete_tls(port, b"") == 200  # le frontal tient toujours


def test_frontal_de_bout_en_bout_reglage_eteint_l_en_tete_proxy_est_refuse(frontal_vivant):
    port = frontal_vivant(False)
    assert _requete_tls(port, b"PROXY TCP4 198.51.100.11 127.0.0.1 40000 8749\r\n") is None
    assert _Amont.recus == []
    assert _requete_tls(port, b"") == 200
    assert _Amont.recus[0]["x-shadowlab-adresse"] == "127.0.0.1"


# --- Le sceau de l'adresse, côté site -----------------------------------------------------------------------


class _Requete:
    def __init__(self, entetes: dict[str, str]) -> None:
        self.headers = {k.lower(): v for k, v in entetes.items()}


def _entetes_site(secret: bytes, adresse: str | None, *, sceau_adresse: str | None = None) -> dict[str, str]:
    entetes = {
        "x-shadowlab-sceau": secrets_arena.signer(secret, "obs", "endurance", JETON, "ja4", "liaison"),
        "x-shadowlab-obs": "obs",
        "x-shadowlab-profil": "endurance",
        "x-shadowlab-session": JETON,
        "x-shadowlab-ja4": "ja4",
        "x-shadowlab-liaison": "liaison",
    }
    if adresse is not None:
        entetes["x-shadowlab-adresse"] = adresse
        entetes["x-shadowlab-adresse-sceau"] = sceau_adresse or adresses.signer(secret, "obs", JETON, adresse)
    return entetes


def test_le_site_lit_l_adresse_signee():
    secret = b"secret-de-test"
    sceau = gardien.lire_sceau(_Requete(_entetes_site(secret, A1)), secret)
    assert sceau is not None and sceau.adresse == A1


def test_le_site_ignore_une_adresse_sans_signature_ou_mal_signee():
    secret = b"secret-de-test"
    sans = _entetes_site(secret, None)
    sans["x-shadowlab-adresse"] = A1  # un en-tête posé sans sceau d'adresse
    assert gardien.lire_sceau(_Requete(sans), secret).adresse is None  # type: ignore[union-attr]
    forge = _entetes_site(secret, A1, sceau_adresse="forge")
    assert gardien.lire_sceau(_Requete(forge), secret).adresse is None  # type: ignore[union-attr]
    changee = _entetes_site(secret, A1)
    changee["x-shadowlab-adresse"] = A2
    assert gardien.lire_sceau(_Requete(changee), secret).adresse is None  # type: ignore[union-attr]
    assert gardien.lire_sceau(_Requete(_entetes_site(secret, None)), secret).adresse is None  # type: ignore[union-attr]


def test_le_sceau_d_avant_reste_valable_sans_adresse():
    secret = b"secret-de-test"
    assert gardien.lire_sceau(_Requete(_entetes_site(secret, None)), secret) is not None


# --- Migration 13 ------------------------------------------------------------------------------------------


def test_migration_13_ajoute_l_adresse_a_la_visite_et_au_bannissement(tmp_path):
    assert len(db.MIGRATIONS) >= 13
    assert "ALTER TABLE visites ADD COLUMN adresse" in db.MIGRATIONS[12]
    assert "ALTER TABLE bannissements ADD COLUMN adresse" in db.MIGRATIONS[12]
    assert "CREATE TABLE" not in db.MIGRATIONS[12]  # que des colonnes vides et un index : sûre sur la base publique
    cx = db.ouvrir(tmp_path / "neuve.sqlite3")
    assert cx.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION >= 13
    for table in ("visites", "bannissements"):
        assert "adresse" in {r["name"] for r in cx.execute(f"PRAGMA table_info({table})")}
    assert "bannissements_adresse" in {r["name"] for r in cx.execute("SELECT name FROM sqlite_master")}


def test_migration_13_sur_une_base_au_schema_12_garde_les_lignes(tmp_path):
    import sqlite3

    chemin = tmp_path / "douze.sqlite3"
    brut = sqlite3.connect(chemin, isolation_level=None)
    for script in db.MIGRATIONS[:12]:
        for instruction in (s.strip() for s in script.split(";")):
            if instruction:
                brut.execute(instruction)
    brut.execute("PRAGMA user_version=12")
    brut.execute("INSERT INTO mondes (nom, cree_le) VALUES ('m', '2026-11-19T00:00:00.000+00:00')")
    brut.execute("INSERT INTO visites (monde_id, visiteur, session_token, neuve, vue_le) VALUES (1, 'v', 's', 1, 'x')")
    brut.close()
    cx = db.ouvrir(chemin)
    ligne = cx.execute("SELECT visiteur, adresse FROM visites").fetchone()
    assert (ligne["visiteur"], ligne["adresse"]) == ("v", None)


# --- L'adresse notée sur la visite --------------------------------------------------------------------------


def test_deux_adresses_distinctes_sont_notees_en_base(client, reglages, cx, nouvelle_session, sans_suspicion):
    NavigateurIp(client, reglages, A1).aller(nouvelle_session())
    NavigateurIp(client, reglages, A2).aller(nouvelle_session())
    assert _adresses_de_visites(cx) == [A1, A2]


def test_sans_adresse_signee_la_visite_n_a_pas_d_adresse(client, reglages, cx, nouvelle_session, sans_suspicion):
    NavigateurIp(client, reglages, None).aller(nouvelle_session())
    assert _adresses_de_visites(cx) == [None]


def test_une_adresse_forgee_par_le_client_n_est_jamais_notee(client, reglages, cx, nouvelle_session, sans_suspicion):
    forges = {
        "x-forwarded-for": "192.0.2.66",
        "x-real-ip": "192.0.2.67",
        "forwarded": "for=192.0.2.68",
        "x-shadowlab-adresse": "192.0.2.69",  # sans le sceau d'adresse qui va avec
    }
    nav = NavigateurIp(client, reglages, None)
    nav.aller(nouvelle_session(), extra=forges)
    assert _adresses_de_visites(cx) == [None]
    # avec une vraie adresse signée, les en-têtes forgés ne la remplacent pas
    NavigateurIp(client, reglages, A1).aller(nouvelle_session(), extra={"x-forwarded-for": "192.0.2.66"})
    assert _adresses_de_visites(cx) == [None, A1]


def test_l_adresse_est_notee_a_la_premiere_requete_de_la_session(client, reglages, cx, nouvelle_session, sans_suspicion):
    jeton = nouvelle_session()
    nav = NavigateurIp(client, reglages, A1)
    nav.aller(jeton)
    nav.adresse = A2
    nav.aller(jeton)
    assert _adresses_de_visites(cx) == [A1]


# --- Le bannissement par adresse ----------------------------------------------------------------------------


def test_bannir_ecrit_une_ligne_qui_ne_vise_que_l_adresse(cx):
    assert bannissements.bannir(cx, MONDE, adresse=A1, motif="manuel", maintenant=MAINTENANT)
    (ban,) = _bans(cx)
    assert (ban["adresse"], ban["visiteur"], ban["empreinte"], ban["compte"], ban["motif"]) == (A1, None, None, None, "manuel")
    assert not bannissements.bannir(cx, MONDE, adresse=A1, motif="manuel", maintenant=MAINTENANT)  # pas de doublon
    assert bannissements.bannir(cx, MONDE, adresse=A2, motif="manuel", maintenant=MAINTENANT)
    assert bannissements.bannir(cx, AUTRE_MONDE, adresse=A1, motif="manuel", maintenant=MAINTENANT)
    assert len(_bans(cx)) == 3


def test_bannir_refuse_une_adresse_illisible_ou_rien(cx):
    with pytest.raises(ValueError):
        bannissements.bannir(cx, MONDE, motif="manuel")
    with pytest.raises(ValueError):
        bannissements.bannir(cx, MONDE, adresse="pas-une-adresse", motif="manuel")
    assert not _bans(cx)


def test_une_adresse_bannie_refuse_un_navigateur_neuf_des_sa_premiere_requete(
    client, reglages, cx, nouvelle_session, sans_suspicion
):
    bannissements.bannir(cx, MONDE, adresse=A1, motif="manuel")
    refus = NavigateurIp(client, reglages, A1).aller(nouvelle_session())
    assert refus.status_code == 403 and refus.json()["bloque_par"] == "bannissement"
    assert refus.headers["x-arena-refus"] == "bannissement"  # la sentinelle du moteur le lit comme un bannissement
    jeton = nouvelle_session()
    html = NavigateurIp(client, reglages, A1).aller(jeton, extra={"accept": "text/html"})
    assert html.status_code == 403 and html.headers["x-arena-refus"] == "bannissement"
    # la page de refus est celle de D-92 : octet pour octet
    from shadowlab.site import pages

    assert html.text == pages.page_blocage()
    decision = [d for d in db.decisions_session(cx, jeton) if d["couche"] == "bannissement"]
    assert decision and decision[0]["decision"] == "bloque"
    assert decision[0]["motifs"][0]["par"] == "adresse" and decision[0]["motifs"][0]["motif"] == "manuel"


def test_une_autre_adresse_n_est_pas_refusee(client, reglages, cx, nouvelle_session, sans_suspicion):
    bannissements.bannir(cx, MONDE, adresse=A1, motif="manuel")
    reponse = NavigateurIp(client, reglages, A2).aller(nouvelle_session())
    assert reponse.status_code == 403 and reponse.json()["bloque_par"] == "defi-js"  # la porte, pas le bannissement


def test_un_navigateur_sans_adresse_signee_n_est_pas_refuse_par_adresse(
    client, reglages, cx, nouvelle_session, sans_suspicion
):
    bannissements.bannir(cx, MONDE, adresse=A1, motif="manuel")
    reponse = NavigateurIp(client, reglages, None).aller(nouvelle_session())
    assert reponse.json()["bloque_par"] == "defi-js"
    # et un en-tête forgé n'y change rien
    forge = NavigateurIp(client, reglages, None).aller(nouvelle_session(), extra={"x-forwarded-for": A1})
    assert forge.json()["bloque_par"] == "defi-js"


def test_le_bannissement_par_adresse_est_propre_au_monde(client, reglages, cx, nouvelle_session, sans_suspicion):
    bannissements.bannir(cx, AUTRE_MONDE, adresse=A1, motif="manuel")
    reponse = NavigateurIp(client, reglages, A1).aller(nouvelle_session())
    assert reponse.json()["bloque_par"] == "defi-js"


def test_un_bannissement_par_adresse_expire(client, reglages, cx, nouvelle_session, sans_suspicion):
    passe = datetime.now(UTC) - timedelta(hours=2)
    bannissements.bannir(cx, MONDE, adresse=A1, motif="manuel", maintenant=passe, expire_le=passe + timedelta(hours=1))
    assert NavigateurIp(client, reglages, A1).aller(nouvelle_session()).json()["bloque_par"] == "defi-js"


def test_un_bannissement_manuel_par_adresse_refuse_aussi_un_visiteur_deja_connu(
    client, reglages, cx, nouvelle_session, sans_suspicion
):
    nav = NavigateurIp(client, reglages, A1)
    nav.franchir_la_porte(nouvelle_session())
    bannissements.bannir(cx, MONDE, adresse=A1, motif="manuel")
    refus = nav.aller(nouvelle_session())
    assert refus.status_code == 403 and refus.json()["bloque_par"] == "bannissement"
    assert len(_bans(cx)) == 1  # aucun bannissement de visiteur n'en découle


def test_un_bannissement_par_adresse_ne_bannit_ni_le_visiteur_ni_l_empreinte(
    client, reglages, cx, nouvelle_session, sans_suspicion
):
    bannissements.bannir(cx, MONDE, adresse=A1, motif="manuel")
    NavigateurIp(client, reglages, A1).aller(nouvelle_session())
    assert [(b["visiteur"], b["empreinte"]) for b in _bans(cx)] == [(None, None)]
    # le même navigateur, arrivé d'une autre adresse, n'est pas banni
    nav = NavigateurIp(client, reglages, A2)
    assert nav.aller(nouvelle_session()).json()["bloque_par"] == "defi-js"


@pytest.mark.parametrize("niveau", ["01", "02", "03", "04", "05", "06", "07"])
def test_aux_niveaux_01_a_07_l_adresse_n_est_jamais_lue_et_aucune_decision_ne_change(
    client, reglages, cx, experience, monkeypatch, niveau
):
    """Même requête, avec et sans adresse signée, avec une adresse bannie dans le monde : mêmes décisions."""
    monkeypatch.setattr(gardien, "suspicion", lambda *a, **k: [])

    def interdit(*a, **k):
        raise AssertionError("le bannissement est lu alors que le niveau ne l'active pas")

    monkeypatch.setattr(bannissements.Surveillance, "juger", interdit)
    monde = f"m-{niveau}"
    resultats = []
    for adresse in (None, A1):
        jeton = nouveau_passage(reglages, nouvelle_experience(reglages, niveau), repetition=1, monde=monde)
        nav = NavigateurIp(client, reglages, adresse, profil=niveau)
        premiere = nav.aller(jeton)
        resultats.append((premiere.status_code, premiere.headers.get("x-arena-refus"), sorted(premiere.json().items())
                          if premiere.status_code == 403 else None))
        decisions = [(d["couche"], d["decision"]) for d in db.decisions_session(cx, jeton)]
        resultats.append(decisions)
    bannissements.bannir(cx, monde, adresse=A1, motif="manuel")
    jeton = nouveau_passage(reglages, nouvelle_experience(reglages, niveau), repetition=1, monde=monde)
    avec_ban = NavigateurIp(client, reglages, A1, profil=niveau).aller(jeton)
    assert (avec_ban.status_code, avec_ban.headers.get("x-arena-refus")) == (resultats[0][0], None)
    assert resultats[0] == resultats[2]
    assert resultats[1] == resultats[3]


def test_seul_endurance_active_le_bannissement():
    actifs = [code for code, p in profils.charger() if p.bannissement.actif]
    assert actifs == ["endurance"]


# --- La règle automatique : des visiteurs bannis depuis la même adresse ----------------------------------------


def _bannir_visiteur_de(cx, monde: str, visiteur: str, adresse: str | None, maintenant: datetime = MAINTENANT):
    _visite_ip(cx, monde, visiteur, f"{abs(hash((monde, visiteur))):032x}"[:32], adresse, maintenant)
    return bannissements.bannir(cx, monde, visiteur=visiteur, motif="detecte:x", maintenant=maintenant)


def _bans_adresse(cx):
    return [b for b in _bans(cx) if b["adresse"] is not None]


def test_deux_visiteurs_bannis_depuis_la_meme_adresse_ne_bannissent_pas_l_adresse(cx):
    for v in ("v1", "v2"):
        _bannir_visiteur_de(cx, MONDE, v, A1)
    assert not _bans_adresse(cx)


def test_trois_visiteurs_distincts_bannis_depuis_la_meme_adresse_en_24_h_bannissent_l_adresse(cx):
    for v in ("v1", "v2", "v3"):
        _bannir_visiteur_de(cx, MONDE, v, A1)
    (ban,) = _bans_adresse(cx)
    assert (ban["monde"], ban["adresse"], ban["visiteur"], ban["empreinte"]) == (MONDE, A1, None, None)
    assert ban["motif"].startswith("visiteurs_bannis")
    assert ban["expire_le"] == _stamp(MAINTENANT + JOUR)  # temporaire : 24 h


def test_la_regle_ne_compte_que_des_visiteurs_distincts(cx):
    _bannir_visiteur_de(cx, MONDE, "v1", A1)
    _visite_ip(cx, MONDE, "v1", "e" * 32, A1)  # une seconde session du même visiteur
    bannissements.bannir(cx, MONDE, visiteur="v1", empreinte="E1", motif="detecte:y", maintenant=MAINTENANT)
    _bannir_visiteur_de(cx, MONDE, "v2", A1)
    assert not _bans_adresse(cx)


def test_la_regle_ne_compte_pas_les_bannissements_de_plus_de_24_h(cx):
    ancien = MAINTENANT - JOUR - timedelta(minutes=1)
    for v in ("v1", "v2"):
        _bannir_visiteur_de(cx, MONDE, v, A1, ancien)
    _bannir_visiteur_de(cx, MONDE, "v3", A1)
    assert not _bans_adresse(cx)


def test_la_regle_ne_melange_pas_les_adresses_ni_les_mondes(cx):
    for v, a in (("v1", A1), ("v2", A2), ("v3", A3)):
        _bannir_visiteur_de(cx, MONDE, v, a)
    for v in ("v4", "v5"):
        _bannir_visiteur_de(cx, MONDE, v, A1)  # A1 : 3 visiteurs (v1, v4, v5) bannis
    assert [b["adresse"] for b in _bans_adresse(cx)] == [A1]
    for v in ("w1", "w2"):
        _bannir_visiteur_de(cx, AUTRE_MONDE, v, A4)
    _bannir_visiteur_de(cx, MONDE, "w3", A4)  # un visiteur dans un autre monde ne compte pas
    assert [b["adresse"] for b in _bans_adresse(cx)] == [A1]


@pytest.mark.parametrize("adresse", ["127.0.0.1", "::1", None])
def test_une_adresse_non_declaree_ne_declenche_jamais_la_regle(cx, adresse):
    """127.0.0.1 est l'adresse du pair quand rien n'est simulé : tous les clients d'un poste la portent."""
    for v in ("v1", "v2", "v3", "v4"):
        _bannir_visiteur_de(cx, MONDE, v, adresse)
    assert not _bans_adresse(cx)


@pytest.mark.parametrize("monde", [visiteurs.MONDE_MANUEL, visiteurs.MONDE_HORS_PASSAGE])
def test_aucun_bannissement_automatique_d_adresse_dans_les_mondes_partages(cx, monde):
    for v in ("v1", "v2", "v3"):
        _bannir_visiteur_de(cx, monde, v, A1)
    assert not _bans_adresse(cx)


def test_la_regle_ne_s_ecrit_qu_une_fois(cx):
    for v in ("v1", "v2", "v3", "v4", "v5"):
        _bannir_visiteur_de(cx, MONDE, v, A1)
    assert len(_bans_adresse(cx)) == 1


def test_un_visiteur_banni_apres_avoir_change_d_adresse_compte_pour_chacune(cx):
    _bannir_visiteur_de(cx, MONDE, "v1", A1)
    _visite_ip(cx, MONDE, "v1", "d" * 32, A2)
    for v in ("v2", "v3"):
        _bannir_visiteur_de(cx, MONDE, v, A1)
    assert [b["adresse"] for b in _bans_adresse(cx)] == [A1]


def test_une_adresse_bannie_automatiquement_ne_refuse_que_les_visiteurs_neufs(
    client, reglages, cx, nouvelle_session, sans_suspicion
):
    """Un humain qui revient (cookie de visiteur valable) derrière une adresse partagée n'est pas refusé parce que trois
    autres visiteurs de cette adresse ont été bannis ; un navigateur neuf l'est."""
    humain = NavigateurIp(client, reglages, A1)
    humain.franchir_la_porte(nouvelle_session())
    for v in ("v1", "v2", "v3"):
        _bannir_visiteur_de(cx, MONDE, v, A1)
    assert [b["adresse"] for b in _bans_adresse(cx)] == [A1]
    assert humain.aller(nouvelle_session()).status_code == 200  # il revient : il passe
    neuf = NavigateurIp(client, reglages, A1).aller(nouvelle_session())
    assert neuf.status_code == 403 and neuf.json()["bloque_par"] == "bannissement"
    assert neuf.headers["x-arena-refus"] == "bannissement"


def test_un_humain_n_est_pas_banni_parce_qu_un_autre_visiteur_de_son_adresse_l_a_ete_une_fois(
    client, reglages, cx, nouvelle_session, sans_suspicion
):
    _bannir_visiteur_de(cx, MONDE, "voisin", A1)
    humain = NavigateurIp(client, reglages, A1)
    humain.franchir_la_porte(nouvelle_session())
    assert humain.aller(nouvelle_session()).status_code == 200
    assert not _bans_adresse(cx)


# --- La commande `shadowlab arena bannir --ip` ---------------------------------------------------------------


def _monde_existant(client, reglages, nouvelle_session):
    NavigateurIp(client, reglages, A1).aller(nouvelle_session())


def test_arena_bannir_ip_ecrit_la_ligne_et_l_adresse_recoit_ensuite_un_403(
    client, reglages, cx, nouvelle_session, sans_suspicion, capsys
):
    _monde_existant(client, reglages, nouvelle_session)
    assert cli.main(["arena", "bannir", "--ip", A1, "--monde", MONDE]) == 0
    (ban,) = _bans(cx)
    assert (ban["monde"], ban["adresse"], ban["visiteur"], ban["compte"], ban["motif"], ban["expire_le"]) == (
        MONDE, A1, None, None, "manuel", None,
    )  # fmt: skip
    assert A1 in capsys.readouterr().out
    assert NavigateurIp(client, reglages, A1).aller(nouvelle_session()).status_code == 403
    assert cli.main(["arena", "bannir", "--ip", A1, "--monde", MONDE]) == 0  # déjà banni : pas de doublon
    assert len(_bans(cx)) == 1


def test_arena_bannir_ip_normalise_l_adresse(client, reglages, cx, nouvelle_session, sans_suspicion):
    _monde_existant(client, reglages, nouvelle_session)
    assert cli.main(["arena", "bannir", "--ip", "::ffff:198.51.100.11", "--monde", MONDE]) == 0
    assert [b["adresse"] for b in _bans(cx)] == [A1]


@pytest.mark.parametrize(
    "arguments",
    [
        ["--ip", A1, "--visiteur", "abc"],
        ["--ip", A1, "--compte", "demo"],
        ["--ip", A1, "--visiteur", "abc", "--compte", "demo"],
    ],
)
def test_arena_bannir_ip_est_exclusif_avec_visiteur_et_compte(reglages, arguments):
    with pytest.raises(SystemExit) as sortie:
        cli.main(["arena", "bannir", *arguments, "--monde", MONDE])
    assert sortie.value.code == 2


def test_arena_bannir_ip_exige_le_monde(reglages):
    with pytest.raises(SystemExit) as sortie:
        cli.main(["arena", "bannir", "--ip", A1])
    assert sortie.value.code == 2


def test_arena_bannir_ip_refuse_un_monde_inconnu_ou_une_adresse_illisible(
    client, reglages, cx, nouvelle_session, sans_suspicion, capsys
):
    _monde_existant(client, reglages, nouvelle_session)
    assert cli.main(["arena", "bannir", "--ip", A1, "--monde", "monde-inexistant"]) == 2
    assert cli.main(["arena", "bannir", "--ip", "pas-une-adresse", "--monde", MONDE]) == 2
    assert cli.main(["arena", "bannir", "--ip", "0.0.0.0", "--monde", MONDE]) == 2
    assert not _bans(cx)
    assert "monde-inexistant" not in {r["nom"] for r in cx.execute("SELECT nom FROM mondes")}
    assert "monde-inexistant" in capsys.readouterr().err


def test_arena_bannir_ip_ne_demarre_pas_la_pile(client, reglages, nouvelle_session, sans_suspicion, monkeypatch):
    from shadowlab.arena import pile

    monkeypatch.setattr(pile, "demarrer", lambda *a, **k: pytest.fail("la pile ne doit pas être touchée"))
    _monde_existant(client, reglages, nouvelle_session)
    assert cli.main(["arena", "bannir", "--ip", A1, "--monde", MONDE]) == 0


def test_le_bannissement_d_un_visiteur_ou_d_un_compte_ne_change_pas(
    client, reglages, cx, nouvelle_session, sans_suspicion
):
    nav = NavigateurIp(client, reglages, A1)
    visiteur = nav.franchir_la_porte(nouvelle_session())
    assert cli.main(["arena", "bannir", "--visiteur", visiteur, "--monde", MONDE]) == 0
    (ban,) = _bans(cx)
    assert (ban["visiteur"], ban["adresse"]) == (visiteur, None)
