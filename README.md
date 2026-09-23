# Préparation de commande — fruits et légumes

Application locale du rayon fruits et légumes d’Intermarché Carmaux. Elle prépare une proposition, permet les comptages et laisse les décisions au responsable de rayon. La commande doit être recopiée et transmise dans l’outil officiel du magasin avant 9h30.

## Installation Windows

Environnement vérifié : Python 3.14 et Microsoft Edge. Les lectures Excel, les aperçus PDF et les photos exigent les dépendances du projet :

```powershell
py -3.14 -m pip install -r requirements.txt
```

Pour les tests navigateur :

```powershell
py -3.14 -m pip install -r requirements-dev.txt
```

Les tests utilisent Chromium disponible ou Microsoft Edge installé. Node.js sert aux vérifications JavaScript de certains tests.
Copier `.env.example` vers `.env`, puis renseigner localement les identifiants si le courrier est utilisé. `.env.example` est le modèle de configuration sans secret ; il doit être conservé. `.env` et les pièces jointes privées ne doivent pas être versionnés.
Un clonage Git ne fournit pas les secrets ni les pièces jointes exclues : leur reprise vient d’une sauvegarde privée autorisée.

## Services

| Composant | Action | Commande |
|---|---|---|
| **Serveur Web Applicatif** (mobile/PC) | Démarrer | `demarrer-serveur.bat` |
| | Arrêter | `arreter-serveur.bat` |
| | État | `py -3.14 -B moteur/gerer-serveur.py etat` |
| **Tri-Sentinelle** (mails, messages, comptages) | Démarrer | `demarrer-sentinelle.bat` |
| | Arrêter | `arreter-sentinelle.bat` |

Le serveur web et la sentinelle sont strictement découplés pour garantir la haute disponibilité mobile :
- **Serveur Web :** tourne en tâche de fond permanente (daemon). Il maintient le serveur HTTP local et sa surveillance de processus active, permettant au responsable de rayon d'accéder à l'application sur son téléphone à tout instant sans risque de coupure.
- **Tri-Sentinelle :** surveille la boîte aux lettres IMAP, les messages du rayon et les comptages. Lorsqu'un événement survient, elle affiche `EVENEMENT: MAIL`, `MESSAGE` ou `COMPTAGE` et se termine pour réveiller le Leader. Sa fin n'affecte en aucun cas le serveur web.

- Application locale : <http://127.0.0.1:8751/app/index.html>.
- Sur téléphone ou tablette avec Tailscale actif : <https://desktop-11kv59v.tail44b4ba.ts.net/app/index.html>.

Le serveur écoute sur `127.0.0.1` ; l’adresse Wi-Fi du PC ne donne donc pas accès direct à l’application. Tailscale Serve relaie l’accès HTTPS vers le port local 8751. La commande `tailscale serve status` permet de vérifier ce relais.

Pour un agent, lancer le serveur avec `py -3.14 -B moteur/gerer-serveur.py demarrer` (processus daemon d'arrière-plan persistant) et la sentinelle séparément avec `py -3.14 -B moteur/surveille-mail-message-comptage.py`. Aucun traitement métier n’est déclenché par ces commandes : voir [la procédure courrier](procedures/courrier.md).

## Fonctionnement

1. L’agent courrier lit les sources et conserve leur provenance.
2. L’agent données simule le lot ; un agent contrôle distinct vérifie les lignes et la chronologie.
3. Après contrôles et autorisations applicables, les importeurs ajoutent les faits puis le filet de sécurité recalcule les sorties.
4. La proposition algorithmique initiale du jour est archivée immuablement dans `donnees/propositions/proposition-AAAA-MM-JJ.json`.
5. Le responsable consulte et ajuste la proposition sur l'écran `app/commander.html`. Ses modifications sont synchronisées en temps réel vers `POST /api/ajustements-commande` et enregistrées dans `donnees/ajustements.jsonl` ainsi que dans le carnet d'entraînement pour les futures IA `donnees/entrainement-ajustements.jsonl` (Contrat CP-04) avec le contexte décisionnel complet (météo, stock, demande, PCB, marges, motifs).
6. Le responsable recopie la commande finale sur la tablette officielle du magasin. Aucun export EDI ni envoi automatique de commande n’est implémenté.

Les factures directes nécessitent une validation explicite ligne par ligne avant import de stock. La préparation du classeur Pomona peut se faire seule avec `--classeur-seul`. Son téléchargement est disponible dans l’application ; un courriel séparé exige un destinataire explicitement demandé.

## Fichiers utiles

| Dossier ou fichier | Rôle |
|---|---|
| [AGENTS.md](AGENTS.md) | Consigne canonique et autorisations |
| `agents/`, `procedures/`, `reference/` | Missions, procédures, contrats métier |
| `moteur/` | Importeurs, calculs, serveur, surveillance et enregistrement d'ajustements (`enregistrer_modifications_commande.py`) |
| `app/` | Accueil, commande, comptage, promotions et maintenance |
| `donnees/` | Sources et sorties métier ; les carnets JSONL se corrigent par ajout |
| `donnees/propositions/` | Archives immuables des propositions algorithmiques de base (`proposition-AAAA-MM-JJ.json`) |
| `donnees/entrainement-ajustements.jsonl` | Exemples d'entraînement supervisé pour les futures IA (Contrat CP-04) |
| `documents-partages/` | Classeurs et documents proposés au téléchargement |
| `tests/` | Contrôles syntaxiques, métier et navigateur |

[Documentation de l’application](Documents/Documentation%20de%20l%27application/index.html) : ouvrir le fichier local dans le navigateur. Le serveur de l’application ne publie pas le dossier `Documents/`.

[Fonctionnement en images](Documents/Documentation%20de%20l%27application/schema-fonctionnement.html) : animation de 19 scènes, avec lecture, pause et navigation par sujet. Courrier, agents, comptages, commande et protections sont expliqués une étape à la fois, sans action sur les données. Le [document détaillé](Documents/Documentation%20de%20l%27application/schema-fonctionnement-detaille.html) conserve les règles, les sources du code et leurs limites.

[Vidéo des échanges entre agents](Documents/Documentation%20de%20l%27application/video-interactions-agents.html) : film illustré avec narration française, sous-titres et accès par chapitre. Il explique les transmissions de missions, les contrôles, les réponses au rayon et le retour à l'écoute.

## Tests et sauvegarde

Exécuter les tests dans une copie jetable protégée :

```powershell
py -3.14 -B tests/lancer_tests_isoles.py
```

Un fichier de test peut être fourni en argument pour une vérification ciblée. Les stocks et configurations réels ne doivent pas servir de cible d’essai.

Les parcours complets dans le navigateur passent également par cette protection : `py -3.14 -B tests/lancer_tests_isoles.py --navigateur --sortie <dossier-externe>`. Ils vérifient les six pages à plusieurs tailles ainsi que des comptages, ajustements et messages fictifs dans la copie.

La sauvegarde avec commit et synchronisation est une action explicite : `sauvegarder.bat` ou `/sauvegarde`. Lire [procedures/sauvegarde.md](procedures/sauvegarde.md) avant de l’exécuter. La mise à jour du code seule ne recalcule pas automatiquement les données métier.
