# Audit de l'interface — agent-controle — 19 septembre 2026

Demande source : « analyses en profondeur ce projet et dit moi si il y a des erreurs, qu'est ce qui pourrait entrainer des erreurs? »

Mandat du Leader : audit indépendant des interfaces de comptage et commande, lecture seule des données métier, reproductions en copie isolée. Aucun import, recalcul, POST au serveur de production, modification de permission ou publication dans le chat.

Documentation consultée : AGENTS.md intégral ; agents/agent-controle.md ; donnees/pouvoirs.json ; documentation officielle index et fiches 18.1, 18.2, 17.1, 17.2, 13.1, 13.2, 14.1, 14.2.

## Verdict

**BLOQUÉ pour un avis global de fiabilité de ces parcours** : trois défauts fonctionnels reproduits. Ce constat ne prouve pas qu'ils ont déjà faussé les données de production ou qu'une commande réelle a été erronée.

Les reproductions chargent des copies des pages dans un navigateur sans interface, dont toutes les requêtes HTTP sont interceptées. Les articles sont fictifs. Le cas de date utilise la véritable fonction `normaliser_comptage`, extraite de la copie du serveur par AST ; aucun serveur réel n'est lancé. Les premières exécutions ont terminé sans erreur JavaScript.

## 1. P1 — Un comptage corrigé dans Commander reste ancien dans Compter

- Références : `app/commander.html:930-979`, `app/compter.html:291-306`, `app/compter.html:341-347`, `app/compter.html:432-444`, `moteur/serveur.py:851-860`.
- Reproduction : compter et envoyer 2 colis ; corriger ensuite la position à 7 colis depuis Commander, recevoir l'accusé et la proposition recalculée ; revenir dans Compter.
- Résultat : le téléphone affiche encore 2 colis, avec l'indication « COMPTÉ À… », même si le nouveau fichier des articles contient 7. Valider recrée un relevé de 2 colis avec une heure plus récente. La règle serveur accepte ce nouvel instant et peut donc remplacer la base de 7 colis.
- Preuve observée : correction acceptée 7 colis à 15:58:33 ; retour affiché 2 ; nouveau relevé en attente 2 colis à 15:58:35 ; aucune erreur JavaScript.
- Cause : l'édition depuis Commander ne met pas à jour la mémoire `rayon-fl.comptages-du-jour`, alors que Compter privilégie toujours cette mémoire sur le fichier frais. La nouvelle validation n'est pas distinguée d'un nouveau comptage physique.
- Correction attendue : synchroniser les deux parcours sur les relevés acquittés, comparer les instants des mesures et traiter explicitement les conflits avec les relevés encore en attente. Ajouter le test de transition entre les deux écrans.

## 2. P1 — Un reliquat de la veille bloque tous les comptages du jour

- Références : `moteur/serveur.py:317-318`, `moteur/serveur.py:800-804`, `app/compter.html:432`, `app/compter.html:573-606`.
- Reproduction : conserver dans la file un relevé du 18 septembre après une coupure réseau ; ajouter un relevé du 19 septembre ; envoyer le 19 septembre.
- Résultat : le validateur refuse « La date de comptage doit être celle du jour. » avant toute intégration du lot. Les deux relevés restent dans la file et les tentatives suivantes échouent de la même manière. La page demande seulement de réessayer devant la porte, sans afficher le motif précis du serveur.
- Preuve observée : deux tentatives, deux refus identiques, file de deux relevés inchangée, aucune erreur JavaScript.
- Cause : la file durable conserve plusieurs jours, l'envoi ne les sépare pas et le serveur ne reçoit que les dates du jour. Aucun parcours UI de résolution du relevé ancien n'est proposé. Le chargement ne purge pas la file : le filtre de `comptagesDuJour` concerne seulement l'affichage, et `valider` ne remplace que le même article à la date actuelle.
- Correction attendue : préserver et isoler explicitement les relevés anciens, permettre l'envoi du périmètre recevable et afficher la date/motif de blocage ; définir une reprise contrôlée des relevés anciens. Ne pas redater silencieusement les anciennes mesures.

