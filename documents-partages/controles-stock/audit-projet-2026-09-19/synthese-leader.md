# Audit approfondi du projet — 19 septembre 2026

**Auteur : Leader.** Synthèse des exécutions distinctes agent-donnees, agent-controle et agent-audit-stock, relue dans le code par le Leader. Demande source : « analyses en profondeur ce projet et dit moi si il y a des erreurs, qu'est ce qui pourrait entrainer des erreurs? ».

**Conclusion : dix défauts principaux et un cas supplémentaire dormant ont été reproduits dans des copies ou des fixtures isolées.** Plusieurs ne sont pas déclenchés par les données actuelles. Les cas usuels passent les tests ; les défauts concernent surtout les transitions entre écrans, les reprises hors connexion, les formats d'import et les limites du calcul. Cet audit ne valide pas les quantités de la commande et n'autorise aucune modification métier.

## Périmètre et méthode

- Documentation officielle : index et fiches applicables aux imports, stocks, prévisions, interfaces, API, tests, sécurité et rôles ; confrontation au code et aux données du dossier de travail.
- Agent-donnees : importeurs de mouvements et Mercalys, pipeline courrier, factures directes et classeurs.
- Agent-controle : saisies sur téléphone, stockage local, échanges avec l'API et actualisation de la proposition.
- Agent-audit-stock : chronologie des faits, conversions, agrégats, calcul et fiabilité des positions/propositions.
- Leader : coordination, contre-lecture des défauts, serveur, surveillance, contrôles de structure et tests d'ensemble.
- État examiné : fichiers locaux, y compris modifications préexistantes ; aucune réinitialisation Git.

**Validation réalisée :** `py -3.14 -B tests/lancer_tests_isoles.py` : **474 tests, OK**, durée annoncée 336,298 secondes, code retour 0. Les messages « ÉCHEC » émis par des scénarios fictifs ne sont pas des échecs de la suite.

`py -3.14 -B tests/lancer_tests_isoles.py --navigateur` : **28 cas réussis** (six écrans à quatre largeurs, puis quatre parcours comprenant comptage hors ligne, renvois/recalculs, commande/masquage et réception de message). Navigateur Edge dans une copie, sans agent externe ni courriel. [Résultat navigateur conservé](C:/Users/user/Desktop/preparation-commande-dev/documents-partages/controles-stock/audit-projet-2026-09-19/resultats-navigateur.json).

Contrôle complémentaire : 60 fichiers Python analysés syntaxiquement et lecture des 29 JSON et 23 JSONL métier sélectionnés, sans erreur de structure/non-fini. Les secrets et le courrier privé sont exclus de ce contrôle. Les empreintes relevées des fichiers moteur/app/données sélectionnés sont restées identiques à la fin des tests. Les essais et leurs sorties temporaires n'ont modifié ni le code applicatif ni les données métier. Seuls les rapports privés de cet audit sont ajoutés au projet.

## Défauts reproduits

P1 : correction prioritaire, risque de perte de données, stock faux ou interruption globale. P2 : défaut réel mais déclenchement plus limité. Il s'agit de priorité de maintenance, pas d'une affirmation que chaque problème s'est déjà produit au magasin.

### 1. P1 — Une ancienne saisie du téléphone peut remplacer une mesure récente

**Déclencheur :** compter 2 colis dans Compter, envoyer, puis corriger à 7 dans Commander. Revenir dans Compter affiche encore 2, malgré la proposition serveur à 7. Valider cette valeur sans la ressaisir crée un nouvel horodatage et renvoie 2 ; le serveur traite cette validation comme une mesure plus récente.

**Cause :** Commander ne met pas à jour le cache des comptages du jour ; Compter donne priorité à ce cache local sans comparer l'instant de mesure avec celui du serveur. Reproduction navigateur sur pages copiées, HTTP intercepté ; pas d'essai sur les stocks réels.

**Sources :** [commander.html:930](C:/Users/user/Desktop/preparation-commande-dev/app/commander.html:930), [compter.html:341](C:/Users/user/Desktop/preparation-commande-dev/app/compter.html:341), [compter.html:432](C:/Users/user/Desktop/preparation-commande-dev/app/compter.html:432), [serveur.py:854](C:/Users/user/Desktop/preparation-commande-dev/moteur/serveur.py:854).

