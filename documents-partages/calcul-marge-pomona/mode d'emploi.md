# Calcul de marge Pomona — mode d'emploi

Le fichier Excel de ce dossier calcule, livraison par livraison, la marge réelle sur ce qui vient
de Pomona / TerreAzur.

---

## Le fichier

`0926 Calcul marge Pomona.xlsx` — le nom porte le mois : **09** = septembre, **26** = 2026.
**Un nouveau fichier chaque mois**, copie de celui-ci avec toutes les feuilles vidées sauf
« Vierge ».

- **Vierge** — le squelette, jamais rempli directement. C'est elle qu'on copie. Il ne faut jamais modifier cette feuille.
- **01**, **02**, **04**… — une feuille par jour de livraison. Un jour sans livraison saute son
  numéro.

---

## Créer la feuille du jour

1. Copier l'onglet **Vierge** (clic droit → Déplacer ou copier → « Créer une copie »).
2. Renommer avec le numéro du jour.
3. Remplir à partir de la **ligne 4**. Les lignes 1 à 3 et les colonnes G et suivantes sont des
   formules : **ne rien y toucher**.

**Si la copie se fait par un programme Python :** `copy_worksheet()` ne recopie **pas** les
règles de mise en forme conditionnelle (les couleurs des colonnes B à E). Il faut recopier
`src.conditional_formatting` explicitement (chaque plage et ses règles, via `copy.deepcopy`),
puis vérifier que la feuille en a autant que « Vierge ».

---

## Les colonnes

| Colonne | Contenu | Où le trouver |
|---|---|---|
| **A** — Produit | le nom simplifié (« Poireau ») | le bordereau |
| **B** — PA base | — | **NE PAS REMPLIR** |
| **C** — PA direct | le prix réellement payé | colonne **PU** du bordereau |
| **D** — PV préco base | — | **NE PAS REMPLIR** |
| **E** — PV magasin | — | **NE PAS REMPLIR** |
| **F** — Quantité | en kg ou en pièces, **jamais en colis** | colonne **« Qté fact. UF »**. C'est exactement la quantité qui sert à enregistrer la livraison en stock — ne la recalcule pas deux fois. |

> **B et D restent vides** : les prix du cadencier ne correspondent pas à ce que le rayon paie
> réellement sur ces produits. Une marge fausse est pire qu'une case vide — une case vide se
> voit, un chiffre faux se croit.

---

## Lire le bordereau

Chaque ligne porte : n° de ligne / code TerreAzur / désignation — puis **Qté livrée** (en colis),
**Qté fact. UF** (poids ou pièces, parfois suivi du poids brut entre parenthèses, à ignorer),
**PU** et **MT HT**.

**Vérification avant de valider une ligne :** Montant HT ÷ PU doit retomber exactement sur la
valeur mise en colonne F. Sinon, mauvaise colonne de quantité.

**Le colisage change d'une livraison à l'autre** — la laitue feuille de chêne arrive tantôt par
6, tantôt par 12. Relire la mention sur la facture du jour (« 12P », « 6P »), ne jamais la
supposer.

---

## Les codes

Les codes du bordereau sont ceux de TerreAzur, pas ceux du magasin. Les correspondances vérifiées
sont dans `donnees/fournisseurs/codes-terreazur.json` : **regarde ce fichier en premier**.

Si le code n'y est pas, cherche par le **nom** du produit, puis ajoute la correspondance une fois
sûr — une ligne à la fois, jamais par lot, et seulement des correspondances démontrées. Une
correspondance fausse écrit un mouvement sur le mauvais article.

---

## Envoyer

Toujours avec l'outil : un fichier Excel est un binaire, le recopier peut le corrompre sans que
ça se voie.

```
python moteur/envoyer-piece-jointe.py DESTINATAIRE "Sujet" "Corps du message" "documents-partages/calcul-marge-pomona/0926 Calcul marge Pomona.xlsx"
```

**Destinataire OBLIGATOIRE : `PDV11768@mousquetaires.com`.** Le classeur doit TOUJOURS être envoyé à cette adresse générique du point de vente, quelle que soit la personne ou l'adresse expéditrice qui a envoyé la photo de la facture Pomona.
