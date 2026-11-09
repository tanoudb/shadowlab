"""Moteur expérimental NOEZIA — proof of concept de contournement anti-bot.

⚠️  AVERTISSEMENT — USAGE RESTREINT
Ce moteur est un outil de RECHERCHE conçu exclusivement pour tester nos propres
protections dans l'Arena ShadowLab et sur des domaines que nous contrôlons.
Les auteurs déclinent toute responsabilité en cas d'utilisation de ce code
ou de ses techniques sur des systèmes tiers sans autorisation explicite.

Techniques combinées :
- Base Patchright (Chromium modifié, pas de fuites CDP/WebDriver)
- Simulation comportementale réaliste (souris, défilement, pauses, frappe)
- Évitement des honeypots par vérification de visibilité DOM
- Résolution des challenges navigateur (PoW, Turnstile/reCAPTCHA en mode test)
- Sous-ressources des widgets autorisées (test keys ; résultat étiqueté captcha_test, D-16)
- Cohérence HTTP/JS (locale, viewport, cookies)
"""

from __future__ import annotations

import importlib.metadata
import random
import time
from typing import Any

from ..perimetre import est_autorisee
from .base import ResultatNavigation, proxy_verrou
from .playwright_engine import DriverPlaywright

# Hôtes des widgets CAPTCHA en mode test — sous-ressources uniquement, jamais cibles de navigation.
HOTES_CHALLENGES = (
    "challenges.cloudflare.com",
    "www.google.com",
    "www.gstatic.com",
    "www.recaptcha.net",
)

