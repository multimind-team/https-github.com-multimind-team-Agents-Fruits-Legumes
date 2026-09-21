"""
Intègre les fichiers du magasin dans les carnets — ventes, casse, dons, livraisons.

C'est le chaînon qui manquait pour que preparation-commande vive sans l'ancienne
application : jusqu'au 3 septembre 2026, il ne savait reprendre que
l'historique déjà constitué. Les fichiers Excel qui arrivent chaque
matin par mail n'avaient aucun chemin vers les carnets.

RÔLE DE CE PROGRAMME, ET LIMITE DE SON RÔLE

Le responsable de rayon a tranché le 2026-09-03 :

  « On passe par un script Python, mais l'agent doit analyser, vérifier et
    corriger s'il le peut, ou m'alerter s'il ne comprend pas. »

Ce programme fait donc le geste MÉCANIQUE, toujours de la même façon : ouvrir
le fichier, retrouver les colonnes, convertir en mouvements, écrire sans jamais
compter deux fois la même chose.

Il ne devine RIEN. Tout ce qui sort de l'ordinaire est mis de côté et signalé
dans un compte rendu (donnees/dernier-import.json) : un article inconnu, une
colonne qui a bougé, une date incohérente, une quantité invraisemblable, un
fichier attendu qui n'est pas là.

C'est ensuite à l'agent de lire ce compte rendu, de comprendre, de corriger ce
qu'il peut et d'alerter le responsable de rayon sur le reste. Le programme ne juge pas ; l'agent
juge mais ne recopie pas 173 lignes à la main.

Usage :
  python moteur/integrer-fichiers.py <dossier>       intègre tout un dossier
  python moteur/integrer-fichiers.py <fichier.xlsx>  un seul fichier
  python moteur/integrer-fichiers.py --courrier      tout ce qui est arrivé par mail
  ... avec --simuler pour voir sans rien écrire
"""
import argparse
import hashlib
import json
from ecriture_derivee import ecrire_json
import math
import re
import sys
from collections import defaultdict, Counter
from datetime import date, datetime, timedelta
from pathlib import Path

MOTEUR = Path(__file__).resolve().parent
sys.path.insert(0, str(MOTEUR))
import catalogue
import journal_agents
import regles
from verrou_donnees import verrou_donnees, append_jsonl

RACINE = MOTEUR.parent
DONNEES = RACINE / "donnees"
DOSSIER_FAITS = DONNEES / "faits"
COMPTE_RENDU = DONNEES / "dernier-import.json"

# Repris à l'identique de la reprise des archives : un lot de bananes ne retire
# pas une unité du stock mais autant de fruits qu'il en contient.
BANANES_PAR_LOT = {"0000087430013": 3, "0000099034238": 4,
                   "0000087430015": 5, "0000087430016": 6}

# Le nom du fichier dit ce qu'il contient. On ne devine pas au-delà.
TYPES = {"vente": "vente", "casse": "casse", "don": "don", "dons": "don",
         "livraison": "livraison"}
# Une journée sans casse ni don est normale : leur absence ne signale rien.
TYPES_ATTENDUS = {"vente", "livraison"}

# Au-delà, on n'écrit pas : on signale. Une vente de 5 000 unités en un jour sur
# un rayon de cette taille est une erreur de fichier, pas une journée record.
QUANTITE_INVRAISEMBLABLE = 5000


def est_dimanche(iso):
    a, m, j = (int(x) for x in iso.split("-"))
    return date(a, m, j).weekday() == 6


def decaler(iso, jours):
    a, m, j = (int(x) for x in iso.split("-"))
    return (date(a, m, j) + timedelta(days=jours)).isoformat()


def date_reception(date_commande):
    """La marchandise entre en chambre froide le jour ouvré suivant la commande.
    Pas de livraison le dimanche : la commande du samedi arrive le lundi."""
    if not date_commande:
        return None
    recu = decaler(date_commande, 1)
    return decaler(recu, 1) if est_dimanche(recu) else recu


