// Relevé enrichi du site public « Humain ou robot ? » (D-76). Servi par l'application publique seulement, et chargé
// seulement pendant une session consentie, sur les pages des deux sites de démonstration. L'observateur du labo
// (site/static/observateur.js) ne change pas : ce script s'y ajoute.
//
// Il relève des gestes sous forme de NOMBRES entiers seulement et les envoie au même point d'entrée que
// l'observateur (`/lab/collecte`, même jeton de session, même forme { kind, page, payload }), avec la nature
// `trace` : quand la page passe à l'arrière-plan ou qu'on la quitte (par sendBeacon), et par morceaux quand un
// tampon est plein. Les instants sont en millisecondes depuis l'ouverture de la page ; dans chaque liste, une ligne
// est écrite en différence avec la précédente (l'instant, et la position pour la souris, le défilement et le
// toucher), pour rester petite. La notice décrit chaque clé, dans les deux langues.
//
// Limites dures, vérifiées par tests/test_public_releve.py : ce script ne lit jamais quelle touche est frappée, ni
// ce qui est tapé, copié ou sélectionné, ni le texte, l'adresse ou l'identifiant d'un élément (seulement sa sorte,
// dans une liste fermée) ; il n'appelle aucune fonction qui demande une autorisation ; il n'écrit rien dans le
// navigateur ; il n'envoie rien ailleurs qu'au point d'entrée de ce site ; sans jeton de session, il ne fait rien.
(() => {
  'use strict';
  const jeton = document.querySelector('meta[name="sl-session"]')?.content || '';
  if (!jeton) return; // hors session : aucun écouteur, aucun envoi

  const VERSION = 1;
  const ADRESSE = '/lab/collecte?sl=';
  const PERIODE_MS = 1000 / 30; // flux échantillonnés : 30 relevés par seconde au plus
  const ENVOIS_PAR_PAGE = 60;
  const TAMPON_PLEIN = 0;
  const ARRIERE_PLAN = 1;
  const SORTIE = 2;
  // Les clés de l'envoi « trace », ici et nulle part ailleurs : la charge est construite à partir de cette table, et
  // la notice décrit chaque clé (test clé par clé). Un nombre seul : null. Une liste : [nombres par ligne, lignes par
  // envoi, lignes par page, colonnes écrites en différence avec la ligne précédente].
  const CLES = Object.freeze({
    version: null,
    morceau: null,
    raison: null,
    instant_ms: null,
    cadre: null,
    ecartes: null,
    souris: [3, 600, 9000, [0, 1, 2]],
    clics: [6, 100, 600, [0]],
    defilement: [2, 300, 4500, [0, 1]],
    molette: [4, 300, 4500, [0]],
    clavier_appuis: [2, 200, 3000, [0]],
    clavier_relaches: [1, 200, 3000, [0]],
    tactile: [7, 300, 4500, [0, 1, 2]],
    premier_plan: [2, 50, 200, [0]],
    focus: [2, 50, 200, [0]],
    redimensionnements: [3, 50, 200, [0]],
  });
  // Sorte de l'élément visé par un clic, liste fermée : 0 autre, 1 lien, 2 bouton, 3 image, 4 zone de texte.
  const ZONE_DE_TEXTE =
    'textarea, [contenteditable]:not([contenteditable="false"]), input:not([type="button"], [type="submit"], ' +
    '[type="reset"], [type="checkbox"], [type="radio"], [type="image"], [type="hidden"], [type="range"], ' +
    '[type="color"], [type="file"])';
  const BOUTON = 'button, input, select, summary, label, [role="button"]';
  const IMAGE = 'img, picture, svg, video, canvas';
  const POINTEURS = { mouse: 1, pen: 2, touch: 3 }; // 0 : inconnu

  const tampons = {};
  const comptes = {};
  for (const [cle, regle] of Object.entries(CLES)) {
    if (regle) {
      tampons[cle] = [];
      comptes[cle] = 0;
    }
  }
  const derniers = {};
  let morceau = 0;
  let ecartes = 0;
  let fini = false;

  function sorte(cible) {
    if (!(cible instanceof Element)) return 0;
    if (cible.closest(ZONE_DE_TEXTE)) return 4;
    if (cible.closest(BOUTON)) return 2;
    if (cible.closest('a[href]')) return 1;
    if (cible.closest(IMAGE)) return 3;
    return 0;
  }

  // Une ligne dans le tampon de `cle`, si le plafond de la page le permet ; tampon plein, un morceau part.
  function relever(cle, ligne) {
    if (fini) return;
    const [, parEnvoi, parPage] = CLES[cle];
    if (comptes[cle] >= parPage || morceau >= ENVOIS_PAR_PAGE) {
      ecartes += 1;
      return;
    }
    comptes[cle] += 1;
    tampons[cle].push(ligne);
    if (tampons[cle].length >= parEnvoi) envoyer(TAMPON_PLEIN);
  }

  // Flux échantillonné : un relevé par trentième de seconde au plus (le premier geste de chaque trentième).
  function echantillon(flux, instant) {
    const trentieme = Math.floor(instant / PERIODE_MS);
    if (trentieme <= (derniers[flux] ?? -1)) return false;
    derniers[flux] = trentieme;
    return true;
  }

  // Le tampon en une liste plate d'entiers ; la première ligne en valeurs, les suivantes en différences.
  function encoder(cle) {
    const [largeur, , , differences] = CLES[cle];
    const sortie = [];
    let precedente = null;
    for (const ligne of tampons[cle]) {
      const entiers = ligne.map((nombre) => Math.round(nombre));
      for (let i = 0; i < largeur; i += 1) {
        sortie.push(precedente && differences.includes(i) ? entiers[i] - precedente[i] : entiers[i]);
      }
      precedente = entiers;
    }
    tampons[cle] = [];
    return sortie;
  }

  function cadre() {
    const racine = document.documentElement;
    const pointeur = matchMedia('(pointer: fine)').matches ? 1 : matchMedia('(pointer: coarse)').matches ? 2 : 0;
    const mesures = [innerWidth, innerHeight, racine.scrollWidth, racine.scrollHeight, scrollY, devicePixelRatio * 100];
    return [...mesures, pointeur].map((nombre) => Math.round(nombre));
  }

  function charge(raison) {
    const nombres = { version: VERSION, morceau, raison, instant_ms: Math.round(performance.now()), cadre: cadre(), ecartes };
    return Object.fromEntries(Object.keys(CLES).map((cle) => [cle, CLES[cle] ? encoder(cle) : nombres[cle]]));
  }

  function envoyer(raison) {
    if (morceau >= ENVOIS_PAR_PAGE || !Object.values(tampons).some((tampon) => tampon.length)) return;
    const corps = JSON.stringify({ kind: 'trace', page: location.pathname, payload: charge(raison) });
    morceau += 1;
    const adresse = ADRESSE + encodeURIComponent(jeton);
    if (raison !== TAMPON_PLEIN && navigator.sendBeacon) {
      navigator.sendBeacon(adresse, new Blob([corps], { type: 'application/json' }));
    } else {
      fetch(adresse, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: corps }).catch(() => {});
    }
  }

  const options = { capture: true, passive: true };
  addEventListener('pointermove', (e) => {
    if (e.pointerType === 'touch' || !echantillon('souris', e.timeStamp)) return;
    relever('souris', [e.timeStamp, e.clientX, e.clientY]);
  }, options);
  addEventListener('pointerdown', (e) => {
    relever('clics', [e.timeStamp, e.clientX, e.clientY, e.button, sorte(e.target), POINTEURS[e.pointerType] || 0]);
  }, options);
  addEventListener('scroll', (e) => {
    if (echantillon('defilement', e.timeStamp)) relever('defilement', [e.timeStamp, scrollY]);
  }, { passive: true });
  addEventListener('wheel', (e) => {
    const derniere = tampons.molette[tampons.molette.length - 1];
    if (derniere && e.timeStamp - derniere[0] < PERIODE_MS) {
      derniere[1] += e.deltaX; // pas cumulés sur un trentième de seconde au plus
      derniere[2] += e.deltaY;
      return;
    }
    relever('molette', [e.timeStamp, e.deltaX, e.deltaY, e.deltaMode]);
  }, options);
  // Clavier : l'instant d'appui (curseur dans une zone de texte ou non) et l'instant de relâche. Jamais la touche.
  addEventListener('keydown', (e) => {
    if (e.repeat) return; // touche maintenue : pas une nouvelle frappe
    const actif = document.activeElement;
    relever('clavier_appuis', [e.timeStamp, actif instanceof Element && actif.matches(ZONE_DE_TEXTE) ? 1 : 0]);
  }, options);
  addEventListener('keyup', (e) => relever('clavier_relaches', [e.timeStamp]), options);
  const toucher = (phase) => (e) => {
    if (phase === 1 && !echantillon('tactile', e.timeStamp)) return;
    const point = e.changedTouches && e.changedTouches[0];
    if (!point) return;
    const rayon = typeof point.radiusX === 'number' ? Math.max(point.radiusX, point.radiusY || 0) : -1;
    const pression = typeof point.force === 'number' ? Math.min(Math.max(point.force, 0), 1) * 100 : -1;
    const doigts = e.touches ? e.touches.length : 0;
    relever('tactile', [e.timeStamp, point.clientX, point.clientY, doigts, rayon, pression, phase]);
  };
  addEventListener('touchstart', toucher(0), options);
  addEventListener('touchmove', toucher(1), options);
  addEventListener('touchend', toucher(2), options);
  addEventListener('touchcancel', toucher(3), options);

  const visible = () => (document.visibilityState === 'visible' ? 1 : 0);
  relever('premier_plan', [performance.now(), visible()]);
  relever('focus', [performance.now(), document.hasFocus() ? 1 : 0]);
  document.addEventListener('visibilitychange', (e) => {
    relever('premier_plan', [e.timeStamp, visible()]);
    if (!visible()) envoyer(ARRIERE_PLAN);
  });
  addEventListener('focus', (e) => {
    if (e.target === window) relever('focus', [e.timeStamp, 1]);
  });
  addEventListener('blur', (e) => {
    if (e.target === window) relever('focus', [e.timeStamp, 0]);
  });
  addEventListener('resize', (e) => {
    if (echantillon('redimensionnements', e.timeStamp)) relever('redimensionnements', [e.timeStamp, innerWidth, innerHeight]);
  });
  // « Terminer ma session » : la trace part avant la fin de la session (sinon elle serait refusée à la sortie).
  document.addEventListener('submit', () => envoyer(SORTIE), true);
  addEventListener('pagehide', () => {
    envoyer(SORTIE);
    fini = true;
  });
  addEventListener('pageshow', (e) => {
    if (e.persisted) fini = false; // page rendue par le cache de navigation : le relevé reprend
  });
})();