# Script injecté avant tout JavaScript de la page pour masquer les signaux headless.
# v3 — toString() natif, canvas, audio, WebGL complet, permissions, window.chrome.
SCRIPT_ANTI_DETECTION = """
(() => {
  // Ne pas modifier les iframes de widgets tiers (Turnstile, reCAPTCHA)
  try { const h = location.hostname;
    if (h !== 'localhost' && h !== '127.0.0.1') return;
  } catch(e) { return; }

  // ─── 1. toString() natif : tous nos overrides passent /native code/.test() ───
  const _ts = Function.prototype.toString;
  const _natifs = new WeakMap();
  function natif(fn, nom) { _natifs.set(fn, nom); return fn; }
  Function.prototype.toString = function() {
    const n = _natifs.get(this);
    if (n !== undefined) return 'function ' + n + '() { [native code] }';
    return _ts.call(this);
  };
  natif(Function.prototype.toString, 'toString');

  // ─── 2. Plugins (4 viewers PDF, MimeTypes, singleton, getters natifs) ───
  const pluginDefs = [
    ['PDF Viewer', 'Portable Document Format', 'internal-pdf-viewer', 'application/pdf'],
    ['Chrome PDF Plugin', 'Portable Document Format', 'internal-pdf-viewer', 'application/pdf'],
    ['Chrome PDF Viewer', 'Portable Document Format', 'internal-pdf-viewer', 'application/pdf'],
    ['Chromium PDF Viewer', 'Portable Document Format', 'internal-pdf-viewer', 'application/pdf'],
  ];
  const fauxPlugins = pluginDefs.map(([nom, desc, fichier, mime]) => {
    const mt = Object.create(MimeType.prototype);
    Object.defineProperties(mt, {
      type:          {get: natif(() => mime, 'get type')},
      description:   {get: natif(() => desc, 'get description')},
      suffixes:      {get: natif(() => 'pdf', 'get suffixes')},
      enabledPlugin: {get: natif(() => p, 'get enabledPlugin')},
    });
    const p = Object.create(Plugin.prototype);
    Object.defineProperties(p, {
      name:        {get: natif(() => nom, 'get name')},
      description: {get: natif(() => desc, 'get description')},
      filename:    {get: natif(() => fichier, 'get filename')},
      length:      {get: natif(() => 1, 'get length')},
      0:           {get: natif(() => mt, '0')},
    });
    return p;
  });
  const pluginArr = Object.create(PluginArray.prototype);
  fauxPlugins.forEach((p, i) => Object.defineProperty(pluginArr, i, {value: p}));
  Object.defineProperty(pluginArr, 'length', {value: fauxPlugins.length});
  pluginArr.item = natif(i => fauxPlugins[i] || null, 'item');
  pluginArr.namedItem = natif(n => fauxPlugins.find(p => p.name === n) || null, 'namedItem');
  pluginArr.refresh = natif(() => {}, 'refresh');
  Object.defineProperty(navigator, 'plugins', {get: natif(() => pluginArr, 'get plugins')});

  const mimeObjs = fauxPlugins.map(p => p[0]);
  const mimeArr = Object.create(MimeTypeArray.prototype);
  mimeObjs.forEach((m, i) => Object.defineProperty(mimeArr, i, {value: m}));
  Object.defineProperty(mimeArr, 'length', {value: mimeObjs.length});
  mimeArr.item = natif(i => mimeObjs[i] || null, 'item');
  mimeArr.namedItem = natif(t => mimeObjs.find(m => m.type === t) || null, 'namedItem');
  Object.defineProperty(navigator, 'mimeTypes', {get: natif(() => mimeArr, 'get mimeTypes')});

  // ─── 3. Notification.permission → "default" (headless = "denied") ───
  try {
    Object.defineProperty(Notification, 'permission', {
      get: natif(() => 'default', 'get permission'), configurable: true,
    });
  } catch(e) {}

  // ─── 4. Permissions API : query('notifications') → 'prompt' (cohérent avec "default") ───
  if (navigator.permissions) {
    const origQuery = navigator.permissions.query.bind(navigator.permissions);
    navigator.permissions.query = natif(function query(desc) {
      if (desc && desc.name === 'notifications') {
        return Promise.resolve({state: 'prompt', onchange: null});
      }
      return origQuery(desc);
    }, 'query');
  }

  // ─── 5. userAgentData Proxy (HeadlessChrome → Google Chrome) ───
  if (navigator.userAgentData) {
    const nettoyer = liste => liste.map(b => ({
      brand: b.brand.replace('HeadlessChrome', 'Google Chrome'), version: b.version,
    }));
    const uaOrig = navigator.userAgentData;
    const uaProxy = new Proxy(uaOrig, {
      get(target, prop) {
        if (prop === 'brands') return nettoyer(target.brands);
        if (prop === 'getHighEntropyValues') {
          return natif(async function getHighEntropyValues(hints) {
            const r = await target.getHighEntropyValues.call(target, hints);
            if (r.brands) r.brands = nettoyer(r.brands);
            if (r.fullVersionList) r.fullVersionList = nettoyer(r.fullVersionList);
            return r;
          }, 'getHighEntropyValues');
        }
        if (prop === 'toJSON') return natif(function toJSON() {
          return {...target.toJSON(), brands: nettoyer(target.brands)};
        }, 'toJSON');
        const v = Reflect.get(target, prop);
        return typeof v === 'function' ? v.bind(target) : v;
      },
    });
    Object.defineProperty(navigator, 'userAgentData', {
      get: natif(() => uaProxy, 'get userAgentData'), configurable: true,
    });
  }

  // ─── 6. WebGL complet : vendor, renderer, extensions, capabilities M5 Pro ───
  const GPU_V = 'Google Inc. (Apple)';
  const GPU_R = 'ANGLE (Apple, ANGLE Metal Renderer: Apple M5 Pro, Unspecified Version)';
  const GPU_EXT = [
    'ANGLE_instanced_arrays','EXT_blend_minmax','EXT_color_buffer_half_float',
    'EXT_disjoint_timer_query','EXT_float_blend','EXT_frag_depth',
    'EXT_shader_texture_lod','EXT_texture_compression_bptc',
    'EXT_texture_compression_rgtc','EXT_texture_filter_anisotropic',
    'EXT_sRGB','KHR_parallel_shader_compile','OES_element_index_uint',
    'OES_fbo_render_mipmap','OES_standard_derivatives',
    'OES_texture_float','OES_texture_float_linear',
    'OES_texture_half_float','OES_texture_half_float_linear',
    'OES_vertex_array_object','WEBGL_color_buffer_float',
    'WEBGL_compressed_texture_s3tc','WEBGL_compressed_texture_s3tc_srgb',
    'WEBGL_debug_renderer_info','WEBGL_debug_shaders',
    'WEBGL_depth_texture','WEBGL_draw_buffers','WEBGL_lose_context','WEBGL_multi_draw',
  ];
  const surchargerGL = proto => {
    const origGP = proto.getParameter;
    const origGSE = proto.getSupportedExtensions;
    proto.getParameter = natif(function getParameter(p) {
      if (p === 37445) return GPU_V;   // UNMASKED_VENDOR_WEBGL
      if (p === 37446) return GPU_R;   // UNMASKED_RENDERER_WEBGL
      return origGP.call(this, p);
    }, 'getParameter');
    proto.getSupportedExtensions = natif(function getSupportedExtensions() {
      return [...GPU_EXT];
    }, 'getSupportedExtensions');
  };
  if (typeof WebGLRenderingContext !== 'undefined')
    surchargerGL(WebGLRenderingContext.prototype);
  if (typeof WebGL2RenderingContext !== 'undefined')
    surchargerGL(WebGL2RenderingContext.prototype);

  // ─── 7. Canvas : bruit déterministe (change le hash sans casser l'image) ───
  const SEED = 0x5AD0B;
  let rng = SEED;
  function prng() { rng = (rng * 1103515245 + 12345) & 0x7fffffff; return (rng >> 16) / 32768; }

  const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
  const origToBlob = HTMLCanvasElement.prototype.toBlob;
  const origGetImageData = CanvasRenderingContext2D.prototype.getImageData;

  function canvasBruite(source) {
    try {
      const w = source.width, h = source.height;
      if (w <= 0 || h <= 0) return null;
      const tmp = document.createElement('canvas');
      tmp.width = w; tmp.height = h;
      const ctx = tmp.getContext('2d');
      ctx.drawImage(source, 0, 0);
      const sw = Math.min(w, 64), sh = Math.min(h, 64);
      const img = origGetImageData.call(ctx, 0, 0, sw, sh);
      rng = SEED;
      for (let i = 0; i < img.data.length; i += 4) {
        img.data[i] = (img.data[i] + (prng() > 0.5 ? 1 : -1)) & 0xff;
      }
      ctx.putImageData(img, 0, 0);
      return tmp;
    } catch(e) { return null; }
  }

  HTMLCanvasElement.prototype.toDataURL = natif(function toDataURL() {
    const b = canvasBruite(this);
    return origToDataURL.apply(b || this, arguments);
  }, 'toDataURL');
  HTMLCanvasElement.prototype.toBlob = natif(function toBlob() {
    const b = canvasBruite(this);
    return origToBlob.apply(b || this, arguments);
  }, 'toBlob');

  // ─── 8. Audio : bruit infime dans OfflineAudioContext ───
  if (typeof OfflineAudioContext !== 'undefined') {
    const origSR = OfflineAudioContext.prototype.startRendering;
    OfflineAudioContext.prototype.startRendering = natif(function startRendering() {
      return origSR.call(this).then(buf => {
        try {
          const d = buf.getChannelData(0);
          rng = SEED;
          for (let i = 0; i < d.length; i++) d[i] += (prng() - 0.5) * 1e-7;
        } catch(e) {}
        return buf;
      });
    }, 'startRendering');
  }

  // ─── 9. window.chrome (structure minimale attendue par les détecteurs) ───
  if (!window.chrome) window.chrome = {};
  if (!window.chrome.runtime) {
    window.chrome.runtime = {
      connect: natif(function connect() { return {}; }, 'connect'),
      sendMessage: natif(function sendMessage() {}, 'sendMessage'),
    };
  }
  if (!window.chrome.csi) {
    window.chrome.csi = natif(function csi() {
      return {onloadT: Date.now(), startE: Date.now() - 300, pageT: 300, tran: 15};
    }, 'csi');
  }
})();
"""


