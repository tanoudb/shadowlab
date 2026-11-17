"""Aides des tests du proxy par identité (étape 3.2, `docs/recherche/proxy-par-identite-2026-11-17.md`).

Tout est local (127.0.0.1, port 0), en threads, et s'arrête proprement (`arreter()`, ou `with`) :

- `ProxyHttpDeTest` et `ProxySocks5DeTest` : de faux proxys à authentification. Ils notent chaque connexion qu'ils
  ouvrent vers la cible (avec le port local de cette connexion) : c'est ce port que la cible voit comme port source.
- `CibleDeTest` : un serveur HTTP qui note chaque connexion ACCEPTÉE (pas seulement chaque requête), puis chaque
  requête.
- `EcouteStunDeTest` : une socket UDP qui compte les paquets reçus (le témoin d'une fuite WebRTC).
- `AmontMuet` : un « proxy » qui accepte la connexion et ne répond jamais (délai d'attente du relais).
- `ecrire_proxy` : écrit `proxy.json` à la main, SANS passer par `identite.declarer_proxy`.
- de petits clients bruts (`ouvrir_tunnel`, `echanger`, `lire_reponse`…) pour parler au relais ou à un proxy.

Importé par `from outils_proxy import ...` (même principe que `outils_recolte.py`).
"""

from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import os
import re
import select
import socket
import ssl
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import psutil

HOTE = "127.0.0.1"
FICHIER_PROXY = "proxy.json"  # le même nom que `identite.FICHIER_PROXY` (écrit en dur ici : pas de dépendance)

# Un PNG de 1 pixel : de quoi servir `/img.png`.
PNG_1_PIXEL = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg=="
)


# ── Bases communes ─────────────────────────────────────────────────────────


def _fermer(sock: socket.socket) -> None:
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    try:
        sock.close()
    except OSError:
        pass


class _Contexte:
    """`with objet:` démarre puis arrête."""

    def __enter__(self):
        self.demarrer()
        return self

    def __exit__(self, *_exc) -> None:
        self.arreter()


class _Serveur(_Contexte):
    """Socket d'écoute + une boucle d'acceptation + un thread par client. `arreter()` ferme tout et attend les fils."""

    def __init__(self) -> None:
        self._ecoute = socket.socket()
        self._ecoute.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._ecoute.bind((HOTE, 0))
        self._ecoute.listen(128)
        self._ecoute.settimeout(0.05)  # fermer une socket d'écoute depuis un autre fil ne débloque pas `accept` partout
        self.port: int = self._ecoute.getsockname()[1]
        self._arret = threading.Event()
        self._verrou = threading.Lock()
        self._sockets: set[socket.socket] = set()
        self._fils: list[threading.Thread] = []
        self._boucle: threading.Thread | None = None
        self.contacts = 0  # connexions TCP acceptées, qu'elles disent quelque chose ou non

    def demarrer(self):
        self._boucle = threading.Thread(target=self._accepter, name=f"{type(self).__name__}-{self.port}", daemon=True)
        self._boucle.start()
        return self

    def arreter(self) -> None:
        self._arret.set()
        try:
            self._ecoute.close()
        except OSError:
            pass
        with self._verrou:
            ouvertes = list(self._sockets)
        for sock in ouvertes:
            _fermer(sock)
        for fil in [self._boucle, *self._fils]:
            if fil is not None and fil is not threading.current_thread():
                fil.join(timeout=3)

    def _suivre(self, sock: socket.socket) -> None:
        with self._verrou:
            self._sockets.add(sock)

    def _liberer(self, sock: socket.socket) -> None:
        with self._verrou:
            self._sockets.discard(sock)
        _fermer(sock)

    def _accepter(self) -> None:
        while not self._arret.is_set():
            try:
                sock, _ = self._ecoute.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            sock.settimeout(None)
            with self._verrou:
                self.contacts += 1
            self._suivre(sock)
            fil = threading.Thread(target=self._client, args=(sock,), name=f"{type(self).__name__}-client", daemon=True)
            with self._verrou:
                self._fils = [f for f in self._fils if f.is_alive()] + [fil]
            fil.start()

    def _client(self, sock: socket.socket) -> None:
        try:
            self._servir(sock)
        except (OSError, ValueError):  # ConnectionError est une OSError ; ValueError : socket fermée sous la select
            pass
        finally:
            self._liberer(sock)

    def _servir(self, client: socket.socket) -> None:  # pragma: no cover — chaque sous-classe
        raise NotImplementedError

    def _relier(self, a: socket.socket, b: socket.socket, deja_lu_de_a: bytes = b"") -> None:
        """Recopie les octets dans les deux sens, jusqu'à ce que les deux côtés aient fini (ou arrêt). La fin d'écriture
        d'un côté est transmise à l'autre : rien n'est coupé avant la dernière réponse."""
        if deja_lu_de_a:
            self._vu_de_a(deja_lu_de_a)
            b.sendall(deja_lu_de_a)
        ouverts = [a, b]
        while ouverts and not self._arret.is_set():
            lisibles, _, _ = select.select(ouverts, [], [], 0.2)
            for sock in lisibles:
                autre = b if sock is a else a
                donnees = sock.recv(65536)
                if not donnees:
                    ouverts.remove(sock)
                    try:
                        autre.shutdown(socket.SHUT_WR)
                    except OSError:
                        pass
                    continue
                if sock is a:
                    self._vu_de_a(donnees)
                autre.sendall(donnees)

    def _vu_de_a(self, donnees: bytes) -> None:
        """Appelé pour tout octet qui va de `a` (le client) vers `b` : les faux proxys le notent."""


