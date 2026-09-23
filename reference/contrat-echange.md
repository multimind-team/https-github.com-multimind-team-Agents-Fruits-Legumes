# Les carnets

Comment les fichiers sont faits et comment tracer leurs écritures. La consigne canonique
reste `AGENTS.md` et les permissions sont déclarées dans `donnees/pouvoirs.json` ; ce contrat
décrit les formats sans créer de pouvoirs supplémentaires.

---

## Les fichiers

Les chemins de ce tableau sont relatifs à `donnees/`.

| Fichier | Contenu | On efface ? | Qui écrit |
|---|---|---|---|
| `faits/AAAA.jsonl` | ce qui s'est **passé**, un fichier par année | jamais | importeurs autorisés sous `agent-donnees`, serveur pour les comptages humains |
| `decisions.jsonl` | les **réglages** des articles | jamais | agents autorisés selon `pouvoirs.json`, serveur pour les décisions humaines |
| `etat.json` | la position calculée depuis les mesures et mouvements | régénérable | moteur de calcul |
| `messages.jsonl`, `reponses.jsonl` | demandes et réponses de l’application | jamais | serveur et agents autorisés |
| `journaux/<rôle>.jsonl` | ce que chaque rôle a fait, avec l'avant et l'après | jamais | le rôle |
| `journaux/tout.jsonl` | les mêmes actions, tous rôles, dans l'ordre | jamais | tous |
| `ajustements.jsonl` | les ajustements de commande | jamais | auteurs habilités selon `pouvoirs.json` et validation de la demande |
| `entrainement-ajustements.jsonl` | carnet d'entraînement IA (CP-04) capturant le contexte complet lors des ajustements | jamais | `moteur/enregistrer_modifications_commande.py` (via `POST /api/ajustements-commande` ou `ajuster-commande.py`) |
| `propositions/proposition-AAAA-MM-JJ.json` | archive figée de la proposition algorithmique initiale du jour | jamais | `moteur/enregistrer_modifications_commande.py` |
| `agregats.json` | statistiques et profils saisonniers des articles | régénérable | `moteur/agregats.py`, avec les calculs de `moteur/calculer-commande.py` |
| `analyse-ventes-annuelle-saisonniere.json` | analyse des années, mois et saisons disponibles | régénérable | `moteur/analyser-historique-complet.py` |
| `proposition.json`, `articles.json` | proposition et aide au comptage | régénérables | producteurs du moteur |
| `fraicheur.json`, `recalcul.json` | contrôles de fraîcheur et état d'une opération de calcul | régénérables | filet de sécurité et opérations coordonnées |
| `pouvoirs.json` | qui a le droit de faire quoi seul | modification explicite seulement | le responsable de rayon |

Les `.jsonl` sont des fichiers texte : **une ligne par information**, ajoutée à la suite. On ne
revient jamais modifier une ligne écrite.

> **`etat.json` est une sortie calculée, pas une preuve d'entrée physique.** Pour reproduire
> une position, conserver les faits, les décisions, les référentiels et unités nécessaires,
> la date de calcul et la version du moteur. Les horodatages de publication peuvent changer.
> La reconstruction s'essaie en copie ; supprimer ce fichier réel n'est pas une étape d'audit.

---

## Les faits

Une ligne = un fait attesté. En cas d'erreur, conserver l'original et utiliser la
procédure de correction applicable par nouvel événement explicite ; un type d'événement
inventé ne corrige pas le calcul.

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

**`id`** — identité stable du fait. Les anciens identifiants sont conservés ; les importeurs vérifient aussi les équivalences de contenu pour résister au réordonnancement des lignes. Une version différente d’un mouvement déjà reçu exige une correction explicite, jamais un second ajout silencieux. La ligne du fichier reste une preuve de provenance, pas une identité métier suffisante.

**`date_source` / `date_effet`** — la date portée ou interprétée depuis la source, et le jour
auquel le mouvement agit sur la position. Pour Scafruit, l'importeur lit la date de commande
dans l'en-tête, sinon dans le nom, puis déduit une réception le lendemain en sautant le
dimanche. Cette convention n'applique pas le calendrier complet des jours fériés : vérifier
la réception réelle. Pour une facture directe ou une saisie de livraison manuelle, les deux
champs reprennent la date de réception attestée. Pour les sorties, ils reprennent la journée
interne de vente, casse ou don. Un fichier tardif conserve son jour d'effet ; ne pas le redater
au jour de réception du mail.

**Heure physique et enregistrement** — pour un comptage de l'API courante, `source.saisi_le`
et `horodatage` conservent l'instant de saisie ; `enregistre_le` date l'enregistrement technique.
Ces champs ne sont pas tous présents dans les autres importeurs et n'ont pas partout ce même
contrat. Le lecteur de position privilégie l'heure physique disponible pour départager les
mesures, pas l'ordre de réception des fichiers.

**`article` / `article_source`** — le code retenu **et** le code d'origine. La provenance aide
à contrôler ou corriger un rapprochement. Une reprise reste soumise à la procédure applicable ;
conserver un code source ne garantit pas à lui seul une annulation sans conséquence.

