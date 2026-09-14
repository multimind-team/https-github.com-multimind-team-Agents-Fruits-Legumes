# RAPPORT D'ANOMALIES DÉTAILLÉ ET PLAN D'AMÉLIORATION
## Rayon Fruits & Légumes — Intermarché Carmaux (PDV 11768)
**Projet :** `C:\Users\user\Desktop\preparation-commande` (Architecture Hermes)  
**Date du rapport :** 11 septembre 2026  
**Auteur :** Antigravity (Assistant d'Ingénierie IA)  
**Périmètre de l'audit :** Moteur prévisionnel, serveur HTTP, scripts batch, suite de tests (352 tests), intégrité des données (141 710 lignes)  
**Contrainte respectée :** Audit strictement passif — Aucune donnée métier modifiée (`donnees/` intact)

---

## 1. Contexte et Synthèse de l'Audit

Le projet de préparation de commande assistée par IA a pour mission critique de calculer chaque matin avant 9h30 les propositions de réapprovisionnement du rayon fruits et légumes d'Intermarché Carmaux. 

La version actuelle (architecture **Hermes** du 10-11 septembre 2026) présente un niveau de maturité technique nettement supérieur aux versions antérieures :
- **Intégrité des stocks sécurisée :** Le mode d'enregistrement des comptages dans `donnees/comptages.jsonl` est désormais en ajout strict (*append-only* avec déduplication et vérification temporelle). L'ancien écrasement destructif de fichier a été totalement éliminé.
- **Sécurité HTTP renforcée :** Le serveur local `moteur/serveur.py` applique une liste blanche stricte (`DONNEES_PUBLIQUES`, `APP_PUBLIQUE`), bloque le *path traversal* (`..`) et vérifie la taille des requêtes entrantes.
- **Zéro erreur de syntaxe :** Le script de contrôle global `tests/verifier_projet.py` a validé 141 710 lignes sans aucune anomalie de syntaxe.
- **Taux de passage des tests :** 350 tests sur 352 sont passés avec succès (les 2 échecs sont purement liés à l'encodage CP1252/UTF-8 de la console Windows sous `subprocess`).
- **Précision globale :** L'évaluation prévisionnelle rétrospective sur 34 323 points réels (`moteur/evaluer-prevision.py`) révèle un biais de +6,1 %, ce qui témoigne d'une politique prudente (légère sur-commande protectrice pour éviter la rupture).

Cependant, l'audit approfondi a mis au jour **11 anomalies et axes d'amélioration**, dont **2 biais algorithmiques substantiels** dans la prise en compte des vacances scolaires et des jours fériés, susceptibles de provoquer des ruptures de stock critiques lors des périodes de fête ou de grand départ.

---

## 2. Tableau Récapitulatif des 11 Anomalies Identifiées

| Réf. | Sévérité | Domaine | Composant / Fichier | Résumé de l'Anomalie |
|---|---|---|---|---|
| **ANO-01** | **Moyenne** | Métier / Algorithme | `moteur/generer-proposition.py` (L.250-254) | Facteur vacances calculé avec `min()` : écrase les hausses de vente lors des départs et fêtes (Noël +16,2 %). |
| **ANO-02** | **Moyenne** | Métier / Algorithme | `moteur/generer-proposition.py` (L.244-248) | Facteur férié calculé avec `min()` : réduit de moitié les ventes estimées d'un jour ouvré normal si le lendemain est férié matin. |
| **ANO-03** | **Faible** | Métier / Algorithme | `moteur/generer-proposition.py` (L.262) | Facteur météo calculé uniquement sur la date de livraison et répercuté à tort sur la consommation d'aujourd'hui. |
| **ANO-04** | **Moyenne** | Tests / Intégration | `tests/test_colisage_chaine.py` (L.78) & `tests/test_correction_conversion_comptage.py` (L.245) | 2 tests en échec sous Windows : omission de `PYTHONIOENCODING="utf-8"` lors des appels `subprocess.run`. |
| **ANO-05** | **Faible** | Robustesse / Batch | `moteur/preparer-liste-comptage.py` (L.89) & `moteur/filet-de-securite.py` (L.122) | Dépendance directe à `date.today()` : empêche la simulation et le rejeu de dates passées en mode batch. |
| **ANO-06** | **Faible** | Portabilité Windows | `demarrer-serveur.bat` (L.8) & `verifier-avant-commande.bat` (L.24) | Appel figé `py -3.14` : échec immédiat si Python 3.12, 3.13 ou un environnement virtuel est utilisé. |
| **ANO-07** | **Ergonomie** | Journalisation | `moteur/integrer-fichiers.py` (L.331-344) | Fausse alerte critique "Livraison absente" lors de la réception normale et asynchrone des ventes de l'après-midi. |
| **ANO-08** | **Hygiène Dépôt** | Documentation | Racine (`AGENT.md` vs `AGENTS.md`) | Coexistence confuse de deux fichiers de cadrage d'orchestration (`AGENT.md` canonique vs `AGENTS.md` reliquat). |
| **ANO-09** | **Hygiène Dépôt** | Nettoyage | Répertoire `roles/` et fichiers orphelins | Dossier vide `roles/`, fichiers `travaux.jsonl` et `a-voir.jsonl` de 0 octet issus de l'ancien polling. |
| **ANO-10** | **Maintenance** | Dépendances | `moteur/promotions.py` & `preparer-apercus-promotion.py` | Import déprécié `import fitz` générant des avertissements dans la console sous PyMuPDF récent. |
| **ANO-11** | **Métier / Précision** | Paramétrage | `moteur/evaluer-prevision.py` & règles de stock | Biais de sur-commande systématique (+6,1 %) constaté sur 34 323 prévisions historiques. |

---

## 3. Fiches Détaillées des Anomalies et Solutions Techniques

---

### FICHE ANO-01 — Biais de calcul : `min()` sur les facteurs de vacances scolaires
- **Gravité :** Moyenne (Impact direct sur le chiffre d'affaires et la disponibilité en rayon)
- **Localisation :** `moteur/generer-proposition.py`, lignes 250-254
- **Code actuel :**
  ```python
  if cal:
      f_vac = min(
          facteur_vacances(date_commande, cal),
          facteur_vacances(date_livraison, cal),
      )
      moy_cmd *= f_vac
      moy_liv *= f_vac
  ```
- **Mécanisme de l'anomalie :**
  Le coefficient multiplicateur des vacances scolaires applique une variation basée sur l'historique saisonnier (par exemple : Noël $= 1,162$ soit $+16,2\,\%$, vacances d'été $= 0,95$, etc.).
  En prenant le minimum `min(facteur(date_commande), facteur(date_livraison))` :
  - Si la commande est passée le vendredi avant les vacances scolaires (`date_commande` en période normale $= 1,0$) pour être livrée le samedi matin, premier jour des départs (`date_livraison` en vacances $= 1,162$) : `min(1.0, 1.162) = 1.0`.
  - **Conséquence directe :** La hausse de fréquentation massive de $+16,2\,\%$ attendue pour le samedi est intégralement écrasée et ramenée à zéro. Le rayon ne commande pas assez et subit une rupture de stock dès le premier jour des vacances.
  - À l'inverse, lors d'un départ de pont (ex. Ascension $= 0,90$), le `min(1.0, 0.90) = 0.90` vient injustement pénaliser les ventes du jour de commande ouvré.
- **Solution technique recommandée :**
  Appliquer à chaque jour son propre coefficient de vacances scolaires :
  ```python
  if cal:
      moy_cmd *= facteur_vacances(date_commande, cal)
      moy_liv *= facteur_vacances(date_livraison, cal)
  ```
- **Protocole de validation :**
  Créer un test unitaire simulant une commande passée le 19 décembre pour livraison le 20 décembre (période de Noël). Vérifier que `moy_liv` augmente bien de $+16,2\,\%$ et que `moy_cmd` reste à $1,0$.

---

### FICHE ANO-02 — Biais de calcul : `min()` sur les facteurs de jours fériés
- **Gravité :** Moyenne (Risque de rupture sévère la veille d'un jour férié)
- **Localisation :** `moteur/generer-proposition.py`, lignes 244-248
- **Code actuel :**
  ```python
  if ferie:
      f_ferie = min(ferie.facteur(date_commande), ferie.facteur(date_livraison))
      moy_cmd *= f_ferie
      moy_liv *= f_ferie
  ```
- **Mécanisme de l'anomalie :**
  Le module `ferie` renvoie le coefficient d'ouverture et d'activité du magasin (ex. $1,0$ en journée normale, $0,54$ pour un jour férié ouvert uniquement la matinée, $0,0$ pour un jour férié fermé).
  Si l'on commande un jour ordinaire ($J$, facteur $1,0$) pour une livraison le matin d'un jour férié ($J+1$, facteur $0,54$) :
  - Le `min(1.0, 0.54)` vaut $0,54$.
  - Ce facteur est appliqué à la fois sur `moy_liv` et sur `moy_cmd`.
  - **Conséquence directe :** La consommation estimée pour la journée en cours (`moy_cmd`) est divisée par deux ! L'algorithme suppose que les clients n'achèteront presque rien aujourd'hui en magasin, alors qu'il s'agit d'un jour normal de forte affluence (les clients faisant souvent leurs courses avant le jour férié). Le stock de sécurité est faussé et la commande est sous-évaluée.
- **Solution technique recommandée :**
  Décorréler strictement le facteur d'activité fériée de chaque date :
  ```python
  if ferie:
      moy_cmd *= ferie.facteur(date_commande)
      moy_liv *= ferie.facteur(date_livraison)
  ```
- **Protocole de validation :**
  Tester la commande passée le 13 juillet (jour plein) pour le 14 juillet (férié matin). Vérifier que `moy_cmd` conserve un coefficient de $1,0$ et que seul `moy_liv` est modulé à $0,54$.

---

### FICHE ANO-03 — Facteur météo calculé uniquement sur la date de livraison
- **Gravité :** Faible (Perturbation mineure des articles thermosensibles)
- **Localisation :** `moteur/generer-proposition.py`, ligne 262
- **Code actuel :**
  ```python
  if meteo_prev:
      f_meteo = facteur_meteo(article_code, date_livraison, meteo_prev)
      moy_cmd *= f_meteo
      moy_liv *= f_meteo
  ```
- **Mécanisme de l'anomalie :**
  Le modèle prévoit la météo de demain (`date_livraison`) et applique ce coefficient unique à la fois sur les ventes estimées d'aujourd'hui (`moy_cmd`) et celles de demain (`moy_liv`).
  S'il fait 30°C et grand soleil aujourd'hui (forte demande de pastèques, concombres, tomates) mais qu'un orage violent est annoncé demain (facteur $0,75$) : la prévision de vente d'aujourd'hui est réduite de $25\,\%$, faussant l'évaluation du stock restant ce soir.
- **Solution technique recommandée :**
  Calculer et appliquer le facteur météo spécifique à chaque date :
  ```python
  if meteo_prev:
      moy_cmd *= facteur_meteo(article_code, date_commande, meteo_prev)
      moy_liv *= facteur_meteo(article_code, date_livraison, meteo_prev)
  ```

---

### FICHE ANO-04 — 2 tests unitaires en échec sous Windows (Subprocess UTF-8)
- **Gravité :** Moyenne (Bloque l'intégration continue et génère de faux négatifs)
- **Localisation :**
  - `tests/test_correction_conversion_comptage.py`, ligne 245
  - `tests/test_colisage_chaine.py`, ligne 78
- **Constat d'échec :**
  Lors de l'exécution de `python -m unittest discover -s tests -p "test_*.py"` (352 tests) :
  1. `test_correction_conversion_comptage.py` :
     ```python
     resultat = subprocess.run(commande, capture_output=True)
     sortie = json.loads(resultat.stdout.decode("utf-8"))
     ```
     L'appel ligne 245 omet `env={"PYTHONIOENCODING": "utf-8"}` (contrairement à la méthode `self.lancer()` définie plus haut dans la classe). Dès qu'un libellé contient un accent (`è` = `0xe8`), Python sous Windows console émet en CP1252, causant :
     `UnicodeDecodeError: 'utf-8' codec can't decode byte 0xe8 in position 494: invalid start byte`.
  2. `test_colisage_chaine.py` :
     L'utilisation de `text=True, encoding='utf-8'` sans forcer la sortie du script enfant plante le thread de lecture interne de Python (`_readerthread`), laissant `resultat.stdout = None` et provoquant :
     `TypeError: unsupported operand type(s) for +: 'NoneType' and 'str'`.
- **Solution technique recommandée :**
  1. Dans `tests/test_correction_conversion_comptage.py` (L.245), réutiliser systématiquement `self.lancer(commande)` ou injecter l'environnement :
     ```python
     env = os.environ.copy()
     env["PYTHONIOENCODING"] = "utf-8"
     resultat = subprocess.run(commande, capture_output=True, env=env)
     sortie = json.loads(resultat.stdout.decode("utf-8", errors="replace"))
     ```
  2. Dans `tests/test_colisage_chaine.py` (L.78), ajouter `errors="replace"` et `env` avec `PYTHONIOENCODING="utf-8"`.
- **Protocole de validation :**
  Exécuter `python -m unittest discover -s tests -p "test_*.py"` sous Windows PowerShell et s'assurer d'obtenir `Ran 352 tests in ...s - OK`.

---

### FICHE ANO-05 — Dépendance directe à `date.today()` dans les scripts batch
- **Gravité :** Faible (Limite la testabilité et les rattrapages historiques)
- **Localisation :**
  - `moteur/preparer-liste-comptage.py`, lignes 89-96
  - `moteur/filet-de-securite.py`, ligne 122 (`hier = (date.today() - timedelta(days=1)).isoformat()`)
- **Mécanisme de l'anomalie :**
  Dans `preparer-liste-comptage.py`, le script estime le stock théorique en boucle jusqu'à `date.today()` :
  ```python
  aujourdhui = date.today()
  d = dernier + timedelta(days=1)
  while d <= aujourdhui:
      ...
  ```
  Si des fichiers sont rejoués le lendemain matin ou lors d'une simulation sur des données historiques, le script déduit des jours de vente inexistants entre la date des données et la date de l'horloge système.
- **Solution technique recommandée :**
  Ajouter un argument `--date AAAA-MM-JJ` en ligne de commande :
  ```python
  parser.add_argument("--date", help="Date de référence (par défaut aujourd'hui)", default=None)
  # ...
  ref_date = date.fromisoformat(args.date) if args.date else date.today()
  ```

---

### FICHE ANO-06 — Commande figée `py -3.14` dans les scripts `.bat`
- **Gravité :** Faible (Défaut de portabilité)
- **Localisation :**
  - `demarrer-serveur.bat`, ligne 8 : `py -3.14 moteur\gerer-serveur.py demarrer`
  - `verifier-avant-commande.bat`, ligne 24 : `py -3.14 moteur\filet-de-securite.py --verifier`
- **Mécanisme de l'anomalie :**
  L'option `-3.14` exige spécifiquement que la version Python 3.14 soit installée et enregistrée auprès du lanceur `py.exe`. Si le poste du magasin ou du développeur tourne sous Python 3.12, Python 3.13 ou dans un environnement virtuel local (`.venv`), les scripts `.bat` échouent immédiatement avec :
  `Requested Python version (3.14) is not installed`.
- **Solution technique recommandée :**
  Remplacer par un appel universel qui essaie `python`, puis `py` en secours :
  ```bat
  python moteur\gerer-serveur.py demarrer 2>NUL || py -3 moteur\gerer-serveur.py demarrer
  ```

---

### FICHE ANO-07 — Alarme critique "Livraison absente" lors de la réception normale des ventes
- **Gravité :** Ergonomie / Bruit opérationnel
- **Localisation :** `moteur/integrer-fichiers.py`, lignes 331-344
- **Mécanisme de l'anomalie :**
  Dans le magasin, les flux arrivent de manière asynchrone :
  1. Le matin à 06h00 : les bordereaux de livraison du jour.
  2. L'après-midi à 15h00 : le fichier Excel des ventes de la veille.
  Lorsque la sentinelle traite le courrier de 15h00 contenant uniquement les ventes, `integrer-fichiers.py` constate qu'aucun fichier de livraison n'est présent dans le dossier temporaire. Il déclenche alors :
  `fichier-absent : ATTENTION: Aucun fichier livraison trouvé`.
  Cette alarme de sévérité élevée sème le doute chez l'opérateur et a conduit l'agent IA à devoir inscrire manuellement des messages de réassurance dans `donnees/reponses.jsonl` (lignes 26 et 28 : *"Pas de panique : la sentinelle a reçu uniquement les ventes d'hier..."*).
- **Solution technique recommandée :**
  Ne qualifier l'absence de livraison d'anomalie bloquante que lors du contrôle matinal d'avant-commande (`verifier-avant-commande.bat`), et transformer l'alerte d'intégration en simple message d'information `[INFO]` si au moins un fichier valide (de vente) a été traité.

---

### FICHE ANO-08 — Doublon documentaire à la racine (`AGENT.md` vs `AGENTS.md`)
- **Gravité :** Hygiène Dépôt
- **Localisation :** Racine du projet
- **Constat :**
  Deux fichiers aux noms presque identiques coexistent :
  - `AGENT.md` (17,6 Ko, daté du 10/09) : C'est la véritable consigne canonique et exhaustive régissant l'orchestration du projet avec Hermes.
  - `AGENTS.md` (5,0 Ko) : Reliquat décrivant l'ancienne architecture multi-rôles dépréciée (coordinateur, préparateur, contrôleur, etc.). Ce fichier indique d'ailleurs lui-même en ligne 2 : *"La vraie consigne d'orchestration est dans AGENT.md"*.
  Cette coexistence crée une ambiguïté pour les agents autonomes ou les collaborateurs arrivant sur le projet.
- **Solution technique recommandée :**
  Archiver `AGENTS.md` sous `docs/archive/ANCIEN_AGENTS_MULTI_ROLES.md` ou le supprimer, afin que `AGENT.md` demeure l'unique point d'entrée documenté du système.

---

### FICHE ANO-09 — Dossiers et fichiers JSONL orphelins
- **Gravité :** Hygiène Dépôt
- **Constat :**
  - Le répertoire `roles/` existe toujours sur le disque mais est vide.
  - Les fichiers `donnees/travaux.jsonl` (0 octet) et `donnees/courrier/a-voir.jsonl` (0 octet) étaient les files de polling de l'ancienne version. Avec Hermes, les emails sont inspectés directement dans `donnees/courrier/`.
  - Des fichiers verrous résiduels (`.gestion-serveur.lock`, `.surveillance-serveur.lock`, `.serveur-arrete`) et un fichier parasite `NUL` (48 octets) sont présents à la racine.
- **Solution technique recommandée :**
  Supprimer le dossier vide `roles/`, archiver les fichiers JSONL vides de 0 octet et nettoyer les fichiers verrous inactifs.

---

### FICHE ANO-10 — Dépréciation de l'import `fitz` (PyMuPDF)
- **Gravité :** Maintenance
- **Localisation :** `moteur/promotions.py` et `moteur/preparer-apercus-promotion.py`
- **Constat :**
  L'import `import fitz` déclenche un message d'avertissement récurrent sous les versions récentes de la bibliothèque :
  `DeprecationWarning: PyMuPDF: import fitz is deprecated, please use import pymupdf`.
- **Solution technique recommandée :**
  Remplacer par :
  ```python
  import pymupdf as fitz
  ```
  Cela supprime les messages d'avertissement tout en maintenant la rétrocompatibilité complète avec le code existant utilisant `fitz`.

---

### FICHE ANO-11 — Biais de sur-commande globale (+6,1 %)
- **Gravité :** Optimisation Métier (Sur-stockage / Risque de freinte et démarque inconnue)
- **Localisation :** Évaluation globale `moteur/evaluer-prevision.py`
- **Constat statistique sur 34 323 points de vente :**
  - Total des ventes constatées : **107 794 kg**
  - Total des commandes proposées par le calcul : **114 357 kg**
  - Biais global : **+6,1 %**
  - Répartition des écarts : **45,8 % de sur-commande** vs **31,4 % de sous-commande**.
  Ce biais positif est volontairement orienté pour éviter les ruptures, mais sur les fruits fragiles (fraises, framboises, salades), une sur-commande de 6 % engendre une augmentation directe de la casse (perte financière).
- **Solution technique recommandée :**
  1. Corriger d'abord les anomalies de calendrier `ANO-01` et `ANO-02`.
  2. Ajuster finement les marges de sécurité par famille de produits dans `donnees/articles.json` : réduire le tampon de sécurité sur les produits ultra-frais à rotation rapide (durée de vie < 2 jours) et le maintenir sur les produits de garde (pommes de terre, agrumes, oignons).
  3. Relancer `evaluer-prevision.py` pour mesurer le gain sur la démarque.

---

## 4. Plan de Déploiement Conseillé (Par Ordre de Priorité)

### Phase 1 : Correctifs Immédiats (Algorithme de Commande)
- [ ] **Corriger `ANO-01` et `ANO-02`** dans `moteur/generer-proposition.py` (suppression du `min()` sur les facteurs vacances et fériés).
- [ ] **Corriger `ANO-03`** dans `moteur/generer-proposition.py` (séparation de la météo pour la commande et la livraison).

### Phase 2 : Fiabilisation des Tests et des Scripts d'Exploitation
- [ ] **Corriger `ANO-04`** dans `tests/test_colisage_chaine.py` et `tests/test_correction_conversion_comptage.py` pour atteindre 352/352 tests réussis sous Windows.
- [ ] **Corriger `ANO-06`** dans `demarrer-serveur.bat` et `verifier-avant-commande.bat` pour rendre les lanceurs compatibles toute version Python.
- [ ] **Corriger `ANO-05`** en ajoutant l'argument optionnel `--date` aux scripts de comptage et de vérification.

### Phase 3 : Confort Opérationnel et Maintenance du Dépôt
- [ ] **Corriger `ANO-07`** dans `moteur/integrer-fichiers.py` pour éliminer les fausses alertes d'absence de livraison.
- [ ] **Corriger `ANO-10`** dans les scripts de promotions (`import pymupdf as fitz`).
- [ ] **Traiter `ANO-08` et `ANO-09`** : archiver `AGENTS.md`, supprimer le dossier `roles/` vide et nettoyer les fichiers temporaires résiduels.