def lire_tete(sock: socket.socket) -> tuple[bytes, bytes]:
    """Lit jusqu'à la ligne vide qui finit l'en-tête HTTP. Rend (en-tête sans la ligne vide, octets lus en trop).
    Rend (b"", b"") si la connexion se ferme avant la fin de l'en-tête."""
    tampon = b""
    while b"\r\n\r\n" not in tampon:
        morceau = sock.recv(4096)
        if not morceau:
            return b"", b""
        tampon += morceau
    tete, _, reste = tampon.partition(b"\r\n\r\n")
    return tete, reste


def _lire_exactement(sock: socket.socket, n: int) -> bytes:
    donnees = b""
    while len(donnees) < n:
        morceau = sock.recv(n - len(donnees))
        if not morceau:
            raise ConnectionError("connexion fermée trop tôt")
        donnees += morceau
    return donnees


# ── Faux proxys ────────────────────────────────────────────────────────────


class _FauxProxy(_Serveur):
    """Un proxy qui ouvre vraiment la connexion vers la cible (avec ses propres noms : `noms_connus`).

    - `connexions` : une entrée `{"methode", "hote", "port", "port_source"}` par connexion sortante réussie ;
      `port_source` est le port local de la socket sortante (celui que la cible voit).
    - `refus` : nombre de refus d'authentification.
    - `contacts` : nombre de connexions reçues, toutes confondues (0 : personne ne l'a contacté).
    Un nom que le proxy ne connaît pas ne passe JAMAIS par le vrai DNS : l'échec est sec (sinon le trafic de fond de
    Chrome sortirait pour de bon). `localhost` est connu d'office (127.0.0.1) ; une adresse IP passe telle quelle.
    """

    schema = ""

    def __init__(self, utilisateur: str, mot_de_passe: str, nom: str, noms_connus: dict[str, str] | None = None):
        super().__init__()
        self.utilisateur = utilisateur
        self.mot_de_passe = mot_de_passe
        self.nom = nom
        self.noms_connus = {"localhost": HOTE, **{k.lower(): v for k, v in (noms_connus or {}).items()}}
        self.connexions: list[dict] = []
        self.refus = 0
        self._octets = bytearray()

    @property
    def adresse(self) -> str:
        return f"{self.schema}://{HOTE}:{self.port}"

    @property
    def octets_du_client(self) -> bytes:
        """Tout ce que le client du proxy a envoyé vers la cible une fois la connexion ouverte (pour HTTP : la requête
        réécrite en forme d'origine, puis la suite). Une requête s'y compte par ses ` HTTP/1.1\\r\\n`."""
        with self._verrou:
            return bytes(self._octets)

    def _vu_de_a(self, donnees: bytes) -> None:
        with self._verrou:
            self._octets += donnees

    def _compter_refus(self) -> None:
        with self._verrou:
            self.refus += 1

    def _ouvrir(self, methode: str, hote: str, port: int) -> socket.socket | None:
        """Connexion vers la cible, ou None (nom inconnu, cible fermée). Note la connexion si elle réussit."""
        adresse = self.noms_connus.get(hote.lower())
        if adresse is None:
            try:
                ipaddress.ip_address(hote)
            except ValueError:
                return None
            adresse = hote
        try:
            sortie = socket.create_connection((adresse, port), timeout=3)
        except OSError:
            return None
        sortie.settimeout(None)
        self._suivre(sortie)
        with self._verrou:
            self.connexions.append(
                {"methode": methode, "hote": hote, "port": port, "port_source": sortie.getsockname()[1]}
            )
        return sortie

    def _relier_et_fermer(self, client, sortie, deja_lu: bytes = b"") -> None:
        try:
            self._relier(client, sortie, deja_lu)
        finally:
            self._liberer(sortie)


