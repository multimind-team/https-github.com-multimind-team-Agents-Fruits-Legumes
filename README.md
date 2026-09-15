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

## Démarrage

- `demarrer-serveur.bat` gère le démarrage du serveur ; `arreter-serveur.bat` l’arrête.
- Application : <http://127.0.0.1:8751/app/index.html>.
- Lancement manuel au premier plan : `py -3.14 moteur/serveur.py 8751`.
- Sur téléphone ou tablette avec Tailscale actif : <https://desktop-11kv59v.tail44b4ba.ts.net/app/index.html>.

Le serveur écoute sur `127.0.0.1` ; l’adresse Wi-Fi du PC ne donne donc pas accès à l’application. Tailscale Serve relaie l’accès HTTPS vers le port local 8751. La commande `tailscale serve status` permet de vérifier ce relais. Le lanceur démarre aussi la surveillance du serveur ; il ne configure pas Tailscale.

La surveillance des entrées est distincte du serveur : `py -3.14 moteur/surveille-mail-message-comptage.py`.
Elle signale les événements de courrier, messages et comptages à un agent externe. Elle ne fournit pas de service IA autonome. Un message reçu peut rester en attente jusqu’au traitement par l’agent ; voir [la procédure courrier](procedures/courrier.md).

## Fonctionnement

1. L’agent courrier lit les sources et conserve leur provenance.
2. L’agent données simule le lot ; un agent contrôle distinct vérifie les lignes et la chronologie.
3. Après contrôles et autorisations applicables, les importeurs ajoutent les faits puis le filet de sécurité recalcule les sorties.
4. Le responsable consulte et ajuste la proposition, puis la recopie sur la tablette officielle. Aucun export EDI ni envoi automatique de commande n’est implémenté.

Les factures directes nécessitent une validation explicite ligne par ligne avant import de stock. La préparation du classeur Pomona peut se faire seule avec `--classeur-seul`. Son téléchargement est disponible dans l’application ; un courriel séparé exige un destinataire explicitement demandé.

## Fichiers utiles

| Dossier ou fichier | Rôle |
|---|---|
| [AGENTS.md](AGENTS.md) | Consigne canonique et autorisations |
| `agents/`, `procedures/`, `reference/` | Missions, procédures, contrats métier |
| `moteur/` | Importeurs, calculs, serveur et surveillance |
| `app/` | Accueil, commande, comptage, promotions et maintenance |
| `donnees/` | Sources et sorties métier ; les carnets JSONL se corrigent par ajout |
| `documents-partages/` | Classeurs et documents proposés au téléchargement |
| `tests/` | Contrôles syntaxiques, métier et navigateur |

[Documentation de l’application](Documents/Documentation%20de%20l%27application/index.html) : ouvrir le fichier local dans le navigateur. Le serveur de l’application ne publie pas le dossier `Documents/`.

## Tests et sauvegarde

Exécuter les tests dans une copie jetable protégée :

```powershell
py -3.14 -B tests/lancer_tests_isoles.py
```

Un fichier de test peut être fourni en argument pour une vérification ciblée. Les stocks et configurations réels ne doivent pas servir de cible d’essai.

Les parcours complets dans le navigateur passent également par cette protection : `py -3.14 -B tests/lancer_tests_isoles.py --navigateur --sortie <dossier-externe>`. Ils vérifient les six pages à plusieurs tailles ainsi que des comptages, ajustements et messages fictifs dans la copie.

La sauvegarde avec commit et synchronisation est une action explicite : `sauvegarder.bat` ou `/sauvegarde`. Lire [procedures/sauvegarde.md](procedures/sauvegarde.md) avant de l’exécuter. La mise à jour du code seule ne recalcule pas automatiquement les données métier.
