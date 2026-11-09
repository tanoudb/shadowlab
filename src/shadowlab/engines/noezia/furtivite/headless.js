// Contre-mesures spécifiques à l'exécution headless.
// Corrige les comportements qui trahissent un environnement sans écran.
// Dépend de __NOEZIA_PROFIL__ et __NOEZIA_NATIF__.
(() => {
  const P = window.__NOEZIA_PROFIL__;
  if (!P) return;
  const natif = window.__NOEZIA_NATIF__ || (fn => fn);

  try { const h = location.hostname;
    if (h !== 'localhost' && h !== '127.0.0.1' && !h.endsWith('.localhost') && !h.endsWith('.test')) return;
  } catch(e) { return; }

  // ─── navigator.webdriver → false (défense redondante après --disable-blink-features) ───
  try {
    Object.defineProperty(Navigator.prototype, 'webdriver', {
      get: natif(() => false, 'get webdriver'), configurable: true,
    });
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
      get: natif(() => 'visible', 'get visibilityState'), configurable: true,
    });
    Object.defineProperty(Document.prototype, 'hidden', {
      get: natif(() => false, 'get hidden'), configurable: true,
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
  try {
    const sx = 22 + Math.floor(Math.random() * 200);
    const sy = 25 + Math.floor(Math.random() * 100);
    Object.defineProperty(window, 'screenX', {
      get: natif(() => sx, 'get screenX'), configurable: true,
    });
    Object.defineProperty(window, 'screenY', {
      get: natif(() => sy, 'get screenY'), configurable: true,
    });
    Object.defineProperty(window, 'screenLeft', {
      get: natif(() => sx, 'get screenLeft'), configurable: true,
    });
    Object.defineProperty(window, 'screenTop', {
      get: natif(() => sy, 'get screenTop'), configurable: true,
    });
  } catch(e) {}
})();
