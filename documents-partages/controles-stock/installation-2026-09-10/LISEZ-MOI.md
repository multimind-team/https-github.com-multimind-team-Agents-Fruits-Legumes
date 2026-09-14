# Contrôle renforcé — état vérifié de l'installation

## Consignes et responsabilités

La consigne canonique est `AGENT.md`. Le circuit détaillé est dans
`procedures/controle-stock.md` et le dossier de preuves suit
`reference/modele-controle-stock.md`.

Les imports confiés aux agents exigent une lecture réelle des sources par courrier, une
simulation par données, un avis d'un contrôleur distinct AVANT écriture, puis une nouvelle
intervention de contrôle APRÈS import et recalcul. Le contrôleur ne s'auto-certifie pas et son
avis ne remplace aucune autorisation humaine requise. L'absence d'avis suspend le périmètre concerné.

La matrice comporte 24 familles de risques. La recette documentaire indépendante porte sur
16 scénarios fictifs, pas sur tous les cas imaginables ni sur des mouvements réels. Les dates,
comptages intercalaires, doublons, rectificatifs, quantités réellement reçues, unités, colisages,
exhaustivité, interruptions et notifications y sont traités explicitement.

## Vérifications réelles

- Revue contradictoire de la documentation : cinq ambiguïtés corrigées et relues par un autre agent.
  Avis limité aux consignes ; l'activation Email n'est pas certifiée.
- Défaut F01 : un vrai second relevé le même jour est désormais un nouveau `comptage` à son
  propre instant, et non une correction antidatée. Les anciennes corrections restent inchangées.
- Un contrôle indépendant a ensuite bloqué le déploiement sur un conflit d'ancien instant non
  détecté. Le nouveau test a échoué avant correction ; le conflit est maintenant refusé sans
  écrire le reste du lot, dans les deux ordres testés. L'avis indépendant v2 lève ce seul blocage.
- Suite complète finale : **352 tests, OK**, 279,480 secondes, code retour 0 et sources stables
  pendant le test. Le précédent gate à 351 tests est une preuve antérieure, pas le gate courant.
- Serveur de l'application redémarré par son gestionnaire ; événement de démarrage journalisé
  le 10 septembre 2026 à 21 h 11 min 59 s. Serveur et surveillance identifiés, maintenance désactivée.
- Contrôle parent après démarrage : cinq GET HTTPS répondent 200 avec les octets exacts des fichiers
  locaux (accueil, comptage, commande, proposition et fraîcheur). Aucun POST métier de test.
- Les 230 fichiers initiaux surveillés ont conservé leurs données. Seul le journal technique a reçu
  une ligne de démarrage supplémentaire, avec préfixe antérieur intact. Aucun mouvement, comptage,
  colisage, mapping, photographie ou classeur n'a été corrigé/réimporté pendant cette installation.

## Limites encore ouvertes

1. **Email : contexte non renouvelé.** L'accord demandé n'a pas été reçu. Aucun reset, restart
   Gateway, mail de test ou envoi SMTP n'a été effectué. Un ancien prompt sauvegardé existe ;
   les fichiers actualisés et les essais Desktop ne prouvent pas le traitement des prochains mails.
   L'activation et sa vérification sur le chemin Email restent à réaliser après accord.
2. **AGENTS.md protégé, inchangé.** L'alignement du résumé secondaire a été bloqué faute
   d'approbation. Aucune autre méthode n'a été utilisée pour contourner cette protection.
   Son entête renvoie déjà au canonique `AGENT.md`, qui porte les règles détaillées actuelles.
3. **Chronologie intrajournalière limitée.** La bascule technique de 14 h du moteur n'atteste pas
   une fermeture. Une mesure pendant l'ouverture et des ventes seulement agrégées par journée
   ne permettent pas d'inventer les ventes avant/après. Bloquer ou clarifier le cas concerné.
4. **Aucune certification du stock physique existant.** Les deux exports de livraison encore
   ambigus n'ont pas été importés et les comptages historiques n'ont pas été réinterprétés.
5. **Consigne d'agents, pas verrou de tous les CLI.** Les outils ne bloquent pas techniquement
   toute commande lancée hors procédure. Les agents doivent lire, confronter, statuer et vérifier
   effectivement chaque lot ; un rapport JSON ou un code retour 0 n'est pas à lui seul ce contrôle.

## Preuves privées

- `audit-moteur-avant.json` : diagnostic avant correctif ; ses constats doivent être lus avec les suites.
- `diagnostic-activation-email.json` : mécanisme natif et limites d'adoption constatés.
- `recette-agents-v1.json` : première recette, conservée sans réécriture.
- `revue-docs-finale-synthese.json` : requalification des 16 cas et réserves documentaires.
- `correctif-recomptage-synthese-auteur.json` : préparation technique initiale, avant la reprise C01.
- `avis-fix-v1-bloque-synthese.json` : refus indépendant ayant empêché le premier déploiement.
- `avis-fix-v2-valide.json` : recontrôle indépendant du cas C01 corrigé.
- `verification-gate-parent-v2.json` : résultat du gate courant et empreintes du code validé.

Les chemins des rapports sources complets et leurs empreintes figurent dans les synthèses.
Ces preuves sont privées : un GET HTTPS vers le rapport d'activation connu renvoie 404.
Les exemples de recette ne constituent jamais une livraison, une vente ou une autorisation d'import.
