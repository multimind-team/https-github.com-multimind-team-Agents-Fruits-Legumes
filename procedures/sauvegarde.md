# Procédure de Sauvegarde et Synchronisation GitHub (/sauvegarde)

## 1. Contexte et Objectif

La commande `/sauvegarde` est le protocole officiel de sauvegarde, de contrôle de cohérence et de synchronisation du système complet sur GitHub.

Elle garantit que l'ensemble du travail (code moteur, carnets de données, documentation officielle des 23 chapitres, règles métier, photos produits optimisées) est pérennisé sur le dépôt distant sans **aucun risque de fuite de secrets ou de données personnelles sensibles**.

---

## 2. Déclenchement

La procédure est déclenchée :
- À la demande explicite de l'utilisateur (commande `/sauvegarde`, « sauvegarde », ou « fais une sauvegarde »).
- Après chaque cycle majeur d'intégration ou d'évolution du système.
- Avant toute intervention structurelle sur le code ou les carnets.

---

## 3. Répartition des rôles : L'IA rédige, le script exécute

Un script Python ne peut pas « inventer » ou rédiger intelligemment de la documentation technique : il ne comprend pas le sens des règles métier ajoutées ni la portée des modifications de code.

La commande `/sauvegarde` repose donc sur une collaboration stricte en deux phases :

```
[Utilisateur tape /sauvegarde]
          │
          ▼
┌─────────────────────────────────────────────────────────────┐
│ PHASE A : L'IA (Agent Orchestrateur / Rédacteur)            │
│ 1. Analyse les modifications récentes (git status, diff).   │
│ 2. Rédige et met à jour les fichiers .md (agents, proc).    │
│ 3. Met à jour les fiches HTML de la Documentation officielle│
│    (23 chapitres) selon les nouveautés fonctionnelles.      │
└─────────────────────────────────────────────────────────────┘
          │
          ▼ (Une fois la doc rédigée par l'IA)
┌─────────────────────────────────────────────────────────────┐
│ PHASE B : Le script technique (moteur/sauvegarder.py)       │
│ 1. Contrôle de sécurité (anti-fuite secrets .env).          │
│ 2. Contrôle de conformité syntaxique et tests unitaires.    │
│ 3. Synchronisation physique vers le miroir secondaire.      │
│ 4. Git add, commit structuré et git push origin main.       │
│ 5. Publication de la confirmation dans le chat web.         │
└─────────────────────────────────────────────────────────────┘
```

---

## 4. Étapes exécutées par la chaîne technique (sauvegarder.py)

Le script `moteur/sauvegarder.py` applique automatiquement un protocole rigoureux en 5 étapes successives :

### Étape 1 : Contrôle strict anti-fuite de secrets (Sécurité absolue)
- Vérifie que le fichier `.env` est **strictement exclu** par `.gitignore` (`git check-ignore .env`).
- Vérifie que le mot de passe Gmail dans `donnees/courrier-config.json` est **totalement vide** (`"mot_de_passe": ""`). Tout mot de passe doit résider exclusivement dans le fichier `.env` local.
- Vérifie que le dossier des pièces jointes brutes reçues par courrier (`donnees/courrier/`) est **strictement exclu** par `.gitignore` afin de ne pas versionner des centaines de mégaoctets de photos brutes ou d'adresses email.
- **En cas d'anomalie :** interruption immédiate, aucun commit n'est créé.

### Étape 2 : Contrôle d'intégrité et tests de non-régression
- Lance l'audit d'intégrité complet `tests/verifier_projet.py` : vérification syntaxique Python (`ast`), intégrité stricte des fichiers JSON et carnets JSONL (plus de 140 000 lignes de faits certifiées).
- Lance la suite de tests unitaires clés (`tests/test_preparer_photos.py`, `tests/test_envoyer_classeur_marge.py`).
- **En cas d'erreur de syntaxe ou de test unitaire :** arrêt immédiat avec rapport d'erreur.

### Étape 3 : Synchronisation de la documentation officielle
- Synchronise les fichiers de la documentation officielle (`Documents/Documentation de l'application/`) et les directives `AGENT.md` / `AGENTS.md` vers l'espace miroir si présent.
- Garantit la parité exacte entre le référentiel documentaire et le code en production.

### Étape 4 : Indexation Git, Commit et Push
- Exécute `git add -A` (en respectant les exclusions de `.gitignore`).
- Analyse le statut de l'arbre de travail :
  - Si aucune modification n'est détectée : confirme l'état à jour sans créer de commit inutile.
  - Si des modifications existent : génère un commit explicite et horodaté, puis effectue un `git push origin main`.

### Étape 5 : Annonce dans l'application web
- Publie une confirmation lisible dans le flux d'activité de l'application web via `moteur/dire.py` sous l'identité de l'**Agent Orchestrateur**, précisant le hash du commit et le statut de publication.

---

## 5. Options du script

| Commande | Description |
|---|---|
| `python moteur/sauvegarder.py` | Sauvegarde complète standard (contrôles + commit + push + annonce web) |
| `python moteur/sauvegarder.py --message "feat: mise à jour X"` | Sauvegarde avec message de commit personnalisé |
| `python moteur/sauvegarder.py --sans-push` | Exécute les contrôles, la synchronisation et le commit local sans pousser sur GitHub |

---

## 6. Vérification après sauvegarde

Après l'exécution, l'Agent Orchestrateur vérifie :
1. Que le message de succès s'affiche avec le hash du commit.
2. Que `git status` indique : *« Your branch is up to date with 'origin/main'. nothing to commit, working tree clean »*.
3. Que l'annonce apparaît bien dans le journal de l'application web.
