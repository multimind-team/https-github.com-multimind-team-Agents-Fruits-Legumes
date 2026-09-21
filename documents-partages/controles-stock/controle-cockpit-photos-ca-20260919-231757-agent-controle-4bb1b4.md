# Contrôle indépendant — journal photo et CA du cockpit

Date locale : 2026-09-19T23:17:57. Rôle réel : agent-controle.

**Avis : SÛR POUR LE PÉRIMÈTRE** des modules serveur et analyse ci-dessous. Cet avis ne vaut ni validation humaine de commande, ni certification du CA commercial, ni recette graphique générale. Le Leader réalise la recette navigateur finale et le démarrage.

## Mandat et limites

Extension utilisateur du cockpit PC : conserver localement des photos datées et leurs commentaires éditables, rapprocher le contexte des ventes, afficher seulement un CA historiquement documenté. Contrôle en lecture seule de la production, essais sur modules copiés et fixtures temporaires hors installation originale. Aucun test écrit au serveur de production ; connexions HTTP uniquement sur port éphémère. Aucune correction de code faite par le contrôleur.

Le rapport complète `controle-cockpit-final-20260919-231057-agent-controle-58426b.md` ; les 35 tests antérieurs, les contrôles contexte/annulation et les archives prévisionnelles ne sont pas rejoués ici.

## Vérifications et preuves

- `moteur/photos_contexte.py:70` : date et heure locales obligatoires, date future refusée, métadonnées contrôlées et article vérifié. `:138` : Pillow vérifie JPEG/PNG/WebP fixes indépendamment du nom, 8 Mio et 40 millions de pixels maximum, orientation appliquée, dérivés reconstruits sans EXIF. `:197` : publication exclusive atomique, aucune substitution d'original. `:221` : journal de versions en ajout seul, révision et requête protégées.
- `moteur/serveur.py:637` : seules tailles JPEG 320/1600 sous empreinte sont publiques, original et JSONL exclus. `:674` et `:708` : limite12Mio spécifique photo, autres routes1Mio conservées ; protocole JSON et provenance existants appliqués. `:998` : route sans recalcul ni écriture de stock/décision.
- Contrôle HTTP indépendant réussi : 11 refus adverses avant toute entrée au carnet (date absente/future, base64 invalide, chemin dans nom, champ stock, Origin étranger, Fetch cross-site, Content-Type incorrect, Transfer-Encoding, Content-Length dupliqué, PNG annonçant100000×100000pixels). 14 GET/HEAD refusés sur original privé, carnet, traversées et noms/tailles hors liste.
- JPEG synthétique contenant orientation6, GPS, EXIF2100 et suffixe script : original conservé octet pour octet, dérivés JPEG corrects60×90sans EXIF/GPS ni suffixe, date humaine2019-03-05T07:42 conservée. Aucune date inventée depuis EXIF ou l'envoi.
- Deux annotations concurrentes de révision1 donnent200 et409 ; deux lignes seulement. Rejeu exact sans écriture supplémentaire ; remplacement image en édition refusé. Nouvel identifiant sur doublon original après annotation renvoie désormais révision2. Ce dernier défaut mineur a été signalé puis corrigé par agent-donnees et vérifié indépendamment.
- Tous les fichiers métier des fixtures sont restés identiques ; aucun appel de recalcul ou de sous-processus. Les empreintes production décisions/état/proposition/pouvoirs sont identiques aux témoins du contrôle précédent.
- `moteur/pilotage.py:332` : dernière version de photo, article exact, date déclarée, aucune lecture image. `:393`, `:439` et `:653` : CA depuis quantité signée et prix unitaire du fait, avant conversion jus ; groupage sans double total, couverture en nombre de faits documentés, marge absente.
- Scénario CA indépendant réussi : ventes A10×2,3456 ; code secondaireC3×5 ; retourC−1×5 ; A100sansPV ; B2×0 ; jus4×3. Ajout d'un doublon exact du premier fait. Total obtenu45,46€, articleA33,46€, couverture5/6=83,333%, aucunCA orange issu du jus, vrai zéroB conservé, PVcatalogue999999ignoré. Date source des ventes employée malgré date_effet différente. PhotoA corrigée datée17/09apparaît au17/09malgré EXIF2100/enregistrement19/09; vue générale exclue de la fiche article. Aucune écriture durant l'analyse.
- Lecture du script photo : date nouvelle initialement vide, contenu humain échappé dans HTML ou affecté par textContent ; formulaire explicite sur l'absence d'analyse visuelle. Documentation technique et utilisateur cohérente. `git check-ignore` confirme exclusion du carnet, des originaux et des dérivés photo.

## Écritures réellement faites et limites restantes

Aucune écriture métier ni permission en production. Écriture du présent rapport privé uniquement ; copies temporaires détruites après les essais. Aucun appel externe d'analyse d'image ou envoi cloud dans ce périmètre.

Le commentaire automatique décrit les champs saisis, pas les pixels. Les photos ne prouvent ni stock, ni prix, ni causalité. Le CA reste une reconstitution avec prix historiques arrondis et couverture partielle ; aucune marge inventée. Ces limites sont indiquées dans l'interface et la documentation. La recette navigateur finale (choix réel d'un fichier, galerie, agrandissement, liens produit et sauvegarde des annotations) demeure sous responsabilité du Leader.

## Empreintes SHA-256 au contrôle

- `moteur/photos_contexte.py` : `93aa6dc647e31f02ce607baca1fc01ef85fdb1e6b6113cb05980d6457c039aff`
- `moteur/pilotage.py` : `ad678beb5b59ec4e668d69bb798ca226b07ef5b0647c42efa69962edcf41c10f`
- `moteur/serveur.py` : `be45a8cd05afc4daf4568de229c7c00a28ceff51079d32933a755ba76c1ca2d2`
- `app/js/cockpit-photos.js` : `9a1f1022f2e2b91ad6a212a0f17f504a6c6865a499b117c03af5c77ff73907d5`
- `.gitignore` : `55267777dc41d1e110c00c00a79ba14e757ab0ae508d1b304bf2c790be49aa75`
- `donnees/decisions.jsonl` : `ae19f78d676fb57ff458eb37fdafdccdbc7bfc29c33a119d3a6d269e1c04de3d`
- `donnees/etat.json` : `8c66aae143d8cd638710b81617daaa8362b609168e71cc6ba11b0d101abb6fee`
- `donnees/proposition.json` : `3c9bde7f273a7730c2a300d16d6486057814e8bcb9868b44e6d2220fab041e7a`
- `donnees/pouvoirs.json` : `51b4c6403e21f9d70cb70d2b08a1f006a0bc00f28e7e30c7ec4cde4148f3129a`
