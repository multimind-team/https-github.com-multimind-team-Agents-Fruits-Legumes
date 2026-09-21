# Recette du cockpit PC — Leader — 19 septembre 2026

Demande source : application PC selon le brief Gemini joint, complétée dans la conversation par le suivi des promotions, les commentaires automatiques modifiables et les photos datées du rayon. Préférence explicite : photos sur ce PC, commentaires fondés sur le contexte renseigné.

## Résultat livré

Application locale `app/cockpit.html` servie par le serveur existant. Raccourci créé : `C:\Users\user\Desktop\Cockpit Fruits et Legumes.lnk`, lanceur `ouvrir-cockpit.vbs`. Fenêtre dédiée Edge constatée, titre « Cockpit · Fruits & Légumes · Carmaux ».

Tableau de bord, enquête produit, contexte terrain, bilan des promotions, historique de consignes, journal photo avec édition et agrandissement. Archives de prévisions futures ; aucun remplissage rétroactif. Commentaires déterministes éditables, aucun envoi des photos à un modèle ou service externe. Photos et carnet photo exclus de Git distant.

## Recette exécutée par le Leader

`py -3.14 -B tests/lancer_tests_isoles.py tests/test_cockpit_navigateur.py` : réussite du parcours complet en 146,205 secondes dans une copie jetable. Le lanceur interdit les écritures dans l'installation originale.

Parcours réel Edge : lecture des données ; recherche d'article ; consigne TG avec dates ; conservation du brouillon sur clic répété ; confirmation humaine ; relecture du calcul ; échappement d'un commentaire contenant du HTML ; bilan promotion avec prix/unité/précommande et rupture ; comptage réel en copie ; changement PCB et relecture proposition ; annulation TG ; commentaire de promotion après annulation sans réactivation ; ajout photo synthétique clairement marquée test ; commentaire automatique recopié ; édition version 2 sans changement d'image ; agrandissement ; affichage aux largeurs 1440, 1024 et 390 px sans débordement horizontal. Aucune erreur JavaScript.

Les échecs intermédiaires ont révélé une balise de bouton de confirmation mal fermée, puis des attentes de test trop précoces avant les fins d'opérations asynchrones. Corrections apportées avant la réussite finale. Le contrôle indépendant a également fait corriger la réactivation d'une consigne annulée par un simple commentaire ; le parcours final couvre ce cas.

Captures privées de recette : dossier `C:\Users\user\.codex\visualizations\2026\09\19\01a0bb6f-51e7-7921-9961-497932a75f07\cockpit-qa`.

## Contrôles indépendants reçus et relus

- `controle-cockpit-final-20260919-231057-agent-controle-58426b.md` : périmètre moteur/contexte/prévisions, complété dans la conversation par les scénarios HTTP d'annotation après annulation.
- `controle-cockpit-photos-ca-20260919-231757-agent-controle-4bb1b4.md` : photos, chemins privés, limites, métadonnées, conflits et CA historique.

Ces avis appartiennent à agent-controle ; le présent rapport décrit seulement la recette et la mise en service effectuées par le Leader.

## Mise en service et limites

Redémarrage distinct exécuté via `py -3.14 -B moteur/gerer-serveur.py demarrer --redemarrer`. État final : un serveur identifié, un surveillant identifié, HTTP applicatif OK. Les pages cockpit/index, les deux JavaScript et les API pilotage/contexte/photos répondent HTTP 200. Ouverture du tableau de bord et du journal photo vérifiée dans le navigateur publié, en bloquant tout POST pendant ce contrôle. Pas de vérification ni d'annonce d'accès mobile.

Huit empreintes de carnets/état/proposition/pouvoirs et absence de carnet photo comparées avant/après mise en service : aucune différence. Aucune archive de prévision de production créée pendant les tests ou le démarrage. Le démarrage a seulement les effets techniques attendus de gestion serveur, notamment journaux/verrous ; il ne certifie pas la fraîcheur métier.

CA reconstitué à partir des seuls prix historiques présents, avec couverture affichée. Marge historique indisponible faute de bases HT/TTC attestées. Précommande future non chiffrée tant que les campagnes comparables, le stock vendable et les réceptions prévues ne permettent pas une proposition fiable. Photos non interprétées visuellement : commentaire automatique tiré uniquement des informations saisies, selon le choix explicite de l'utilisateur.
