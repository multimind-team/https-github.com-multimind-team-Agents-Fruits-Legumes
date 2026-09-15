"""
moteur/analyser-ecarts-comptage.py - Analyse et explication des écarts de stock (comptage).

Ce module est l'outil déterministe de l'agent-audit-stock.
Dès qu'un comptage physique est reçu depuis la chambre froide (app/compter.html) :
1. Il compare la mesure physique au stock théorique attendu juste avant ce comptage.
2. Il calcule l'écart exact en unités et en colis (Δ = physique - théorique).
3. Il analyse méthodiquement les causes probables :
   - Règle des 17h / Matin : livraison du matin non encore entrée en chambre froide.
   - Casse non enregistrée : démarque ou pourrissement jeté sans saisie.
   - Inversion en caisse / codes jumeaux : vente scannée sous un autre code.
   - Anomalie de livraison : livraison directe non saisie, doublon ou colisage erroné.
   - Vente bloquée en caisse : code-barre non scanné.
4. Il génère un rapport structuré dans donnees/audit-comptages.json.
5. Avec --publier, il publie une explication simple et claire dans le chat mobile du rayon via dire.py.

Usage :
  python moteur/analyser-ecarts-comptage.py
  python moteur/analyser-ecarts-comptage.py --date 2026-09-11
  python moteur/analyser-ecarts-comptage.py --id <comptage_id>
  python moteur/analyser-ecarts-comptage.py --publier
"""
import argparse
import importlib.util
from collections import defaultdict
from datetime import datetime
import json
import math
from pathlib import Path
import re
import sys
import unicodedata

RACINE = Path(__file__).resolve().parent.parent
MOTEUR = RACINE / "moteur"
DONNEES = RACINE / "donnees"
DOSSIER_FAITS = DONNEES / "faits"
FICHIER_AUDIT = DONNEES / "audit-comptages.json"
FICHIER_RECEPTIONS = DONNEES / "receptions-courrier.json"

sys.path.insert(0, str(MOTEUR))
import catalogue
import faits
import regles
from verrou_donnees import operation_donnees
from ecriture_derivee import ecrire_json

_spec_position = importlib.util.spec_from_file_location("position_pour_audit", MOTEUR / "calculer-position.py")
position = importlib.util.module_from_spec(_spec_position)
_spec_position.loader.exec_module(position)
AJOUTE, RETIRE = position.AJOUTE, position.RETIRE
moment_du_comptage = position.moment_du_comptage

FRUITS_LEGUMES_PERISSABLES = {
    "tomate", "salade", "batavia", "laitue", "sucrine", "mache", "fraise", "framboise",
    "peche", "nectarine", "abricot", "raisin", "cerise", "banane", "concombre", "courgette",
    "poivron", "avocat", "melon", "pasteque", "champignon", "epinard", "haricot", "herbe",
    "persil", "coriandre", "menthe", "basilic", "radis", "figue", "prune"
}


def sans_accent(t):
    return "".join(c for c in unicodedata.normalize("NFD", t or "")
                   if unicodedata.category(c) != "Mn").lower()


def mots_cles(t):
    vides = {"vrac", "piece", "pieces", "kg", "france", "petit", "prix", "itm", "mmp",
             "de", "du", "la", "le", "les", "a", "en", "et", "cat", "import", "1", "2", "x3", "x6"}
    return {m for m in re.split(r"[^a-z0-9]+", sans_accent(t)) if m and m not in vides and len(m) > 1}


