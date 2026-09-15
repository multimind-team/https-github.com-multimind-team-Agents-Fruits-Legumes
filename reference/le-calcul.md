# Le calcul de la commande

Référence relue sur les modules exécutés le 15 septembre 2026. Ce document décrit
les calculs ; il n'accorde aucun droit d'import, d'ajustement ou d'envoi.
Les instructions du responsable et les pouvoirs restent applicables. Si le code
s'écarte d'une règle métier, signaler l'écart avant de changer la règle.

## 1. Sources et dates distinctes

- `faits.py` relit les carnets en ajout seul, ignore les doublons exacts et refuse
  les identifiants contradictoires.
- `date_source` garde la date portée par l'export. `date_effet` indique le jour où
  le mouvement agit sur la position. Pour les livraisons, la date d'effet de
  réception prévaut pour le stock et pour l'analyse de l'écoulement.
- Dans le lot du matin de J, ventes/casse/dons portent sur J−1 et les livraisons
  portent sur J. Ce décalage est normal. Un import tardif garde sa date d'effet.
- `agregats.json.date_reference` date les statistiques de vente. Un nouveau
  comptage n'actualise pas ces statistiques.
- Le référentiel Mercalys se fusionne avec `importer-catalogue-mercalys.py` après
  simulation et contrôle indépendant. Les articles absents restent au catalogue,
  pour préserver l'historique. Le cadencier Webtelevente donne les offres réellement
  commandables et leur ordre ; ce sont deux sources distinctes.

### Codes regroupés et offres commandables

Les fusions déjà validées rassemblent ventes et position sous un code principal.
Une ligne Webtelevente portant un code secondaire conserve son identifiant, son
libellé et son ordre, mais lit les données du principal (`article_stock`). Son
PCB et son prix restent ceux de son offre, avec priorité aux décisions effectives
sur son propre code. Le PCB, l'unité, le fournisseur et le masquage du principal
ne sont pas copiés sur un autre code commandable. La promotion déjà précommandée
du groupe reste applicable aux codes associés.

Le besoin automatique est proposé **une seule fois** : sur la ligne principale
active si elle figure au cadencier, sinon sur l'unique code associé actif. Si
plusieurs codes associés restent actifs sans ligne principale active, aucune
répartition commerciale n'est déduite de leur ordre : le groupe reçoit zéro
automatique et `commande_groupe_ambigue=true`, avec un motif demandant un choix.
Les positions et statistiques restent visibles. `commande_groupe_portee_par`
identifie la ligne choisie, et `motif_commande_groupe` explique le report ou le
choix manquant. Les quantités manuelles restent attachées à leurs codes d'origine ;
leur total de groupe doit être vérifié après un changement manuel.

## 2. Position physique

`calculer-position.py` part du dernier comptage de chaque article, puis applique
les livraisons en plus et les ventes/casse/dons en moins, selon la phase du relevé.
Aucun comptage antérieur signifie une position **inconnue**, jamais un stock nul.

| Phase du comptage | Mouvements de la même journée à appliquer ensuite |
|---|---|
| Soir | Aucun : ils sont déjà contenus dans la mesure. |
| Matin avant réception du mail de livraison | Livraison, ventes, casse et dons. |
| Matin après réception du mail | Ventes, casse et dons ; livraison déjà comprise. |

Les mouvements des jours suivants s'appliquent. L'heure physique `source.saisi_le`
prime sur l'heure d'envoi différé. La qualification utilise l'heure de réception
conservée dans `receptions-courrier.json`, ou le repli technique 06h30 en son absence.
La phase « soir » commence exactement à **17h00**, conformément à la consigne.
Une saisie antérieure, même à 16h59, ne prouve pas une clôture de journée.

Une `correction-comptage` vise `cible_id` et remplace la valeur de cette mesure sans
effacer le fait, ni déplacer la date/l'heure du relevé. Les regroupements validés
sont appliqués. Le cas particulier des oranges à jus convertit les ventes de jus
1 L en 2 kg d'oranges et de 50 cl en 1 kg, selon les codes explicites du moteur.

