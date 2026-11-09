// Observateur du laboratoire : lit les propriétés exposées par le navigateur, exécute BotD,
// puis envoie le tout au serveur local (`/lab/collecte`). Rien n'est envoyé ailleurs.
import { load } from './vendor/botd-2.0.0.esm.js';

const jeton = document.querySelector('meta[name="sl-session"]')?.content || '';
const debut = performance.now();
const evenements = { mousemove: 0, click: 0, keydown: 0, scroll: 0, touchstart: 0 };
let premiereInteraction = null;
const delais_souris = [];
let dernierMouvementMs = null;
// Trajectoire spatiale : angles entre segments consécutifs (détection linéarité)
const angles_segments = [];
let dernierePos = null;
let avantDernierePos = null;
// Délais inter-touches clavier (détection rythme de frappe)
const delais_clavier = [];
let dernierKeydownMs = null;
// Scroll / wheel : deltas, timing, directions (détection uniformité)
const delais_scroll = [];
const wheel_deltas = [];
let dernierScrollMs = null;
for (const type of Object.keys(evenements)) {
  addEventListener(type, (e) => {
    const maintenant = performance.now() - debut;
    evenements[type] += 1;
    if (premiereInteraction === null) premiereInteraction = Math.round(maintenant);
    if (type === 'mousemove') {
      if (delais_souris.length < 50 && dernierMouvementMs !== null) {
        delais_souris.push(Math.round((maintenant - dernierMouvementMs) * 100) / 100);
      }
      dernierMouvementMs = maintenant;
      // Collecter les changements d'angle entre 3 points consécutifs
      const pos = { x: e.clientX, y: e.clientY };
      if (avantDernierePos && dernierePos && angles_segments.length < 40) {
        const dx1 = dernierePos.x - avantDernierePos.x;
        const dy1 = dernierePos.y - avantDernierePos.y;
        const dx2 = pos.x - dernierePos.x;
        const dy2 = pos.y - dernierePos.y;
        const len1 = Math.sqrt(dx1 * dx1 + dy1 * dy1);
        const len2 = Math.sqrt(dx2 * dx2 + dy2 * dy2);
        if (len1 > 3 && len2 > 3) {
          const dot = dx1 * dx2 + dy1 * dy2;
          const cos = Math.max(-1, Math.min(1, dot / (len1 * len2)));
          angles_segments.push(Math.round(Math.acos(cos) * 1000) / 1000);
        }
      }
      avantDernierePos = dernierePos;
      dernierePos = pos;
    }
    if (type === 'keydown' && delais_clavier.length < 40) {
      if (dernierKeydownMs !== null) {
        delais_clavier.push(Math.round((maintenant - dernierKeydownMs) * 100) / 100);
      }
      dernierKeydownMs = maintenant;
    }
    if (type === 'scroll' && delais_scroll.length < 50) {
      if (dernierScrollMs !== null) {
        delais_scroll.push(Math.round((maintenant - dernierScrollMs) * 100) / 100);
      }
      dernierScrollMs = maintenant;
    }
  }, { passive: true });
}
// Wheel events : collecter les deltaY pour détecter les deltas uniformes (robot)
addEventListener('wheel', (e) => {
  if (wheel_deltas.length < 50) {
    wheel_deltas.push(Math.round(e.deltaY * 10) / 10);
  }
}, { passive: true });

function envoyer(kind, payload, enFin = false) {
  if (!jeton) return Promise.resolve();
  const corps = JSON.stringify({ kind, page: location.pathname, payload });
  const url = `/lab/collecte?sl=${encodeURIComponent(jeton)}`;
  if (enFin && navigator.sendBeacon) {
    navigator.sendBeacon(url, new Blob([corps], { type: 'application/json' }));
    return Promise.resolve();
  }
  return fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: corps, keepalive: true });
}

async function empreinteCanvas() {
  try {
    const canvas = document.createElement('canvas');
    canvas.width = 220; canvas.height = 40;
    const ctx = canvas.getContext('2d');
    ctx.textBaseline = 'top'; ctx.font = '16px Arial';
    ctx.fillStyle = '#c33'; ctx.fillRect(2, 2, 60, 30);
    ctx.fillStyle = '#123'; ctx.fillText('ShadowLab ✓ 2026', 6, 10);
    const donnees = new TextEncoder().encode(canvas.toDataURL());
    const hache = await crypto.subtle.digest('SHA-256', donnees);
    return Array.from(new Uint8Array(hache)).slice(0, 8).map((o) => o.toString(16).padStart(2, '0')).join('');
  } catch (erreur) {
    return `erreur: ${erreur}`;
  }
}

