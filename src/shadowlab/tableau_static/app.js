// Tableau de bord ShadowLab : lit l'API locale et dessine les vues (SVG, sans bibliothèque externe).
// Tout texte venant des données passe par textContent (jamais innerHTML).

const SERIES = ['playwright', 'selenium', 'scrapling', 'httpx']; // ordre fixe : la couleur suit le moteur
const contenu = document.getElementById('contenu');
const choixExperience = document.getElementById('choix-experience');
const infobulle = document.getElementById('infobulle');
const etat = { experiences: [], experienceId: null, vue: 'vue', minuterie: null };

// --- Outils -----------------------------------------------------------------------------------------

function h(tag, attributs = {}, ...enfants) {
  const el = document.createElement(tag);
  for (const [cle, valeur] of Object.entries(attributs)) {
    if (valeur === undefined || valeur === null || valeur === false) continue;
    if (cle === 'class') el.className = valeur;
    else if (cle.startsWith('on')) el.addEventListener(cle.slice(2), valeur);
    else el.setAttribute(cle, valeur === true ? '' : valeur);
  }
  for (const enfant of enfants.flat()) {
    if (enfant === null || enfant === undefined || enfant === false) continue;
    el.append(enfant instanceof Node ? enfant : document.createTextNode(String(enfant)));
  }
  return el;
}

function s(tag, attributs = {}, ...enfants) {
  const el = document.createElementNS('http://www.w3.org/2000/svg', tag);
  for (const [cle, valeur] of Object.entries(attributs)) {
    if (valeur === undefined || valeur === null) continue;
    if (cle.startsWith('on')) el.addEventListener(cle.slice(2), valeur);
    else el.setAttribute(cle, valeur);
  }
  for (const enfant of enfants.flat()) {
    if (enfant === null || enfant === undefined) continue;
    el.append(enfant instanceof Node ? enfant : document.createTextNode(String(enfant)));
  }
  return el;
}

async function api(chemin, options = {}) {
  const reponse = await fetch(`/api${chemin}`, options);
  const texte = await reponse.text();
  const donnees = texte ? JSON.parse(texte) : null;
  if (!reponse.ok) throw new Error(donnees?.detail ? JSON.stringify(donnees.detail) : `${reponse.status}`);
  return donnees;
}

const nombre = (v, d = 0) => (v === null || v === undefined ? '—'
  : Number(v).toLocaleString('fr-FR', { minimumFractionDigits: d, maximumFractionDigits: d }));
const pct = (bloc, d = 1) => (bloc ? `${nombre(bloc.taux * 100, d)} %` : 'n. m.');
const ic = (bloc) => (bloc ? `[${nombre(bloc.bas * 100, 1)} – ${nombre(bloc.haut * 100, 1)}]` : '');

function couleur(engine) {
  const i = SERIES.indexOf(engine);
  return i >= 0 ? `var(--serie-${i + 1})` : 'var(--texte-3)';
}

function pastille(texte) {
  return h('span', { class: `pastille ${texte}` }, texte.replace('_', ' '));
}

function legende(moteurs) {
  return h('div', { class: 'legende' },
    moteurs.map((m) => h('span', { class: 'cle' }, h('i', { style: `background:${couleur(m.engine)}` }), m.label)));
}

function vide(texte) {
  return h('div', { class: 'vide' }, texte);
}

// --- Infobulle -------------------------------------------------------------------------------------

function montrer(evenement, valeur, lignes, teinte) {
  infobulle.textContent = '';
  infobulle.append(h('b', {}, valeur));
  for (const ligne of lignes) {
    infobulle.append(h('div', {}, teinte ? h('span', { class: 'trait', style: `background:${teinte}` }) : null, ligne));
    teinte = null;
  }
  infobulle.hidden = false;
  const cible = evenement.currentTarget.getBoundingClientRect();
  const x = evenement.clientX ?? cible.right;
  const y = evenement.clientY ?? cible.top;
  const largeur = infobulle.offsetWidth;
  infobulle.style.left = `${Math.min(x + 14, innerWidth - largeur - 8)}px`;
  infobulle.style.top = `${Math.max(8, y - infobulle.offsetHeight - 10)}px`;
}

function cacher() {
  infobulle.hidden = true;
}

// Plus petite valeur « ronde » (1, 2, 2,5 ou 5 × 10^n) au moins égale à v : graduations lisibles.
function arrondiHaut(v) {
  const puissance = 10 ** Math.floor(Math.log10(v));
  return [1, 2, 2.5, 5, 10].map((m) => m * puissance).find((x) => x >= v);
}

