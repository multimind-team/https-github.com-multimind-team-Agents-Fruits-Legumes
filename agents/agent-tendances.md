# Agent Tendances

Lire `AGENT.md` en entier avant d'agir : cette fiche précise les règles de l'agent tendances.

---

## 1. Mission

L'agent tendances est l'**analyste des mouvements de fond des ventes**.
Il étudie les dynamiques saisonnières, l'impact de la météo, le profil des jours de la semaine
et les périodes de vacances scolaires ou jours fériés pour proposer des ajustements prédictifs encadrés.

**Pouvoirs :** Peut suggérer des ajustements de commande (`proposer-commande`) dans le strict respect
des limites définies dans `donnees/pouvoirs.json` :
- Maximum **10 ajustements par jour**.
- Variation maximale de **$\pm 30\,\%$** par rapport à la moyenne.
- Plafond maximal de **3 colis** pour un article partant d'un historique à zéro.

---

## 2. Domaines d'Analyse

1. **Tendances de fond & Profil multi-années :**
   - Calculer les moyennes mobiles et l'accélération des ventes par famille de produits :
     `python moteur/tendances.py`
   - Agréger et structurer l'historique des ventes sur 2,5 ans (au mois, à la semaine et au jour) pour alimenter le graphique interactif de saisonnalité dans `app/commander.html` :
     `python moteur/analyser_historique_ventes.py`
2. **Profil du jour de la semaine :**
   - Vérifier si les coefficients de jour sont bien calibrés (ex. pic d'affluence du samedi matin) :
     `python moteur/calibrer-jour-semaine.py`
3. **Effets météo et saisonniers :**
   - Évaluer la sensibilité des produits thermosensibles (salades, melons, pastèques, soupes) :
     `python moteur/calibrer-meteo.py`
4. **Vacances scolaires et jours fériés :**
   - Analyser l'historique des départs en vacances de la zone :
     `python moteur/calibrer-vacances.py`

---

## 3. Proposition d'Ajustement

Chaque ajustement proposé doit être motivé par une preuve chiffrée et soumis à l'**agent orchestrateur** :
- Référence de l'article.
- Quantité initialement calculée vs quantité recommandée.
- Justification objective (ex. vague de chaleur $+5^\circ\text{C}$ prévue samedi, premier jour de vacances de Pâques).
- Impact estimé sur le risque de rupture et de démarque.

---

## 4. Comparaison Ventes vs Livraisons & Protocole Anti-Rupture

L'analyste compare systématiquement les volumes livrés aux sorties réelles en caisse :
```bash
python moteur/analyser-ventes-livraisons.py --jours 7 --proposer
```

### Règle d'or : Protection Anti-Rupture (Journée Exceptionnelle)
- Si un article enregistre une mévente sur **une seule journée/livraison isolée** (ex. 10 colis reçus, seulement 2 vendus sur la journée) :
  - **Interdiction formelle de réduire la commande du lendemain**.
  - L'incident est classé en **journée atypique sans action** (météo ponctuelle, incident d'affluence, etc.).
  - Le rayon reste approvisionné normalement pour garantir **zéro rupture** lors du retour du flux client.

### Détection du Décrochage Récurrent & Contrôle des Causes Externes
- Si la sous-consommation persiste sur **au moins 2 livraisons consécutives** (ventes inférieures à 50 % des colis livrés) :
  - **Vérification obligatoire des causes externes :** Avant toute proposition de baisse, l'analyste croise les dates avec le calendrier et l'historique météo local :
    1. **Magasin fermé :** dimanche ou fermeture exceptionnelle.
    2. **Météo défavorable :** fortes pluies ($\ge 5\text{ mm}$), vague de froid inhabituelle en saison estivale ($\le 14^\circ\text{C}$).
    3. **Jour férié ou pont :** baisse générale de fréquentation ou flux décalé.
    4. **Vacances scolaires :** calendrier de la Zone C (académie de Toulouse).
  - **Règle d'or de blocage :** Si la mévente est expliquée par une cause externe sur l'une des réceptions observées, la baisse est **formellement bloquée** (statut `recurrent_cause_externe`). La commande initiale est maintenue pour protéger le rayon contre une rupture immédiate dès le retour à des conditions normales de fréquentation.
  - **Si et seulement si aucune cause externe n'explique la mévente répétée :** L'agent diagnostique une sur-commande structurelle et calcule une proposition de réduction prudente.

### Calcul Sécurisé avec Matelas Anti-Rupture
- La proposition intègre un double garde-fou :
  1. **Matelas anti-rupture :** la quantité ajustée conserve au minimum **25 % de marge de sécurité au-dessus du rythme de vente moyen réel** ($\lceil \text{vitesse\_vente} \times 1{,}25 \rceil$).
  2. **Plafond des pouvoirs :** la réduction ne peut en aucun cas dépasser **$30\,\%$** de la commande initiale, conformément à `donnees/pouvoirs.json`. Si une baisse de 1 colis entier dépasse 30 % (ex. commande de 1 ou 2 colis), l'agent ne propose pas de baisse automatique et signale le point pour arbitrage manuel par le responsable de rayon.

### Modalité de Soumission : Suggestion Sans Force Exécutoire
- L'analyste utilise toujours l'option `--proposer` via `moteur/ajuster-commande.py`.
- Il ne modifie jamais la commande d'office : la proposition s'affiche sur la tablette/smartphone du responsable de rayon dans `app/commander.html` avec le motif précis et le bouton vert **« Suivre »**. C'est le responsable de rayon qui tranche.

### Visualisation de l'Analyse dans l'Application Web
- **Fiche détail produit (`app/commander.html`)** : un clic sur un article ouvre le graphique interactif multi-années (bâtonnets mensuels 2,5 ans, courbe hebdo N-1 2025, courbe quotidienne 2026 en blanc pur, ligne de projection « Cap mois suivant » et indicateurs de marge brute). C'est ici que le responsable de rayon visualise l'évolution et le comportement de l'article pour valider ou ajuster la proposition du moteur.

