"""Sonde jetable (hors dépôt) : cas que les tests écrits ne couvrent pas."""
import socket, sys, threading, time
sys.path.insert(0, "tests"); sys.path.insert(0, "src")
from outils_proxy import ProxyHttpDeTest, ProxySocks5DeTest, ouvrir_connexion, lire_jusqu_a_fin, statut_de, lire_reponse, lire_tete
from shadowlab.engines.noezia.proxy_identite import RelaisProxy, analyser

class Origine:
    """Serveur brut : lit tout le corps (Content-Length) AVANT de répondre ; selon le chemin : 403, keep-alive, écho."""
    def __init__(self):
        self.s = socket.socket(); self.s.bind(("127.0.0.1", 0)); self.s.listen(8); self.port = self.s.getsockname()[1]
        threading.Thread(target=self.run, daemon=True).start()
    def run(self):
        while True:
            try: c, _ = self.s.accept()
            except OSError: return
            threading.Thread(target=self.servir, args=(c,), daemon=True).start()
    def servir(self, c):
        tete, reste = lire_tete(c)
        lignes = tete.decode().split("\r\n"); chemin = lignes[0].split(" ")[1]
        h = {n.lower(): v.strip() for n, _, v in (l.partition(":") for l in lignes[1:])}
        n = int(h.get("content-length", 0)); corps = reste
        while len(corps) < n: corps += c.recv(65536)
        if chemin == "/403": rep = b"HTTP/1.1 403 Forbidden\r\nContent-Length: 4\r\n\r\nnope"
        elif chemin == "/ka": rep = b"HTTP/1.1 200 OK\r\nConnection: keep-alive\r\nKeep-Alive: timeout=5\r\nContent-Length: 2\r\n\r\nok"
        else: rep = b"HTTP/1.1 200 OK\r\nContent-Length: " + str(len(corps)).encode() + b"\r\n\r\n" + corps
        c.sendall(rep); time.sleep(0.3); c.close()

o = Origine()
for nom, faux in (("http", ProxyHttpDeTest), ("socks5", ProxySocks5DeTest)):
    with faux("u", "p") as px, RelaisProxy(analyser(px.adresse, "u", "p"), ("127.0.0.1",)) as r:
        port = int(r.adresse.rsplit(":", 1)[1])
        corps = bytes(i % 251 for i in range(300_000))
        req = f"POST http://127.0.0.1:{o.port}/echo HTTP/1.1\r\nHost: 127.0.0.1:{o.port}\r\nContent-Length: {len(corps)}\r\nProxy-Connection: keep-alive\r\n\r\n".encode() + corps
        t = time.monotonic()
        with ouvrir_connexion(port) as sock:
            sock.sendall(req); rep = lire_jusqu_a_fin(sock, 10)
        st, h, b = lire_reponse(rep)
        print(f"[{nom}] POST 300 Ko : statut {st}, corps identique {b == corps}, {time.monotonic()-t:.2f}s")
        for chemin in ("/403", "/ka"):
            with ouvrir_connexion(port) as sock:
                sock.sendall(f"GET http://127.0.0.1:{o.port}{chemin} HTTP/1.1\r\nHost: x\r\n\r\n".encode()); rep = lire_jusqu_a_fin(sock, 10)
            st, h, b = lire_reponse(rep)
            print(f"[{nom}] {chemin} : statut {st}, connection={h.get('connection')}, keep-alive={h.get('keep-alive')}, corps={b!r}")
        print(f"[{nom}] demandes :", [tuple(d) for d in r.demandes])

# IPv6 par CONNECT
srv = socket.socket(socket.AF_INET6); srv.bind(("::1", 0)); srv.listen(1); p6 = srv.getsockname()[1]
def un():
    c, _ = srv.accept(); c.sendall(b"salut-v6"); c.close()
threading.Thread(target=un, daemon=True).start()
with ProxySocks5DeTest("u", "p") as px, RelaisProxy(analyser(px.adresse, "u", "p"), ("::1",)) as r:
    port = int(r.adresse.rsplit(":", 1)[1])
    with ouvrir_connexion(port) as sock:
        sock.sendall(f"CONNECT [::1]:{p6} HTTP/1.1\r\nHost: x\r\n\r\n".encode())
        tete, reste = lire_tete(sock)
        print("[ipv6 socks5] CONNECT :", statut_de(tete), reste or sock.recv(100))
    print("[ipv6] demandes :", [tuple(d) for d in r.demandes])
print(repr(analyser("http://[::1]:3128", "u", "p")))
r = RelaisProxy(analyser("http://h:1"), ("*",)); r.arreter(); r.arreter(); print("arreter sans demarrer + deux fois : ok")