class ProxyHttpDeTest(_FauxProxy):
    """Faux proxy HTTP, authentification Basic. `CONNECT hote:port` et requêtes en forme absolue `GET http://…`.
    Mauvais ou aucun identifiant : `407 Proxy Authentication Required`, aucune connexion ouverte."""

    schema = "http"

    def __init__(self, utilisateur, mot_de_passe, nom="A", noms_connus=None):
        super().__init__(utilisateur, mot_de_passe, nom, noms_connus)

    def _authentifie(self, entetes: list[tuple[str, str]]) -> bool:
        for nom, valeur in entetes:
            if nom.lower() != "proxy-authorization":
                continue
            schema, _, jeton = valeur.partition(" ")
            if schema.lower() != "basic":
                return False
            try:
                return base64.b64decode(jeton).decode("utf-8") == f"{self.utilisateur}:{self.mot_de_passe}"
            except ValueError:
                return False
        return False

    @staticmethod
    def _reponse(client: socket.socket, ligne: str, *entetes: str) -> None:
        corps = "\r\n".join([ligne, *entetes, "Content-Length: 0", "Connection: close"]) + "\r\n\r\n"
        client.sendall(corps.encode("latin-1"))

    def _servir(self, client: socket.socket) -> None:
        tete, reste = lire_tete(client)
        if not tete:
            return
        lignes = tete.decode("latin-1").split("\r\n")
        methode, cible, version = lignes[0].split(" ", 2)
        entetes = [(n.strip(), v.strip()) for n, _, v in (ligne.partition(":") for ligne in lignes[1:])]
        if not self._authentifie(entetes):
            self._compter_refus()
            self._reponse(
                client, "HTTP/1.1 407 Proxy Authentication Required", 'Proxy-Authenticate: Basic realm="test"'
            )
            return
        if methode == "CONNECT":
            hote, _, port = cible.rpartition(":")
            sortie = self._ouvrir(methode, hote.strip("[]"), int(port))
            if sortie is None:
                self._reponse(client, "HTTP/1.1 502 Bad Gateway")
                return
            client.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            self._relier_et_fermer(client, sortie, reste)
            return
        url = urlsplit(cible)
        if url.scheme != "http" or not url.hostname:
            self._reponse(client, "HTTP/1.1 400 Bad Request")
            return
        sortie = self._ouvrir(methode, url.hostname, url.port or 80)
        if sortie is None:
            self._reponse(client, "HTTP/1.1 502 Bad Gateway")
            return
        # Comme un vrai proxy : la requête repart en forme d'origine, sans les en-têtes qui ne regardent que le proxy
        # (la cible ne doit jamais voir `Proxy-Authorization`). `Connection` et le reste passent tels quels.
        chemin = (url.path or "/") + (f"?{url.query}" if url.query else "")
        sortant = [f"{methode} {chemin} {version}"]
        sortant += [f"{n}: {v}" for n, v in entetes if n.lower() not in ("proxy-authorization", "proxy-connection")]
        tete_sortante = ("\r\n".join(sortant) + "\r\n\r\n").encode("latin-1")
        self._relier_et_fermer(client, sortie, tete_sortante + reste)


class ProxySocks5DeTest(_FauxProxy):
    """Faux proxy SOCKS5, authentification utilisateur/mot de passe (RFC 1929), type d'adresse « nom de domaine »
    (et IPv4, IPv6). Mauvais identifiants : réponse d'échec RFC 1929 (`01 01`) puis fermeture."""

    schema = "socks5"

    def __init__(self, utilisateur, mot_de_passe, nom="B", noms_connus=None):
        super().__init__(utilisateur, mot_de_passe, nom, noms_connus)

    def _servir(self, client: socket.socket) -> None:
        version, nombre = _lire_exactement(client, 2)
        if version != 5:
            return
        methodes = _lire_exactement(client, nombre)
        if 2 not in methodes:
            client.sendall(b"\x05\xff")
            return
        client.sendall(b"\x05\x02")
        if _lire_exactement(client, 1) != b"\x01":
            return
        utilisateur = _lire_exactement(client, _lire_exactement(client, 1)[0])
        mot_de_passe = _lire_exactement(client, _lire_exactement(client, 1)[0])
        if (utilisateur, mot_de_passe) != (self.utilisateur.encode(), self.mot_de_passe.encode()):
            self._compter_refus()
            client.sendall(b"\x01\x01")
            return
        client.sendall(b"\x01\x00")
        _, commande, _, type_adresse = _lire_exactement(client, 4)
        if type_adresse == 1:
            hote = socket.inet_ntoa(_lire_exactement(client, 4))
        elif type_adresse == 3:
            hote = _lire_exactement(client, _lire_exactement(client, 1)[0]).decode("ascii")
        elif type_adresse == 4:
            hote = socket.inet_ntop(socket.AF_INET6, _lire_exactement(client, 16))
        else:
            client.sendall(b"\x05\x08\x00\x01" + bytes(6))  # type d'adresse non pris en charge
            return
        port = int.from_bytes(_lire_exactement(client, 2), "big")
        if commande != 1:
            client.sendall(b"\x05\x07\x00\x01" + bytes(6))  # seule la commande CONNECT existe
            return
        sortie = self._ouvrir("SOCKS5", hote, port)
        if sortie is None:
            client.sendall(b"\x05\x04\x00\x01" + bytes(6))  # hôte injoignable
            return
        client.sendall(b"\x05\x00\x00\x01" + socket.inet_aton(HOTE) + sortie.getsockname()[1].to_bytes(2, "big"))
        self._relier_et_fermer(client, sortie)