**Correction proposée :** partager l'état des mesures entre écrans et arbitrer par instant/identifiant de mesure ; conserver séparément les relevés non acquittés. Un affichage ancien ne doit pas être présenté comme le dernier comptage connu.

### 2. P1 — Un relevé resté hors ligne la veille bloque les envois suivants

**Déclencheur :** une file contient un comptage du 18/09 et un du 19/09. Le 19/09, l'écran envoie toute la file ; l'API refuse le lot parce qu'il contient une date autre qu'aujourd'hui. Deux tentatives reproduites donnent le même refus et conservent les deux relevés.

**Cause :** aucune résolution de la file ancienne n'est prévue dans l'interface. L'affichage conseille de réessayer devant la porte alors que la cause est la date, pas le réseau. Reproduction avec navigateur copié et la vraie fonction de validation serveur extraite pour la fixture.

**Sources :** [serveur.py:317](C:/Users/user/Desktop/preparation-commande-dev/moteur/serveur.py:317), [compter.html:573](C:/Users/user/Desktop/preparation-commande-dev/app/compter.html:573), [compter.html:602](C:/Users/user/Desktop/preparation-commande-dev/app/compter.html:602).

**Correction proposée :** isoler les relevés anciens, expliquer le refus et proposer leur traitement contrôlé ; permettre l'envoi du périmètre actuel sans perdre ni redater les anciens relevés.

### 3. P2 — Une réponse réseau ancienne peut faire reculer la proposition affichée

**Déclencheur :** corriger l'article A puis B. Retenir la réponse de lecture après A, laisser arriver celle après B, puis libérer la première. Dans la reproduction, B passe correctement à 9 puis revient à 2 à l'écran.

**Cause :** le code accepte toute génération différente de celle capturée au début de sa propre requête. Il ne vérifie pas qu'elle est plus récente que la proposition déjà affichée ni que la requête est encore pertinente. Le défaut est visuel ; cette réponse GET ne réécrit pas le stock du serveur.

**Source :** [commander.html:958](C:/Users/user/Desktop/preparation-commande-dev/app/commander.html:958).

**Correction proposée :** ordonner les actualisations, ignorer les réponses dépassées et vérifier la génération/fin du recalcul correspondant à l'action.

### 4. P1 — Une perte de 100 % arrête la génération de toute la proposition

**Déclencheur :** un article avec ventes cumulées à zéro et casse positive. Le calcul fournit un taux de perte de 1, puis divise par `1 - tauxPerte`. Vente 0 et casse 10 reproduisent `ZeroDivisionError`.

**Sources :** [calculer-commande.py:136](C:/Users/user/Desktop/preparation-commande-dev/moteur/calculer-commande.py:136), [proposer-commande.py:162](C:/Users/user/Desktop/preparation-commande-dev/moteur/proposer-commande.py:162).

**Situation actuelle :** aucun taux ≥ 0,9 trouvé dans les agrégats ; aucune panne actuelle attribuée à ce défaut. Les carnets contiennent néanmoins 230 faits de vente à quantité zéro, une entrée admise par l'importeur.

**Correction proposée :** qualifier les taux non exploitables et traiter explicitement le produit concerné, sans inventer un taux de substitution et sans faire échouer tous les autres articles.

### 5. P2 — Un même instant donne un stock différent selon son fuseau horaire

**Déclencheur :** une mesure à `17:30+02:00` est classée soir, la même à `15:30Z` est classée matin. Avec une mesure de 10 et une vente de 4, la position calculée est respectivement 10 et 6.

**Cause :** l'API accepte les fuseaux, mais le moteur découpe le texte de l'heure sans conversion vers l'heure du magasin. Cela affecte aussi le classement chronologique des mesures.

**Sources :** [serveur.py:349](C:/Users/user/Desktop/preparation-commande-dev/moteur/serveur.py:349), [calculer-position.py:129](C:/Users/user/Desktop/preparation-commande-dev/moteur/calculer-position.py:129), [calculer-position.py:183](C:/Users/user/Desktop/preparation-commande-dev/moteur/calculer-position.py:183).

