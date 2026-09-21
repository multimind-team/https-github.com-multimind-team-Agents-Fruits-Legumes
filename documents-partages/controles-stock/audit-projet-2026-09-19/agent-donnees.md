# Rapport privé d’audit — agent-donnees

Date : 19 septembre 2026.
Demande source : « analyses en profondeur ce projet et dit moi si il y a des erreurs, qu’est ce qui pourrait entrainer des erreurs? »
Rôle réel : agent-donnees. Mandat : audit technique, sans intégration, correction, envoi ou publication métier.
Périmètre : moteur/integrer-fichiers.py, traiter-courrier.py, courrier_pipeline.py, courrier_fichiers.py, facture_directe.py, importer-facture-directe.py, importer-catalogue-mercalys.py et dépendances nécessaires.

## Conditions et limites

Les consignes AGENTS.md, agents/agent-donnees.md, donnees/pouvoirs.json, la documentation officielle de l’application (index et chapitres pertinents), procedures/controle-stock.md et le mode d’emploi Pomona ont été consultés. Le skill Spreadsheets et ses consignes de lecture seule ont été consultés pour la vérification des classeurs. Les modifications préexistantes du projet ont été constatées et préservées.

Aucun fichier de production n’a été modifié pendant l’investigation. Les reproductions utilisent une copie du moteur et des fixtures sous :
`C:\Users\user\AppData\Local\Temp\preparation-audit-imports-yevnxoee`

Ce dossier temporaire contient les fichiers d’essai et sorties, mais pas un programme autonome réunissant tous les scénarios. Les commandes et sorties détaillées sont conservées dans la conversation d’audit. Aucun nouvel essai n’a été réalisé lors de la rédaction de ce rapport.

La suite générale et les essais navigateur ont été exécutés séparément par le Leader. Ce rapport ne prétend pas les avoir exécutés. L’audit par lecture et les scénarios ciblés ne prouvent pas l’absence d’autres défauts. Les gravités ci-dessous qualifient les défauts reproduits, pas la preuve d’un incident déjà survenu en production.

## 1. P1 — Course lors de la création du classeur : perte d’une facture

Références : `moteur/facture_directe.py:154-163`, `moteur/importer-facture-directe.py:38-40`, `moteur/facture_directe.py:447-448`.

Le choix du classeur teste son absence puis copie le modèle avec shutil.copy2 avant la prise du verrou d’import. Deux opérations concurrentes peuvent donc toutes deux décider de créer le même fichier.

Scénario réellement exécuté :
1. Copie du modèle installé, contenant seulement l’onglet « Date du jour », dans une racine isolée. Le classeur générique de travail est absent.
2. Deux threads utilisent les véritables fonctions choisir_classeur puis importer_facture, en mode classeur_seul, avec deux factures synthétiques A et B de la même date.
3. A passe le contrôle d’absence et attend avant copy2. B copie le modèle et importe sa facture. Après la réussite de B, A reprend et recopie le modèle, écrasant le classeur rempli par B, puis importe A.
4. Les deux bilans annoncent chacun une nouvelle ligne de marge et aucune livraison. Le fichier final contient seulement « Produit A », quantité 12. « Produit B », quantité 24, a disparu.

La synchronisation de copy2 est instrumentée par unittest.mock pour reproduire un entrelacement possible. Les fonctions d’import et de publication sont les fonctions réelles de la copie du projet.

Fixture : `C:\Users\user\AppData\Local\Temp\preparation-audit-imports-yevnxoee\race`.

Correction conseillée : placer choix, création et import sous le même verrou ; utiliser une création exclusive/atomique qui ne remplace pas une destination apparue entre-temps.

## 2. P1 — Des codes Excel numériques sont ignorés sans alerte

Références : `moteur/integrer-fichiers.py:307-309` et `moteur/integrer-fichiers.py:398-406`.

L’importeur convertit le code en texte puis ignore silencieusement les valeurs qui ne correspondent pas à 8–13 chiffres. Un entier court perd les zéros initiaux ; un code numérique lu sous forme de flottant peut se terminer par .0 et être rejeté. Le lecteur XLS utilise xlrd, qui peut fournir des cellules numériques sous forme flottante. L’importeur de catalogue possède une normalisation différente dans `moteur/importer-catalogue-mercalys.py:31`.

Reproductions réellement exécutées, avec lecteur remplacé par une fixture de tableau :
- Code texte « 0000000000049 » : 1 fait, aucune alerte.
- Code numérique 49 : 0 fait, aucune alerte.
- Code numérique 87010624.0 : 0 fait, aucune alerte.
- Code texte « 87010624.0 » : 0 fait, aucune alerte.

Un appel à la véritable fonction CLI main(), en --simuler --json, a aussi été réalisé avec le lecteur, le catalogue et les règles remplacés par des fixtures. Résultat : code retour 0, statut « simulation », mouvements 0, mouvements_nouveaux 0, jours_couverts vide, a_verifier vide.

