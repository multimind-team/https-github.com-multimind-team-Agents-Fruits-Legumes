# Le métier — rayon fruits & légumes

À lire avant de conclure que quelque chose est anormal.

Consigne canonique : `AGENTS.md`. Ce document explique le métier ; les écritures et leurs droits
sont définis dans `reference/contrat-echange.md` et `donnees/pouvoirs.json`.

---

## La journée

Les heures ci-dessous sont les repères d'organisation habituels du rayon. Elles ne prouvent
pas l'heure réelle d'une livraison, son rangement ou la présence d'un export ; elles ne
constituent pas non plus des tâches automatiques installées dans le logiciel.

| Heure | Quoi |
|---|---|
| 05h00 | La livraison arrive sur le quai. |
| 06h20 | Envoi des fichiers du jour par mail. |
| 06h30 | Rangement de la livraison en chambre froide. |
| 08h00 | Préparation de la commande du lendemain. |
| 09h20 | Envoi de la commande. **Limite absolue : 09h30.** |
| 19h00 | Mise à jour du stock dans l'application. |
| 19h30 | Fermeture. |

**Samedi** : la commande habituelle est livrée le **lundi**, sans livraison le dimanche,
sous réserve d'une fermeture ou d'une réception réellement décalée à contrôler.
**Dimanche** : organisation habituelle sans livraison ni envoi des exports, avec ouverture
9h–12h15. L'envoi du lundi peut donc contenir les sorties du samedi et du dimanche ; vérifier
les périodes internes. Un renvoi ou une facture reçu le dimanche garde son propre périmètre.

---

## L'envoi du matin

Le lot habituel apporte cadencier Mercalys, cadencier Webtelevente, ventes et livraisons,
selon l'organisation décrite ci-dessus ; casse et dons sont facultatifs.

### Calendrier normal et période réellement attestée

Dans le lot matinal de J, **ventes, casse et dons portent normalement sur J−1** ; la
**livraison du matin porte normalement sur J**. Le décalage d'un jour est attendu, pas une
anomalie. Le lundi, les sorties peuvent concerner aussi le samedi.

Cette règle ne permet pas de déduire le contenu du seul nom du fichier. Lire les journées
et périodes internes : une sortie du jour encore ouvert, un cumul sans détail, un renvoi
ou une facture tardive exigent leur contrôle propre. Ne jamais répartir un total ni forcer
la date de J pour faire correspondre le fichier au calendrier habituel.

Pour Scafruit, l'importeur lit la date de commande puis déduit le lendemain, en sautant
dimanche, comme date d'effet. Il ne prend pas ici en compte le calendrier complet des jours
fériés. Pour une livraison directe, la date de réception attestée est fournie explicitement.
La réception du mail ne prouve ni l'arrivée du camion ni le rangement des marchandises.

- **L'heure du mail varie** : vers 6h certains jours, en début d'après-midi d'autres. Un traitement de fichier repose sur son arrivée et son contrôle, pas sur une heure supposée.
- **Un envoi en double ne doit jamais compter double** : contrôler les identifiants et le résultat du rejeu. Des doublons historiques peuvent exister ; ne jamais nettoyer le carnet en place.
- **Un fichier peut manquer.** Il faut le dire.

---

## La position — la notion centrale

**Ce n'est pas un stock.** Le rayon est d'abord rempli au maximum, **ensuite** on mesure :

- **il reste des colis en chambre froide** → position = ce qui reste, **en positif** ;
- **la chambre froide est vide** → position = ce qui pourrait encore entrer en rayon, **en
  négatif**.

> Concombres : rayon plein, 2 colis en réserve → **2**
> Tomates grappe : réserve vide, on pourrait mettre 3 cartons → **−3**

**Une position négative est normale** : il manque cette quantité pour tenir le rayon plein. Les
deux cas ne coexistent jamais, puisque le rayon est rempli en premier.

Remplir le rayon depuis la chambre froide sort un colis de la réserve et comble un manque en
rayon : **la position ne bouge pas**. C'est pour ça que ce geste, qu'aucun fichier n'enregistre,
n'a aucun effet sur la mesure.

**Le moment physique du comptage change ce qu'il contient.** Le moteur applique les phases
suivantes ; le contrôleur doit vérifier que cette convention représente bien la réalité :

