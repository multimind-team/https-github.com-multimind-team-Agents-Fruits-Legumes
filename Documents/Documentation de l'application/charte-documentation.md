# Charte et entretien de la documentation

Ce fichier conserve les repères de présentation du portail documentaire. Les règles d’action des agents viennent uniquement de `AGENTS.md` ; ce document ne crée aucun rôle, pouvoir, validation obligatoire ou étape d’envoi.

## Sources et contenu

- Vérifier les affirmations contre le code et les procédures actuels.
- Distinguer fonctions présentes, limites et exemples fictifs.
- Ne pas publier de taux de performance ou de garantie commerciale sans preuve mesurée.
- Conserver les 23 chapitres et 48 fiches reliés depuis `index.html` ; actualiser ensemble le contenu et le sommaire.
- Les références de code restent locales au dépôt ; le serveur métier ne publie pas ce dossier.
- Les détails métier et autorisations restent décrits dans `reference/`, `procedures/` et `AGENTS.md`.

## Présentation

- Nom du portail : « Agents Fruits & Légumes ».
- Logo : `assets/logo.webp`, avec repli `assets/logo.gif`. Le master vidéo conservé est `assets/logo.mp4` dans ce même dossier.
- Feuille de style : `assets/style.css`, commune aux fiches.
- Préserver navigation, recherche du sommaire et impression navigateur.
- Utiliser les liens relatifs vers les fichiers existants et vérifier aussi les ancres.
- Le logo, les couleurs et les titres identifient le projet local ; ils ne prouvent pas une certification ou une performance officielle du groupement.

## Vérifications avant livraison

Relire les modifications, vérifier les chemins et le JavaScript, puis contrôler le rendu sur ordinateur et téléphone. Les tests de l’application s’exécutent en copie isolée selon `tests/lancer_tests_isoles.py`. Une mise à jour documentaire ne déclenche ni sauvegarde GitHub ni envoi de commande.