class AmontMuet(_Serveur):
    """Un « proxy » qui accepte la connexion et ne dit jamais rien (le relais doit finir par renoncer)."""

    schema = "http"

    @property
    def adresse(self) -> str:
        return f"{self.schema}://{HOTE}:{self.port}"

    def _servir(self, client: socket.socket) -> None:
        self._arret.wait()


class AmontEnregistreur(AmontMuet):
    """Comme `AmontMuet` (aucune réponse, jamais), mais note tout ce que le relais lui envoie : `octets_recus`, toutes
    connexions confondues. De quoi lire l'en-tête exact d'une requête sans avoir de vraie cible (port 80, IPv6…)."""

    def __init__(self) -> None:
        super().__init__()
        self._recu = bytearray()

    @property
    def octets_recus(self) -> bytes:
        with self._verrou:
            return bytes(self._recu)

    def _servir(self, client: socket.socket) -> None:
        while not self._arret.is_set():
            if not select.select([client], [], [], 0.2)[0]:
                continue
            donnees = client.recv(65536)
            if not donnees:
                return
            with self._verrou:
                self._recu += donnees


def attendre(condition, delai_s: float = 3.0) -> bool:
    """Vrai dès que `condition()` l'est, faux au bout de `delai_s` (les aides notent en fils, après la réponse)."""
    fin = time.monotonic() + delai_s
    while time.monotonic() < fin:
        if condition():
            return True
        time.sleep(0.02)
    return bool(condition())


def port_ferme() -> int:
    """Un port local sur lequel personne n'écoute (un proxy amont éteint)."""
    with socket.socket() as s:
        s.bind((HOTE, 0))
        return s.getsockname()[1]


# ── La cible : un site local qui note qui s'y connecte ──────────────────────

_IDENTIFIANT_SUR = re.compile(r"[A-Za-z0-9_.-]{1,40}")


def _page(identifiant: str) -> str:
    """La page de test : une image, un script, un appel de données (`fetch`), puis un élément `#fini` (et le titre
    « fini ») quand l'appel de données est revenu. Tout est en chemins relatifs : la page charge ses ressources par le
    même hôte et le même chemin réseau qu'elle. `#erreur` si l'appel échoue."""
    return (
        '<!doctype html><html><head><meta charset="utf-8"><title>debut</title></head><body>'
        f'<img src="/img.png?id={identifiant}" width="1" height="1" alt="">'
        f'<script src="/s.js?id={identifiant}"></script>'
        "<script>"
        "function marque(i,t){var p=document.createElement('p');p.id=i;p.textContent=t;document.body.appendChild(p);"
        "document.title=t}"
        f"fetch('/xhr?id={identifiant}').then(function(r){{return r.text()}})"
        ".then(function(){marque('fini','fini')}).catch(function(){marque('erreur','erreur')});"
        "</script></body></html>"
    )


def _page_webrtc(port_stun: int | None) -> str:
    """Crée une connexion WebRTC avec un serveur STUN local (UDP), un canal de données, une offre ; attend 3 s."""
    return (
        '<!doctype html><html><head><meta charset="utf-8"><title>webrtc</title></head><body><script>'
        "(async function(){"
        f"var pc=new RTCPeerConnection({{iceServers:[{{urls:'stun:{HOTE}:{port_stun}'}}]}});"
        "pc.createDataChannel('x');"
        "await pc.setLocalDescription(await pc.createOffer());"
        "await new Promise(function(r){setTimeout(r,3000)});"
        "var p=document.createElement('p');p.id='fini';p.textContent='fini';document.body.appendChild(p);"
        "document.title='webrtc-fini'"
        "})()</script></body></html>"
    )


