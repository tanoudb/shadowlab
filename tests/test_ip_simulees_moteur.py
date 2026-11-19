"""Palier 4, étape 4.1 (D-105), côté moteur : l'adresse simulée d'une identité, envoyée à notre Arena locale seulement.

Le relais de D-99 (`RelaisProxy`) a un nouveau schéma d'amont, `arena://127.0.0.1:<port>` : pas de proxy réel, la
connexion va droit au frontal local de l'Arena, et le premier octet du tunnel est l'en-tête PROXY v1 qui porte l'adresse
déclarée par l'identité (`adresse_simulee`). Le relais reste le verrou réseau : un tunnel vers un autre hôte, un autre
port, ou une requête simple est refusé (403) sans qu'aucune connexion ne soit ouverte, donc sans aucun octet PROXY
envoyé ailleurs. Un amont HTTP ou SOCKS5 ne reçoit jamais d'en-tête PROXY et n'accepte pas d'adresse simulée.
"""

from __future__ import annotations

import importlib
import json
import socket
import threading

import pytest
from outils_proxy import AmontEnregistreur, attendre, ouvrir_tunnel, statut_de
from test_espacement import campagne

from shadowlab import campaigns
from shadowlab.config import RACINE
from shadowlab.engines import registre
from shadowlab.engines.noezia import identite as ident

A1, A2 = "198.51.100.11", "198.51.100.22"
FICHIER_ESSAI = RACINE / "configs" / "experiments" / "ip-simulees-essai.yaml"
NATIVE = {"headless": False, "channel": "chrome", "identite_native": True}


@pytest.fixture(scope="module")
def px():
    return importlib.import_module("shadowlab.engines.noezia.proxy_identite")


@pytest.fixture
def racine(tmp_path, monkeypatch):
    dossier = tmp_path / "identites"
    monkeypatch.setenv("SHADOWLAB_IDENTITES", str(dossier))
    return dossier


class FauxFrontal:
    """Une « Arena » qui note tout ce qu'elle reçoit, connexion par connexion (des octets et un compteur)."""

    def __init__(self) -> None:
        self.ecoute = socket.socket()
        self.ecoute.bind(("127.0.0.1", 0))
        self.ecoute.listen(8)
        self.ecoute.settimeout(0.2)
        self.port = self.ecoute.getsockname()[1]
        self.connexions: list[bytes] = []
        self._arret = threading.Event()
        self._fil = threading.Thread(target=self._boucle, daemon=True)
        self._fil.start()

    def _boucle(self) -> None:
        while not self._arret.is_set():
            try:
                client, _ = self.ecoute.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            index = len(self.connexions)
            self.connexions.append(b"")
            threading.Thread(target=self._lire, args=(client, index), daemon=True).start()

    def _lire(self, client: socket.socket, index: int) -> None:
        client.settimeout(0.2)
        while not self._arret.is_set():
            try:
                donnees = client.recv(65536)
            except TimeoutError:
                continue
            except OSError:
                return
            if not donnees:
                return
            self.connexions[index] += donnees

    def __enter__(self) -> FauxFrontal:
        return self

    def __exit__(self, *_exc) -> None:
        self._arret.set()
        self.ecoute.close()
        self._fil.join(timeout=2)


@pytest.fixture
def faux_frontal():
    with FauxFrontal() as f:
        yield f


# ── analyser ──────────────────────────────────────────────────────────────


def test_analyser_accepte_un_amont_arena_avec_son_adresse_simulee(px):
    p = px.analyser("arena://127.0.0.1:8749", adresse_simulee=A1)
    assert (p.schema, p.hote, p.port, p.adresse_simulee) == ("arena", "127.0.0.1", 8749, A1)
    assert p.masque() == "arena://127.0.0.1:8749"
    assert "arena" in px.SCHEMAS


def test_analyser_normalise_l_adresse_simulee(px):
    assert px.analyser("arena://127.0.0.1:8749", adresse_simulee="::ffff:198.51.100.11").adresse_simulee == A1


