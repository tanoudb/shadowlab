"""Les aides de `outils_proxy.py` contre elles-mêmes : faux proxys HTTP et SOCKS5, cible, écoute STUN, `proxy.json`.

Aucun code du relais : de `src/`, ces tests n'utilisent que le certificat jetable (`arena.frontal.creer_certificat`).
Ils prouvent que les mesures des autres fichiers (le port source que la cible voit, les refus d'authentification, les
connexions notées) sont justes avant de s'y fier.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import socket
import ssl
import subprocess
import sys
import threading
import time

import pytest
from outils_proxy import (
    AmontMuet,
    CibleDeTest,
    Echantillonneur,
    EcouteStunDeTest,
    ProxyHttpDeTest,
    ProxySocks5DeTest,
    attendre,
    client_socks5,
    echanger,
    ecrire_proxy,
    get_absolu,
    get_dans_le_tunnel,
    get_direct,
    lire_jusqu_a_fin,
    lire_reponse,
    ouvrir_connexion,
    ouvrir_tunnel,
    port_ferme,
    statut_de,
)

from shadowlab.arena.frontal import creer_certificat

BASIC_BON = "Proxy-Authorization: Basic " + base64.b64encode(b"bon-user:bon-mdp").decode() + "\r\n"
BASIC_FAUX = "Proxy-Authorization: Basic " + base64.b64encode(b"bon-user:faux-mdp").decode() + "\r\n"


@pytest.fixture
def cible():
    with CibleDeTest() as c:
        yield c


@pytest.fixture
def proxy_http():
    with ProxyHttpDeTest("bon-user", "bon-mdp", noms_connus={"cible-dns.test": "127.0.0.1"}) as p:
        yield p


@pytest.fixture
def proxy_socks():
    with ProxySocks5DeTest("bon-user", "bon-mdp", noms_connus={"cible-dns.test": "127.0.0.1"}) as p:
        yield p


# ── Faux proxy HTTP ────────────────────────────────────────────────────────


def test_proxy_http_adresse_et_nom(proxy_http):
    assert proxy_http.adresse == f"http://127.0.0.1:{proxy_http.port}"
    assert proxy_http.nom == "A" and proxy_http.connexions == [] and proxy_http.refus == 0


def test_proxy_http_connect_transmet_et_note_le_port_source_que_la_cible_voit(cible, proxy_http):
    statut, _, sock = ouvrir_tunnel(proxy_http.port, "127.0.0.1", cible.port, entetes=BASIC_BON)
    assert statut == 200
    with sock:
        reponse = get_dans_le_tunnel(sock, "127.0.0.1", cible.port, "/page?id=A")
    statut_page, _, corps = lire_reponse(reponse)
    assert statut_page == 200 and b"/img.png?id=A" in corps
    assert len(proxy_http.connexions) == 1
    entree = proxy_http.connexions[0]
    assert (entree["methode"], entree["hote"], entree["port"]) == ("CONNECT", "127.0.0.1", cible.port)
    # LA mesure des autres fichiers : le port source noté par le proxy est celui que la cible a vu.
    assert cible.connexions_recues == [entree["port_source"]]
    assert [r["port_source"] for r in cible.requetes] == [entree["port_source"]]


@pytest.mark.parametrize(
    "entetes", ["", BASIC_FAUX, "Proxy-Authorization: Bearer abc\r\n", "Proxy-Authorization: Basic ?\r\n"]
)
def test_proxy_http_refuse_sans_les_bons_identifiants_avec_407(cible, proxy_http, entetes):
    statut, tete, sock = ouvrir_tunnel(proxy_http.port, "127.0.0.1", cible.port, entetes=entetes)
    sock.close()
    assert statut == 407 and b"Proxy-Authenticate" in tete
    assert proxy_http.refus == 1 and proxy_http.connexions == []
    time.sleep(0.2)
    assert cible.connexions_recues == [], "aucune connexion ouverte vers la cible"


def test_proxy_http_requete_absolue_reecrite_en_forme_d_origine_sans_les_identifiants(cible, proxy_http):
    url = cible.url("/page?id=A")
    reponse = get_absolu(proxy_http.port, url, entetes=BASIC_BON + "Connection: close\r\n")
    statut, _, corps = lire_reponse(reponse)
    assert statut == 200 and b"/xhr?id=A" in corps
    (requete,) = [r for r in cible.requetes if r["chemin"].startswith("/page")]
    assert requete["chemin"] == "/page?id=A", "la cible reçoit la forme d'origine, pas l'adresse complète"
    assert "proxy-authorization" not in requete["entetes"], "les identifiants du proxy ne vont pas jusqu'à la cible"
    assert requete["entetes"]["connection"] == "close"
    (entree,) = proxy_http.connexions
    assert entree["methode"] == "GET" and entree["port_source"] == requete["port_source"]


def test_proxy_http_requete_absolue_sans_identifiants_407(cible, proxy_http):
    reponse = get_absolu(proxy_http.port, cible.url("/page?id=A"))
    assert statut_de(reponse) == 407 and proxy_http.refus == 1 and proxy_http.connexions == []
    assert cible.connexions_recues == []


def test_proxy_http_noms_que_seul_le_proxy_connait(cible, proxy_http):
    statut, _, sock = ouvrir_tunnel(proxy_http.port, "cible-dns.test", cible.port, entetes=BASIC_BON)
    assert statut == 200
    sock.close()
    assert (
        proxy_http.connexions[0]["hote"] == "cible-dns.test"
    )  # le nom est noté tel quel : personne ne l'a résolu avant
    statut, _, sock = ouvrir_tunnel(proxy_http.port, "inconnu.test", cible.port, entetes=BASIC_BON)
    sock.close()
    assert statut == 502 and len(proxy_http.connexions) == 1, "un nom inconnu : 502, aucune connexion, pas de vrai DNS"


def test_proxy_http_localhost_et_ip_passent_cible_fermee_donne_502(cible, proxy_http):
    for hote in ("localhost", "127.0.0.1"):
        statut, _, sock = ouvrir_tunnel(proxy_http.port, hote, cible.port, entetes=BASIC_BON)
        sock.close()
        assert statut == 200, hote
    statut, _, sock = ouvrir_tunnel(proxy_http.port, "127.0.0.1", port_ferme(), entetes=BASIC_BON)
    sock.close()
    assert statut == 502 and len(proxy_http.connexions) == 2


def test_proxy_http_gros_corps_arrive_en_entier(cible, proxy_http):
    _, _, sock = ouvrir_tunnel(proxy_http.port, "127.0.0.1", cible.port, entetes=BASIC_BON)
    with sock:
        reponse = get_dans_le_tunnel(sock, "127.0.0.1", cible.port, "/gros?n=600000")
    statut, entetes, corps = lire_reponse(reponse)
    assert statut == 200 and len(corps) == 600000 == int(entetes["content-length"])
    assert corps[:5] == bytes(range(5)) and corps[-1] == (600000 - 1) % 251


def test_proxy_http_compte_les_contacts_meme_muets(proxy_http):
    assert proxy_http.contacts == 0
    muet = ouvrir_connexion(proxy_http.port)
    assert attendre(lambda: proxy_http.contacts == 1)
    muet.close()
    assert proxy_http.refus == 0 and proxy_http.connexions == []


# ── Faux proxy SOCKS5 ──────────────────────────────────────────────────────


def test_proxy_socks5_adresse(proxy_socks):
    assert proxy_socks.adresse == f"socks5://127.0.0.1:{proxy_socks.port}"
    assert proxy_socks.nom == "B"


@pytest.mark.parametrize("domaine", [True, False], ids=["nom_de_domaine", "ipv4"])
def test_proxy_socks5_transmet_et_note_le_port_source_que_la_cible_voit(cible, proxy_socks, domaine):
    hote = "cible-dns.test" if domaine else "127.0.0.1"
    code, sock = client_socks5(proxy_socks.port, "bon-user", "bon-mdp", hote, cible.port, domaine=domaine)
    assert code == 0 and sock is not None
    with sock:
        reponse = get_dans_le_tunnel(sock, "127.0.0.1", cible.port, "/page?id=B")
    assert statut_de(reponse) == 200
    (entree,) = proxy_socks.connexions
    assert (entree["methode"], entree["hote"], entree["port"]) == ("SOCKS5", hote, cible.port)
    assert cible.connexions_recues == [entree["port_source"]]


@pytest.mark.parametrize("utilisateur,mot_de_passe", [("bon-user", "faux-mdp"), ("faux-user", "bon-mdp")])
def test_proxy_socks5_mauvais_identifiants_echec_rfc1929_puis_fermeture(cible, proxy_socks, utilisateur, mot_de_passe):
    code, sock = client_socks5(proxy_socks.port, utilisateur, mot_de_passe, "127.0.0.1", cible.port)
    assert (code, sock) == (0x100, None), "réponse d'échec `01 01` de la RFC 1929"
    assert proxy_socks.refus == 1 and proxy_socks.connexions == []
    time.sleep(0.2)
    assert cible.connexions_recues == []


def test_proxy_socks5_nom_inconnu_et_cible_fermee_hote_injoignable(cible, proxy_socks):
    assert client_socks5(proxy_socks.port, "bon-user", "bon-mdp", "inconnu.test", cible.port) == (4, None)
    assert client_socks5(proxy_socks.port, "bon-user", "bon-mdp", "127.0.0.1", port_ferme(), domaine=False) == (4, None)
    assert proxy_socks.connexions == [] and proxy_socks.refus == 0


def test_proxy_socks5_refuse_une_salutation_sans_mot_de_passe(proxy_socks):
    with ouvrir_connexion(proxy_socks.port) as sock:
        sock.sendall(b"\x05\x01\x00")  # « aucune authentification » seulement
        assert sock.recv(2) == b"\x05\xff"


# ── La cible ───────────────────────────────────────────────────────────────


def test_les_faux_proxys_notent_les_octets_que_leur_client_envoie_vers_la_cible(cible, proxy_http, proxy_socks):
    reponse = get_absolu(proxy_http.port, cible.url("/page?id=O"), entetes=BASIC_BON + "Connection: close\r\n")
    assert statut_de(reponse) == 200
    assert attendre(lambda: proxy_http.octets_du_client.count(b" HTTP/1.1\r\n") == 1)
    assert proxy_http.octets_du_client.startswith(b"GET /page?id=O HTTP/1.1\r\n"), (
        "forme d'origine, comme la cible la voit"
    )
    code, sock = client_socks5(proxy_socks.port, "bon-user", "bon-mdp", "127.0.0.1", cible.port)
    assert code == 0 and sock is not None
    with sock:
        get_dans_le_tunnel(sock, "127.0.0.1", cible.port, "/page?id=O2")
    assert attendre(lambda: proxy_socks.octets_du_client.count(b" HTTP/1.1\r\n") == 1)
    assert proxy_socks.octets_du_client.startswith(b"GET /page?id=O2 HTTP/1.1\r\n")
    assert proxy_http.refus == 0 and proxy_socks.refus == 0


def test_cible_sert_la_page_avec_image_script_et_appel_de_donnees(cible):
    statut, entetes, corps = lire_reponse(get_direct(cible.port, "/page?id=X-1"))
    assert statut == 200 and entetes["content-type"].startswith("text/html")
    texte = corps.decode()
    assert '<img src="/img.png?id=X-1"' in texte and '<script src="/s.js?id=X-1">' in texte
    assert "fetch('/xhr?id=X-1')" in texte and "'fini'" in texte
    for chemin, type_attendu in (
        ("/img.png", "image/png"),
        ("/s.js", "application/javascript"),
        ("/xhr", "text/plain"),
    ):
        statut, entetes, _ = lire_reponse(get_direct(cible.port, chemin + "?id=X-1"))
        assert (statut, entetes["content-type"]) == (200, type_attendu), chemin


def test_cible_refuse_un_identifiant_exotique_dans_la_page(cible):
    corps = lire_reponse(get_direct(cible.port, "/page?id=a'%3E%3Cscript%3E"))[2].decode()
    assert "<script>" not in corps.split("<script>", 1)[0] and "id=?" in corps


def test_cible_inconnu_404_racine_marquee_et_gros(cible):
    assert lire_reponse(get_direct(cible.port, "/favicon.ico"))[0] == 404
    assert b"cible-atteinte" in lire_reponse(get_direct(cible.port, "/"))[2]
    assert len(lire_reponse(get_direct(cible.port, "/gros?n=12345"))[2]) == 12345


def test_cible_redirige_dehors_vers_localhost_sur_le_port_de_cible2():
    with CibleDeTest() as cible2, CibleDeTest(cible2=cible2) as cible:
        statut, entetes, _ = lire_reponse(get_direct(cible.port, "/redirige-dehors"))
        assert statut == 302 and entetes["location"] == f"http://localhost:{cible2.port}/"
        assert cible2.connexions_recues == [], "elle n'a rien reçu : seule la cible 1 a été jointe"
    with CibleDeTest() as seule:
        assert lire_reponse(get_direct(seule.port, "/redirige-dehors"))[0] == 404


def test_cible_recoit_un_corps_post_en_entier_et_le_note(cible):
    corps = bytes(i % 251 for i in range(70_000))
    requete = f"POST /depot?id=D HTTP/1.1\r\nHost: x\r\nContent-Length: {len(corps)}\r\nConnection: close\r\n\r\n"
    with ouvrir_connexion(cible.port) as sock:
        sock.sendall(requete.encode() + corps)
        statut, _, reponse = lire_reponse(lire_jusqu_a_fin(sock))
    assert statut == 200 and reponse == f"recu={len(corps)} sha256={hashlib.sha256(corps).hexdigest()}".encode()
    assert cible.corps_recus == [("/depot?id=D", corps)]
    assert [r["chemin"] for r in cible.requetes] == ["/depot?id=D"], "le POST est aussi une requête notée"


def test_cible_en_tls_sert_en_https_et_redirige_vers_l_autre_en_https(tmp_path):
    cle, cert = creer_certificat(tmp_path)
    contexte = ssl.create_default_context(cafile=str(cert))
    with CibleDeTest(tls=(cle, cert)) as cible2, CibleDeTest(cible2=cible2, tls=(cle, cert)) as cible:
        assert cible.url("/page?id=T").startswith("https://127.0.0.1:") and cible2.schema == "https"
        with ouvrir_connexion(cible.port) as brut, contexte.wrap_socket(brut, server_hostname="127.0.0.1") as sock:
            sock.sendall(b"GET /redirige-dehors HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n")
            statut, entetes, _ = lire_reponse(lire_jusqu_a_fin(sock))
        assert statut == 302 and entetes["location"] == f"https://localhost:{cible2.port}/"
        assert cible.connexions_recues == [cible.requetes[0]["port_source"]], "le port source vu est celui du client"
        assert CibleDeTest().schema == "http"


def test_cible_en_tls_une_connexion_qui_ne_parle_pas_tls_ne_bloque_pas_les_autres(tmp_path):
    cle, cert = creer_certificat(tmp_path)
    contexte = ssl.create_default_context(cafile=str(cert))
    with CibleDeTest(tls=(cle, cert)) as cible:
        muet = ouvrir_connexion(cible.port)  # Chrome ouvre des connexions d'avance et ne dit rien : elles ne gênent pas
        try:
            with ouvrir_connexion(cible.port) as brut, contexte.wrap_socket(brut, server_hostname="127.0.0.1") as sock:
                sock.sendall(b"GET / HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n")
                assert statut_de(lire_jusqu_a_fin(sock)) == 200
        finally:
            muet.close()


def test_cible_webrtc_annonce_le_port_udp():
    with EcouteStunDeTest() as stun, CibleDeTest(port_stun=stun.port) as cible:
        corps = lire_reponse(get_direct(cible.port, "/webrtc"))[2].decode()
    assert f"stun:127.0.0.1:{stun.port}" in corps
    for morceau in ("RTCPeerConnection", "createDataChannel", "createOffer", "setLocalDescription", "3000"):
        assert morceau in corps


def test_cible_note_la_connexion_a_l_acceptation_pas_a_la_requete(cible):
    sock = socket.create_connection(("127.0.0.1", cible.port))
    try:
        assert attendre(lambda: len(cible.connexions_recues) == 1), "une connexion qui ne dit rien compte"
        assert cible.connexions_recues == [sock.getsockname()[1]] and cible.requetes == []
    finally:
        sock.close()


def test_cible_une_connexion_persistante_garde_son_port_source(cible):
    with ouvrir_connexion(cible.port) as sock:
        port_local = sock.getsockname()[1]
        for chemin in ("/page?id=P", "/img.png?id=P", "/s.js?id=P"):
            sock.sendall(f"GET {chemin} HTTP/1.1\r\nHost: x\r\n\r\n".encode())
            time.sleep(0.1)
        assert attendre(lambda: len(cible.requetes_de("P")) == 3)
    assert {r["port_source"] for r in cible.requetes_de("P")} == {port_local}
    assert cible.connexions_recues == [port_local]


def test_cible_requetes_de_ne_prend_que_l_identifiant_exact(cible):
    for identifiant in ("A", "AB", "dns-A"):
        get_direct(cible.port, f"/page?id={identifiant}")
    assert [r["chemin"] for r in cible.requetes_de("A")] == ["/page?id=A"]
    assert [r["chemin"] for r in cible.requetes_de("dns-A")] == ["/page?id=dns-A"]


def test_cible_delai_de_l_appel_de_donnees():
    with CibleDeTest(delai_xhr_s=0.4) as cible:
        debut = time.monotonic()
        assert lire_reponse(get_direct(cible.port, "/xhr?id=D"))[0] == 200
        assert time.monotonic() - debut >= 0.4


# ── Écoute STUN, amont muet, proxy.json ─────────────────────────────────────


def test_ecoute_stun_compte_les_paquets_udp():
    with EcouteStunDeTest() as stun:
        assert stun.paquets == 0
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as emetteur:
            for _ in range(3):
                emetteur.sendto(b"\x00\x01", ("127.0.0.1", stun.port))
        assert attendre(lambda: stun.paquets == 3)
        assert len(stun.sources) == 3


def test_amont_muet_accepte_et_ne_dit_rien():
    with AmontMuet() as muet:
        sock = ouvrir_connexion(muet.port, delai_s=0.5)
        with pytest.raises(TimeoutError):
            sock.recv(10)
        sock.close()
        assert muet.adresse == f"http://127.0.0.1:{muet.port}"


def test_ecrire_proxy_dossier_0700_fichier_0600_contenu_relu(tmp_path):
    ancien = os.umask(0o000)  # un umask permissif ne doit rien changer : `chmod` explicite
    try:
        chemin = ecrire_proxy(tmp_path / "ids", "a", "http://h:3128", "u", "secret")
    finally:
        os.umask(ancien)
    assert chemin == tmp_path / "ids" / "a" / "proxy.json"
    assert chemin.stat().st_mode & 0o777 == 0o600 and chemin.parent.stat().st_mode & 0o777 == 0o700
    assert json.loads(chemin.read_text(encoding="utf-8")) == {
        "serveur": "http://h:3128",
        "utilisateur": "u",
        "mot_de_passe": "secret",
    }


def test_ecrire_proxy_sans_identifiants_mode_choisi_et_texte_brut(tmp_path):
    chemin = ecrire_proxy(tmp_path, "a", "socks5://h:1080")
    assert json.loads(chemin.read_text(encoding="utf-8")) == {"serveur": "socks5://h:1080"}
    chemin = ecrire_proxy(tmp_path, "a", "http://h:1", "u", "p", mode=0o644)
    assert chemin.stat().st_mode & 0o777 == 0o644, "même sur un fichier existant, le mode demandé est appliqué"
    chemin = ecrire_proxy(tmp_path, "a", "", brut="{pas du json")
    assert chemin.read_text(encoding="utf-8") == "{pas du json" and chemin.stat().st_mode & 0o777 == 0o600


# ── Arrêt propre ───────────────────────────────────────────────────────────


def test_arret_propre_ferme_les_ports_et_ne_laisse_aucun_fil():
    avant = set(threading.enumerate())
    cible, stun = CibleDeTest(), EcouteStunDeTest()
    proxy, socks = ProxyHttpDeTest("u", "p"), ProxySocks5DeTest("u", "p")
    ports = [cible.port, proxy.port, socks.port]
    for objet in (cible, proxy, socks, stun):
        objet.demarrer()
    # Un tunnel ouvert et resté ouvert, et une connexion muette : `arreter` doit tout fermer.
    _, _, tunnel = ouvrir_tunnel(proxy.port, "127.0.0.1", cible.port, entetes="Proxy-Authorization: Basic dTpw\r\n")
    muet = ouvrir_connexion(socks.port)
    assert attendre(lambda: socks.contacts == 1 and len(cible.connexions_recues) == 1)
    for objet in (cible, proxy, socks, stun):
        objet.arreter()
    try:
        # Les clients n'ont encore rien fermé : c'est `arreter` qui a tout fermé.
        assert attendre(lambda: not [f for f in set(threading.enumerate()) - avant if f.is_alive()]), [
            f.name for f in set(threading.enumerate()) - avant if f.is_alive()
        ]
        for port in ports:
            with pytest.raises(ConnectionRefusedError):
                socket.create_connection(("127.0.0.1", port), timeout=1)
    finally:
        tunnel.close()
        muet.close()


def test_contexte_with_demarre_et_arrete(cible):
    with ProxyHttpDeTest("u", "p") as proxy:
        assert echanger(proxy.port, b"x\r\n\r\n") == b"", "il écoute (puis ferme sur une requête qu'il ne comprend pas)"
    with pytest.raises(ConnectionRefusedError):
        socket.create_connection(("127.0.0.1", proxy.port), timeout=1)


# ── Échantillonneur de sockets (psutil) : contre un faux « Chrome » ──────────


FAUX_ENFANT = (
    "import socket,sys,time\n"
    "t=socket.create_connection(('127.0.0.1',int(sys.argv[2])))\n"
    "u=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);u.bind(('127.0.0.1',0))\n"
    "time.sleep(30)\n"
)
FAUX_CHROME = (
    "import socket,subprocess,sys,time\n"
    "a=socket.create_connection(('127.0.0.1',int(sys.argv[2])))\n"
    "b=socket.create_connection(('127.0.0.1',int(sys.argv[3])))\n"
    "enfant=subprocess.Popen([sys.executable,'-c',sys.argv[4],'--type=renderer',sys.argv[3],sys.argv[3]])\n"
    "print('pret',flush=True)\n"
    "time.sleep(30)\n"
)


def test_echantillonneur_retrouve_le_processus_principal_et_classe_les_connexions(tmp_path):
    with CibleDeTest() as relais, CibleDeTest() as ailleurs:
        profil = tmp_path / "identite-x" / "chrome"
        profil.mkdir(parents=True)
        faux = subprocess.Popen(
            [
                sys.executable,
                "-c",
                FAUX_CHROME,
                f"--user-data-dir={profil}",
                str(relais.port),
                str(ailleurs.port),
                FAUX_ENFANT,
            ],
            stdout=subprocess.PIPE,
            text=True,
        )
        try:
            assert faux.stdout.readline().strip() == "pret"
            echantillonneur = Echantillonneur("identite-x", relais.port)
            echantillonneur.start()
            attendre(lambda: echantillonneur.vers_le_relais and echantillonneur.interdites and echantillonneur.udp)
            echantillonneur.arreter()
        finally:
            faux.kill()
            faux.wait(timeout=5)
    assert echantillonneur.echantillons > 0 and echantillonneur.acces_refuses == 0
    assert echantillonneur.vers_le_relais >= 1, "la connexion vers le port du relais est comptée, pas interdite"
    destinations = {destination for _, destination, _ in echantillonneur.interdites}
    assert destinations == {("127.0.0.1", ailleurs.port)}, "deux processus (le principal et son enfant) vont ailleurs"
    assert any(statut == "ESTABLISHED" for _, _, statut in echantillonneur.interdites)
    assert echantillonneur.udp, "le socket UDP de l'enfant est vu, sans rien interdire"
    assert any("--user-data-dir=" in ligne and "identite-x" in ligne for ligne in echantillonneur.lignes_de_commande), (
        "les lignes de commande des descendants sont relevées"
    )


def test_echantillonneur_sans_chrome_de_cette_identite_n_echantillonne_rien(tmp_path):
    echantillonneur = Echantillonneur("identite-absente", 1)
    echantillonneur.start()
    time.sleep(0.5)
    echantillonneur.arreter()
    assert echantillonneur.echantillons == 0 and not echantillonneur.interdites
