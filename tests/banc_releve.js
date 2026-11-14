'use strict';
// Banc d'essai de src/shadowlab/public/static/releve.js sous Node (tests/test_public_releve.py) : un navigateur
// factice, des gestes rejoués, les envois relevés. Tout ce que le script ne doit jamais lire (touche, texte, adresse
// ou identifiant d'un élément, cookie, stockage, fonctions à autorisation…) est piégé : lu, cela lève une erreur,
// notée dans `lues`. Sortie : JSON { pages: [{ envois, ecouteurs }], lues, erreurs }.
//   node banc_releve.js <releve.js> pas '{"options": {...}, "pas": [[instant, action, ...], ...]}'
//   node banc_releve.js <releve.js> promenade '{"pages": 150, "duree_ms": 8000, "souris_ms": 16, ...}'
const fs = require('fs');
const vm = require('vm');

const [, , cheminScript, mode, parametres] = process.argv;
const source = fs.readFileSync(cheminScript, 'utf8');
const P = JSON.parse(parametres || '{}');

// Ce que le script ne doit jamais lire : lu, cela lève une erreur, notée.
const INTERDITES = [
  'key', 'code', 'keyCode', 'which', 'charCode', 'char', 'keyIdentifier', 'location', 'value', 'textContent',
  'innerText', 'innerHTML', 'outerHTML', 'id', 'href', 'src', 'alt', 'title', 'className', 'name', 'dataset',
  'data', 'clipboardData', 'getAttribute', 'attributes', 'nodeValue', 'placeholder', 'form', 'selectionStart',
];
const lues = [];
const erreurs = [];
function pieger(objet, noms) {
  for (const nom of noms) {
    Object.defineProperty(objet, nom, {
      configurable: true,
      get() {
        lues.push(nom);
        throw new Error(`lu : ${nom}`);
      },
    });
  }
  return objet;
}
class Element {
  constructor(motifs) {
    this.motifs = motifs;
    pieger(this, INTERDITES);
  }
  correspond(selecteur) {
    return selecteur.split(',').some((s) => this.motifs.some((m) => s.trim().startsWith(m)));
  }
  closest(selecteur) {
    return this.correspond(selecteur) ? this : null;
  }
  matches(selecteur) {
    return this.correspond(selecteur);
  }
}
const SORTES = { autre: [], lien: ['a[href]'], bouton: ['button'], image: ['img'], texte: ['textarea'] };

function fabriquer(options) {
  const jeton = options.jeton === undefined ? 'a'.repeat(32) : options.jeton;
  const ecouteurs = [];
  const envois = [];
  const etat = { maintenant: 0 };
  const doc = pieger(
    {
      visibilityState: 'visible',
      activeElement: null,
      documentElement: { scrollWidth: 1280, scrollHeight: 5000 },
      hasFocus: () => true,
      querySelector: (s) => (s === 'meta[name="sl-session"]' && jeton ? { content: jeton } : null),
      addEventListener: (type, f) => ecouteurs.push({ cible: 'document', type, f }),
    },
    ['cookie', 'getSelection', 'body', 'forms', 'title', 'referrer', 'URL', 'domain', 'execCommand'],
  );
  const env = {
    console,
    Element,
    Blob: class {
      constructor(parties, opts) {
        this.parties = parties;
        this.type = opts && opts.type;
      }
    },
    performance: { now: () => etat.maintenant },
    innerWidth: 1280,
    innerHeight: 800,
    scrollY: 0,
    devicePixelRatio: 2,
    location: { pathname: options.chemin || '/lab/social/fil' },
    matchMedia: (q) => ({ matches: q === '(pointer: fine)' }),
    addEventListener: (type, f) => ecouteurs.push({ cible: 'window', type, f }),
    fetch: (url, o) => {
      envois.push({ url, via: 'fetch', corps: o.body, methode: o.method, keepalive: Boolean(o.keepalive) });
      return Promise.resolve({});
    },
    navigator: pieger(
      {
        sendBeacon: (url, blob) => {
          envois.push({ url, via: 'beacon', corps: blob.parties.join(''), type: blob.type });
          return true;
        },
      },
      ['geolocation', 'mediaDevices', 'clipboard', 'permissions', 'credentials', 'storage', 'serviceWorker',
        'bluetooth', 'usb', 'hid', 'serial', 'wakeLock', 'requestMIDIAccess', 'vibrate'],
    ),
    document: doc,
  };
  env.window = env;
  pieger(env, ['localStorage', 'sessionStorage', 'indexedDB', 'caches', 'getSelection', 'open', 'postMessage',
    'XMLHttpRequest', 'WebSocket', 'EventSource', 'Notification', 'DeviceMotionEvent', 'DeviceOrientationEvent',
    'name', 'opener', 'history', 'cookieStore', 'showOpenFilePicker']);
  const contexte = vm.createContext(env);
  // `window` tel que le script le voit (Node rend le global du contexte, pas l'objet `env`) : cible du focus.
  const fenetre = vm.runInContext('window', contexte);

  function emettre(cible, type, props) {
    const e = pieger({ type, timeStamp: etat.maintenant, ...props }, INTERDITES);
    for (const ecouteur of ecouteurs) {
      if (ecouteur.cible !== cible || ecouteur.type !== type) continue;
      try {
        ecouteur.f(e);
      } catch (erreur) {
        erreurs.push(String(erreur));
      }
    }
  }
  function jouer([t, action, ...a]) {
    etat.maintenant = t;
    switch (action) {
      case 'souris':
        return emettre('window', 'pointermove', { pointerType: a[2] || 'mouse', clientX: a[0], clientY: a[1] });
      case 'clic':
        return emettre('window', 'pointerdown', {
          clientX: a[0], clientY: a[1], button: a[2], target: new Element(SORTES[a[3]]), pointerType: a[4] || 'mouse',
        });
      case 'defiler':
        env.scrollY = a[0];
        return emettre('window', 'scroll', {});
      case 'molette':
        return emettre('window', 'wheel', { deltaX: a[0], deltaY: a[1], deltaMode: a[2] || 0 });
      case 'appui':
        doc.activeElement = a[0] ? new Element(SORTES.texte) : null;
        return emettre('window', 'keydown', { repeat: Boolean(a[1]) });
      case 'relache':
        return emettre('window', 'keyup', {});
      case 'toucher': {
        const point = { clientX: a[1], clientY: a[2] };
        if (a[4] !== undefined) {
          point.radiusX = a[4];
          point.radiusY = a[4];
        }
        if (a[5] !== undefined) point.force = a[5];
        const types = ['touchstart', 'touchmove', 'touchend', 'touchcancel'];
        return emettre('window', types[a[0]], { changedTouches: [point], touches: { length: a[3] } });
      }
      case 'cacher':
        doc.visibilityState = 'hidden';
        return emettre('document', 'visibilitychange', {});
      case 'montrer':
        doc.visibilityState = 'visible';
        return emettre('document', 'visibilitychange', {});
      case 'focus':
        return emettre('window', a[0] ? 'focus' : 'blur', { target: fenetre });
      case 'taille':
        env.innerWidth = a[0];
        env.innerHeight = a[1];
        return emettre('window', 'resize', {});
      case 'soumettre':
        return emettre('document', 'submit', {});
      case 'quitter':
        return emettre('window', 'pagehide', { persisted: false });
      case 'revenir':
        doc.visibilityState = 'visible';
        return emettre('window', 'pageshow', { persisted: true });
      default:
        throw new Error(`action inconnue : ${action}`);
    }
  }
  try {
    vm.runInContext(source, contexte);
  } catch (erreur) {
    erreurs.push(String(erreur));
  }
  return { jouer, envois, ecouteurs, etat };
}