function webgl() {
  try {
    const gl = document.createElement('canvas').getContext('webgl');
    if (!gl) return { disponible: false };
    const info = gl.getExtension('WEBGL_debug_renderer_info');
    return {
      disponible: true,
      vendor: info ? gl.getParameter(info.UNMASKED_VENDOR_WEBGL) : gl.getParameter(gl.VENDOR),
      renderer: info ? gl.getParameter(info.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER),
    };
  } catch (erreur) {
    return { disponible: false, erreur: String(erreur) };
  }
}

function automation() {
  const indices = {};
  try {
    const cdc = Object.keys(window).filter((k) => k.startsWith('cdc_') || k.startsWith('$cdc_'));
    if (cdc.length) indices.cdc = cdc;
  } catch (_) { /* ignore */ }
  indices.playwright = typeof window.__playwright !== 'undefined';
  indices.selenium = typeof window.__selenium_unwrapped !== 'undefined'
    || typeof window.__webdriver_evaluate !== 'undefined'
    || typeof window.__driver_evaluate !== 'undefined'
    || typeof document.__selenium_unwrapped !== 'undefined';
  try {
    const desc = Object.getOwnPropertyDescriptor(Navigator.prototype, 'webdriver');
    indices.webdriver_patched = !!(desc && typeof desc.get === 'function' && /native code/.test(desc.get.toString()) === false);
  } catch (_) {
    indices.webdriver_patched = 'erreur';
  }
  try {
    indices.permissions_patched = /native code/.test(Notification.permission) === false
      && typeof Notification.permission === 'string';
  } catch (_) { /* ignore */ }
  indices.callPhantom = typeof window.callPhantom !== 'undefined' || typeof window._phantom !== 'undefined';
  return indices;
}

async function permissions() {
  const resultat = { notification: typeof Notification !== 'undefined' ? Notification.permission : 'absent' };
  try {
    resultat.query = (await navigator.permissions.query({ name: 'notifications' })).state;
  } catch (erreur) {
    resultat.query = 'indisponible';
  }
  return resultat;
}

async function botd() {
  try {
    const detecteur = await load({ monitoring: false });
    return detecteur.detect();
  } catch (erreur) {
    return { erreur: String(erreur) };
  }
}

// FingerprintJS n'est lancé que sur les pages d'empreinte : il est coûteux (polices, audio) et fausserait les durées.
const PAGES_FPJS = ['/lab/empreinte', '/lab/detection'];

function resumer(valeur) {
  const texte = typeof valeur === 'string' ? valeur : JSON.stringify(valeur);
  return texte && texte.length > 160 ? `${texte.slice(0, 160)}…` : texte;
}

async function fingerprintjs() {
  if (!PAGES_FPJS.includes(location.pathname)) return null;
  try {
    const { default: FingerprintJS } = await import('./vendor/fingerprintjs-5.3.0.esm.js');
    const agent = await FingerprintJS.load({ monitoring: false });
    const resultat = await agent.get();
    const composants = {};
    for (const [nom, c] of Object.entries(resultat.components)) {
      composants[nom] = 'error' in c ? { erreur: String(c.error) } : { valeur: resumer(c.value), ms: c.duration };
    }
    return {
      visitorId: resultat.visitorId, confidence: resultat.confidence?.score, version: resultat.version, composants,
    };
  } catch (erreur) {
    return { erreur: String(erreur) };
  }
}

