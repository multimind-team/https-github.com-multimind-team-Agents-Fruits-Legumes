# Avis indépendant — cockpit PC

Rôle réel : agent-controle. Demande source : réalisation du cockpit du brief Gemini fourni, puis extension promotions/commentaires transmise par le Leader. Mandat : revue indépendante, aucun changement métier ; tests uniquement en copies temporaires. Le présent rapport est une écriture privée autorisée, pas une décision métier.

VERDICT : SÛR POUR LE PÉRIMÈTRE

Périmètre validé : moteur de contexte, intégration dans la proposition, archivage prospectif, API et lecture analytique relus dans les versions empreintées ci-dessous. La validation graphique et le parcours navigateur complet restent à la charge du Leader ; cet avis ne les invente pas. Aucune validation de commande ni import réel autorisé par cet avis.

## Preuves indépendantes exécutées

- `py -3.14 -B tests/lancer_tests_isoles.py tests/test_recomptage_api_chaine.py tests/test_ajustements_limites.py tests/test_regle_comptage_17h.py tests/test_correction_conversion_comptage.py` : 35 tests, OK, 35,862 secondes. Copies jetables, garde interdisant écritures originales et réseau externe.
- Scénario bout à bout indépendant dans une nouvelle copie des modules : article de fixture, PCB 10, stock physique 0, ventes moyennes 10/jour, TG active coefficient 1,5 et minimum 1 colis. Demande sur 2 jours = 30 unités ; proposition = 4 colis ; objet positions inchangé. Archivage le 09/04/2030 à 20h pour 10 et 11/04 : deux prévisions de 15 unités. Tentative de remplacement rétroactif à 999 unités le 12/04 : zéro ajout, octets inchangés. Faits de vente 8 puis 12 : pilotage retourne 2 paires, conformité 50 %, ventes comparées 2 colis et prévisions comparées 3 colis ; conformité des commandes reste inconnue. Identifiant opération conservé. Archives inchangées à la lecture.

## Preuves exécutants relues (distinctes de mes exécutions)

- Agent-donnees : 64 tests initiaux contexte/HTTP, colisages et garde-fous existants ; puis 18 tests contexte après extension promotions. Vérification annoncée en copie. Les doublons initiaux de tests HTTP liés à l'héritage de classe ont été retirés ensuite ; ne pas additionner ces nombres comme scénarios uniques.
- Agent-tendances : 22 tests pilotage et archives après extension et correction historique des campagnes ; puis mêmes 22 tests après cache mémoire. Lecture du code et des assertions par agent-controle.

## Constats précis

- `contexte_terrain.py` : carnet append-only, révision optimiste, idempotence de requête, valeurs finies et dates validées ; programmation évaluée au jour demandé, ancienne consigne maintenue avant début suivant, expiration sans réactivation antérieure, annulation explicite. Bilans tardifs admis seulement pour observations avec paramètres/dates existants conservés.
- `proposer-commande.py` : coefficients TG/îlot sur chaque jour, y compris intermédiaires ; minimum de présentation explicite. Promotion précommandée historique, blocages de position et arrondis protégés. Maturité, note et dates prospectus ne fabriquent ni mouvement physique ni vente. Lignes inconnues/secondaires portent avertissement si contexte non appliqué.
- `previsions_archivees.py` : horloge réelle locale, cibles strictement postérieures au jour d'écriture ; dernière prévision antérieure au jour observé. Aucune reconstitution du passé. Provenance de la proposition publiée relue après écriture atomique.
- `pilotage.py` : null distinct de zéro ; quantités rayon en équivalents PCB actuel explicités ; codes partagés comptés une fois ; comparaison prévisions sur seules paires observées et unités compatibles. Moyennes de promotions sur 28 jours précédents, comparaison supplémentaire des mêmes jours de semaine, couverture explicite, aucune causalité déduite. Précommandes humaines jamais assimilées aux réceptions ou à une commande envoyée. Implantation d'une campagne passée ne change plus lors d'une nouvelle consigne terrain sans rapport.
- Cache de flux : seulement sommes en mémoire ; invalidation nom/taille/mtime_ns des carnets, regroupements et date. Aucune nouvelle source persistée.
- Relecture UI : texte échappé, anciennes saisies protégées à navigation ; clic de la vue déjà active ne réinitialise plus formulaire ; consigne effective et prochaine distinguées ; ligne effective n'annule pas silencieusement la prochaine ; annotation sans recalcul n'attend plus un recalcul absent ; unité du prix promo choisie explicitement ; résumé de confirmation présente prix/unité/précommande. Parcours réel navigateur à confirmer par le Leader.

