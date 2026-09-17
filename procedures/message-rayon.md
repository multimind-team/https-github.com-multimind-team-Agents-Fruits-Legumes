# Procedure message du rayon

## Quand l'utiliser

Utilise-la quand le responsable de rayon ecrit depuis l'application ou directement au Leader.

le Leader reçoit le message entier et son identifiant ; `agent-rayon` possède l'interprétation et
l'exécution de la demande explicite. La sortie est une décision vérifiée ou une question unique,
publiée dans le même fil. Un agent de contrôle peut donner un avis, pas exécuter la décision.

## Etapes

1. Lis le message entier.
2. Verifie s'il demande :
   - une correction de position ;
   - un changement de fournisseur ;
   - masquer ou demasquer un article ;
   - signaler une promotion ;
   - expliquer une quantite ;
   - noter un evenement terrain.
3. Pour un réglage article explicite, utiliser `py -3.14 moteur/appliquer-decision.py` sous
   l'auteur réel `agent-rayon`, avec un motif d'au moins 30 caractères ; simuler avant l'écriture.
   La fiche `agents/agent-rayon.md` donne les actions et la syntaxe. Une position se corrige par
   `procedures/comptage.md`, pas par un réglage article. Ne jamais ajouter une décision à la main
   ni changer d'auteur pour passer un refus. Les permissions restent obligatoires même si un CLI
   ancien ne les vérifie pas partout.
   Pour tout changement affectant mouvements, comptages, unités, mappings ou colisages,
   faire intervenir un agent contrôle distinct selon `procedures/controle-stock.md` avant/après
   l'écriture de l'agent autorisé. Une simple illustration n'autorise aucun mouvement réel.
4. Si le message est ambigu, pose une seule question simple.
5. Recalcule si la decision change la proposition.
6. Reponds en francais simple avec ce qui a ete fait. Pour le fil applicatif :
   `py -3.14 moteur/dire.py --auteur "Agent rayon" --en-reponse-a "<id-message>" "<reponse-verifiee>"`.
   Relire la réponse cible et fournir son ID au Leader. Une réponse seulement visible au terminal
   n'est pas une réponse reçue sur le téléphone.
7. Si la demande provient de la sentinelle, acquitter son événement seulement après
   vérification du traitement et de la réponse publiée :
   `py -3.14 moteur/surveille-mail-message-comptage.py --acquitter MESSAGE "<id-message>" --preuve "<id-reponse-verifiee>"`.
   Une question de clarification ou un traitement encore en échec laisse l'événement en attente.

Avant une annulation, lire l'action originale et les changements postérieurs. Ne jamais annuler
une décision devenue conflictuelle ou un type non pris en charge seulement parce que le CLI dit
« annulable ». Si une exécution ou la publication chat échoue, le signaler dans le canal courant.

## Interdits

- Ne pas transformer une remarque vague en decision.
- Ne pas masquer un article sans demande claire.
- Ne pas inventer l'effet d'une tete de gondole, d'une fete locale ou d'une meteo.
