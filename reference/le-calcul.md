# Le calcul de la commande

Cette formule est le fruit de dizaines de corrections vérifiées sur les vraies données. Elle ne
se réinvente pas.

---

## La formule

```
Pour chaque article :

  tauxPerte = pertes / (ventes + pertes)        (5 % si aucun historique)

  demandeAujourdhui = venteMoyenne[jour de la commande]  × météo × férié × vacances × jourSemaine
  demandeLivraison  = venteMoyenne[jour de la livraison] × météo × férié × vacances × jourSemaine

  quantité = max(0, demandeLivraison − ( position − demandeAujourdhui ))

  (les deux demandes sont divisées par (1 − tauxPerte) pour couvrir la casse)

  puis arrondi au colis
```

**La commande ne couvre qu'un seul jour : celui de la livraison.** Si deux demandes
apparaissent, c'est parce que la position date de la veille au soir : il faut lui retirer ce qui
sera vendu aujourd'hui.

*Exemple.* Concombres, position lundi soir 2 colis, vente ~3/jour. Mardi on commande pour
mercredi : il faut 3 colis, il en restera 2 → **on commande 1**.

**La position est soustraite**, et comme elle peut être négative, une position de −3 **augmente**
la commande de 3.

**Attention à l'ordre du matin :** ce qui est mesuré ne contient jamais la livraison du jour (le
comptage se fait avant de rentrer la marchandise) ; le calcul l'ajoute lui-même. Si l'ordre
changeait — rentrer la livraison avant de compter — **la marchandise serait comptée deux fois**.

---

## La vente moyenne

Moyenne des ventes dans une fenêtre de **± 21 jours autour de ce jour de l'année, toutes années
confondues**.

**Moins de 5 jours de vente observés dans la fenêtre → prévision zéro**, jamais la moyenne
annuelle. Sans cette règle, des clémentines dont la dernière vente datait de décembre recevaient
encore une prévision fin août.

### Visualisation et contrôle de la vente moyenne (écran de commande)

Dans l'application web (`app/commander.html`), un clic sur n'importe quel article ouvre un **graphique annuel interactif** confrontant la vente retenue par le moteur avec l'historique réel sur 2,5 ans :
- **Bâtonnets mensuels** : moyenne historique par mois sur 2,5 ans, montrant le profil de consommation annuelle du rayon.
- **Courbe pointillée (2025)** : ventes hebdomadaires de l'année précédente (N-1), avec rupture visible dès qu'un article n'a pas été approvisionné.
- **Courbe blanche continue (2026)** : ventes quotidiennes de l'année en cours, révélant immédiatement les ruptures de stock ou les reprises de livraison.
- **Pastille de vente du jour & Cap mois suivant** : situe la cadence actuelle par rapport à la moyenne du mois et projette la tendance vers le mois prochain (hausse, stabilité, repli).
- **Rentabilité financière** : cartouche récapitulant la marge brute actuelle (%), le gain brut par colis, le prix d'achat et le prix de vente.

---

## Les facteurs

| Facteur | Règle |
|---|---|
| **Météo** | **juin à août uniquement** : pluie ≥ 10 mm → ×0,901 · température ≥ 25 °C → ×1,076 (cumulables). Hors été : 1. |
| **Jour férié** | ×0,54 si une **demi-journée** a été confirmée, ×1 sinon. La confirmation est demandée quelques jours avant (`moteur/ouverture-jours-feries.py`) ; sans réponse, le calcul n'invente rien. |
| **Vacances scolaires** (zone C) | par période : Noël ×1,162 · Toussaint ×1,045 · Été ×1,027 · Hiver ×1,002 · Printemps ×0,984 · Ascension ×0,901. |
| **Jour de la semaine** | tiré du profil hebdomadaire réel du magasin. |

---

## L'arrondi

- Livré il y a **7 jours ou moins** → arrondi au colis **le plus proche** (sous un demi-colis,
  la commande tombe à zéro).
- **Jamais livré, ou pas depuis plus de 7 jours** → arrondi au colis **supérieur**.

Sans ce garde-fou, un article à faible demande régulière — gingembre, colis de 5 kg pour 2 kg de
demande — ne serait plus jamais recommandé.

---

## Commande forcée à zéro

1. **Article en promotion** — précommandé par le chef de rayon. *Exception :* si la livraison
   tombe un lundi, la promo (mardi→samedi) est finie, le blocage ne s'applique pas.
2. **Position à −5 ou moins** — **sauf** si l'article a été compté dans les 7 derniers jours,
   auquel cas la mesure fraîche fait foi.

---

## Le cycle des dates

- **Date de commande** = lendemain de la dernière journée de ventes reçue — **jamais la date de
  l'ordinateur**. Décalée si dimanche ou férié.
- **Date de livraison** = lendemain de la date de commande, même décalage.
- Commande du **samedi** → livraison le **lundi**.
- Dans les fichiers, une livraison est datée de sa **date de commande**, pas de sa réception.
  Chercher la livraison à sa date de réception donne une clé qui n'existe pas : elle n'est alors
  **jamais ajoutée au stock**, en silence.

---

## Les pièges connus

| Le piège | La parade |
|---|---|
| **Date de l'ordinateur** | « aujourd'hui » vient toujours des données reçues |
| **Journée incomplète** (export généré à 13h38) | toute ligne datée du jour de génération du fichier est écartée |
| **Même journée comptée deux fois** | étiquette unique par mouvement : on recalcule, on ne décrémente jamais |
| **Livraison cherchée à la mauvaise date** | deux dates séparées dès l'import |
| **Deux codes pour un produit** | le code d'origine est conservé à côté du code retenu |
| **Position qui plonge sans fin** | livraisons directes saisies à la main, ou entrées déduites |
| **Prévision hors saison** | moins de 5 jours observés → zéro |
| **Correction invisible sur le téléphone** | tout changement de données change le marqueur de version |
| **Réglage écrasé par une page restée ouverte** | l'écran ne réécrit jamais un réglage qu'il n'a pas modifié |
| **Article en promo resté masqué** | une promotion démasque toujours ; la fin d'une promo ne remasque pas |

---

**Quand un document et le code se contredisent, c'est le code qui dit la vérité.**

**Conditionnements encore douteux** : raisin blanc Italia, tomate ronde en grappe, tomate ronde
noire, carton d'orange à jus (12 kg, estimé, jamais vérifié).
