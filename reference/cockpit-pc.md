# Cockpit PC — architecture et contrat technique

Fiche complémentaire du référentiel, alignée sur le code du projet. Elle ne crée aucun pouvoir d’agent. Les règles d’autorisation restent celles de [AGENTS.md](../AGENTS.md).

## Architecture locale

Le cockpit est une interface HTML/CSS/JavaScript servie par le serveur Python 3.14 existant sur `127.0.0.1:8751`. Aucun framework Web, environnement Electron/Tauri, service cloud ou base de données supplémentaire n’est ajouté.

| Composant | Fonction |
|---|---|
| `app/cockpit.html`, `app/css/cockpit.css`, `app/js/cockpit.js` | Interface PC, graphiques SVG, formulaires et relecture du recalcul. |
| `moteur/pilotage.py` | Analyse dérivée à la lecture des faits et projections existants. |
| `moteur/contexte_terrain.py` | Validation et reconstitution des consignes datées. |
| `moteur/photos_contexte.py`, `app/js/cockpit-photos.js` | Bibliothèque locale des photos datées, dérivés et annotations versionnées. |
| `moteur/proposer-commande.py` | Application du contexte au besoin et production des prévisions journalières. |
| `moteur/generer-proposition.py` | Publication cohérente de la proposition, puis archivage des prévisions futures. |
| `moteur/previsions_archivees.py` | Journal analytique des prévisions et lecture de la dernière prévision antérieure à chaque jour. |
| `moteur/serveur.py` | Routes protégées et liste explicite des fichiers publics. |

`ouvrir-cockpit.vbs` appelle `py -3.14 -B moteur/ouvrir-cockpit.py` sans console. Celui-ci passe par `gerer-serveur.py demarrer`, vérifie le HTTP local puis ouvre Edge, Chrome ou le navigateur par défaut. Le raccourci du Bureau peut cibler ce lanceur. Ce démarrage ne redémarre pas arbitrairement une instance existante. Après une modification du serveur Python, un redémarrage reste une opération distincte du gestionnaire.

L’URL de l’interface est `http://127.0.0.1:8751/app/cockpit.html`. Les pages de documentation restent des fichiers du dépôt ; elles ne sont pas ajoutées à la liste des ressources publiques du serveur métier. L’accès mobile et Tailscale sont indépendants de cette fenêtre PC.

## Routes et protection des écritures

| Route | Contrat |
|---|---|
| `GET /api/pilotage?horizon=14&article=<code>` | `horizon` : `3`, `7`, `14`, `30`, `annee` (`annuel` accepté) ; `article` facultatif. Retourne période, couverture, indicateurs, chronologie, articles, causes, limites et détail éventuel. |
| `GET /api/contexte` | `{ok, jour, articles, historique}` ; dernière version éditable par article, calendrier des versions, contexte effectif, 500 consignes récentes au maximum dans `historique`. |
| `POST /api/contexte` | Création/remplacement, annotation ou annulation d’une consigne humaine ; révision et identifiant de requête obligatoires. |
| `GET /api/photos-contexte?article=<code>` | Dernière version de chaque photo, filtre article facultatif, URLs des dérivés et limites déclarées. |
| `POST /api/photos-contexte` | Ajout d’image avec contexte, ou édition des métadonnées avec `id` et `revision` ; aucun recalcul métier. |
| `POST /api/comptages` | Route existante : nouvelle mesure physique, conversion validée, motif et commentaire ; aucun fait rétroactif créé par le cockpit. |
| `POST /api/conditionnement` | Route existante : contenu du colis, ancienne valeur attendue et motif facultatif côté API, obligatoire dans le cockpit. |

Les nouvelles routes utilisent les protections existantes : contrôle de provenance HTTP et des origines, lecture JSON stricte, limite du corps, verrou commun et publication explicite des seules ressources autorisées. Elles ne constituent pas une nouvelle authentification utilisateur. Le client ne choisit ni l’auteur durable du contexte ni le libellé de référence.

`POST /api/contexte` répond avec `enregistre`, `deja_enregistre`, `contexte`, `annotation_seule` et `recalcul`. Une annotation seule retourne `recalcul: "non_necessaire"`. Une modification moteur lance le recalcul existant et retourne `"en_cours"`. Une révision périmée ou une requête réutilisée différemment produit HTTP 409. Le frontal conserve le même identifiant pour rejouer un envoi incertain.

L’interface attend un nouveau statut `termine` et relit une proposition portant le même identifiant d’opération. Un enregistrement réussi suivi d’un échec de recalcul reste présenté comme enregistré, avec recalcul à vérifier. Aucun ajustement manuel de la commande n’est effacé par le cockpit.

