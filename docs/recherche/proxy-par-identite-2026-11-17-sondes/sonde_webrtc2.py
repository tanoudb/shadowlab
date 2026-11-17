"""Sonde jetable (hors dépôt) : STUN sur l'adresse du réseau local (pas le bouclage)."""
import socket, sys, tempfile, threading, time
sys.path.insert(0, "tests"); sys.path.insert(0, "src")
from outils_proxy import ProxyHttpDeTest
from patchright.sync_api import sync_playwright
from shadowlab.engines.noezia.proxy_identite import RelaisProxy, analyser

LAN = sys.argv[2]
POL = "--webrtc-ip-handling-policy=disable_non_proxied_udp"

class Stun:
    def __init__(self):
        self.s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); self.s.bind((LAN, 0)); self.s.settimeout(0.05)
        self.port = self.s.getsockname()[1]; self.n = 0; self.stop = False
        self.t = threading.Thread(target=self.run, daemon=True); self.t.start()
    def run(self):
        while not self.stop:
            try: self.s.recvfrom(4096); self.n += 1
            except TimeoutError: pass
            except OSError: return
    def close(self): self.stop = True; self.t.join(); self.s.close()

def essai(nom, args, proxy=None):
    stun = Stun()
    dossier = tempfile.mkdtemp()
    with sync_playwright() as pw:
        kw = dict(user_data_dir=dossier, channel="chrome", headless=False, no_viewport=True, args=args)
        if proxy: kw["proxy"] = {"server": proxy}
        ctx = pw.chromium.launch_persistent_context(**kw)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("about:blank")
        page.evaluate("""async (u) => { const pc = new RTCPeerConnection({iceServers:[{urls:u}]}); pc.createDataChannel('x');
          await pc.setLocalDescription(await pc.createOffer()); await new Promise(r => setTimeout(r, 3000)); }""", f"stun:{LAN}:{stun.port}")
        print(nom, "paquets STUN reçus:", stun.n)
        ctx.close()
    stun.close()

which = sys.argv[1]
if which == "sans":
    essai("LAN sans proxy sans drapeau", []); essai("LAN sans proxy avec drapeau", [POL])
else:
    with ProxyHttpDeTest("u", "p") as px, RelaisProxy(analyser(px.adresse, "u", "p"), ("*",)) as r:
        essai("LAN relais avec drapeau", [POL], proxy=r.adresse); essai("LAN relais sans drapeau", [], proxy=r.adresse)
