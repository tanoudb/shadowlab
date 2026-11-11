// Bloc « Annonces similaires » : chargé après coup par `fetch`, absent du HTML initial de la fiche.
const zone = document.getElementById('similaires');

function carte(a) {
  const article = document.createElement('article');
  article.className = 'carte';
  article.dataset.reference = a.reference;

  const photo = document.createElement('img');
  photo.src = a.photo;
  photo.alt = '';
  photo.width = 320;
  photo.height = 200;

  const corps = document.createElement('div');
  corps.className = 'carte-corps';
  const titre = document.createElement('h3');
  const lien = document.createElement('a');
  lien.className = 'similaire';
  lien.href = a.lien;
  lien.textContent = a.titre;
  titre.append(lien);
  const prix = document.createElement('p');
  prix.className = 'carte-prix';
  prix.textContent = `${a.prix.toLocaleString('fr-FR')} €`;
  const detail = document.createElement('p');
  detail.className = 'carte-detail';
  detail.textContent = `${a.surface} m² · ${a.ville}`;
  corps.append(titre, prix, detail);

  article.append(photo, corps);
  return article;
}

if (zone) {
  fetch(zone.dataset.url, { headers: { Accept: 'application/json' } })
    .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
    .then((donnees) => zone.append(...donnees.annonces.map(carte)))
    .catch(() => {
      zone.textContent = 'Les annonces similaires sont momentanément indisponibles.';
    });
}
