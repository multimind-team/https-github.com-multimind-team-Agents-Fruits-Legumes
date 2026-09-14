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

Le comptage du matin se fait après rangement de la livraison, avant les ventes : cette livraison
est déjà dans la mesure. Les ventes, casse et dons du même jour seront soustraits quand ils seront
connus. Le soir, la mesure contient tous les mouvements de sa journée : ne rien réappliquer de
ce jour. Sans heure connue, le moteur traite le comptage comme une mesure du soir ; signaler une
heure douteuse plutôt que la deviner. Voir `reference/le-metier.md`.

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
   les autres articles. La bascule technique à 14 h n'atteste pas une fermeture : comptage pendant
   l'ouverture, phase incertaine ou livraison après mesure le même jour doivent être signalés,
   sans répartition inventée des ventes journalières. Recalcule les positions dans le périmètre sûr.
5. Recalcule la proposition si la commande du jour peut changer.
6. Si une position atteint -10 colis ou moins, affiche `--` et signale qu'il faut recompter.
7. Vérifie le résultat relu dans l'état et la proposition ; le simple accusé de réception du
   téléphone ne prouve pas que le recalcul asynchrone est fini. L'envoi peut se faire avant la fin
   de la liste ; ne jamais obliger à parcourir les articles restants.

## Interdits

- Ne pas convertir en stock theorique.
- Ne pas retirer deux fois les ventes du jour.
- Ne pas corriger une position sans mouvement ou comptage qui l'explique.
- Ne pas déduire qu'une livraison récente suffit à valider la couverture de tout le stock.
- Ne pas re-bloquer un article réellement recompté parce que ses statistiques de ventes sont plus
  anciennes : conserver et afficher les deux dates avec leurs limites respectives.