function prototypes() {
  const resultats = {};
  try {
    const toStr = Function.prototype.toString;
    resultats.toString_self = toStr.call(toStr);
    resultats.toString_natif = /\[native code\]/.test(resultats.toString_self);
  } catch (_) { resultats.toString_self = 'erreur'; }
  try {
    const desc = Object.getOwnPropertyDescriptor(HTMLCanvasElement.prototype, 'toDataURL');
    resultats.canvas_writable = desc ? desc.writable : 'absent';
    resultats.canvas_configurable = desc ? desc.configurable : 'absent';
    const src = HTMLCanvasElement.prototype.toDataURL.toString();
    resultats.canvas_toString = src.length > 80 ? src.slice(0, 80) : src;
    resultats.canvas_natif = /\[native code\]/.test(src);
  } catch (_) { resultats.canvas_toString = 'erreur'; }
  try {
    const desc = Object.getOwnPropertyDescriptor(Navigator.prototype, 'hardwareConcurrency');
    resultats.hwc_propre = desc ? (typeof desc.get === 'function') : 'absent';
    resultats.hwc_prototype = 'hardwareConcurrency' in Navigator.prototype;
    resultats.hwc_instance = navigator.hasOwnProperty('hardwareConcurrency');
  } catch (_) { /* ignore */ }
  try {
    const gl = document.createElement('canvas').getContext('webgl');
    if (gl) {
      const src = gl.getParameter.toString();
      resultats.webgl_getParameter_natif = /\[native code\]/.test(src);
    }
  } catch (_) { /* ignore */ }
  try {
    const desc = Object.getOwnPropertyDescriptor(navigator, 'plugins');
    resultats.plugins_propre = !!desc;
    if (desc && desc.get) {
      resultats.plugins_getter_natif = /\[native code\]/.test(desc.get.toString());
    }
  } catch (_) { /* ignore */ }
  return resultats;
}

function integrite() {
  const r = {};
  // Vérifier que les fonctions natives ont la bonne longueur (.length)
  try {
    r.toDataURL_length = HTMLCanvasElement.prototype.toDataURL.length;
    r.toDataURL_name = HTMLCanvasElement.prototype.toDataURL.name;
  } catch (_) { /* ignore */ }
  try {
    const gl = document.createElement('canvas').getContext('webgl');
    if (gl) {
      r.getParameter_length = gl.getParameter.length;
      r.getParameter_name = gl.getParameter.name;
    }
  } catch (_) { /* ignore */ }
  try {
    r.toString_length = Function.prototype.toString.length;
    r.toString_name = Function.prototype.toString.name;
  } catch (_) { /* ignore */ }
  // navigator : propriétés propres inattendues
  try {
    r.navigator_own_keys = Object.getOwnPropertyNames(navigator)
      .filter((k) => !['vendorSub', 'productSub', 'vendor'].includes(k));
  } catch (_) { /* ignore */ }
  // Screen : propriétés propres (ne devrait pas en avoir si c'est sur le prototype)
  try {
    r.screen_own_keys = Object.getOwnPropertyNames(screen)
      .filter((k) => ['width', 'height', 'availWidth', 'availHeight', 'colorDepth'].includes(k));
  } catch (_) { /* ignore */ }
  // Stack trace d'un appel à toDataURL sur un objet invalide
  try {
    HTMLCanvasElement.prototype.toDataURL.call({});
  } catch (e) {
    const stack = (e.stack || '').split('\n').slice(0, 5);
    r.toDataURL_error_stack = stack.map((l) => l.trim().slice(0, 120));
  }
  // Error.prepareStackTrace surchargé ? (V8 : utilisé pour filtrer les stack traces)
  try {
    r.prepareStackTrace_modifie = Error.prepareStackTrace !== undefined
      && typeof Error.prepareStackTrace === 'function';
  } catch (_) { /* ignore */ }
  // Vérifier si outerWidth et outerHeight sont sur window (pas définis par un script)
  try {
    const descOW = Object.getOwnPropertyDescriptor(window, 'outerWidth');
    r.outerWidth_propre = !!descOW;
    if (descOW && descOW.get) {
      r.outerWidth_getter_natif = /\[native code\]/.test(descOW.get.toString());
    }
  } catch (_) { /* ignore */ }
  // devicePixelRatio : sur window ou hérité ?
  try {
    r.dpr_propre = window.hasOwnProperty('devicePixelRatio');
    const descDPR = Object.getOwnPropertyDescriptor(window, 'devicePixelRatio');
    if (descDPR && descDPR.get) {
      r.dpr_getter_natif = /\[native code\]/.test(descDPR.get.toString());
    }
  } catch (_) { /* ignore */ }
  return r;
}