@pytest.mark.parametrize(
    ("serveur", "adresse"),
    [
        ("arena://127.0.0.1:8749", None),  # un amont arena sans adresse n'a pas de raison d'être
        ("arena://localhost:8749", A1),  # l'hôte est l'adresse littérale 127.0.0.1, pas un nom
        ("arena://192.0.2.1:8749", A1),  # jamais un autre hôte
        ("arena://[::1]:8749", A1),
        ("arena://127.0.0.1", A1),  # port absent
        ("arena://127.0.0.1:0", A1),
        ("arena://127.0.0.1:8749", "pas-une-adresse"),
        ("arena://127.0.0.1:8749", "0.0.0.0"),
        ("arena://127.0.0.1:8749", "224.0.0.1"),
        ("arena://127.0.0.1:8749", ""),
        ("http://127.0.0.1:3128", A1),  # l'adresse simulée ne part jamais vers un proxy réel
        ("socks5://127.0.0.1:1080", A1),
    ],
)
def test_analyser_refuse_les_amonts_et_adresses_hors_regle(px, serveur, adresse):
    with pytest.raises(px.ProxyInvalide):
        px.analyser(serveur, adresse_simulee=adresse)


def test_analyser_arena_refuse_des_identifiants(px):
    with pytest.raises(px.ProxyInvalide):
        px.analyser("arena://127.0.0.1:8749", "u", "m", adresse_simulee=A1)


def test_sans_adresse_simulee_rien_ne_change_pour_http_et_socks5(px):
    assert px.analyser("http://127.0.0.1:3128").adresse_simulee is None
    assert px.analyser("socks5://127.0.0.1:1080", "u", "m").adresse_simulee is None


# ── proxy.json ────────────────────────────────────────────────────────────


def test_declarer_et_lire_une_adresse_simulee(racine, px):
    chemin = ident.declarer_proxy("ip-a", "arena://127.0.0.1:8749", adresse_simulee=A1)
    assert oct(chemin.stat().st_mode & 0o777) == "0o600"
    assert json.loads(chemin.read_text())["adresse_simulee"] == A1
    lu = ident.lire_proxy("ip-a")
    assert (lu.schema, lu.adresse_simulee) == ("arena", A1)


def test_declarer_n_ecrit_rien_si_l_adresse_est_refusee(racine, px):
    with pytest.raises(px.ProxyInvalide):
        ident.declarer_proxy("ip-b", "arena://127.0.0.1:8749", adresse_simulee="x")
    with pytest.raises(px.ProxyInvalide):
        ident.declarer_proxy("ip-b", "http://127.0.0.1:3128", adresse_simulee=A1)
    assert not (racine / "ip-b" / ident.FICHIER_PROXY).exists()


def test_un_proxy_http_declare_comme_avant_ne_porte_pas_d_adresse(racine, px):
    chemin = ident.declarer_proxy("ip-c", "http://127.0.0.1:3128", "u", "m")
    assert "adresse_simulee" not in json.loads(chemin.read_text())
    assert ident.lire_proxy("ip-c").adresse_simulee is None


# ── le relais ─────────────────────────────────────────────────────────────


def relais_arena(px, port: int, adresse: str = A1):
    return px.RelaisProxy(px.analyser(f"arena://127.0.0.1:{port}", adresse_simulee=adresse), ("*",), ())


def _port(relais) -> int:
    return int(relais.adresse.rsplit(":", 1)[1])


@pytest.mark.parametrize("hote", ["127.0.0.1", "localhost", "LOCALHOST"])
def test_le_tunnel_vers_l_arena_locale_commence_par_l_en_tete_proxy(px, faux_frontal, hote):
    with relais_arena(px, faux_frontal.port) as relais:
        statut, _, sock = ouvrir_tunnel(_port(relais), hote, faux_frontal.port)
        assert statut == 200
        sock.sendall(b"coucou")
        attendu = f"PROXY TCP4 {A1} 127.0.0.1 0 {faux_frontal.port}\r\ncoucou".encode()
        assert attendre(lambda: faux_frontal.connexions and faux_frontal.connexions[0] == attendu)
        sock.close()


