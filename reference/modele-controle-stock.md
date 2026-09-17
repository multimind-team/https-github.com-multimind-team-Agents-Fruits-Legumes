# Modèle de rapport de contrôle de stock

Ce modèle doit être rempli avec des preuves réelles, pas copié comme certificat. Ne créer aucun
fait métier pour remplir une case. Les exemples de la procédure sont fictifs. Les rapports sont
privés, versionnés dans de nouveaux fichiers, sans secret ni modification des journaux historiques.

## Identification

- Lot local et version du rapport :
- Demande originale / référence réelle du message, sinon « non fournie » :
- Phase : avant import / après import / reprise :
- Exécutant réel, référence de délégation vérifiable et chemin du rapport source :
- Contrôleur distinct, référence de délégation vérifiable et chemin du rapport source :
- Heure de la revue et racine examinée (production en lecture seule / copie isolée) :
- Autorisation applicable, validations humaines requises et preuve exacte :
- Consignes effectivement relues :

## Inventaire exhaustif des pièces

| Chemin privé littéral et nom original | SHA-256 | Type confirmé / référence document | Pages/feuilles/lignes lues et attendues | Période interne / date d'effet / réception | Statut final de la pièce et preuve |
|---|---|---|---|---|---|

Confronter le total des pièces annoncées au total des pièces inventoriées. Pour un manque, donner
la preuve qu'une pièce était attendue. Si le nombre total de pages est inconnu, le dire.

## Rapprochement de toutes les lignes de mouvement

| Source feuille/cellule ou page/ligne | Code source brut → article exact et preuve du mapping | Quantité/unité brutes | Colis reçus / contenu livré / quantité métier / colis habituel | Date d'effet prouvée | Dernier comptage ID/date/heure/phase prouvée | Déjà compris ou mouvement à appliquer, justification | Décision de ligne, fait ID existant ou attendu |
|---|---|---|---|---|---|---|---|

Chaque ligne source est classée exactement une fois : à intégrer, déjà intégrée identique,
bloquée, ou hors mouvement avec motif (total, frais...). Rapprocher les nombres avec un outil.
Une ligne « déjà comprise dans un comptage » peut rester à intégrer dans l'historique : ne pas
confondre cet effet nul sur la position avec un doublon de fait.

Joindre les calculs des montants/totaux et quantités PAR unité, les écarts et la tolérance utilisée.
Relier les duplications BL/facture/export/manuel par leurs identités métier, pas seulement leur SHA.

## Matrice obligatoire

Pour chaque repère R01 à R24 de `procedures/controle-stock.md` :
- vérifié / anomalie / non applicable (motif obligatoire) ;
- sources effectivement ouvertes avec cellule/page/ligne ;
- conclusion et action minimale ;
- contrôle non réalisé ou limite technique, s'il y en a une.

## Avis avant écriture

- Verdict : SÛR POUR LE PÉRIMÈTRE / BLOQUÉ.
- État d'exécution distinct : NON INTÉGRÉ / INCOMPLET-ÉCRITURE À ÉTABLIR /
  PARTIELLEMENT INTÉGRÉ ET VÉRIFIÉ / INTÉGRÉ ET VÉRIFIÉ / DÉJÀ INTÉGRÉ ET VÉRIFIÉ.
- Liste exacte des fichiers/lignes couverts, aucune permission implicite :
- Commandes simulées, leur racine, leurs codes retour et refus :
- Rapprochement attendu de chaque position affectée (unités puis colis habituels) :
- Effets historiques sans effet sur la position recomptée :
- Hypothèses interdites / ambiguïtés non résolues / validation attendue :
- Empreintes/IDs des faits, comptages, mappings, règles et fichiers réellement utilisés :
- Contrôle des préconditions à refaire immédiatement avant écriture :

Si un seul périmètre dépendant est ambigu, bloquer ce périmètre complet. Une séparation de lot
n'est permise qu'avec preuve d'indépendance et commande ciblée ; une facture incomplète reste bloquée.
L'avis indépendant n'est pas une autorisation humaine de stock Pomona.

## Avis après écriture

- Commandes réellement exécutées, codes retour et étapes non faites :
- Nouveaux faits relus : liste d'IDs, articles, dates, quantités et unités :
- Faits déjà présents / refus / conflits / état partiel :
- Préfixes des journaux et originaux préservés, périmètre d'empreintes exact :
- Derniers comptages et mappings toujours identiques, sinon nouvelle analyse :
- Reproduction indépendante de chaque delta et position obtenue :
- Dérivés relus (état, proposition, fraîcheur), génération et dates distinctes :
- Résultat de rejeu idempotent et environnement où il a été testé :
- Application consultée et résultat réellement visible (ne pas confondre lecture JSON et écran) :
- Verdict final : SÛR POUR LE PÉRIMÈTRE / BLOQUÉ.
- État d'exécution : distinct de l'avis, selon la liste ci-dessus ; un contrôle manquant
  ne permet pas d'affirmer une intégration partielle. Détailler les sous-ensembles vérifiés.
- Ce qui n'a pas été vérifié :

## Anomalies et clôture

| Anomalie / constat initial | Pièces, dates et articles concernés | Effet position / statistiques | Propriétaire de la suite | Message d'erreur publié : ID relu et texte | Résolution vérifiée ou encore ouverte |
|---|---|---|---|---|---|

L'agent contrôle transmet son constat au Leader ; le Leader ou l'exécutant autorisé publie et relit
le message d'erreur. Donner la référence réelle du message au canal d'origine, si disponible.
Aucune publication ou réception ne doit être affirmée faute de preuve. Un succès sur une autre
pièce ne clôt pas cette anomalie. Un échec de notification reste lui-même à signaler.
