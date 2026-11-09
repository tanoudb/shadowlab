// Observateur du laboratoire : lit les propriétés exposées par le navigateur, exécute BotD,
// puis envoie le tout au serveur local (`/lab/collecte`). Rien n'est envoyé ailleurs.
import { load } from './vendor/botd-2.0.0.esm.js';

const jeton = document.querySelector('meta[name="sl-session"]')?.content || '';
const debut = performance.now();
const evenements = { mousemove: 0, click: 0, keydown: 0, scroll: 0, touchstart: 0 };
let premiereInteraction = null;
const delais_souris = [];
let dernierMouvementMs = null;
for (const type of Object.keys(evenements)) {
  addEventListener(type, () => {
    const maintenant = performance.now() - debut;
    evenements[type] += 1;
    if (premiereInteraction === null) premiereInteraction = Math.round(maintenant);
    if (type === 'mousemove' && delais_souris.length < 50) {
      if (dernierMouvementMs !== null) {
        delais_souris.push(Math.round((maintenant - dernierMouvementMs) * 100) / 100);
      }
      dernierMouvementMs = maintenant;
    }
  }, { passive: true });
}

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

function timing() {
  return {
    performance_now: typeof performance.now === 'function',
    date_now: Date.now(),
    perf_timeOrigin: performance.timeOrigin,
    perf_now: performance.now(),
    navigation_type: performance.getEntriesByType?.('navigation')?.[0]?.type || 'unknown',
  };
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
    timing: timing(),
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
  }, true);
});

demarrer();