def vers_iso(valeur):
    if valeur is None:
        return None
    if isinstance(valeur, datetime):
        return valeur.date().isoformat()
    if isinstance(valeur, date):
        return valeur.isoformat()
    texte = str(valeur).strip()
    try:
        if re.fullmatch(r"\d{2}/\d{2}/\d{4}", texte):
            return datetime.strptime(texte, "%d/%m/%Y").date().isoformat()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", texte):
            return date.fromisoformat(texte).isoformat()
        if re.match(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}", texte):
            return datetime.fromisoformat(texte).date().isoformat()
    except ValueError:
        pass
    return None


def periode_selection(entete):
    """Dates affichées dans l'en-tête d'un export Mercalys non détaillé."""
    texte = " ".join(str(cellule) for ligne in entete for cellule in ligne if cellule)
    trouve = re.search(
        r"[Ss]élection de données\s*:\s*Du\s+(\d{2}/\d{2}/\d{4})\s+Au\s+(\d{2}/\d{2}/\d{4})",
        texte,
    )
    if not trouve:
        return None
    return vers_iso(trouve.group(1)), vers_iso(trouve.group(2))


def nombre(valeur):
    if valeur in ("", None) or isinstance(valeur, bool):
        return None
    try:
        resultat = float(str(valeur).replace(",", ".").replace(" ", ""))
        return resultat if math.isfinite(resultat) else None
    except (TypeError, ValueError):
        return None          # None = illisible, ce n'est pas zéro


def nettoyer_code_article(valeur):
    """Normalise un code article provenant d'Excel sous forme numérique ou texte.
    Rend (code_normalise, est_ligne_total).
    """
    if valeur in ("", None) or isinstance(valeur, bool):
        return None, True
    if isinstance(valeur, (int, float)):
        if not math.isfinite(valeur) or valeur < 0 or int(valeur) != valeur:
            return None, False
        valeur = str(int(valeur))
    brut = str(valeur).strip()
    if not brut:
        return None, True
    if brut.endswith(".0"):
        partie = brut[:-2].strip()
        if partie.isdigit():
            brut = partie
    if re.fullmatch(r"\d{8,13}", brut):
        return brut, False
    if re.fullmatch(r"\d{1,7}", brut):
        return brut.zfill(13), False
    texte_lower = brut.lower()
    if any(mot in texte_lower for mot in ("total", "nombre", "lignes", "sous-total", "cumul")):
        return None, True
    return None, False


def lire_tableau(chemin):
    """Rend (colonnes, lignes). Les fichiers du magasin ont un en-tête de
    plusieurs lignes avant le vrai tableau : on cherche la ligne des titres au
    lieu de supposer qu'elle est toujours au même endroit."""
    entetes_connues = ("itm8 prio", "code itm")
    if chemin.suffix.lower() == ".xls":
        import xlrd
        classeur = xlrd.open_workbook(str(chemin))
        feuille = classeur.sheet_by_index(0)
        toutes = [[feuille.cell_value(r, c) for c in range(feuille.ncols)]
                  for r in range(feuille.nrows)]
    else:
        import openpyxl
        classeur = openpyxl.load_workbook(chemin, read_only=True, data_only=True)
        toutes = [list(r) for r in classeur.active.iter_rows(values_only=True)]
        classeur.close()

    for i, ligne in enumerate(toutes):
        premiere = str(ligne[0] or "").strip().lower()
        if premiere in entetes_connues:
            colonnes = [str(c).strip() if c is not None else "" for c in ligne]
            return colonnes, toutes[i + 1:], toutes[:i]
    return None, [], toutes


def date_du_fichier(nom):
    m = re.search(r"(\d{2})[.\-](\d{2})[.\-](\d{4})", nom)
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None


def type_du_fichier(nom):
    debut = re.match(r"([a-z]+)(?:[-_.\s]|$)", nom.lower())
    return TYPES.get(debut.group(1)) if debut else None


