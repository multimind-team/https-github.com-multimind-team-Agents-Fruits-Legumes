# Cockpit — feuille de route des analyses et de l’apprentissage local

Proposition du 19 septembre 2026, après lecture du code, des carnets et du référentiel documentaire. Ce document décrit des évolutions à développer ; il n’active aucune fonction ni aucune modification de commande.

La déclinaison technique destinée aux IA est désormais intégrée au référentiel : [fiche 24.3 — contrats et lots de développement](Documentation%20de%20l'application/24%20-%20Evolutions%20futures%20et%20roadmap/24.3%20-%20Contrat%20de%20developpement%20du%20cockpit%20et%20apprentissage%20local.html).

## 1. Point de départ vérifié

Le cockpit dispose du contexte terrain daté, des commentaires promotion modifiables, du journal photo local, du profil hebdomadaire et des graphiques de flux sur 14 jours. Les commentaires automatiques reprennent les données disponibles ; ils ne sont pas une analyse visuelle des photos ni un entraînement automatique.

Inventaire brut des carnets au moment de l’étude :

| Donnée | Présence constatée | Limite |
|---|---|---|
| Ventes | 138 730 lignes du 19/03/2024 au 18/09/2026, sur 838 dates distinctes | Ni nombre de tickets ni preuve de couverture complète par article/jour. |
| Prix de vente historique | Champ renseigné sur 3 161 lignes de vente | La présence du champ ne valide ni sa base fiscale ni sa qualité ; ne pas extrapoler au reste. |
| Livraisons | 2 170 lignes depuis le 19/08/2026 | Historique beaucoup plus court que les ventes. |
| Casse et dons | 376 lignes de casse, 189 de dons | Une absence de déclaration ne signifie pas zéro perte. |
| Prévisions archivées | Mécanisme développé ; aucun carnet annuel présent | La mesure des prévisions réellement faites doit se constituer progressivement. |
| Contexte et photos | Interfaces développées ; aucun carnet photo ni décision de contexte trouvé | La mémoire terrain reste à alimenter. |
| Météo et calendrier | Fichiers locaux présents | Couverture, qualité et date de disponibilité à vérifier avant chaque rapprochement. |

Les volumes ci-dessus sont des comptes de lignes brutes, pas un jeu d’entraînement déjà nettoyé ou validé. La marge historique reste indisponible dans le code actuel, faute de bases HT/TTC et TVA attestées. La feuille de route générale du chapitre 24 contient encore des fonctions désormais réalisées et des exemples prospectifs : le code prime pour distinguer existant et futur.

Le contrôle indépendant relève aussi 117 219 lignes de vente portant une unité inconnue dans le fait brut, et aucune date d’enregistrement/import dans ces faits de vente. Une correspondance historique prouvée peut rendre certaines lignes exploitables ; les autres doivent rester exclues des comparaisons quantitatives incompatibles. Ne pas inventer leur date de disponibilité à partir de la date de vente : ces archives peuvent documenter l’historique, mais ne prouvent pas ce qui était connu du moteur à chaque ancienne décision.

## 2. Une mémoire quotidienne du rayon

Créer une fiche par article et journée, liée à des événements plus précis lorsque l’heure est connue. Les flux importés alimentent automatiquement la fiche ; le responsable complète les observations. Un fait importé reste conservé dans sa source : sa correction passe par un nouvel événement avec motif.

| Domaine | Informations à conserver et à compléter | Utilité |
|---|---|---|
| Disponibilité | Présent en rayon, rupture rayon, réserve disponible, rupture totale, début/fin constatés, heure de réassort, disponibilité inconnue | Éviter d’interpréter les ventes limitées par une rupture comme une demande faible. |
| Prix et coût | Prix affiché et encaissé, unité, HT/TTC, TVA attestée, période, coût d’achat, remises, démarque, référence de pièce | Analyser CA, prix moyen et contribution commerciale sur un périmètre comparable. |
| Implantation | Zone identifiée, TG/îlot/meuble, longueur exposée, nombre de faces, stock de présentation, signalétique, dates, produits voisins | Comparer la performance par emplacement et par mètre d’exposition. |
| Fraîcheur et lots | Fournisseur, réception, lot si connu, origine, variété, calibre, maturité observée, quantité concernée, quantité vendable constatée, tri effectué | Comprendre les ralentissements, la casse et les différences fournisseurs. |
| Promotion | Identifiant stable de campagne, articles, dates, prix normal/promo, mécanique, visibilité, objectif, quantités engagées, livraisons attendues et reçues, disponibilité, bilan | Comparer les campagnes et préparer les engagements suivants. |
| Vie du magasin | Horaires et fermetures attestées, événement local, travaux, panne, fréquentation et tickets agrégés si disponibles | Distinguer un problème produit d’une baisse générale de fréquentation. |
| Action humaine | Action envisagée, décision prise, motif, résultat attendu, date d’évaluation, résultat observé | Constituer un historique des décisions et de leurs résultats. |
| Photos | Original local, date de prise de vue et de saisie, zone, plusieurs articles si nécessaire, campagne, étiquettes et commentaire corrigé | Replacer visuellement les événements dans leur contexte. |

La maturité seule ne déduit pas une quantité du stock. Les modifications analytiques et les consignes qui agissent sur le calcul restent explicitement distinguées à l’écran. La saisie d’une commande observée ne prouve pas son envoi au fournisseur.

Deux corrections de conception sont prioritaires avant d’apprendre sur les annotations : la maturité actuelle vaut « impeccable » par défaut, y compris pour une simple note ; prévoir « non observée » et une confirmation explicite. La campagne actuelle est regroupée par article et dates ; lui donner une identité indépendante des dates évitera qu’une correction de période duplique une campagne ou que deux offres distinctes soient confondues.

## 3. Rendre la saisie rapide et utile

- Une page « À compléter aujourd’hui » classe les informations manquantes selon leur utilité : rupture pendant une promo, prix manquant, réception problématique, contexte d’un fort écart.
- Saisie en tableau, navigation au clavier, filtres et sélection de plusieurs articles pour une même implantation. Prévisualiser les articles, dates et conséquences avant l’enregistrement groupé.
- Modèles d’observation : « TG installée », « réassort tardif », « lot trop mûr », « étiquette absente ». Chaque modèle prépare des champs modifiables ; il ne les présente pas comme des faits déjà constatés.
- Commentaires automatiques accompagnés de leurs chiffres, période et sources. Commandes « Confirmer », « Corriger », « Compléter » et « Information inconnue ». Une hypothèse générée reste une hypothèse jusqu’à observation.
- Historique avant/après, motif, auteur désigné par son rôle, date réelle de l’événement, date de saisie et référence de preuve. Annuler ou corriger ajoute une version ; cela n’efface pas l’original.
- Champs complémentaires personnalisables avec type, unité, valeurs possibles et définition. Toute modification de sens est versionnée pour ne pas mélanger deux interprétations à l’entraînement.
- Localement, export et sauvegarde comprenant données, annotations, originaux photo et versions. Vérifier la restauration. Aucun envoi de photos à une IA externe.

## 4. Bibliothèque de graphiques

Chaque graphique partage les filtres période, article, famille, fournisseur, zone et promotion. Il affiche son unité, la couverture des données et les valeurs manquantes. Un clic sur un point ouvre les faits, commentaires et photos associés. Les euros, kilogrammes, pièces et colis équivalents ne sont pas mélangés sur un axe sans conversion explicitée.

| Graphique proposé | Question à laquelle il répond | Condition |
|---|---|---|
| Courbes ventes, réceptions, pertes et prévisions avec repères terrain | Que s’est-il passé ce jour-là ? | Étendre le graphique au filtre choisi ; conserver l’absence de données visible. |
| Carte de chaleur jours × semaines | Quels jours vendent régulièrement mieux ? | Distinguer fermé, zéro observé, inconnu et rupture. |
| CA, prix moyen, volume et contribution commerciale | La hausse vient-elle du volume ou du prix ? | Prix historiques attestés ; marge seulement sur coûts et fiscalité documentés. |
| Classement des contributions et des pertes par article/famille | Quels produits concentrent les euros vendus, gagnés ou perdus ? | Afficher les articles exclus et la couverture. |
| Calendrier de disponibilité et durée des ruptures | Quand le produit était-il réellement disponible ? | Observations horaires ; ne pas inventer l’heure depuis des ventes quotidiennes. |
| Comparaison avant/pendant/après promotion | L’offre est-elle associée à un gain de volume ou de contribution ? | Jours comparables, disponibilité et contexte ; estimation distincte d’un effet causal démontré. |
| Ventes prix/volume et ventes météo | Quelles associations locales méritent un examen ? | Tenir compte des promotions, saisons et jours de semaine ; ne pas déduire directement un coefficient causal. |
| Rendement par TG ou mètre de rayon | Où l’exposition est-elle la plus productive ? | Mesures d’espace et périodes d’occupation connues. |
| Prévu/réalisé, biais et erreurs par horizon | Où le système surévalue-t-il ou sous-évalue-t-il ? | Prévisions enregistrées avant la décision ; unités comparables. |
| Commandé, confirmé, attendu et réceptionné | Où les engagements fournisseurs divergent-ils ? | Preuves séparées pour chaque étape, réceptions partielles et reliquats. |
| Comparateur de scénarios de précommande | Quel compromis entre disponibilité, reliquat et pertes ? | Stock vendable, engagements existants, horizon, durée de vie et contraintes vérifiés. |
| Carte de qualité des données | Qu’est-ce qui empêche une analyse fiable ? | Compteurs explicites de champs et journées documentés, pas score opaque. |

Un tableau de bord personnalisable affiche quelques graphiques favoris ; les autres restent accessibles dans les espaces Ventes, Rentabilité, Promotions, Terrain et Prévisions. Le thème sombre actuel est conservé.

## 5. Base d’entraînement locale

Construire une table analytique versionnée « article canonique × jour », et une table distincte « campagne × article ». Les événements horaires et les lots restent dans des tables liées. Les carnets sources demeurent la référence ; les tables analytiques sont reconstruisibles et ne réécrivent pas le stock.

Chaque ligne porte ses unités, sa couverture, ses références sources, ses dates d’effet, les dates auxquelles les informations étaient connues, et la version des traitements. Les correspondances de codes et conversions doivent être valides à la date étudiée ; le colisage actuel ne doit pas réécrire la réalité historique.

Séparer trois types de contenu : faits observés, déclarations humaines et calculs/hypothèses. Un commentaire automatique n’ajoute pas un nouvel exemple indépendant de vente. Plusieurs photos du même événement ne sont pas plusieurs résultats commerciaux. Les hypothèses de causes et ventes perdues estimées ne deviennent pas des vérités d’entraînement.

Pour reproduire une décision passée, n’utiliser que les informations disponibles à cet instant : prévision météo connue alors, prix et implantation prévus, stocks connus, engagements documentés. Le bilan de promotion rédigé après l’opération et la météo réellement constatée servent à expliquer le résultat, pas à simuler une connaissance préalable.

Archiver les prévisions selon plusieurs horizons pertinents : commande du lendemain et engagement promotionnel plusieurs semaines avant. Conserver modèle/version, instant de décision, horizon, paramètres, données utilisées et correction humaine. Le lecteur actuel choisit la dernière prévision avant chaque journée ; l’évaluation par horizon exige un lecteur supplémentaire des différentes versions, sans écraser les archives.

Comparer les futurs modèles à une référence simple et au moteur actuel, sur des périodes ultérieures à celles utilisées pour les régler. Mesurer erreur en quantité, biais, couverture des intervalles et performances par famille, saison et promotion. Évaluer ensuite les conséquences commerciales avec les limites des données disponibles. Une bonne erreur moyenne ne garantit pas moins de ruptures ni plus de marge.

Le premier modèle travaille en observation : prévisions conservées, comparées ensuite, sans modifier les commandes. Le déploiement d’une nouvelle règle relève d’une décision distincte après contrôle. L’apprentissage et les exports restent sur le PC ; aucune infrastructure cloud n’est nécessaire au périmètre proposé.

Références méthodologiques : [validation chronologique des prévisions](https://otexts.com/fpp3/tscv.html), [prévention des fuites d’information](https://scikit-learn.org/stable/common_pitfalls.html#data-leakage).

## 6. Ordre de réalisation proposé

1. **Fondations de collecte** : journal quotidien, ruptures et disponibilité, provenance/version des champs, identité stable des campagnes, retours sur commentaires, archivage vérifié des prévisions à venir. Résultat vérifiable : un événement corrigé garde son original et n’altère pas une ancienne décision.
2. **Analyses visuelles** : périodes libres, filtres communs, historique des prix, graphiques de ventes/pertes, chronologie photos et comparaison des promotions. Résultat vérifiable : chaque point se retrouve dans les sources et les inconnues restent visibles.
3. **Rentabilité et engagements** : sources de prix attestées, méthode de valorisation explicite, commandes confirmées, réceptions et reliquats. Résultat vérifiable : rapprochement des montants et des quantités sans double comptage ; aucun bénéfice net annoncé à partir de la seule marge produit.
4. **Apprentissage et simulation** : exports reproductibles, tests chronologiques, comparaison par horizon, scénarios de précommande et suivi des corrections humaines. Résultat vérifiable : score calculé sur des données non utilisées pour régler le modèle et explication des exclusions.

Le premier lot apporte la matière qui manque aujourd’hui aux trois suivants. L’objectif de saisie est quelques minutes par jour grâce au préremplissage et aux observations groupées ; ce temps devra être mesuré avec l’usage réel.

## Références internes relues

- [Architecture actuelle du cockpit](../reference/cockpit-pc.md) et [mode d’emploi](Cockpit%20PC%20-%20mode%20d'emploi.md).
- [Référentiel documentaire](Documentation%20de%20l'application/index.html) et [fiche cockpit](Documentation%20de%20l'application/cockpit-pc.html).
- `moteur/pilotage.py`, `moteur/contexte_terrain.py`, `moteur/previsions_archivees.py`, `moteur/photos_contexte.py`.
- `donnees/faits/2024.jsonl`, `2025.jsonl`, `2026.jsonl`, `donnees/decisions.jsonl`, météo et calendrier locaux : lecture seule.

Coordination et inventaire : Leader. Avis de conception : agent-tendances et agent-controle, relus par le Leader. Aucun changement de données métier dans cette étude.
