# Calcul de marge Pomona — mode d'emploi

Le fichier Excel de ce dossier prépare, livraison par livraison, les éléments facturés par
Pomona / TerreAzur. L'agent renseigne A/C/F uniquement. Sans prix de vente réel renseigné et
vérifié par le responsable, aucun taux de marge n'est validé.

---

## Les fichiers et la procédure

- **`Calcul marge Pomona - Original.xlsx`** : le classeur de référence original. **INTERDICTION FORMELLE DE MODIFIER CE FICHIER**.
- **`Calcul marge Pomona.xlsx`** : la copie de travail officielle. L'agent effectue une copie de `Calcul marge Pomona - Original.xlsx` renommée `Calcul marge Pomona.xlsx`. Tout le travail est effectué exclusivement sur ce fichier.
- **Vierge** : l'onglet modèle du classeur, jamais rempli directement.
- **Feuille du jour** : la feuille « Date du jour » (ou une copie de l'onglet Vierge) est renommée avec la vraie date du jour de livraison indiqué sur la facture (ex: `18`, `19`).

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
| **F** — Quantité | quantité facturée UF, **jamais le nombre de colis** | colonne **« Qté fact. UF »**. Pour une nouvelle livraison en stock, l'unité physique doit en plus être attestée et compatible avec l'article magasin. |

> **B/D/E restent vides sur les nouvelles lignes préparées par l'agent**. Ne pas déduire de prix
> de vente depuis le catalogue. Préserver les valeurs saisies manuellement et l'historique existants.

---

## Lire le bordereau

Chaque ligne porte : n° de ligne / code TerreAzur / désignation — puis **Qté livrée** (en colis),
**Qté fact. UF** (poids ou pièces, parfois suivi du poids brut entre parenthèses, à ignorer),
**PU** et **MT HT**.

**Vérification avant de valider une ligne :** l'écart absolu entre Montant HT et
« Qté fact. UF × PU » doit être inférieur ou égal à **0,01 €**, sans arrondir un écart supérieur
pour le faire accepter. Au-delà, refuser la ligne et relire la source.

**Le colisage change d'une livraison à l'autre** — la laitue feuille de chêne arrive tantôt par
6, tantôt par 12. Relire la mention sur la facture du jour (« 12P », « 6P »), ne jamais la
supposer.

---

## Les codes

Les codes du bordereau sont ceux de TerreAzur, pas ceux du magasin. Les correspondances vérifiées
sont dans `donnees/fournisseurs/codes-terreazur.json` : **regarde ce fichier en premier**.

Si le code n'y est pas, suspendre la ligne et transmettre les preuves pour vérifier la
correspondance selon `AGENTS.md` et les pouvoirs applicables. Le nom seul n'autorise pas un
rapprochement. Une correspondance fausse écrit un mouvement sur le mauvais article.

---

## Préparer le document et distinguer le stock

Lire toutes les pages puis écrire un JSON avec `fournisseur` (`POMONA` ou `TERREAZUR`, casse
indifférente), `date_reception` (`AAAA-MM-JJ`), `bordereau`, `pages_lues`, `pages_totales` et
`lignes`. Les deux nombres de pages sont des entiers positifs égaux. Chaque ligne contient
`code_fournisseur`, `produit`, `quantite_uf`, `pu`, `montant_ht`, et `colis` si celui-ci est lu.
Relever également `unite_uf` depuis la source physique avant tout **nouvel import de stock** ;
ne pas la déduire du prix ou de l'unité du catalogue. Si elle manque ou ne concorde pas, le stock
est refusé. Le mode document seul reste possible lorsque les autres contrôles sont valides.

Pour préparer A/C/F sans lire ni écrire le stock :

```text
py -3.14 moteur/importer-facture-directe.py "<json-verifie>" --marge "<classeur-du-mois>" --classeur-seul --simuler
```

Après contrôle, retirer seulement `--simuler`, conserver `--classeur-seul`, puis vérifier le
classeur réel. La simulation ne prouve pas que le fichier sera disponible en écriture.
L'import de stock est une opération distincte : simulation sans `--classeur-seul`, contrôle
indépendant et validation explicite du responsable sur chaque ligne avant l'exécution par
`agent-donnees`. Suivre `procedures/courrier.md` pour les reprises et le recalcul.

## Mettre à disposition et envoyer

Le serveur liste les fichiers remplis dans `GET /api/marges-pomona`. Transmettre au responsable
le lien `url` retourné et vérifier son téléchargement. L'accueil ne comporte pas de bouton
« Marge Pomona ». Cette liste ne constitue pas une validation des prix ou des marges.

Noms reconnus dans ce dossier : `Calcul marge Pomona.xlsx` (classeur de travail courant), `MMYY Calcul marge Pomona.xlsx` et
`MMYY Calcul marge Pomona - livraison JJ-MM-AAAA.xlsx`. Pour apparaître, le classeur doit contenir une feuille nommée
sur deux chiffres correspondant à un jour valide du mois : à partir de la ligne 4, au moins une
ligne doit avoir un produit textuel en A et une quantité numérique strictement positive en F.
Le modèle « Vierge » seul n'est pas proposé. Vérifier séparément les cellules A/C/F, les formules,
les saisies manuelles et le fichier téléchargé.

Pour l'envoi par courriel :
- L'adresse officielle du magasin est **`PDV11768@mousquetaires.com`**.
- Commande d'envoi :

```text
py -3.14 moteur/envoyer-classeur-marge.py --destinataire "PDV11768@mousquetaires.com" --classeur "documents-partages/calcul-marge-pomona/Calcul marge Pomona.xlsx"
```

Lire le JSON : `smtp_accepte: true` prouve la remise SMTP, pas la réception. Dès que le courriel est envoyé avec succès, le fichier de travail temporaire `Calcul marge Pomona.xlsx` est automatiquement supprimé, tandis que `Calcul marge Pomona - Original.xlsx` reste préservé intact. L'absence de demande d'envoi ou de destinataire ne bloque pas la mise à disposition du document par son lien.