def charger_heures_reception_mail():
    if FICHIER_RECEPTIONS.exists():
        try:
            with open(FICHIER_RECEPTIONS, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def charger_faits_par_article():
    tous_faits = list(faits.lire(DOSSIER_FAITS))
    faits_par_article = defaultdict(list)
    for f in tous_faits:
        art = f.get("article")
        if art:
            faits_par_article[art].append(f)
    return faits_par_article, tous_faits


def trouver_codes_jumeaux_potentiels(itm8, libelle_cible, tous_articles):
    mots_cible = mots_cles(libelle_cible)
    if not mots_cible:
        return []
    jumeaux = []
    for code, info in tous_articles.items():
        if code == itm8:
            continue
        lib = info.get("LIBELLE") or ""
        mots_autre = mots_cles(lib)
        intersection = mots_cible & mots_autre
        if intersection and (len(intersection) >= 2 or (len(intersection) == 1 and any(m in ("banane", "melon", "avocat", "citron") for m in intersection))):
            jumeaux.append({
                "itm8": code,
                "libelle": lib,
                "mots_communs": list(intersection),
            })
    return jumeaux[:3]


def calculer_stock_theorique_avant_comptage(comptage, faits_article, heures_mail, config=None):
    resultat = position.position_avant_comptage(
        comptage, faits_article, config if config is not None else regles.charger(), heures_mail)
    return resultat.get("position"), resultat.get("depart"), resultat.get("mouvements_appliques", [])


def auditer_un_comptage(comptage, faits_article, catalogue_articles, heures_mail, tous_articles):
    itm8 = comptage["article"]
    fiche_cat = catalogue_articles.get(itm8, {})
    libelle = comptage.get("libelle") or fiche_cat.get("LIBELLE") or itm8
    unite = comptage.get("unite") or fiche_cat.get("UNITE MESURE") or "unité"
    quantite_physique = float(comptage.get("quantite") or 0.0)
    colis_physique = comptage.get("colis")
    colisage = comptage.get("conditionnement") or comptage.get("colisage")
    # La conversion attestée dans le relevé prime sur un PCB catalogue plus récent.
    if not colisage and colis_physique not in (None, 0):
        colisage = quantite_physique / float(colis_physique)
    colisage = colisage or fiche_cat.get("CONDIT.BASE") or fiche_cat.get("COLISAGE")
    try:
        colisage = float(colisage)
        if not math.isfinite(colisage) or colisage <= 0:
            colisage = None
    except (ValueError, TypeError):
        colisage = None
    colis_physique = (float(colis_physique) if colis_physique is not None else
                      quantite_physique / colisage if colisage else None)

    date_comptage = comptage.get("date_effet") or comptage.get("date_source")
    moment = moment_du_comptage(comptage, heures_mail)

    stock_theorique_unites, depart, mouvements = calculer_stock_theorique_avant_comptage(
        comptage, faits_article, heures_mail
    )
    if stock_theorique_unites is None or colisage is None:
        return {"comptage_id": comptage.get("id"), "article": itm8, "libelle": libelle,
                "date": date_comptage, "moment": moment, "colisage": colisage,
                "physique": {"colis": colis_physique, "unites": quantite_physique},
                "theorique": {"colis": None, "unites": stock_theorique_unites},
                "ecart": {"colis": None, "unites": None}, "statut": "inconnu",
                "causes_identifiees": [],
                "explication_responsable": ("Aucun stock antérieur exploitable : le stock attendu et l'écart restent inconnus."
                    if stock_theorique_unites is None else "Conditionnement du relevé inconnu : aucun écart en colis calculé.")}
    stock_theorique_colis = round(stock_theorique_unites / colisage, 2)

    ecart_unites = round(quantite_physique - stock_theorique_unites, 2)
    ecart_colis = round(colis_physique - stock_theorique_colis, 1)

    diagnostic = {
        "comptage_id": comptage.get("id"),
        "article": itm8,
        "libelle": libelle,
        "date": date_comptage,
        "horodatage": comptage.get("horodatage") or comptage.get("enregistre_le"),
        "moment": moment,
        "colisage": colisage,
        "physique": {"colis": colis_physique, "unites": quantite_physique},
        "theorique": {"colis": stock_theorique_colis, "unites": stock_theorique_unites},
        "ecart": {"colis": ecart_colis, "unites": ecart_unites},
        "statut": "conforme",
        "causes_identifiees": [],
        "explication_responsable": "",
    }

    if abs(ecart_colis) < 0.2:
        diagnostic["statut"] = "conforme"
        diagnostic["explication_responsable"] = (
            f"Stock physique conforme au stock attendu ({colis_physique:.1f} colis comptés vs "
            f"{stock_theorique_colis:.1f} attendus, écart négligeable de {ecart_colis:+.1f} colis)."
        )
        return diagnostic

    diagnostic["statut"] = "ecart_detecte"
    causes = []

    livraisons_du_jour = [m for m in mouvements if m.get("date_effet") == date_comptage and m["type"] == "livraison"]
    q_livree_jour = sum(float(m.get("quantite") or 0.0) for m in livraisons_du_jour)
    c_livres_jour = q_livree_jour / colisage

    if moment in ("soir", "avant-livraison") and c_livres_jour > 0:
        diff_sans_livraison = round(quantite_physique - (stock_theorique_unites - q_livree_jour), 2)
        if abs(diff_sans_livraison / colisage) < 0.5:
            causes.append({
                "type": "regle_17h_livraison_matin",
                "gravite": "a_verifier",
                "titre": "Écart égal à la livraison du matin : vérifier le quai et le rangement",
                "details": (
                    f"Comptage effectué à {moment} ({comptage.get('horodatage')}). "
                    f"L'écart correspond à la livraison du jour de {c_livres_jour:.1f} colis. "
                    f"Vérifier si elle était sur le quai, déjà rangée ou comptée. Cette égalité ne prouve pas sa localisation."
                ),
            })

    if ecart_unites < 0:
        casses_recentes = [m for m in mouvements if m["type"] == "casse"]
        total_casse = sum(float(m.get("quantite") or 0.0) for m in casses_recentes)
        mots_lib = mots_cles(libelle)
        est_perissable = any(p in mots_lib for p in FRUITS_LEGUMES_PERISSABLES)

        if total_casse == 0 and est_perissable:
            causes.append({
                "type": "casse_non_enregistree",
                "gravite": "forte_suspicion",
                "titre": "Suspicion de casse / pourrissement non saisi",
                "details": (
                    f"Déficit de {abs(ecart_colis):.1f} colis ({abs(ecart_unites):.1f} {unite}). "
                    f"Aucun enregistrement de casse n'a été fait sur cet article périssable récemment. "
                    f"Vérifier une éventuelle casse non saisie ; cette absence ne prouve pas qu’une marchandise a été jetée."
                ),
            })
        elif total_casse > 0:
            causes.append({
                "type": "casse_partielle",
                "gravite": "information",
                "titre": "Démarque partielle enregistrée",
                "details": (
                    f"De la casse a été enregistrée ({total_casse / colisage:.1f} colis), mais le déficit restant "
                    f"est de {abs(ecart_colis):.1f} colis."
                ),
            })

    jumeaux = trouver_codes_jumeaux_potentiels(itm8, libelle, tous_articles)
    if jumeaux:
        for jum in jumeaux:
            causes.append({
                "type": "code_jumeau_caisse",
                "gravite": "piste_serieuse",
                "titre": f"Risque d'inversion en caisse avec {jum['libelle']}",
                "details": (
                    f"Article jumeau identifié : {jum['libelle']} ({jum['itm8']}). "
                    f"Les passages en caisse ont pu être scannés ou pesés sous ce code jumeau au lieu de l'article compté."
                ),
            })

    if abs(ecart_unites) >= colisage:
        multiples = round(abs(ecart_unites) / colisage, 1)
        if abs(multiples - round(multiples)) < 0.1:
            if ecart_unites > 0:
                causes.append({
                    "type": "livraison_directe_oubli",
                    "gravite": "suspicion",
                    "titre": f"Surplus équivalent à {int(round(multiples))} colis",
                    "details": (
                        f"Le stock physique dépasse le théorique de {int(round(multiples))} colis entiers. "
                        f"Vérifier si une livraison directe (ex: Pomona, TerreAzur ou producteur) n'a pas été omise."
                    ),
                })
            else:
                causes.append({
                    "type": "livraison_double_theorique",
                    "gravite": "suspicion",
                    "titre": f"Déficit équivalent à {int(round(multiples))} colis",
                    "details": (
                        f"Le déficit correspond exactement à {int(round(multiples))} colis. "
                        f"Vérifier si une ancienne livraison n'a pas été saisie deux fois dans les carnets."
                    ),
                })

    lignes_explication = []
    signe = "+" if ecart_colis > 0 else ""
    lignes_explication.append(
        f"Article {libelle} : stock mesuré à {colis_physique:.1f} colis (attendu : {stock_theorique_colis:.1f} colis, écart : {signe}{ecart_colis:.1f} colis)."
    )

    if causes:
        diagnostic["causes_identifiees"] = causes
        for c in causes:
            lignes_explication.append(f"- {c['titre']} : {c['details']}")
    else:
        diagnostic["causes_identifiees"] = [{
            "type": "ajustement_physique",
            "gravite": "arbitrage",
            "titre": "Décalage physique à arbitrer",
            "details": f"Écart net de {signe}{ecart_colis:.1f} colis sans cause évidente répertoriée.",
        }]
        lignes_explication.append(f"- Décalage physique net de {signe}{ecart_colis:.1f} colis recalibré par votre comptage.")

    diagnostic["explication_responsable"] = "\n".join(lignes_explication)
    return diagnostic


def analyser_comptages_recents(date_cible=None, comptage_id=None, limite=20):
    faits_par_article, tous_faits = charger_faits_par_article()
    heures_mail = charger_heures_reception_mail()
    catalogue_articles = catalogue.articles()

    # Une correction remplace seulement le diagnostic du relevé qu'elle corrige.
    corrections = {f.get("cible_id"): f for f in tous_faits if f.get("type") == "correction-comptage"}
    comptages = [{**f, **({"id": corrections[f.get("id")]["id"],
                            "type": "correction-comptage", "cible_id": f.get("id"),
                            "quantite": corrections[f.get("id")]["quantite"],
                            "conditionnement": corrections[f.get("id")].get("conditionnement", f.get("conditionnement")),
                            "colis": corrections[f.get("id")].get("colis")}
                           if f.get("id") in corrections else {})}
                 for f in tous_faits if f.get("type") == "comptage"]
    if not comptages:
        return {
            "genere_le": datetime.now().isoformat(timespec="seconds"),
            "comptages_audites": 0,
            "total_comptages": 0,
            "resultats": [],
            "synthese": {"conformes": 0, "ecarts_detectes": 0},
        }

    if comptage_id:
        selection = [c for c in comptages if c.get("id") == comptage_id or c.get("cible_id") == comptage_id]
    elif date_cible:
        selection = [c for c in comptages if (c.get("date_effet") or c.get("date_source")) == date_cible]
    else:
        derniere_date = max((c.get("date_effet") or c.get("date_source") or "") for c in comptages)
        selection = [c for c in comptages if (c.get("date_effet") or c.get("date_source")) == derniere_date]

    selection = selection[-limite:]

    resultats = []
    for c in selection:
        itm8 = c.get("article")
        audit = auditer_un_comptage(
            c,
            tous_faits,
            catalogue_articles,
            heures_mail,
            catalogue_articles,
        )
        resultats.append(audit)

    nb_conformes = len([r for r in resultats if r["statut"] == "conforme"])
    nb_ecarts = len([r for r in resultats if r["statut"] == "ecart_detecte"])

    rapport = {
        "_lisez_moi": "Audit des écarts de stock (agent-audit-stock) lors de la réception d'un comptage.",
        "genere_le": datetime.now().isoformat(timespec="seconds"),
        "date_analysee": date_cible or (selection[0].get("date_effet") if selection else None),
        "total_comptages": len(resultats),
        "synthese": {
            "conformes": nb_conformes,
            "ecarts_detectes": nb_ecarts,
            "inconnus": sum(r["statut"] == "inconnu" for r in resultats),
        },
        "resultats": resultats,
    }
    return rapport


def formater_message_chat(rapport):
    resultats = rapport.get("resultats", [])
    ecarts = [r for r in resultats if r["statut"] != "conforme"]

    if not resultats:
        return "Comptage reçu : aucun relevé à auditer."

    if not ecarts:
        return (
            f"Comptage en chambre froide bien reçu ({len(resultats)} article(s)) : "
            f"tous les stocks physiques mesurés sont parfaitement conformes aux calculs."
        )

    lignes = [
        f"Audit de votre comptage ({len(resultats)} articles, dont {len(ecarts)} à examiner) :"
    ]

    for item in ecarts[:5]:
        if item["statut"] == "inconnu":
            lignes.append(f"• {item['libelle']} : comptage reçu ; {item['explication_responsable']}")
            continue
        lib = item["libelle"]
        c_phy = item["physique"]["colis"]
        c_att = item["theorique"]["colis"]
        d_col = item["ecart"]["colis"]
        signe = "+" if d_col > 0 else ""

        motif = "Écart à arbitrer"
        if item.get("causes_identifiees"):
            prem = item["causes_identifiees"][0]
            motif = prem["titre"]

        lignes.append(f"• {lib} : {c_phy:.1f} colis comptés (attendu : {c_att:.1f}, écart {signe}{d_col:.1f} colis) -> {motif}.")

    if len(ecarts) > 5:
        lignes.append(f"... et {len(ecarts) - 5} autre(s) article(s) audité(s).")

    return "\n".join(lignes)


def publier_dans_chat(rapport):
    import dire
    message = formater_message_chat(rapport)
    dire.publier(message, auteur="Agent Audit Stock")
    return message


@operation_donnees(lambda: DONNEES)
def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--date", type=str, default=None, help="Date des comptages à analyser (AAAA-MM-JJ)")
    parser.add_argument("--id", type=str, default=None, help="Identifiant exact d'un comptage")
    parser.add_argument("--limite", type=int, default=20, help="Nombre maximal de comptages analysés")
    parser.add_argument("--publier", action="store_true", help="Publie l'analyse dans le chat du rayon")
    parser.add_argument("--silencieux", action="store_true", help="N'affiche pas les détails dans la console")
    args = parser.parse_args()

    rapport = analyser_comptages_recents(date_cible=args.date, comptage_id=args.id, limite=args.limite)
    ecrire_json(FICHIER_AUDIT, rapport)

    if not args.silencieux:
        print(f"=== AUDIT DES ÉCARTS DE STOCK ({rapport.get('date_analysee')}) ===")
        print(f"  Articles comptés évalués : {rapport['total_comptages']}")
        print(f"  Stocks conformes : {rapport['synthese']['conformes']}")
        print(f"  Écarts détectés : {rapport['synthese']['ecarts_detectes']}")

        for r in rapport.get("resultats", []):
            if r["statut"] == "inconnu":
                print(f"[?] {r['libelle']} : {r['explication_responsable']}")
            elif r["statut"] != "conforme":
                print(f"\n[!] {r['libelle']} ({r['article']}) :")
                print(f"    Physique : {r['physique']['colis']} colis | Attendu : {r['theorique']['colis']} colis | Écart : {r['ecart']['colis']:+} colis")
                for c in r.get("causes_identifiees", []):
                    print(f"    -> Cause [{c['gravite']}] : {c['titre']}")
                    print(f"       {c['details']}")

    if args.publier:
        print("\nPublication de l'audit dans le chat mobile...")
        msg = publier_dans_chat(rapport)
        print(f"  -> Publié : {msg[:100]}...")


if __name__ == "__main__":
    main()