def test_une_adresse_ipv6_donne_un_en_tete_tcp6(px, faux_frontal):
    with relais_arena(px, faux_frontal.port, "2001:db8::7") as relais:
        statut, _, sock = ouvrir_tunnel(_port(relais), "127.0.0.1", faux_frontal.port)
        assert statut == 200
        sock.sendall(b"x")
        attendu = f"PROXY TCP6 2001:db8::7 ::1 0 {faux_frontal.port}\r\nx".encode()
        assert attendre(lambda: faux_frontal.connexions and faux_frontal.connexions[0] == attendu)
        sock.close()


def test_chaque_tunnel_porte_l_adresse_de_son_identite(px, faux_frontal):
    with relais_arena(px, faux_frontal.port, A1) as r1, relais_arena(px, faux_frontal.port, A2) as r2:
        for relais in (r1, r2):
            statut, _, sock = ouvrir_tunnel(_port(relais), "127.0.0.1", faux_frontal.port)
            assert statut == 200
            sock.sendall(b".")
        assert attendre(lambda: len(faux_frontal.connexions) == 2 and all(faux_frontal.connexions))
        debuts = sorted(c.split(b"\r\n")[0] for c in faux_frontal.connexions)
        assert debuts[0].startswith(f"PROXY TCP4 {A1} ".encode()) and debuts[1].startswith(f"PROXY TCP4 {A2} ".encode())


@pytest.mark.parametrize(
    ("hote", "decalage_port"),
    [("example.com", 0), ("192.0.2.1", 0), ("127.0.0.2", 0), ("127.0.0.1", 1), ("localhost", -1), ("[::1]", 0)],
)
def test_un_autre_hote_ou_un_autre_port_est_refuse_sans_connexion_ni_octet_proxy(px, faux_frontal, hote, decalage_port):
    with relais_arena(px, faux_frontal.port) as relais:
        statut, _, sock = ouvrir_tunnel(_port(relais), hote.strip("[]"), faux_frontal.port + decalage_port)
        assert statut == 403
        sock.close()
        assert [d.decision for d in relais.demandes] == ["refusee_perimetre"]
    assert faux_frontal.connexions == []  # aucune connexion ouverte : aucun octet PROXY n'est parti nulle part


def test_une_requete_simple_est_refusee_aussi(px, faux_frontal):
    from outils_proxy import echanger

    with relais_arena(px, faux_frontal.port) as relais:
        reponse = echanger(
            _port(relais), f"GET http://127.0.0.1:{faux_frontal.port}/lab/ HTTP/1.1\r\nHost: x\r\n\r\n".encode()
        )
        assert statut_de(reponse) == 403
    assert faux_frontal.connexions == []


def test_un_amont_http_ne_recoit_jamais_d_en_tete_proxy(px):
    with AmontEnregistreur() as amont:
        relais = px.RelaisProxy(px.analyser(f"http://127.0.0.1:{amont.port}"), ("*",), ())
        with relais:
            from outils_proxy import ouvrir_connexion

            with ouvrir_connexion(_port(relais), 1) as sock:
                sock.sendall(b"CONNECT example.com:443 HTTP/1.1\r\nHost: example.com:443\r\n\r\n")
                attendre(lambda: amont.octets_recus)
        recu = amont.octets_recus
    assert recu.startswith(b"CONNECT example.com:443") and b"PROXY " not in recu