## 3. P2 — Une réponse retardée peut annuler visuellement une correction plus récente

- Références : `app/commander.html:958-979`. Le parcours colisage dispose d'une protection de séquence (`1079-1082`), absente du parcours stock.
- Reproduction : corriger le stock de A à 7, retenir sa première relecture HTTP ; fermer sa fiche ; corriger B à 9 ; laisser la proposition contenant A=7/B=9 arriver ; laisser ensuite arriver la première réponse contenant A=7/B=2.
- Résultat : B repasse de 9 à 2 à l'écran, car le seul critère d'acceptation est une date `genere_le` différente de celle précédant l'envoi. Il n'existe ni ordre de réponse commun ni vérification que le relevé demandé est dans le calcul. Les données serveur ne sont pas changées par cette régression visuelle.
- Preuve observée : B=9 après deuxième correction, puis B=2 après réponse A retardée ; deux POST interceptés ; aucune erreur JavaScript.
- Impact : la proposition dépassée peut être recopiée ou servir à une nouvelle saisie. Le contrôle périodique du recalcul peut signaler une version différente ultérieurement ; il ne protège pas l'affectation immédiate ni ne recharge automatiquement les données.
- Correction attendue : rattacher les relectures aux versions/opérations et aux mesures attendues, rejeter une réponse plus ancienne que la proposition active, protéger tous les chemins modifiant `proposition`.

## Défaut supplémentaire dormant, P2

`app/commander.html:561-566` et `885-887` : avec proposition initiale 3 colis et ajustement agent **appliqué** à 2, le clic `+` calcule 3 puis supprime l'ajustement humain puisque 3 égale la proposition initiale. `quantite` réapplique aussitôt 2 : le bouton ne permet pas de revenir à 3. Reproduit dans le navigateur (avant 2, après clic 2, mémoire vide). Ce cas nécessite `applique:true` ; les trois lignes du carnet d'ajustements consulté sont `applique:false`, donc aucun incident actuel n'est établi. Correction : conserver la décision humaine lorsqu'elle diffère de la valeur effectivement utilisée sans ajustement local.

## Couverture et limites

Les tests existants examinent le stockage plein, les fractions, l'identité/colisage pendant les rechargements, la conservation des relevés créés pendant un envoi, les conflits API au même instant et les renvois anciens dans une même journée. Aucun test trouvé pour les trois transitions ci-dessus. Le Leader exécute séparément la suite complète ; elle n'a pas été dupliquée par cet agent.

Pas de service worker trouvé : le cache local conserve les articles et les relevés, pas un parcours complet de réouverture hors connexion garanti. Le comportement d'un téléphone réel fermé/réouvert dans la chambre froide reste à éprouver ; ce point est un risque d'exploitation, pas un défaut confirmé par cet audit.

Écritures réelles : uniquement ce rapport privé et le script de reproduction voisin, ainsi que des copies temporaires supprimées à la fin des reproductions. Aucune donnée métier ou configuration de production modifiée. Aucune correction du code faite.

Script reproductible : `repro-ui-20260919-agent-controle.py` dans le même dossier. Exécution : `py -3.14 -B documents-partages/controles-stock/repro-ui-20260919-agent-controle.py`.

Le script archivé a été exécuté à nouveau avec succès (code 0) vers 16:03 le 19 septembre : les quatre scénarios ont produit les mêmes défauts et aucune erreur JavaScript. Pour le premier, la correction de 7 à 16:03:27 a été suivie d'un ancien 2 recréé à 16:03:29.

Empreintes SHA256 des sources au terme du contrôle :

- `app/compter.html` : `85B627C29DB8A376289A00CFAA007E81E61AAB20A9DA83F4C0FE9D5C8F55B3B5`
- `app/commander.html` : `F84944D59FFD53E9E71345B84E7495273B537598A44B559398FD3235F7AD91AE`
- `moteur/serveur.py` : `C5E23554C5EB055CF70CD3B89A145F53A991682D3CD13665400A816FC5F8D399`
