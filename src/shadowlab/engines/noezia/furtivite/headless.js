// Contre-mesures spécifiques à l'exécution headless.
// Corrige les comportements qui trahissent un environnement sans écran.
// Dépend de __NOEZIA_PROFIL__ et __NOEZIA_NATIF__.
(() => {
  const P = window.__NOEZIA_PROFIL__;
  if (!P) return;
  const natif = window.__NOEZIA_NATIF__ || (fn => fn);


  // ─── navigator.webdriver : suppression complète ───
  // fpCollect vérifie `'webdriver' in navigator` (présence, pas valeur).
  // Même avec value=false, `in` retourne true → fpscanner.WEBDRIVER FAIL.
  // Supprimer du prototype : navigator.webdriver → undefined (falsy, passe tous les tests).
  try {
    delete Navigator.prototype.webdriver;
    if ('webdriver' in navigator) {
      Object.defineProperty(Navigator.prototype, 'webdriver', {
        get: natif(() => undefined, 'get webdriver', Navigator),
        configurable: true,
      });
      delete Navigator.prototype.webdriver;
    }
  } catch(e) {}

  // ─── document.hasFocus() → true (headless renvoie false) ───
  try {
    Document.prototype.hasFocus = natif(function hasFocus() {
      return true;
    }, 'hasFocus');
  } catch(e) {}

  // ─── document.visibilityState / hidden (headless : 'hidden') ───
  try {
    Object.defineProperty(Document.prototype, 'visibilityState', {
      get: natif(() => 'visible', 'get visibilityState', Document), configurable: true,
    });
    Object.defineProperty(Document.prototype, 'hidden', {
      get: natif(() => false, 'get hidden', Document), configurable: true,
    });
  } catch(e) {}

  // ─── speechSynthesis.getVoices() (headless : liste vide) ───
  if (typeof speechSynthesis !== 'undefined') {
    try {
      const os = P.platform_name || 'macOS';
      const voix = os === 'macOS' ? [
        {name: 'Samantha', lang: 'en-US', localService: true, default: true},
        {name: 'Alex', lang: 'en-US', localService: true, default: false},
        {name: 'Thomas', lang: 'fr-FR', localService: true, default: false},
        {name: 'Daniel', lang: 'en-GB', localService: true, default: false},
      ] : os === 'Windows' ? [
        {name: 'Microsoft David - English (United States)', lang: 'en-US', localService: true, default: true},
        {name: 'Microsoft Zira - English (United States)', lang: 'en-US', localService: true, default: false},
        {name: 'Microsoft Paul - French (France)', lang: 'fr-FR', localService: true, default: false},
      ] : [
        {name: 'English (America)', lang: 'en-US', localService: true, default: true},
        {name: 'French (France)', lang: 'fr-FR', localService: true, default: false},
      ];
      const fauxVoix = voix.map(v => {
        const sv = Object.create(SpeechSynthesisVoice.prototype);
        Object.defineProperties(sv, {
          name:         {get: natif(() => v.name, 'get name'), enumerable: true},
          lang:         {get: natif(() => v.lang, 'get lang'), enumerable: true},
          localService: {get: natif(() => v.localService, 'get localService'), enumerable: true},
          voiceURI:     {get: natif(() => v.name, 'get voiceURI'), enumerable: true},
          default:      {get: natif(() => v.default, 'get default'), enumerable: true},
        });
        return sv;
      });
      speechSynthesis.getVoices = natif(function getVoices() {
        return fauxVoix;
      }, 'getVoices');
    } catch(e) {}
  }

  // ─── navigator.mediaDevices.enumerateDevices() (headless : vide) ───
  if (navigator.mediaDevices && navigator.mediaDevices.enumerateDevices) {
    const origEnum = navigator.mediaDevices.enumerateDevices.bind(navigator.mediaDevices);
    navigator.mediaDevices.enumerateDevices = natif(async function enumerateDevices() {
      const vrais = await origEnum();
      if (vrais.length > 0) return vrais;
      return [
        {deviceId: '', groupId: 'default', kind: 'audioinput', label: ''},
        {deviceId: '', groupId: 'default', kind: 'videoinput', label: ''},
        {deviceId: '', groupId: 'default', kind: 'audiooutput', label: ''},
      ];
    }, 'enumerateDevices');
  }

  // ─── Notification.requestPermission (headless le refuse) ───
  try {
    if (typeof Notification !== 'undefined') {
      Notification.requestPermission = natif(function requestPermission(cb) {
        const result = Promise.resolve('default');
        if (typeof cb === 'function') cb('default');
        return result;
      }, 'requestPermission');
    }
  } catch(e) {}

  // ─── performance.memory (headless a des valeurs différentes) ───
  try {
    if (performance && performance.memory) {
      const origMemory = performance.memory;
      const fauxMemory = {
        get jsHeapSizeLimit()  { return 4294705152; },
        get totalJSHeapSize()  { return origMemory.totalJSHeapSize || 35000000; },
        get usedJSHeapSize()   { return origMemory.usedJSHeapSize  || 25000000; },
      };
      Object.setPrototypeOf(fauxMemory, origMemory.constructor ? origMemory.constructor.prototype : Object.prototype);
      Object.defineProperty(performance, 'memory', {
        get: natif(() => fauxMemory, 'get memory'), configurable: true,
      });
    }
  } catch(e) {}

  // ─── navigator.scheduling (présent uniquement en headless/test) ───
  try {
    if (navigator.scheduling) {
      delete navigator.scheduling;
    }
  } catch(e) {}

  // ─── window.screenX / screenY (headless : souvent 0,0 — un vrai navigateur a un offset) ───
  // Déterministe par profil (canvas_seed) pour rester stable entre les pages d'une même session.
  try {
    let _ws = (P.canvas_seed || 77) >>> 0;
    function _wxr() { _ws ^= _ws << 13; _ws ^= _ws >>> 17; _ws ^= _ws << 5; return (_ws >>> 0) / 0xFFFFFFFF; }
    const sx = 22 + Math.floor(_wxr() * 200);
    const sy = 25 + Math.floor(_wxr() * 100);
    const getSX = natif(() => sx, 'get screenX', Window);
    const getSY = natif(() => sy, 'get screenY', Window);
    const getSL = natif(() => sx, 'get screenLeft', Window);
    const getST = natif(() => sy, 'get screenTop', Window);
    for (const target of [Window.prototype, window]) {
      Object.defineProperty(target, 'screenX', {
        get: getSX, configurable: true, enumerable: true,
      });
      Object.defineProperty(target, 'screenY', {
        get: getSY, configurable: true, enumerable: true,
      });
      Object.defineProperty(target, 'screenLeft', {
        get: getSL, configurable: true, enumerable: true,
      });
      Object.defineProperty(target, 'screenTop', {
        get: getST, configurable: true, enumerable: true,
      });
    }
  } catch(e) {}

  // ─── PerformancePaintTiming (headless peut manquer FP/FCP ou les avoir à t=0) ───
  // Un vrai navigateur a toujours FirstPaint et FirstContentfulPaint avec des durées > 0.
  // On s'assure que ces entrées existent avec des valeurs crédibles.
  try {
    const origGetEntries = performance.getEntriesByType.bind(performance);
    const origGetAll = performance.getEntries.bind(performance);
    let _paintPatched = null;

    function _ensurePaintEntries(entries) {
      const hasFP = entries.some(e => e.entryType === 'paint' && e.name === 'first-paint');
      const hasFCP = entries.some(e => e.entryType === 'paint' && e.name === 'first-contentful-paint');
      if (hasFP && hasFCP) return entries;

      if (!_paintPatched) {
        const navStart = performance.timing ? performance.timing.navigationStart : (performance.timeOrigin || 0);
        const baseDelay = 80 + Math.floor(_wxr() * 200);
        _paintPatched = [];
        if (!hasFP) {
          _paintPatched.push({
            name: 'first-paint',
            entryType: 'paint',
            startTime: baseDelay,
            duration: 0,
            toJSON() { return {name: this.name, entryType: this.entryType, startTime: this.startTime, duration: 0}; },
          });
        }
        if (!hasFCP) {
          _paintPatched.push({
            name: 'first-contentful-paint',
            entryType: 'paint',
            startTime: baseDelay + 5 + Math.floor(_wxr() * 30),
            duration: 0,
            toJSON() { return {name: this.name, entryType: this.entryType, startTime: this.startTime, duration: 0}; },
          });
        }
      }
      return [...entries, ..._paintPatched];
    }

    performance.getEntriesByType = natif(function getEntriesByType(type) {
      const entries = origGetEntries(type);
      if (type === 'paint') return _ensurePaintEntries(entries);
      return entries;
    }, 'getEntriesByType');

    performance.getEntries = natif(function getEntries() {
      const entries = origGetAll();
      return _ensurePaintEntries(entries);
    }, 'getEntries');

    // PerformanceObserver : si un observateur demande 'paint', lui donner nos entrées
    if (typeof PerformanceObserver !== 'undefined') {
      const OrigPO = PerformanceObserver;
      const PatchedPO = natif(function PerformanceObserver(callback) {
        const wrappedCb = (list, observer) => {
          const origEntries = list.getEntries();
          const patched = _ensurePaintEntries(origEntries);
          if (patched !== origEntries && patched.length > origEntries.length) {
            const fakeList = {
              getEntries: () => patched,
              getEntriesByType: (t) => patched.filter(e => e.entryType === t),
              getEntriesByName: (n) => patched.filter(e => e.name === n),
            };
            callback(fakeList, observer);
          } else {
            callback(list, observer);
          }
        };
        return new OrigPO(wrappedCb);
      }, 'PerformanceObserver');
      PatchedPO.prototype = OrigPO.prototype;
      PatchedPO.supportedEntryTypes = OrigPO.supportedEntryTypes;
      window.PerformanceObserver = PatchedPO;
    }
  } catch(e) {}
})();
