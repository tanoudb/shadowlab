#!/usr/bin/env python3
"""Sonde du navigateur réel (étape 3.1) : ce qu'un Chrome ou un Chromium montre à une page, sans le moteur.

Lance le navigateur avec Patchright, tel quel (aucune réécriture, aucun script d'empreinte), devant une page locale
(`http://localhost`, contexte sécurisé) et écrit un JSON de propriétés brutes : architecture réelle, carte
graphique (WebGL, WebGPU), écran, fenêtre, voix, périphériques, fuseau, codecs (les polices ne sont pas sondées : voir `font_fingerprint` des campagnes).

Sert à lister les écarts qu'aucun détecteur de l'Arena ne relève : on les compare à ce que le moteur annonce
(`engines/noezia/profils`) et à la même sonde lancée sur le poste. Aucune requête hors de `localhost`.

    python3 scripts/fumee-linux-sonde.py --canal chrome|chromium [--sans-interface] --sortie sonde.json
"""

from __future__ import annotations

import argparse
import json
import platform
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

PAGE = b"<!doctype html><meta charset=utf-8><title>sonde</title><body>sonde</body>"

SCRIPT = """
async () => {
  const r = {};
  r.navigateur = {
    userAgent: navigator.userAgent, platform: navigator.platform, vendor: navigator.vendor,
    hardwareConcurrency: navigator.hardwareConcurrency, deviceMemory: navigator.deviceMemory ?? null,
    languages: navigator.languages, webdriver: navigator.webdriver, plugins: navigator.plugins.length,
    pdfViewerEnabled: navigator.pdfViewerEnabled, maxTouchPoints: navigator.maxTouchPoints,
  };
  if (navigator.userAgentData) {
    const u = navigator.userAgentData;
    r.userAgentData = {brands: u.brands, mobile: u.mobile, platform: u.platform};
    try {
      r.userAgentData.haute_entropie = await u.getHighEntropyValues(
        ['architecture', 'bitness', 'model', 'platformVersion', 'uaFullVersion', 'wow64', 'fullVersionList']);
    } catch (e) { r.userAgentData.haute_entropie = String(e); }
  }
  r.ecran = {width: screen.width, height: screen.height, availWidth: screen.availWidth, availHeight: screen.availHeight,
             colorDepth: screen.colorDepth, devicePixelRatio: devicePixelRatio};
  r.fenetre = {innerWidth, innerHeight, outerWidth, outerHeight, screenX: window.screenX, screenY: window.screenY};
  r.intl = {fuseau: Intl.DateTimeFormat().resolvedOptions().timeZone, langue: Intl.DateTimeFormat().resolvedOptions().locale,
            decalage: new Date().getTimezoneOffset()};
  const webgl = {};
  for (const nom of ['webgl', 'webgl2']) {
    const c = document.createElement('canvas'); const gl = c.getContext(nom);
    if (!gl) { webgl[nom] = null; continue; }
    const ext = gl.getExtension('WEBGL_debug_renderer_info');
    webgl[nom] = {vendor: ext ? gl.getParameter(ext.UNMASKED_VENDOR_WEBGL) : gl.getParameter(gl.VENDOR),
                  renderer: ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER),
                  extensions: (gl.getSupportedExtensions() || []).length,
                  maxTexture: gl.getParameter(gl.MAX_TEXTURE_SIZE), subpixelBits: gl.getParameter(gl.SUBPIXEL_BITS)};
  }
  r.webgl = webgl;
  r.webgpu = {present: 'gpu' in navigator, adaptateur: null};
  try { if (navigator.gpu) { const a = await navigator.gpu.requestAdapter(); r.webgpu.adaptateur = a ? (a.info ? {vendor: a.info.vendor, architecture: a.info.architecture, description: a.info.description} : 'oui') : null; } } catch (e) { r.webgpu.erreur = String(e); }
  r.voix = await new Promise(res => {
    const t0 = performance.now(); const lire = () => speechSynthesis.getVoices();
    if (lire().length) return res({n: lire().length, attente_ms: 0});
    const fin = () => res({n: lire().length, attente_ms: Math.round(performance.now() - t0)});
    speechSynthesis.onvoiceschanged = fin; setTimeout(fin, 1500);
  });
  try { const d = await navigator.mediaDevices.enumerateDevices(); r.peripheriques = d.map(x => x.kind); } catch (e) { r.peripheriques = String(e); }
  const v = document.createElement('video');
  r.codecs = {h264: v.canPlayType('video/mp4; codecs="avc1.42E01E"'), aac: v.canPlayType('audio/mp4; codecs="mp4a.40.2"'),
              vp9: v.canPlayType('video/webm; codecs="vp9"'), mp3: v.canPlayType('audio/mpeg')};
  r.connexion = navigator.connection ? {rtt: navigator.connection.rtt, downlink: navigator.connection.downlink, type: navigator.connection.effectiveType} : null;
  r.audio = {offline: typeof OfflineAudioContext !== 'undefined', echantillonnage: new (window.AudioContext || window.webkitAudioContext)().sampleRate};
  return r;
}
"""


class Silencieux(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(PAGE)

    def log_message(self, *args):
        pass


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument(
        "--canal",
        choices=["chrome", "chromium"],
        required=True,
        help="chrome : Google Chrome installé ; chromium : le Chromium embarqué de Patchright",
    )
    p.add_argument("--sans-interface", action="store_true", help="headless (sinon : avec interface, il faut un écran)")
    p.add_argument("--sortie", required=True)
    args = p.parse_args()

    from patchright.sync_api import sync_playwright

    serveur = HTTPServer(("127.0.0.1", 0), Silencieux)
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    url = f"http://localhost:{serveur.server_address[1]}/"
    resultat: dict = {
        "hote": {
            "machine": platform.machine(),
            "systeme": platform.system(),
            "version_python": platform.python_version(),
        },
        "reglage": {"canal": args.canal, "sans_interface": args.sans_interface},
    }
    try:
        with sync_playwright() as pw:
            nav = pw.chromium.launch(channel="chrome" if args.canal == "chrome" else None, headless=args.sans_interface)
            resultat["version_navigateur"] = nav.version
            page = nav.new_context(no_viewport=True).new_page()
            page.goto(url)
            resultat["sonde"] = page.evaluate(SCRIPT)
            nav.close()
    except Exception as erreur:  # un navigateur qui ne démarre pas est un résultat
        resultat["erreur"] = f"{type(erreur).__name__}: {str(erreur)[:600]}"
    finally:
        serveur.shutdown()
    Path(args.sortie).parent.mkdir(parents=True, exist_ok=True)
    Path(args.sortie).write_text(json.dumps(resultat, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in resultat.items() if k != "sonde"}, ensure_ascii=False))
    return 0 if "erreur" not in resultat else 1


if __name__ == "__main__":
    raise SystemExit(main())