## Modèle de contexte et journal

La source est `donnees/decisions.jsonl`, avec une entrée `type: "contexte-terrain"` par version. Aucune projection `contexte-terrain.json` n’est nécessaire. Le journal reste en ajout seul ; l’annulation est une nouvelle entrée et conserve les valeurs précédentes.

| Champ de saisie | Validation / signification |
|---|---|
| `itm8`, `revision`, `requete_id` | Article présent dans la proposition, entier ≥ 0, identifiant stable de 8 à 100 caractères autorisés. |
| `motif` | Texte obligatoire de 1 à 500 caractères. |
| `emplacement` | `rayon`, `tg`, `ilot`, `fond`. |
| `statut` | `actif`, `reimplantation`, `fin-saison`, `rupture-fournisseur`. |
| `debut`, `fin` | Dates ISO inclusives ; fin ≥ début. |
| `date_cible` | Date facultative, obligatoire pour réimplantation et comprise dans la consigne. |
| `maturite` | `impeccable`, `sur-mur`, `trop-vert`, `heterogene`. |
| `stock_min_colis` | Nombre fini entre 0 et 9999. |
| `note` | Texte de 4000 caractères au maximum. |
| `promo_debut`, `promo_fin` | Deux dates ensemble, fin ≥ début ; repère analytique sans coefficient ni précommande automatique. |
| `commentaire_promo`, `objectif_promo`, `bilan_promo` | Textes de 4000, 500 et 6000 caractères au maximum. |
| `precommande_colis`, `prix_promo` | Nombres finis ≥ 0 ou `null` ; informations humaines, sans mouvement de stock ni ordre fournisseur. |
| `unite_prix_promo` | `kg`, `piece`, `barquette`, `lot`, `autre` ou `null` ; unité requise si prix renseigné. |
| `rupture_promo` | `inconnue`, `oui`, `non`. |
| `annuler` | Booléen ; l’annulation utilise article, révision, requête et motif. |
| `observations_seules` | Booléen ; note et observations promotion, dates promotion comprises, sans changement des paramètres moteur ni de l’annulation. |

Le journal conserve aussi `id`, `auteur`, `origine`, `enregistre_le`, la requête normalisée et `annotation_seule`. Les nombres booléens, non finis, les champs inconnus et les dates invalides sont refusés avant ajout. Le carnet incomplet n’est pas réparé silencieusement.

Une programmation future garde la précédente consigne jusqu’à sa date de début. La dernière version commencée prime ; son expiration ne réactive pas une ancienne version. `contexte_effectif` fournit la version retenue pour aujourd’hui, tandis que les champs du premier niveau restent ceux de la dernière version éditable. L’annulation agit dès sa date de saisie.

Les observations promotion et la note omises lors d’une modification sont conservées ; un texte vide ou `null` explicitement envoyé retire la valeur correspondante. Le mode `observations_seules: true` reçoit article, révision, requête, motif et les seules observations à modifier, dates promotion comprises. Il conserve strictement la période moteur, l’emplacement, le statut, la maturité, le minimum et l’état d’annulation. Tout paramètre moteur ou état d’annulation transmis dans ce mode est refusé. Une note sur une consigne annulée ne peut donc réactiver ni TG ni arrêt de commande. Sans consigne précédente, le mode crée un contexte neutre courant (rayon normal, actif, minimum nul). Cette annotation ne relance pas le calcul et peut documenter une promotion passée.

Le remplacement complet d’une consigne expirée reste limité aux observations et à la note, à dates et paramètres inchangés. La création d’une consigne entièrement antidatée reste refusée. L’interface utilise le mode observations seules pour les bilans promotion et les notes sans modification des paramètres moteur.

## Calcul et limites de portée

Pour chaque jour `d` de l’horizon commande/livraison, le moteur multiplie la demande déjà calculée par `M(d)` : 1 sans mise en avant, 1,5 pour une TG ou 2 pour un îlot lorsque la consigne couvre ce jour. Chaque jour intermédiaire reçoit son propre coefficient. Les dates de prospectus, commentaires et observations de maturité n’ajoutent aucun multiplicateur.

```text
PrévisionVente(d) = prévision existante(d) × M(d)
DemandeHorizon = somme(PrévisionVente(d)) / diviseur de pertes existant
BesoinBrut = max(0, DemandeHorizon + MinimumColis × PCB − Position)
```

