"""Proxy par identité : l'adresse de sortie d'une identité et le relais local qui la fait respecter.

Conception : `docs/recherche/proxy-par-identite-2026-11-17.md`.

Chrome n'a pour proxy que le `RelaisProxy`, sur 127.0.0.1, sans identifiant : rien de secret dans ses arguments ni
dans la mémoire du pilote Playwright. Le relais tient les identifiants, joint le proxy de l'identité (HTTP ou SOCKS5) et
recopie les octets. Il est aussi le verrou réseau de l'identité : Chrome n'a aucun chemin direct, et tout hôte hors
périmètre est refusé avant que le proxy soit contacté.

Règles tenues partout dans ce module :
- le mot de passe, l'utilisateur et leur forme encodée n'entrent dans aucun message d'erreur, aucune `Demande`, aucun
  journal (un message d'erreur d'`open()` finit dans les journaux et dans la base d'une campagne) ;
- aucun repli sur une connexion directe : si le proxy ne répond pas, la demande échoue ;
- aucun nom d'hôte n'est résolu ici (le nom part au proxy, qui résout et sort) ; seul le nom du proxy lui-même l'est.
"""

from __future__ import annotations

import base64
import dataclasses
import ipaddress
import re
import selectors
import socket
import threading
import time
from typing import NamedTuple
from urllib.parse import urlsplit

from ...perimetre import ILLIMITE

SCHEMAS = ("http", "socks5")
TAILLE_MAX_ENTETE = 64 * 1024  # un en-tête plus gros n'est pas une requête de navigateur : refusé
_HOTE_SUR = re.compile(r"[A-Za-z0-9_.:-]{1,253}")  # nom ou adresse ; rien qui puisse casser une ligne de requête
_CIBLE_SURE = re.compile(r"[\x21-\x7e]+")  # ni espace ni caractère de contrôle dans la cible d'une requête
# En-têtes qui ne regardent que le saut entre le client et le relais : jamais transmis, le relais impose les siens.
_ENTETES_DE_SAUT = frozenset({"connection", "proxy-connection", "keep-alive", "proxy-authorization"})


class ProxyInvalide(ValueError):
    """Le proxy déclaré (adresse, identifiants, fichier, droits) est refusé. Le message ne cite jamais ce qu'on a lu."""


@dataclasses.dataclass(frozen=True)
class ProxyIdentite:
    """Le proxy d'une identité. `mot_de_passe` est hors du `repr` ; `repr` et `str` donnent le masque."""

    schema: str
    hote: str
    port: int
    utilisateur: str | None = None
    mot_de_passe: str | None = dataclasses.field(default=None, repr=False)

    def masque(self) -> str:
        """L'adresse sans les identifiants (`***:***@` à leur place s'il y en a) : la seule forme à écrire ailleurs."""
        identifiants = "***:***@" if self.utilisateur is not None or self.mot_de_passe is not None else ""
        return f"{self.schema}://{identifiants}{_autorite(self.hote, self.port)}"

    def __repr__(self) -> str:
        return self.masque()

    __str__ = __repr__


def _autorite(hote: str, port: int) -> str:
    return f"[{hote}]:{port}" if ":" in hote else f"{hote}:{port}"


def analyser(serveur: str, utilisateur: str | None = None, mot_de_passe: str | None = None) -> ProxyIdentite:
    """Valide l'adresse (`http://hote:port` ou `socks5://hote:port`) et les identifiants, donnés à part.

    Aucun message ne répète un morceau de l'adresse : sans schéma, `utilisateur:mdp@hote:1` serait lu avec l'utilisateur
    pour schéma."""
    if not isinstance(serveur, str) or not serveur:
        raise ProxyInvalide("adresse de proxy absente (un texte est attendu)")
    for nom, valeur in (("utilisateur", utilisateur), ("mot_de_passe", mot_de_passe)):
        if valeur is not None and not isinstance(valeur, str):
            raise ProxyInvalide(f"{nom} du proxy : un texte est attendu")
    try:
        morceaux = urlsplit(serveur)
        port = morceaux.port
    except ValueError:
        raise ProxyInvalide("adresse de proxy illisible (port ou crochets)") from None
    if morceaux.scheme not in SCHEMAS:
        raise ProxyInvalide("schéma de proxy refusé (http ou socks5 attendu)")
    if "@" in morceaux.netloc:
        raise ProxyInvalide(
            "identifiants dans l'adresse du proxy refusés (utilisateur et mot de passe se donnent à part)"
        )
    if not morceaux.hostname:
        raise ProxyInvalide("hôte du proxy absent")
    if port is None or not 1 <= port <= 65535:
        raise ProxyInvalide("port du proxy absent ou hors de 1 à 65535")
    if morceaux.path not in ("", "/") or morceaux.query or morceaux.fragment:
        raise ProxyInvalide("l'adresse du proxy ne porte que schéma, hôte et port")
    if morceaux.scheme == "socks5" and any(len(v.encode()) > 255 for v in (utilisateur or "", mot_de_passe or "")):
        raise ProxyInvalide("identifiants SOCKS5 : 255 octets au plus chacun")
    return ProxyIdentite(morceaux.scheme, morceaux.hostname, port, utilisateur, mot_de_passe)


