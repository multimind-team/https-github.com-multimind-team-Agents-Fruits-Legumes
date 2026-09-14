# Les carnets

Comment les fichiers sont faits, et qui a le droit d'y écrire. Si une règle change, elle change
**ici d'abord**, jamais dans une fiche de rôle.

---

## Les fichiers

| Fichier | Contenu | On efface ? | Qui écrit |
|---|---|---|---|
| `faits/AAAA.jsonl` | ce qui s'est **passé**, un fichier par année | jamais | préparateur |
| `decisions.jsonl` | les **réglages** des articles | jamais | préparateur, assistant |
| `etat.json` | la position **d'aujourd'hui** | à volonté | préparateur |
| `travaux.jsonl` | ce qui est **à faire** | jamais | l'application |
| `journaux/<rôle>.jsonl` | ce que chaque rôle a fait, avec l'avant et l'après | jamais | le rôle |
| `journaux/tout.jsonl` | les mêmes actions, tous rôles, dans l'ordre | jamais | tous |
| `ajustements.jsonl` | les ajustements de commande | jamais | analyste |
| `faits/analyse_historique_ventes.json` | profil de vente et saisonnalité sur 2,5 ans | à volonté | `analyser_historique_ventes.py` |
| `pouvoirs.json` | qui a le droit de faire quoi seul | à volonté | le responsable de rayon |

Les `.jsonl` sont des fichiers texte : **une ligne par information**, ajoutée à la suite. On ne
revient jamais modifier une ligne écrite.

> **`etat.json` ne fait jamais foi.** On doit pouvoir le supprimer, tout relire depuis le début,
> et retrouver exactement le même stock.

---

## Les faits

Une ligne = un mouvement qui a vraiment eu lieu. En cas d'erreur, on **ajoute** une ligne qui
annule la précédente.

```json
{
  "id": "livraison:2026-08-29:0000087004958:14",
  "type": "livraison",
  "date_source": "2026-08-29",
  "date_effet": "2026-08-31",
  "article": "0000087004958",
  "article_source": "0000087005028",
  "quantite": 60,
  "unite": "kg",
  "libelle": "CITRON VRAC",
  "source": {"origine": "mail/Livraison 31.08.2026.xlsx", "ligne": 16}
}
```

**`id`** — fabriqué à partir du type, de la date, de l'article et de la ligne du fichier
d'origine. Si l'étiquette existe déjà, la ligne est ignorée : on peut relancer un traitement dix
fois sans changer le résultat.

**`date_source` / `date_effet`** — la date écrite dans le fichier (pour une livraison : la date
de **commande**), et le jour où la marchandise arrive vraiment. Les confondre fait chercher la
livraison à une date qui n'existe pas.

**`article` / `article_source`** — le code retenu **et** le code d'origine. Si un rapprochement
se révèle faux, on peut tout refaire.

**`quantite` / `unite`** — toujours en kilos ou en pièces, **jamais en colis** : le nombre de
pièces par colis change d'une livraison à l'autre.

**Les cinq types :**

| Type | Effet |
|---|---|
| `livraison` | ajoute |
| `vente` | retire |
| `casse` (jetée) | retire |
| `don` (Restos du Cœur) | retire |
| `comptage` | **remplace** tout ce qui précède |

Un comptage porte `"mesure": "position"` et `origine_mesure`. Il remet l'incertitude à zéro ; les
mouvements postérieurs s'appliquent par-dessus. La position n'est **pas un stock** : voir
`reference/le-metier.md`.

---

## Les décisions

Constater un mouvement et **interpréter** sont deux choses différentes. « Ces deux codes sont le
même produit », « ce carton contient 80 bananes » : ce sont des conclusions, et il faut pouvoir
les rejouer ou les défaire.

```json
{
  "id": "fusion:0000087004958:2026-08-30",
  "type": "fusion",
  "principal": "0000087004958",
  "membres": ["0000087005028"],
  "valide_a_partir_de": "2026-08-30",
  "motif": "Livré sous un code, jamais vendu sous celui-ci. Vérifié sur le bordereau.",
  "auteur": "preparateur",
  "enregistre_le": "2026-08-30T21:14:02"
}
```