def message_alerte_chat(alertes, mouvements_nouveaux):
    """Formule pour le chat l'état vérifié d'un import incomplet."""
    sujets = [str(alerte.get("sujet") or "fichier inconnu") for alerte in alertes[:3]]
    complement = " ; ".join(sujets)
    if len(alertes) > len(sujets):
        complement += f" ; et {len(alertes) - len(sujets)} autre(s)"
    return (f"⚠ Import incomplet : {mouvements_nouveaux} mouvements intégrés, "
            f"{len(alertes)} point(s) à vérifier — {complement}. "
            "Aucune donnée non vérifiée n'a été ajoutée.")


def types_absents_par_jour(resume):
    """Retourne les types manquants pour chaque journée réellement couverte."""
    presents_par_jour = {}
    for entree in resume:
        jour = date_du_fichier(entree["fichier"])
        if jour:
            presents_par_jour.setdefault(jour, set()).add(entree["type"])
    attendus = TYPES_ATTENDUS
    return {
        jour: attendus - presents
        for jour, presents in presents_par_jour.items()
        if attendus - presents
    }


def charger_colisages_vrac():
    """Charge les colisages des articles vrac : d'abord décisions magasin, puis cadencier."""
    colisages = {}
    fichier_cadencier = DONNEES / "cadencier-du-jour.json"
    if fichier_cadencier.exists():
        cad = json.loads(fichier_cadencier.read_text(encoding="utf-8"))
        for a in cad.get("articles", []):
            code = a.get("article")
            if code and a.get("offres"):
                pcb = a["offres"][0].get("par_colis")
                if pcb and float(pcb) > 0:
                    colisages[code] = float(pcb)
    config = regles.charger()
    for code, surch in config.get("overrides", {}).items():
        if "conditionnement" in surch:
            valeur = surch["conditionnement"]
            try:
                c = float(valeur)
            except (ValueError, TypeError) as exc:
                raise ValueError(f"Colisage de décision invalide pour {code} : import interrompu.") from exc
            if isinstance(valeur, bool) or not math.isfinite(c) or c <= 0:
                raise ValueError(f"Colisage de décision invalide pour {code} : import interrompu.")
            colisages[code] = c
    return colisages


def est_article_vrac(libelle, unite):
    """Détecte si un article est vendu au poids (vrac en kg).
    Les sacs/filets de 5 kg vendus à la pièce/filet ne sont pas du vrac."""
    lib = (libelle or "").upper()
    u = (unite or "").strip().lower()
    if "VRAC" in lib:
        return True
    if "5KG" in lib and ("FILET" in lib or "PDT" in lib):
        return False
    if u == "kg" and not any(mot in lib for mot in ("FILET", "SACHET", "BARQUETTE", "PIECE", "PIÈCE", "BTE", "BOITE")):
        return True
    return False


def dimension_unite(unite, *, catalogue_source=False):
    # Le préfixe du catalogue est un code de type (ex. « 2 kg »).
    # Les exports de livraison attestent explicitement « kg » ou « Pièce ».
    texte = str(unite or "").strip().casefold()
    if catalogue_source:
        texte = re.sub(r"^\d+\s+", "", texte)
    if texte in {"kg", "kilogramme", "kilogrammes"}:
        return "masse-kg"
    if texte in {"pièce", "piece", "pièces", "pieces", "barquette", "boite", "boîte",
                 "filet", "plateau", "sachet", "botte"}:
        return "nombre"
    if texte in {"l", "litre", "litres"}:
        return "volume-l"
    return None


