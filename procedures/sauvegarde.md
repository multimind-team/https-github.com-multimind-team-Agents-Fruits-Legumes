# Sauvegarde et synchronisation GitHub (`/sauvegarde`)

## Déclenchement et périmètre

Lancer cette procédure sur demande explicite du responsable (`/sauvegarde`, « sauvegarde »), après la revue documentaire. Une correction de code ou un import de fichiers ne déclenche pas à lui seul un commit ou un envoi sur GitHub.

Le script sauvegarde les fichiers retenus par Git. Le fichier local `.env`, le courrier brut et les autres chemins exclus restent sur le disque : cette publication ne remplace pas une sauvegarde privée de ces originaux. Les contrôles ci-dessous sont ciblés ; ils ne prouvent pas l'absence de données sensibles dans tout l'historique Git ou dans le dépôt distant.

## Phase A – Revue par le Leader

1. Lire le statut Git et les différences réelles, en distinguant les modifications antérieures à l'intervention.
2. Mettre à jour les procédures, références et fiches HTML concernées dans `Documents/Documentation de l'application/`.
3. Vérifier que les règles expliquées correspondent au comportement du code et aux autorisations en vigueur. Aucun script ne peut certifier cette cohérence métier.

La source canonique est `AGENTS.md`. `AGENT.md` est un renvoi historique vers cette source ; il ne doit pas redevenir une copie divergente des règles.

## Phase B — Chaîne technique

Lancer `sauvegarder.bat` ou `py -3.14 -B moteur/sauvegarder.py` uniquement après cette revue.

### 1. Vérifier les exclusions et l'index réel

- Vérifier que `.env` est ignoré et que `donnees/courrier-config.json` ne contient aucun mot de passe.
- Vérifier l'exclusion des nouveaux fichiers de `donnees/courrier/` avec un nom `.eml` ; un nom `.tmp` serait une fausse preuve, cette extension étant déjà ignorée partout.
- Vérifier aussi les traces privées exactes : `donnees/.sentinelle-evenements.json` (contenus et en-têtes en attente), `donnees/.courrier_uids_connus.json` (ancien registre mail) et `donnees/.operations-bail.lock` (bail technique). Leur exclusion ne dispense pas du contrôle des fichiers déjà suivis.
- Relire les chemins effectivement suivis/indexés avec `git ls-files -z`. Un `.env`, une trace privée listée ci-dessus ou un fichier de `donnees/courrier/` encore suivi bloque la sauvegarde, même si `.gitignore` contient déjà son exclusion.
- Refaire ce contrôle avant et après `git add -A`. Le script ne retire pas spontanément un fichier de l'index et ne supprime jamais les originaux du courrier.

Un retrait du suivi Git conserve le fichier local. Il n'efface pas les anciennes versions déjà enregistrées dans l'historique ; une intervention sur cet historique est une opération distincte.

### 2. Vérifier la syntaxe et exécuter les tests en copie

- `tests/verifier_projet.py` lit les fichiers du projet et vérifie leur syntaxe Python, JavaScript, JSON et JSONL. Un résultat absent ou illisible est un échec, pas un succès implicite.
- Les tests sélectionnés de préparation des photos et d'envoi du classeur sont lancés par `tests/lancer_tests_isoles.py` dans une copie temporaire. Les secrets et le courrier brut sont exclus ; la configuration de courrier de cette copie est neutralisée.
- La garde Python bloque les écritures dans l'installation originale, les connexions externes et les appels au serveur de production sur le port 8751. Les fixtures peuvent ouvrir leurs propres serveurs locaux. Ce dispositif de test coopératif n'est pas une isolation système pour du code hostile.
- Toute erreur de contrôle ou de test interrompt la publication.

Pour un audit complet explicitement demandé : `py -3.14 -B tests/lancer_tests_isoles.py`. Pour une vérification ciblée : ajouter les chemins des fichiers de test comme arguments séparés.

Pour les parcours navigateur avec envois de comptages et changements de réglages fictifs : `py -3.14 -B tests/lancer_tests_isoles.py --navigateur --sortie <dossier-externe>`. Ce chemin ajoute la garde aux sous-processus de recalcul et utilise uniquement des copies sans courrier ni secrets. Le mode `tests/e2e_application.py --lecture-seule --url <adresse>` vérifie les pages réelles dans un navigateur neuf, sans effectuer les scénarios d'écriture.

### 3. Copier la documentation vers le miroir configuré

Si le dossier miroir configuré dans `moteur/sauvegarder.py` existe, le script copie la documentation officielle et le `AGENTS.md` canonique. `AGENT.md` reste seulement le point d'entrée historique du projet.

L'absence du miroir est annoncée et n'empêche pas la sauvegarde principale. Une erreur de `robocopy` est signalée dans la sortie ; elle ne doit pas être interprétée comme une synchronisation réussie. Cette copie matérielle ne prouve aucune parité sémantique entre code et documentation : cette vérification appartient à la phase A.

### 4. Créer le commit et vérifier la publication

- La procédure automatique exige la branche locale `main`, avant toute indexation. Une branche différente ou une tête détachée entraîne un refus explicite.
- Après les contrôles de l'index privé, créer un commit uniquement si des changements sont indexés. Le message est transmis à Git par un fichier temporaire.
- Même si aucun nouveau commit n'est nécessaire, effectuer la publication demandée : un commit local antérieur peut encore attendre son envoi.
- Publier le `HEAD` vérifié vers `origin/refs/heads/main`, puis relire cette référence distante avec `git ls-remote`. Le hash distant doit correspondre au hash local complet.
- Avec `--sans-push`, conserver un résultat de sauvegarde locale et ne pas affirmer que GitHub est synchronisé.

### 5. Publier le résultat exact dans l'application

`moteur/dire.py` publie sous l'identité de le Leader le hash et le statut réellement obtenu : publication distante vérifiée ou sauvegarde locale seulement. Un échec est annoncé ; si cette annonce échoue aussi, le script le signale dans sa sortie d'erreur.

Cette annonce intervient après le commit et peut ajouter de nouvelles lignes aux carnets locaux de dialogue. Un arbre Git parfaitement propre après l'annonce n'est donc pas une condition de succès de la publication précédente.

## Options

| Commande | Résultat demandé |
|---|---|
| `py -3.14 -B moteur/sauvegarder.py` | Contrôles, commit si nécessaire, publication vérifiée et annonce |
| `py -3.14 -B moteur/sauvegarder.py --message "Correction documentée"` | Même procédure avec message de commit personnalisé |
| `py -3.14 -B moteur/sauvegarder.py --sans-push` | Contrôles, copie documentaire éventuelle, commit local et annonce locale |

## Relecture finale

Le Leader relit le code retour, le hash annoncé, le statut de publication et la réponse effectivement ajoutée dans l'application. Il vérifie séparément les avertissements de miroir et les modifications locales créées après le commit. Il ne présente ni un commit local comme un envoi distant, ni l'exclusion actuelle du courrier comme un nettoyage de l'historique GitHub.