Types : rapprocher deux codes ou les séparer, corriger un fournisseur, un conditionnement, une
unité, cacher ou réafficher un article, signaler une promotion.

**Trois obligations, sans exception :**

1. **une date de début** — une décision d'aujourd'hui ne réécrit pas le passé ;
2. **une explication** ;
3. **la validation notée** — ce qui est proposé n'entre pas dans le calcul tant que ce n'est pas
   validé.

**Les événements du terrain** (tête de gondole, fête locale) sont un type à part. Deux règles :
**aucun effet inventé** — tant que l'ampleur n'a pas été mesurée, l'événement est signalé à
l'écran, jamais appliqué au calcul ; et **une période, pas une date** — sinon son effet se
prolonge indéfiniment.

**Les réglages sont rejoués, jamais stockés.** Le fournisseur d'un article, son colisage, son
unité, s'il est masqué : tout est reconstitué en rejouant le carnet (`moteur/regles.py`), la
ligne la plus récente gagne. Les décisions du **2 septembre 2026** sont les décisions
fondatrices ; tout ce qui a été décidé depuis s'empile par-dessus. Une décision retirée n'est
pas gommée : on ajoute une ligne qui remet la valeur d'avant.

```
python moteur/regles.py 0000087010624
```

---

## L'état

`etat.json` est **recalculé** par `calculer-position.py` : par article, la position, la date du
dernier comptage, celle du dernier mouvement, et le signal « trop bas pour être crédible ». Il
retient aussi le dernier jour de ventes connu — **jamais** la date de l'ordinateur.

**Interdit :** modifier le stock sans avoir d'abord écrit le mouvement qui le justifie.

---

## Qui écrit où

| Rôle | faits | décisions | position | commande | son journal |
|---|---|---|---|---|---|
| préparateur | oui | oui, dans ses limites | oui | — | oui |
| assistant de rayon | oui (comptages) | oui | oui | — | oui |
| analyste des tendances | — | — | — | oui | oui |
| détective des articles | — | — | — | — | oui |
| contrôleur | — | — | — | — | — |

Les limites sont dans `pouvoirs.json`, et **l'outil refuse ce qui dépasse** : une consigne écrite
peut être oubliée, un refus non. Le contrôleur ne modifie rien : c'est celui dont une erreur —
valider ce qui n'aurait pas dû l'être — coûterait le plus cher.

---

## Les cinq propriétés à garantir

Si l'une tombe, quelque chose est cassé.

1. **On peut tout reconstruire** — supprimer `etat.json`, tout relire, retrouver les mêmes
   chiffres.
2. **On peut tout refaire dix fois** — réimporter le même fichier ne change rien.
3. **Chaque chiffre s'explique** — on remonte aux mouvements qui composent une position.
4. **Rien sans explication.**
5. **On peut revenir en arrière** — retirer une décision et tout relire redonne la situation
   d'avant.

---

## Ce que les carnets ne contiennent pas

- **La proposition de commande** — un calcul refait à neuf à chaque fois
  (`proposition.json`, écrasé). Ce qu'un rôle en *dit* est un événement (`ajustements.jsonl`).
- **Les cadenciers** — des catalogues, pas des mouvements.
- **La météo et les jours fériés** — des ingrédients du calcul.

---

## Où aller vérifier

| Pour vérifier | Commande |
|---|---|
| un chiffre sur un article | `python moteur/agregats.py <code>` |
| le nom, le prix, le conditionnement | `python moteur/catalogue.py <code>` |
| pourquoi ce réglage | `python moteur/regles.py <code>` |
| ce qu'un rôle a fait | `python moteur/annuler.py --liste` |
| le profil de saisonnalité d'un article | `python moteur/analyser_historique_ventes.py` ou fiche détail dans `app/commander.html` |

Un chiffre juste au moment où il a été calculé peut être faux au moment où on le répète : entre
les deux, un comptage est arrivé, ou une décision a été appliquée.
