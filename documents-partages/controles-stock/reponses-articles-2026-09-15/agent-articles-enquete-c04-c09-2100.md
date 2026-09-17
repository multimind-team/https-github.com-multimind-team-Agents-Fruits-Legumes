# Enquête C04 à C09 — dernières sources locales

**Agent-articles · 15 septembre 2026 · lecture seule métier.**

Mandat : retrouver les calibres, fournisseurs et contenus de colis dans les sources locales, sans import, modification de stock, mapping ou paramètres. La [demande originale transcrite](demande-source.md) a été lue. Aucun identifiant de message n’est inventé. Les positions P et les autres repères sont hors de cette enquête.

## Résultat à transmettre

| Repère | Code magasin et produit | Conclusion prouvée | Suite proposée |
|---|---|---|---|
| **C04** | `0000087004282` — POMELO ROUGE PIECE | Dernier export contenant cet article : **calibre 4, Star Ruby, Afrique du Sud, 45 pièces/colis**. Même calibre/base dans l’export du 09/09. | L’offre calibre 4 / PCB 45 correspond aux dernières sources retrouvées ; ne pas sélectionner calibre 5 / PCB 50 sur le seul premier choix logiciel. |
| **C05** | `0000087004562` — CAROTTE NON LAVEE VRAC | Cadencier : **PCB 12** ; export récent : base **1 kg**, insuffisante pour attester le poids du colis. Le responsable indique une demi-cagette mais dit explicitement « ce sera à confirmer ». | **Reste à confirmer.** Ne pas transformer l’hypothèse de demi-cagette en validation de 12 kg ni en division automatique par deux. |
| **C06** | `0000087005002` — CAROTTE VRAC | Exports du **11, 12 et 14/09 : base 12 kg, conservation, calibre 20/45 mm**. Les précédents montrent **10 kg, primeur, 20/50 mm**. | La dernière offre documentée est 12 kg / 20–45 mm. Conserver la distinction entre formats, sans affirmer un colisage permanent unique. |
| **C07** | `0000087004662` — ECHALOTE TRADITIONNELLE VRAC | Pomona/TerreAzur, bordereau du **12/09**, code fournisseur **106051** : libellé **30/50, 5K**, **1 COL = 5 KG**, PU **1,60 €/kg**, HT **8,00 €**. | Le colis Pomona documenté est **5 kg** ; le PCB 6 de Webtelevente concerne une autre offre/filière et ne justifie pas son remplacement. |
| **C08** | `0000087004082` — OIGNON ROUGE VRAC | Pomona/TerreAzur, bordereau du **14/09**, code fournisseur **106535** : libellé **60/80, 5K**, **1 COL = 5 KG**, PU **1,39 €/kg**, HT **6,95 €**. | Le colis Pomona documenté est **5 kg** ; ne pas le remplacer par le PCB 6 de l’offre Webtelevente. |
| **C09** | `0000087010621` — PDT VAPEUR BLONDE 2.5KG ITM | Le responsable confirme **box 55 sacs × 2,5 kg** et **caisse 6 sacs × 2,5 kg**. Le cadencier affiche ces deux offres 55/6 avec filet 2,5 kg ; les dernières sources magasin ont une base 6. | Remplacement de l’ancien réglage 8 par le format actuel à effectuer seulement par le rôle habilité et sous contrôle. Préserver les faits/comptages historiques et signaler l’unité « kg » de l’export, incohérente avec le comptage de sacs. |

Ces recommandations sont une enquête, pas l’avis indépendant d’exécution. Aucun réglage n’a été appliqué par agent-articles.

## Sources et méthode

