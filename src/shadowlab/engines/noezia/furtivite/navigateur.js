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
  function natif(fn, nom) { _natifs.set(fn, nom); return fn; }
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
  fauxPlugins.forEach((p, i) => Object.defineProperty(pluginArr, i, {value: p}));
  Object.defineProperty(pluginArr, 'length', {value: fauxPlugins.length});
  pluginArr.item = natif(i => fauxPlugins[i] || null, 'item');
  pluginArr.namedItem = natif(n => fauxPlugins.find(p => p.name === n) || null, 'namedItem');
  pluginArr.refresh = natif(() => {}, 'refresh');
  Object.defineProperty(Navigator.prototype, 'plugins', {
    get: natif(() => pluginArr, 'get plugins'), configurable: true,
  });

  const mimeObjs = fauxPlugins.map(p => p[0]);
  const mimeArr = Object.create(MimeTypeArray.prototype);
  mimeObjs.forEach((m, i) => Object.defineProperty(mimeArr, i, {value: m}));
  Object.defineProperty(mimeArr, 'length', {value: mimeObjs.length});
  mimeArr.item = natif(i => mimeObjs[i] || null, 'item');
  mimeArr.namedItem = natif(t => mimeObjs.find(m => m.type === t) || null, 'namedItem');
  Object.defineProperty(Navigator.prototype, 'mimeTypes', {
    get: natif(() => mimeArr, 'get mimeTypes'), configurable: true,
  });

  // ─── Notification.permission → "default" ───
  try {
    Object.defineProperty(Notification, 'permission', {
      get: natif(() => 'default', 'get permission'), configurable: true,
    });
  } catch(e) {}

  // ─── Permissions API : query('notifications') → 'prompt' ───
  if (navigator.permissions) {
    const origQuery = navigator.permissions.query.bind(navigator.permissions);
    navigator.permissions.query = natif(function query(desc) {
      if (desc && desc.name === 'notifications')
        return Promise.resolve({state: 'prompt', onchange: null});
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

  // ─── window.chrome ───
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