## Écritures, limites et autorisation

Aucune écriture de stock, de décision, de permission, de proposition ni aucun envoi par agent-controle. Seul ce rapport privé est créé. Les empreintes décisions/état/proposition/pouvoirs sont identiques avant/après mes vérifications. Ce contrôle ne prétend pas couvrir les nombreux changements qui préexistaient à la mission ni tous les autres fichiers de données non empreintés au début.

Les prévisions avant installation resteront absentes ; les comparaisons se rempliront avec les futures archives réelles. Pas de taux de conformité des commandes fournisseur sans ces commandes reçues. Pas de précommande future chiffrée automatiquement sans données comparables et stock/réceptions vérifiés. Commentaires automatiques déterministes, complétables par l'humain, distincts d'un avis d'agent IA nouvellement exécuté. Un nouveau changement pertinent invalide la partie correspondante de l'avis.

Autorisation métier : réalisation technique demandée par l'utilisateur. Les futures écritures métier n'arrivent que par la saisie humaine explicite dans l'interface, avec ses pouvoirs ; ce rapport ne crée aucune délégation nouvelle.

## Empreintes SHA256 à la revue

- `moteur/contexte_terrain.py` : `B93451C21261A442BFDBAE6EB39F37BA6F8B17D28CA5EBE81DACB4A41AF6F78B`
- `moteur/proposer-commande.py` : `DF1320D76ABBF58CB809C488F0F1609F09E52573181C9DBAB225150BE825F3A6`
- `moteur/generer-proposition.py` : `C54293C51D2DE22748B852E8426BB84D7DF755EEDDF689416EC0C6DCD7E74EE0`
- `moteur/previsions_archivees.py` : `AC9E8492874F5F70118EA20C0899C239735BFAA83CDB8BAE081B291F12423645`
- `moteur/pilotage.py` : `094B258FFBA46A3468A016EB8ED6C254F65790B48B2A4CC67BB9C05E7FC34654`
- `moteur/serveur.py` : `CD5E95B3BBF6876A37AEB9886C9616C8A0D894AC1D7EE60FF82A3619050DDF88`
- `app/js/cockpit.js` : `50480C88F3DBFAC5825E99B445672CE3A90800E279580517341FD02066771469`
- `app/cockpit.html` : `4C9C8CDA73B9F97AC5797ECF68C79D5390B325B4C113902D9F402466F0474423`
- `app/css/cockpit.css` : `329F12C1812418ED3FF5F8B76A3016A5CAE9595616A14295434CA87C8DADA018`
- `donnees/decisions.jsonl` : `AE19F78D676FB57FF458EB37FDAFDCCDBC7BFC29C33A119D3A6D269E1C04DE3D`
- `donnees/etat.json` : `8C66AAE143D8CD638710B81617DAAA8362B609168E71CC6BA11B0D101ABB6FEE`
- `donnees/proposition.json` : `3C9BDE7F273A7730C2A300D16D6486057814E8BCB9868B44E6D2220FAB041E7A`
- `donnees/pouvoirs.json` : `51B4C6403E21F9D70CB70D2B08A1F006A0BC00F28E7E30C7EC4CDE4148F3129A`