function timing() {
  return {
    performance_now: typeof performance.now === 'function',
    date_now: Date.now(),
    perf_timeOrigin: performance.timeOrigin,
    perf_now: performance.now(),
    navigation_type: performance.getEntriesByType?.('navigation')?.[0]?.type || 'unknown',
  };
}

function chromeApis() {
  const r = {};
  // chrome.app
  try {
    r.chrome_app = typeof window.chrome?.app !== 'undefined';
    if (window.chrome?.app) {
      r.chrome_app_isInstalled = window.chrome.app.isInstalled;
      r.chrome_app_getDetails = typeof window.chrome.app.getDetails === 'function';
      r.chrome_app_runningState = typeof window.chrome.app.runningState === 'function';
    }
  } catch (_) { /* ignore */ }
  // chrome.loadTimes
  try {
    r.chrome_loadTimes = typeof window.chrome?.loadTimes === 'function';
    if (window.chrome?.loadTimes) {
      const lt = window.chrome.loadTimes();
      r.loadTimes_keys = Object.keys(lt).sort();
      r.loadTimes_requestTime_positif = lt.requestTime > 0;
      r.loadTimes_connectionInfo = lt.connectionInfo;
    }
  } catch (_) { /* ignore */ }
  // chrome.csi
  try {
    r.chrome_csi = typeof window.chrome?.csi === 'function';
    if (window.chrome?.csi) {
      const csi = window.chrome.csi();
      r.csi_keys = Object.keys(csi).sort();
      r.csi_pageT_positif = csi.pageT > 0;
    }
  } catch (_) { /* ignore */ }
  // chrome.runtime
  try {
    r.chrome_runtime = typeof window.chrome?.runtime !== 'undefined';
    if (window.chrome?.runtime) {
      r.runtime_connect = typeof window.chrome.runtime.connect === 'function';
      r.runtime_sendMessage = typeof window.chrome.runtime.sendMessage === 'function';
      r.runtime_PlatformOs = typeof window.chrome.runtime.PlatformOs !== 'undefined';
    }
  } catch (_) { /* ignore */ }
  return r;
}

function mediaCodecs() {
  const r = {};
  try {
    const v = document.createElement('video');
    r.mp4_avc1 = v.canPlayType('video/mp4; codecs="avc1.42E01E"');
    r.audio_aac = v.canPlayType('audio/aac');
    r.audio_mpeg = v.canPlayType('audio/mpeg');
    r.audio_xm4a = v.canPlayType('audio/x-m4a');
    r.canPlayType_natif = /\[native code\]/.test(HTMLMediaElement.prototype.canPlayType.toString());
  } catch (_) { /* ignore */ }
  return r;
}

function iframeTest() {
  const r = {};
  try {
    const iframe = document.createElement('iframe');
    iframe.srcdoc = '<html></html>';
    iframe.style.display = 'none';
    document.body.appendChild(iframe);
    setTimeout(() => {
      try {
        r.contentWindow_existe = !!iframe.contentWindow;
        if (iframe.contentWindow) {
          r.iframe_chrome = typeof iframe.contentWindow.chrome !== 'undefined';
          r.iframe_self_pas_top = iframe.contentWindow.self !== window.top;
        }
      } catch (_) { /* ignore */ }
      iframe.remove();
    }, 100);
  } catch (_) { /* ignore */ }
  return r;
}

async function webrtcTest() {
  const r = {};
  try {
    if (typeof RTCPeerConnection === 'undefined') { r.disponible = false; return r; }
    r.disponible = true;
    r.rtc_natif = /\[native code\]/.test(RTCPeerConnection.toString());
    const pc = new RTCPeerConnection({iceServers: [{urls: 'stun:stun.l.google.com:19302'}]});
    pc.createDataChannel('test');
    const candidats = [];
    await new Promise((resolve) => {
      const timeout = setTimeout(resolve, 3000);
      pc.onicecandidate = (e) => {
        if (e.candidate) {
          candidats.push({
            type: e.candidate.type,
            protocol: e.candidate.protocol,
            has_ip: /\d+\.\d+\.\d+\.\d+/.test(e.candidate.candidate),
          });
        } else {
          clearTimeout(timeout);
          resolve();
        }
      };
      pc.createOffer().then(o => pc.setLocalDescription(o));
    });
    r.candidats_count = candidats.length;
    r.candidats_host = candidats.filter(c => c.type === 'host').length;
    r.candidats_avec_ip = candidats.filter(c => c.has_ip).length;
    // SDP check
    const sdp = pc.localDescription?.sdp || '';
    r.sdp_host_lines = (sdp.match(/a=candidate:[^\r\n]*host/g) || []).length;
    pc.close();
  } catch (e) { r.erreur = String(e).slice(0, 100); }
  return r;
}