// --- Graphique en barres horizontales (une barre par moteur) ---------------------------------------
// donnees : [{ label, engine, valeur, bas?, haut?, texte, details: [] }]

function barres(donnees, { max = null, format = (v) => nombre(v), pourcentage = false } = {}) {
  const L = 560, gauche = 104, droite = 76, ligne = 30, haut = 8;
  const largeur = L - gauche - droite;
  const borne = pourcentage ? 1 : arrondiHaut(max ?? Math.max(1e-9, ...donnees.map((d) => d.haut ?? d.valeur ?? 0)));
  const H = haut + donnees.length * ligne + 22;
  const x = (v) => gauche + (Math.max(0, Math.min(v, borne)) / borne) * largeur;
  const svg = s('svg', { class: 'graphique', viewBox: `0 0 ${L} ${H}`, role: 'img' });
  const graduations = pourcentage ? [0, 0.25, 0.5, 0.75, 1] : [0, borne / 2, borne];
  for (const g of graduations) {
    svg.append(s('line', { class: 'axe', x1: x(g), x2: x(g), y1: haut, y2: H - 20 }));
    svg.append(s('text', { x: x(g), y: H - 6, 'text-anchor': 'middle' }, pourcentage ? `${g * 100} %` : format(g)));
  }
  donnees.forEach((d, i) => {
    const y = haut + i * ligne;
    const hauteur = 14;
    const yb = y + (ligne - hauteur) / 2;
    const w = d.valeur === null || d.valeur === undefined ? 0 : x(d.valeur) - gauche;
    const groupe = s('g', { class: 'barre', tabindex: 0, 'aria-label': `${d.label} : ${d.texte}` });
    const montrerBulle = (ev) => montrer(ev, d.texte, [d.label, ...(d.details || [])], couleur(d.engine));
    groupe.addEventListener('pointermove', montrerBulle);
    groupe.addEventListener('focus', montrerBulle);
    groupe.addEventListener('pointerleave', cacher);
    groupe.addEventListener('blur', cacher);
    groupe.append(s('rect', { class: 'cible', x: 0, y, width: L, height: ligne, fill: 'transparent' }));
    groupe.append(s('text', { x: gauche - 10, y: y + ligne / 2 + 4, 'text-anchor': 'end' }, d.label));
    if (w > 0) {
      const r = Math.min(4, w);
      const chemin = `M${gauche},${yb} h${w - r} a${r},${r} 0 0 1 ${r},${r} v${hauteur - 2 * r}`
        + ` a${r},${r} 0 0 1 ${-r},${r} h${-(w - r)} z`;
      groupe.append(s('path', { class: 'marque', d: chemin, fill: couleur(d.engine) }));
    }
    let fin = gauche + w;
    if (d.bas !== undefined && d.haut !== undefined && d.bas !== null) {
      const ym = yb + hauteur / 2;
      groupe.append(s('line', { class: 'ic-ligne', x1: x(d.bas), x2: x(d.haut), y1: ym, y2: ym }));
      groupe.append(s('line', { class: 'ic-ligne', x1: x(d.bas), x2: x(d.bas), y1: ym - 4, y2: ym + 4 }));
      groupe.append(s('line', { class: 'ic-ligne', x1: x(d.haut), x2: x(d.haut), y1: ym - 4, y2: ym + 4 }));
      fin = Math.max(fin, x(d.haut));
    }
    groupe.append(s('text', { class: 'valeur', x: fin + 8, y: y + ligne / 2 + 4 }, d.texte));
    svg.append(groupe);
  });
  return svg;
}

function carteGraphique(titre, sous, donnees, options) {
  return h('section', { class: 'carte' }, h('h2', {}, titre), sous ? h('p', { class: 'sous' }, sous) : null,
    donnees.length ? barres(donnees, options) : vide('Aucune donnée.'));
}

function tableau(entetes, lignes, { classes = [] } = {}) {
  return h('div', { class: 'table-defilante' }, h('table', {},
    h('thead', {}, h('tr', {}, entetes.map((t, i) => h('th', { class: classes[i] }, t)))),
    h('tbody', {}, lignes)));
}

// --- Données partagées -----------------------------------------------------------------------------

