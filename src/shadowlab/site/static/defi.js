// Défi de l'Arena : trouver un nombre tel que SHA-256(défi:nombre) commence par assez de bits nuls, puis revenir
// à la page demandée. Prouve que le client exécute JavaScript et garde ses cookies.
const zone = document.getElementById('defi');
const { defi, difficulte, retour } = zone.dataset;
const encodeur = new TextEncoder();

function bitsNuls(octets) {
  let total = 0;
  for (const octet of octets) {
    if (octet === 0) { total += 8; continue; }
    return total + Math.clz32(octet) - 24;
  }
  return total;
}

async function resoudre() {
  const debut = performance.now();
  for (let nonce = 0; ; nonce += 1) {
    const empreinte = await crypto.subtle.digest('SHA-256', encodeur.encode(`${defi}:${nonce}`));
    if (bitsNuls(new Uint8Array(empreinte)) >= Number(difficulte)) {
      return { nonce, ms: Math.round(performance.now() - debut) };
    }
  }
}

const preuve = await resoudre();
const reponse = await fetch('/lab/defi/verifier', {
  method: 'POST',
  credentials: 'same-origin',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ defi, ...preuve }),
});
if (reponse.ok) {
  location.replace(retour);
} else {
  document.getElementById('etat-defi').textContent = 'La vérification a échoué.';
}
