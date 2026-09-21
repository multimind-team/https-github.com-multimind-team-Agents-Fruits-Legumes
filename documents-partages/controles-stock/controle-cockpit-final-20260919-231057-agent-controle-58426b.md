# Avis indépendant complémentaire — cockpit PC, version finale du backend

Auteur réel : agent-controle. Date locale : 2026-09-19T23:10:57.
Ce rapport complète, sans l'écraser, [controle-cockpit-20260919-230624-agent-controle-45f4e3.md](controle-cockpit-20260919-230624-agent-controle-45f4e3.md). Il borne l'avis aux empreintes ci-dessous. QA navigateur/graphique : Leader, en cours lors de cette remise. Aucune validation de commande.

VERDICT : SÛR POUR LE PÉRIMÈTRE

## Blocage découvert puis levé

Scénario initial reproduit indépendamment en copie : après annulation d'une TG, le formulaire promotion reconstruisait une consigne complète sans `annuler`. Un simple commentaire faisait passer annuler=true/coefficient1 à annuler=false/coefficient1,5. Une fin de saison annulée aurait également pu rétablir l'arrêt automatique. Blocage signalé au Leader et à agent-donnees avant ouverture réelle.

Correction relue : mode `observations_seules:true` dans contexte_terrain.py. Base conservée sous verrou ; observations, note et dates promotion seulement ; paramètres moteur et annulation conservés ; création initiale neutre ; aucun recalcul. Le frontal emploie ce mode pour promotions et pour les notes seules sans changement de paramètres.

Preuve indépendante finale par vrais POST HTTP sur serveur en copie :
- Deux articles synthétiques, TG et fin-saison, tous deux annulés.
- POST commentaires+note en mode observations seules : HTTP200, annotation_seule=true, recalcul=non_necessaire ; annuler reste true, coefficient reste1, actif=false.
- Ordonnanceur de recalcul remplacé par une assertion d'interdiction : jamais appelé.
- Rejeu exact : déjà enregistré, carnet strictement inchangé.
- Tentative de changement emplacement vers îlot via mode observation : HTTP400, carnet inchangé.
- Écritures en ajout seul dans les seules fixtures temporaires.

Agent-donnees a transmis séparément 24 tests contexte isolés réussis après correction. Cette preuve de l'exécutant ne remplace pas mes essais indépendants ci-dessus.

## Vérification indépendante du démarrage

Lecture de gerer-serveur.py:248/284/313 et surveiller-serveur.py:32 : redémarrage ciblé du seul projet, vérification identité/HTTP, surveillance de disponibilité ; aucun lancement d'import, de filet ou de recalcul métier.

Essai indépendant réel en copie des modules avec fixtures synthétiques et port éphémère : serveur.py main, réponse HTTP200 de l'accueil ; faits, décisions, état, proposition, pouvoirs, fraîcheur et recalcul strictement inchangés. Aucun dossier de prévisions créé. Seuls nouveaux fichiers sous donnees : `.operations.lock` et `journal.jsonl`, avec une unique entrée technique de démarrage. Processus de test arrêté ensuite. La lecture de serveur.py:1132 confirme l'écriture de cette entrée technique : ne pas promettre un démarrage sans aucune écriture.

Consommation contexte : generer-proposition.py:401 recharge les décisions ; publication puis relecture du JSON exact sous verrou et archivage futur à la ligne609. Sauvegarde d'un changement moteur par API déclenche calculer-position/generer-proposition/preparer-liste-comptage ; annotation seule ne lance rien. Filet --forcer inclut le générateur et les nouvelles archives ; --verifier ne recalcule pas mais acquiert le bail technique.

Le redémarrage ne rajeunit aucune source métier et ne constitue pas un passage du filet. Il ne faut pas annoncer les stocks ou la fraîcheur métier remis à jour par cette seule opération.

## Preuves conservées et limites

Les 35 tests de régression indépendants et le scénario moteur→archives→pilotage du premier rapport restent acquis pour leurs périmètres inchangés. Cache mémoire pilotage relu : sommes converties en dictionnaires ordinaires, invalidation sur carnets/groupes/date, aucune écriture. Les 22 tests analytics/archives de l'exécutant ont été repassés après ce cache.

Les modifications UI signalées ont été relues : protection saisies vue active, contexte effectif vs prochain, actions non trompeuses sur ancienne consigne active, profil comparé sur paires, unité de prix non déduite, résumé prix/précommande, traitement non_necessaire. Le verdict graphique/navigation complet appartient au parcours navigateur du Leader.

Écritures réalisées par agent-controle dans le projet réel : uniquement les deux rapports privés. Aucun stock, décision, permission, proposition, archive de prévision ou envoi modifié. Les quatre empreintes métier de début de revue ci-dessous restent inchangées.

Une modification pertinente postérieure invalide le périmètre correspondant de cet avis. Les limitations analytiques déjà détaillées demeurent : aucun passé de prévisions reconstitué, conformité des commandes fournisseur indisponible, précommande future non chiffrée automatiquement, causalité promotion non établie.

## Empreintes SHA256 finales

- `moteur/contexte_terrain.py` : `626A3AB04CFFBC59F94CB999C8D837903CBD16FCDB8EC283115CA79346DC69D1`
- `moteur/proposer-commande.py` : `DF1320D76ABBF58CB809C488F0F1609F09E52573181C9DBAB225150BE825F3A6`
- `moteur/generer-proposition.py` : `C54293C51D2DE22748B852E8426BB84D7DF755EEDDF689416EC0C6DCD7E74EE0`
- `moteur/previsions_archivees.py` : `AC9E8492874F5F70118EA20C0899C239735BFAA83CDB8BAE081B291F12423645`
- `moteur/pilotage.py` : `094B258FFBA46A3468A016EB8ED6C254F65790B48B2A4CC67BB9C05E7FC34654`
- `moteur/serveur.py` : `CD5E95B3BBF6876A37AEB9886C9616C8A0D894AC1D7EE60FF82A3619050DDF88`
- `moteur/gerer-serveur.py` : `5692CDFB15BBA6FBC56CE2593FEDC938C7A648650BE1C4A4A218F9F27855C0E1`
- `moteur/surveiller-serveur.py` : `3CB6CFC6414114B4F06ADF02773C7FDA891893E57DF1DF74E195BD1A3F182DB8`
- `moteur/filet-de-securite.py` : `D274D622A06E9F8658D026EB5C99A5DF0FB3F6D8522E7BD2D5547F93FF4441DC`
- `app/js/cockpit.js` : `349098B3A17C8B4E1D8555F0A76500A5278EA3F62A5DFC13E987E87F0E9D51BB`
- `donnees/decisions.jsonl` : `AE19F78D676FB57FF458EB37FDAFDCCDBC7BFC29C33A119D3A6D269E1C04DE3D`
- `donnees/etat.json` : `8C66AAE143D8CD638710B81617DAAA8362B609168E71CC6BA11B0D101ABB6FEE`
- `donnees/proposition.json` : `3C9BDE7F273A7730C2A300D16D6486057814E8BCB9868B44E6D2220FAB041E7A`
- `donnees/pouvoirs.json` : `51B4C6403E21F9D70CB70D2B08A1F006A0BC00F28E7E30C7EC4CDE4148F3129A`