async function headlessSignals() {
  const r = {};
  // document.hasFocus
  try { r.hasFocus = document.hasFocus(); } catch (_) { /* ignore */ }
  // visibilityState
  try { r.visibilityState = document.visibilityState; } catch (_) { /* ignore */ }
  try { r.hidden = document.hidden; } catch (_) { /* ignore */ }
  // webdriver
  try {
    r.webdriver = navigator.webdriver;
    const desc = Object.getOwnPropertyDescriptor(Navigator.prototype, 'webdriver');
    r.webdriver_sur_prototype = !!desc;
    if (desc && desc.get) {
      r.webdriver_getter_natif = /\[native code\]/.test(desc.get.toString());
    }
  } catch (_) { /* ignore */ }
  // speechSynthesis.getVoices
  try {
    if (typeof speechSynthesis !== 'undefined') {
      const voix = speechSynthesis.getVoices();
      r.voices_count = voix.length;
      r.getVoices_natif = /\[native code\]/.test(speechSynthesis.getVoices.toString());
    }
  } catch (_) { /* ignore */ }
  // mediaDevices.enumerateDevices
  try {
    if (navigator.mediaDevices && navigator.mediaDevices.enumerateDevices) {
      const devices = await navigator.mediaDevices.enumerateDevices();
      r.devices_count = devices.length;
      r.devices_kinds = [...new Set(devices.map(d => d.kind))].sort();
    }
  } catch (_) { /* ignore */ }
  // Permissions API étendu (tester plusieurs permissions)
  try {
    if (navigator.permissions) {
      const tests = ['geolocation', 'camera', 'microphone'];
      r.permissions = {};
      for (const perm of tests) {
        try {
          const result = await navigator.permissions.query({name: perm});
          r.permissions[perm] = result.state;
        } catch (_) { r.permissions[perm] = 'erreur'; }
      }
    }
  } catch (_) { /* ignore */ }
  // Notification.requestPermission natif ?
  try {
    if (typeof Notification !== 'undefined') {
      r.requestPermission_natif = /\[native code\]/.test(
        Notification.requestPermission.toString()
      );
    }
  } catch (_) { /* ignore */ }
  return r;
}

function languagesTest() {
  const r = {};
  try {
    r.languages = Array.from(navigator.languages || []);
    r.language = navigator.language;
    r.languages_gelees = Object.isFrozen(navigator.languages);
    const desc = Object.getOwnPropertyDescriptor(Navigator.prototype, 'languages');
    r.languages_sur_prototype = !!desc;
    if (desc && desc.get) {
      r.languages_getter_natif = /\[native code\]/.test(desc.get.toString());
    }
    // Cohérence language ∈ languages
    r.language_dans_languages = navigator.languages?.includes(navigator.language);
  } catch (_) { /* ignore */ }
  // vendor
  try {
    r.vendor = navigator.vendor;
  } catch (_) { /* ignore */ }
  // Intl locale vs navigator.language
  try {
    const intlLocale = new Intl.DateTimeFormat().resolvedOptions().locale;
    r.intl_locale = intlLocale;
    r.intl_timezone = new Intl.DateTimeFormat().resolvedOptions().timeZone;
    const navLang = (navigator.language || '').toLowerCase();
    const intlLang = intlLocale.toLowerCase();
    r.intl_coherent = intlLang.startsWith(navLang.split('-')[0]);
  } catch (_) { /* ignore */ }
  return r;
}

