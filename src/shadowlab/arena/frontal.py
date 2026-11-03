"""Frontal de l'Arena : termine TLS, observe le client tel qu'il arrive, puis relaie vers la chaîne de protection.

C'est le seul point qui voit le ClientHello et les en-têtes HTTP dans leur ordre et leur casse d'origine : les
mandataires suivants les réécrivent (Go, notamment, perd l'ordre). Il enregistre donc les observations lui-même, puis
retient les décisions que Nginx et Coraza lui renvoient dans des en-têtes internes, retirés avant de répondre au client.

Les en-têtes `X-ShadowLab-*` reçus d'un client sont supprimés : seul le frontal les pose, et il les signe.
"""

from __future__ import annotations

import base64
import http.client
import json
import logging
import socket
import socketserver
import ssl
import threading
from datetime import UTC, datetime, timedelta
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import h11

from .. import database as db
from ..config import Reglages
from . import secret as secrets_arena
from . import tls
from .profils import NIVEAUX

journal = logging.getLogger("shadowlab.frontal")

COOKIE_SESSION = "sl_session"
TAILLE_CORPS_MAX = 2 * 1024 * 1024
PROFIL_SANS_SESSION = "faible"
ENTETES_DE_SAUT = {"connection", "keep-alive", "proxy-connection", "te", "trailer", "transfer-encoding", "upgrade"}


def creer_certificat(dossier: Path) -> tuple[Path, Path]:
    """Certificat auto-signé pour `localhost`, créé une fois. Les moteurs sont réglés pour l'accepter."""
    cle_pem, cert_pem = dossier / "cle.pem", dossier / "cert.pem"
    if cle_pem.exists() and cert_pem.exists():
        return cle_pem, cert_pem
    import ipaddress

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    dossier.mkdir(parents=True, exist_ok=True)
    cle = ec.generate_private_key(ec.SECP256R1())
    nom = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "ShadowLab Arena (local)")])
    maintenant = datetime.now(UTC)
    certificat = (
        x509.CertificateBuilder()
        .subject_name(nom)
        .issuer_name(nom)
        .public_key(cle.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(maintenant - timedelta(days=1))
        .not_valid_after(maintenant + timedelta(days=825))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]),
            critical=False,
        )
        .sign(cle, hashes.SHA256())
    )
    cle_pem.touch(mode=0o600)
    cle_pem.write_bytes(
        cle.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    )
    cert_pem.write_bytes(certificat.public_bytes(serialization.Encoding.PEM))
    return cle_pem, cert_pem


def jeton_de(cible: str, entetes: list[tuple[str, str]]) -> str:
    """Même règle que le site : paramètre `sl` en priorité, sinon cookie de session."""
    valeurs = parse_qs(urlsplit(cible).query).get("sl")
    candidat = valeurs[0] if valeurs else ""
    if not candidat:
        for nom, valeur in entetes:
            if nom.lower() == "cookie":
                try:
                    morceau = SimpleCookie(valeur).get(COOKIE_SESSION)
                except Exception:  # cookie mal formé : pas de session
                    morceau = None
                if morceau is not None:
                    candidat = morceau.value
                    break
    return candidat if len(candidat) == 32 and all(c in "0123456789abcdef" for c in candidat) else ""


def noms_cookies(entetes: list[tuple[str, str]]) -> list[str]:
    noms: set[str] = set()
    for nom, valeur in entetes:
        if nom.lower() == "cookie":
            for morceau in valeur.split(";"):
                if "=" in morceau:
                    noms.add(morceau.split("=", 1)[0].strip())
    return sorted(noms)


def observable(chemin: str) -> bool:
    return chemin.startswith("/lab")