async function chargerExperiences() {
  etat.experiences = await api('/experiences');
  const avant = etat.experienceId;
  choixExperience.textContent = '';
  for (const e of etat.experiences) {
    choixExperience.append(h('option', { value: e.id }, `#${e.id} · ${e.name} (${e.status})`));
  }
  const automatiques = etat.experiences.filter((e) => e.name !== 'sessions-manuelles');
  if (!etat.experiences.some((e) => e.id === avant)) etat.experienceId = (automatiques[0] || etat.experiences[0])?.id ?? null;
  if (etat.experienceId !== null) choixExperience.value = String(etat.experienceId);
  const enCours = etat.experiences.find((e) => e.status === 'en_cours');
  const badge = document.getElementById('etat-campagne');
  badge.hidden = !enCours;
  if (enCours) badge.textContent = `Campagne #${enCours.id} en cours · ${nombre(enCours.passages)} passages`;
  return enCours;
}

async function statistiques() {
  if (etat.experienceId === null) return null;
  return api(`/experiences/${etat.experienceId}/statistiques`);
}

// --- Vues ------------------------------------------------------------------------------------------

const VUES = {
  async vue() {
    const stats = await statistiques();
    const total = etat.experiences.reduce((n, e) => n + (e.passages || 0), 0);
    const moteurs = await api('/moteurs');
    const tuiles = h('div', { class: 'grille kpi' },
      [[etat.experiences.length, 'expériences'], [nombre(total), 'passages enregistrés'],
        [moteurs.disponibles.length, 'moteurs disponibles'],
        [stats ? stats.sessions_humaines.n : 0, 'sessions humaines de référence']]
        .map(([v, t]) => h('div', { class: 'carte tuile' }, h('b', {}, v), h('span', {}, t))));
    const lignes = etat.experiences.map((e) => h('tr', {
      class: 'cliquable',
      onclick: () => { etat.experienceId = e.id; location.hash = '#/detection'; },
    }, h('td', {}, `#${e.id}`), h('td', {}, e.name), h('td', {}, pastille(e.status)),
    h('td', { class: 'num' }, nombre(e.passages)), h('td', { class: 'num' }, nombre(e.reussis)),
    h('td', { class: 'num' }, nombre(e.erreurs)), h('td', {}, e.created_at.slice(0, 16).replace('T', ' '))));
    const blocs = [h('h1', {}, "Vue d'ensemble"),
      h('p', { class: 'chapeau' }, 'Comparaison des moteurs de navigation automatisée sur le site de test local. '
        + 'Les scores mesurent les détecteurs du laboratoire, pas ceux d’un service externe.'), tuiles];
    if (stats && stats.moteurs.length) {
      blocs.push(h('div', { class: 'grille deux' },
        carteGraphique('Réussite des scénarios', `Expérience #${stats.experience.id} · IC 95 %`,
          stats.moteurs.map((m) => ({ label: m.label, engine: m.engine, valeur: m.reussite?.taux, bas: m.reussite?.bas,
            haut: m.reussite?.haut, texte: pct(m.reussite), details: [`${m.passages} passages`, ic(m.reussite)] })),
          { pourcentage: true }),
        carteGraphique('Durée médiane d’un passage', 'en millisecondes',
          stats.moteurs.map((m) => ({ label: m.label, engine: m.engine, valeur: m.duree_ms.mediane,
            texte: `${nombre(m.duree_ms.mediane)} ms`, details: [`p95 ${nombre(m.duree_ms.p95)} ms`] })),
          { format: (v) => nombre(v) })));
    }
    blocs.push(h('section', { class: 'carte', style: 'margin-top:16px' }, h('h2', {}, 'Expériences'),
      etat.experiences.length
        ? tableau(['N°', 'Nom', 'État', 'Passages', 'Réussis', 'Erreurs', 'Créée le'], lignes,
          { classes: ['', '', '', 'num', 'num', 'num', ''] })
        : vide('Aucune expérience. Lancez-en une depuis « Expériences ».')));
    return blocs;
  },

  async moteurs() {
    const m = await api('/moteurs');
    return [h('h1', {}, 'Moteurs'),
      h('p', { class: 'chapeau' }, 'Moteurs intégrés, dans leur configuration standard. Un paquet externe peut en '
        + 'ajouter par le point d’entrée « shadowlab.engines ».'),
      h('section', { class: 'carte' }, h('h2', {}, 'Disponibles'),
        tableau(['Moteur', 'Type', 'JavaScript', 'Description'], m.disponibles.map((d) => h('tr', {},
          h('td', {}, h('span', { class: 'cle' }, h('i', { style: `background:${couleur(d.name)}` }), d.name)),
          h('td', {}, d.runtime), h('td', {}, d.javascript ? 'oui' : 'non'), h('td', {}, d.description))))),
      h('section', { class: 'carte', style: 'margin-top:16px' }, h('h2', {}, 'Versions et configurations enregistrées'),
        m.enregistres.length ? tableau(['N°', 'Moteur', 'Versions', 'Configuration'], m.enregistres.map((e) => h('tr', {},
          h('td', {}, e.id), h('td', {}, e.configuration?.label || e.name),
          h('td', {}, Object.entries(e.versions || {}).map(([k, v]) => `${k} ${v}`).join(' · ')),
          h('td', {}, h('code', {}, JSON.stringify(e.configuration))))))
          : vide('Aucun moteur encore utilisé.'))];
  },

  async experiences() {
    const exemple = `experiment:\n  name: mon_essai\n  description: Essai rapide\n  environment: local\n`
      + `  engines: [playwright, selenium, scrapling, httpx]\n  scenarios: [static_html, javascript_content, `
      + `form_interaction, api_json]\n  repetitions: 5\n  output: [json, csv, html]\n`;
    const zone = h('textarea', { id: 'yaml', spellcheck: 'false', 'aria-label': 'Définition YAML' });
    zone.value = exemple;
    const message = h('p', { class: 'message', role: 'status' });
    const envoyer = async (ev) => {
      ev.preventDefault();
      message.className = 'message';
      message.textContent = 'Validation…';
      try {
        const r = await api('/experiences', { method: 'POST', headers: { 'X-ShadowLab': '1' }, body: zone.value });
        message.textContent = `Expérience #${r.id} lancée.`;
        etat.experienceId = r.id;
        await rafraichir();
      } catch (erreur) {
        message.className = 'message erreur';
        message.textContent = `Refusée : ${erreur.message}`;
      }
    };
    const arreter = async () => {
      await api('/arret', { method: 'POST', headers: { 'X-ShadowLab': '1' } });
      message.className = 'message';
      message.textContent = 'Arrêt demandé : la campagne s’arrête après le passage en cours.';
    };
    const [scenarios, detecteurs] = await Promise.all([api('/scenarios'), api('/detecteurs')]);
    return [h('h1', {}, 'Expériences'),
      h('p', { class: 'chapeau' }, 'Une campagne se décrit en YAML. Toute URL est contrôlée par le périmètre ; '
        + 'les destinations externes sont refusées.'),
      h('div', { class: 'grille deux' },
        h('section', { class: 'carte' }, h('h2', {}, 'Nouvelle campagne'),
          h('form', { class: 'campagne', onsubmit: envoyer }, zone,
            h('div', { class: 'actions' }, h('button', { class: 'bouton', type: 'submit' }, 'Valider et lancer'),
              h('button', { class: 'bouton danger', type: 'button', onclick: arreter }, 'Arrêt d’urgence')),
            message)),
        h('section', { class: 'carte' }, h('h2', {}, 'Scénarios'),
          tableau(['Nom', 'Description', 'JS'], scenarios.map((sc) => h('tr', {}, h('td', {}, h('code', {}, sc.name)),
            h('td', {}, sc.description), h('td', {}, sc.javascript ? 'oui' : 'non')))),
          h('h2', { style: 'margin-top:20px' }, 'Détecteurs'),
          tableau(['Nom', 'Version', 'Rôle'], detecteurs.map((d) => h('tr', {}, h('td', {}, h('code', {}, d.name)),
            h('td', {}, d.version), h('td', {}, d.description.split('\n')[0])))))),
    ];
  },

  async empreintes() {
    if (etat.experienceId === null) return [h('h1', {}, 'Empreintes'), vide('Aucune expérience.')];
    const stats = await statistiques();
    const filtreMoteur = h('select', { 'aria-label': 'Moteur' }, h('option', { value: '' }, 'Tous les moteurs'),
      stats.moteurs.map((m) => h('option', { value: m.label }, m.label)));
    const filtreScenario = h('select', { 'aria-label': 'Scénario' }, h('option', { value: '' }, 'Tous les scénarios'),
      [...new Set(stats.scenarios.map((x) => x.scenario))].map((x) => h('option', { value: x }, x)));
    const liste = h('div');
    const detail = h('section', { class: 'carte' }, vide('Choisissez un passage pour voir son empreinte.'));
    filtreMoteur.value = etat.filtreMoteur || '';
    filtreScenario.value = etat.filtreScenario || '';
    const charger = async () => {
      etat.filtreMoteur = filtreMoteur.value;
      etat.filtreScenario = filtreScenario.value;
      const params = new URLSearchParams({ limite: 200 });
      if (filtreMoteur.value) params.set('moteur', filtreMoteur.value);
      if (filtreScenario.value) params.set('scenario', filtreScenario.value);
      const passages = await api(`/experiences/${etat.experienceId}/passages?${params}`);
      liste.textContent = '';
      liste.append(tableau(['N°', 'Moteur', 'Scénario', 'Rép.', 'État', 'Durée', 'Détecté par'],
        passages.map((p) => h('tr', {
          class: 'cliquable',
          onclick: (ev) => {
            liste.querySelectorAll('tr.choisi').forEach((t) => t.classList.remove('choisi'));
            ev.currentTarget.classList.add('choisi');
            afficherPassage(p.id, detail);
          },
        }, h('td', {}, p.id), h('td', {}, p.moteur), h('td', {}, p.scenario), h('td', { class: 'num' }, p.repetition),
        h('td', {}, pastille(p.status)), h('td', { class: 'num' }, `${nombre(p.duration_ms)} ms`),
        h('td', { class: 'num' }, `${p.detections} / 4`))), { classes: ['', '', '', 'num', '', 'num', 'num'] }));
    };
    filtreMoteur.addEventListener('change', charger);
    filtreScenario.addEventListener('change', charger);
    await charger();
    return [h('h1', {}, 'Empreintes'),
      h('p', { class: 'chapeau' }, 'Ce que le site a observé pour chaque passage : en-têtes HTTP dans l’ordre reçu, '
        + 'propriétés JavaScript, comportement, et les raisons de chaque classement.'),
      h('div', { class: 'actions', style: 'margin-bottom:12px' }, filtreMoteur, filtreScenario),
      h('div', { class: 'grille deux' }, h('section', { class: 'carte' }, h('h2', {}, '200 premiers passages'),
        h('div', { class: 'liste-defilante' }, liste)), detail)];
  },

  async detection() {
    const stats = await statistiques();
    if (!stats || !stats.moteurs.length) return [h('h1', {}, 'Détection'), vide('Aucun passage dans cette expérience.')];
    const detecteurs = [...new Set(stats.moteurs.flatMap((m) => Object.keys(m.detection)))].sort();
    const signaux = await api(`/experiences/${etat.experienceId}/signaux`);
    const cartes = detecteurs.map((d) => carteGraphique(d, 'taux de détection parmi les passages tranchés · IC 95 %',
      stats.moteurs.filter((m) => m.detection[d]).map((m) => {
        const b = m.detection[d];
        return { label: m.label, engine: m.engine, valeur: b.taux_detection?.taux, bas: b.taux_detection?.bas,
          haut: b.taux_detection?.haut, texte: pct(b.taux_detection),
          details: [`${b.vp} détectés · ${b.fn} non détectés`, `${b.indetermine} indéterminés sur ${b.n}`,
            ic(b.taux_detection)] };
      }), { pourcentage: true }));
    const q = stats.qualite_detecteurs;
    const qualite = tableau(['Détecteur', 'Rappel', 'Précision', 'F1', 'Faux positifs (humains)', 'Sessions humaines'],
      Object.entries(q).map(([d, v]) => h('tr', {}, h('td', {}, h('code', {}, d)),
        h('td', { class: 'num' }, v.rappel ?? 'n. m.'), h('td', { class: 'num' }, v.precision ?? 'n. m.'),
        h('td', { class: 'num' }, v.f1 ?? 'n. m.'),
        h('td', { class: 'num' }, pct(v.faux_positifs), h('small', { class: 'ic' }, ic(v.faux_positifs))),
        h('td', { class: 'num' }, v.sessions_humaines))), { classes: ['', 'num', 'num', 'num', 'num', 'num'] });
    const lignesSignaux = signaux.signaux.filter((x) => x.poids > 0).map((x) => h('tr', {},
      h('td', {}, h('span', { class: 'cle' }, h('i', { style: `background:${couleur(stats.moteurs.find((m) => m.label === x.moteur)?.engine)}` }), x.moteur)),
      h('td', {}, h('code', {}, x.detecteur)), h('td', {}, x.description),
      h('td', { class: 'num' }, x.poids), h('td', { class: 'num' }, `${nombre(100 * x.n / signaux.passages[x.moteur])} %`)));
    return [h('h1', {}, 'Détection'),
      h('p', { class: 'chapeau' }, 'Chaque détecteur classe chaque session « automatisé », « humain » ou « indéterminé ». '
        + 'Un taux élevé signifie que le détecteur repère bien ce moteur, ici, sur ce site.'),
      legende(stats.moteurs),
      h('div', { class: 'grille deux' }, cartes),
      h('section', { class: 'carte', style: 'margin-top:16px' }, h('h2', {}, 'Qualité des détecteurs'),
        h('p', { class: 'sous' }, stats.sessions_humaines.n
          ? `Faux positifs mesurés sur ${stats.sessions_humaines.n} sessions humaines.`
          : 'Aucune session humaine : faux positifs, précision et F1 non mesurables. Faites-en depuis « Session manuelle ».'),
        qualite),
      h('section', { class: 'carte', style: 'margin-top:16px' }, h('h2', {}, 'Signaux relevés'),
        h('p', { class: 'sous' }, 'Part des passages de chaque moteur où le signal a été vu.'),
        lignesSignaux.length ? tableau(['Moteur', 'Détecteur', 'Signal', 'Poids', 'Fréquence'], lignesSignaux,
          { classes: ['', '', '', 'num', 'num'] }) : vide('Aucun signal.')),
      h('section', { class: 'carte', style: 'margin-top:16px' }, h('h2', {}, 'Limites'),
        h('ul', { class: 'limites' }, stats.limites.map((l) => h('li', {}, l))))];
  },

  async performance() {
    const stats = await statistiques();
    if (!stats || !stats.moteurs.length) return [h('h1', {}, 'Performance'), vide('Aucun passage dans cette expérience.')];
    const M = stats.moteurs;
    const scenarios = [...new Set(stats.scenarios.map((x) => x.scenario))];
    const matrice = tableau(['Moteur', ...scenarios], M.map((m) => h('tr', {}, h('td', {}, m.label),
      scenarios.map((sc) => {
        const c = stats.scenarios.find((x) => x.label === m.label && x.scenario === sc);
        if (!c) return h('td', { class: 'nm' }, '—');
        const t = c.reussite?.taux ?? 0;
        return h('td', { class: 'num', title: `${c.passages} passages · médiane ${nombre(c.duree_ms.mediane)} ms` },
          h('span', { class: `pastille ${t === 1 ? 'reussi' : t === 0 ? 'echec' : 'interrompu'}` }, pct(c.reussite, 0)));
      }))), { classes: ['', ...scenarios.map(() => 'num')] });
    return [h('h1', {}, 'Performance'),
      h('p', { class: 'chapeau' }, 'Mesures sur la machine locale. CPU et mémoire couvrent le lanceur et ses processus '
        + '(navigateur compris), hors site de test.'),
      legende(M),
      h('div', { class: 'grille deux' },
        carteGraphique('Réussite', 'part des passages réussis · IC 95 %', M.map((m) => ({ label: m.label, engine: m.engine,
          valeur: m.reussite?.taux, bas: m.reussite?.bas, haut: m.reussite?.haut, texte: pct(m.reussite),
          details: [`erreurs ${pct(m.taux_erreur)}`] })), { pourcentage: true }),
        carteGraphique('Durée d’un passage', 'médiane, en ms (p95 et p99 au survol)', M.map((m) => ({
          label: m.label, engine: m.engine, valeur: m.duree_ms.mediane, texte: `${nombre(m.duree_ms.mediane)} ms`,
          details: [`p95 ${nombre(m.duree_ms.p95)} ms · p99 ${nombre(m.duree_ms.p99)} ms`, `max ${nombre(m.duree_ms.max)} ms`] }))),
        carteGraphique('Temps CPU par passage', 'moyenne, en ms', M.map((m) => ({ label: m.label, engine: m.engine,
          valeur: m.cpu_ms?.moyenne, texte: `${nombre(m.cpu_ms?.moyenne)} ms`,
          details: [`${nombre(m.cpu_pct.moyenne)} % d’un cœur en moyenne`] }))),
        carteGraphique('Mémoire', 'moyenne du maximum par passage, en Mo', M.map((m) => ({ label: m.label, engine: m.engine,
          valeur: m.memoire_mo.moyenne, texte: `${nombre(m.memoire_mo.moyenne)} Mo`,
          details: [`maximum ${nombre(m.memoire_mo.max)} Mo`] })))),
      h('section', { class: 'carte', style: 'margin-top:16px' }, h('h2', {}, 'Réussite par scénario'), matrice),
      h('section', { class: 'carte', style: 'margin-top:16px' }, h('h2', {}, 'Tableau des mesures'),
        tableau(['Moteur', 'Passages', 'Réussite', 'Médiane', 'p95', 'p99', 'CPU (ms)', 'Mémoire (Mo)', 'Requêtes'],
          M.map((m) => h('tr', {}, h('td', {}, m.label), h('td', { class: 'num' }, m.passages),
            h('td', { class: 'num' }, pct(m.reussite)), h('td', { class: 'num' }, nombre(m.duree_ms.mediane)),
            h('td', { class: 'num' }, nombre(m.duree_ms.p95)), h('td', { class: 'num' }, nombre(m.duree_ms.p99)),
            h('td', { class: 'num' }, nombre(m.cpu_ms?.moyenne)), h('td', { class: 'num' }, nombre(m.memoire_mo.moyenne)),
            h('td', { class: 'num' }, nombre(m.requetes.moyenne, 1)))),
          { classes: ['', 'num', 'num', 'num', 'num', 'num', 'num', 'num', 'num'] }))];
  },

  async comparer() {
    const candidates = etat.experiences.filter((e) => e.name !== 'sessions-manuelles');
    etat.comparaison = etat.comparaison || candidates.slice(0, 2).map((e) => e.id);
    const resultat = h('div');
    const cases = candidates.map((e) => {
      const c = h('input', { type: 'checkbox', value: e.id, checked: etat.comparaison.includes(e.id) });
      c.addEventListener('change', () => {
        etat.comparaison = [...cases.map((l) => l.querySelector('input'))].filter((x) => x.checked).map((x) => Number(x.value));
        charger();
      });
      return h('label', { class: 'cle' }, c, `#${e.id} ${e.name}`);
    });
    const charger = async () => {
      resultat.textContent = '';
      if (!etat.comparaison.length) { resultat.append(vide('Cochez au moins une expérience.')); return; }
      const donnees = await api(`/comparaison?ids=${etat.comparaison.join(',')}`);
      const detecteurs = [...new Set(donnees.flatMap((d) => d.moteurs.flatMap((m) => Object.keys(m.detection))))].sort();
      resultat.append(tableau(['Expérience', 'Moteur', 'Passages', 'Réussite', 'Médiane (ms)', 'CPU (ms)', 'Mémoire (Mo)',
        ...detecteurs.map((d) => `Détection ${d}`)],
      donnees.flatMap((d) => d.moteurs.map((m) => h('tr', {}, h('td', {}, `#${d.experience.id} ${d.experience.name}`),
        h('td', {}, m.label), h('td', { class: 'num' }, m.passages), h('td', { class: 'num' }, pct(m.reussite)),
        h('td', { class: 'num' }, nombre(m.duree_ms.mediane)), h('td', { class: 'num' }, nombre(m.cpu_ms?.moyenne)),
        h('td', { class: 'num' }, nombre(m.memoire_mo.moyenne)),
        detecteurs.map((det) => h('td', { class: 'num' }, pct(m.detection[det]?.taux_detection))))))));
    };
    await charger();
    return [h('h1', {}, 'Comparer'),
      h('p', { class: 'chapeau' }, 'Les mêmes moteurs d’une expérience à l’autre : changement de version, de '
        + 'configuration ou de machine. À comparer seulement à environnement équivalent.'),
      h('section', { class: 'carte' }, h('div', { class: 'actions', style: 'margin-bottom:12px' }, cases), resultat)];
  },

  async rapports() {
    const lignes = etat.experiences.filter((e) => e.name !== 'sessions-manuelles').map((e) => h('tr', {},
      h('td', {}, `#${e.id}`), h('td', {}, e.name), h('td', {}, pastille(e.status)), h('td', { class: 'num' }, nombre(e.passages)),
      h('td', {}, ['html', 'csv', 'json'].map((f) => h('a', { href: `/api/experiences/${e.id}/export.${f}`,
        target: '_blank', rel: 'noopener', style: 'margin-right:12px' }, f.toUpperCase())))));
    return [h('h1', {}, 'Rapports'),
      h('p', { class: 'chapeau' }, 'Rapport HTML autonome, passages en CSV, statistiques en JSON. Les mêmes fichiers sont '
        + 'écrits dans outputs/rapports/<n°>/ à la fin de chaque campagne.'),
      h('section', { class: 'carte' }, lignes.length ? tableau(['N°', 'Nom', 'État', 'Passages', 'Exports'], lignes,
        { classes: ['', '', '', 'num', ''] }) : vide('Aucune expérience.'))];
  },

  async reglages() {
    const r = await api('/reglages');
    const ligne = (cle, valeur) => h('tr', {}, h('th', { scope: 'row' }, cle), h('td', {}, valeur));
    return [h('h1', {}, 'Réglages'),
      h('p', { class: 'chapeau' }, 'Lecture seule. Les réglages se changent par variables d’environnement '
        + '(SHADOWLAB_*) au démarrage.'),
      h('section', { class: 'carte' }, h('table', {}, h('tbody', {},
        ligne('Adresse d’écoute', `${r.hote}:${r.port}`),
        ligne('Destinations autorisées (périmètre)', r.hotes_autorises.join(', ')),
        ligne('Plafond mémoire par passage', `${nombre(r.memoire_max_mo)} Mo`),
        ligne('Concurrence maximale', r.concurrence_max),
        ligne('Base de données', r.base_donnees),
        ligne('Jeton d’accès configuré', r.jeton_configure ? 'oui' : 'non (écoute locale uniquement)'),
        ligne('Campagne lancée depuis l’interface', r.campagne_en_cours ? 'oui' : 'non')))),
      h('section', { class: 'carte', style: 'margin-top:16px' }, h('h2', {}, 'Ce que le laboratoire ne fait pas'),
        h('ul', { class: 'limites' },
          h('li', {}, 'Aucune destination externe : rejet par défaut, redirections comprises.'),
          h('li', {}, 'Aucune résolution de CAPTCHA, rotation d’identité ni modification d’empreinte.'),
          h('li', {}, 'Aucune donnée de collecte exposée hors de cette machine sans jeton.')))];
  },
};