class _ServeurCible(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, adresse, gestionnaire, cible: CibleDeTest, contexte_tls: ssl.SSLContext | None = None):
        super().__init__(adresse, gestionnaire)
        self.cible = cible
        self.contexte_tls = contexte_tls

    def handle_error(self, request, client_address) -> None:
        # Un client qui coupe d'un coup (RST) ou une fermeture à l'arrêt est normal ici : pas de trace. Le reste
        # (une vraie erreur du gestionnaire) s'affiche comme d'habitude.
        if not isinstance(sys.exc_info()[1], OSError):
            super().handle_error(request, client_address)

    def get_request(self):
        sock, adresse = super().get_request()
        if self.contexte_tls is not None:
            # La poignée de main TLS se fait au premier octet lu, dans le fil de la connexion : une connexion d'avance
            # qui ne dit rien (Chrome en ouvre) ne bloque pas la boucle d'acceptation.
            sock = self.contexte_tls.wrap_socket(sock, server_side=True, do_handshake_on_connect=False)
        self.cible._noter_connexion(sock, adresse[1])  # à l'ACCEPTATION : une connexion qui ne dit rien compte aussi
        return sock, adresse


class _GestionnaireCible(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"  # connexions persistantes : tout ce qui passe par un même tunnel garde un port source

    def log_message(self, *args) -> None:
        pass

    def _repondre(self, statut: int, corps: bytes, type_contenu: str, *, entetes: dict[str, str] | None = None) -> None:
        self.send_response(statut)
        self.send_header("Content-Type", type_contenu)
        self.send_header("Content-Length", str(len(corps)))
        for nom, valeur in (entetes or {}).items():
            self.send_header(nom, valeur)
        self.end_headers()
        self.wfile.write(corps)

    def do_POST(self) -> None:
        """`Content-Length` octets de corps, lus en entier, notés dans `corps_recus` ; la réponse dit leur nombre et
        leur empreinte. Pas de corps découpé : la cible ne sait pas le lire, et le relais le refuse avant."""
        cible: CibleDeTest = self.server.cible
        cible._noter_requete(self.path, self.client_address[1], {k.lower(): v for k, v in self.headers.items()})
        corps = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        cible._noter_corps(self.path, corps)
        resume = f"recu={len(corps)} sha256={hashlib.sha256(corps).hexdigest()}"
        self._repondre(200, resume.encode(), "text/plain")

    def do_GET(self) -> None:
        cible: CibleDeTest = self.server.cible
        cible._noter_requete(self.path, self.client_address[1], {k.lower(): v for k, v in self.headers.items()})
        url = urlsplit(self.path)
        requete = parse_qs(url.query)
        identifiant = requete.get("id", ["?"])[0]
        identifiant = identifiant if _IDENTIFIANT_SUR.fullmatch(identifiant) else "?"
        html = "text/html; charset=utf-8"
        if url.path == "/page":
            self._repondre(200, _page(identifiant).encode(), html)
        elif url.path == "/img.png":
            self._repondre(200, PNG_1_PIXEL, "image/png")
        elif url.path == "/s.js":
            self._repondre(200, b"window.sl_script = true;", "application/javascript")
        elif url.path == "/xhr":
            time.sleep(cible.delai_xhr_s)
            self._repondre(200, b"ok", "text/plain")
        elif url.path == "/redirige-dehors":
            if cible.cible2 is None:
                self._repondre(404, b"pas de cible2", "text/plain")
            else:
                adresse = (  # `localhost` : un second hôte, hors d'une liste 127.0.0.1
                    f"{cible.cible2.schema}://localhost:{cible.cible2.port}/"
                )
                self._repondre(302, b"", "text/plain", entetes={"Location": adresse})
        elif url.path == "/webrtc":
            self._repondre(200, _page_webrtc(cible.port_stun).encode(), html)
        elif url.path == "/gros":
            taille = int(requete.get("n", ["1000"])[0])
            self._repondre(200, bytes(i % 251 for i in range(taille)), "application/octet-stream")
        elif url.path == "/":
            self._repondre(200, b"<!doctype html><title>racine</title><p id='marque'>cible-atteinte</p>", html)
        else:
            self._repondre(404, b"inconnu", "text/plain")  # /favicon.ico et autres bruits de Chrome


class CibleDeTest(_Contexte):
    """Un serveur HTTP local qui note qui s'y connecte.

    - `tls` : `(cle.pem, cert.pem)` pour servir en HTTPS (`schema`, `url()` suivent) ; la poignée de main se fait dans
      le fil de la connexion ;
    - `corps_recus` : `(chemin, corps)` de chaque POST (n'importe quel chemin ; `Content-Length` octets lus) ;
    - `connexions_recues` : le port source de chaque connexion acceptée (liste, dans l'ordre) ;
    - `requetes` : une entrée `{"chemin", "port_source", "entetes"}` par requête (chemin avec sa requête, en-têtes en
      minuscules) ;
    - `port_stun` : le port UDP annoncé par `/webrtc` ; `cible2` : l'autre cible, où `/redirige-dehors` renvoie (par
      le nom `localhost`) ; `delai_xhr_s` : attente avant de répondre à `/xhr` (garde les connexions ouvertes plus
      longtemps, pour qu'un échantillonnage de sockets les voie).
    Routes : `/page?id=X`, `/img.png`, `/s.js`, `/xhr`, `/redirige-dehors`, `/webrtc`, `/gros?n=N`, `/` ; le reste 404.
    """

    def __init__(
        self,
        port_stun: int | None = None,
        cible2: CibleDeTest | None = None,
        delai_xhr_s: float = 0.0,
        tls: tuple[Path, Path] | None = None,
    ):
        self.port_stun = port_stun
        self.cible2 = cible2
        self.delai_xhr_s = delai_xhr_s
        self._connexions: list[int] = []
        self._requetes: list[dict] = []
        self._corps: list[tuple[str, bytes]] = []
        self._verrou = threading.Lock()
        self._sockets: set[socket.socket] = set()
        contexte = None
        if tls is not None:
            contexte = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            contexte.load_cert_chain(str(tls[1]), str(tls[0]))
        self.schema = "https" if tls is not None else "http"
        self._serveur = _ServeurCible((HOTE, 0), _GestionnaireCible, self, contexte)
        self.port: int = self._serveur.server_port
        self._fil: threading.Thread | None = None

    @property
    def connexions_recues(self) -> list[int]:
        with self._verrou:
            return list(self._connexions)

    @property
    def requetes(self) -> list[dict]:
        with self._verrou:
            return list(self._requetes)

    @property
    def corps_recus(self) -> list[tuple[str, bytes]]:
        with self._verrou:
            return list(self._corps)

    def requetes_de(self, identifiant: str) -> list[dict]:
        """Les requêtes qui portent `id=<identifiant>` (page, image, script, appel de données)."""
        return [r for r in self.requetes if f"id={identifiant}" in r["chemin"].split("?", 1)[-1].split("&")]

    def url(self, chemin: str, hote: str = HOTE) -> str:
        return f"{self.schema}://{hote}:{self.port}{chemin}"

    def _noter_connexion(self, sock: socket.socket, port_source: int) -> None:
        with self._verrou:
            self._connexions.append(port_source)
            self._sockets.add(sock)

    def _noter_corps(self, chemin: str, corps: bytes) -> None:
        with self._verrou:
            self._corps.append((chemin, corps))

    def _noter_requete(self, chemin: str, port_source: int, entetes: dict[str, str]) -> None:
        with self._verrou:
            self._requetes.append({"chemin": chemin, "port_source": port_source, "entetes": entetes})

    def demarrer(self):
        self._fil = threading.Thread(
            target=self._serveur.serve_forever, kwargs={"poll_interval": 0.02}, name="CibleDeTest", daemon=True
        )
        self._fil.start()
        return self

    def arreter(self) -> None:
        self._serveur.shutdown()
        self._serveur.server_close()
        with self._verrou:
            ouvertes = list(self._sockets)
        for sock in ouvertes:
            _fermer(sock)
        if self._fil is not None:
            self._fil.join(timeout=3)


class EcouteStunDeTest(_Contexte):
    """Une socket UDP locale (port 0) qui compte les paquets reçus : `paquets`, et `sources` (leurs adresses)."""

    def __init__(self) -> None:
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.bind((HOTE, 0))
        self._socket.settimeout(0.05)
        self.port: int = self._socket.getsockname()[1]
        self.paquets = 0
        self.sources: list[tuple[str, int]] = []
        self._arret = threading.Event()
        self._fil: threading.Thread | None = None

    def demarrer(self):
        self._fil = threading.Thread(target=self._ecouter, name="EcouteStunDeTest", daemon=True)
        self._fil.start()
        return self

    def _ecouter(self) -> None:
        while not self._arret.is_set():
            try:
                _, source = self._socket.recvfrom(4096)
            except TimeoutError:
                continue
            except OSError:
                return
            self.sources.append(source)
            self.paquets += 1

    def arreter(self) -> None:
        self._arret.set()
        if self._fil is not None:
            self._fil.join(timeout=3)
        self._socket.close()


# ── proxy.json écrit à la main ─────────────────────────────────────────────


def ecrire_proxy(
    racine_identites: Path | str,
    nom: str,
    serveur: str,
    utilisateur: str | None = None,
    mot_de_passe: str | None = None,
    *,
    mode: int = 0o600,
    brut: str | None = None,
) -> Path:
    """Écrit `<racine>/<nom>/proxy.json` SANS passer par `identite.declarer_proxy` : les tests de `lire_proxy` ne
    dépendent donc pas de lui. Dossier en 0700, fichier en 0600 (`chmod` explicite : l'umask ne compte pas).
    `mode` : un autre droit, pour essayer les refus ; `brut` : le texte exact du fichier (JSON cassé, etc.)."""
    dossier = Path(racine_identites) / nom
    dossier.mkdir(parents=True, exist_ok=True)
    dossier.chmod(0o700)
    if brut is None:
        champs = {"serveur": serveur, "utilisateur": utilisateur, "mot_de_passe": mot_de_passe}
        brut = json.dumps({cle: valeur for cle, valeur in champs.items() if valeur is not None})
    chemin = dossier / FICHIER_PROXY
    descripteur = os.open(chemin, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descripteur, "w", encoding="utf-8") as f:
        f.write(brut)
    chemin.chmod(mode)
    return chemin


# ── Petits clients bruts ───────────────────────────────────────────────────


def lire_jusqu_a_fin(sock: socket.socket, delai_s: float = 10.0) -> bytes:
    """Tout ce que le pair envoie jusqu'à ce qu'il ferme (ou jusqu'au délai : `TimeoutError`, signe d'une connexion
    qui reste ouverte)."""
    sock.settimeout(delai_s)
    tampon = b""
    while True:
        morceau = sock.recv(65536)
        if not morceau:
            return tampon
        tampon += morceau


def statut_de(octets: bytes) -> int:
    """Le code de la première ligne `HTTP/1.x NNN …` ; 0 s'il n'y en a pas."""
    trouve = re.match(rb"HTTP/1\.[01] (\d{3})", octets)
    return int(trouve.group(1)) if trouve else 0


def lire_reponse(octets: bytes) -> tuple[int, dict[str, str], bytes]:
    """(statut, en-têtes en minuscules, corps) d'une réponse HTTP complète lue jusqu'à la fermeture."""
    tete, _, corps = octets.partition(b"\r\n\r\n")
    lignes = tete.decode("latin-1").split("\r\n")
    entetes = {n.strip().lower(): v.strip() for n, _, v in (ligne.partition(":") for ligne in lignes[1:])}
    return statut_de(octets), entetes, corps


def ouvrir_connexion(port: int, delai_s: float = 10.0) -> socket.socket:
    sock = socket.create_connection((HOTE, port), timeout=delai_s)
    sock.settimeout(delai_s)
    return sock


def ouvrir_tunnel(
    port_relais: int, hote: str, port: int, delai_s: float = 10.0, entetes: str = ""
) -> tuple[int, bytes, socket.socket]:
    """Envoie `CONNECT hote:port` à un relais (ou à un proxy) et lit la réponse. Rend (statut, tête, socket) : la socket
    reste ouverte, prête à porter le trafic de la suite quand le statut est 200."""
    sock = ouvrir_connexion(port_relais, delai_s)
    sock.sendall(f"CONNECT {hote}:{port} HTTP/1.1\r\nHost: {hote}:{port}\r\n{entetes}\r\n".encode("latin-1"))
    tete, _ = lire_tete(sock)
    return statut_de(tete), tete, sock


def echanger(port: int, octets: bytes, delai_s: float = 10.0) -> bytes:
    """Ouvre une connexion, envoie `octets`, lit tout jusqu'à la fermeture, ferme."""
    with ouvrir_connexion(port, delai_s) as sock:
        sock.sendall(octets)
        return lire_jusqu_a_fin(sock, delai_s)


def get_absolu(port: int, url: str, entetes: str = "", delai_s: float = 10.0) -> bytes:
    """Une requête simple en forme absolue (`GET http://hote:port/chemin`), comme Chrome la pose à un proxy HTTP."""
    morceaux = urlsplit(url)
    requete = f"GET {url} HTTP/1.1\r\nHost: {morceaux.netloc}\r\n{entetes}\r\n"
    return echanger(port, requete.encode("latin-1"), delai_s)


def get_direct(port: int, chemin: str, delai_s: float = 10.0) -> bytes:
    """Une requête ordinaire, en forme d'origine, à un serveur (la cible) : `Connection: close`, lue jusqu'à la fin."""
    return echanger(port, f"GET {chemin} HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n".encode("latin-1"), delai_s)


def get_dans_le_tunnel(sock: socket.socket, hote: str, port: int, chemin: str, delai_s: float = 10.0) -> bytes:
    """Une requête dans un tunnel déjà ouvert ; `Connection: close` pour que la cible ferme après la réponse."""
    sock.sendall(f"GET {chemin} HTTP/1.1\r\nHost: {hote}:{port}\r\nConnection: close\r\n\r\n".encode("latin-1"))
    return lire_jusqu_a_fin(sock, delai_s)


def client_socks5(
    port: int, utilisateur: str, mot_de_passe: str, hote: str, port_cible: int, *, domaine: bool = True
) -> tuple[int, socket.socket | None]:
    """Un client SOCKS5 minimal (RFC 1928 et 1929) : nom de domaine (`domaine`) ou IPv4.
    Rend (code de réponse, socket) : 0 réussi (socket prête), 0x100 si l'authentification échoue (socket fermée,
    None), sinon le code d'échec de la réponse (ex. 4 : hôte injoignable)."""
    sock = ouvrir_connexion(port)
    sock.sendall(b"\x05\x01\x02")
    if _lire_exactement(sock, 2) != b"\x05\x02":
        sock.close()
        return 0x101, None
    u, m = utilisateur.encode(), mot_de_passe.encode()
    sock.sendall(b"\x01" + bytes([len(u)]) + u + bytes([len(m)]) + m)
    if _lire_exactement(sock, 2) != b"\x01\x00":
        sock.close()
        return 0x100, None
    if domaine:
        adresse = b"\x03" + bytes([len(hote)]) + hote.encode("ascii")
    else:
        adresse = b"\x01" + socket.inet_aton(hote)
    sock.sendall(b"\x05\x01\x00" + adresse + port_cible.to_bytes(2, "big"))
    reponse = _lire_exactement(sock, 10)  # 4 d'en-tête + IPv4 + port : le faux proxy répond toujours en IPv4
    if reponse[1] != 0:
        sock.close()
        return reponse[1], None
    return 0, sock


# ── Échantillonnage des sockets de Chrome (psutil) ──────────────────────────


class Echantillonneur(threading.Thread):
    """Toutes les 0,2 s : les connexions de l'arbre de processus de Chrome (identifié par son dossier de profil).

    - `interdites` : connexions TCP établies ou en cours vers autre chose que `127.0.0.1:<port du relais>` ;
    - `vers_le_relais` : combien de fois une connexion vers le relais a été vue ;
    - `udp` : sockets UDP vus (noté au compte rendu, rien n'est affirmé) ;
    - `lignes_de_commande` : celles de tous les descendants du processus de test (Chrome, pilote Playwright).
    """

    def __init__(self, nom_identite: str, port_relais: int) -> None:
        super().__init__(name=f"echantillonneur-{nom_identite}", daemon=True)
        self.nom_identite, self.port_relais = nom_identite, port_relais
        self.interdites: set[tuple] = set()
        self.vers_le_relais = 0
        self.udp: set[tuple] = set()
        self.lignes_de_commande: set[str] = set()
        self.echantillons = 0
        self.acces_refuses = 0
        self._arret = threading.Event()

    def arreter(self) -> None:
        self._arret.set()
        self.join(timeout=5)

    def run(self) -> None:
        while not self._arret.is_set():
            try:
                self._une_fois()
            except psutil.Error:
                pass
            self._arret.wait(0.2)

    def _principal(self, descendants) -> psutil.Process | None:
        """Le processus principal de Chrome pour cette identité : son `--user-data-dir`, et pas de `--type=`."""
        for p in descendants:
            try:
                ligne = p.cmdline()
            except psutil.Error:
                continue
            if any(a.startswith("--type=") for a in ligne):
                continue
            if any(a.startswith("--user-data-dir=") and f"/{self.nom_identite}/chrome" in a for a in ligne):
                return p
        return None

    def _une_fois(self) -> None:
        descendants = psutil.Process().children(recursive=True)
        for p in descendants:
            try:
                self.lignes_de_commande.add(" ".join(p.cmdline()))
            except psutil.Error:
                pass
        principal = self._principal(descendants)
        if principal is None:
            return
        arbre = [principal, *principal.children(recursive=True)]
        self.echantillons += 1
        for p in arbre:
            try:
                connexions = p.net_connections(kind="inet")
            except psutil.Error:
                self.acces_refuses += 1
                continue
            for c in connexions:
                if c.type == socket.SOCK_DGRAM:
                    self.udp.add((p.name(), tuple(c.laddr)))
                    continue
                if not c.raddr or c.status not in ("ESTABLISHED", "SYN_SENT", "SYN_RECV"):
                    continue  # en écoute, ou déjà en fin de vie
                if tuple(c.raddr) == ("127.0.0.1", self.port_relais):
                    self.vers_le_relais += 1
                else:
                    self.interdites.add((tuple(c.laddr), tuple(c.raddr), c.status))