def convertir(chemin, vers_principal, noms_catalogue, signaler, colisages_vrac=None):
    """Transforme un fichier en mouvements. Tout ce qui cloche est signalé,
    jamais deviné."""
    type_fait = type_du_fichier(chemin.name)
    if not type_fait:
        signaler("fichier-inconnu", chemin.name,
                 "Le nom ne dit pas ce que contient ce fichier. Non intégré.")
        return []

    colonnes, lignes, entete = lire_tableau(chemin)
    if colonnes is None:
        signaler("colonnes-introuvables", chemin.name,
                 "Impossible de retrouver la ligne des titres — le format a "
                 "peut-être changé. RIEN n'a été intégré de ce fichier.")
        return []

    index = {nom.strip().lower(): i for i, nom in enumerate(colonnes) if nom}

    def col(*noms):
        for n in noms:
            if n.lower() in index:
                return index[n.lower()]
        return None

    faits = []
    if type_fait == "livraison":
        # La date de commande est dans l'en-tête, pas dans les lignes.
        date_commande = None
        for ligne in entete:
            texte = " ".join(str(c) for c in ligne if c)
            m = re.search(r"[Cc]ommande du\s+(\d{2}/\d{2}/\d{4})", texte)
            if m:
                date_commande = vers_iso(m.group(1))
                break
        date_commande = date_commande or date_du_fichier(chemin.name)
        if not date_commande:
            signaler("date-introuvable", chemin.name,
                     "Aucune date de commande trouvée. RIEN n'a été intégré.")
            return []

        i_code = col("Code ITM")
        i_lib = col("Libellé article", "Libelle article")
        i_cond = col("Cond. de base")
        i_colis = col("Qté cmdée (nbre colis)", "Qte cmdee (nbre colis)")
        i_unite = col("Unité de mesure", "Unite de mesure")
        if i_code is None or i_colis is None:
            signaler("colonnes-manquantes", chemin.name,
                     f"Colonnes attendues absentes (trouvé : {', '.join(colonnes[:8])}). "
                     "RIEN n'a été intégré.")
            return []

        if colisages_vrac is None:
            colisages_vrac = charger_colisages_vrac()

        for n, ligne in enumerate(lignes):
            code, est_total = nettoyer_code_article(ligne[i_code])
            if est_total:
                continue
            if not code:
                signaler("code-invalide", str(ligne[i_code]),
                         f"{chemin.name} ligne {n + 2} : code article invalide « {ligne[i_code]} ».")
                continue
            brut = code
            colis = nombre(ligne[i_colis])
            if colis is None:
                signaler("quantite-illisible", brut,
                         f"{chemin.name} ligne {n + 2} : nombre de colis illisible.")
                continue
            if colis == 0:
                continue
            par_colis = nombre(ligne[i_cond]) if i_cond is not None else None
            libelle = (str(ligne[i_lib]).strip() if i_lib is not None and ligne[i_lib] else "")
            unite = (str(ligne[i_unite]).strip() if i_unite is not None and ligne[i_unite] else "inconnue")
            principal = vers_principal.get(brut, brut)
            unite_catalogue = catalogue.unite(principal) if principal in noms_catalogue else ""
            dimension_source = dimension_unite(unite)
            dimension_cible = dimension_unite(unite_catalogue, catalogue_source=True)
            if not dimension_source or (unite_catalogue and dimension_source != dimension_cible):
                signaler("unite-non-prouvee", brut,
                         f"{chemin.name} ligne {n + 2} : unité source absente ou incompatible "
                         f"avec le catalogue ({unite} / {unite_catalogue or 'non référencé'}). "
                         "Livraison non intégrée.")
                continue

            # Une base de facturation 1 ne prouve pas le poids du colis livré.
            if (par_colis == 1.0 or par_colis is None) and est_article_vrac(libelle, unite):
                signaler("conversion-non-prouvee", brut,
                         f"{chemin.name} ligne {n + 2} : poids livré par colis non attesté "
                         "(base absente ou égale à 1). Livraison non intégrée ; "
                         "le colisage habituel ne prouve pas le colis livré.")
                continue

            if par_colis is None or par_colis <= 0:
                signaler("conditionnement-invalide", brut,
                         f"{chemin.name} ligne {n + 2} : conditionnement absent ou invalide. "
                         "Livraison non intégrée : ne jamais supposer un colisage.")
                continue
            quantite = colis * par_colis
            faits.append({
                "id": f"livraison:{date_commande}:{brut}:{n}",
                "type": "livraison",
                "date_source": date_commande,
                "date_effet": date_reception(date_commande),
                "article": principal,
                "article_source": brut,
                "quantite": round(quantite, 3),
                "unite": unite,
                "libelle": libelle,
                "colis": colis,
                "par_colis": par_colis,
                "source": {"origine": f"mail/{chemin.name}", "ligne": n + 2,
                           "unite_source": unite, "unite_catalogue": unite_catalogue,
                           "conversion": "colis_source * conditionnement_source"},
            })
    else:
        i_code = col("ITM8 Prio")
        i_lib = col("Libellé", "Libelle")
        i_date = col("Date")
        i_qte = col("Quantité", "Quantite")
        # Le fichier de vente donne aussi ce qui a vraiment été payé et vendu
        # ce jour-là (colonnes "Valeur prix achat"/"Valeur prix vente", des
        # MONTANTS pour la quantité de la ligne, pas un prix unitaire) — la
        # seule vraie source du prix de vente. Le catalogue.json ne l'est pas :
        # c'est une photo figée du 3 septembre, jamais remise à jour depuis
        # (trouvé le 2026-09-04, le responsable de rayon a demandé la correction).
        i_valeur_achat = col("Valeur prix achat") if type_fait == "vente" else None
        i_valeur_vente = col("Valeur prix vente") if type_fait == "vente" else None
        if i_code is None or i_qte is None:
            signaler("colonnes-manquantes", chemin.name,
                     f"Colonnes attendues absentes (trouvé : {', '.join(colonnes[:8])}). "
                     "RIEN n'a été intégré.")
            return []
        texte_entete = " ".join(str(c) for ligne in entete for c in ligne if c)
        generation = re.search(r"\bDate\s*:\s*(\d{2}/\d{2}/\d{4})", texte_entete, re.IGNORECASE)
        date_generation = vers_iso(generation.group(1)) if generation else date_du_fichier(chemin.name)
        date_commune = None
        if i_date is None:
            periode = periode_selection(entete)
            if not periode or periode[0] != periode[1]:
                etendue = (f"du {periode[0]} au {periode[1]}" if periode else
                            "dont la période n'est pas lisible")
                signaler(
                    "periode-non-detaillee", chemin.name,
                    "La colonne Date est absente et l'export couvre " + etendue +
                    ". Les quantités cumulées ne peuvent pas être réparties sans inventer. "
                    "RIEN n'a été intégré.",
                )
                return []
            date_commune = periode[0]

        for n, ligne in enumerate(lignes):
            code, est_total = nettoyer_code_article(ligne[i_code])
            if est_total:
                continue
            if not code:
                signaler("code-invalide", str(ligne[i_code]),
                         f"{chemin.name} ligne {n + 2} : code article invalide « {ligne[i_code]} ».")
                continue
            brut = code
            jour = date_commune if i_date is None else vers_iso(ligne[i_date])
            if not jour:
                signaler("date-illisible", brut,
                         f"{chemin.name} ligne {n + 2} : date « {ligne[i_date]} » illisible.")
                continue
            if date_generation and jour >= date_generation:
                signaler("journee-incomplete", brut,
                         f"{chemin.name} ligne {n + 2} : journée {jour} non close à la génération "
                         f"du fichier ({date_generation}). Mouvement non intégré.")
                continue
            quantite = nombre(ligne[i_qte])
            if quantite is None:
                signaler("quantite-illisible", brut,
                         f"{chemin.name} ligne {n + 2} : quantité illisible.")
                continue
            # Un lot de bananes retire plusieurs fruits, pas un seul.
            quantite = quantite * BANANES_PAR_LOT.get(brut, 1)
            fait = {
                "id": f"{type_fait}:{jour}:{brut}:{n}",
                "type": type_fait,
                "date_source": jour,
                "date_effet": jour,
                "article": vers_principal.get(brut, brut),
                "article_source": brut,
                "quantite": round(quantite, 3),
                "unite": "inconnue",
                "libelle": (str(ligne[i_lib]).strip() if i_lib is not None and ligne[i_lib] else ""),
                "source": {"origine": f"mail/{chemin.name}", "ligne": n + 2},
            }
            if quantite:
                if i_valeur_vente is not None:
                    valeur_vente = nombre(ligne[i_valeur_vente])
                    if valeur_vente is not None:
                        fait["prix_vente_unitaire"] = round(valeur_vente / quantite, 4)
                if i_valeur_achat is not None:
                    valeur_achat = nombre(ligne[i_valeur_achat])
                    if valeur_achat is not None:
                        fait["prix_achat_unitaire"] = round(valeur_achat / quantite, 4)
            faits.append(fait)

    # Contrôles de bon sens, faits APRÈS la conversion : on signale, on n'écarte
    # pas — sauf l'invraisemblable, qui serait plus dangereux qu'utile.
    gardes = []
    for fait in faits:
        if abs(fait["quantite"]) > QUANTITE_INVRAISEMBLABLE:
            signaler("quantite-invraisemblable", fait["article_source"],
                     f"{fait['quantite']} en une journée ({fait['libelle']}). "
                     "Non intégré : à vérifier dans le fichier.")
            continue
        if fait["article_source"] not in noms_catalogue:
            signaler("article-inconnu", fait["article_source"],
                     f"« {fait['libelle']} » n'est pas au catalogue. Le mouvement est "
                     "quand même enregistré, mais l'article ne pourra pas être commandé.")
        gardes.append(fait)
    occurrences = Counter()
    for fait in gardes:
        empreinte = hashlib.sha256(signature_mouvement(fait).encode("utf-8")).hexdigest()
        occurrences[empreinte] += 1
        fait["id"] = f"import-v2:{empreinte}:{occurrences[empreinte]}"
    return gardes


