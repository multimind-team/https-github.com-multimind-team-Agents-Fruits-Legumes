# Rapport privé — agent-audit-stock — 19 septembre 2026

Demande source : audit profond du projet et recherche de causes d'erreurs, demandé par le responsable dans la conversation Codex. Mandat du Leader : examiner les calculs de stock et de commande en lecture seule, reproduire les défauts uniquement en copie isolée, sans import ni recalcul de production ni publication dans le chat de l'application.

Rôle réel : agent-audit-stock. Le présent document est un rapport d'audit, pas une validation de commande, un avis d'intégration ou une écriture de stock. Le Leader relit les conclusions avant restitution.

## Périmètre et preuves

Modules examinés : `moteur/calculer-position.py`, `faits.py`, `agregats.py`, `calculer-commande.py`, `proposer-commande.py`, `generer-proposition.py`, `filet-de-securite.py` ; vérifications ciblées de `serveur.py`, `integrer-fichiers.py` et `regles.py`.

Références consultées : `AGENTS.md`, `agents/agent-audit-stock.md`, `donnees/pouvoirs.json`, documentation officielle `Documents/Documentation de l'application/index.html` et fiches des chapitres 6, 8, 10, 11, 12, 13, `reference/le-calcul.md`, `reference/le-metier.md`, `procedures/controle-stock.md`.

Données relues : `donnees/etat.json`, `dernier-import.json`, `agregats.json`, `proposition.json`, `fraicheur.json`, `recalcul.json` et carnets `donnees/faits/*.jsonl` pour les contrôles décrits ci-dessous. Aucun original d'export n'a été certifié par cet audit du moteur.

Reproduction autonome exécutée avec succès en copie isolée :

- Script : `C:/Users/user/AppData/Local/Temp/audit_stock_20260919_ijbk0yhp/reproduire.py`.
- Copie des modules : `C:/Users/user/AppData/Local/Temp/audit_stock_20260919_ijbk0yhp/moteur/`.
- Résultats : `C:/Users/user/AppData/Local/Temp/audit_stock_20260919_ijbk0yhp/preuves.json`.
- Commande : `py -3.14 -B C:\Users\user\AppData\Local\Temp\audit_stock_20260919_ijbk0yhp\reproduire.py`.

Le script utilise des faits fictifs et ne lit aucun carnet ni journal du projet. Ces fichiers Temp sont des preuves temporaires ; le présent rapport conserve leurs résultats essentiels.

## Défauts techniques démontrés

### F1 — Priorité proposée P1 : perte de 100 % et arrêt de la génération globale

`moteur/calculer-commande.py:136` calcule `tauxPerte=perdu/(vendu+perdu)`. Une ligne de vente nulle avec une casse positive produit exactement 1. `moteur/proposer-commande.py:162` divise ensuite par `1-taux_perte` sans traiter le cas.

Reproduction fictive : vente 0, casse 10 → taux 1 → `ZeroDivisionError: division by zero`. L'exception intervient avant les filtres promotion/masquage : un seul article peut interrompre la génération de toutes les lignes. L'importeur conserve les ventes nulles (`moteur/integrer-fichiers.py:415` et suivants).

Incidence actuelle : aucun article à tauxPerte >= 0,9 dans les agrégats relus, donc aucune panne actuelle de cette nature démontrée. Les carnets contiennent 230 faits de vente à quantité zéro : ce type de ligne existe dans les données réelles.

Piste technique à examiner : qualifier explicitement un taux inexploitable et isoler la ligne concernée, sans inventer un taux de remplacement ni arrêter tous les articles. Aucune correction appliquée.

### F2 — Priorité proposée P2 : fuseau accepté par l'API, ignoré par le calcul

`moteur/serveur.py:349` et suivants acceptent les horodatages avec `Z` ou un décalage `+/-HH:MM`. `moteur/calculer-position.py:129` extrait uniquement les caractères de l'heure ; `heure_physique`, ligne 183, fait de même pour l'ordre des mesures.

Reproduction fictive : `2026-09-18T17:30:00+02:00` et `2026-09-18T15:30:00Z` désignent le même instant, mais donnent respectivement les phases soir et matin. Pour une mesure de 10 et une vente de 4 dans la journée, les positions sont respectivement 10 et 6. L'ordre de deux mesures peut également dépendre de la représentation horaire plutôt que de leur instant réel.

Incidence actuelle : aucun comptage avec fuseau explicite trouvé dans les carnets relus. Défaut latent, pas incident actuel revendiqué.

Piste technique à examiner : normaliser les instants dans le fuseau du magasin avant classement et comparaison. Aucune correction appliquée.

### F3 — Priorité proposée P2 : conflit sur l'heure physique masqué comme doublon

`moteur/faits.py:12` exclut entièrement `source` de la signature de comparaison des faits. Or `source.saisi_le` prévaut dans le calcul de position et dans le choix de la dernière mesure.

Reproduction fictive : deux faits de même ID et mêmes champs sauf `source.saisi_le`, à 08h pour l'un et 18h pour l'autre, ont la même signature. Le lecteur ignore la seconde copie sans signaler de conflit. Avec une vente journalière de 4 et une mesure de 10, la position vaut 6 si la copie matinale arrive en premier, ou 10 si la copie du soir arrive en premier. Chaque lecture annonce un doublon ignoré.

