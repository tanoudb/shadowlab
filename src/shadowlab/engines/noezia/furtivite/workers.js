// Interception des Web Workers pour propager les patches navigator.
// Un Worker a son propre scope global : addInitScript ne s'y applique pas.
// Un détecteur peut lire hardwareConcurrency/deviceMemory/platform dans un Worker
// et comparer avec les valeurs du main thread — la moindre différence = bot.
//
// Stratégie : intercepter le constructeur Worker/SharedWorker, lire le script
// source via fetch, préfixer notre prologue, et créer un Blob URL à la place.
(() => {
  const P = window.__NOEZIA_PROFIL__;
  if (!P) return;
  const natif = window.__NOEZIA_NATIF__ || (fn => fn);

  try { const h = location.hostname;
    if (h !== 'localhost' && h !== '127.0.0.1' && !h.endsWith('.localhost') && !h.endsWith('.test')) return;
  } catch(e) { return; }

  const PROLOGUE = `
(function() {
  var _hc = ${P.hardware_concurrency || 'undefined'};
  var _dm = ${P.device_memory || 'undefined'};
  var _pf = ${JSON.stringify(P.platform || '')};
  var _pn = ${JSON.stringify(P.platform_name || '')};
  var NP = Object.getPrototypeOf(navigator);
  if (_hc !== undefined) {
    var getHC = function() { return _hc; };
    Object.defineProperty(NP, 'hardwareConcurrency', {
      get: getHC, configurable: true, enumerable: true,
    });
    Object.defineProperty(navigator, 'hardwareConcurrency', {
      get: getHC, configurable: true, enumerable: true,
    });
  }
  if (_dm !== undefined) {
    var getDM = function() { return _dm; };
    Object.defineProperty(NP, 'deviceMemory', {
      get: getDM, configurable: true, enumerable: true,
    });
    Object.defineProperty(navigator, 'deviceMemory', {
      get: getDM, configurable: true, enumerable: true,
    });
  }
  if (_pf) {
    Object.defineProperty(NP, 'platform', {
      get: function() { return _pf; }, configurable: true,
    });
  }
  if (_pn) {
    try {
      var ua = navigator.userAgentData;
      if (ua) {
        Object.defineProperty(navigator, 'userAgentData', {
          get: function() {
            return new Proxy(ua, {
              get: function(t, p) {
                if (p === 'platform') return _pn;
                var v = Reflect.get(t, p);
                return typeof v === 'function' ? v.bind(t) : v;
              }
            });
          }, configurable: true,
        });
      }
    } catch(e) {}
  }
})();
`;

  const OrigWorker = window.Worker;
  if (!OrigWorker) return;

  function _wrapBlobURL(scriptURL) {
    if (typeof scriptURL === 'string' && scriptURL.startsWith('blob:')) {
      return scriptURL;
    }
    return null;
  }

  function _patchedWorker(scriptURL, options) {
    if (scriptURL instanceof URL) scriptURL = scriptURL.href;
    if (typeof scriptURL !== 'string') return new OrigWorker(scriptURL, options);

    if (options && options.type === 'module') {
      const wrapper = `${PROLOGUE}\nimport ${JSON.stringify(scriptURL)};`;
      const blob = new Blob([wrapper], {type: 'application/javascript'});
      const blobURL = URL.createObjectURL(blob);
      return new OrigWorker(blobURL, options);
    }

    if (scriptURL.startsWith('blob:')) {
      try {
        const xhr = new XMLHttpRequest();
        xhr.open('GET', scriptURL, false);
        xhr.send();
        if (xhr.status === 200) {
          const patched = PROLOGUE + '\n' + xhr.responseText;
          const blob = new Blob([patched], {type: 'application/javascript'});
          const newURL = URL.createObjectURL(blob);
          return new OrigWorker(newURL, options);
        }
      } catch(e) {}
      return new OrigWorker(scriptURL, options);
    }

    const importWrapper = PROLOGUE + '\nimportScripts(' + JSON.stringify(scriptURL) + ');';
    const blob = new Blob([importWrapper], {type: 'application/javascript'});
    const blobURL = URL.createObjectURL(blob);
    return new OrigWorker(blobURL, options);
  }

  window.Worker = natif(function Worker(scriptURL, options) {
    return _patchedWorker(scriptURL, options);
  }, 'Worker');
  window.Worker.prototype = OrigWorker.prototype;

  const OrigShared = window.SharedWorker;
  if (OrigShared) {
    window.SharedWorker = natif(function SharedWorker(scriptURL, options) {
      if (scriptURL instanceof URL) scriptURL = scriptURL.href;
      if (typeof scriptURL !== 'string') return new OrigShared(scriptURL, options);

      if (options && typeof options === 'object' && options.type === 'module') {
        const wrapper = `${PROLOGUE}\nimport ${JSON.stringify(scriptURL)};`;
        const blob = new Blob([wrapper], {type: 'application/javascript'});
        const blobURL = URL.createObjectURL(blob);
        return new OrigShared(blobURL, options);
      }

      const importWrapper = PROLOGUE + '\nimportScripts(' + JSON.stringify(scriptURL) + ');';
      const blob = new Blob([importWrapper], {type: 'application/javascript'});
      const blobURL = URL.createObjectURL(blob);
      return new OrigShared(blobURL, options);
    }, 'SharedWorker');
    window.SharedWorker.prototype = OrigShared.prototype;
  }
})();