- Correspondance des repères : `etat_actuel.colisages_a_verifier` de [articles-a-verifier.json](C:/Users/user/Desktop/audit-preparation-commande-2026-09-15/articles-a-verifier.json), état figé daté du 15/09 à 18:27:33. Aucun repère de la liste initiale n’a été substitué à ceux de cet état.
- **12 fichiers de livraison locaux**, soit **10 contenus SHA-256 distincts**, ont été lus sans sauvegarde Excel. Ils couvrent les exports conservés du 21/08 au 15/09. Les colonnes et les dates internes ont été lues, pas seulement les noms de fichiers.
- Le cadencier Webtelevente du 15/09 a été lu aux cellules des offres ciblées.
- Les deux pages de chacun des bordereaux Pomona du 12/09 et du 14/09 ont été inspectées visuellement. Les extraits JSON existants ont servi à localiser les lignes, puis les photos ont fourni la preuve d’unité et de quantité.
- Les carnets de faits et le mapping fournisseur ont été consultés comme traces secondaires ; ils ne remplacent pas les originaux.
- Les exports Mercalys s’intitulent **« Liste des articles commandés »**. Leurs champs « Cond. de base » et « Qté cmdée (nbre colis) » constituent une preuve documentaire du format commandé. Ils ne démontrent pas seuls une réception physique complète ni le contenu d’un comptage.

Preuves privées détaillées : [cellules des exports et empreintes avant/après](agent-articles-sources-c04-c09-205815.json), [photos lues, transcriptions et cellules du cadencier](agent-articles-preuves-factures-cadencier-2100.json). Le tableur `.xls` ancien exigeait `xlrd`, absent du runtime bureautique fourni : lecture avec la bibliothèque déjà installée, sans installation ni écriture du classeur. Les `.xlsx` ont été lus avec le Python bureautique fourni, en `read_only=True`.

## C04 — Pomelo rouge : calibre 4 prouvé

Source la plus récente trouvée contenant le code : [livraison 14.09.2026.xlsx](<C:/Users/user/Desktop/preparation-commande-dev/donnees/courrier/pdv11768@mousquetaires.com-2026-09-14/livraison 14.09.2026.xlsx>), feuille **Mercalys**.

| Cellule | Valeur source |
|---|---|
| A2 / A4 | Export du 14/09/2026 à 05:09:54 ; commande du 12/09/2026 |
| A18 / D18 | `0000087004282` / POMELO ROUGE PIECE |
| G18 / H18 / L18 | Base 45 / 1 colis commandé / Pièce |
| N18 / O18 / P18 | Afrique du Sud / Star Ruby / **4** |
| E18 | Prix de cession 0,50 |

Le [fichier du 09/09](<C:/Users/user/Desktop/preparation-commande-dev/donnees/courrier/2026-09-09-reprise-cache-controlee/livraison 09.09.2026.xlsx>), **Mercalys A16, G16, L16, O16, P16**, présente déjà le même article, 45 pièces et calibre 4. L’export du 15/09 lu ne contient pas ce code.

Dans le [cadencier du 15/09](<C:/Users/user/Desktop/preparation-commande-dev/donnees/courrier/2026-09-15-pdv11768-mousquetaires.com/cadencier webtelevente 15.09.2026.xls>), feuille **Sheet0**, **A150/D150/E150** décrit calibre 4 / PCB 45 / 0,50 ; **A151/D151/E151** décrit une autre offre calibre 5 / PCB 50 / environ 0,33. La sélection calibre 4 est donc fondée sur une colonne explicite de calibre dans les derniers exports, pas déduite du seul nombre 45.

## C05 — Carotte non lavée : la demi-cagette reste à confirmer

Le cadencier du 15/09, **Sheet0 A291/D291/E291**, annonce « CAROTTE SABLE NON LAVE FRANCE 20/45MM C 1 VRAC NON LAVEE », **PCB 12**, prix d’achat environ **1,30**. La source ne contient pas ici le mot demi-cagette.

Dans le [dernier export du 15/09](<C:/Users/user/Desktop/preparation-commande-dev/donnees/courrier/2026-09-15-pdv11768-mousquetaires.com/livraison 15.09.2026.xlsx>), **Mercalys A25/D25/G25/H25/I25/L25/P25** donne code exact, carotte non lavée, **base 1**, **1 colis**, commande du 14/09, **kg**, calibre **20/45 mm**. Les exports du 11/09, 12/09 et 14/09 ont également une base 1.

Le réglage historique 5 kg et les faits déjà enregistrés avec 5 kg ne résolvent pas cette preuve manquante : ils peuvent reprendre le réglage existant. Il n’est pas possible d’affirmer « le dernier colis pesait 5 kg » à partir de la seule base 1 du fichier source. De même, le PCB 12 du cadencier ne prouve pas le poids d’une demi-cagette réellement reçue.

