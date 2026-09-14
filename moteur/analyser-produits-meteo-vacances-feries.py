"""
moteur/analyser-produits-meteo-vacances-feries.py - Analyse sur 2,5 ans des ventes par produit.

Ce module analyse les 137 000+ faits de vente réels d'Intermarché Carmaux (mars 2024 - septembre 2026)
croisés avec l'historique météo quotidien, les vacances scolaires (Zone C - académie de Toulouse)
et les jours fériés.

Méthode statistique :
- Pour chaque article et chaque jour de la semaine (lundi à samedi), on calcule les ventes de base.
- Pour chaque condition externe (chaleur >= 25°C / >= 30°C, pluie >= 5mm, vacances été/autres, veille de férié),
  on calcule le ratio pondéré : somme(ventes réelles) / somme(ventes attendues selon le jour de semaine).
- Les articles sont également regroupés par famille métier pour fournir des coefficients stabilisés
  même en cas d'historique court sur un article spécifique.
- Les profils sont sauvegardés dans donnees/profils-produits-sensibilites.json pour utilisation
  directe par le moteur de proposition de commande (generer-proposition.py).

Usage :
  python moteur/analyser-produits-meteo-vacances-feries.py
"""
from collections import defaultdict
from datetime import date, datetime, timedelta
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
FICHIER_METEO = DONNEES / "meteo-historique.json"
FICHIER_CALENDRIER = DONNEES / "calendrier.json"
FICHIER_SORTIE = DONNEES / "profils-produits-sensibilites.json"

sys.path.insert(0, str(MOTEUR))
import calendrier
import catalogue
from ecriture_derivee import ecrire_json
import faits


FAMILLES_DEFINITIONS = {
    "fruits_ete": [
        "melon", "pasteque", "peche", "nectarine", "abricot", "cerise", "prune",
        "raisin", "figue", "fraise", "framboise", "myrtille", "mure", "groseille"
    ],
    "salades_crudites": [
        "salade", "batavia", "laitue", "sucrine", "mache", "roquette", "concombre",
        "tomate", "radis", "poivron", "avocat"
    ],
    "legumes_a_cuire": [
        "pomme de terre", "pdt", "carotte", "poireau", "oignon", "echalote", "ail",
        "chou", "courge", "potiron", "potimarron", "navet", "courgette", "aubergine",
        "epinard", "haricot", "champignon", "endive", "blette", "panais", "artichaut"
    ],
    "agrumes_fruits_hiver": [
        "orange", "clementine", "mandarine", "pamplemousse", "pomelo", "citron",
        "pomme", "poire", "kiwi", "chataigne", "noix"
    ],
    "bananes_exotiques": [
        "banane", "ananas", "mangue", "kaki", "grenade", "passion", "noix de coco", "lime"
    ],
    "herbes_aromatiques": [
        "persil", "coriandre", "menthe", "basilic", "ciboulette", "aneth", "estragon", "cerfeuil"
    ]
}


def sans_accent(t):
    return "".join(c for c in unicodedata.normalize("NFD", t or "")
                   if unicodedata.category(c) != "Mn").lower()


def classifier_famille(nom_article):
    nom = sans_accent(nom_article)
    if re.search(r"\bbio\b", nom):
        for famille, mots in FAMILLES_DEFINITIONS.items():
            if any(mot in nom for mot in mots):
                return f"{famille}_bio"
        return "autre_bio"
    for famille, mots in FAMILLES_DEFINITIONS.items():
        if any(mot in nom for mot in mots):
            return famille
    return "autres"