function entetesOrdonnes(http) {
  // Format actuel : liste de paires dans l'ordre reçu. Ancien format : dictionnaire + `ordre_entetes`.
  if (Array.isArray(http.entetes)) return http.entetes;
  const valeurs = http.entetes || {};
  return (http.ordre_entetes || Object.keys(valeurs)).map((k) => [k, valeurs[k]]);
}

async function afficherPassage(id, conteneur) {
  const p = await api(`/passages/${id}`);
  conteneur.textContent = '';
  const e = p.empreinte;
  conteneur.append(h('h2', {}, `Passage #${id} · ${p.passage.moteur} · ${p.passage.scenario}`),
    h('p', { class: 'sous' }, `${p.passage.status} · ${nombre(p.passage.duration_ms)} ms`),
    ...p.detections.map((d) => h('div', { class: 'signal' }, h('span', {}, h('code', {}, d.detector_name), ' ',
      pastille(d.classification)), h('span', { class: 'nm' }, d.signals.map((x) => x.description).join(' · ') || '—'))),
    h('h2', { style: 'margin-top:16px' }, 'En-têtes HTTP (ordre reçu)'),
    h('pre', { class: 'json' }, e ? entetesOrdonnes(e.http_properties).map(([k, v]) => `${k}: ${v}`).join('\n') : '—'),
    h('h2', { style: 'margin-top:16px' }, 'Propriétés JavaScript'),
    h('pre', { class: 'json' }, e ? JSON.stringify(e.browser_properties, null, 2) : '—'),
    h('h2', { style: 'margin-top:16px' }, 'Session'),
    h('pre', { class: 'json' }, e ? JSON.stringify(e.session_properties, null, 2) : '—'));
}

