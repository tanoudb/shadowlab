// Demande au serveur le verdict des détecteurs une fois l'empreinte reçue par lui.
const jeton = document.querySelector('meta[name="sl-session"]')?.content || '';

function cellule(texte) {
  const td = document.createElement('td');
  td.textContent = texte;
  return td;
}

async function afficher() {
  const reponse = await fetch(`/lab/verdict?sl=${encodeURIComponent(jeton)}`);
  const corps = document.querySelector('#verdicts tbody');
  corps.textContent = '';
  for (const c of await reponse.json()) {
    const tr = document.createElement('tr');
    tr.className = `verdict ${c.classification}`;
    tr.append(cellule(c.detector_name), cellule(c.classification),
      cellule(c.signals.map((s) => s.description).join(' · ') || '—'));
    corps.append(tr);
  }
  const marque = document.createElement('div');
  marque.id = 'verdict-affiche';
  marque.hidden = true;
  document.body.append(marque);
}

document.addEventListener('shadowlab:empreinte', () => setTimeout(afficher, 150));