function stackTraceTest() {
  const r = {};
  try {
    const err = new Error('probe');
    r.stack_brut = err.stack ? err.stack.split('\n').slice(0, 6) : [];
    r.contient_patchright = /patchright/i.test(err.stack || '');
    r.contient_playwright = /playwright/i.test(err.stack || '');
    r.contient_puppeteer = /puppeteer/i.test(err.stack || '');
    r.contient_cdp = /__cdp/i.test(err.stack || '');
    r.contient_devtools = /devtools/i.test(err.stack || '');
    // Error.prepareStackTrace natif ?
    r.prepareStackTrace_present = typeof Error.prepareStackTrace === 'function';
    if (r.prepareStackTrace_present) {
      r.prepareStackTrace_natif = /\[native code\]/.test(Error.prepareStackTrace.toString());
    }
    // Tester via eval (injection paths apparaissent souvent là)
    try {
      eval('throw new Error("eval-probe")');
    } catch (e2) {
      r.eval_stack = e2.stack ? e2.stack.split('\n').slice(0, 4) : [];
    }
  } catch (_) { /* ignore */ }
  return r;
}

function automationGlobals() {
  const r = {};
  // Globales d'automation connues
  const SUSPECTS = [
    '__playwright', '__pw_manual', '__playwright_evaluation_script__',
    '__pwright_target__', '__selenium_unwrapped', '__webdriver_evaluate',
    '__driver_evaluate', '__webdriver_script_fn', 'callPhantom', '_phantom',
    '__nightmare', 'domAutomation', 'domAutomationController',
  ];
  r.globales_trouvees = [];
  for (const nom of SUSPECTS) {
    try {
      if (nom in window && window[nom] !== undefined) {
        r.globales_trouvees.push(nom);
      }
    } catch (_) { /* ignore */ }
  }
  // cdc_/\$cdc_ (ChromeDriver)
  try {
    const cdc = Object.keys(window).filter(k => k.startsWith('cdc_') || k.startsWith('$cdc_'));
    if (cdc.length) r.cdc_keys = cdc;
  } catch (_) { /* ignore */ }
  // Noms NOEZIA visibles dans Object.keys ?
  try {
    const noezia = Object.keys(window).filter(k => k.includes('NOEZIA'));
    r.noezia_enumerable = noezia;
  } catch (_) { /* ignore */ }
  // Document markers
  try {
    const docSuspects = ['__selenium_unwrapped', '__webdriver_evaluate', '$chrome_asyncScriptInfo'];
    r.doc_trouvees = docSuspects.filter(n => { try { return n in document; } catch(_) { return false; } });
  } catch (_) { /* ignore */ }
  return r;
}

function cssMediaTest() {
  const r = {};
  try {
    // hover: none = pas de souris (mobile ou headless)
    r.hover_none = window.matchMedia('(hover: none)').matches;
    r.hover_hover = window.matchMedia('(hover: hover)').matches;
    r.pointer_none = window.matchMedia('(pointer: none)').matches;
    r.pointer_fine = window.matchMedia('(pointer: fine)').matches;
    // prefers-color-scheme
    r.prefers_dark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    r.prefers_light = window.matchMedia('(prefers-color-scheme: light)').matches;
    // prefers-reduced-motion
    r.reduced_motion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    // matchMedia natif ?
    r.matchMedia_natif = /\[native code\]/.test(window.matchMedia.toString());
  } catch (_) { /* ignore */ }
  return r;
}

function prototypeChainTest() {
  const r = {};
  // navigator : propriétés propres vs prototype
  try {
    const props = ['webdriver', 'hardwareConcurrency', 'deviceMemory', 'languages', 'language', 'plugins'];
    r.navigator_own = {};
    for (const p of props) {
      const own = Object.getOwnPropertyDescriptor(navigator, p);
      const proto = Object.getOwnPropertyDescriptor(Navigator.prototype, p);
      r.navigator_own[p] = {
        own: !!own,
        prototype: !!proto,
      };
    }
  } catch (_) { /* ignore */ }
  // screen : propres ?
  try {
    r.screen_own_width = screen.hasOwnProperty('width');
    r.screen_own_height = screen.hasOwnProperty('height');
  } catch (_) { /* ignore */ }
  return r;
}

function timingPrecisionTest() {
  const r = {};
  try {
    // Mesurer la précision de performance.now()
    const samples = [];
    let last = performance.now();
    for (let i = 0; i < 20; i++) {
      const now = performance.now();
      if (now !== last) {
        samples.push(now - last);
        last = now;
      }
    }
    r.precision_samples = samples.slice(0, 10);
    // Précision minimale observée (delta minimum non-nul)
    if (samples.length > 0) {
      r.min_delta = Math.min(...samples);
    }
    // performance.now natif ?
    r.perf_now_natif = /\[native code\]/.test(performance.now.toString());
  } catch (_) { /* ignore */ }
  return r;
}