L'audit `analyser-ecarts-comptage.py` utilise ce même calcul pur, borné au moment du
relevé audité. Les ventes ultérieures à un relevé matinal ne sont pas soustraites.
Sans base antérieure exploitable, l'attendu et l'écart restent inconnus. Les
pistes de casse, de codes jumeaux ou de marchandise sur quai sont des hypothèses à
vérifier, jamais des preuves tirées de la seule égalité de deux quantités.

## 3. Moyennes et pertes

`calculer-commande.py` construit un profil de 366 jours : fenêtre circulaire de
**±21 jours**, toutes années disponibles confondues. Il divise les quantités de
vente par le nombre de journées distinctes observées pour l'article.

- Au moins **5 journées** dans la fenêtre : moyenne saisonnière, arrondie à 2 décimales.
- Moins de 5 journées : prévision **zéro** et `saisonFiable=0`. Aucun remplacement
  automatique par une moyenne annuelle.
- Un article totalement absent des ventes n'a pas de profil exploitable. Il peut
  rester affiché dans le cadencier, avec zéro proposé et le statut non connu.
- `tauxPerte = (casse + dons) / (ventes + casse + dons)` lorsque le dénominateur
  est positif. Si le total est nul, le repli technique est 5 %. En présence de
  ventes et sans casse/don enregistré, le taux calculé est zéro. Casse et dons
  restent des flux facultatifs : leur absence ne prouve pas une absence de pertes.

## 4. Besoin et arrondi

Pour chaque article disposant d'un profil et d'un référentiel :

```text
demande_commande = moyenne[jour_commande] × météo_commande × férié_commande
                  × vacances_commande × profil_semaine_commande
demande_livraison = moyenne[jour_livraison] × météo_livraison × férié_livraison
                  × vacances_livraison × profil_semaine_livraison
besoin_unites = max(0, (demande_commande + demande_livraison) / (1 − tauxPerte)
                      − position_unites)
```

La demande du jour de commande représente la consommation avant réception de la
commande préparée. Exemple sans pertes ni modulation : position 2 colis, demande
3 colis le jour de commande et 3 à la livraison → besoin `3 + 3 − 2 = 4 colis`.
Une position négative augmente le besoin, tant qu'elle n'est pas bloquée.

**Limite actuelle explicite :** si la position est inconnue, `proposer-commande.py`
utilise zéro comme base arithmétique provisoire, tout en conservant
`position_unites=null` et l'alerte de stock inconnu. Ce chiffre ne certifie pas
l'absence de marchandise ; un comptage reste nécessaire pour connaître le stock.

Le besoin est converti avec le conditionnement sélectionné :

- Dernière livraison à 7 jours ou moins de la commande : arrondi Python `round`
  au colis le plus proche. À exactement x,5, cet arrondi choisit l'entier pair
  (0,5 → 0 ; 1,5 → 2 ; 2,5 → 2).
- Jamais livré ou dernière livraison à plus de 7 jours : arrondi au colis supérieur
  si le besoin est strictement positif.
- Un blocage de position ou une promotion précommandée met la proposition à zéro.

## 5. Conditionnements et prix

`conditionnements.py` choisit en priorité une décision valide du responsable,
puis l'offre Webtelevente du jour. Des règles explicites choisissent la caissette
pour certains couples d'offres de pommes de terre et d'oranges en filet.
Sans PCB du jour, le module se replie sur Mercalys avec avertissement ; sans aucune
valeur exploitable, le repli technique à 1 reste signalé comme inconnu.

Le prix d'achat vient de l'offre sélectionnée ; à défaut, du dernier prix d'achat
observé dans les ventes, puis du référentiel. Le prix de vente vient de la dernière
vente connue, sinon du référentiel. Une décision de colisage sans offre assortie
conserve l'offre disponible et affiche une contradiction : elle ne crée pas un
nouveau prix fournisseur. L'interface doit relire ensemble prix et quantités après
recalcul. Les comptages historiques conservent leurs unités d'origine. La comparaison d’un PCB
avec l’offre tolère seulement la précision relative float32 de certains exports XLS
(`2**-23`) : 1,7000000476837158 et 1,7 sont équivalents pour l’appariement,
mais 1,71 reste différent. Aucune valeur source, quantité ou décision n’est arrondie.

