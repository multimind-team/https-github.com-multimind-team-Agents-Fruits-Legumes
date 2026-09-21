# Cockpit Fruits & Légumes — mode d’emploi

Le cockpit permet de comprendre les chiffres du rayon et de conserver ce que vous constatez sur le terrain. Il utilise les mêmes données que l’application de commande. La commande du matin reste à préparer et à transmettre avant **9 h 30**.

## Ouvrir l’application

Utilisez le raccourci **Cockpit Fruits et Legumes** sur le Bureau, ou double-cliquez sur [ouvrir-cockpit.vbs](../ouvrir-cockpit.vbs) dans le dossier du projet. Le lanceur vérifie le serveur local et ouvre une fenêtre dédiée dans Edge ou Chrome. À défaut, le navigateur habituel s’ouvre.

L’adresse directe est [http://127.0.0.1:8751/app/cockpit.html](http://127.0.0.1:8751/app/cockpit.html). Elle fonctionne sur ce PC lorsque le serveur est démarré. Fermer la fenêtre du cockpit n’arrête pas le serveur du magasin.

## Un parcours de cinq à dix minutes

1. Dans **Vue d’ensemble**, regardez la date des dernières ventes et choisissez une période : 3, 7, 14, 30 jours ou l’année de référence.
2. Ouvrez un article à examiner. Vérifiez sa position, son colisage et les flux enregistrés.
3. Complétez son contexte ou son bilan de promotion avec les faits observés en rayon.
4. Dans **Consignes terrain**, vérifiez les consignes actives et les échéances à renouveler.
5. Utilisez **Préparer la commande** pour revenir à l’écran habituel. Une observation ou une précommande renseignée dans le cockpit ne transmet aucune commande.

Le bouton **↻** relit les données. La touche **/** ouvre la recherche produit lorsque vous n’êtes pas en train de saisir du texte.

## Les espaces de travail

### Vue d’ensemble

Vous retrouvez les ventes, les réceptions, le rapport ventes/livraisons et les écarts à examiner. Le graphique affiche toujours les 14 derniers jours de données ; le filtre choisi s’applique aux indicateurs et aux analyses de période. Survolez une barre pour lire sa quantité.

Les volumes globaux sont exprimés en **colis équivalents au colisage actuel**. Ils permettent de comparer les flux ; ils ne représentent pas nécessairement le nombre de colis réellement réceptionnés à l’époque. Le rapport ventes/livraisons peut dépasser 100 %, car une partie des ventes peut provenir du stock initial.

La légende distingue **Ventes en caisse**, **Livraisons reçues** et **Prévisions de ventes archivées**. Si aucune prévision n’existe pour les dates du graphique, un encadré le précise et le repère de légende devient vide. Lorsqu’elles existent, le nombre de jours avec prévision est indiqué ; cela ne garantit pas que tous les articles sont couverts. Les barres violettes ne représentent pas les commandes envoyées au fournisseur. Le graphique ne permet donc pas de mesurer un écart entre ventes et commandes réelles.

Les pistes telles que « stock négatif » ou « colisage à examiner » orientent votre enquête. Un écart de flux supérieur à 25 % ne prouve à lui seul ni casse ni rupture.

### Enquête produit

Recherchez un nom, un code ou une famille, puis sélectionnez l’article. **Analyse & historique** présente les flux sur 14 jours, le profil du lundi au dimanche et une lecture commentée des données.

Les textes automatiques sont construits à partir des chiffres disponibles. Aucun nouvel agent IA n’est appelé à chaque ouverture. Le bouton **Reprendre & compléter** copie ces commentaires dans votre note terrain : vous pouvez les corriger, ajouter une explication et enregistrer votre version. Le commentaire automatique et votre note restent distincts.

Un jour sans vente enregistrée reste inconnu : ce n’est pas automatiquement une journée à zéro vente. La date d’un comptage récent ne rajeunit pas l’historique des ventes.

### Console de contexte, stock et colisage

Dans **Contexte terrain**, renseignez des dates de début et de fin, puis expliquez le motif.

| Saisie | Conséquence |
|---|---|
| Rayon normal ou fond de rayon | Aucun coefficient de mise en avant. |
| Tête de gondole | Prévision multipliée par 1,5 sur les jours concernés. |
| Îlot central | Prévision multipliée par 2 sur les jours concernés. |
| Fond de présentation minimum | Réserve souhaitée après le besoin calculé à la livraison. |
| Réimplantation | Date cible obligatoire ; le minimum de présentation attend cette date. Aucune vente n’est inventée. |
| Fin de saison ou rupture fournisseur | Arrêt explicite de la proposition automatique pour les livraisons couvertes. |
| Maturité, note, dates de prospectus | Informations pour l’analyse ; aucune déduction automatique du stock ni coefficient promotion ajouté. |

Dans **Stock & colisage**, le comptage est une nouvelle mesure physique à l’instant présent. Suivez le même périmètre que l’écran de comptage : position en chambre froide, rayon déjà rempli. Précisez notamment si la livraison est déjà rangée. Choisir « casse non enregistrée » comme motif explique la mesure ; cela ne crée pas un mouvement de casse séparé.

Le colisage indique le **contenu d’un colis**, par exemple 6 kg, et non le nombre de colis à commander. Le motif est obligatoire. Les anciens comptages gardent leur conversion d’origine.

Relisez la confirmation avant d’enregistrer. Après une saisie qui change le calcul, attendez la confirmation du recalcul. Si l’application indique « enregistré, mais recalcul non confirmé », la saisie a été conservée : actualisez et faites vérifier le calcul avant de vous appuyer sur la nouvelle proposition.

### Carnet des consignes

**Consignes terrain** regroupe les consignes actives, planifiées, expirées ou annulées, ainsi que les colisages personnalisés. Le filtre **Toutes les consignes** permet de retrouver les dernières versions expirées ou annulées.

**Modifier** ouvre la dernière version. **Renouveler** prépare de nouvelles dates à vérifier avant enregistrement. **Annuler** désactive la consigne sans effacer son historique. Une nouvelle consigne programmée plus tard laisse l’ancienne s’appliquer jusqu’à son début ; une ancienne version ne revient pas automatiquement après l’expiration de la nouvelle.

## Promotions : commenter, mesurer, préparer les suivantes

L’onglet **Promotions & bilan** rassemble les campagnes documentées de l’article. Renseignez les dates exactes, le prix observé et son unité, la précommande initiale en colis si vous la connaissez, ainsi que la disponibilité constatée. **Non renseignée** et **Non, disponibilité vérifiée** sont deux informations différentes.

Décrivez ce qui peut expliquer le résultat : implantation, visibilité, réceptions tardives, jours de rupture, maturité, météo, concurrence. Le champ **Objectif et dispositif de l’offre** précise ce que vous cherchiez à obtenir. Vous pouvez reprendre le bilan automatique dans **Votre bilan corrigé ou complété**, puis l’éditer.

L’analyse compare les jours documentés pendant l’offre aux 28 jours précédents. Lorsque les données le permettent, elle compare aussi les mêmes jours de la semaine. Une hausse apparente ne démontre pas à elle seule l’effet de la promotion. Une rupture peut au contraire cacher une demande plus forte que les ventes enregistrées.

Vous pouvez compléter les observations d’une consigne expirée ou annulée, et renseigner les dates exactes de la promotion. La période et les paramètres de commande restent conservés : un commentaire ne réactive pas une consigne annulée. Ces annotations sont enregistrées sans recalcul. Une ancienne promotion jamais documentée peut être renseignée avec ses dates passées ; si l’article n’a pas encore de contexte, l’application crée un contexte courant neutre.

La précommande indiquée ici est une **information d’analyse** : elle n’est ni envoyée au fournisseur, ni ajoutée aux réceptions. Le cockpit constitue une mémoire des campagnes et repère les campagnes comparables. **Il ne fournit pas encore de quantité automatique de précommande future.** Même avec plusieurs campagnes comparables, le stock vendable, les réceptions prévues et la capacité de présentation restent à vérifier.

## Journal photo : voir ce qui a changé

Ouvrez **Journal photo**, puis **Ajouter une photo**. Choisissez une image sur le PC (JPEG, PNG ou WebP, 8 Mo maximum), renseignez sa date et son heure réelles, puis l’emplacement : rayon, TG, îlot, produit ou réserve. Une photo de produit doit être rattachée à l’article correspondant. Vous pouvez aussi relier une vue de TG ou de rayon à un article.

Donnez un titre et décrivez le changement : déplacement, largeur d’exposition, remplissage, signalétique, fraîcheur, incident ou autre observation. Ajoutez les dates promotion si elles sont utiles. La date renseignée correspond à la prise de vue ; la date d’enregistrement est conservée séparément. Les informations éventuelles de l’appareil photo restent indicatives et ne remplacent pas votre saisie.

Le commentaire automatique reprend la date, la zone, l’article et le changement déclaré. Il **n’interprète pas les pixels de la photo**. Utilisez **Utiliser et compléter ce texte** pour le corriger avec vos observations. Après enregistrement, **Compléter** ajoute une nouvelle version du commentaire ; l’image originale est conservée.

La galerie se filtre par emplacement, article et date de début. Cliquez sur une miniature pour agrandir la photo. La fiche produit relie les photos et les changements datés aux jours de son historique afin de faciliter la comparaison avec les ventes. Cela ne démontre pas qu’un changement a causé une hausse ou une baisse.

Les photos restent sur ce PC, sans envoi à un service IA externe. Les originaux sont privés ; les aperçus visibles dans l’application ne contiennent pas de métadonnées GPS. L’ajout d’une photo ne change aucune quantité, aucun colisage ni aucune commande. Les images et leur journal sont exclus de la sauvegarde Git distante : pour conserver cette mémoire en cas de panne du PC, prévoyez une sauvegarde locale du dossier du projet, incluant le journal et les fichiers photo.

Le **CA reconstitué** utilise uniquement les ventes disposant d’un prix historique exploitable et affiche sa couverture. Il peut donc être partiel. La marge historique reste indisponible : les bases HT/TTC et la TVA des prix historiques de vente et d’achat ne sont pas attestées. Elle n’est pas inventée à partir de l’image ou du prix actuel.

## Pourquoi certaines prévisions sont absentes

Les anciennes prévisions quotidiennes n’étaient pas archivées. Le cockpit laisse donc les cases correspondantes absentes. À partir des prochains calculs, il conserve les prévisions des jours futurs avant que ces jours ne commencent. Les comparaisons se construiront progressivement avec les ventes reçues ensuite.

La conformité des commandes réellement transmises au fournisseur n’est pas disponible : le cockpit ne récupère pas ces quantités validées. Les prévisions archivées et la proposition de commande sont deux informations différentes.

Si un article n’a pas de profil de ventes ou partage son stock avec une autre offre, suivez l’avertissement de sa fiche. Une consigne enregistrée sur une offre secondaire peut devoir être reportée sur l’article qui porte la proposition automatique.

Pour le détail du fonctionnement, consulter [la fiche technique](../reference/cockpit-pc.md) et [la fiche du portail documentaire](Documentation%20de%20l'application/cockpit-pc.html).