// Générateur pseudo-aléatoire reproductible (mulberry32).
function hasard(graine) {
  let a = graine >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// Une promenade : `pages` pages de `duree_ms` chacune, souris en mouvement continu, défilement, clics, frappe.
function* promenade(p, numero) {
  const alea = hasard(1000 + numero);
  let x = 600;
  let y = 400;
  let defilement = 0;
  const evenements = [];
  for (let t = 0; t < p.duree_ms; t += p.souris_ms) {
    x = Math.max(0, Math.min(1279, x + Math.round((alea() - 0.5) * 16)));
    y = Math.max(0, Math.min(799, y + Math.round((alea() - 0.5) * 16)));
    evenements.push([t, 'souris', x, y]);
  }
  if (p.defilement) {
    const [debut, fin] = p.defilement;
    for (let t = debut; t < Math.min(fin, p.duree_ms); t += 16) {
      defilement += 15;
      evenements.push([t + 1, 'molette', 0, 4 + Math.round(alea() * 26), 0]);
      evenements.push([t + 2, 'defiler', defilement]);
    }
  }
  for (const t of p.clics || []) if (t < p.duree_ms) evenements.push([t, 'clic', x, y, 0, 'lien']);
  if (p.frappe && numero % p.frappe.toutes_les === 0) {
    for (let k = 0, t = p.frappe.debut; k < p.frappe.touches && t < p.duree_ms; k += 1, t += 180) {
      evenements.push([t, 'appui', 1, 0]);
      evenements.push([t + 90, 'relache']);
    }
  }
  evenements.sort((a, b) => a[0] - b[0]);
  yield* evenements;
  yield [p.duree_ms, 'cacher'];
  yield [p.duree_ms + 1, 'quitter'];
}

const sorties = [];
if (mode === 'pas') {
  const page = fabriquer(P.options || {});
  for (const pas of P.pas) page.jouer(pas);
  sorties.push({ envois: page.envois, ecouteurs: page.ecouteurs.length });
} else if (mode === 'promenade') {
  for (let numero = 0; numero < P.pages; numero += 1) {
    const page = fabriquer({ chemin: '/lab/social/p/abc' });
    for (const pas of promenade(P, numero)) page.jouer(pas);
    sorties.push({ envois: page.envois, ecouteurs: page.ecouteurs.length });
  }
} else {
  throw new Error(`mode inconnu : ${mode}`);
}
process.stdout.write(JSON.stringify({ pages: sorties, lues, erreurs }));
