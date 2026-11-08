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
from .base import MANDATAIRE_BLOQUANT, ResultatNavigation, liste_directe
from .playwright_engine import DriverPlaywright

# Hôtes des widgets CAPTCHA en mode test — sous-ressources uniquement, jamais cibles de navigation.
HOTES_CHALLENGES = (
    "challenges.cloudflare.com",
    "www.google.com",
    "www.gstatic.com",
    "www.recaptcha.net",
)

# Script injecté avant tout JavaScript de la page pour masquer les signaux headless.
SCRIPT_ANTI_DETECTION = """
(() => {
  // --- Plugins : Chrome moderne expose les viewers PDF (Native Client retiré depuis Chrome 117) ---
  const noms = [
    ['PDF Viewer', 'Portable Document Format', 'internal-pdf-viewer', 'application/pdf'],
    ['Chrome PDF Plugin', 'Portable Document Format', 'internal-pdf-viewer', 'application/pdf'],
    ['Chrome PDF Viewer', 'Portable Document Format', 'internal-pdf-viewer', 'application/pdf'],
    ['Chromium PDF Viewer', 'Portable Document Format', 'internal-pdf-viewer', 'application/pdf'],
  ];
  const faux = noms.map(([nom, desc, fichier, mime]) => {
    const mt = Object.create(MimeType.prototype);
    Object.defineProperties(mt, {
      type: {get: () => mime}, description: {get: () => desc},
      suffixes: {get: () => 'pdf'}, enabledPlugin: {get: () => p},
    });
    const p = Object.create(Plugin.prototype);
    Object.defineProperties(p, {
      name: {get: () => nom}, description: {get: () => desc},
      filename: {get: () => fichier}, length: {get: () => 1},
      0: {get: () => mt},
    });
    return p;
  });
  const pluginArr = Object.create(PluginArray.prototype);
  faux.forEach((p, i) => Object.defineProperty(pluginArr, i, {value: p}));
  Object.defineProperty(pluginArr, 'length', {value: faux.length});
  pluginArr.item = i => faux[i] || null;
  pluginArr.namedItem = n => faux.find(p => p.name === n) || null;
  pluginArr.refresh = () => {};
  Object.defineProperty(navigator, 'plugins', {get: () => pluginArr});

  // --- MimeTypes cohérents avec les plugins ---
  const mimes = faux.map(p => p[0]);
  const mimeArr = Object.create(MimeTypeArray.prototype);
  mimes.forEach((m, i) => Object.defineProperty(mimeArr, i, {value: m}));
  Object.defineProperty(mimeArr, 'length', {value: mimes.length});
  mimeArr.item = i => mimes[i] || null;
  mimeArr.namedItem = t => mimes.find(m => m.type === t) || null;
  Object.defineProperty(navigator, 'mimeTypes', {get: () => mimeArr});

  // --- Notification.permission : "default" au lieu de "denied" (headless) ---
  try {
    Object.defineProperty(Notification, 'permission', {
      get: () => 'default', configurable: true,
    });
  } catch(e) {}

  // --- userAgentData : proxy complet pour retirer HeadlessChrome ---
  if (navigator.userAgentData) {
    const nettoyer = liste => liste.map(b => ({
      brand: b.brand.replace('HeadlessChrome', 'Google Chrome'),
      version: b.version,
    }));
    const orig = navigator.userAgentData;
    const proxy = new Proxy(orig, {
      get(target, prop) {
        if (prop === 'brands') return nettoyer(target.brands);
        if (prop === 'getHighEntropyValues') {
          return async hints => {
            const r = await target.getHighEntropyValues.call(target, hints);
            if (r.brands) r.brands = nettoyer(r.brands);
            if (r.fullVersionList) r.fullVersionList = nettoyer(r.fullVersionList);
            return r;
          };
        }
        if (prop === 'toJSON') return () => ({...target.toJSON(), brands: nettoyer(target.brands)});
        const v = Reflect.get(target, prop);
        return typeof v === 'function' ? v.bind(target) : v;
      },
    });
    Object.defineProperty(navigator, 'userAgentData', {get: () => proxy, configurable: true});
  }

  // --- WebGL : cacher SwiftShader, annoncer un vrai GPU ---
  const surcharger = proto => {
    const orig = proto.getParameter;
    proto.getParameter = function(p) {
      if (p === 37445) return 'Google Inc. (Apple)';
      if (p === 37446)
        return 'ANGLE (Apple, ANGLE Metal Renderer: Apple M5 Pro, Unspecified Version)';
      return orig.call(this, p);
    };
  };
  if (typeof WebGLRenderingContext !== 'undefined')
    surcharger(WebGLRenderingContext.prototype);
  if (typeof WebGL2RenderingContext !== 'undefined')
    surcharger(WebGL2RenderingContext.prototype);
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
        verrou = {"server": MANDATAIRE_BLOQUANT, "bypass": ",".join(liste_directe(tous_hotes))}
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
            self._page.keyboard.press("Control+a")
            self._page.keyboard.press("Backspace")
            for caractere in value:
                self._page.keyboard.type(caractere, delay=random.randint(40, 140))
        else:
            self._page.fill(selector, value)

    # --- Comportement humain ---

    def _interaction_post_chargement(self) -> None:
        try:
            time.sleep(random.uniform(0.3, 0.7))
            self._page.mouse.move(random.randint(100, 700), random.randint(100, 400), steps=random.randint(8, 16))
            time.sleep(random.uniform(0.1, 0.3))
            self._page.mouse.wheel(0, random.randint(80, 350))
            time.sleep(random.uniform(0.15, 0.4))
        except Exception:
            pass

    def _deplacer_vers(self, selector: str) -> None:
        try:
            box = self._page.eval_on_selector(
                selector,
                "e => { const r = e.getBoundingClientRect(); return {x: r.x, y: r.y, w: r.width, h: r.height}; }",
            )
            if box:
                x = int(box["x"] + box["w"] / 2 + random.randint(-3, 3))
                y = int(box["y"] + box["h"] / 2 + random.randint(-3, 3))
                self._page.mouse.move(x, y, steps=random.randint(6, 18))
                time.sleep(random.uniform(0.03, 0.1))
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