class Demande(NamedTuple):
    """Une demande reçue par le relais. `methode` est celle que le client a écrite (`CONNECT`, `GET`…) ; `decision` :
    `transmise`, `refusee_perimetre`, `refusee_amont` (le proxy a dit non) ou `echec_amont` (injoignable, muet,
    illisible)."""

    methode: str
    hote: str
    port: int
    decision: str


class _RequeteInvalide(Exception):
    pass


class _AmontRefuse(Exception):
    """Le proxy de l'identité a répondu non (identifiants, hôte refusé)."""


class _Requete(NamedTuple):
    methode: str
    hote: str
    port: int
    cible: str  # telle que le client l'a écrite
    chemin: str  # forme d'origine (`/chemin?requete`) d'une requête simple ; vide pour CONNECT
    version: str
    entetes: list[tuple[str, str]]


def _fermer(sock: socket.socket) -> None:
    for operation in (lambda: sock.shutdown(socket.SHUT_RDWR), sock.close):
        try:
            operation()
        except OSError:
            pass


def _couper(sock: socket.socket) -> None:
    """Coupe les deux sens sans fermer le descripteur : réveille un autre fil bloqué sur cette socket."""
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass


def _demi_fermer(sock: socket.socket) -> None:
    """Dit au pair qu'il n'y a plus rien à lire de ce côté (fin d'un sens), sans couper l'autre sens."""
    try:
        sock.shutdown(socket.SHUT_WR)
    except OSError:
        pass


def _attendre_lisible(sock: socket.socket, fin: float) -> None:
    """Attend de la donnée jusqu'à `fin` (`time.monotonic`), sinon `TimeoutError`. Un délai de socket ne convient pas :
    il s'appliquerait aussi aux envois de l'autre fil, qui peuvent légitimement durer (corps de requête)."""
    reste = fin - time.monotonic()
    try:
        if reste > 0:
            with selectors.DefaultSelector() as selecteur:
                selecteur.register(sock, selectors.EVENT_READ)
                if selecteur.select(reste):
                    return
    except ValueError:  # socket fermée par `arreter()` pendant l'attente
        raise ConnectionError("relais arrêté") from None
    raise TimeoutError("le proxy de l'identité n'a pas répondu à temps")


def _recevoir_exactement(sock: socket.socket, nombre: int, fin: float) -> bytes:
    donnees = b""
    while len(donnees) < nombre:
        _attendre_lisible(sock, fin)
        morceau = sock.recv(nombre - len(donnees))
        if not morceau:
            raise ConnectionError("le proxy de l'identité a fermé la connexion")
        donnees += morceau
    return donnees


def _lire_tete(sock: socket.socket, fin: float | None = None) -> tuple[bytes, bytes] | None:
    """Lit jusqu'à la ligne vide qui finit un en-tête HTTP. Rend (en-tête sans la ligne vide, octets lus en trop), ou
    None si la connexion se ferme avant la fin ou si l'en-tête dépasse `TAILLE_MAX_ENTETE`. Sans `fin`, attend sans
    limite (un navigateur ouvre des connexions d'avance et les laisse longtemps muettes)."""
    tampon = b""
    while b"\r\n\r\n" not in tampon:
        if fin is not None:
            _attendre_lisible(sock, fin)
        morceau = sock.recv(4096)
        if not morceau or len(tampon) > TAILLE_MAX_ENTETE:
            return None
        tampon += morceau
    tete, _, reste = tampon.partition(b"\r\n\r\n")
    return tete, reste


def _statut(tete: bytes) -> int:
    trouve = re.match(rb"HTTP/1\.[01] (\d{3})", tete)
    if trouve is None:
        raise ConnectionError("réponse du proxy de l'identité illisible")
    return int(trouve.group(1))