Limite explicite : le scénario CLI est partiellement mocké ; il ne constitue pas un essai end-to-end d’un XLS généré. Les exports réels de ventes, livraison et casse du 19 septembre ont été lus séparément : leurs codes sont actuellement des chaînes de caractères. Aucune perte de leurs lignes due à ce défaut n’a été constatée.

Impact possible : un changement de type de cellule dans un export peut faire omettre des mouvements et laisser un statut sans anomalie.

Correction conseillée : normalisation stricte et commune des identifiants, préservation de leur largeur canonique, et alerte explicite pour toute ligne produit rejetée. Ne pas confondre une ligne mal lue avec un total.

## 3. P2 — Le mode simulation crée réellement un classeur

Références : `moteur/facture_directe.py:154-163` et `moteur/importer-facture-directe.py:38-40`.

choisir_classeur copie le modèle avant que le CLI transmette le booléen simuler à importer_facture.

Scénario réellement exécuté : vrai CLI copié, mappings et facture synthétiques valides, copie du modèle installé, cible générique inexistante. Appel : --marge <racine-isolee>/documents-partages/calcul-marge-pomona/Calcul marge Pomona.xlsx --classeur-seul --simuler.

Résultat : code retour 0 et simulation:true ; comparaison des fichiers avant/après révélant la création de `documents-partages/calcul-marge-pomona/Calcul marge Pomona.xlsx`. Aucune écriture de stock.

Correction conseillée : rendre la sélection pure ; en simulation, lire le modèle et préparer en mémoire. Créer le fichier seulement lors de l’exécution réelle, sous verrou.

## 4. P2 — Le modèle installé ne permet pas deux dates successives dans le même fichier

Références : `moteur/facture_directe.py:223-236`.

État inspecté en lecture seule : `documents-partages/calcul-marge-pomona/0926 Calcul marge Pomona.xlsx` et `Calcul marge Pomona - Original.xlsx` contiennent chacun seulement « Date du jour », avec 51 lignes et 18 colonnes, sans produit renseigné en A à partir de la ligne 4. La sauvegarde mensuelle contient Vierge et les jours historiques. Le caractère vide du modèle peut être volontaire : il ne constitue pas à lui seul un défaut.

Scénario réellement exécuté avec une copie du modèle exact :
- Facture synthétique du 20/09/2026 : import classeur_seul réussi ; l’onglet est renommé « 20-09-2026 ».
- Facture synthétique du 21/09/2026 dans le même fichier : refus « La feuille 'Date du jour' ou 'Vierge' est absente du classeur de marge ».

Le code consomme le seul onglet modèle au premier import, puis ne dispose plus d’un modèle pour une autre date.

Limite et contexte : le mode d’emploi modifié prévoit une suppression du fichier temporaire après envoi SMTP. Le blocage concerne donc notamment un classeur conservé pour téléchargement sans courriel, un envoi qui échoue, ou l’utilisation du classeur mensuel explicite. Le circuit canonique permet la préparation et le téléchargement sans envoi de courriel.

Correction conseillée : conserver un modèle permanent dans la copie de travail ou copier une feuille depuis l’original pour chaque nouvelle date, en préservant les feuilles remplies et les saisies manuelles.

## Limite supplémentaire — disparition complète d’un article dans un renvoi

Référence : `moteur/integrer-fichiers.py:528-532`.

Le contrôle de multiplicité compare uniquement les clés rencontrées dans le nouvel import. Scénario réellement exécuté sur carnet isolé : premier export A=12 et B=15, puis renvoi ne contenant plus que A=12. Le premier import ajoute 2 faits. Le renvoi est accepté avec 0 nouveau et 1 doublon, et les 2 faits initiaux restent au carnet.

Le moteur détecte les différences de quantité ou de nombre de lignes d’un article encore présent, mais pas la disparition complète de B. Un export partiel peut être légitime ; cette observation n’établit donc pas à elle seule une erreur de stock. Pour un renvoi annoncé comme remplaçant intégralement l’export précédent, il faut comparer les périmètres des deux sources et demander une correction explicite si un article disparaît. Aucun mouvement ne doit être effacé automatiquement.

## Protections constatées par lecture

- Les factures contrôlent les montants au centime et l’unité physique compatible avant toute nouvelle écriture de stock.
- Les faits et les lignes de marge possèdent des traces permettant des reprises contrôlées.
- L’import Mercalys refuse ses erreurs avant publication du catalogue.
- Le pipeline courrier ne traite pas l’existence d’une archive comme une preuve suffisante d’intégration réussie.

Ces protections ne suppriment pas les défauts reproduits ci-dessus.

## Écritures réellement faites et fin

Pendant l’investigation : seulement copies de code, fixtures et sorties sous la racine temporaire indiquée. Aucun stock, carnet, fichier de configuration, classeur de production ou message de l’application modifié. Aucun accès aux serveurs mail ni envoi effectué.

Pour la livraison durable : création de ce rapport privé, autorisée explicitement par le Leader. Aucun fichier préexistant écrasé. Aucune correction appliquée. Les corrections et leur vérification restent à réaliser dans une mission distincte.
