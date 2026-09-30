# Correspondance de la vidéo avec les consignes

Revue du 16 septembre 2026 : 15 scènes comparées à 13 fichiers `.md` actuels.
Le rôle de contrôle a effectué une lecture indépendante du scénario initial puis des
corrections. Avis final : favorable pour le fonctionnement prescrit et le périmètre pédagogique.

Cette comparaison ne certifie ni la présence d'un superviseur actif ni le respect des
consignes par une exécution réelle. Aucun service ou traitement métier n'a été lancé pour la revue.

## Résultat par scène

Les chemins ci-dessous partent de la racine du projet. Leurs empreintes exactes sont dans
`verification-consignes.json` ; elles permettent de détecter une nouvelle modification.

| Scène | Résultat de la comparaison | Source principale |
|---|---|---|
| 1 · Rôles | Conforme : huit rôles activés selon le besoin, pas huit services permanents. | `AGENTS.md`, `agents/agent-orchestrateur.md` |
| 2 · Réveil | Précisé : logiciel de supervision à configurer ; comptages corrigés et événements anciens en attente inclus. Le détecteur seul ne démarre aucun agent. | `AGENTS.md`, `agents/agent-orchestrateur.md` |
| 3 · Lecture | Précisé : mandat avec documents exacts, action permise, limites et résultat attendu ; chaque pièce est examinée. | `AGENTS.md`, `agents/agent-courrier.md` |
| 4 · Preuves et dates | Précisé : veille/jour est la convention du lot habituel ; les dates attestées priment. Classer un mail ne prouve pas son traitement. | `AGENTS.md`, `procedures/courrier.md` |
| 5 · Simulation | Conforme : calcul des effets attendus sans écriture de stock réel. | `agents/agent-donnees.md`, `procedures/controle-stock.md` |
| 6 · Contrôle avant | Conforme : intervention distincte, lecture des originaux et de la simulation, aucune correction métier par le contrôleur. | `agents/agent-controle.md`, `procedures/controle-stock.md` |
| 7 · Autorisation | Conforme : l'avis ne crée pas l'autorisation ; délégation habituelle et accord ligne par ligne pour le stock des factures directes sont distincts. | `AGENTS.md`, `procedures/courrier.md` |
| 8 · Import | Précisé : des sources ou comptages modifiés imposent une nouvelle simulation et un contrôle du périmètre changé. | `agents/agent-donnees.md`, `procedures/controle-stock.md` |
| 9 · Contrôle après | Conforme : retour du contrôle des résultats réels avant l'annonce de réussite ; échecs et intégrations partielles signalés. | `agents/agent-controle.md`, `procedures/controle-stock.md` |
| 10 · Message rayon | Précisé : contrôle indépendant avant/après les changements sensibles ; relecture du résultat et de la réponse publiée. | `agents/agent-rayon.md`, `procedures/message-rayon.md` |
| 11 · Comptage | Précisé : recalcul lancé par le serveur, réussite à vérifier ; analyse du relevé ou de sa correction exacts, distinction preuve/hypothèse. | `agents/agent-audit-stock.md`, `procedures/comptage.md` |
| 12 · Articles | Conforme : enquête et preuves transmises au Leader, aucune correspondance inventée. | `agents/agent-articles.md` |
| 13 · Tendances | Conforme : suggestion argumentée et prudente ; aucune commande envoyée. | `agents/agent-tendances.md` |
| 14 · Décision humaine | Conforme : proposition de l'application, décision du responsable et envoi dans l'outil habituel. | `AGENTS.md`, `agents/agent-orchestrateur.md` |
| 15 · Reprise | Précisé : clôture du seul événement terminé avec preuve ; les autres restent ouverts ; enquêtes parallèles possibles, écritures d'un lot ordonnées. | `AGENTS.md`, `agents/agent-orchestrateur.md`, `procedures/message-rayon.md` |

## Narration

La voix Windows Hortense a été remplacée par la voix neuronale française Vivienne.
Les sous-titres utilisent maintenant les repères de phrases du moteur vocal. La vidéo
reste un résumé des interactions : elle ne remplace pas les procédures détaillées.