Incidence actuelle : aucun doublon réel avec `source.saisi_le` divergent trouvé. Défaut latent, pas incident actuel revendiqué.

Piste technique à examiner : inclure dans la comparaison métier les champs de source qui influencent le calcul ; seules les différences de provenance sans effet peuvent être ignorées. Aucune correction appliquée.

## Risques métier distincts des trois défauts

### R1 — Dimanche absent de l'horizon calculé

Le besoin exécuté additionne uniquement la demande du jour de commande et celle du jour de livraison (`moteur/proposer-commande.py:107`, 108 et 159 à 162). Pour samedi 19/09 vers lundi 21/09, modifier la prévision du dimanche de 0 à 100 unités laisse la proposition fictive inchangée à 20 unités.

Le magasin ouvre normalement le dimanche de 9h à 12h15 (`reference/le-metier.md:26`). Les carnets contiennent des ventes sur 63 dimanches, dont 120 lignes le 13/09/2026. La formule exécutée est documentée ; ce constat est donc présenté comme un risque du modèle à arbitrer avec le responsable, pas comme une nouvelle règle autorisée ni une correction automatique. Aucun manque réel de commande n'est quantifié par cette reproduction fictive.

### R2 — Exception des sept jours sur des positions très négatives

`moteur/proposer-commande.py:184` autorise encore le calcul sous -10 colis si le comptage est récent. Cette exception existe aussi dans `reference/le-calcul.md` : ce n'est pas une divergence code/documentation. Elle peut néanmoins produire de fortes propositions sur des positions affichées perdues.

Dans la proposition enregistrée le 19/09 à 05:27 :

| Article | Code | Position calculée | Proposition | Dernière mesure |
|---|---|---:|---:|---|
| Banane vrac | 0000087004011 | -21,4 colis | 31 colis | 15/09 |
| Batavia blonde pièce | 0000087003169 | -14,7 colis | 28 colis | 15/09 |
| Tomate côtelée noire vrac | 0000087004808 | -16,8 colis | 26 colis | 15/09 |
| Tomate côtelée rouge vrac | 0000087004807 | -45,7 colis | 60 colis | 15/09 |

Les mesures initiales étaient respectivement 5,7 ; 0 ; 16,2 ; 7,7 colis. Les valeurs négatives ci-dessus résultent donc des calculs postérieurs ; leur cause physique n'a pas été démontrée par cet audit.

Références exactes dans `donnees/faits/2026.jsonl` :

- Ligne 44471 : `comptage:2026-09-15:0000087004011:mesure:2026-09-15T18:21:58` ; quantité métier 105,45, soit 5,7 colis lors de la mesure.
- Ligne 44480 : `comptage:2026-09-15:0000087003169:mesure:2026-09-15T18:23:10` ; quantité 0.
- Ligne 44513 : `comptage:2026-09-15:0000087004808:mesure:2026-09-15T18:26:17` ; quantité métier 56,7, soit 16,2 colis lors de la mesure.
- Ligne 44498 : `comptage:2026-09-15:0000087004807:mesure:2026-09-15T18:25:07` ; quantité métier 26,95, soit 7,7 colis lors de la mesure.

Un recomptage ciblé et une enquête sur les mouvements permettraient de vérifier ces bases avant de s'appuyer sur les propositions. Aucun mouvement correcteur n'a été inventé.

### R3 — Phases intrajournalières et réception mail

Limites déjà documentées dans `procedures/controle-stock.md` : phase soir à partir de 17h, absence d'heure assimilée au soir, traitement à la journée et heure du mail utilisée comme repère de livraison, avec repli à 06h30. Ces conventions ne prouvent ni la fermeture réelle du magasin ni le rangement physique des marchandises. Une livraison tardive le même jour ou une mesure pendant l'ouverture peut exiger un contrôle humain que le calcul ne représente pas finement.

## État relu, écritures et limites

Dernier calcul enregistré : 19/09/2026 vers 05:27, `recalcul.json=termine`, `fraicheur.json=a-jour`. Ces statuts rapportent le calcul enregistré ; ils ne certifient pas à eux seuls les sources et quantités physiques.

Proposition : 328 lignes, 183 non masquées, 8 positions inconnues, 7 positions <= -10 colis. Quatre de ces sept lignes bénéficient de l'exception de mesure récente décrite ci-dessus. Au moment de la lecture, les positions présentes dans `agregats.json` correspondaient à celles d'`etat.json`.

Écritures réellement faites : copie temporaire des modules, script et résultats de reproduction en Temp ; présent rapport privé, conformément au mandat complémentaire du Leader. Aucun stock, carnet, permission, configuration, code applicatif, commande ou message de l'application modifié. Aucun recalcul de production lancé. Aucun acquittement de sentinelle réalisé.

Ce rapport n'attribue aucun écart physique à une livraison manquante, une casse, une erreur de caisse ou une autre cause non démontrée. La suite globale de tests relève du Leader ; ses résultats ne sont pas présentés comme des tests exécutés par cet agent.
