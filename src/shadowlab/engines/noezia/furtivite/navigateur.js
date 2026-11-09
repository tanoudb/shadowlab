// Patches navigator : plugins, mimeTypes, permissions, userAgentData, window.chrome.
// Paramètres injectés via __NOEZIA_PROFIL__ avant exécution.
(() => {
  const P = window.__NOEZIA_PROFIL__;
  if (!P) return;

  // Ne pas modifier les iframes de widgets tiers
  try { const h = location.hostname;
    if (h !== 'localhost' && h !== '127.0.0.1' && !h.endsWith('.localhost') && !h.endsWith('.test')) return;
  } catch(e) { return; }

  // ─── toString() natif : tous nos overrides passent /native code/.test() ───
  const _ts = Function.prototype.toString;
  const _natifs = new WeakMap();
  function natif(fn, nom) {
    _natifs.set(fn, nom);
    // Un getter natif C++ n'a pas de .prototype et a length=0.
    // Sans ce nettoyage, Object.getOwnPropertyDescriptor(Navigator.prototype, prop).get
    // révèle une fonction JS au lieu d'un getter natif.
    delete fn.prototype;
    try {
      Object.defineProperty(fn, 'name', { value: nom, writable: false, configurable: true });
    } catch(e) {}
    // Getters/setters natifs ont length=0 ; les méthodes gardent leur longueur déclarée
    if (nom.startsWith('get ') || nom.startsWith('set ') || nom === 'toString') {
      try {
        Object.defineProperty(fn, 'length', { value: 0, writable: false, configurable: true });
      } catch(e) {}
    }
    return fn;
  }
  const _remplacement = {toString() {
    const n = _natifs.get(this);
    if (n !== undefined) return 'function ' + n + '() { [native code] }';
    return _ts.call(this);
  }}.toString;
  Object.defineProperty(Function.prototype, 'toString', {
    value: _remplacement, writable: true, configurable: true,
  });
  natif(Function.prototype.toString, 'toString');

  // Exposer natif() pour les autres scripts
  window.__NOEZIA_NATIF__ = natif;

  // ─── Filtrage des stack traces via Error.prototype.stack getter ───
  // On ne touche PAS à Error.prepareStackTrace (sa présence est détectable).
  // À la place, on intercepte la lecture de .stack sur chaque Error.
  const _SUSPECTS = /patchright|playwright|puppeteer|__cdp|devtools|injected|chrome-extension:\/\//i;
  const _origStackDesc = Object.getOwnPropertyDescriptor(Error.prototype, 'stack')
    || Object.getOwnPropertyDescriptor(Object.getPrototypeOf(Error.prototype), 'stack');
  if (_origStackDesc && _origStackDesc.get) {
    const _origGet = _origStackDesc.get;
    const _filteredGet = natif(function get stack() {
      const s = _origGet.call(this);
      if (typeof s !== 'string') return s;
      return s.split('\n').filter(l => !_SUSPECTS.test(l)).join('\n');
    }, 'get stack');
    Object.defineProperty(Error.prototype, 'stack', {
      get: _filteredGet,
      set: _origStackDesc.set,
      configurable: true,
    });
  }

  // ─── Plugins (4 viewers PDF) ───
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
  fauxPlugins.forEach((p, i) => Object.defineProperty(pluginArr, i, {value: p, enumerable: true}));
  Object.defineProperty(pluginArr, 'length', {value: fauxPlugins.length});
  pluginArr.item = natif(i => fauxPlugins[i] || null, 'item');
  pluginArr.namedItem = natif(n => fauxPlugins.find(p => p.name === n) || null, 'namedItem');
  pluginArr.refresh = natif(() => {}, 'refresh');
  pluginArr[Symbol.iterator] = natif(function* values() {
    for (let i = 0; i < fauxPlugins.length; i++) yield fauxPlugins[i];
  }, 'values');
  // Accès par nom (Chrome le supporte)
  fauxPlugins.forEach(p => { pluginArr[p.name] = p; });
  Object.defineProperty(Navigator.prototype, 'plugins', {
    get: natif(() => pluginArr, 'get plugins'), configurable: true,
  });

  const mimeObjs = fauxPlugins.map(p => p[0]);
  const mimeArr = Object.create(MimeTypeArray.prototype);
  mimeObjs.forEach((m, i) => Object.defineProperty(mimeArr, i, {value: m, enumerable: true}));
  Object.defineProperty(mimeArr, 'length', {value: mimeObjs.length});
  mimeArr.item = natif(i => mimeObjs[i] || null, 'item');
  mimeArr.namedItem = natif(t => mimeObjs.find(m => m.type === t) || null, 'namedItem');
  mimeArr[Symbol.iterator] = natif(function* values() {
    for (let i = 0; i < mimeObjs.length; i++) yield mimeObjs[i];
  }, 'values');
  mimeObjs.forEach(m => { mimeArr[m.type] = m; });
  Object.defineProperty(Navigator.prototype, 'mimeTypes', {
    get: natif(() => mimeArr, 'get mimeTypes'), configurable: true,
  });

  // ─── Notification.permission → "default" ───
  try {
    Object.defineProperty(Notification, 'permission', {
      get: natif(() => 'default', 'get permission'), configurable: true,
    });
  } catch(e) {}

  // ─── Permissions API : toutes les requêtes → état réaliste ───
  if (navigator.permissions) {
    const origQuery = navigator.permissions.query.bind(navigator.permissions);
    const PERM_PROMPT = new Set([
      'notifications', 'geolocation', 'camera', 'microphone',
      'persistent-storage', 'midi', 'screen-wake-lock', 'nfc',
      'display-capture', 'idle-detection', 'clipboard-read',
      'clipboard-write', 'payment-handler', 'background-fetch',
      'background-sync', 'periodic-background-sync',
      'storage-access', 'window-management', 'local-fonts',
    ]);
    const PERM_GRANTED = new Set(['accelerometer', 'gyroscope', 'magnetometer']);
    navigator.permissions.query = natif(function query(desc) {
      if (!desc || !desc.name) return origQuery(desc);
      const nom = desc.name;
      if (PERM_PROMPT.has(nom))
        return Promise.resolve({state: 'prompt', onchange: null});
      if (PERM_GRANTED.has(nom))
        return Promise.resolve({state: 'granted', onchange: null});
      return origQuery(desc);
    }, 'query');
  }

  // ─── userAgentData (HeadlessChrome → Google Chrome) ───
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
            if (P.platform) r.platform = P.platform_name || r.platform;
            return r;
          }, 'getHighEntropyValues');
        }
        if (prop === 'toJSON') return natif(function toJSON() {
          return {...target.toJSON(), brands: nettoyer(target.brands)};
        }, 'toJSON');
        if (prop === 'platform') return P.platform_name || Reflect.get(target, prop);
        const v = Reflect.get(target, prop);
        return typeof v === 'function' ? v.bind(target) : v;
      },
    });
    Object.defineProperty(navigator, 'userAgentData', {
      get: natif(() => uaProxy, 'get userAgentData'), configurable: true,
    });
  }

  // ─── hardwareConcurrency et deviceMemory (sur le prototype, pas l'instance) ───
  if (P.hardware_concurrency) {
    Object.defineProperty(Navigator.prototype, 'hardwareConcurrency', {
      get: natif(() => P.hardware_concurrency, 'get hardwareConcurrency'),
      configurable: true,
    });
  }
  if (P.device_memory) {
    Object.defineProperty(Navigator.prototype, 'deviceMemory', {
      get: natif(() => P.device_memory, 'get deviceMemory'),
      configurable: true,
    });
  }

  // ─── navigator.languages (sur le prototype, gelée) ───
  if (P.locale) {
    const langPrimaire = P.locale.replace('_', '-');
    const langBase = langPrimaire.split('-')[0];
    const langues = langPrimaire === langBase
      ? Object.freeze([langPrimaire])
      : Object.freeze([langPrimaire, langBase]);
    Object.defineProperty(Navigator.prototype, 'languages', {
      get: natif(() => langues, 'get languages'), configurable: true,
    });
    Object.defineProperty(Navigator.prototype, 'language', {
      get: natif(() => langPrimaire, 'get language'), configurable: true,
    });
  }

  // ─── navigator.platform (doit correspondre à l'OS du profil et au User-Agent) ───
  if (P.platform) {
    Object.defineProperty(Navigator.prototype, 'platform', {
      get: natif(() => P.platform, 'get platform'), configurable: true,
    });
  }

  // ─── navigator.vendor ───
  Object.defineProperty(Navigator.prototype, 'vendor', {
    get: natif(() => 'Google Inc.', 'get vendor'), configurable: true,
  });

  // ─── window.chrome ───
  if (!window.chrome) window.chrome = {};

  // chrome.app — mock complet (absent en headless)
  if (!window.chrome.app) {
    const InstallState = {DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed'};
    const RunningState = {CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run', RUNNING: 'running'};
    window.chrome.app = {
      isInstalled: false,
      InstallState,
      RunningState,
      getDetails: natif(function getDetails() { return null; }, 'getDetails'),
      getIsInstalled: natif(function getIsInstalled() { return false; }, 'getIsInstalled'),
      runningState: natif(function runningState() { return 'cannot_run'; }, 'runningState'),
    };
  }

  // chrome.runtime — connect/sendMessage avec Proxy et messages d'erreur réalistes
  if (!window.chrome.runtime || !window.chrome.runtime.id) {
    const MSG_NO_EXT = 'Could not establish connection. Receiving end does not exist.';
    const makePort = () => {
      const port = {
        name: '', sender: undefined,
        disconnect: natif(function disconnect() {}, 'disconnect'),
        onDisconnect: {addListener: natif(function addListener() {}, 'addListener'),
                       dispatch: natif(function dispatch() {}, 'dispatch'),
                       hasListener: natif(function hasListener() { return false; }, 'hasListener'),
                       hasListeners: natif(function hasListeners() { return false; }, 'hasListeners'),
                       removeListener: natif(function removeListener() {}, 'removeListener')},
        onMessage: {addListener: natif(function addListener() {}, 'addListener'),
                    dispatch: natif(function dispatch() {}, 'dispatch'),
                    hasListener: natif(function hasListener() { return false; }, 'hasListener'),
                    hasListeners: natif(function hasListeners() { return false; }, 'hasListeners'),
                    removeListener: natif(function removeListener() {}, 'removeListener')},
        postMessage: natif(function postMessage() { throw new Error(MSG_NO_EXT); }, 'postMessage'),
      };
      return port;
    };
    window.chrome.runtime = {
      OnInstalledReason: {CHROME_UPDATE: 'chrome_update', INSTALL: 'install',
                          SHARED_MODULE_UPDATE: 'shared_module_update', UPDATE: 'update'},
      OnRestartRequiredReason: {APP_UPDATE: 'app_update', OS_UPDATE: 'os_update', PERIODIC: 'periodic'},
      PlatformArch: {ARM: 'arm', MIPS: 'mips', MIPS64: 'mips64', X86_32: 'x86-32', X86_64: 'x86-64'},
      PlatformNaclArch: {ARM: 'arm', MIPS: 'mips', MIPS64: 'mips64', X86_32: 'x86-32', X86_64: 'x86-64'},
      PlatformOs: {ANDROID: 'android', CROS: 'cros', LINUX: 'linux', MAC: 'mac', OPENBSD: 'openbsd', WIN: 'win'},
      RequestUpdateCheckStatus: {NO_UPDATE: 'no_update', THROTTLED: 'throttled', UPDATE_AVAILABLE: 'update_available'},
      connect: natif(function connect(_extId) { return makePort(); }, 'connect'),
      sendMessage: natif(function sendMessage(_id, _msg, _opts, cb) {
        if (typeof cb === 'function') cb(undefined);
      }, 'sendMessage'),
      id: undefined,
    };
  }

  // chrome.csi — version complète basée sur PerformanceTiming
  if (!window.chrome.csi) {
    window.chrome.csi = natif(function csi() {
      const t = window.performance && window.performance.timing;
      if (!t) return {onloadT: Date.now(), startE: Date.now() - 300, pageT: 300, tran: 15};
      return {
        onloadT: t.domContentLoadedEventEnd || Date.now(),
        startE: t.navigationStart || (Date.now() - 300),
        pageT: Date.now() - (t.navigationStart || (Date.now() - 300)),
        tran: 15,
      };
    }, 'csi');
  }

  // chrome.loadTimes — mock complet basé sur PerformanceTiming
  if (!window.chrome.loadTimes) {
    window.chrome.loadTimes = natif(function loadTimes() {
      const t = window.performance && window.performance.timing;
      if (!t) return {
        commitLoadTime: Date.now() / 1000, connectionInfo: 'http/1.1',
        finishDocumentLoadTime: 0, finishLoadTime: 0, firstPaintAfterLoadTime: 0,
        firstPaintTime: 0, navigationType: 'Other', npnNegotiatedProtocol: 'unknown',
        requestTime: 0, startLoadTime: 0, wasAlternateProtocolAvailable: false,
        wasFetchedViaSpdy: false, wasNpnNegotiated: false,
      };
      const nav = t.navigationStart / 1000;
      return {
        commitLoadTime: (t.responseStart || Date.now()) / 1000,
        connectionInfo: 'http/1.1',
        finishDocumentLoadTime: (t.domContentLoadedEventEnd || Date.now()) / 1000,
        finishLoadTime: (t.loadEventEnd || Date.now()) / 1000,
        firstPaintAfterLoadTime: 0,
        firstPaintTime: (t.domContentLoadedEventEnd || Date.now()) / 1000,
        navigationType: t.redirectCount > 0 ? 'BackForward' : 'Other',
        npnNegotiatedProtocol: 'h2',
        requestTime: nav,
        startLoadTime: nav,
        wasAlternateProtocolAvailable: false,
        wasFetchedViaSpdy: true,
        wasNpnNegotiated: true,
      };
    }, 'loadTimes');
  }
})();