| Phase programmée | Ce que la convention présume déjà inclus | Mouvements du même jour appliqués ensuite |
|---|---|---|
| **À partir de 17h00** (soir) | Tous les mouvements du jour | Aucun. Les mouvements des jours suivants s'appliqueront. |
| **Avant 17h00 et avant le repère de réception du mail** | Position avant livraison du jour et avant ses sorties | Livraison, ventes, casse et dons du jour. |
| **Avant 17h00 et à partir du repère de réception du mail** | Livraison rangée, avant les sorties de la journée | Ventes, casse et dons ; livraison déjà comprise. |

Le comptage courant conserve son heure locale de saisie, distincte de l'enregistrement
technique. Sans heure connue, le lecteur se replie sur la phase soir. Sans repère de réception
disponible, il utilise 06h30 : à cette heure exacte, la phase est déjà matin après réception.

Ce sont des repères techniques, pas des preuves de clôture ou de rangement. Une livraison
reçue à 11h après un comptage de 8h, ou un relevé à 16h59 qui contient déjà des ventes du jour,
peut ne pas être représenté correctement par cette convention journalière. Bloquer le
périmètre douteux et vérifier l'ordre physique ; ne pas modifier l'heure ou la date pour
contourner le problème. Voir `procedures/controle-stock.md`.

Une mesure physiquement plus récente renouvelle la base du seul article concerné, même si
les statistiques de ventes sont anciennes. Conserver les deux dates ; ne pas dégrader cette
position au seul motif des anciennes ventes. Cela ne certifie ni les autres articles ni les
sorties survenues ensuite. Une seule livraison récente ne valide pas non plus leur couverture.
Un document tardif garde sa date d'effet et n'est pas réappliqué à une mesure qui le contient
déjà. Une correction historique conserve l'instant de sa cible et suit sa procédure propre.

**Pas de position du tout** : sans mesure exploitable, la position est inconnue, pas zéro.
L'écran n'invente aucun chiffre. Un article sans activité depuis longtemps peut ne plus être en
rayon, mais une absence de mesure ne suffit pas à le prouver : vérifier les faits avant de masquer.

Dans la soustraction du besoin, le calcul utilise provisoirement **0 pour une position
inconnue**, tout en conservant le signal d'inconnu. Ce zéro n'atteste pas « rayon plein,
réserve vide ». Une demande peut être proposée, selon le profil, les arrondis et les autres
règles : l'absence de mesure ne suffit ni à prouver une quantité disponible ni à garantir
une commande. Voir `reference/le-calcul.md` pour les exceptions et blocages.

**À partir de −10 colis inclus**, l'écran affiche `--` et demande de recompter. Le calcul
bloque le proposé si la mesure est antérieure aux sept derniers jours de la commande ; une
mesure récente bénéficie de l'exception existante, sans rajeunir les statistiques.

---

## Les fournisseurs

| Fournisseur | Source et traitement habituels |
|---|---|
| **Scafruit** — l'officiel | export de livraison, intégré par `agent-donnees` après simulation et contrôle indépendant |
| **Pomona / TerreAzur** | facture reçue par mail, lue et structurée ; document et import de stock sont distincts |
| Garrigues, Pouget, autres directs | facture à lire ; identité, unités et parcours d'import à vérifier pour ce fournisseur |

On commande chez Pomona en cas de rupture chez Scafruit, et certains produits en permanence pour
le prix ou la qualité. Ça change régulièrement.

Dans ce fonctionnement, les factures arrivent par mail. Leur réception ne crée pas une
entrée de stock : il faut un fait de livraison attesté et effectivement importé. Les exports
Scafruit habituels bénéficient de la délégation décrite dans `AGENTS.md`, après simulation et
contrôle, sans nouvelle confirmation pour un lot sûr. Une livraison directe exige son
autorisation distincte. Si son entrée manque alors que les sorties sont intégrées, la
position calculée peut baisser à tort ; vérifier l'historique au lieu d'inventer un reçu.

**D'où l'obligation de lire et contrôler les factures directes**, puis de confier leur import à
`agent-donnees` selon `procedures/courrier.md`. Pour Pomona/TerreAzur, le parcours normal utilise
`moteur/importer-facture-directe.py`, la simulation, la validation explicite du responsable ligne
par ligne et la vérification séparée des faits et de la marge. Ne jamais prendre le PV dans le
seul catalogue ni supposer le colisage du jour.

