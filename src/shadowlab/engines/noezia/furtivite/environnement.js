// Spoofing environnement : screen dimensions, window chrome gap, WebRTC, battery.
// Dépend de __NOEZIA_PROFIL__ et __NOEZIA_NATIF__ (injectés par navigateur.js).
(() => {
  const P = window.__NOEZIA_PROFIL__;
  if (!P) return;
  const natif = window.__NOEZIA_NATIF__ || (fn => fn);

  try { const h = location.hostname;
    if (h !== 'localhost' && h !== '127.0.0.1' && !h.endsWith('.localhost') && !h.endsWith('.test')) return;
  } catch(e) { return; }

  // ─── Screen dimensions cohérentes avec le profil ───
  if (P.screen_width && P.screen_height) {
    const sw = P.screen_width, sh = P.screen_height;
    const dpr = P.device_pixel_ratio || 1;
    // Barre système : macOS dock ~25px, Windows taskbar ~40px, Linux ~28px
    const barreH = P.platform_name === 'macOS' ? 25 : P.platform_name === 'Windows' ? 40 : 28;
    const aw = sw, ah = sh - barreH;

    for (const [prop, val] of [['width', sw], ['height', sh], ['availWidth', aw], ['availHeight', ah]]) {
      Object.defineProperty(Screen.prototype, prop, {
        get: natif(() => val, 'get ' + prop), configurable: true,
      });
    }
    Object.defineProperty(Screen.prototype, 'colorDepth', {
      get: natif(() => 24, 'get colorDepth'), configurable: true,
    });
    Object.defineProperty(Screen.prototype, 'pixelDepth', {
      get: natif(() => 24, 'get pixelDepth'), configurable: true,
    });
    Object.defineProperty(Window.prototype, 'devicePixelRatio', {
      get: natif(() => dpr, 'get devicePixelRatio'), configurable: true,
    });

    // outerWidth/Height > innerWidth/Height (chrome de fenêtre)
    // macOS : pas de bordure latérale, 28px barre de titre
    // Windows : 8px bordure de chaque côté, 31px titre + 8px bord bas = 39+16
    // Linux : variable, ~37px titre + bordures
    const gapW = P.platform_name === 'macOS' ? 0 : P.platform_name === 'Windows' ? 16 : 2;
    const gapH = P.platform_name === 'macOS' ? 28 : P.platform_name === 'Windows' ? 39 : 37;

    const getOW = natif(function outerWidth() {
      return (window.innerWidth || 0) + gapW;
    }, 'get outerWidth');
    const getOH = natif(function outerHeight() {
      return (window.innerHeight || 0) + gapH;
    }, 'get outerHeight');

    for (const target of [Window.prototype, window]) {
      Object.defineProperty(target, 'outerWidth', {
        get: getOW, configurable: true, enumerable: true,
      });
      Object.defineProperty(target, 'outerHeight', {
        get: getOH, configurable: true, enumerable: true,
      });
    }
  }

  // ─── WebRTC protection : empêcher la fuite d'IP via ICE candidates ───
  if (typeof RTCPeerConnection !== 'undefined') {
    const OrigRTC = RTCPeerConnection;
    const filtrerCandidat = (e, cb) => {
      if (e.candidate && e.candidate.candidate && e.candidate.candidate.includes('host')) return;
      cb.call(this, e);
    };
    const PatchedRTC = natif(function RTCPeerConnection(config, constraints) {
      const clean = config ? {...config, iceServers: []} : config;
      const pc = new OrigRTC(clean, constraints);
      // Filtrer via addEventListener
      const origAddEvent = pc.addEventListener.bind(pc);
      pc.addEventListener = function(type, cb, opts) {
        if (type === 'icecandidate') {
          return origAddEvent(type, (e) => filtrerCandidat(e, cb), opts);
        }
        return origAddEvent(type, cb, opts);
      };
      // Filtrer via onicecandidate (propriété)
      let _userHandler = null;
      Object.defineProperty(pc, 'onicecandidate', {
        get() { return _userHandler; },
        set(cb) {
          _userHandler = cb;
          origAddEvent('icecandidate', (e) => {
            if (typeof cb === 'function') filtrerCandidat(e, cb);
          });
        },
        configurable: true,
      });
      // createDataChannel : vider la description locale des candidats host
      const origLocalDesc = Object.getOwnPropertyDescriptor(
        OrigRTC.prototype, 'localDescription'
      );
      if (origLocalDesc && origLocalDesc.get) {
        Object.defineProperty(pc, 'localDescription', {
          get() {
            const desc = origLocalDesc.get.call(pc);
            if (desc && desc.sdp) {
              const sdp = desc.sdp.replace(/a=candidate:[^\r\n]*host[^\r\n]*/g, '');
              return {type: desc.type, sdp, toJSON: () => ({type: desc.type, sdp})};
            }
            return desc;
          },
          configurable: true,
        });
      }
      return pc;
    }, 'RTCPeerConnection');
    PatchedRTC.prototype = OrigRTC.prototype;
    PatchedRTC.generateCertificate = OrigRTC.generateCertificate;
    window.RTCPeerConnection = PatchedRTC;
    if (window.webkitRTCPeerConnection) window.webkitRTCPeerConnection = PatchedRTC;
  }

  // ─── Battery API : état réaliste et variable ───
  // Un vrai navigateur retourne un niveau de batterie qui change au fil du temps.
  // Valeur statique = signal bot. On simule un desktop branché (le cas le plus courant).
  if (navigator.getBattery) {
    let _bs = (P.audio_seed || 77) >>> 0;
    function _bxr() { _bs ^= _bs << 13; _bs ^= _bs >>> 17; _bs ^= _bs << 5; return (_bs >>> 0) / 0xFFFFFFFF; }
    const isDesktop = (P.platform_name === 'macOS' || P.platform_name === 'Windows');
    const baseLevel = isDesktop ? 1.0 : (0.4 + _bxr() * 0.55);
    const isCharging = isDesktop ? true : (_bxr() > 0.3);

    let _battLevel = baseLevel, _battLastT = Date.now();
    function _battUpdate() {
      const now = Date.now();
      if (now - _battLastT > 5000) {
        _bs ^= _bs << 13; _bs ^= _bs >>> 17; _bs ^= _bs << 5;
        const r = (_bs >>> 0) / 0xFFFFFFFF;
        if (!isDesktop) {
          _battLevel = Math.min(1, Math.max(0.05,
            baseLevel + (r - 0.5) * 0.03));
          _battLevel = Math.round(_battLevel * 100) / 100;
        }
        _battLastT = now;
      }
    }

    const battObj = {
      get charging() { return isCharging; },
      get chargingTime() { return isCharging ? 0 : Infinity; },
      get dischargingTime() { return isCharging ? Infinity : 3600 + Math.floor(_bxr() * 7200); },
      get level() { _battUpdate(); return _battLevel; },
      addEventListener: natif(function addEventListener() {}, 'addEventListener'),
      removeEventListener: natif(function removeEventListener() {}, 'removeEventListener'),
      dispatchEvent: natif(function dispatchEvent() { return true; }, 'dispatchEvent'),
      onchargingchange: null,
      onchargingtimechange: null,
      ondischargingtimechange: null,
      onlevelchange: null,
    };
    Navigator.prototype.getBattery = natif(function getBattery() {
      return Promise.resolve(battObj);
    }, 'getBattery');
  }

  // ─── Connection API : profil réseau crédible, DYNAMIQUE ───
  // Un vrai navigateur fait varier rtt/downlink au fil du temps (fenêtre glissante).
  // Valeurs statiques = signal de bot. On simule la dérive naturelle.
  if (navigator.connection) {
    let _cs = (P.canvas_seed || 42) >>> 0;
    function _cxr() { _cs ^= _cs << 13; _cs ^= _cs >>> 17; _cs ^= _cs << 5; return (_cs >>> 0) / 0xFFFFFFFF; }
    const baseRttChoices = [50, 50, 50, 100, 100, 150];
    const baseDlChoices  = [10, 10, 8.65, 5.6, 3.4, 1.5];
    const cidx = Math.floor(_cxr() * baseRttChoices.length);
    const baseRtt = baseRttChoices[cidx];
    const baseDl  = baseDlChoices[cidx];
    const connType = baseRtt <= 100 ? '4g' : '3g';

    let _lastRtt = baseRtt, _lastDl = baseDl, _lastT = Date.now();
    function _connJitter() {
      const now = Date.now();
      if (now - _lastT > 800) {
        _cs ^= _cs << 13; _cs ^= _cs >>> 17; _cs ^= _cs << 5;
        const r = (_cs >>> 0) / 0xFFFFFFFF;
        _lastRtt = Math.round(baseRtt + (r - 0.5) * 50);
        if (_lastRtt < 0) _lastRtt = 0;
        _lastRtt = Math.round(_lastRtt / 25) * 25;
        _cs ^= _cs << 13; _cs ^= _cs >>> 17; _cs ^= _cs << 5;
        const r2 = (_cs >>> 0) / 0xFFFFFFFF;
        _lastDl = Math.round((baseDl + (r2 - 0.5) * 2) * 100) / 100;
        if (_lastDl < 0.3) _lastDl = 0.3;
        _lastDl = Math.round(_lastDl * 20) / 20;
        _lastT = now;
      }
    }

    const NI = Object.getPrototypeOf(navigator.connection);
    try {
      Object.defineProperty(NI, 'effectiveType', {
        get: natif(() => connType, 'get effectiveType'), configurable: true,
      });
      Object.defineProperty(NI, 'rtt', {
        get: natif(() => { _connJitter(); return _lastRtt; }, 'get rtt'), configurable: true,
      });
      Object.defineProperty(NI, 'downlink', {
        get: natif(() => { _connJitter(); return _lastDl; }, 'get downlink'), configurable: true,
      });
      Object.defineProperty(NI, 'saveData', {
        get: natif(() => false, 'get saveData'), configurable: true,
      });
    } catch(e) {}
  }

  // ─── Intl API : locale cohérente avec navigator.language ───
  if (P.locale) {
    const localeTag = P.locale.replace('_', '-');
    const OrigDTF = Intl.DateTimeFormat;
    const OrigNF = Intl.NumberFormat;

    Intl.DateTimeFormat = natif(function DateTimeFormat(locales, options) {
      const l = locales || localeTag;
      return new OrigDTF(l, options);
    }, 'DateTimeFormat');
    Intl.DateTimeFormat.prototype = OrigDTF.prototype;
    Intl.DateTimeFormat.supportedLocalesOf = OrigDTF.supportedLocalesOf;

    Intl.NumberFormat = natif(function NumberFormat(locales, options) {
      const l = locales || localeTag;
      return new OrigNF(l, options);
    }, 'NumberFormat');
    Intl.NumberFormat.prototype = OrigNF.prototype;
    Intl.NumberFormat.supportedLocalesOf = OrigNF.supportedLocalesOf;
  }
})();