function paintTimingTest() {
  const r = {};
  try {
    const entries = performance.getEntriesByType('paint');
    r.count = entries.length;
    r.entries = entries.map(e => ({name: e.name, startTime: e.startTime}));
    const fp = entries.find(e => e.name === 'first-paint');
    const fcp = entries.find(e => e.name === 'first-contentful-paint');
    r.has_first_paint = !!fp;
    r.has_first_contentful_paint = !!fcp;
    if (fp) r.first_paint_time = fp.startTime;
    if (fcp) r.first_contentful_paint_time = fcp.startTime;
    if (fp && fcp) r.fp_fcp_gap = fcp.startTime - fp.startTime;
    // Vérifier que getEntriesByType est natif
    r.getEntriesByType_natif = /\[native code\]/.test(performance.getEntriesByType.toString());
  } catch (_) { /* ignore */ }
  return r;
}

function performanceMemoryTest() {
  const r = {};
  try {
    if (performance.memory) {
      r.jsHeapSizeLimit = performance.memory.jsHeapSizeLimit;
      r.totalJSHeapSize = performance.memory.totalJSHeapSize;
      r.usedJSHeapSize = performance.memory.usedJSHeapSize;
      // Vérifier getter natif
      const desc = Object.getOwnPropertyDescriptor(performance, 'memory');
      r.memory_propre = !!desc;
      if (desc && desc.get) {
        r.memory_getter_natif = /\[native code\]/.test(desc.get.toString());
      }
    } else {
      r.memory_absent = true;
    }
  } catch (_) { /* ignore */ }
  try {
    r.screenX = window.screenX;
    r.screenY = window.screenY;
  } catch (_) { /* ignore */ }
  return r;
}

function canvasConsistencyTest() {
  const r = {};
  try {
    const c = document.createElement('canvas');
    c.width = 64; c.height = 64;
    const ctx = c.getContext('2d');
    ctx.fillStyle = '#f60';
    ctx.fillRect(0, 0, 32, 32);
    ctx.fillStyle = '#069';
    ctx.fillRect(32, 0, 32, 32);
    ctx.font = '14px Arial';
    ctx.fillText('test', 2, 50);
    const dataUrl1 = c.toDataURL();
    const dataUrl2 = c.toDataURL();
    r.toDataURL_stable = dataUrl1 === dataUrl2;
    const img1 = ctx.getImageData(0, 0, 64, 64);
    const img2 = ctx.getImageData(0, 0, 64, 64);
    let same = true;
    for (let i = 0; i < img1.data.length; i++) {
      if (img1.data[i] !== img2.data[i]) { same = false; break; }
    }
    r.getImageData_stable = same;
    // Vérifier que les mêmes pixels reviennent par les deux APIs
    // (toDataURL encode en PNG, getImageData retourne les pixels bruts — pas directement comparable,
    //  mais la stabilité de chaque API est le signal le plus fiable)
  } catch (_) { /* ignore */ }
  return r;
}

function stackGetterTest() {
  const r = {};
  try {
    const desc = Object.getOwnPropertyDescriptor(Error.prototype, 'stack');
    r.stack_has_getter = !!(desc && desc.get);
    if (desc && desc.get) {
      r.stack_getter_natif = /\[native code\]/.test(desc.get.toString());
    }
    const err = new Error('probe');
    const stack = err.stack || '';
    r.stack_has_patchright = /patchright/i.test(stack);
    r.stack_has_playwright = /playwright/i.test(stack);
    r.stack_has_anonymous = /<anonymous>/.test(stack);
    r.stack_line_count = stack.split('\n').length;
  } catch (_) { /* ignore */ }
  return r;
}