**`quantite` / `unite`** — quantité dans l'unité métier compatible avec l'article : kg, pièce,
sachet, filet, botte, etc. Le nombre de colis et son contenu attesté sont conservés séparément
quand la source les fournit. Une UF facturée n'est pas une conversion universelle vers cette
unité. Le contenu réellement livré peut différer du PCB habituel, sans modifier celui-ci.
Certains exports de sorties laissent `unite` à `inconnue` : le contrôle doit établir la
dimension depuis les sources. La boucle de position additionne les quantités reçues ; elle
ne vérifie ni ne convertit elle-même leurs dimensions physiques.

**Types de mouvements et de comptages reconnus :**

| Type | Effet |
|---|---|
| `livraison` | ajoute |
| `vente` | retire |
| `casse` (jetée) | retire |
| `don` (Restos du Cœur) | retire |
| `comptage` | la mesure physiquement la plus récente devient la base de l'article concerné |
| `correction-comptage` | corrige la quantité du comptage désigné par `cible_id`, en conservant son instant physique |

Les comptages courants portent `"mesure": "position"` et `origine_mesure`. Ils donnent une
nouvelle base à leur périmètre et à leur instant, sans certifier les autres articles ni
actualiser les statistiques. Les mouvements antérieurs sont déjà inclus ; ceux du même jour
dépendent de la phase du relevé ; ceux des jours suivants s'appliquent. La position est un
écart par rapport au rayon plein, pas la quantité totale présente : voir `reference/le-metier.md`.