**Conclusion : aucune modification proposée comme certaine.** Il reste à confirmer le poids net de la demi-cagette commandée/reçue et à quelle offre elle correspond. Aucun 6 kg n’est déduit automatiquement de 12.

## C06 — Carotte vrac : passage documenté de 10 à 12 kg

| Export source | Feuille/cellules | Base, unité, variété, calibre |
|---|---|---|
| 10/09 | Mercalys A53/G53/H53/L53/O53/P53 | **10**, 2 colis, kg, PRIMEUR, **20/50 mm** |
| 11/09 | Mercalys A57/G57/H57/L57/O57/P57 | **12**, 2 colis, kg, CONSERVATION, **20/45 mm** |
| 12/09 | Mercalys A56/G56/H56/L56/O56/P56 | **12**, 4 colis, kg, CONSERVATION, **20/45 mm** |
| 14/09 | Mercalys A64/G64/H64/L64/O64/P64 | **12**, 5 colis, kg, CONSERVATION, **20/45 mm** |

Fichiers : [10/09](<C:/Users/user/Desktop/preparation-commande-dev/donnees/courrier/pdv11768@mousquetaires.com-2026-09-11/livraison 10.09.2026.xlsx>), [11/09](<C:/Users/user/Desktop/preparation-commande-dev/donnees/courrier/pdv11768@mousquetaires.com-2026-09-11/livraison 11.09.2026.xlsx>), [12/09](<C:/Users/user/Desktop/preparation-commande-dev/donnees/courrier/2026-09-12-pdv11768-mousquetaires.com/livraison 12.09.2026.xlsx>), [14/09](<C:/Users/user/Desktop/preparation-commande-dev/donnees/courrier/pdv11768@mousquetaires.com-2026-09-14/livraison 14.09.2026.xlsx>). Le 15/09 ne contient pas ce code dans les exports lus.

Le cadencier du 15/09 distingue **Sheet0 A299/D299** (20/45 mm, PCB 12), **A300/D300** (20/50 mm, PCB 10) et **A301/D301** (28/40 mm, PCB 12). La dernière série d’exports correspond à l’offre conservation 20/45 mm et 12 kg, sans démontrer qu’une autre offre ne sera plus jamais commandée.

## C07 — Échalote Pomona : 5 kg

Original : bordereau **TerreAzur, groupe Pomona n° 7835384670 du 12/09/2026**, [page 1](C:/Users/user/Desktop/preparation-commande-dev/donnees/courrier/2026-09-12-Antoine-Parraga/20260912_110144.jpg) et [page 2](C:/Users/user/Desktop/preparation-commande-dev/donnees/courrier/2026-09-12-Antoine-Parraga/20260912_110156.jpg), toutes deux lues.

**Page 1/2, ligne imprimée 30, article 106051 :** « Echalote td 1/2 lg 30/50 5K c1 FR ». Qté livrée **1,000 COL** ; Qté fact. UF **5,000 KG** ; PU **1,600** ; MT HT **8,00**. Le libellé 5K et la colonne KG appuient la quantité physique, en plus du nombre de colis. « 1/2 lg » appartient au libellé d’échalote ; il ne prouve pas une demi-cagette de C05.

Le [mapping fournisseur existant](C:/Users/user/Desktop/preparation-commande-dev/donnees/fournisseurs/codes-terreazur.json), entrée `codes.106051`, renvoie à **0000087004662**. Le fait existant du 12/09 est repérable dans [faits/2026.jsonl:43202](C:/Users/user/Desktop/preparation-commande-dev/donnees/faits/2026.jsonl:43202), avec ce bordereau ; aucun nouveau fait n’est nécessaire pour prouver ce qui est déjà conservé.

Le bordereau local plus récent du 14/09 a aussi été lu sur ses deux pages : il ne contient pas d’échalote. La preuve la plus récente trouvée pour ce produit est donc celle du 12/09. Le cadencier Webtelevente **Sheet0 A363/D363** propose une échalote 6 kg ; cette différence ne contredit pas le fournisseur Pomona confirmé par le responsable.

## C08 — Oignon rouge Pomona : 5 kg

Original : bordereau **TerreAzur, groupe Pomona n° 7835385131 du 14/09/2026**, [page 1](C:/Users/user/Desktop/preparation-commande-dev/donnees/courrier/parraga.antoine@gmail.com-2026-09-14/20260914_120258.jpg) et [page 2](C:/Users/user/Desktop/preparation-commande-dev/donnees/courrier/parraga.antoine@gmail.com-2026-09-14/20260914_120309.jpg), toutes deux lues.