function rafTimingTest() {
  return new Promise(resolve => {
    const r = {};
    const deltas = [];
    let prev = null;
    let count = 0;
    const max = 6;
    function frame(ts) {
      if (prev !== null) deltas.push(ts - prev);
      prev = ts;
      count++;
      if (count < max) {
        requestAnimationFrame(frame);
      } else {
        r.deltas = deltas.map(d => Math.round(d * 100) / 100);
        r.mean_delta = deltas.length ? Math.round(deltas.reduce((a, b) => a + b, 0) / deltas.length * 100) / 100 : 0;
        r.all_zero = deltas.every(d => d === 0);
        r.all_same = deltas.length > 1 && deltas.every(d => d === deltas[0]);
        resolve(r);
      }
    }
    requestAnimationFrame(frame);
  });
}

async function collecter() {
  const nav = navigator;
  return {
    navigateur: {
      userAgent: nav.userAgent,
      platform: nav.platform,
      language: nav.language,
      languages: Array.from(nav.languages || []),
      hardwareConcurrency: nav.hardwareConcurrency ?? 'unknown',
      deviceMemory: nav.deviceMemory ?? 'unknown',
      maxTouchPoints: nav.maxTouchPoints ?? 'unknown',
      webdriver: nav.webdriver,
      cookieEnabled: nav.cookieEnabled,
      pdfViewerEnabled: nav.pdfViewerEnabled ?? 'unknown',
      plugins: nav.plugins ? nav.plugins.length : 'unknown',
      mimeTypes: nav.mimeTypes ? nav.mimeTypes.length : 'unknown',
      userAgentData: nav.userAgentData
        ? { brands: nav.userAgentData.brands, mobile: nav.userAgentData.mobile, platform: nav.userAgentData.platform }
        : null,
    },
    ecran: {
      width: screen.width, height: screen.height, availWidth: screen.availWidth, availHeight: screen.availHeight,
      colorDepth: screen.colorDepth, devicePixelRatio: devicePixelRatio,
    },
    fenetre: { innerWidth, innerHeight, outerWidth, outerHeight },
    fuseau: { zone: Intl.DateTimeFormat().resolvedOptions().timeZone, decalage: new Date().getTimezoneOffset() },
    apis: {
      chrome: typeof window.chrome !== 'undefined',
      bluetooth: 'bluetooth' in nav, usb: 'usb' in nav, serial: 'serial' in nav, hid: 'hid' in nav,
      share: 'share' in nav, credentials: 'credentials' in nav, mediaDevices: 'mediaDevices' in nav,
      speechSynthesis: 'speechSynthesis' in window, serviceWorker: 'serviceWorker' in nav,
    },
    permissions: await permissions(),
    webgl: webgl(),
    canvas: await empreinteCanvas(),
    prototypes: prototypes(),
    integrite: integrite(),
    timing: timing(),
    chrome_apis: chromeApis(),
    media_codecs: mediaCodecs(),
    iframe_test: iframeTest(),
    languages_test: languagesTest(),
    webrtc_test: await webrtcTest(),
    headless_signals: await headlessSignals(),
    stack_trace_test: stackTraceTest(),
    performance_memory: performanceMemoryTest(),
    paint_timing: paintTimingTest(),
    automation_globals: automationGlobals(),
    css_media: cssMediaTest(),
    prototype_chain: prototypeChainTest(),
    timing_precision: timingPrecisionTest(),
    canvas_consistency: canvasConsistencyTest(),
    stack_getter: stackGetterTest(),
    raf_timing: await rafTimingTest(),
    automation: automation(),
    botd: await botd(),
    fpjs: await fingerprintjs(),
    duree_collecte_ms: Math.round(performance.now() - debut),
  };
}

async function demarrer() {
  const empreinte = await collecter();
  window.__shadowlab = empreinte;
  document.dispatchEvent(new CustomEvent('shadowlab:empreinte', { detail: empreinte }));
  await envoyer('empreinte', empreinte);
  const marque = document.createElement('div');
  marque.id = 'observation-envoyee';
  marque.hidden = true;
  document.body.append(marque);
}

addEventListener('pagehide', () => {
  envoyer('comportement', {
    evenements, premiere_interaction_ms: premiereInteraction, duree_page_ms: Math.round(performance.now() - debut),
    delais_souris_ms: delais_souris,
    angles_segments: angles_segments,
    delais_clavier_ms: delais_clavier,
    delais_scroll_ms: delais_scroll,
    wheel_deltas: wheel_deltas,
  }, true);
});

demarrer();