def _separer_hote_port(autorite: str) -> tuple[str, int]:
    hote, deux_points, port = autorite.rpartition(":")
    if not deux_points or not port.isascii() or not port.isdigit() or not 1 <= int(port) <= 65535:
        raise _RequeteInvalide
    return _hote_sur(hote.removeprefix("[").removesuffix("]")), int(port)


def _hote_sur(hote: str) -> str:
    if not _HOTE_SUR.fullmatch(hote):
        raise _RequeteInvalide
    return hote


def _lire_requete(tete: bytes) -> _Requete:
    """Comprend l'en-tête d'un client : `CONNECT hote:port` ou une requête simple en forme absolue `http://hote/chemin`.
    La forme d'origine n'est pas acceptée : le relais n'est pas un serveur. Tout le reste est refusé."""
    lignes = tete.decode("latin-1").split("\r\n")
    if any("\n" in ligne or "\r" in ligne for ligne in lignes):  # une ligne glissée dans la requête du proxy
        raise _RequeteInvalide
    try:
        methode, cible, version = lignes[0].split(" ")
    except ValueError:
        raise _RequeteInvalide from None
    if not re.fullmatch(r"[A-Z-]+", methode) or not re.fullmatch(r"HTTP/1\.[01]", version):
        raise _RequeteInvalide
    if not _CIBLE_SURE.fullmatch(cible):
        raise _RequeteInvalide
    entetes = []
    for ligne in lignes[1:]:
        nom, deux_points, valeur = ligne.partition(":")
        if not deux_points or not nom or nom != nom.strip():
            raise _RequeteInvalide
        entetes.append((nom, valeur.strip()))
    if methode == "CONNECT":
        hote, port = _separer_hote_port(cible)
        return _Requete(methode, hote, port, cible, "", version, entetes)
    try:
        morceaux = urlsplit(cible)
        port = morceaux.port or 80
    except ValueError:
        raise _RequeteInvalide from None
    if morceaux.scheme != "http" or "@" in morceaux.netloc or not morceaux.hostname or not 1 <= port <= 65535:
        raise _RequeteInvalide
    chemin = (morceaux.path or "/") + (f"?{morceaux.query}" if morceaux.query else "")
    return _Requete(methode, _hote_sur(morceaux.hostname), port, cible, chemin, version, entetes)


def _entetes_sortants(requete: _Requete, *supplementaires: str) -> str:
    """Les en-têtes du client sans ceux du saut, puis `Connection: close` et les `supplementaires`, et la ligne vide."""
    gardes = [f"{nom}: {valeur}" for nom, valeur in requete.entetes if nom.lower() not in _ENTETES_DE_SAUT]
    return "".join(f"{ligne}\r\n" for ligne in (*gardes, "Connection: close", *supplementaires)) + "\r\n"


_RAISONS = {400: "Bad Request", 403: "Forbidden", 502: "Bad Gateway"}


def _refuser(client: socket.socket, statut: int, explication: str) -> None:
    """Refuse en une réponse complète. 502 et non 407 pour un refus du proxy : sur un 407 Chrome ouvre une demande
    d'identifiants à l'écran, et ce n'est pas lui qui les tient."""
    corps = explication.encode()
    entete = (
        f"HTTP/1.1 {statut} {_RAISONS[statut]}\r\nContent-Type: text/plain; charset=utf-8\r\n"
        f"Content-Length: {len(corps)}\r\nConnection: close\r\n\r\n"
    )
    client.sendall(entete.encode("ascii") + corps)