**Page 1/2, ligne imprimée 110, article 106535 :** « Oignon rge 60/80 5K c1 FR ». Qté livrée **1,000 COL** ; Qté fact. UF **5,000 KG** ; PU **1,390** ; MT HT **6,95**. Les preuves concernent précisément l’oignon **rouge** et son calibre 60/80, pas tout article nommé OIGNON.

Le mapping `codes.106535` renvoie à **0000087004082**. Le fait existant est repérable dans [faits/2026.jsonl:44204](C:/Users/user/Desktop/preparation-commande-dev/donnees/faits/2026.jsonl:44204). Le cadencier Webtelevente **Sheet0 A411/D411** propose une autre offre rouge 60/80 avec PCB 6 ; aucun motif ne permet de substituer ce 6 au colis Pomona documenté.

## C09 — Sacs 2,5 kg : confirmation humaine, deux formats et historique à préserver

La demande source confirme explicitement : **55 sacs de 2,5 kg par box**, **6 sacs de 2,5 kg par caisse**, et l’ancien choix 8 provenait des sacs de 2 kg. Le cadencier du 15/09, **Sheet0 A472/D472** et **A473/D473**, porte deux offres au même libellé « […] FILET 2,5 Kg […] » avec PCB **55** et **6**. Il confirme la coexistence des formats ; leur dénomination box/caisse vient du responsable.

Dernier export : **Mercalys A53/D53/G53/H53/I53/L53** du fichier du 15/09 : code **0000087010621**, libellé **2.5KG**, base **6**, deux colis commandés, commande du 14/09, mais **unité source `kg`**. Cette unité est incohérente avec la confirmation physique « 6 sacs × 2,5 kg » si la base est lue comme un poids : six sacs représentent **15 kg**, pas 6 kg. Le box confirmé représente **137,5 kg**, sans que 137,5 devienne un PCB en sacs.

Les faits historiques présentent notamment un ancien membre `0000087010806` (« PDT CHAIR FERME BLONDE 2KG CQL »), déjà rattaché au code canonique **0000087010621**, avec base 8. Les nouveaux relevés actuels ne donnent pas l’autorisation de réécrire ces mouvements ou de reconvertir silencieusement un ancien comptage. La quantité historique et l’unité ERP ambiguë demandent un contrôle distinct si une correction de faits est envisagée.

**Recommandation :** utiliser la confirmation pour le réglage commercial actuel en **sacs de 2,5 kg**, avec le format caisse 6 et le format box 55 distincts. Ne pas importer de livraison à partir de cette enquête. Le contrôleur doit vérifier l’effet du nouveau réglage sur les positions et conserver les faits/comptages antérieurs ; aucune quantité de stock n’a été recalculée ici.

## Contrôles et limites

- Aucune commande d’import, de recalcul, de publication de chat, d’acquittement, de relève IMAP ou de SMTP n’a été exécutée.
- Tous les contenus Excel lus sont restés identiques à leur empreinte initiale. Les seuls fichiers créés par cette enquête sont le présent rapport et ses deux preuves JSON privées ; aucun original n’a été réécrit.
- « Dernier » signifie dernier document local retrouvé dans le périmètre examiné. Cela ne prouve pas l’absence d’un mail ou d’une livraison non encore conservés localement.
- Les sources datées 09/09 ne sont pas toutes identiques : un fichier portant ce nom a une date interne du 10/09 et une commande du 08/09 ; la preuve JSON garde ces différences. Le nom de fichier n’a pas remplacé la date interne.
- La compétence Spreadsheets a été appliquée à la lecture et à la traçabilité cellule par cellule. Les photos originales ont été inspectées directement ; aucun PDF utile à ces articles n’a été trouvé dans les dossiers ciblés, aucun OCR n’a été présenté comme une lecture certaine.
- Restent réellement ouverts : **C05**, et le contrôle de l’unité/du devenir historique des faits C09 si une correction de stock distincte est envisagée. C04, C06, C07 et C08 disposent désormais des sources précises ci-dessus, sans transformer une observation récente en règle universelle.
