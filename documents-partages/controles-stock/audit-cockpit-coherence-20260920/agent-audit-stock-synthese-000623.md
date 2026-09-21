# Audit privé — cohérence du cockpit depuis les relevés terrain

Auteur réel : agent-audit-stock. Preuves complètes : `agent-audit-stock-preuves-000623.json`.

## Résultat

Les 74 saisies du 15/09 couvrent 73 articles distincts (melon 0000087003306 saisi deux fois à 18:20:58 et 18:21:51, dernière mesure retenue). Il reste 52 bases écran et 21 déclarations en conversation. 41 positions sont négatives ; 45 n’ont aucune livraison appliquée (ce total inclut des articles sans activité). Les 73 positions reproduisent exactement etat.json ; les 44 valeurs numériques présentes dans proposition.json concordent aussi. Les autres entrées de proposition absentes ou sans position_unites ne sont pas des divergences arithmétiques.

Les négatifs importants sont donc bien calculés. Les alertes enregistrées des imports partiels du 16 au 19/09 imposent de rechercher les lignes refusées avant toute certification des stocks. Aucun mouvement correctif n’a été ajouté.

## Exemples prioritaires

|Article|Base (date)|Livraisons depuis|Ventes depuis|Casse/dons|Position calculée|
|---|---:|---:|---:|---:|---:|
|BANANE VRAC (0000087004011)|105.45 (2026-09-15)|0.0|501.45|0.0/0.0|-396.0|
|TOMATE COTELEE ROUGE VRAC (0000087004807)|26.95 (2026-09-15)|0.0|186.92|0.0/0.0|-159.97|
|TOMATE COTELEE JAUNE VRAC (0000087004778)|-10.5 (2026-09-07)|91.0|136.11|1.5/0.0|-57.11|
|TOMATE COTELEE NOIRE VRAC (0000087004808)|56.7 (2026-09-15)|0.0|113.61|2.0/0.0|-58.91|
|RAISIN NOIR MUSCAT VRAC (0000087004957)|8 (2026-09-07)|72.0|173.98|0.0/0.0|-93.98|
|RAISIN ROSE VRAC (0000087004636)|0 (2026-09-07)|20.0|131.91|10.0/0.0|-121.91|

Chiffres dans les unités métier utilisées par le moteur ; vente/casse souvent stockées comme « inconnue ». Catalogue et bases des exemples indiquent kg : ne pas transformer ce rapprochement documentaire en certification des sources vente. Aucun total global mélangeant unités.

## Interprétation et limites

- La position est relative au rayon plein, pas le stock total. La capacité du rayon manque pour déduire le stock physique absolu.
- Ventes et casses portent souvent unite=inconnue; quantités arithmétiques reproduites ne certifient pas les unités originales.
- Aucune livraison appliquée signifie aucune entrée enregistrée après le repère, pas absence physique de livraison.
- Phase soir >=17h est convention moteur, pas preuve de clôture physique.
- Les totaux journaliers ne permettent pas un delta intrajournalier exact après un comptage pendant ouverture.
- L’origine ecran-comptage du relevé19/09 Chantecler vient ici app/fiabilite.html et motif réimplantation; ne pas le présenter comme inventaire général.
- Code demandé0000087004638 absent;4636 existe pour raisin rose, analysé séparément sans substituer identité.

Les bases du 15 sont toutes classées soir : le moteur exclut donc tous les flux du 15/09. L’exclusion de ventes éventuellement postérieures au relevé de 18 h reste une limite de la granularité journalière. Elle ne peut expliquer à elle seule les entrées de livraison non enregistrées les jours suivants.

## Alertes déjà présentes dans le chat

- Ligne 3, `rep:2026-09-16T05:24:50:346fa7` : ⚠ Import incomplet : 0 mouvements intégrés, 20 point(s) à vérifier — 0000087003021 ; 0000087003359 ; 0000087003495 ; et 17 autre(s). Aucune donnée non vérifiée n'a été ajoutée.
- Ligne 4, `rep:2026-09-16T08:16:04:8a1f43` : ⚠ Import incomplet : 46 mouvements intégrés, 25 point(s) à vérifier — 0000087003021 ; 0000087003359 ; 0000087003495 ; et 22 autre(s). Aucune donnée non vérifiée n'a été ajoutée.
- Ligne 8, `rep:2026-09-17T05:18:48:5128e4` : ⚠ Import incomplet : 0 mouvements intégrés, 24 point(s) à vérifier — 0000087003021 ; 0000087003359 ; 0000087003495 ; et 21 autre(s). Aucune donnée non vérifiée n'a été ajoutée.
- Ligne 9, `rep:2026-09-17T06:10:27:9d909b` : ⚠ Import incomplet : 48 mouvements intégrés, 21 point(s) à vérifier — 0000087003021 ; 0000087003495 ; 0000087004011 ; et 18 autre(s). Aucune donnée non vérifiée n'a été ajoutée.
- Ligne 17, `rep:2026-09-18T08:14:14:8b2406` : ⚠ Import incomplet : 43 mouvements intégrés, 23 point(s) à vérifier — 0000087003021 ; 0000087003495 ; 0000087004011 ; et 20 autre(s). Aucune donnée non vérifiée n'a été ajoutée.
- Ligne 19, `rep:2026-09-19T05:23:39:f28bce` : ⚠ Import incomplet : 46 mouvements intégrés, 20 point(s) à vérifier — 0000087003021 ; 0000087004011 ; 0000087004035 ; et 17 autre(s). Aucune donnée non vérifiée n'a été ajoutée.

Les messages généraux de réussite ultérieurs ne prouvent pas que les refus ont été repris. Un fichier dernier-import.json de ventes réussi ne certifie pas une livraison antérieure partielle.

## Suite utile

1. Vérifier les lignes de réception refusées dans les originaux, unités et facteurs attestés, puis distinguer correction technique, preuve métier et autorisation.
2. Afficher pour chaque produit la base exacte, les flux retenus/exclus, unités et écarts, ainsi que les refus encore ouverts.
3. Ne jamais exiger qu’un total ventes soit inférieur au total livraisons sur une fenêtre arbitraire ; comparer le bilan depuis un relevé pertinent et la position actuelle.
4. Conserver commande, livraison reçue, prévision et position dans des séries séparées.

Écritures effectuées : ce rapport Markdown et le JSON de preuves privés uniquement. Aucun stock, décision, dérivé opérationnel, journal de réponse ou acquittement modifié.
