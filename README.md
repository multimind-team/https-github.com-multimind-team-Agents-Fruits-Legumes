# Préparation de commande — rayon fruits & légumes

Intermarché Carmaux, point de vente 11768. Projet démarré le 2 septembre 2026.

---

## À quoi ça sert

Chaque matin, le rayon décide quoi commander sur environ 600 articles. **La commande part à
9h30, sans rattrapage.** Trop commandé, la marchandise part à la casse ; pas assez, le rayon est
vide.

L'application calcule la proposition et laisse le dernier mot au responsable de rayon.

---

## Comment ça marche

Les données arrivent **par mail** — ventes, livraisons, casse, dons, cadencier. La sentinelle mail est déclenchée de deux façons :
- **À la demande** : via le bouton *« 📩 Relever les mails maintenant »* sur l'application web.
- **En arrière-plan** : par une tâche planifiée Windows (script `installer-tache-planifiee-mails.bat`) qui fait un passage toutes les 5 minutes.

Elle dépose le travail dans le guichet unique `donnees/travaux.jsonl`. Tous les événements du magasin y sont rassemblés au même endroit :
- La sentinelle y dépose les travaux de **courrier**.
- Le serveur web y dépose les **messages** du responsable de rayon.
- L'écran de comptage y dépose les **comptages** de la chambre froide.

Le **guetteur** (`moteur/surveiller-travaux-pour-agent.py`) surveille ce fichier central et alerte immédiatement l'IA dès qu'un travail est à faire. La séparation *« les producteurs déposent le ticket, le guetteur avertit l'IA »* garantit qu'aucun événement du magasin ne soit manqué.

Un **rôle IA** s'en saisit alors : il ouvre les fichiers, repère ce qui cloche, prend les décisions métier et met à jour la commande.



Trois choses le rendent solide :

- **le travail attend dans un fichier**, jamais dans une mémoire : si personne n'est là, il
  reste ;
- **rien ne s'efface** — une erreur se corrige en ajoutant une ligne qui l'annule ;
- **un filet de sécurité tourne seul** : même sans aucun rôle, une proposition existe avant
  9h30, avec son âge affiché.

---

## Les écrans et l'analyse d'aide à la décision

- **Accueil (`app/index.html`)** : tableau de bord du magasin, état des carnets, alertes du jour, relève manuelle du courrier et accès direct aux actions.
- **Commande (`app/commander.html`)** : écran de saisie et de décision de commande quotidienne.
  - **Ajustement instantané** : quantités proposées par le moteur, modifiables en un clic avec calcul immédiat du montant total d'achat et du taux de marge globale.
  - **Fiche détail article enrichie** :
    - **Rentabilité financière** : cartouche indiquant le taux de marge brute actuel, le gain brut réalisé par colis, le prix d'achat et le prix de vente.
    - **Graphique interactif de saisonnalité (2,5 ans)** :
      - *Moyennes mensuelles (bâtonnets)* : vision du profil annuel de consommation sur 12 mois.
      - *L'an dernier 2025 (pointillés à la semaine)* : repère de comparaison saisonnier avec détection des ruptures.
      - *Cette année 2026 (courbe fine en blanc pur)* : tracé quotidien mettant en évidence les incidents récents et les ruptures en rayon.
      - *Projection « Cap mois suivant »* : ligne directrice vers la tendance attendue (hausse, stabilité, repli saisonnier).
      - *Diagnostic automatique* : badge de tendance, mois du pic annuel de vente et explication textuelle du comportement de l'article.
      - *Comparatif de rythme* : ventes journalières moyennes constatées sur le mois en cours pour 2024, 2025 et 2026.
    - **Navigation épinglée (Sticky)** : barre d'en-tête permanente avec boutons de retour en format pilule (`← Retour à la liste` et `← Retour accueil`) permettant de naviguer sans remonter manuellement le défilement.
- **Comptage (`app/compter.html`)** : interface mobile tactile sans clavier pour enregistrer les positions de stock en chambre froide.
- **Maintenance (`app/maintenance.html`)** : vue technique sur les carnets, les règles de fusion/éclatement et l'état des traitements.

---

## Le contenu

```
AGENTS.md      les consignes — à lire en premier
roles/         les six rôles
reference/     le métier, le calcul, la forme des carnets
moteur/        programmes : calculs, courrier, carnets, analyse historique, serveur
donnees/       les carnets : faits, décisions, journaux, état, analyse des ventes
app/           les écrans : accueil, commande, comptage, maintenance
```

---

## 🚀 Installation & Migration sur un nouveau PC Windows (Guide pas à pas)

Pour installer et faire tourner l'application sur une nouvelle machine ou un PC vierge :

### 1. Pré-requis sur le PC neuf
* **Installer Python (3.10 ou supérieur)** depuis [python.org/downloads](https://www.python.org/downloads/).
  * ⚠️ **TRÈS IMPORTANT** : Cochez impérativement la case **`Add python.exe to PATH`** au tout début de l'installation.
* **Aucun module PIP n'est nécessaire** : le projet n'utilise que les fonctions natives de Python.

### 2. Procédure d'installation (En 3 clics)

1. **Copier le dossier du projet** `preparation-commande` sur le nouveau PC.
   *(Le fichier `.env` contenant les identifiants mail est déjà présent à la racine du dossier).*
2. **Activer la relève des mails en arrière-plan** :
   * Clic droit sur `installer-tache-planifiee-mails.bat` ➔ **« Exécuter en tant qu'administrateur »** (à faire une seule fois).
3. **Lancer le serveur Web d'application** :
   * Double-cliquer sur `demarrer-serveur.bat`.
   * L'application est disponible sur : `http://127.0.0.1:8751/app/index.html`.

### 💡 Démarrage 100 % automatique au lancement de Windows
Pour que le serveur démarre tout seul dès l'allumage du PC sans ouvrir de terminal :
1. Appuyer sur `Windows + R`, taper `shell:startup` et valider par Entrée.
2. Déposer un raccourci de `demarrer-serveur.bat` dans ce dossier.