Le minimum représente une réserve après l’horizon et s’applique à la livraison. En réimplantation, il attend une date cible atteinte. L’arrondi historique est conservé ; lorsqu’un minimum est demandé, l’arrondi supérieur évite de passer sous cette réserve. Aucun profil de ventes n’est inventé pour un article sans historique.

`fin-saison` et `rupture-fournisseur` arrêtent explicitement la proposition si la date de livraison est couverte. Les blocages existants de position perdue et de promotion précommandée restent prioritaires. La promotion précommandée historique — avec sa règle de livraison le lundi — reste distincte des dates de promotion du contexte.

La maturité ne modifie ni le stock physique ni les ventes historiques. Les champs qualitatifs n’appliquent aucune baisse arbitraire. Les groupes de codes partagent toujours une seule ligne porteuse du besoin ; un contexte sur une offre secondaire produit un avertissement. Un article sans profil reçoit également un avertissement si sa consigne ne peut pas alimenter un calcul automatique.

## Archives et comparaisons

`previsions_journalieres` contient les ventes attendues par jour, **avant pertes, déduction du stock, minimum de présentation et arrondi de commande**. La proposition publiée est relue sous le verrou afin de transmettre son `_operation_id` exact à l’archive.

`donnees/previsions/AAAA.jsonl` conserve les nouvelles prévisions des seules dates strictement postérieures au jour réel d’écriture. Le jour courant et les jours passés sont exclus. Une valeur inchangée pour le même stock, la même date, la même unité, le même PCB et la même offre n’est pas ajoutée de nouveau. Le lecteur sélectionne la dernière prévision enregistrée avant chaque journée civile. Les offres secondaires n’ajoutent pas une deuxième prévision au stock commun.

L’historique antérieur à ce mécanisme reste absent ; il n’est pas reconstruit avec les ventes désormais connues. Les unités anciennes incompatibles sont exclues. La conformité des prévisions porte seulement sur les paires article/jour documentées, avec tolérance de ±25 % des ventes ; pour zéro vente, seule une prévision nulle est conforme. La conformité des commandes envoyées reste indisponible.

Les horizons de pilotage finissent au dernier jour de vente observé, indépendamment de la date des comptages. Les graphiques de flux conservent 14 jours ; l’année est celle de la référence des ventes. Les agrégations globales utilisent des colis équivalents au PCB actuel, dédupliquent les stocks communs et n’assimilent jamais l’absence de fait à zéro.

L’interface affiche explicitement l’absence de prévisions pour les dates du graphique, à partir de la série représentée et non des indicateurs d’une autre période. Une prévision nulle est une valeur présente. Le nombre de jours couverts ne certifie pas une couverture complète des articles. Les libellés distinguent les réceptions des commandes réellement envoyées, dont les quantités restent indisponibles. Le rapport ventes/réceptions peut dépasser 100 % ; son calcul n’inclut pas le stock initial et ne certifie pas la complétude des réceptions.

## Analyses promotion et commentaires modifiables

Une campagne est identifiée par article et dates promotion. Sa dernière version fournit les commentaires humains. L’analyse compare la campagne aux 28 jours précédents, sur les jours documentés, avec une variante corrigée de la répartition des jours de semaine lorsque les données le permettent. Prix, disponibilité, implantation, météo et saison sont des facteurs explicatifs possibles ; aucune causalité n’est affirmée.

Le module peut repérer au moins deux campagnes précédentes de même prix, unité, durée et emplacement, entièrement documentées et déclarées sans rupture. Il retourne alors une piste `a_etudier`. **Aucune quantité de précommande future n’est produite** : le stock vendable initial, les réceptions prévues et la présentation restent à vérifier. Le prix renseigné n’est pas un prix de vente validé par un agent.

Les commentaires automatiques sont déterministes, sourcés dans les données chargées et recalculés à la lecture. Aucun appel à un modèle ni apprentissage automatique en arrière-plan n’est installé. L’utilisateur peut copier puis corriger ces textes dans sa note ou son bilan ; sa rédaction est conservée séparément des constats automatiques.

## Photos datées : stockage et contrat

Les photographies restent locales. `donnees/photos-contexte.jsonl` est un carnet analytique distinct des faits de stock et des décisions moteur. Chaque entrée complète porte `type: "photo-contexte"`, `schema: 1`, un `id` stable, une `revision`, `operation: "ajout"` ou `"annotation"`, les métadonnées, l’auteur, `enregistre_le` et la signature privée de la requête. La dernière version par identifiant est affichée. Aucune suppression n’est proposée.

