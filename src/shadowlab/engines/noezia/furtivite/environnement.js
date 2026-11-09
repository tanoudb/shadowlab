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

    Object.defineProperty(Window.prototype, 'outerWidth', {
      get: natif(function outerWidth() {
        return (window.innerWidth || 0) + gapW;
      }, 'get outerWidth'),
      configurable: true,
    });
    Object.defineProperty(Window.prototype, 'outerHeight', {
      get: natif(function outerHeight() {
        return (window.innerHeight || 0) + gapH;
      }, 'get outerHeight'),
      configurable: true,
    });
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

  // ─── Battery API : retourner un état réaliste ───
  if (navigator.getBattery) {
    Navigator.prototype.getBattery = natif(function getBattery() {
      return Promise.resolve({
        charging: true,
        chargingTime: 0,
        dischargingTime: Infinity,
        level: 1.0,
        addEventListener: natif(function addEventListener() {}, 'addEventListener'),
        removeEventListener: natif(function removeEventListener() {}, 'removeEventListener'),
        dispatchEvent: natif(function dispatchEvent() { return true; }, 'dispatchEvent'),
        onchargingchange: null,
        onchargingtimechange: null,
        ondischargingtimechange: null,
        onlevelchange: null,
      });
    }, 'getBattery');
  }

  // ─── Connection API : profil réseau crédible ───
  if (navigator.connection) {
    const conn = navigator.connection;
    try {
      Object.defineProperty(conn, 'effectiveType', {
        get: natif(() => '4g', 'get effectiveType'), configurable: true,
      });
      Object.defineProperty(conn, 'rtt', {
        get: natif(() => 50, 'get rtt'), configurable: true,
      });
      Object.defineProperty(conn, 'downlink', {
        get: natif(() => 10, 'get downlink'), configurable: true,
      });
      Object.defineProperty(conn, 'saveData', {
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