class _Connexion:
    """Une connexion client : une empreinte TLS, éventuellement plusieurs requêtes HTTP/1.1."""

    def __init__(self, serveur: Frontal, prise: ssl.SSLSocket, empreinte: dict, adresse: str) -> None:
        self.serveur, self.prise, self.empreinte, self.adresse = serveur, prise, empreinte, adresse
        self.tls_id: int | None = None
        self.h11 = h11.Connection(h11.SERVER)
        self.cx = db.ouvrir(serveur.reglages.base_donnees)

    def _recevoir(self) -> h11.Event | type[h11.PAUSED] | None:
        while True:
            evenement = self.h11.next_event()
            if evenement is not h11.NEED_DATA:
                return evenement
            try:
                donnees = self.prise.recv(65536)
            except (TimeoutError, OSError, ssl.SSLError):
                return None
            self.h11.receive_data(donnees)

    def boucle(self) -> None:
        try:
            while True:
                requete = self._recevoir()
                if requete is None or isinstance(requete, h11.ConnectionClosed | h11.PAUSED):
                    return
                if not isinstance(requete, h11.Request):
                    return
                corps = bytearray()
                while True:
                    evenement = self._recevoir()
                    if evenement is None:
                        return
                    if isinstance(evenement, h11.Data):
                        corps += evenement.data
                        if len(corps) > TAILLE_CORPS_MAX:
                            return
                    elif isinstance(evenement, h11.EndOfMessage):
                        break
                    else:
                        return
                self._traiter(requete, bytes(corps))
                if self.h11.our_state is h11.MUST_CLOSE or self.h11.their_state is h11.MUST_CLOSE:
                    return
                self.h11.start_next_cycle()
        except (h11.ProtocolError, OSError, ssl.SSLError) as erreur:
            journal.debug("connexion fermée : %s", erreur)
        finally:
            self.cx.close()

    def _traiter(self, requete: h11.Request, corps: bytes) -> None:
        cible = requete.target.decode("latin-1")
        chemin = urlsplit(cible).path
        methode = requete.method.decode("ascii")
        # `raw_items` : noms et ordre tels qu'envoyés par le client.
        entetes = [(n.decode("latin-1"), v.decode("latin-1")) for n, v in requete.headers.raw_items()]
        jeton = jeton_de(cible, entetes)
        profil = self.serveur.profil_de(self.cx, jeton)
        obs_id = self._observer(jeton, methode, chemin, requete, entetes) if jeton and observable(chemin) else None
        statut, reponse_entetes, reponse_corps = self._relayer(
            methode, cible, entetes, corps, jeton, profil, obs_id, chemin
        )
        if obs_id is not None:
            self.cx.execute("UPDATE observations_http SET status = ? WHERE id = ?", (statut, obs_id))
        sortie = [(n.encode("latin-1"), v.encode("latin-1")) for n, v in reponse_entetes]
        sortie.append((b"Content-Length", str(len(reponse_corps)).encode()))
        if b"close" in [v.lower() for n, v in requete.headers if n == b"connection"]:
            sortie.append((b"Connection", b"close"))
        self.prise.sendall(self.h11.send(h11.Response(status_code=statut, headers=sortie)))
        if methode != "HEAD" and reponse_corps:
            self.prise.sendall(self.h11.send(h11.Data(data=reponse_corps)))
        self.prise.sendall(self.h11.send(h11.EndOfMessage()))

    def _observer(self, jeton, methode, chemin, requete, entetes) -> int:
        if self.tls_id is None:
            curseur = self.cx.execute(
                "INSERT INTO observations_tls (received_at, ja3, ja3_hash, ja4, details) VALUES (?, ?, ?, ?, ?)",
                (
                    db.maintenant(),
                    self.empreinte["ja3"],
                    self.empreinte["ja3_hash"],
                    self.empreinte["ja4"],
                    db.j(self.empreinte["details"]),
                ),
            )
            self.tls_id = curseur.lastrowid
        curseur = self.cx.execute(
            "INSERT INTO observations_http (session_token, received_at, method, path, http_version, headers, cookies,"
            " tls_id, source) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'frontal')",
            (
                jeton,
                db.maintenant(),
                methode,
                chemin,
                requete.http_version.decode("ascii"),
                db.j([[n, v] for n, v in entetes]),
                db.j(noms_cookies(entetes)),
                self.tls_id,
            ),
        )
        return int(curseur.lastrowid)

    def _relayer(self, methode, cible, entetes, corps, jeton, profil, obs_id, chemin):
        reglages = self.serveur.reglages
        ja4 = self.empreinte["ja4"]
        obs = str(obs_id or 0)
        internes = [
            ("X-ShadowLab-Profil", profil),
            ("X-ShadowLab-Session", jeton),
            ("X-ShadowLab-Obs", obs),
            ("X-ShadowLab-JA4", ja4),
            ("X-ShadowLab-Amont", str(reglages.port)),
            ("X-ShadowLab-Sceau", secrets_arena.signer(self.serveur.secret, obs, profil, jeton, ja4)),
            ("X-Forwarded-For", self.adresse),
            ("X-Forwarded-Proto", "https"),
        ]
        conservees = [
            (n, v)
            for n, v in entetes
            if not n.lower().startswith("x-shadowlab-") and n.lower() not in (*ENTETES_DE_SAUT, "x-forwarded-for")
        ]
        if corps and not any(n.lower() == "content-length" for n, _ in conservees):
            conservees.append(("Content-Length", str(len(corps))))
        aval = http.client.HTTPConnection("127.0.0.1", self.serveur.port_aval, timeout=45)
        try:
            aval.putrequest(methode, cible, skip_host=True, skip_accept_encoding=True)
            for nom, valeur in (*conservees, *internes):
                aval.putheader(nom, valeur)
            aval.endheaders(corps or None)
            reponse = aval.getresponse()
            brut = reponse.read()
            statut, recus = reponse.status, reponse.getheaders()
        except OSError as erreur:
            journal.warning("chaîne de protection injoignable : %s", erreur)
            if jeton:
                db.enregistrer_decision(self.cx, jeton, "arena", "indisponible", chemin, [str(erreur)])
            return 502, [("Content-Type", "text/plain; charset=utf-8")], b"Arena indisponible\n"
        finally:
            aval.close()
        if jeton and observable(chemin):
            self._decisions(jeton, chemin, statut, recus)
        return (
            statut,
            [
                (n, v)
                for n, v in recus
                if not n.lower().startswith("x-shadowlab-") and n.lower() not in (*ENTETES_DE_SAUT, "content-length")
            ],
            brut,
        )

    def _decisions(self, jeton: str, chemin: str, statut: int, entetes: list[tuple[str, str]]) -> None:
        """Retient ce que Nginx et Coraza ont décidé pour cette requête."""
        valeurs = {n.lower(): v for n, v in entetes}
        limite = valeurs.get("x-shadowlab-limite", "")
        if limite:
            decision = "bloque" if limite == "REJECTED" else "passe"
            motifs = [{"code": f"statut_{limite.lower()}", "statut": statut}]
            if decision == "bloque":
                motifs[0]["description"] = "débit dépassé pour cette session (limit_req)"
            db.enregistrer_decision(self.cx, jeton, "limitation", decision, chemin, motifs)
        waf = valeurs.get("x-shadowlab-waf", "")
        if waf:
            try:
                d = json.loads(base64.b64decode(waf))
            except ValueError:
                db.enregistrer_decision(self.cx, jeton, "waf", "illisible", chemin)
                return
            motifs = [{"score": d.get("score", 0)}, *d.get("regles", [])]
            db.enregistrer_decision(self.cx, jeton, "waf", d.get("decision", "inconnue"), chemin, motifs)


