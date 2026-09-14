# Procedure commande

## Quand l'utiliser

Utilise-la chaque matin avant la preparation de commande, ou apres integration de nouveaux
fichiers.

Propriétaire : `agent-donnees` pour le recalcul ; l'agent orchestrateur pour la relecture et la restitution ;
le responsable conserve la décision finale. Entrées : proposition, état, fraîcheur, cadencier et
résultats d'import. Sortie : dates vérifiées, limites et anomalies utiles avant 9h30.

## Etapes

1. Verifie la fraicheur de la proposition :

```bat
py -3.14 moteur/filet-de-securite.py --verifier
```

2. Si les données sont en retard, distingue position physique, couverture par article et
   statistiques de ventes. Cherche les mails/fichiers réellement disponibles, sans attribuer
   au stock recompté l'ancienne date des ventes. Casse et dons ne sont pas requis sans activité.
3. Si les donnees sont disponibles, recalcule :

```bat
py -3.14 moteur/filet-de-securite.py --forcer
```

4. Ouvre `donnees/proposition.json` et controle :
   - la date de commande ;
   - la date de livraison ;
   - le nombre d'articles ;
   - le total de colis ;
   - les lignes bloquees ou masquees.
   - fruits non bio, légumes non bio, bio, puis l'ordre Webtelevente dans chaque groupe, sans nouveau sous-groupe ;
   - la fraîcheur par article et les alertes ; une position perdue commence à -10 colis inclus.
5. Lis aussi `donnees/fraicheur.json`, y compris les calculs en échec. Un code 0 ou la bonne date
   ne prouve pas à lui seul que toutes les étapes ont réussi.
6. Signale au responsable ce qui peut changer sa décision ; publie les anomalies dans le chat.

Consulter aussi les avis et anomalies du circuit `procedures/controle-stock.md`. Une fraîcheur
« à jour » ou un bandeau absent ne prouve ni que toutes les livraisons ont été intégrées, ni que
leurs colisages sont justes. Un lot de mouvements non contrôlé indépendamment reste non certifié ;
conserver visibles les limites utiles sans invalider un nouveau comptage physique confirmé.

`--verifier` est consultatif ; `--forcer` régénère des sorties et écrit des journaux. Ne pas lancer
un recalcul destructif pour un simple audit de lecture. En cas d'échec, vérifier qu'une proposition
précédente est réellement lisible avant d'affirmer qu'elle est conservée.

## Regle centrale

La proposition aide le responsable de rayon. Elle ne remplace pas sa decision.

Sous 9h30, une proposition ancienne mais signalee vaut mieux qu'un ecran vide.
Si aucune proposition valide ne reste disponible, dire clairement de reprendre la préparation
manuelle avec Webtelevente ; ne pas fabriquer de données de remplacement et ne pas envoyer de
commande fournisseur pour tester l'application.
