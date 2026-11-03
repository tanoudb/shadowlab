// Remplit la zone dynamique après 400 ms : un client sans JavaScript ne voit jamais ce texte.
setTimeout(() => {
  const zone = document.getElementById('zone-dynamique');
  zone.textContent = '';
  const resultat = document.createElement('span');
  resultat.id = 'resultat-js';
  resultat.textContent = 'contenu-dynamique-ok';
  zone.append(resultat);
}, 400);
