# Le métier — rayon fruits & légumes

À lire avant de conclure que quelque chose est anormal.

Consigne canonique : `AGENTS.md`. Ce document explique le métier ; les écritures et leurs droits
sont définis dans `reference/contrat-echange.md` et `donnees/pouvoirs.json`.

---

## La journée

| Heure | Quoi |
|---|---|
| 05h00 | La livraison arrive sur le quai. |
| 06h20 | Envoi des fichiers du jour par mail. |
| 06h30 | Rangement de la livraison en chambre froide. |
| 08h00 | Préparation de la commande du lendemain. |
| 09h20 | Envoi de la commande. **Limite absolue : 09h30.** |
| 19h00 | Mise à jour du stock dans l'application. |
| 19h30 | Fermeture. |

**Samedi** : la commande est livrée le **lundi**, pas de livraison le dimanche.
**Dimanche** : pas de livraison, ouverture 9h–12h15, **aucun fichier envoyé**. Les ventes du
dimanche arrivent dans l'envoi du lundi, avec celles du samedi.

---

## L'envoi du matin

Cadencier Mercalys, cadencier Webtelevente, vente et livraison **tous les jours** ; casse et
dons **seulement s'il y en a eu**.

### La règle temporelle d'or des fichiers du matin (Date du nom J vs Contenu réel) :
Dans les e-mails envoyés au petit matin (vers 05h00-06h30) avec une date de fichier **JJ.MM.AAAA (jour J)** :
1. **Les Ventes (`vente JJ.MM.AAAA`)** : portent **TOUJOURS sur la veille (J−1)**. La journée du jour J n'ayant pas encore commencé, les caisses arrêtent et exportent le bilan complet de la veille pendant la nuit. *(Le lundi matin, l'envoi couvre le samedi et le dimanche).*
2. **La Casse (`casse JJ.MM.AAAA`)** : porte **TOUJOURS sur la veille (J−1)**. Il s'agit des fruits et légumes triés et jetés lors de la fermeture de la veille.
3. **Les Dons (`don JJ.MM.AAAA` ou `dons JJ.MM.AAAA`)** : portent **TOUJOURS sur la veille (J−1)**. Ce sont les produits écartés pour les associations la veille au soir.
4. **Les Livraisons (`livraison JJ.MM.AAAA` ou bordereaux du jour)** : portent **TOUJOURS sur le jour même (J)**. Les camions (Scafruit, TerreAzur, etc.) sont déchargés sur le quai entre 05h00 et 06h00 avant l'ouverture du magasin. La marchandise est donc physiquement livrée et rangée pour la journée qui s'ouvre.

- **L'heure varie beaucoup** : vers 6h certains jours, en début d'après-midi d'autres. Rien ne se déclenche donc à heure fixe.
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

**Le moment du comptage change ce qu'il contient (Règle d'or chambre froide) :**

| Compté | Ce qui est dedans | Ce qu'on applique ensuite |
|---|---|---|
| **Entre 17h00 et la fermeture** (le soir) | La livraison du jour **et** les ventes écoulées | Rien du jour même. La livraison du lendemain s'ajoutera à son arrivée le matin. |
| **Le matin, AVANT la réception du mail** (ex. 5h30) | Le stock de la veille. La livraison **n'est pas encore entrée** en chambre froide. | La livraison du matin **DOIT s'ajouter** au stock à son arrivée. Les ventes du jour seront déduites. |
| **Le matin, APRÈS la réception du mail** (ex. 7h15) | La livraison est rangée, **aucune vente** encore passée | Ventes, casse et dons du jour — **jamais la livraison** (déjà dedans). |

L'heure du comptage est donc enregistrée précisément, pas seulement le jour. Sans heure connue, il est
traité comme un comptage du soir.

Le moteur utilise l'heure réelle de réception du mail de livraison du matin pour distinguer exactement
si le comptage a été fait avant ou après l'arrivée physique des palettes en chambre froide.

Un recomptage remet la position à jour, même si les statistiques de ventes reçues sont anciennes.
Conserver les deux dates ; ne pas dégrader le stock recompté au seul motif des anciennes ventes.
Inversement, une seule livraison récente ne valide pas la couverture de tous les articles.

**Pas de position du tout** : sans mesure exploitable, la position est inconnue, pas zéro.
L'écran n'invente aucun chiffre. Un article sans activité depuis longtemps peut ne plus être en
rayon, mais une absence de mesure ne suffit pas à le prouver : vérifier les faits avant de masquer.

Le calcul, lui, **traite une position inconnue comme 0** — « rayon plein, réserve vide » — et
propose donc la demande attendue. Si un tel article n'est pas commandé, c'est parce que sa
demande attendue est nulle (moins de 5 jours de vente observés dans la fenêtre de saison), pas
parce que sa position manque. Un article qui **continue de vendre** mais qu'on a cessé de
compter sera donc bien commandé.

