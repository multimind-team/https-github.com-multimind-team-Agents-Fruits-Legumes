# Procedure comptage

## Quand l'utiliser

Utilise-la quand une position est saisie depuis l'ecran de comptage ou corrigee pendant la
commande.

Propriétaire de la mesure : responsable de rayon via l'application. Le serveur enregistre les
faits ; l'agent données vérifie le rejeu et les dérivés, l'agent orchestrateur restitue les écarts. Une demande de
correction ambiguë revient au responsable, pas à une estimation de l'agent.

## Regle metier

La position n'est pas un stock.

Le rayon est rempli d'abord. Ensuite seulement on mesure :

- reste en chambre froide : position positive ;
- chambre froide vide et rayon pas plein : position negative.

Le comptage matinal habituel se fait après rangement de la livraison et avant les ventes :
quand ces conditions sont attestées, cette livraison est déjà dans la mesure. Les sorties
postérieures seront soustraites quand elles seront connues. Une mesure réellement de fin de
journée contient les mouvements antérieurs de cette journée. Le moteur applique une convention
à la journée (soir à partir de 17h, « soir » sans heure) : elle ne prouve ni la fermeture ni le rangement.
Si la situation réelle ne correspond pas, signaler la limite plutôt que supposer une inclusion.
Voir `reference/le-metier.md` et `procedures/controle-stock.md`.

## Etapes

1. Verifie la date et l'heure du comptage.
2. Verifie l'article et son conditionnement.
3. L'application transmet une position ; vérifier le fait de type `comptage`, mesure `position`,
   et sa quantité dans l'unité de l'article. Ne pas écrire un nombre de colis dans `quantite`.
   Un nouveau relevé physique ajoute un `comptage` distinct à son propre instant, même le même
   jour ou avec la même valeur. Une correction de saisie historique ajoute `correction-comptage`
   avec le `cible_id` stable de l'original : conserver les faits et l'instant de cette ancienne
   mesure. Ne pas appeler une nouvelle mesure une correction historique. Deux valeurs différentes
   au même instant exigent une vérification, pas une correction implicite par l'API de relevés.
4. Pour un fichier reçu ou renvoyé après cette mesure, appliquer `procedures/controle-stock.md` :
   rechercher le comptage de chaque article, distinguer mouvements déjà compris et postérieurs,
   faire contrôler indépendamment le plan puis le résultat. Un comptage partiel ne valide pas
   les autres articles. La phase technique du relevé n'atteste pas une fermeture : comptage pendant
   l'ouverture, phase incertaine ou livraison après mesure le même jour doivent être signalés,
   sans répartition inventée des ventes journalières. Recalcule les positions dans le périmètre sûr.
5. Recalcule la proposition si la commande du jour peut changer.
6. Si une position atteint -10 colis ou moins, affiche `--` et signale qu'il faut recompter.
7. Vérifie le résultat relu dans l'état et la proposition ; le simple accusé de réception du
   téléphone ne prouve pas que le recalcul asynchrone est fini. L'envoi peut se faire avant la fin
   de la liste ; ne jamais obliger à parcourir les articles restants.
8. Si la sentinelle a confié un événement, faire analyser l'ID exact du relevé/correction par
   `agent-audit-stock`, vérifier le rapport et sa restitution puis acquitter avec la référence
   de preuve selon `AGENTS.md`. Le CLI d'audit sans `--id` ne couvre pas nécessairement cet événement.

## Interdits

- Ne pas convertir en stock theorique.
- Ne pas retirer deux fois les ventes du jour.
- Ne pas corriger une position sans mouvement ou comptage qui l'explique.
- Ne pas déduire qu'une livraison récente suffit à valider la couverture de tout le stock.
- Ne pas re-bloquer un article réellement recompté parce que ses statistiques de ventes sont plus
  anciennes : conserver et afficher les deux dates avec leurs limites respectives.
