# RAPPORT D'AUDIT TECHNIQUE ET MÉTIER APPROFONDI
## Projet : Préparation de Commande Fruits & Légumes (Architecture Hermes)
**Emplacement audité :** `C:\Users\user\Desktop\preparation-commande`  
**Date d'audit :** 11 septembre 2026  
**Statut de l'audit :** Conforme aux consignes strictes — Aucune modification des données de production (`donnees/`)

---

## 1. Synthèse Exécutive

Le projet `preparation-commande` (version Hermes du 10-11 septembre 2026) constitue une évolution majeure et nettement consolidée par rapport aux versions initiales :
- **Corrections antérieures confirmées** : La faille critique de réécriture destructive des comptages (`comptages.jsonl`) a été corrigée en basculant sur un mode d'ajout strict (*append-only* avec déduplication en mémoire). Le serveur HTTP (`serveur.py`) dispose désormais de contrôles de sécurité stricts (whitelist de fichiers autorisés, rejet du path traversal `..`, limitation `Content-Length`).
- **Fiabilité générale** : L'outil d'intégrité globale `tests/verifier_projet.py` a validé **141 710 lignes de code et de données sans aucune erreur de syntaxe**.
- **Couverture de tests** : Sur **352 tests unitaires et fonctionnels**, **350 ont réussi**. Les 2 seuls échecs constatés sont liés au décodage des caractères accentués sous Windows dans les sous-processus de test, et non à une défaillance de la logique métier.
- **Performance prévisionnelle** : L'évaluation sur **34 323 points de vente réels** (`evaluer-prevision.py`) montre un biais global de **+6,1 %** (légère sur-commande protectrice pour éviter la rupture en rayon).

Cependant, l'audit approfondi a mis en lumière **trois incohérences algorithmiques dans le calcul prévisionnel** (gestion des vacances scolaires, des jours fériés et de la météo) ainsi que plusieurs fragilités de portabilité et résidus architecturaux qui méritent d'être corrigés.

---

## 2. Tableau Récapitulatif des Anomalies et Axes d'Amélioration

| Identifiant | Sévérité | Composant / Fichier | Nature de l'anomalie | Impact Métier / Technique |
|---|---|---|---|---|
| **ANO-H01** | **Moyenne** | `moteur/generer-proposition.py` (L.250-254) | Biais de calcul : `min()` sur les facteurs de vacances scolaires | Écrase les pics de vente festifs (ex. Noël +16,2 %) si la commande précède le début des vacances. |
| **ANO-H02** | **Moyenne** | `moteur/generer-proposition.py` (L.244-248) | Biais de calcul : `min()` sur les facteurs fériés appliqué aux 2 jours | Réduit artificiellement la demande d'un jour normal si le lendemain de livraison est férié (ou demi-journée). |
| **ANO-H03** | **Faible** | `moteur/generer-proposition.py` (L.262) | Facteur météo calculé uniquement sur la date de livraison | Ignore les conditions météo du jour de commande pour la période $J \to J+1$. |
| **ANO-H04** | **Faible** | `tests/test_colisage_chaine.py` & `tests/test_correction_conversion_comptage.py` | 2 tests en échec sous Windows (encodage UTF-8 subprocess) | Faux échecs de tests dus aux caractères accentués (`0xe9`, `0xe8`) sous Windows CP1252. |
| **ANO-H05** | **Faible** | `moteur/preparer-liste-comptage.py` & `filet-de-securite.py` | Dérive temporelle liée à l'utilisation directe de `date.today()` | Impossibilité de rejouer ou tester fidèlement des scénarios passés en mode batch. |
| **ANO-H06** | **Faible** | `demarrer-serveur.bat` & `verifier-avant-commande.bat` | Commande rigide `py -3.14` dans les fichiers `.bat` | Échec de lancement sur les environnements disposant de Python 3.11, 3.12 ou d'un environnement virtuel `venv`. |
| **ANO-H07** | **Nettoyage** | Racine du projet (`AGENT.md` vs `AGENTS.md`) | Doublon de documentation d'orchestration | Confusion possible entre le prompt canonique (`AGENT.md`) et le résumé déprécié (`AGENTS.md`). |
| **ANO-H08** | **Nettoyage** | Répertoire `roles/` et fichiers `.jsonl` orphelins | Fichiers résiduels de l'ancienne architecture pré-Hermes | Dossier `roles/` vide, `travaux.jsonl` et `a-voir.jsonl` vides mais persistants. |
| **ANO-H09** | **Ergonomie** | `moteur/integrer-fichiers.py` (L.331-344) | Fausse alerte "livraison absente" lors d'imports partiels | Alarme inutile dans le chat et le carnet d'échanges quand seul un fichier de vente arrive l'après-midi. |
| **ANO-H10** | **Maintenance** | `moteur/promotions.py` & `preparer-apercus-promotion.py` | Dépréciation de l'import `fitz` (PyMuPDF) | Avertissements de dépréciation répétés dans la console Python. |

