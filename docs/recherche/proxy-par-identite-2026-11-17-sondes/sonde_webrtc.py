"""Sonde jetable (hors dépôt) : paquets UDP reçus par un STUN local selon les arguments de lancement de Chrome."""
import os, sys, tempfile, time
sys.path.insert(0, "tests")
from outils_proxy import CibleDeTest, EcouteStunDeTest, ProxyHttpDeTest
from patchright.sync_api import sync_playwright

def essai(nom, args, proxy=None):
    with EcouteStunDeTest() as stun, CibleDeTest(port_stun=stun.port) as cible:
        dossier = tempfile.mkdtemp()
        with sync_playwright() as pw:
            kw = dict(user_data_dir=dossier, channel="chrome", headless=False, no_viewport=True, args=args)
            if proxy:
                kw["proxy"] = {"server": proxy}
            ctx = pw.chromium.launch_persistent_context(**kw)
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(cible.url("/webrtc"))
            page.wait_for_selector("#fini", timeout=15000)
            print(nom, "version", ctx.browser.version, "paquets STUN", stun.paquets, "ports sources", sorted(set(p for _, p in stun.sources)))
            ctx.close()

POL = "--webrtc-ip-handling-policy=disable_non_proxied_udp"
if __name__ == "__main__":
    which = sys.argv[1]
    if which == "sans":
        essai("sans proxy, sans drapeau", [])
    elif which == "drapeau":
        essai("sans proxy, drapeau", [POL])
    elif which == "relais":
        sys.path.insert(0, "src")
        from shadowlab.engines.noezia.proxy_identite import RelaisProxy, analyser
        with ProxyHttpDeTest("u", "p") as px:
            with RelaisProxy(analyser(px.adresse, "u", "p"), ("*",)) as r:
                essai("relais, drapeau", [POL], proxy=r.adresse)
                essai("relais, sans drapeau", [], proxy=r.adresse)
