// Nettoyage des marqueurs d'automation et cohérence CSS/timing.
// Supprime les globales trahissant Playwright/Puppeteer/Selenium/ChromeDriver,
// normalise les media queries headless, et aligne la précision des timers.
(() => {
  const P = window.__NOEZIA_PROFIL__;
  if (!P) return;
  const natif = window.__NOEZIA_NATIF__ || (fn => fn);


  // ─── Nettoyage des globales d'automation ───
  const GLOBALES_SUSPECTES = [
    '__playwright', '__pw_manual', '__playwright_evaluation_script__',
    '__pwright_target__', '__playwright_routeHandler',
    '__selenium_unwrapped', '__webdriver_evaluate', '__driver_evaluate',
    '__webdriver_script_fn', '__fxdriver_evaluate', '__driver_unwrapped',
    '__webdriver_script_func', '__lastWatirAlert', '__lastWatirConfirm',
    '__lastWatirPrompt', '_Selenium_IDE_Recorder', '_WEBDRIVER_ELEM_CACHE',
    'callPhantom', '_phantom', '__nightmare',
    'domAutomation', 'domAutomationController',
  ];

  for (const nom of GLOBALES_SUSPECTES) {
    try {
      if (nom in window) {
        delete window[nom];
        if (nom in window) {
          Object.defineProperty(window, nom, {
            get: () => undefined,
            set: () => {},
            configurable: true,
          });
        }
      }
    } catch(e) {}
  }

  // cdc_ et $cdc_ (ChromeDriver) : préfixes dynamiques
  try {
    for (const k of Object.keys(window)) {
      if (k.startsWith('cdc_') || k.startsWith('$cdc_')) {
        try { delete window[k]; } catch(e) {}
      }
    }
  } catch(e) {}

  // document aussi
  const DOC_SUSPECTES = [
    '__selenium_unwrapped', '__webdriver_evaluate',
    '$chrome_asyncScriptInfo', '$cdc_asdjflasutopfhvcZLmcfl_',
  ];
  for (const nom of DOC_SUSPECTES) {
    try {
      if (nom in document) {
        delete document[nom];
      }
    } catch(e) {}
  }

  // ─── CSS media queries : cohérence headless → headed ───
  // Headless Chrome : prefers-color-scheme = light (correct)
  //                   prefers-reduced-motion = no-preference (correct)
  //                   forced-colors = none (correct)
  // Mais matchMedia peut trahir un écran absent via des queries obscures.
  const origMatchMedia = window.matchMedia;
  if (origMatchMedia) {
    function _fauxResult(result, forcedMatches) {
      return {
        matches: forcedMatches,
        media: result.media,
        onchange: null,
        addListener: natif(function addListener() {}, 'addListener'),
        removeListener: natif(function removeListener() {}, 'removeListener'),
        addEventListener: natif(function addEventListener() {}, 'addEventListener'),
        removeEventListener: natif(function removeEventListener() {}, 'removeEventListener'),
        dispatchEvent: natif(function dispatchEvent() { return true; }, 'dispatchEvent'),
      };
    }
    window.matchMedia = natif(function matchMedia(query) {
      const q = typeof query === 'string' ? query : '';
      const result = origMatchMedia.call(window, q);
      // hover:none → false (un desktop a toujours hover:hover)
      if (/\(hover:\s*none\)/.test(q) && result.matches) return _fauxResult(result, false);
      // pointer:none → false (un desktop a toujours pointer:fine)
      if (/\(pointer:\s*none\)/.test(q) && result.matches) return _fauxResult(result, false);
      // display-mode:browser → true (headless Chrome retourne false)
      if (/\(display-mode:\s*browser\)/.test(q) && !result.matches) return _fauxResult(result, true);
      return result;
    }, 'matchMedia');
  }

  // ─── Prototype chain : propriétés propres inattendues sur navigator ───
  // Certaines propriétés sont sur Navigator.prototype dans un vrai Chrome,
  // mais Playwright/Patchright peut en ajouter comme propriétés propres.
  // On supprime les propres pour que le prototype les fournisse.
  const PROPS_PROTOTYPE_ONLY = [
    'webdriver',
    'hardwareConcurrency', 'deviceMemory',
    'languages', 'language', 'platform', 'vendor', 'plugins', 'mimeTypes',
  ];
  for (const prop of PROPS_PROTOTYPE_ONLY) {
    try {
      const desc = Object.getOwnPropertyDescriptor(navigator, prop);
      if (desc) {
        // Propriété propre inattendue : la supprimer (le prototype la fournit)
        delete navigator[prop];
      }
    } catch(e) {}
  }

  // Même chose pour screen : les dimensions doivent être sur Screen.prototype
  const SCREEN_PROTO = ['width', 'height', 'availWidth', 'availHeight', 'colorDepth', 'pixelDepth'];
  for (const prop of SCREEN_PROTO) {
    try {
      const desc = Object.getOwnPropertyDescriptor(screen, prop);
      if (desc && !Object.getOwnPropertyDescriptor(Screen.prototype, prop)) {
        // Si c'est sur l'instance mais pas sur le prototype, c'est suspect
        // Ne rien faire ici : nos patches les mettent sur le prototype
      } else if (desc) {
        delete screen[prop];
      }
    } catch(e) {}
  }

  // ─── Performance.now() : normalisation de la précision ───
  // Headless Chrome peut avoir une précision de timer différente.
  // Un navigateur standard avec cross-origin isolation off arrondit à 100µs.
  // On s'assure que la précision est cohérente.
  try {
    const origPerfNow = performance.now.bind(performance);
    performance.now = natif(function now() {
      // Arrondir à 100µs (0.1ms) — comportement standard sans SharedArrayBuffer
      return Math.round(origPerfNow() * 10) / 10;
    }, 'now');
  } catch(e) {}

  // ─── Date.now() : micro-jitter pour masquer les patterns d'automation ───
  // Les bots appellent Date.now() à intervalles très réguliers.
  // On n'ajoute PAS de bruit (ça casserait les mesures), mais on s'assure
  // que la fonction reste native.
  // (natif() suffit pour passer le toString test)

  // ─── Cleanup : supprimer nos marqueurs — plus aucun script ne les utilise ───
  // Suppression totale : '__NOEZIA_PROFIL__' in window → false
  try { delete window.__NOEZIA_PROFIL__; } catch(e) {}
  try { delete window.__NOEZIA_NATIF__; } catch(e) {}
  // Aussi via Proxy si delete a échoué (propriété non-configurable)
  try {
    if ('__NOEZIA_PROFIL__' in window) {
      Object.defineProperty(window, '__NOEZIA_PROFIL__', {
        get: () => undefined, set: () => {}, enumerable: false, configurable: true,
      });
    }
    if ('__NOEZIA_NATIF__' in window) {
      Object.defineProperty(window, '__NOEZIA_NATIF__', {
        get: () => undefined, set: () => {}, enumerable: false, configurable: true,
      });
    }
  } catch(e) {}
})();
