// Réseau social fictif « Mosaïk Démo » : des interactions qui restent dans la page.
// Rien ne part vers le serveur et rien n'est gardé dans le navigateur. Un « j'aime » ne change que l'affichage ;
// un commentaire tapé s'affiche sur place, par textContent, puis disparaît au changement de page ; la recherche
// filtre ce qui est déjà dans la page.

const langue = document.documentElement.lang === 'en' ? 'en' : 'fr';
const nombres = new Intl.NumberFormat(langue);

// « J'aime » : bascule l'état du bouton et le compte affiché.
for (const bouton of document.querySelectorAll('button[data-aime]')) {
  const base = Number(bouton.dataset.aime) || 0;
  const compte = bouton.querySelector('.aime-compte');
  bouton.addEventListener('click', () => {
    const aime = bouton.getAttribute('aria-pressed') !== 'true';
    bouton.setAttribute('aria-pressed', String(aime));
    if (compte) compte.textContent = nombres.format(base + (aime ? 1 : 0));
  });
}

// Commentaire : ajouté à la liste de la page, jamais envoyé.
for (const zone of document.querySelectorAll('[data-zone-commentaire]')) {
  const champ = zone.querySelector('[data-commentaire]');
  const bouton = zone.querySelector('[data-publier]');
  const section = zone.parentElement;
  const liste = section.querySelector('[data-commentaires]');
  const aucun = section.querySelector('[data-aucun-commentaire]');
  if (!champ || !bouton || !liste) continue;
  bouton.addEventListener('click', () => {
    const texte = champ.value.trim();
    if (!texte) return;
    const element = document.createElement('li');
    element.className = 'commentaire commentaire-local';
    const qui = document.createElement('span');
    qui.className = 'auteur-nom';
    qui.textContent = zone.dataset.vous || '';
    const quoi = document.createElement('span');
    quoi.className = 'commentaire-texte';
    quoi.textContent = texte;
    element.append(qui, ' ', quoi);
    liste.append(element);
    if (aucun) aucun.hidden = true;
    champ.value = '';
    champ.focus();
  });
}

// Recherche : garde les éléments de la page dont la clé contient tous les mots tapés (sans accents ni majuscules).
const recherche = document.querySelector('input[data-recherche]');
if (recherche) {
  const replier = (texte) => texte.normalize('NFKD').replace(/\p{M}/gu, '').toLowerCase();
  const elements = [...document.querySelectorAll('[data-cherchable]')];
  const vide = document.querySelector('[data-recherche-vide]');
  recherche.addEventListener('input', () => {
    const mots = replier(recherche.value).split(/\s+/).filter(Boolean);
    let visibles = 0;
    for (const element of elements) {
      const garde = mots.every((mot) => (element.dataset.texte || '').includes(mot));
      element.hidden = !garde;
      if (garde) visibles += 1;
    }
    if (vide) vide.hidden = visibles > 0;
  });
}