**À partir de −10 colis inclus**, l'écran affiche `--` : ce n'est plus une mesure, c'est le signe
qu'on a perdu le fil. Il faut recompter.

---

## Les fournisseurs

| Fournisseur | Part du rayon | Comment sa livraison arrive |
|---|---|---|
| **Scafruit** — l'officiel | ~79 % | dans le fichier `Livraison-*.xlsx`, intégré tout seul |
| **Pomona / TerreAzur** | ~14 % | **facture reçue par mail**, à lire et à saisir |
| Garrigues, Pouget, autres directs | ~6 % | **facture reçue par mail**, à lire et à saisir |

On commande chez Pomona en cas de rupture chez Scafruit, et certains produits en permanence pour
le prix ou la qualité. Ça change régulièrement.

**Les factures de livraison de tous les fournisseurs arrivent par mail.** Mais seul le fichier
`Livraison-*.xlsx` de Scafruit est intégré automatiquement : une facture est un document, pas un
fichier de données. Tant que personne ne la saisit, l'entrée en stock n'existe pas — pour
environ **un article sur cinq**, toutes les sorties sont alors enregistrées et **aucune entrée**,
et la position ne peut que descendre toute seule.

**D'où l'obligation de lire et contrôler les factures directes**, puis de confier leur import à
`agent-donnees` selon `procedures/courrier.md`. Pour Pomona/TerreAzur, le parcours normal utilise
`moteur/importer-facture-directe.py`, la simulation, la validation explicite du responsable ligne
par ligne et la vérification séparée des faits et de la marge. Ne jamais prendre le PV dans le
seul catalogue ni supposer le colisage du jour.

`moteur/enregistrer-livraison-directe.py` est un outil historique de saisie unitaire, pas un
équivalent sûr du validateur facture : ne pas l'utiliser en automatique ni cumuler les deux
parcours pour une même livraison. Un fournisseur sans mapping vérifié nécessite une décision
humaine ; ne pas appliquer les codes TerreAzur à un autre fournisseur.

Un comptage remet la position juste quelle que soit l'origine de la marchandise. Une position qui
remonte sans livraison enregistrée indique une anomalie à enquêter, **pas une quantité livrée
prouvée** : erreur de mesure, unité ou mouvement oublié restent possibles. Aucune entrée déduite
ne doit être inventée pour équilibrer le calcul.

**Le masquage est réversible** : un article masqué n'est pas en rayon *pour l'instant*.
Vérifier les changements intervenus depuis avant une annulation : réversible ne veut pas dire
qu'il soit sûr de restaurer n'importe quelle ancienne valeur sans contrôle.

---

## Trois cas normaux à ne jamais signaler

**Les oranges de la machine à jus** ne passent jamais en caisse : elles partent à la presse. Ce
sont les ventes de jus qui les font sortir — **2 kg par litre, 1 kg par 50 cl**.

**Le box et la caissette** : pommes de terre et filets d'orange existent en box (65 filets, 90
pour l'orange) et en caissette (8, ou 9). Seules les caissettes sont commandées, donc **un box
compte +8**, pas +65.

**Le colisage change d'une livraison à l'autre**, surtout chez Pomona : 6 pièces un jour, 12 le
lendemain. **Ne jamais le supposer** d'après une livraison précédente : le relire sur la facture
du jour.

---

## Casse et dons

Marchandise sortie sans être vendue ; la casse est jetée, les dons vont aux Restos du Cœur.
**Strictement équivalents pour le calcul** : les deux entrent dans le taux de perte, qui gonfle
la commande. Ils restent séparés dans les carnets parce que la destination est une information
utile. Le taux de perte du rayon tourne autour de **3 %**.

Ce taux est un repère historique, pas un substitut au taux calculé sur les données de l'article.
L'absence d'un fichier de casse ou de dons est normale lorsqu'il n'y a pas eu d'activité : elle
ne doit ni bloquer la commande ni faire déclarer les données incomplètes à elle seule.

## Ordre et photos des produits

Le cadencier Webtelevente reste la référence de l'ordre. Conserver ses séparateurs Fruits,
Légumes et Bio et les sections qui se répètent ; ne pas ajouter un regroupement global ou un tri.
Une photo est indicative : elle ne prouve ni code, ni prix, ni quantité, ni colisage. Les seules
associations publiées viennent d'une correspondance exacte, unique et cohérente avec une ligne
déjà présente dans la proposition. Voir `procedures/courrier.md`.

---

## Vocabulaire

| Terme | Sens |
|---|---|
| **TG** — tête de gondole | bout de rayon, très visible : ce qui y est mis se vend nettement plus |
| **Cadencier** | la liste des produits commandables chez un fournisseur, avec conditionnements et prix |
| **PCB / Cond. de base** | le nombre d'unités dans un colis |
| **Réappro** | le réapprovisionnement du rayon depuis la chambre froide |
| **Position** | la mesure du besoin — **pas** un stock |