## 6. Modulations et promotions

| Facteur | Calcul effectivement exécuté |
|---|---|
| Météo globale | Toute l'année : pluie ≥10 mm → ×0,901 ; température ≥25°C → ×1,076, cumulables. Prévision absente : facteur neutre, disponibilité déclarée. |
| Profil météo de l'article | S'il existe, remplace le facteur global ; ratios selon température/pluie, produit borné entre 0,4 et 2,5. Commande et livraison sont évaluées séparément. |
| Jour férié | ×0,54 pour une demi-journée confirmée ; ×1 pour journée complète ou statut non confirmé. Les fermetures confirmées sont sautées dans le cycle des dates. |
| Vacances, zone C | Noël 1,162 ; Toussaint 1,045 ; Été 1,027 ; Hiver 1,002 ; Printemps 0,984 ; Ascension 0,901. Facteurs distincts pour commande et livraison. |
| Semaine | Profil hebdomadaire du magasin normalisé par sa moyenne et corrections explicites lundi→dimanche : 0,953 ; 0,932 ; 0,931 ; 0,934 ; 0,925 ; 0,923 ; 1,047. |

Deux notions de promotion ne doivent pas être confondues :

1. La décision métier `promotion` du responsable indique une précommande et bloque
   le quotidien, sauf pour une livraison le lundi selon la règle existante.
2. Le prospectus et ses correspondances servent de repères. Une correspondance
   `a_confirmer` ne modifie aucune quantité. Une correspondance `confirme` peut
   porter le repère **FIN PROMO**, mais sans baisse automatique ni facteur 0,7/0,8.
   Une réduction passe par une suggestion contrôlée puis la validation du responsable.

## 7. Position perdue et dates de préparation

Une position à **−10 colis ou moins** est affichée comme perdue (`--`). Le calcul
la bloque à zéro proposé si le comptage est antérieur aux 7 derniers jours de la
commande. Une mesure récente bénéficie de l'exception existante de calcul ; son
âge ne modifie pas celui des statistiques de ventes.

`calculer-position.py` déduit une `date_base_commande` des faits : un événement
matinal de J donne la base J−1 ; un comptage du soir donne J. Le générateur utilise
cette base. À partir de 9h30, il peut passer au cycle suivant uniquement lorsque
l'état est daté du jour courant. Un vieux carnet n'est pas rajeuni par l'horloge.
Un ancien format d'état sans cette base se replie sur la date des statistiques.

La commande est le prochain jour valide après la base, et la livraison le prochain
jour valide après la commande. Sont sautés : dimanche, 1er janvier, 1er mai,
25 décembre et fermetures variables explicitement confirmées. Exemple : commande
samedi → livraison lundi si ce lundi est ouvert.

## 8. Suggestions de baisse et traçabilité

`analyser-ventes-livraisons.py` observe les ventes depuis chaque réception réelle
jusqu'à la veille de la suivante, au plus tard la dernière journée statistique
close et la veille de l'horloge. Une réception à venir n'est jamais comparée aux
ventes de la veille. Une journée manquante n'est pas assimilée à une vente nulle.

- Une seule réception sous le seuil d'écoulement : observation, aucune baisse.
- Au moins deux réceptions consécutives sous le seuil (50 % par défaut) : contrôle
  préalable du calendrier, météo, vacances, ponts et ouvertures effectives.
- Cause externe avérée, ou contexte incomplet : maintien, aucune baisse proposée.
- Contexte vérifié sans cause externe : suggestion avec tampon de 25 % au-dessus
  de la vitesse observée, plancher de 1 colis et plafond de baisse des pouvoirs
  (30 % actuellement), respecté **après arrondi supérieur**.
- La suggestion passe par `ajuster-commande.py --proposer --agent agent-tendances` ;
  elle n'écrit pas une commande acceptée. Le responsable peut choisir « Suivre ».

Les calculs dérivés utilisent le verrou partagé des opérations et une écriture
atomique de chaque JSON. Une interruption entre deux sorties peut encore laisser
un lot incomplet : contrôler le bilan du filet de sécurité avant d'annoncer une
application à jour. Les essais et audits techniques utilisent des copies isolées.
