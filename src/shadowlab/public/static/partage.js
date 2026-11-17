/* Bouton « Partager mon résultat » de la page de fin de session.
   Partage la phrase du score et l'adresse du site, rien d'autre : ni identifiant de session, ni adresse de page.
   Sans partage du système (ordinateur), copie « phrase + espace + adresse » dans le presse-papiers.
   Le bouton est caché dans la page ; il n'apparaît que si l'une des deux voies existe. */
(function () {
  "use strict";
  var bouton = document.querySelector("[data-partage]");
  if (!bouton) return;
  var statut = document.querySelector(".partage-statut");
  var texte = bouton.getAttribute("data-texte") || "";
  var adresse = location.origin + "/";
  var peutPartager = typeof navigator.share === "function";
  var peutCopier = !!(navigator.clipboard && typeof navigator.clipboard.writeText === "function");
  if (!peutPartager && !peutCopier) return;

  function dire(message) {
    if (statut) statut.textContent = message || "";
  }

  function copier() {
    if (!peutCopier) {
      dire(bouton.getAttribute("data-echec"));
      return;
    }
    navigator.clipboard.writeText(texte + " " + adresse).then(
      function () {
        dire(bouton.getAttribute("data-copie"));
      },
      function () {
        dire(bouton.getAttribute("data-echec"));
      }
    );
  }

  bouton.hidden = false;
  bouton.addEventListener("click", function () {
    dire("");
    if (!peutPartager) {
      copier();
      return;
    }
    navigator.share({ text: texte, url: adresse }).catch(function (erreur) {
      if (erreur && erreur.name === "AbortError") return; // le visiteur a fermé la feuille de partage
      copier();
    });
  });
})();