def test_le_relais_arena_n_a_aucune_connexion_directe_vers_un_autre_hote(px, faux_frontal, monkeypatch):
    """Le seul `create_connection` du relais vise le frontal local, et il est littéral : 127.0.0.1."""
    cibles: list[tuple] = []
    reel = socket.create_connection

    def espion(adresse, *a, **k):
        cibles.append(adresse)
        return reel(adresse, *a, **k)

    monkeypatch.setattr(socket, "create_connection", espion)
    with relais_arena(px, faux_frontal.port) as relais:
        for hote in ("example.com", "127.0.0.1"):
            statut, _, sock = ouvrir_tunnel(_port(relais), hote, faux_frontal.port)
            sock.close()
    assert ("127.0.0.1", faux_frontal.port) in cibles
    assert all(c[0] == "127.0.0.1" for c in cibles if c[1] == faux_frontal.port)
    assert not any("example.com" in str(c) for c in cibles)


# ── configuration() ───────────────────────────────────────────────────────


def pilote(nom: str):
    return registre()["noezia"](("127.0.0.1",), {**NATIVE, "identite": nom})


def test_configuration_declare_l_adresse_simulee_et_le_masque(racine, px):
    ident.declarer_proxy("ip-a", "arena://127.0.0.1:8749", adresse_simulee=A1)
    conf = pilote("ip-a").configuration()
    assert conf["identite_proxy"] == "arena://127.0.0.1:8749"
    assert conf["identite_adresse_simulee"] == A1
    assert "identite_proxy_arguments" in conf  # WebRTC fermé, comme pour tout proxy d'identité


def test_configuration_sans_adresse_simulee_pas_de_cle(racine, px):
    ident.declarer_proxy("ip-b", "http://127.0.0.1:3128", "u", "m")
    assert "identite_adresse_simulee" not in pilote("ip-b").configuration()
    assert "identite_adresse_simulee" not in pilote("ip-sans-proxy").configuration()


# ── la campagne ───────────────────────────────────────────────────────────

NAT = "options: {headless: false, channel: chrome, identite_native: true, identite: %s}"
ESPACEMENT = "  espacement: {mode: fixe, minutes: 1}\n  concurrency: 2\n"


def bras_adresse(**champs) -> str:
    base = {"name": "noezia", "bannir_avant_visite": 2, "bannir_adresse": "true", "visites": 2, **champs}
    corps = ", ".join(f"{k}: {v}" for k, v in base.items())
    return f"\n    - {{{corps}, {NAT % 'x'}}}\n"


def test_une_campagne_qui_bannit_une_adresse_se_valide(tmp_path, reglages):
    e = campagne(tmp_path, reglages, engines=bras_adresse(identite_apres_bannissement="y"), extra=ESPACEMENT)
    (bras,) = e.engines
    assert bras.bannir_adresse is True and bras.identite_apres_bannissement == "y"


@pytest.mark.parametrize(
    ("bras", "message"),
    [
        (bras_adresse(bannir_avant_visite="null"), "bannir_adresse"),  # sans visite de bannissement
        (bras_adresse(compte="demo"), "bannir_adresse"),  # on ne bannit pas deux cibles à la fois
        (bras_adresse(identite_apres_bannissement="x"), "identite_apres_bannissement"),  # la même identité
    ],
)
def test_les_champs_du_bannissement_d_adresse_sont_controles(tmp_path, reglages, bras, message):
    with pytest.raises(ValueError, match=message):
        campagne(tmp_path, reglages, engines=bras, extra=ESPACEMENT)


def test_le_fichier_de_l_essai_se_valide(reglages):
    e = campaigns.lire(FICHIER_ESSAI, reglages)
    assert e.protections == ["endurance"] and e.scenarios == ["visite"] and e.monde == "serie"
    par_nom = {m.nom_affiche: m for m in e.engines}
    assert len(par_nom) == 3
    temoin = next(m for m in e.engines if m.bannir_adresse)
    assert temoin.bannir_avant_visite == 2 and temoin.identite_apres_bannissement
    assert temoin.identite_apres_bannissement != temoin.options["identite"]
    assert e.visites_de(temoin) == 2
    for m in e.engines:
        assert m.name == "noezia" and m.options["identite_native"] is True and m.options["headless"] is False