**Situation actuelle :** aucun comptage avec fuseau explicite trouvé ; défaut latent. **Correction proposée :** normaliser les instants dans le fuseau magasin avant comparaison, avec traitement explicite des anciennes dates sans fuseau.

### 6. P2 — Un conflit d'heure physique peut être accepté comme un doublon exact

**Déclencheur :** deux faits avec le même ID ne diffèrent que par `source.saisi_le` (08h ou 18h). Le lecteur ignore la seconde version comme doublon. Le stock de la reproduction vaut 6 ou 10 selon l'ordre des versions.

**Cause :** la signature exclut tout le champ `source`, alors que son heure de saisie influence le calcul. [faits.py:12](C:/Users/user/Desktop/preparation-commande-dev/moteur/faits.py:12).

**Situation actuelle :** aucun doublon réel de ce type trouvé. **Correction proposée :** comparer tous les champs qui influencent le résultat métier, même lorsqu'ils sont rangés dans `source` ; permettre uniquement les différences de provenance sans effet métier.

### 7. P1 — Certains codes numériques Excel font ignorer des mouvements sans alerte

**Déclencheur :** `0000000000049` en texte donne un fait ; le nombre `49` ou le flottant `87010624.0` donne zéro fait et zéro alerte. Le CLI en simulation, avec lecteur et référentiels remplacés par fixtures, rend code 0 et `a_verifier: []`.

**Cause :** seules les chaînes de 8 à 13 chiffres sont retenues ; tout autre code est ignoré comme une ligne de total. Les zéros initiaux perdus et le suffixe `.0` de certains nombres Excel ne sont pas distingués d'un total. **Limite de preuve :** pas de fichier XLS synthétique lu de bout en bout ; conversion et compte rendu CLI vérifiés. Les exports réels du 19/09 utilisent des codes texte : aucune omission actuelle revendiquée.

**Sources :** [integrer-fichiers.py:307](C:/Users/user/Desktop/preparation-commande-dev/moteur/integrer-fichiers.py:307), [integrer-fichiers.py:398](C:/Users/user/Desktop/preparation-commande-dev/moteur/integrer-fichiers.py:398).

**Correction proposée :** normaliser les codes de façon contrôlée, vérifier leur correspondance au catalogue et signaler chaque ligne produit non intégrée. Ne pas compléter arbitrairement un code ambigu.

### 8. P1 — Deux créations simultanées du classeur peuvent effacer une facture

**Déclencheur reproduit :** classeur générique absent. A constate l'absence puis attend ; B crée le classeur et importe sa facture ; A reprend et recopie le modèle par-dessus, puis importe. Les deux imports annoncent une ligne ajoutée, mais il ne reste que la facture A.

**Cause :** le choix et la copie du modèle se font avant le verrou de l'import. Reproduction déterministe avec les véritables fonctions, le modèle installé copié et deux threads synchronisés. Aucun fichier original touché.

**Sources :** [facture_directe.py:154](C:/Users/user/Desktop/preparation-commande-dev/moteur/facture_directe.py:154), [importer-facture-directe.py:38](C:/Users/user/Desktop/preparation-commande-dev/moteur/importer-facture-directe.py:38), [facture_directe.py:447](C:/Users/user/Desktop/preparation-commande-dev/moteur/facture_directe.py:447).

**Correction proposée :** mettre choix, création et import sous le même verrou ; empêcher la création d'écraser une destination apparue entre-temps. Le risque porte sur le classeur, pas sur un stock doublé démontré par ce scénario.

### 9. P2 — Le mode simulation de facture écrit un fichier

**Déclencheur :** exécuter le vrai CLI copié avec `--classeur-seul --simuler` vers un classeur générique absent. Le résultat dit `simulation: true`, mais le classeur est créé sur disque. Aucun fait de stock n'est écrit.

**Cause :** la même copie anticipée que dans le défaut 8 précède la prise en compte de `--simuler`. **Correction proposée :** sélection sans écriture et préparation depuis le modèle en mémoire ; création seulement à l'exécution réelle.

### 10. P2 — Le modèle Pomona actuel échoue lors d'une seconde date

**Déclencheur :** avec une copie exacte du modèle à une seule feuille `Date du jour`, le 20/09 est importé et renomme cette feuille. Le 21/09 est refusé faute de feuille `Date du jour` ou `Vierge`.