---

## 3. Analyse Détaillée des Anomalies et Solutions Proposées

### ANO-H01 — Biais de calcul : `min()` sur les facteurs de vacances scolaires
- **Localisation** : `moteur/generer-proposition.py`, lignes 250-254
- **Constat dans le code** :
  Le coefficient `f_vac` est calculé en prenant le minimum entre le jour de commande ($J$) et le jour de livraison ($J+1$) :
  `f_vac = min(facteur_vacances(date_commande, cal), facteur_vacances(date_livraison, cal))`
- **Mécanisme et risque métier** :
  1. Si $J$ est un jour scolaire normal (facteur = $1,0$) et que $J+1$ correspond au grand départ ou aux fêtes de Noël (facteur = $1,162$ soit $+16,2\,\%$) : le `min(1.0, 1.162)` donne **1,0**. Le surcroît massif de demande du jour de livraison est **complètement annulé**, conduisant à une sous-commande et à des rayons vides le jour de pointe.
  2. Si $J$ est un jour de départ (ex. pont de l'Ascension avec baisse de fréquentation locale $-10\,\%$ soit facteur = $0,90$) et $J+1$ est normal : le `min(1.0, 0.90)` pénalise indûment les ventes de $J+1$.
- **Solution recommandée** :
  Dissocier l'application des facteurs de vacances pour chaque période respective :
  ```python
  if cal:
      moy_cmd *= facteur_vacances(date_commande, cal)
      moy_liv *= facteur_vacances(date_livraison, cal)
  ```

---

### ANO-H02 — Biais de calcul : `min()` sur les facteurs fériés
- **Localisation** : `moteur/generer-proposition.py`, lignes 244-248
- **Constat dans le code** :
  `f_ferie = min(ferie.facteur(date_commande), ferie.facteur(date_livraison))`
- **Mécanisme et risque métier** :
  Le calendrier des jours fériés applique un coefficient de présence (ex. $0,54$ pour un jour férié ouvert uniquement le matin, ou $0,0$ pour un jour fermé). En prenant le `min()`, si le jour de livraison est un matin férié ($0,54$) et le jour de commande un jour normal ($1,0$), les ventes attendues pour aujourd'hui (`moy_cmd`) sont réduites de près de moitié ($0,54$). Le calcul déduit à tort que le stock actuel suffira amplement, sous-estimant la commande requise.
- **Solution recommandée** :
  Appliquer à chaque jour son propre facteur d'activité fériée :
  ```python
  if ferie:
      moy_cmd *= ferie.facteur(date_commande)
      moy_liv *= ferie.facteur(date_livraison)
  ```

---

### ANO-H03 — Facteur météo appliqué à l'aveugle sur la date de livraison seule
- **Localisation** : `moteur/generer-proposition.py`, ligne 262
- **Constat dans le code** :
  `f_meteo = facteur_meteo(article_code, date_livraison, meteo_prev)`
  Le facteur est appliqué à la fois sur `moy_cmd` et `moy_liv`.
- **Mécanisme et risque métier** :
  Le facteur météo est évalué uniquement pour la météo du jour de livraison (`date_livraison`), puis multiplié à la fois sur `moy_cmd` (consommation du jour actuel) et sur `moy_liv` (consommation post-livraison). S'il fait beau aujourd'hui mais qu'un orage éclate demain, la demande d'aujourd'hui sera artificiellement comprimée.
- **Solution recommandée** :
  Calculer `f_meteo_cmd` pour `date_commande` et `f_meteo_liv` pour `date_livraison`.

---

### ANO-H04 — Tests unitaires en échec sous Windows (Subprocess UTF-8)
- **Localisation** :
  - `tests/test_correction_conversion_comptage.py`, ligne 245
  - `tests/test_colisage_chaine.py`, ligne 78
- **Constat** :
  L'absence de `PYTHONIOENCODING="utf-8"` et de gestion d'encodage explicite fait échouer `json.loads` sur les caractères accentués (« Pièce », « Barquette ») sous Windows console CP1252.
- **Solution recommandée** :
  Standardiser les appels `subprocess.run` dans les tests avec `env = {**os.environ, "PYTHONIOENCODING": "utf-8"}` et `encoding="utf-8", errors="replace"`.

---

### ANO-H05 — Horloge système `date.today()` figeant le comportement batch
- **Localisation** :
  - `moteur/preparer-liste-comptage.py`, lignes 89-96
  - `moteur/filet-de-securite.py`, ligne 122
- **Constat** :
  L'utilisation directe de l'horloge machine empêche de rejouer des scénarios historiques ou des vérifications rétrospectives fiables en simulation.
- **Solution recommandée** :
  Supporter un paramètre optionnel `--date AAAA-MM-JJ` par défaut égal à `date.today()`.

---

### ANO-H06 — Scripts `.bat` verrouillés sur `py -3.14`
- **Localisation** : `demarrer-serveur.bat` (L.8) et `verifier-avant-commande.bat` (L.24)
- **Constat** :
  L'instruction rigide `py -3.14` fait échouer l'exécution si une autre version de Python (3.12, 3.13) ou un environnement virtuel est actif.
- **Solution recommandée** :
  Adopter une commande avec repli automatique (`python || py -3`).

---

### ANO-H07 & ANO-H08 — Nettoyage documentaire et résidus pré-Hermes
- **Constat** :
  - Présence redondante de `AGENTS.md` (qui redirige lui-même vers `AGENT.md`).
  - Répertoire `roles/` vide.
  - Fichiers `donnees/travaux.jsonl` et `donnees/courrier/a-voir.jsonl` de 0 octet obsolètes.
- **Solution recommandée** :
  Conserver `AGENT.md` comme unique référence, supprimer `roles/`, archiver les fichiers de queue de travaux obsolètes.

---

### ANO-H09 — Fausse alerte "livraison absente" lors d'imports asynchrones
- **Localisation** : `moteur/integrer-fichiers.py`, lignes 331-344
- **Constat** :
  Un avertissement d'absence de livraison est levé même quand on intègre normalement les ventes de l'après-midi, créant du bruit inutile dans les carnets.
- **Solution recommandée** :
  Ne déclencher d'alerte critique que si aucun des deux types de fichiers n'est trouvé, ou adoucir le niveau de log lors d'imports monotypes.

---

### ANO-H10 — Dépréciation de l'import `fitz` (PyMuPDF)
- **Localisation** : `moteur/promotions.py` et `moteur/preparer-apercus-promotion.py`
- **Constat** :
  Avertissement de dépréciation de `fitz` sous PyMuPDF récent.
- **Solution recommandée** :
  Remplacer par `import pymupdf as fitz`.

---

## 4. Recommandations de Déploiement

1. **Phase 1 (Immédiate)** : Corriger les 2 biais algorithmiques `min()` (`ANO-H01`, `ANO-H02`) dans `generer-proposition.py`.
2. **Phase 2** : Corriger l'encodage des 2 tests sous Windows (`ANO-H04`) pour atteindre 100 % de réussite (352/352).
3. **Phase 3** : Assouplir les scripts `.bat` (`ANO-H06`) et nettoyer les résidus documentaires (`ANO-H07`, `ANO-H08`).
