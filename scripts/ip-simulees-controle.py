"""Contrôle d'un en-tête d'adresse forgé devant la vraie chaîne de l'Arena (4.1, D-105).

    SHADOWLAB_PORT=… SHADOWLAB_PORT_ARENA=… SHADOWLAB_ARENA_PROXY_PROTOCOLE=1 uv run python <ce fichier>

Le frontal et le site de ce dossier de travail doivent tourner (par exemple pendant ou après la campagne, sous le même
jeu de ports). Trois clients TLS directs, chacun avec une nouvelle session :
- « forge » : envoie X-Forwarded-For, X-Real-IP, Forwarded et X-ShadowLab-Adresse forgés, sans en-tête PROXY ;
- « proxy » : envoie en plus un en-tête PROXY v1 déclarant 192.0.2.44 ;
- « simple » : rien de forgé, rien de simulé.
Puis lit, dans la base du dossier, l'adresse notée sur la visite de chaque session. Attendu : forge et simple notés
127.0.0.1 (la vraie adresse du pair), proxy noté 192.0.2.44 (jamais l'adresse forgée). Code 0 si tout est conforme.
"""

from __future__ import annotations

import secrets
import socket
import ssl
import sys
import time

from shadowlab import database as db
from shadowlab.config import charger

FORGES = (
    "X-Forwarded-For: 192.0.2.66\r\nX-Real-IP: 192.0.2.67\r\nForwarded: for=192.0.2.68\r\n"
    "X-ShadowLab-Adresse: 192.0.2.69\r\nX-ShadowLab-Adresse-Sceau: forge\r\n"
)


def requete(port: int, avant: bytes, entetes_en_plus: str) -> tuple[str, int | None]:
    jeton = secrets.token_hex(16)
    contexte = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)  # certificat auto-signé de notre Arena locale
    contexte.check_hostname = False
    contexte.verify_mode = ssl.CERT_NONE
    statut = None
    with socket.create_connection(("127.0.0.1", port), timeout=10) as brut:
        if avant:
            brut.sendall(avant)
        with contexte.wrap_socket(brut, server_hostname="localhost") as flux:
            flux.sendall(
                f"GET /lab/?sl={jeton} HTTP/1.1\r\nHost: localhost\r\n{entetes_en_plus}"
                "Connection: close\r\n\r\n".encode()
            )
            debut = flux.recv(64)
            statut = int(debut.split()[1]) if debut.startswith(b"HTTP/") else None
    return jeton, statut


def main() -> int:
    reglages = charger()
    if not reglages.proxy_protocole:
        print("SHADOWLAB_ARENA_PROXY_PROTOCOLE=1 est exigé (le frontal doit l'avoir aussi).", file=sys.stderr)
        return 2
    clients = {
        "forge": (b"", FORGES, "127.0.0.1"),
        "proxy": (b"PROXY TCP4 192.0.2.44 127.0.0.1 40000 %d\r\n" % reglages.port_arena, FORGES, "192.0.2.44"),
        "simple": (b"", "", "127.0.0.1"),
    }
    jetons = {nom: requete(reglages.port_arena, avant, plus) for nom, (avant, plus, _) in clients.items()}
    time.sleep(1)  # la visite s'écrit après la réponse
    cx = db.ouvrir(reglages.base_donnees)
    conforme = True
    for nom, (jeton, statut) in jetons.items():
        ligne = cx.execute("SELECT adresse FROM visites WHERE session_token = ?", (jeton,)).fetchone()
        note = ligne["adresse"] if ligne else None
        attendu = clients[nom][2]
        ok = note == attendu
        conforme &= ok
        print(f"{nom:7} statut {statut}  adresse notée {note}  attendue {attendu}  {'OK' if ok else 'ECART'}")
    cx.close()
    return 0 if conforme else 1


if __name__ == "__main__":
    raise SystemExit(main())