class _Gestion(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        serveur: Frontal = self.server.frontal
        prise: socket.socket = self.request
        prise.settimeout(30)
        try:
            hello = tls.analyser(tls.lire_client_hello(prise))
        except (tls.TlsIllisible, OSError) as erreur:
            journal.debug("ClientHello illisible : %s", erreur)
            return
        try:
            flux = serveur.contexte.wrap_socket(prise, server_side=True)
        except (ssl.SSLError, OSError) as erreur:
            journal.debug("poignée de main refusée : %s", erreur)
            return
        _Connexion(serveur, flux, tls.empreinte(hello), self.client_address[0]).boucle()


class _Serveur(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True
    request_queue_size = 128


class Frontal:
    def __init__(self, reglages: Reglages, port_aval: int | None = None) -> None:
        self.reglages = reglages
        self.port_aval = port_aval or reglages.port_aval
        self.secret = secrets_arena.charger(reglages.dossier_arena)
        cle, certificat = creer_certificat(reglages.dossier_arena / "tls")
        self.contexte = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.contexte.load_cert_chain(certificat, cle)
        self.contexte.set_alpn_protocols(["http/1.1"])  # h11 ne parle que HTTP/1.1 : voir les limites de l'Arena
        self._profils: dict[str, str] = {}
        self._verrou = threading.Lock()
        self._serveur: _Serveur | None = None

    def profil_de(self, cx, jeton: str) -> str:
        if not jeton:
            return PROFIL_SANS_SESSION
        with self._verrou:
            connu = self._profils.get(jeton)
        if connu:
            return connu
        ligne = cx.execute("SELECT protection FROM runs WHERE session_token = ?", (jeton,)).fetchone()
        profil = ligne["protection"] if ligne and ligne["protection"] in NIVEAUX else PROFIL_SANS_SESSION
        if ligne:
            with self._verrou:
                if len(self._profils) > 50_000:
                    self._profils.clear()
                self._profils[jeton] = profil
        return profil

    def demarrer(self) -> None:
        self._serveur = _Serveur(("127.0.0.1", self.reglages.port_arena), _Gestion)
        self._serveur.frontal = self
        threading.Thread(target=self._serveur.serve_forever, daemon=True, name="frontal-arena").start()
        journal.info("frontal de l'Arena sur %s", self.reglages.url_arena)

    def arreter(self) -> None:
        if self._serveur is not None:
            self._serveur.shutdown()
            self._serveur.server_close()
            self._serveur = None