class DriverNoeziaExperimental(DriverPlaywright):
    name = "noezia-experimental"
    categorie = "anti_detection"
    options_permises = {
        "headless": bool,
        "simuler_souris": bool,
        "simuler_frappe": bool,
        "eviter_pieges": bool,
        "interaction_post_page": bool,
        "locale": str,
    }

    def _api(self):
        from patchright.sync_api import sync_playwright

        return sync_playwright

    def configuration(self) -> dict[str, Any]:
        return {
            "browser": "chromium-patchright",
            "headless": True,
            "trace": False,
            "tls_non_verifie": True,
            "simuler_souris": True,
            "simuler_frappe": True,
            "eviter_pieges": True,
            "interaction_post_page": True,
            "locale": "fr-FR",
            "viewport": "1920x1080",
            "ua_spoof": True,
            "plugins_spoof": True,
            "webgl_spoof": "Apple M5 Pro",
            "canvas_noise": True,
            "audio_noise": True,
            "tostring_native": True,
            "permissions_coherent": True,
            "bezier_mouse": True,
            "gaussian_typing": True,
            **self.options,
        }

    def versions(self) -> dict[str, str]:
        versions = {"patchright": importlib.metadata.version("patchright")}
        if getattr(self, "_navigateur", None) is not None:
            versions["chromium"] = self._navigateur.version
        return versions

    # --- Lancement avec bypass réseau pour les widgets de challenge ---

    def open(self) -> None:
        config = self.configuration()
        self._pw = self._api()().start()
        tous_hotes = tuple(self.hotes_autorises) + HOTES_CHALLENGES
        verrou = proxy_verrou(tous_hotes)  # None en périmètre illimité
        self._navigateur = self._pw.chromium.launch(headless=config["headless"], proxy=verrou)

    def _nouveau_contexte(self):
        config = self.configuration()
        version = self._navigateur.version
        major = version.split(".")[0]
        ua = (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            f"Chrome/{version} Safari/537.36"
        )
        contexte = self._navigateur.new_context(
            ignore_https_errors=True,
            locale=config.get("locale", "fr-FR"),
            viewport={"width": 1920, "height": 1080},
            user_agent=ua,
            extra_http_headers={
                "sec-ch-ua": (f'"Not:A-Brand";v="8", "Chromium";v="{major}", "Google Chrome";v="{major}"'),
            },
        )
        contexte.add_init_script(SCRIPT_ANTI_DETECTION)
        contexte.route("**/*", self._filtrer)
        return contexte

    def _filtrer(self, route) -> None:
        url = route.request.url
        autorise = est_autorisee(url, self.hotes_autorises)
        challenge = not autorise and est_autorisee(url, HOTES_CHALLENGES)
        if challenge and route.request.is_navigation_request():
            frame = route.request.frame
            if frame is not None and frame.parent_frame is None:
                self.mesures.details["requetes_bloquees"] += 1
                route.abort("blockedbyclient")
                return
        if autorise or challenge:
            headers = {**route.request.headers}
            ua = headers.get("user-agent", "")
            if "HeadlessChrome" in ua:
                headers["user-agent"] = ua.replace("HeadlessChrome", "Chrome")
            ch_ua = headers.get("sec-ch-ua", "")
            if "HeadlessChrome" in ch_ua:
                headers["sec-ch-ua"] = ch_ua.replace("HeadlessChrome", "Google Chrome")
            route.continue_(headers=headers)
        else:
            self.mesures.details["requetes_bloquees"] += 1
            route.abort("blockedbyclient")

    # --- Navigation avec simulation post-chargement ---

    def navigate(self, url: str) -> ResultatNavigation:
        resultat = super().navigate(url)
        if self.configuration().get("interaction_post_page", True):
            self._interaction_post_chargement()
        return resultat

    # --- Clic avec déplacement de souris et détection de piège ---

    def click(self, selector: str) -> None:
        if self.configuration().get("eviter_pieges", True) and not self._est_visible(selector):
            return
        if self.configuration().get("simuler_souris", True):
            self._deplacer_vers(selector)
        super().click(selector)

    # --- Remplissage avec frappe humaine caractère par caractère ---

    def fill(self, selector: str, value: str) -> None:
        if self.configuration().get("eviter_pieges", True) and not self._est_visible(selector):
            return
        if self.configuration().get("simuler_souris", True):
            self._deplacer_vers(selector)
        if self.configuration().get("simuler_frappe", True):
            self._page.click(selector)
            self._page.keyboard.press("ControlOrMeta+a")
            self._page.keyboard.press("Backspace")
            for caractere in value:
                self._page.keyboard.type(caractere, delay=self._delai_frappe())
        else:
            self._page.fill(selector, value)

    # --- Comportement humain ---

    @staticmethod
    def _bezier(x0: float, y0: float, x1: float, y1: float, n: int = 22) -> list[tuple[int, int]]:
        dist = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
        amp = max(15, min(dist * 0.35, 120))
        cx = (x0 + x1) / 2 + random.uniform(-amp, amp)
        cy = (y0 + y1) / 2 + random.uniform(-amp * 0.7, amp * 0.7)
        pts: list[tuple[int, int]] = []
        for i in range(n + 1):
            t = i / n
            t = t * t * (3 - 2 * t)
            bx = (1 - t) ** 2 * x0 + 2 * (1 - t) * t * cx + t**2 * x1
            by = (1 - t) ** 2 * y0 + 2 * (1 - t) * t * cy + t**2 * y1
            bx = max(0, min(1920, bx + (random.gauss(0, 0.5) if 0 < i < n else 0)))
            by = max(0, min(1080, by + (random.gauss(0, 0.5) if 0 < i < n else 0)))
            pts.append((int(bx), int(by)))
        return pts

    def _mouvement_bezier(self, x: int, y: int) -> None:
        try:
            ox = getattr(self, "_mx", 400)
            oy = getattr(self, "_my", 300)
            pts = self._bezier(ox, oy, x, y)
            for px, py in pts:
                self._page.mouse.move(px, py)
                time.sleep(random.uniform(0.004, 0.014))
            self._mx, self._my = x, y
        except Exception:
            self._page.mouse.move(x, y, steps=random.randint(8, 16))
            self._mx, self._my = x, y

    @staticmethod
    def _delai_frappe() -> int:
        if random.random() < 0.07:
            return random.randint(180, 420)
        return max(25, int(random.gauss(82, 28)))

    def _interaction_post_chargement(self) -> None:
        try:
            time.sleep(random.uniform(0.3, 0.8))
            self._mouvement_bezier(random.randint(100, 800), random.randint(100, 500))
            time.sleep(random.uniform(0.08, 0.25))
            self._page.mouse.wheel(0, random.randint(60, 400))
            time.sleep(random.uniform(0.1, 0.35))
            if random.random() < 0.4:
                self._mouvement_bezier(random.randint(200, 900), random.randint(80, 450))
                time.sleep(random.uniform(0.05, 0.2))
        except Exception:
            pass

    def _deplacer_vers(self, selector: str) -> None:
        try:
            box = self._page.eval_on_selector(
                selector,
                "e => { const r = e.getBoundingClientRect(); return {x: r.x, y: r.y, w: r.width, h: r.height}; }",
            )
            if box:
                x = int(box["x"] + box["w"] / 2 + random.gauss(0, 2))
                y = int(box["y"] + box["h"] / 2 + random.gauss(0, 2))
                self._mouvement_bezier(x, y)
                time.sleep(random.uniform(0.02, 0.08))
        except Exception:
            pass

    def _est_visible(self, selector: str) -> bool:
        try:
            return bool(
                self._page.eval_on_selector(
                    selector,
                    """e => {
                const s = window.getComputedStyle(e);
                const r = e.getBoundingClientRect();
                return s.display !== 'none'
                    && s.visibility !== 'hidden'
                    && parseFloat(s.opacity) > 0.01
                    && r.width > 1
                    && r.height > 1;
            }""",
                )
            )
        except Exception:
            return True
