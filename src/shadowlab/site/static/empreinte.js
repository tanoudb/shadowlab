// Affiche l'empreinte collectée par l'observateur.
document.addEventListener('shadowlab:empreinte', (evenement) => {
  document.getElementById('proprietes').textContent = JSON.stringify(evenement.detail, null, 2);
});
