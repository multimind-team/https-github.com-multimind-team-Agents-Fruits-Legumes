# Exception temporaire explicitement autorisée

Source : conversation Codex du 15 septembre 2026 ; identifiant technique du message non fourni.

Question présentée au responsable :

« Autorisez-vous, pour ce seul lot, le passage temporaire du plafond de l’agent rayon de 15 à 18 et du plafond global de 20 à 25 ? Cela permet les six colisages confirmés (C01, C02, C03, C09, C10, C11), les douze masquages demandés, vos vingt et une positions et le recalcul. Les plafonds habituels seront rétablis ensuite. Cette confirmation est nécessaire car donnees/pouvoirs.json et agents/agent-rayon.md imposent ces limites. »

Réponse explicite reçue ensuite : **« j'autorise le dépassement temporaire du plafond »**.

Portée : ce lot uniquement. Valeurs temporaires autorisées : `agents.agent-rayon.plafond_par_jour = 18` et `plafond_par_jour_tous_agents = 25`. Les autres permissions et plafonds restent inchangés. Restituer les valeurs d’origine après traitement ; ne pas effacer les actions consommées du journal.

Cette exception n’autorise aucun nouveau mouvement de livraison, aucune fusion, aucun prix inventé, aucun changement du contenu historique des carnets ni aucune transmission de commande fournisseur.
