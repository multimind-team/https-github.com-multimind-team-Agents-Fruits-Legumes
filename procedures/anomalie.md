# Procedure anomalie

## Quand l'utiliser

Utilise-la quand un chiffre, un article ou un fichier semble bizarre.

l'agent orchestrateur choisit `agent-controle` pour le risque, `agent-articles` pour une enquête produit, ou
`agent-donnees` pour un import. Entrée : anomalie exacte et sources. Sortie : fait vérifié,
hypothèses, effet possible, correction proposée et propriétaire autorisé à l'appliquer.

Le contrôle n'attend pas l'apparition d'un chiffre bizarre : chaque lot suit la revue indépendante
avant/après de `procedures/controle-stock.md`. Utiliser `reference/modele-controle-stock.md` pour
suivre les sources, les avis, le message d'erreur relu et sa résolution. Un nouveau mail sain ne
clôt pas une anomalie d'un autre fichier ; un rectificatif doit être intégré et vérifié réellement.

## Etapes

1. Lire `reference/le-metier.md` avant de conclure que c'est anormal.
2. Lire `reference/le-calcul.md` si la quantite proposee surprend.
3. Verifier l'article :

```bat
py -3.14 moteur/catalogue.py <code>
py -3.14 moteur/regles.py <code>
```

Lire directement `donnees/agregats.json` existant pour les statistiques. `agregats.py <code>`
peut créer ce fichier s'il manque : une analyse sans écriture l'exécute en copie. De même,
`articles-masques-vendus.py` produit un dérivé ; son nom ne garantit pas la lecture seule.

4. Chercher la cause :
   - livraison directe non saisie ;
   - code jumeau ;
   - conditionnement faux ;
   - article masque qui vend encore ;
   - promotion ;
   - position trop basse ;
   - fichier absent ou incomplet.
   - doublon historique, instant de comptage ou conversion d'unité incohérent ;
   - désaccord entre une règle documentée et le code en cours d'exécution.
5. Les agents de contrôle/articles restent en lecture seule métier ; ils peuvent rendre leurs rapports de preuve privés selon le mandat. Si une correction est sûre, l'agent orchestrateur
   la transmet à l'agent autorisé avec son motif et, si nécessaire, la validation du responsable.
6. Sinon, signaler ce que tu as trouve et demander validation.

## Cas normaux a ne pas signaler trop vite

- Position negative.
- Orange machine a jus qui sort via les ventes de jus.
- Casse et dons traites pareil dans le calcul.
- Article sans position parce qu'il n'est plus en rayon.
- Fournisseur direct qui n'apparait pas dans le fichier Scafruit.
- Casse ou dons absents parce qu'il n'y en a pas eu.
- Position recomptée plus récente que les statistiques de vente ; ne pas fusionner leurs dates.

Un doublon de carnet n'autorise jamais à supprimer une ligne. Un code fournisseur inconnu,
une photo ressemblante ou une position qui remonte ne justifient aucune quantité, livraison ou
correspondance inventée. Rapporter les preuves `fichier:ligne` et les constats devenus périmés si
un autre intervenant modifie le code pendant l'enquête.
