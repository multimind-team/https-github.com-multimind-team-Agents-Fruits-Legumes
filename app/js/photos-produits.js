/* Photos purement indicatives : aucune quantité ni correspondance métier modifiée. */
(function () {
  "use strict";
  let articles = {};
  const cheminPublic = /^app\/img\/produits\/[a-f0-9]{64}-(96|240)\.webp$/;
  const echapper = valeur => String(valeur ?? "").replace(/[&<>"']/g,
    c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"})[c]);

  async function charger() {
    try {
      const reponse = await fetch("../donnees/photos.json", {cache: "no-store"});
      if (!reponse.ok) return;
      const donnees = await reponse.json();
      if (donnees.version === 1 && donnees.articles && typeof donnees.articles === "object") {
        articles = donnees.articles;
      }
    } catch (e) { /* Une photo absente ne bloque jamais la commande. */ }
  }

  function image(itm8, contexte) {
    const photo = Object.hasOwn(articles, itm8) ? articles[itm8] : null;
    if (!photo || !cheminPublic.test(photo.src) || !cheminPublic.test(photo.miniature)) return "";
    const mode = ["liste", "comptage", "detail"].includes(contexte) ? contexte : "liste";
    const liste = mode === "liste";
    // Taille d'affichage, jamais les dimensions du fichier : une ancienne CSS
    // en cache ne doit pas laisser une photo de 240 px recouvrir les quantités.
    // La variable CSS permet l'agrandissement tablette sans dépendre du réseau.
    const taille = {liste: 48, comptage: 64, detail: 180}[mode];
    const style = 'display:block;box-sizing:border-box;object-fit:contain;flex-shrink:0;max-width:100%;'
      + 'width:var(--photo-produit-taille,' + taille + 'px);height:var(--photo-produit-taille,' + taille + 'px)';
    return '<img class="photo-produit photo-produit-' + mode + '" src="../' + (liste ? photo.miniature : photo.src)
      + '"' + (liste ? ' srcset="../' + photo.miniature + ' 1x, ../' + photo.src + ' 2x"' : '')
      + ' width="' + taille + '" height="' + taille + '" style="' + style + '" loading="' + (liste ? 'lazy' : 'eager')
      + '" decoding="async" alt="Photo indicative — ' + echapper(photo.libelle)
      + '" title="Photo indicative ; vérifier le libellé et le conditionnement">';
  }

  // La panne d'une image ne masque ni le nom de l'article ni sa quantité.
  document.addEventListener("error", evenement => {
    const cible = evenement.target;
    if (cible && cible.classList && cible.classList.contains("photo-produit")) cible.hidden = true;
  }, true);
  window.PhotosProduits = Object.freeze({charger, image});
})();
