// Réseau social fictif « Mosaïk Démo » : des interactions qui restent dans la page.
// Rien ne part vers le serveur et rien n'est gardé dans le navigateur. Un « j'aime » ne change que l'affichage ;
// un commentaire tapé s'affiche sur place, par textContent, puis disparaît au changement de page ; la recherche
// filtre ce qui est déjà dans la page. Ce script ne fait que basculer des attributs et des classes : les animations
// sont dans la feuille de style (et s'effacent avec prefers-reduced-motion). Aucun défilement ni focus imposé.

const langue = document.documentElement.lang === 'en' ? 'en' : 'fr';
const nombres = new Intl.NumberFormat(langue);

// « J'aime » : bascule l'état du bouton et le compte affiché ; la feuille de style anime le cœur.
for (const bouton of document.querySelectorAll('button[data-aime]')) {
  const base = Number(bouton.dataset.aime) || 0;
  const compte = bouton.querySelector('.aime-compte');
  bouton.addEventListener('click', () => {
    const aime = bouton.getAttribute('aria-pressed') !== 'true';
    bouton.setAttribute('aria-pressed', String(aime));
    if (compte) compte.textContent = nombres.format(base + (aime ? 1 : 0));
  });
}

// Commentaire : ajouté à la liste de la page, jamais envoyé. « Publier » reste inactif tant que le champ est vide ;
// Ctrl+Entrée ou Cmd+Entrée publie aussi.
for (const zone of document.querySelectorAll('[data-zone-commentaire]')) {
  const champ = zone.querySelector('[data-commentaire]');
  const bouton = zone.querySelector('[data-publier]');
  const section = zone.closest('.commentaires') || zone.parentElement;
  const liste = section.querySelector('[data-commentaires]');
  const aucun = section.querySelector('[data-aucun-commentaire]');
  const compteur = section.querySelector('[data-compte]');
  if (!champ || !bouton || !liste) continue;
  let total = liste.children.length;
  const vous = zone.dataset.vous || '';
  const actualiser = () => {
    bouton.disabled = !champ.value.trim();
  };
  const publier = () => {
    const texte = champ.value.trim();
    if (!texte) return;
    const element = document.createElement('li');
    element.className = 'commentaire commentaire-local';
    const image = document.createElement('span');
    image.className = 'avatar avatar-vous';
    image.setAttribute('aria-hidden', 'true');
    image.textContent = vous.slice(0, 1);
    const corps = document.createElement('div');
    corps.className = 'commentaire-corps';
    const tete = document.createElement('p');
    tete.className = 'commentaire-tete';
    const qui = document.createElement('span');
    qui.className = 'auteur-nom';
    qui.textContent = vous;
    const quand = document.createElement('span');
    quand.className = 'commentaire-quand';
    quand.textContent = zone.dataset.instant || '';
    tete.append(qui, ' ', quand);
    const quoi = document.createElement('p');
    quoi.className = 'commentaire-texte';
    quoi.textContent = texte;
    corps.append(tete, quoi);
    element.append(image, corps);
    liste.append(element);
    total += 1;
    if (compteur) compteur.textContent = nombres.format(total);
    if (aucun) aucun.hidden = true;
    champ.value = '';
    actualiser();
    champ.focus();
  };
  champ.addEventListener('input', actualiser);
  champ.addEventListener('keydown', (evenement) => {
    if (evenement.key === 'Enter' && (evenement.ctrlKey || evenement.metaKey)) publier();
  });
  bouton.addEventListener('click', publier);
  actualiser();
}

// Recherche : garde les éléments de la page dont la clé contient tous les mots tapés (sans accents ni majuscules).
// Pendant une recherche, la mosaïque passe en grille régulière (classe en-recherche) pour ne pas laisser de trous.
const recherche = document.querySelector('input[data-recherche]');
if (recherche) {
  const replier = (texte) => texte.normalize('NFKD').replace(/\p{M}/gu, '').toLowerCase();
  const elements = [...document.querySelectorAll('[data-cherchable]')];
  const mosaiques = [...document.querySelectorAll('.mosaique')].filter((m) => m.querySelector('[data-cherchable]'));
  const vide = document.querySelector('[data-recherche-vide]');
  const filtrer = () => {
    const mots = replier(recherche.value).split(/\s+/).filter(Boolean);
    let visibles = 0;
    for (const element of elements) {
      const garde = mots.every((mot) => (element.dataset.texte || '').includes(mot));
      element.hidden = !garde;
      if (garde) visibles += 1;
    }
    for (const mosaique of mosaiques) mosaique.classList.toggle('en-recherche', mots.length > 0);
    if (vide) vide.hidden = visibles > 0;
  };
  recherche.addEventListener('input', filtrer);
  if (recherche.value) filtrer(); // valeur gardée par le navigateur au retour sur la page
}