def cle_mouvement(fait):
    return tuple(fait.get(cle) for cle in
                 ("type", "date_source", "date_effet", "article_source"))


def signature_mouvement(fait):
    # Ni le rang, ni le nom du fichier, ni le libellé ne changent la mesure.
    champs = ("type", "date_source", "date_effet", "article_source", "quantite",
              "unite", "colis", "par_colis", "prix_vente_unitaire", "prix_achat_unitaire")
    contenu = {cle: fait.get(cle) for cle in champs}
    for cle, valeur in contenu.items():
        if isinstance(valeur, (int, float)):
            contenu[cle] = float(valeur)
    return json.dumps(contenu, sort_keys=True, ensure_ascii=False, allow_nan=False)


def ecrire(faits, simuler=False):
    """Ajoute aux carnets, un fichier par année, sans jamais compter deux fois."""
    if simuler:
        return _ecrire(faits, simuler=True)
    dossier_donnees = DOSSIER_FAITS.parent if DOSSIER_FAITS.name == "faits" else DOSSIER_FAITS
    with verrou_donnees(dossier_donnees):
        return _ecrire(faits)


def _ecrire(faits, simuler=False):
    import faits as carnet
    existants = list(carnet.lire(DOSSIER_FAITS))
    connues = {f['id']: carnet.signature(f) for f in existants if f.get('id')}
    # Reconnaître aussi les anciens identifiants à rang, sans réécrire les carnets.
    anciens = defaultdict(Counter)
    for fait in existants:
        if (str(fait.get("id", "")).startswith("import-v2:") or
                re.fullmatch(r"(?:vente|casse|don|livraison):\d{4}-\d{2}-\d{2}:\d+:\d+",
                             str(fait.get("id", "")))):
            anciens[cle_mouvement(fait)][signature_mouvement(fait)] += 1
    consommes = Counter()
    lot_ids = {}
    nouveaux = []
    for fait in faits:
        if str(fait.get("id", "")).startswith("import-v2:"):
            if fait["id"] in lot_ids:
                if lot_ids[fait["id"]] != carnet.signature(fait):
                    raise ValueError(f"Fait {fait['id']} en conflit dans le lot ; aucun ajout.")
                continue
            lot_ids[fait["id"]] = carnet.signature(fait)
            cle, mesure = cle_mouvement(fait), signature_mouvement(fait)
            if cle in anciens:
                consommes[(cle, mesure)] += 1
                if consommes[(cle, mesure)] > anciens[cle][mesure]:
                    raise ValueError(f"Chevauchement d'import pour {cle} : contenu ou nombre de lignes "
                                     "différent. Correction explicite requise ; aucun fait du lot ajouté.")
                continue
        signature = carnet.signature(fait)
        if fait["id"] in connues and connues[fait["id"]] != signature:
            raise ValueError(f"Fait {fait['id']} en conflit avec une saisie existante ; aucun fait du lot ajouté.")
        if fait["id"] not in connues:
            nouveaux.append(fait)
            connues[fait["id"]] = signature
    for cle in {cle for cle, mesure in consommes}:
        recu = Counter({mesure: quantite for (groupe, mesure), quantite in consommes.items() if groupe == cle})
        if recu != anciens[cle]:
            raise ValueError(f"Chevauchement d'import pour {cle} : nombre de lignes différent. "
                             "Correction explicite requise ; aucun fait du lot ajouté.")
    deja = len(faits) - len(nouveaux)
    if simuler:
        return nouveaux, deja
    par_annee = defaultdict(list)
    for fait in nouveaux:
        par_annee[(fait["date_effet"] or fait["date_source"])[:4]].append(fait)
    DOSSIER_FAITS.mkdir(parents=True, exist_ok=True)
    for annee, lot in par_annee.items():
        append_jsonl(DOSSIER_FAITS / f"{annee}.jsonl", lot)
    return nouveaux, deja


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("chemin", nargs="?", help="un fichier ou un dossier")
    p.add_argument("--courrier", action="store_true",
                   help="tout ce qui est arrivé par mail (donnees/courrier/)")
    p.add_argument("--simuler", action="store_true")
    p.add_argument("--agent", default="agent-donnees")
    p.add_argument("--json", action="store_true", help="Résultat structuré uniquement")
    args = p.parse_args()
    if args.json:
        # Conserver les diagnostics existants sur stderr et un seul objet JSON stdout.
        import contextlib
        sortie_json = sys.stdout
        with contextlib.redirect_stdout(sys.stderr):
            return executer_import(args, sortie_json)
    return executer_import(args)