**Source :** [facture_directe.py:223](C:/Users/user/Desktop/preparation-commande-dev/moteur/facture_directe.py:223).

**Portée :** le modèle vide n'est pas à lui seul une erreur. Le nouveau mode d'emploi prévoit un classeur temporaire supprimé après SMTP. Le défaut apparaît si l'on garde le fichier pour téléchargement sans courriel, si l'envoi échoue ou si l'on utilise le classeur mensuel explicite. Ces usages nécessitent de préserver l'historique.

**Correction proposée :** préserver une feuille modèle permanente ou recopier une feuille de l'original pour la date suivante sans supprimer les feuilles renseignées.

### Cas supplémentaire dormant — Le bouton + peut rester sans effet

Avec une proposition de 3 colis et un ajustement agent marqué `applique:true` à 2, cliquer sur + calcule 3 puis supprime la décision locale parce qu'elle égale la proposition initiale. Le calcul d'affichage réapplique alors 2. Reproduction navigateur : 2 avant, 2 après, mémoire locale vide. Sources : [commander.html:561](C:/Users/user/Desktop/preparation-commande-dev/app/commander.html:561) et [commander.html:887](C:/Users/user/Desktop/preparation-commande-dev/app/commander.html:887).

Les trois lignes d'ajustement réelles consultées ont `applique:false` : le déclencheur est absent dans l'état examiné. La correction devra comparer l'action humaine avec la valeur effectivement utilisée sans décision locale, afin de respecter sa priorité. Ce point est conservé séparément des parcours actuellement usuels.

## Risques métier et d'exploitation distincts

### Positions perdues qui continuent d'alimenter de grosses propositions

État enregistré le 19/09 vers 05:27 : `recalcul=termine`, `fraicheur=a-jour`, 328 lignes dont 183 non masquées ; parmi les actives, 8 positions inconnues, 7 positions ≤ −10 colis et 14 articles sans correspondance connue.

L'exception documentée des sept jours continue d'autoriser le calcul sur certaines positions affichées perdues :

| Article | Position calculée | Proposition | Dernière mesure |
|---|---:|---:|---|
| Banane vrac | −21,4 colis | 31 colis | 15/09 |
| Batavia blonde | −14,7 colis | 28 colis | 15/09 |
| Tomate côtelée noire | −16,8 colis | 26 colis | 15/09 |
| Tomate côtelée rouge | −45,7 colis | 60 colis | 15/09 |

Les valeurs initialement mesurées étaient positives ou nulles. La négativité résulte des mouvements postérieurs ; cet audit n'en démontre pas la cause physique. Le statut « à jour » n'est donc pas une certification du stock physique. **Action utile : recomptage ciblé et enquête sur les mouvements avant de s'appuyer sur ces quantités.** Ne pas réduire ou modifier automatiquement la commande sur la seule base de cet audit.

### Le dimanche intermédiaire n'entre pas dans le besoin

Le calcul additionne la demande du jour de commande et celle du jour de livraison. Pour samedi → lundi, la demande du dimanche est absente. Dans la reproduction, la faire passer de 0 à 100 unités ne change pas le besoin de 20 unités. Le magasin ouvre le dimanche matin et les carnets présentent des ventes sur 63 dimanches.

Cette limite est cohérente avec le modèle actuellement documenté ; elle nécessite un arbitrage métier explicite sur l'horizon de couverture. Risque : besoin sous-estimé le week-end.

### Un export rectificatif incomplet peut laisser des mouvements anciens

Initial A=12/B=15, renvoi A=12 seulement : B reste dans les faits sans conflit. Ce comportement peut être correct pour un export partiel, mais insuffisant pour un remplacement intégral. Comparer les périmètres et conserver une correction explicite ; ne pas additionner ou supprimer automatiquement des lignes absentes.

### Le serveur et la surveillance ne prouvent pas une réponse automatique d'agent

Le contrôle d'exploitation a trouvé **zéro serveur identifié, zéro surveillance serveur et maintenance active**. Tailscale Serve reste configuré vers `127.0.0.1:8751`. Cet état de maintenance n'est pas qualifié de panne accidentelle et n'a pas été changé pendant l'audit.