def charger_meteo():
    if FICHIER_METEO.exists():
        try:
            return json.loads(FICHIER_METEO.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def charger_faits_ventes():
    """Lit toutes les ventes des carnets 2024, 2025, 2026."""
    ventes = []
    for fait in faits.lire(DOSSIER_FAITS):
        if fait.get("type") == "vente":
            ventes.append(fait)
    return ventes


def qualifier_contexte_global(meteo_dict, cal_dict, dates_ventes):
    """Prépare le contexte pour chaque date présente dans l'historique."""
    contexte_dates = {}
    feries_set = set(cal_dict.get("feries", {}).keys())
    
    # Veilles de jours fériés
    veilles_feries = set()
    for f in feries_set:
        try:
            d_obj = date.fromisoformat(f)
            # Veille calendaire (ou samedi si férié le lundi)
            veille_1 = (d_obj - timedelta(days=1)).isoformat()
            veilles_feries.add(veille_1)
            if d_obj.weekday() == 0:  # lundi férié -> samedi veille active
                veilles_feries.add((d_obj - timedelta(days=2)).isoformat())
        except Exception:
            pass

    # Vacances
    vacances_list = cal_dict.get("vacances", [])

    toutes_dates = set(meteo_dict.keys()) | set(dates_ventes)
    for v in vacances_list:
        try:
            d_courante = date.fromisoformat(v["debut"])
            d_fin = date.fromisoformat(v["fin"])
            while d_courante <= d_fin:
                toutes_dates.add(d_courante.isoformat())
                d_courante += timedelta(days=1)
        except Exception:
            pass

    for d_iso in toutes_dates:
        try:
            dt = date.fromisoformat(d_iso)
            js = dt.weekday()
            info_m = meteo_dict.get(d_iso)
            tmax, pluie = None, 0.0
            if isinstance(info_m, (list, tuple)) and len(info_m) >= 2:
                tmax = float(info_m[0])
                pluie = float(info_m[1])
            elif isinstance(info_m, dict):
                tmax = float(info_m.get("temperature_max", info_m.get("tmax", 0)))
                pluie = float(info_m.get("pluie_mm", info_m.get("pluie", 0)))

            nom_vacances = None
            for vac in vacances_list:
                if vac["debut"] <= d_iso <= vac["fin"]:
                    nom_vacances = calendrier.famille(vac.get("nom", ""))
                    break

            mois = dt.month
            ctx = {
                "date": d_iso,
                "jour_semaine": js,
                "mois": mois,
                "tmax": tmax,
                "pluie": pluie,
                "chaud_25": (tmax is not None and tmax >= 25.0),
                "chaud_30": (tmax is not None and tmax >= 30.0),
                "frais_16": (tmax is not None and tmax < 16.0),
                "froid_10": (tmax is not None and tmax < 10.0),
                "pluie_5mm": (pluie is not None and pluie >= 5.0),
                "ferie": d_iso in feries_set,
                "veille_ferie": d_iso in veilles_feries,
                "vacances_ete": (nom_vacances == "Été"),
                "vacances_toussaint": (nom_vacances is not None and "Toussaint" in nom_vacances),
                "vacances_noel": (nom_vacances is not None and "Noël" in nom_vacances),
                "vacances_autres": (nom_vacances is not None and nom_vacances != "Été"),
                "scolaire": (nom_vacances is None),
                "septembre": (mois == 9),
                "septembre_chaud_25": (mois == 9 and tmax is not None and tmax >= 25.0),
                "automne": (mois in (9, 10, 11))
            }
            contexte_dates[d_iso] = ctx
        except Exception:
            pass

    return contexte_dates


def calculer_profils(ventes, contextes, catalogue_noms):
    # 1. Regrouper ventes par (article, date)
    ventes_art_date = defaultdict(float)
    dates_actives_par_art = defaultdict(set)
    for v in ventes:
        art = v.get("article")
        d = v.get("date_source")
        q = float(v.get("quantite", 0) or 0)
        if art and d and q > 0:
            ventes_art_date[(art, d)] += q
            dates_actives_par_art[art].add(d)

    # 2. Baseline par jour de semaine pour chaque article
    ventes_par_js = defaultdict(lambda: [0.0] * 7)
    jours_par_js = defaultdict(lambda: [0] * 7)
    
    for (art, d), q in ventes_art_date.items():
        try:
            dt = date.fromisoformat(d)
            js = dt.weekday()
            ventes_par_js[art][js] += q
            jours_par_js[art][js] += 1
        except Exception:
            pass

    moyennes_js = {}
    for art in ventes_par_js:
        moy = [0.0] * 7
        for js in range(7):
            if jours_par_js[art][js] > 0:
                moy[js] = ventes_par_js[art][js] / jours_par_js[art][js]
        moyennes_js[art] = moy

    # 3. Accumulateurs par condition
    conditions = [
        "chaud_25", "chaud_30", "frais_16", "froid_10", "pluie_5mm",
        "vacances_ete", "vacances_toussaint", "vacances_noel", "vacances_autres",
        "veille_ferie", "septembre", "septembre_chaud_25", "automne"
    ]
    
    art_stats = defaultdict(lambda: {c: {"obs": 0.0, "att": 0.0, "nb": 0} for c in conditions})
    fam_stats = defaultdict(lambda: {c: {"obs": 0.0, "att": 0.0, "nb": 0} for c in conditions})
    total_ventes_art = defaultdict(float)

    for (art, d), obs in ventes_art_date.items():
        ctx = contextes.get(d)
        if not ctx:
            continue
        js = ctx["jour_semaine"]
        att = moyennes_js.get(art, [0.0]*7)[js]
        if att <= 0:
            continue

        total_ventes_art[art] += obs
        nom_art = catalogue_noms.get(art, art)
        fam = classifier_famille(nom_art)

        for cond in conditions:
            if ctx.get(cond):
                art_stats[art][cond]["obs"] += obs
                art_stats[art][cond]["att"] += att
                art_stats[art][cond]["nb"] += 1

                fam_stats[fam][cond]["obs"] += obs
                fam_stats[fam][cond]["att"] += att
                fam_stats[fam][cond]["nb"] += 1

    # 4. Calcul des coefficients famille
    familles_ratios = {}
    for fam, cond_dict in fam_stats.items():
        familles_ratios[fam] = {}
        for cond, val in cond_dict.items():
            if val["att"] > 0 and val["nb"] >= 10:
                ratio = round(val["obs"] / val["att"], 3)
            else:
                ratio = 1.0
            familles_ratios[fam][cond] = ratio

    # 5. Calcul des coefficients par article (avec seuil de significativité)
    articles_ratios = {}
    for art, cond_dict in art_stats.items():
        nom_art = catalogue_noms.get(art, art)
        fam = classifier_famille(nom_art)
        nb_jours = len(dates_actives_par_art[art])
        vol_total = round(total_ventes_art[art], 1)

        art_data = {
            "itm8": art,
            "libelle": nom_art,
            "famille": fam,
            "volume_total_2ans_demi": vol_total,
            "jours_observes": nb_jours,
            "ratios": {}
        }

        for cond in conditions:
            val = cond_dict[cond]
            # Si au moins 15 occurrences et attendu significatif, on retient le ratio spécifique article
            if val["att"] >= 10.0 and val["nb"] >= 15:
                art_data["ratios"][cond] = round(val["obs"] / val["att"], 3)
                art_data[f"{cond}_source"] = "article"
            else:
                art_data["ratios"][cond] = familles_ratios.get(fam, {}).get(cond, 1.0)
                art_data[f"{cond}_source"] = "famille"

        articles_ratios[art] = art_data

    return familles_ratios, articles_ratios


def main():
    print("Chargement des metadonnees et des 2.5 ans de faits...")
    meteo = charger_meteo()
    cal = json.loads(FICHIER_CALENDRIER.read_text(encoding="utf-8")) if FICHIER_CALENDRIER.exists() else {}
    noms = catalogue.noms()
    ventes = charger_faits_ventes()

    dates_ventes = {v["date_source"] for v in ventes if v.get("date_source")}
    print(f"  Ventes brutes lues : {len(ventes)}")
    print(f"  Jours meteo connus : {len(meteo)}")
    print(f"  Jours de vente uniques : {len(dates_ventes)}")

    contextes = qualifier_contexte_global(meteo, cal, dates_ventes)
    familles_ratios, articles_ratios = calculer_profils(ventes, contextes, noms)

    resultat = {
        "calcule_le": datetime.now().isoformat(),
        "periode_analyse": "2024-03-19 a 2026-09-11 (2.5 ans)",
        "nombre_ventes_analysees": len(ventes),
        "nombre_articles_profils": len(articles_ratios),
        "familles": familles_ratios,
        "articles": articles_ratios
    }

    ecrire_json(FICHIER_SORTIE, resultat)
    print(f"\nProfils de sensibilite calcules et enregistres dans : {FICHIER_SORTIE}")
    print(f"Articles profils generes : {len(articles_ratios)}")
    print("\n--- SYNTHESE DES COEFFICIENTS PAR FAMILLE (Impact meteo & calendrier) ---")
    print(f"{'Famille':<25} | {'Chaud >=25°':<12} | {'Chaud >=30°':<12} | {'Pluie >=5mm':<12} | {'Vac. Ete':<10} | {'Veille Ferie':<12}")
    print("-" * 95)
    for fam, r in sorted(familles_ratios.items()):
        c25 = r.get('chaud_25', 1.0)
        c30 = r.get('chaud_30', 1.0)
        pluie = r.get('pluie_5mm', 1.0)
        ete = r.get('vacances_ete', 1.0)
        vf = r.get('veille_ferie', 1.0)
        print(f"{fam:<25} | x{c25:<11.3f} | x{c30:<11.3f} | x{pluie:<11.3f} | x{ete:<9.3f} | x{vf:<11.3f}")


if __name__ == "__main__":
    main()