def executer_import(args, sortie_json=None):
    if not args.simuler:
        with verrou_donnees(DONNEES):
            return _executer_import(args, sortie_json)
    return _executer_import(args, sortie_json)


def _executer_import(args, sortie_json=None):

    if args.courrier:
        fichiers = sorted((DONNEES / "courrier").rglob("*.xls*"))
    elif args.chemin:
        cible = Path(args.chemin)
        if not cible.exists():
            sys.exit(f"Introuvable : {cible}")
        fichiers = sorted(cible.rglob("*.xls*")) if cible.is_dir() else [cible]
    else:
        print("Indiquer un chemin ou --courrier.")
        return 1

    # Les cadenciers ne sont pas des mouvements : ils décrivent les articles.
    fichiers = [f for f in fichiers if not f.name.lower().startswith("cadencier")
                and not f.name.startswith("~$")]
    if not fichiers:
        resultat = {"statut": "a-verifier", "fichiers": [], "a_verifier": [
            {"genre": "fichier-absent", "message": "Aucun fichier de mouvements à intégrer"}]}
        print(json.dumps(resultat, ensure_ascii=False), file=sortie_json or sys.stdout)
        return 3

    alertes = []
    def signaler(genre, quoi, message):
        alertes.append({"genre": genre, "sujet": quoi, "message": message})

    config = regles.charger()
    vers_principal = {m: p for p, membres in config["groupes"].items() for m in membres}
    noms_catalogue = set(catalogue.articles())
    colisages_vrac = charger_colisages_vrac()

    tous, resume = [], []
    for chemin in fichiers:
        faits = convertir(chemin, vers_principal, noms_catalogue, signaler, colisages_vrac)
        tous.extend(faits)
        resume.append({"fichier": chemin.name, "mouvements": len(faits),
                       "type": type_du_fichier(chemin.name)})
        print(f"  {chemin.name:38} {len(faits):>5} mouvements")

    nouveaux, deja = ecrire(tous, args.simuler)

    # Ce qui manque compte autant que ce qui est là, pour un lot complet (plusieurs fichiers ou --courrier).
    jours = {f["date_source"] for f in tous}
    if len(fichiers) > 1 or args.courrier:
        for jour, manquants in sorted(types_absents_par_jour(resume).items()):
            for attendu in sorted(manquants):
                signaler("fichier-absent", f"{attendu} ({jour})",
                         f"Aucun fichier « {attendu} » pour le {jour} dans ce lot. "
                         "Est-ce normal, ou manque-t-il un envoi ?")

    compte_rendu = {
        "statut": "a-verifier" if alertes else "simulation" if args.simuler else "ok",
        "quand": datetime.now().isoformat(timespec="seconds"),
        "simulation": args.simuler,
        "fichiers": resume,
        "mouvements_nouveaux": len(nouveaux),
        "mouvements_deja_connus": deja,
        "jours_couverts": sorted(jours),
        "a_verifier": alertes,
    }
    if not args.simuler:
        ecrire_json(COMPTE_RENDU, compte_rendu)
    else:
        print(json.dumps(compte_rendu, ensure_ascii=False, indent=1))

    if alertes and not args.simuler:
        import dire
        dire.publier(message_alerte_chat(alertes, len(nouveaux)), auteur="Agent Données",
                     action="import-à-vérifier")

    print(f"\n  {len(nouveaux)} mouvements ajoutés, {deja} déjà connus"
          f"{' (SIMULATION)' if args.simuler else ''}")
    if jours:
        print(f"  jours couverts : {', '.join(sorted(jours))}")

    if alertes:
        print(f"\n  {len(alertes)} POINT(S) À VÉRIFIER — c'est le travail de l'agent :")
        for a in alertes[:12]:
            print(f"    [{a['genre']}] {a['sujet']} — {a['message'][:95]}")
        if len(alertes) > 12:
            print(f"    … et {len(alertes) - 12} autres, voir {COMPTE_RENDU.name}")
    else:
        print("\n  Rien d'anormal à signaler.")

    if not args.simuler:
        journal_agents.enregistrer(
            agent=args.agent,
            message=f"{len(nouveaux)} mouvements intégrés depuis {len(fichiers)} fichier(s)",
            motif=("Intégration des fichiers du magasin. Le programme fait le geste "
                   "mécanique ; ce qu'il n'a pas compris est listé dans "
                   "dernier-import.json, à charge pour l'agent de vérifier, corriger "
                   "ou alerter le responsable de rayon."),
            annulable=False,
            details={"fichiers": resume, "nouveaux": len(nouveaux),
                     "deja_connus": deja, "a_verifier": len(alertes)})
        print("\n  Penser à relancer : agregats.py, calculer-position.py, "
              "generer-proposition.py")
        print("  (ou simplement verifier-avant-commande.bat)")
    if sortie_json:
        print(json.dumps(compte_rendu, ensure_ascii=False), file=sortie_json)
    return 3 if alertes else 0


if __name__ == "__main__":
    sys.exit(main())