Un ajout reçoit `requete_id`, `image_base64` brut, `nom_fichier`, `date_photo` au format local `AAAA-MM-JJTHH:MM`, `zone`, `itm8` facultatif, `titre`, `changement`, `commentaire`, et éventuellement les deux dates promotion. La zone `produit` exige un article connu. Titre, changement et commentaire sont limités respectivement à 160, 2000 et 6000 caractères. La date humaine est obligatoire, valide et non future ; `date_exif` conserve seulement une éventuelle indication de l’appareil, séparément.

Une édition reçoit `id`, `revision`, `requete_id` et les seules métadonnées à modifier. Les champs omis sont conservés ; l’image et son nom ne sont pas remplaçables par cette route d’édition. Les conflits de version ou de requête donnent HTTP 409. Un même original et une même observation ne créent pas de doublon, et un nouvel envoi identique retourne la dernière annotation disponible de cette photo.

Pillow vérifie le contenu, indépendamment de l’extension : JPEG, PNG ou WebP fixes seulement, 8 Mio décodés et 40 millions de pixels au maximum. La route reçoit au plus 12 Mio de JSON pour le base64 ; les anciennes routes conservent leur plafond de 1 Mio. Les dimensions sont contrôlées avant décodage complet, l’orientation EXIF est appliquée et les aperçus sont reconstruits sans métadonnées.

Les originaux sont conservés sous `documents-partages/contexte-visuel/originaux/<sha256>.<extension>` ; leurs octets ne sont jamais remplacés. Les dérivés JPEG de 1600 et 320 pixels au maximum sont publiés atomiquement sous `app/img/contexte/<sha256>-1600.jpg` et `-320.jpg`. La liste HTTP n’autorise que ces deux formes avec empreinte hexadécimale de 64 caractères. Ni les originaux, ni le carnet brut ne sont publiés. La publication exclusive refuse une collision de contenu ; une interruption ne réécrit aucun historique.

Le `.gitignore` exclut `donnees/photos-contexte.jsonl`, `documents-partages/contexte-visuel/` et `app/img/contexte/` de la sauvegarde Git distante, conformément au choix de conservation sur ce PC. Une sauvegarde locale doit inclure ces trois emplacements ensemble : le code seul ne permet pas de retrouver les observations et les images.

`commentaire_auto` est une description déterministe des champs renseignés, avec `analyse_visuelle: "non_realisee"`. Le champ `commentaire` est la rédaction modifiable de l’utilisateur. Aucun appel IA externe, aucune extraction visuelle de prix, de quantité ou de fraîcheur, et aucune conséquence automatique sur stock ou commande ne sont ajoutés.

Le pilotage relie les événements photo datés aux articles et à leur chronologie. Le CA reconstitué exploite seulement les faits de vente disposant d’un prix unitaire historique, avec couverture explicite ; aucun prix courant ne remplit une donnée historique manquante. La marge historique reste indisponible : bases HT/TTC et TVA des prix historiques de vente et d’achat non attestées dans les faits. Une concordance entre photo, modification du rayon et variation de ventes ne constitue pas une preuve causale.

## Vérification et maintenance

Les essais d’écriture se font uniquement dans une copie jetable avec `py -3.14 -B tests/lancer_tests_isoles.py`. Les tests pertinents sont `test_contexte_terrain.py`, `test_photos_contexte.py`, `test_pilotage.py`, `test_previsions_archivees.py`, les tests serveur/colisage existants et le parcours navigateur du cockpit. Une simple lecture ou ouverture du cockpit ne lance aucun import, recalcul complet, agent IA ou envoi de commande.

Sources : [interface](../app/cockpit.html), [logique des écrans](../app/js/cockpit.js), [serveur](../moteur/serveur.py), [contexte](../moteur/contexte_terrain.py), [pilotage](../moteur/pilotage.py), [calcul](../moteur/proposer-commande.py), [génération](../moteur/generer-proposition.py), [archives](../moteur/previsions_archivees.py), [lanceur](../moteur/ouvrir-cockpit.py).

## Évolutions à développer

La [fiche 24.3 — contrat de développement du cockpit et apprentissage local](../Documents/Documentation%20de%20l'application/24%20-%20Evolutions%20futures%20et%20roadmap/24.3%20-%20Contrat%20de%20developpement%20du%20cockpit%20et%20apprentissage%20local.html) distingue les fonctions présentes des lots CP-01 à CP-10 à construire. Elle définit la collecte des observations, les identités de campagnes, la provenance temporelle, les graphiques, les exports et les critères de validation. Ses schémas et interfaces futurs ne sont pas des API disponibles. Cette fiche technique conserve la description du code livré.