class RelaisProxy:
    """Relais HTTP local (127.0.0.1, port libre) vers le proxy d'une identité. Un fil par connexion et un fil par sens.

    `hotes_autorises` (le périmètre ; `*` : tout passe) et `hotes_supplementaires` (les hôtes des défis) disent les
    hôtes permis ; le contrôle se fait par nom, comme `perimetre.verifier_url` mais sans sa résolution : le relais ne
    joint jamais rien en direct (le proxy résout et sort), donc résoudre ici ne protégerait de rien, fuirait le nom hors
    proxy et refuserait à tort un nom que seul le proxy connaît.

    `delai_s` borne ce qu'on attend du proxy : connexion, échange d'ouverture, et pour une requête simple le début de la
    réponse (une origine plus lente que cela donne 502). Une fois un tunnel ouvert, rien n'est borné.

    Une connexion du client porte une seule requête : le relais impose `Connection: close` dans les deux sens, et c'est
    le client qui obéit (Chrome : mesuré, une demande notée par requête reçue). La recopie ne relit pas ce qu'elle
    transporte : un client qui désobéirait enverrait sa seconde requête sans décision de périmètre (un proxy HTTP,
    averti par `Connection: close`, la refuserait)."""

    def __init__(
        self,
        amont: ProxyIdentite,
        hotes_autorises: tuple[str, ...],
        hotes_supplementaires: tuple[str, ...] = (),
        delai_s: float = 15.0,
    ) -> None:
        self._amont = amont
        self._illimite = ILLIMITE in {h.strip() for h in hotes_autorises}
        self._hotes = frozenset(h.lower().strip("[]") for h in (*hotes_autorises, *hotes_supplementaires))
        self._delai_s = delai_s
        self._demandes: list[Demande] = []
        self._verrou = threading.Lock()
        self._arret = threading.Event()
        self._sockets: set[socket.socket] = set()  # tout ce qui est ouvert : `arreter()` le ferme
        self._fils: list[threading.Thread] = []
        self._ecoute: socket.socket | None = None
        self._boucle: threading.Thread | None = None
        self._port: int | None = None

    @property
    def amont(self) -> ProxyIdentite:
        return self._amont

    @property
    def adresse(self) -> str:
        if self._port is None:
            raise RuntimeError("relais pas démarré")
        return f"http://127.0.0.1:{self._port}"

    @property
    def demandes(self) -> list[Demande]:
        with self._verrou:
            return list(self._demandes)

    def demarrer(self) -> int:
        if self._ecoute is not None:
            raise RuntimeError("relais déjà démarré")
        ecoute = socket.socket()
        try:
            ecoute.bind(("127.0.0.1", 0))
            ecoute.listen(128)
        except OSError:
            ecoute.close()
            raise
        ecoute.settimeout(0.2)  # fermer une socket d'écoute depuis un autre fil ne réveille pas `accept` partout
        self._ecoute = ecoute
        self._port = ecoute.getsockname()[1]
        self._boucle = threading.Thread(target=self._accepter, args=(ecoute,), name="relais-accept", daemon=True)
        self._boucle.start()
        return self._port

    def arreter(self) -> None:
        """Ferme l'écoute et toutes les connexions ouvertes (tunnels compris), puis attend les fils. Sans effet si le
        relais est déjà arrêté ou n'a pas démarré."""
        with self._verrou:
            self._arret.set()
            ouvertes = list(self._sockets)
            fils = [self._boucle, *self._fils]
        if self._ecoute is not None:
            _fermer(self._ecoute)
        for sock in ouvertes:
            _fermer(sock)
        for fil in fils:
            if fil is not None and fil is not threading.current_thread():
                fil.join(timeout=3)

    def __enter__(self) -> RelaisProxy:
        self.demarrer()
        return self

    def __exit__(self, *_exc) -> None:
        self.arreter()

    # ── Connexions des clients ─────────────────────────────────────────

    def _accepter(self, ecoute: socket.socket) -> None:
        while not self._arret.is_set():
            try:
                client, _ = ecoute.accept()
            except TimeoutError:
                continue
            except OSError:  # écoute fermée par `arreter()`
                return
            client.settimeout(None)
            try:
                self._suivre(client)
                self._lancer(threading.Thread(target=self._client, args=(client,), name="relais-client", daemon=True))
            except ConnectionError:  # arrêt survenu entre `accept` et ici : rien ne doit survivre à `arreter()`
                self._liberer(client)
                return

    def _suivre(self, sock: socket.socket) -> None:
        """Note une socket ouverte pour que `arreter()` la ferme. Si le relais s'arrête, la ferme et lève."""
        with self._verrou:
            if not self._arret.is_set():
                self._sockets.add(sock)
                return
        _fermer(sock)
        raise ConnectionError("relais arrêté")

    def _lancer(self, fil: threading.Thread) -> None:
        """Démarre un fil que `arreter()` attendra. Lève si le relais s'arrête (aucun fil ne naît après l'arrêt)."""
        with self._verrou:
            if self._arret.is_set():
                raise ConnectionError("relais arrêté")
            self._fils = [f for f in self._fils if f.is_alive()] + [fil]
            fil.start()

    def _liberer(self, sock: socket.socket) -> None:
        with self._verrou:
            self._sockets.discard(sock)
        _fermer(sock)

    def _noter(self, requete: _Requete, decision: str) -> None:
        with self._verrou:
            self._demandes.append(Demande(requete.methode, requete.hote, requete.port, decision))

    def _autorise(self, hote: str) -> bool:
        return self._illimite or hote.lower() in self._hotes

    def _client(self, client: socket.socket) -> None:
        try:
            self._servir(client)
        except OSError:  # le client a coupé, ou arrêt en cours : rien à dire à personne
            pass
        finally:
            self._liberer(client)

    def _servir(self, client: socket.socket) -> None:
        lu = _lire_tete(client)
        if lu is None:
            return
        tete, deja_lu = lu
        try:
            requete = _lire_requete(tete)
        except _RequeteInvalide:
            _refuser(client, 400, "Requête incompréhensible pour le relais.")
            return
        if not self._autorise(requete.hote):
            self._noter(requete, "refusee_perimetre")
            _refuser(client, 403, "Hôte hors périmètre pour cette identité.")
            return
        amont: socket.socket | None = None
        try:
            try:
                fin = time.monotonic() + self._delai_s
                amont = self._ouvrir_amont(fin)
                reponse, aller = self._joindre(client, amont, requete, deja_lu, fin)
            except _AmontRefuse:
                decision = "refusee_amont"
            except OSError:  # injoignable, muet, coupé, réponse illisible
                decision = "echec_amont"
            else:
                self._noter(requete, "transmise")
                client.sendall(reponse)
                self._recopier(amont, client)
                aller.join()
                return
            # Jamais de repli sur une connexion directe : la demande échoue.
            self._noter(requete, decision)
            _refuser(client, 502, "Le proxy de l'identité a refusé la demande ou n'a pas répondu.")
        finally:
            # Fermer réveille le fil de recopie encore bloqué (arrêt, ou échec après son départ) ; `arreter()` l'attend.
            if amont is not None:
                self._liberer(amont)
            self._liberer(client)

    # ── Vers le proxy de l'identité ────────────────────────────────────

    def _ouvrir_amont(self, fin: float) -> socket.socket:
        sock = socket.create_connection(
            (self._amont.hote, self._amont.port), timeout=max(fin - time.monotonic(), 0.001)
        )
        sock.settimeout(None)
        self._suivre(sock)
        return sock

    def _joindre(
        self, client: socket.socket, amont: socket.socket, requete: _Requete, deja_lu: bytes, fin: float
    ) -> tuple[bytes, threading.Thread]:
        """Ouvre le chemin vers l'hôte demandé, puis lance la recopie client -> proxy dans un fil. Rend ce qu'il faut
        répondre au client avant de recopier le retour, et ce fil. Lève `_AmontRefuse` ou `OSError`."""
        if requete.methode == "CONNECT":
            en_trop = b""
            if self._amont.schema == "http":
                en_trop = self._connect_http(amont, requete, fin)
            else:
                self._connect_socks5(amont, requete, fin)
            return b"HTTP/1.1 200 Connection Established\r\n\r\n" + en_trop, self._aller(client, amont, deja_lu)
        # Requête simple : `Connection: close` impose une requête par connexion.
        if self._amont.schema == "http":
            envoi = self._requete_pour_proxy_http(requete)
        else:
            self._connect_socks5(amont, requete, fin)
            envoi = self._requete_d_origine(requete)
        # La recopie part avant la lecture de la réponse : une origine qui attend tout le corps pour répondre
        # (formulaire) bloquerait sinon, le corps restant chez le client.
        aller = self._aller(client, amont, envoi + deja_lu)
        retour = _lire_tete(amont, fin)
        if retour is None:
            raise ConnectionError("le proxy de l'identité a fermé la connexion")
        tete, en_trop = retour
        if self._amont.schema == "http" and _statut(tete) == 407:
            raise _AmontRefuse  # 407 seul : un 403 d'une requête simple est la réponse de l'origine (l'Arena en sert)
        lignes = [
            ligne for ligne in tete.split(b"\r\n") if not ligne.lower().startswith((b"connection:", b"keep-alive:"))
        ]
        return b"\r\n".join([*lignes, b"Connection: close"]) + b"\r\n\r\n" + en_trop, aller

    def _requete_pour_proxy_http(self, requete: _Requete) -> bytes:
        entete = f"{requete.methode} {requete.cible} {requete.version}\r\n"
        return (entete + _entetes_sortants(requete, *self._autorisation())).encode("latin-1")

    def _requete_d_origine(self, requete: _Requete) -> bytes:
        entete = f"{requete.methode} {requete.chemin} {requete.version}\r\n"
        return (entete + _entetes_sortants(requete)).encode("latin-1")

    def _autorisation(self) -> list[str]:
        if self._amont.utilisateur is None and self._amont.mot_de_passe is None:
            return []
        brut = f"{self._amont.utilisateur or ''}:{self._amont.mot_de_passe or ''}".encode()
        return [f"Proxy-Authorization: Basic {base64.b64encode(brut).decode('ascii')}"]

    def _connect_http(self, amont: socket.socket, requete: _Requete, fin: float) -> bytes:
        """`CONNECT` auprès d'un proxy HTTP. Rend les octets reçus après sa réponse (ils sont déjà ceux du tunnel)."""
        autorite = _autorite(requete.hote, requete.port)
        lignes = [f"CONNECT {autorite} HTTP/1.1", f"Host: {autorite}", *self._autorisation()]
        amont.sendall(("\r\n".join(lignes) + "\r\n\r\n").encode("ascii"))
        retour = _lire_tete(amont, fin)
        if retour is None:
            raise ConnectionError("le proxy de l'identité a fermé la connexion")
        tete, en_trop = retour
        if not 200 <= _statut(tete) < 300:  # 407, 403, 502… : tout refus d'un tunnel est un refus du proxy
            raise _AmontRefuse
        return en_trop

    def _connect_socks5(self, amont: socket.socket, requete: _Requete, fin: float) -> None:
        """Poignée de main SOCKS5 (RFC 1928, mot de passe RFC 1929). Un nom d'hôte part tel quel (type 3) : c'est le
        proxy qui le résout."""
        proxy = self._amont
        avec_identifiants = proxy.utilisateur is not None or proxy.mot_de_passe is not None
        methode = b"\x02" if avec_identifiants else b"\x00"
        amont.sendall(b"\x05\x01" + methode)
        version, choisie = _recevoir_exactement(amont, 2, fin)
        if version != 5:
            raise ConnectionError("réponse du proxy de l'identité illisible")
        if choisie != methode[0]:
            raise _AmontRefuse
        if avec_identifiants:
            utilisateur, mot_de_passe = (proxy.utilisateur or "").encode(), (proxy.mot_de_passe or "").encode()
            amont.sendall(b"\x01" + bytes([len(utilisateur)]) + utilisateur + bytes([len(mot_de_passe)]) + mot_de_passe)
            if _recevoir_exactement(amont, 2, fin)[1] != 0:
                raise _AmontRefuse
        amont.sendall(b"\x05\x01\x00" + _adresse_socks5(requete.hote) + requete.port.to_bytes(2, "big"))
        version, reponse, _, type_adresse = _recevoir_exactement(amont, 4, fin)
        if version != 5:
            raise ConnectionError("réponse du proxy de l'identité illisible")
        if reponse != 0:
            raise _AmontRefuse
        if type_adresse == 3:
            _recevoir_exactement(amont, _recevoir_exactement(amont, 1, fin)[0] + 2, fin)
        elif type_adresse in (1, 4):
            _recevoir_exactement(amont, (4 if type_adresse == 1 else 16) + 2, fin)
        else:
            raise ConnectionError("réponse du proxy de l'identité illisible")

    # ── Recopie des octets ─────────────────────────────────────────────

    def _aller(self, client: socket.socket, amont: socket.socket, initial: bytes) -> threading.Thread:
        fil = threading.Thread(target=self._recopier, args=(client, amont, initial), name="relais-aller", daemon=True)
        self._lancer(fil)
        return fil

    def _recopier(self, source: socket.socket, destination: socket.socket, initial: bytes = b"") -> None:
        """Recopie `source` vers `destination` jusqu'à la fin de `source`, puis ferme l'écriture de `destination` : le
        sens inverse continue (demi-fermeture). Un fil par sens, pour qu'un sens qui attend ne bloque jamais l'autre."""
        try:
            if initial:
                destination.sendall(initial)
            while donnees := source.recv(65536):
                destination.sendall(donnees)
        except OSError:  # coupure franche d'un côté : on coupe l'autre pour réveiller le sens inverse
            _couper(source)
            _couper(destination)
        else:
            _demi_fermer(destination)


def _adresse_socks5(hote: str) -> bytes:
    try:
        adresse = ipaddress.ip_address(hote)
    except ValueError:
        nom = hote.encode("ascii")  # `_hote_sur` n'a laissé passer que de l'ASCII
        return b"\x03" + bytes([len(nom)]) + nom  # 253 octets au plus
    return (b"\x01" if adresse.version == 4 else b"\x04") + adresse.packed