`moteur/enregistrer-livraison-directe.py` est un outil historique de saisie unitaire, pas un
équivalent sûr du validateur facture : ne pas l'utiliser en automatique ni cumuler les deux
parcours pour une même livraison. Un fournisseur sans mapping vérifié nécessite une décision
humaine ; ne pas appliquer les codes TerreAzur à un autre fournisseur.

Un comptage correctement effectué fournit une nouvelle base physique quelle que soit
l'origine de la marchandise comprise dans la mesure. Il ne complète pas les livraisons
historiques manquantes. Une position qui remonte sans livraison enregistrée est un écart à
enquêter, **pas une quantité livrée prouvée** : erreur de mesure, unité ou mouvement oublié
restent possibles. Aucune entrée déduite ne doit être inventée pour équilibrer le calcul.

**Le masquage est réversible** : il retire une ligne de la préparation selon la décision
applicable ; il ne prouve pas que toute marchandise a disparu du rayon.
Vérifier les changements intervenus depuis avant une annulation : réversible ne veut pas dire
qu'il soit sûr de restaurer n'importe quelle ancienne valeur sans contrôle.

---

## Trois particularités à reconnaître et à contrôler

**Les oranges de la machine à jus** ne passent jamais en caisse : elles partent à la presse. Ce
sont les ventes de jus qui les font sortir — **2 kg par litre, 1 kg par 50 cl**.

**Le box et la caissette** : pour certains couples d'offres du cadencier, le moteur choisit
la caissette : pommes de terre 65/8 ou 55/6, oranges en filet 90/9. C'est une sélection de
l'offre commandable, pas une conversion de quantité livrée. Un box réellement reçu avec
65 filets reste 65 filets attestés ; ne pas enregistrer 8 à sa place. Une décision de PCB
effective reste prioritaire et tout autre couple douteux doit être vérifié.

**Le colisage change d'une livraison à l'autre**, surtout chez Pomona : 6 pièces un jour, 12 le
lendemain. **Ne jamais le supposer** d'après une livraison précédente : le relire sur la facture
du jour.

---

## Casse et dons

Marchandise sortie sans être vendue ; la casse est jetée, les dons vont aux Restos du Cœur.
**Strictement équivalents pour le calcul** : les deux entrent dans le taux de perte, qui gonfle
la commande. Ils restent séparés dans les carnets parce que la destination est une information
utile. Le repère historique de **3 %** cité pour le rayon n'est pas une mesure de la période actuelle.

Ce taux est un repère historique, pas un substitut au taux calculé sur les données de l'article.
L'absence d'un fichier de casse ou de dons est normale lorsqu'il n'y a pas eu d'activité : elle
ne doit ni bloquer la commande ni faire déclarer les données incomplètes à elle seule.

## Ordre et photos des produits

Le tri demandé reste fruits non bio, puis légumes non bio, puis bio, avec l'ordre Webtelevente
à l'intérieur de chaque groupe. Ne pas modifier ce tri ni ajouter des sous-groupes sans la
comparaison demandée avec la liste du responsable.
Une photo est indicative : elle ne prouve ni code, ni prix, ni quantité, ni colisage.
Le rapprochement automatique exige une correspondance exacte avec l'offre et une entrée
cohérente déjà présente dans la proposition. Une entrée `nom:<libellé>` reste sans code métier
connu : la photo ne lui en crée pas un. Les associations exactes historiques prouvées peuvent
être conservées avec leur preuve privée, sans inventer une validation humaine.
Une association explicitement validée par le responsable conserve sa preuve et l'empreinte
de l'original. Elle résiste aux changements de libellé d'offre, mais reste contrôlée sur
l'identifiant et le libellé vérifiés dans la proposition. Les ambiguïtés et conflits restent
exclus. Voir `procedures/courrier.md` et `AGENTS.md`.

---

## Vocabulaire

| Terme | Sens |
|---|---|
| **TG** — tête de gondole | bout de rayon très visible ; son effet commercial doit être observé, pas converti en coefficient supposé |
| **Cadencier** | la liste des produits commandables chez un fournisseur, avec conditionnements et prix |
| **PCB / Cond. de base** | le nombre d'unités dans un colis |
| **Réappro** | le réapprovisionnement du rayon depuis la chambre froide |
| **Position** | écart physique par rapport au rayon plein, pas la quantité totale présente |