Une correction conserve la date, l'heure et la phase de sa cible. Le lecteur doit retrouver
cette cible plus tôt dans le carnet, pour le même article ; une cible absente n'est pas une
correction appliquée. `corriger-conversion-comptage.py` est limité aux anciens IDs `:saisie`
et refuse notamment un autre comptage simultané ou postérieur. Un nouveau comptage courant
et une correction historique sont deux opérations distinctes.

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
  "auteur": "agent-donnees",
  "enregistre_le": "2026-08-30T21:14:02"
}
```

Le lecteur `moteur/regles.py` traite `fusion`, `fournisseur`, `conditionnement`, `unite`,
`masquage`, `demasquage`, `promotion` et les annulations. Cela ne signifie pas que chaque outil
permet d'écrire tous ces types : `appliquer-decision.py` expose les actions rapprocher,
conditionnement, fournisseur, masquer, démasquer et promotion, avec ses contrôles de pouvoirs.

**Trois obligations, sans exception :**

1. **une date de début explicite pour une nouvelle décision** — le lecteur filtre les
   décisions effectives à la date demandée, aujourd'hui par défaut ;
2. **une explication** ;
3. **l'autorisation applicable et sa preuve** — avant écriture, distinguer ce que le rôle
   peut faire seul et ce qui exige la validation du responsable. Le lecteur n'authentifie pas
   lui-même cette validation ; ajouter une décision effective peut agir sur le calcul.

**Les événements du terrain** (tête de gondole, fête locale) sont des éléments de contexte à
faire examiner avec leur période et leurs preuves. Ils ne constituent pas un type générique
de décision appliqué automatiquement par `regles.py`. Ne pas inventer de coefficient ni
confondre une remarque dans le fil avec une instruction d'ajustement autorisée.

**Les décisions sont stockées ; leurs effets sont rejoués.** `regles.py` reconstitue les
groupes et surcharges à partir du carnet, dans l'ordre des lignes effectives non annulées.
Les référentiels et offres restent nécessaires aux valeurs de repli. Le carnet original
n'est pas réécrit, mais une règle devenue effective peut changer le résultat d'un recalcul
de faits anciens : la date de début n'est pas une garantie universelle de calcul historique
avec les règles de chaque journée. Une annulation ajoute des événements et contrôle les
changements intermédiaires ; elle ne gomme pas la décision d'origine.

```
python moteur/regles.py 0000087010624
```

---

## L'état

`etat.json` est **recalculé** par `calculer-position.py`. Par article, il publie notamment
`position`, `mesuree_le`, `moment_mesure`, `origine_mesure` et le nombre `mouvements_depuis`.
Sans mesure exploitable, la position reste `null`. Le signal de position perdue est produit
pour la proposition et l'aide au comptage, pas comme un champ de cet état.

Au niveau global :

- `calcule_jusquau` est le maximum des dates d'effet connues, sans preuve de complétude ;
- `date_base_commande` combine les dates de ventes et les phases des faits pour préparer le cycle ;
- `date_reference` vient des agrégats de ventes ; sans aucune vente, l'agrégateur utilise le
  jour de l'ordinateur, ce qui ne prouve pas l'existence de statistiques ;
- `reconstruit_le` est un horodatage de publication, distinct de ces dates métier.

`proposition.json` précise la couverture des sorties par article. Elle avance sur les jours
consécutifs disponibles, sans combler artificiellement un trou ; la présence d'une vente
pour une journée ne prouve pas l'exhaustivité de l'export. `articles.json` peut déduire des
ventes estimées du repère de comptage, sans ajouter de faits de vente.

**Interdit :** modifier le stock sans avoir d'abord écrit le mouvement qui le justifie.

---

## Qui écrit où

| Rôle canonique | Périmètre de mission et écritures |
|---|---|
| `Leader` | coordonne, transmet les mandats et relit ; aucun droit métier acquis à la place de l'exécutant |
| `agent-courrier` | relève et prépare les preuves ; ses droits déclarés ne transforment pas une relève en autorisation d'import |
| `agent-donnees` | importe le périmètre contrôlé et autorisé, puis produit les dérivés ; décisions limitées par ses pouvoirs |
| `agent-rayon` | traite les demandes explicites du responsable avec les outils et droits applicables |
| `agent-controle` | contrôle indépendant des données métier et paramètres en lecture seule ; peut rédiger sa preuve privée |
| `agent-articles` | enquête sur les articles sans modifier les données métier |
| `agent-tendances` | analyse et propose des ajustements habilités, sans droit de transmettre une commande |
| `agent-audit-stock` | enquête sur les écarts sans créer de mouvement ni corriger les quantités |
| `responsable-rayon` | décisions humaines selon ses pouvoirs ; le serveur enregistre notamment ses mesures directes |

Les plafonds et actions viennent de `pouvoirs.json`. `appliquer-decision.py` et `annuler.py`
contrôlent le rôle déclaré, les actions permises et les plafonds via `journal_agents.py` ;
`ajuster-commande.py` contrôle les droits et limites propres aux ajustements. Pour les ajustements
de commande du responsable et la capture de référence des propositions, `moteur/enregistrer_modifications_commande.py`
(via `POST /api/ajustements-commande` ou `ajuster-commande.py`) archive immuablement la proposition de base
(`donnees/propositions/`) et alimente simultanément `ajustements.jsonl` et le carnet d'entraînement IA
`entrainement-ajustements.jsonl`. Ces plafonds d'actions ne sont pas un quota de lignes de ventes dans un import.

Il n'existe pas de contrôle universel des pouvoirs autour de toute écriture de fichier : les
importeurs restent soumis aux mandats et à `procedures/controle-stock.md`. Les outils ne
vérifient pas l'identité d'une personne derrière le rôle déclaré, et les routes humaines ne
doivent pas servir aux agents pour contourner leurs droits. Un avis de contrôle sûr ne donne
aucune autorisation supplémentaire ; chaque exécutant signe sa propre action.

---

## Les cinq propriétés à contrôler

Ce sont des contrôles à démontrer sur le périmètre traité, pas des garanties déduites du seul
nom d'un script ou de son code retour.

1. **Reconstruction reproductible** — en copie, avec les mêmes faits, règles, référentiels,
   date et code, expliquer les positions obtenues.
2. **Pas de double mouvement** — rejouer une source déjà intégrée ne doit pas ajouter sa
   quantité une seconde fois ; les journaux et comptes rendus peuvent néanmoins être renouvelés.
3. **Chaque chiffre s'explique** — on remonte aux mouvements qui composent une position.
4. **Rien sans explication.**
5. **Correction contrôlée** — vérifier les événements intervenus depuis, utiliser une
   annulation ou correction prise en charge, puis relire son résultat. Une panne partielle
   ne supprime pas automatiquement les fichiers ou faits déjà écrits.

---

## Ce que les carnets ne contiennent pas

- **La proposition de commande active** — un calcul refait à neuf à chaque fois
  (`proposition.json`, écrasé). En revanche, la proposition algorithmique initiale de chaque jour
  est archivée de façon immuable dans `donnees/propositions/proposition-AAAA-MM-JJ.json`.
  Ce qu'un rôle ou le responsable en *dit* est un événement tracé dans `ajustements.jsonl`
  et enrichi dans `entrainement-ajustements.jsonl`.
- **Les cadenciers** — des catalogues, pas des mouvements.
- **La météo et les jours fériés** — des ingrédients du calcul.

---

## Où aller vérifier

| Pour vérifier | Commande |
|---|---|
| un chiffre sur un article | `python moteur/agregats.py <code>` |
| le nom, le prix, le conditionnement | `python moteur/catalogue.py <code>` |
| pourquoi ce réglage | `python moteur/regles.py <code>` |
| les actions journalisées d'un rôle | `python moteur/annuler.py --liste <role-canonique>` ; la liste n'est pas un relevé exhaustif de toute activité |
| le profil de saisonnalité d'un article | fiche de `app/commander.html` et profils de `agregats.json`, calculés par `moteur/calculer-commande.py` |
| l'analyse historique détaillée | `app/analyse-historique.html`, alimenté par `donnees/analyse-ventes-annuelle-saisonniere.json` |

`python moteur/analyser-historique-complet.py` **réécrit** l'analyse dérivée. Même une commande
de consultation d'`agregats.py` peut créer `agregats.json` s'il manque. Pour un audit strict
sans écriture, lire les fichiers existants ou travailler en copie isolée.

Un chiffre juste au moment où il a été calculé peut être faux au moment où on le répète : entre
les deux, un comptage est arrivé, ou une décision a été appliquée.