La sentinelle indiquait une écoute des sources et zéro événement en attente à sa dernière vérification enregistrée ; ce fichier ne prouve pas à lui seul la disponibilité d'un superviseur externe. Le serveur lance un script qui prépare un prompt et rend `agent-requis`, puis jette sa sortie ; le script ne lance pas d'agent. Sans superviseur externe, un message peut être enregistré sans réponse métier. C'est une dépendance d'exploitation documentée, pas une fonctionnalité autonome validée ici. Sources : [serveur.py:382](C:/Users/user/Desktop/preparation-commande-dev/moteur/serveur.py:382), [repondre-message-rayon.py:26](C:/Users/user/Desktop/preparation-commande-dev/moteur/repondre-message-rayon.py:26).

### Chronologie physique et interruptions

L'heure du mail, le seuil de 17h et l'ancienneté du comptage sont des conventions techniques, pas des preuves de rangement de livraison ou de fermeture du magasin. Une vente journalière ne fournit pas son heure de passage. Le contrôle humain des cas ambigus reste nécessaire.

Le verrou commun et le remplacement atomique protègent les opérations courantes, mais ne forment pas une transaction unique entre carnets, classeur et dérivés. Après coupure du PC, échec Excel ou recalcul interrompu, vérifier les écritures réellement présentes avant de reprendre ; ne jamais considérer un seul code retour ou fichier archivé comme preuve de fin.

## Ordre proposé pour les corrections

1. Sécuriser les mesures entre les deux écrans et débloquer proprement les files conservées d'un jour à l'autre.
2. Protéger la création du classeur et rendre la simulation sans écriture.
3. Empêcher l'omission silencieuse des lignes Excel et l'arrêt global sur un taux de perte invalide.
4. Ordonner les réponses de recalcul ; unifier le traitement des heures et des conflits de faits.
5. Permettre les dates successives du classeur sans perte d'historique.
6. Après contrôle du stock physique, arbitrer séparément le traitement des positions perdues et du dimanche.

Chaque correction devra ajouter le scénario de régression correspondant dans la copie isolée. Les tests existants seuls ne couvrent pas les défauts décrits ici.

## Rapports et limites

- [Rapport agent-donnees](C:/Users/user/Desktop/preparation-commande-dev/documents-partages/controles-stock/audit-projet-2026-09-19/agent-donnees.md).
- [Rapport agent-audit-stock](C:/Users/user/Desktop/preparation-commande-dev/documents-partages/controles-stock/audit-projet-2026-09-19/agent-audit-stock.md).
- [Rapport indépendant agent-controle avec empreintes](C:/Users/user/Desktop/preparation-commande-dev/documents-partages/controles-stock/audit-ui-20260919-agent-controle.md) et [script navigateur reproductible](C:/Users/user/Desktop/preparation-commande-dev/documents-partages/controles-stock/repro-ui-20260919-agent-controle.py). Le script lit les sources puis les copie en temporaire ; son HTTP est intercepté et ses articles sont fictifs.
- [Reproduction calcul autonome](C:/Users/user/AppData/Local/Temp/audit_stock_20260919_ijbk0yhp/reproduire.py) et [résultats calcul conservés](C:/Users/user/Desktop/preparation-commande-dev/documents-partages/controles-stock/audit-projet-2026-09-19/preuves-calcul.json). Le script temporaire dépend de la copie moteur voisine et peut disparaître lors d'un nettoyage de Windows ; les résultats essentiels sont conservés dans ce dossier.
- [Empreintes des sources examinées](C:/Users/user/Desktop/preparation-commande-dev/documents-partages/controles-stock/audit-projet-2026-09-19/empreintes-sources.json), vérifiées inchangées après les essais.
- Fixtures d'import : `C:/Users/user/AppData/Local/Temp/preparation-audit-imports-yevnxoee` ; aucune prétention de traitement des factures réelles.

La revue n'est ni une garantie d'absence d'autres bugs, ni un audit exhaustif de toutes les pièces jointes historiques. Aucun contrôle sur téléphone physique, aucun envoi de commande ou de courriel, aucune validation des prix/marges et aucune correction de stock n'ont été effectués.