// --- Navigation et rafraîchissement ----------------------------------------------------------------

async function rafraichir() {
  contenu.classList.add('rechargement'); // la vue précédente reste affichée pendant le chargement
  try {
    const enCours = await chargerExperiences();
    const blocs = await (VUES[etat.vue] || VUES.vue)();
    contenu.replaceChildren(...blocs);
    clearTimeout(etat.minuterie);
    if (enCours && ['vue', 'detection', 'performance'].includes(etat.vue)) etat.minuterie = setTimeout(rafraichir, 5000);
  } catch (erreur) {
    contenu.replaceChildren(h('h1', {}, 'Erreur'), h('p', { class: 'message erreur' }, erreur.message));
  } finally {
    contenu.classList.remove('rechargement');
  }
}

function route() {
  etat.vue = (location.hash.replace('#/', '') || 'vue');
  document.querySelectorAll('#navigation a').forEach((a) => {
    if (a.getAttribute('href') === `#/${etat.vue}`) a.setAttribute('aria-current', 'page');
    else a.removeAttribute('aria-current');
  });
  cacher();
  rafraichir();
}

choixExperience.addEventListener('change', () => {
  etat.experienceId = Number(choixExperience.value);
  rafraichir();
});

const boutonTheme = document.getElementById('theme');
function appliquerTheme(theme) {
  document.documentElement.dataset.theme = theme;
  boutonTheme.textContent = theme === 'dark' ? 'Thème clair' : 'Thème sombre';
  try { localStorage.setItem('shadowlab-theme', theme); } catch { /* stockage indisponible : sans conséquence */ }
}
boutonTheme.addEventListener('click', () => appliquerTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'));
let themeEnregistre = 'dark';
try { themeEnregistre = localStorage.getItem('shadowlab-theme') || 'dark'; } catch { /* idem */ }
appliquerTheme(themeEnregistre);

addEventListener('hashchange', route);
route();
