"""
moteur/analyser-historique-complet.py - Analyse des ventes sur la période disponible.

Ce module décrit les ventes positives présentes dans les faits, y compris les articles
absents du cadencier du jour. La dernière date retenue détermine l'année et le mois
de référence ; les statistiques historiques ne sont pas une prévision de commande.
- Par année civile réellement observée
- Par Mois (1 à 12) : saisonnalité, mois de pic, part annuelle
- Par Semaine ISO (1 à 52/53) : profil annuel semaine par semaine
- Par Jour de la semaine (lundi à dimanche) : rythme d'achats hebdomadaire
- Par Météo locale (canicule >= 30°C, chaud >= 25°C, tempéré, frais < 16°C, grand froid < 10°C, pluie >= 5mm)
- Par Période de Vacances Scolaires (Zone C Toulouse : Été, Toussaint, Noël, Hiver, Printemps vs Scolaire)
- Par Jours Fériés et Veilles de Fériés (sur-ventes d'anticipation à J-1)

Sortie :
  donnees/analyse-ventes-annuelle-saisonniere.json

Usage :
  python moteur/analyser-historique-complet.py
"""
from collections import defaultdict
from datetime import date, datetime, timedelta
import json
from pathlib import Path
import sys
import unicodedata

RACINE = Path(__file__).resolve().parent.parent
MOTEUR = RACINE / "moteur"
DONNEES = RACINE / "donnees"
DOSSIER_FAITS = DONNEES / "faits"
FICHIER_METEO = DONNEES / "meteo-historique.json"
FICHIER_CALENDRIER = DONNEES / "calendrier.json"
FICHIER_SORTIE = DONNEES / "analyse-ventes-annuelle-saisonniere.json"

sys.path.insert(0, str(MOTEUR))
import faits
import catalogue
from ecriture_derivee import ecrire_json

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

NOMS_MOIS = ["", "Janvier", "Février", "Mars", "Avril", "Mai", "Juin", "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"]
NOMS_JOURS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]


def sans_accent(t):
    return "".join(c for c in unicodedata.normalize("NFD", t or "")
                   if unicodedata.category(c) != "Mn").lower()


def classifier_famille(nom_article):
    nom = sans_accent(nom_article)
    for famille, mots in FAMILLES_DEFINITIONS.items():
        if any(mot in nom for mot in mots):
            return famille
    return "autres"


def charger_donnees():
    meteo = json.loads(FICHIER_METEO.read_text(encoding="utf-8")) if FICHIER_METEO.exists() else {}
    cal = json.loads(FICHIER_CALENDRIER.read_text(encoding="utf-8")) if FICHIER_CALENDRIER.exists() else {}
    noms = catalogue.noms()
    ventes = [f for f in faits.lire(DOSSIER_FAITS) if f.get("type") == "vente"]
    return meteo, cal, noms, ventes


def analyser():
    print("Chargement des ventes disponibles et métadonnées...")
    meteo, cal, noms, ventes = charger_donnees()
    feries_dict = cal.get("feries", {})
    vacances_list = cal.get("vacances", [])

    # Veilles de fériés
    veilles_feries = set()
    for f in feries_dict.keys():
        try:
            df = date.fromisoformat(f)
            veilles_feries.add((df - timedelta(days=1)).isoformat())
            if df.weekday() == 0:  # Lundi férié -> samedi veille active
                veilles_feries.add((df - timedelta(days=2)).isoformat())
        except Exception:
            pass

    def get_vac_info(d_iso):
        for vac in vacances_list:
            if vac["debut"] <= d_iso <= vac["fin"]:
                nom = vac.get("nom", "")
                if "Été" in nom: return "Vacances d'Été"
                if "Toussaint" in nom: return "Vacances de la Toussaint"
                if "Noël" in nom: return "Vacances de Noël"
                if "Hiver" in nom: return "Vacances d'Hiver"
                if "Printemps" in nom: return "Vacances de Printemps"
                return "Vacances"
        return "Période Scolaire Normale"

    def get_meteo_cond(d_iso):
        info = meteo.get(d_iso)
        if not info:
            return {"tmax": None, "pluie": 0.0, "tranche": "inconnue", "pluvieux": False}
        if isinstance(info, (list, tuple)) and len(info) >= 2:
            tmax, pluie = float(info[0]), float(info[1])
        else:
            tmax = float(info.get("temperature_max", 0))
            pluie = float(info.get("pluie_mm", 0))

        if tmax >= 30.0:
            tranche = "canicule_sup_30"
        elif tmax >= 25.0:
            tranche = "chaud_25_30"
        elif tmax >= 16.0:
            tranche = "tempere_16_25"
        elif tmax >= 10.0:
            tranche = "frais_10_16"
        else:
            tranche = "froid_inf_10"

        return {"tmax": tmax, "pluie": pluie, "tranche": tranche, "pluvieux": (pluie >= 5.0)}

    print("Indexation multi-dimensionnelle de l'ensemble des articles...")
    ventes_totales_date = defaultdict(float)
    ventes_par_famille_date = defaultdict(lambda: defaultdict(float))
    
    # Structures par article pour tous les articles avec ventes retenues
    ventes_art_date = defaultdict(float)
    ventes_art_total = defaultdict(float)
    jours_art_observes = defaultdict(set)
    ventes_art_annee = defaultdict(lambda: defaultdict(float))
    ventes_art_mois = defaultdict(lambda: defaultdict(float))
    jours_art_mois = defaultdict(lambda: defaultdict(set))
    ventes_art_annee_mois = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
    jours_art_annee_mois = defaultdict(lambda: defaultdict(lambda: defaultdict(set)))
    ventes_art_semaine = defaultdict(lambda: defaultdict(float))
    jours_art_semaine = defaultdict(lambda: defaultdict(set))
    ventes_art_annee_semaine = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
    jours_art_annee_semaine = defaultdict(lambda: defaultdict(lambda: defaultdict(set)))
    ventes_art_js = defaultdict(lambda: [0.0] * 7)
    jours_art_js = defaultdict(lambda: [0] * 7)
    ventes_art_jour = defaultdict(lambda: defaultdict(float))

    # Accumulateurs météo et calendrier par article
    art_cond_stats = defaultdict(lambda: defaultdict(lambda: {"obs": 0.0, "att": 0.0, "nb": 0}))
    fam_cond_stats = defaultdict(lambda: defaultdict(lambda: {"obs": 0.0, "att": 0.0, "nb": 0}))

    dates_toutes_set = set()
    for v in ventes:
        art = v.get("article")
        d = v.get("date_source")
        q = float(v.get("quantite", 0) or 0)
        if art and d and q > 0:
            dates_toutes_set.add(d)
            dt = date.fromisoformat(d)
            m = dt.month
            yr = str(dt.year)
            annee_iso, s_iso, _ = dt.isocalendar()
            js = dt.weekday()

            ventes_totales_date[d] += q
            ventes_art_date[(art, d)] += q
            ventes_art_total[art] += q
            jours_art_observes[art].add(d)

            ventes_art_annee[art][yr] += q
            ventes_art_mois[art][m] += q
            jours_art_mois[art][m].add(d)
            ventes_art_annee_mois[art][yr][m] += q
            jours_art_annee_mois[art][yr][m].add(d)
            ventes_art_semaine[art][s_iso] += q
            jours_art_semaine[art][s_iso].add(d)
            ventes_art_annee_semaine[art][str(annee_iso)][s_iso] += q
            jours_art_annee_semaine[art][str(annee_iso)][s_iso].add(d)
            ventes_art_js[art][js] += q
            jours_art_js[art][js] += 1
            ventes_art_jour[art][d] += q

            fam = classifier_famille(noms.get(art, art))
            ventes_par_famille_date[d][fam] += q

    dates_toutes = sorted(dates_toutes_set)
    date_reference = dates_toutes[-1] if dates_toutes else None
    reference = date.fromisoformat(date_reference) if date_reference else None
    annee_reference = reference.year if reference else None
    annees_observees = sorted({d[:4] for d in dates_toutes})
    annees_iso_observees = sorted({str(date.fromisoformat(d).isocalendar().year) for d in dates_toutes})
    mois_reference = reference.month if reference else None
    mois_suivant = mois_reference % 12 + 1 if reference else None
    annee_suivante = annee_reference + (mois_reference == 12) if reference else None
    total_unites = sum(ventes_totales_date.values())
    total_jours = len(dates_toutes)
    moyenne_globale_jour = round(total_unites / total_jours, 1) if total_jours else 0.0

    # Baseline par jour de la semaine pour chaque article (pour calcul d'élasticité rigoureux)
    art_moy_js = {}
    for art in ventes_art_total:
        moy = [0.0] * 7
        for js in range(7):
            if jours_art_js[art][js] > 0:
                moy[js] = ventes_art_js[art][js] / jours_art_js[art][js]
        art_moy_js[art] = moy

    # Contextes pour chaque date
    contextes_dates = {}
    for d in dates_toutes:
        dt = date.fromisoformat(d)
        m_info = get_meteo_cond(d)
        vcat = get_vac_info(d)
        tmax = m_info["tmax"]

        ctx = {
            "date": d,
            "jour_semaine": dt.weekday(),
            "mois": dt.month,
            "annee": str(dt.year),
            "semaine_iso": dt.isocalendar().week,
            "annee_iso": str(dt.isocalendar().year),
            "tranche_meteo": m_info["tranche"],
            "pluvieux": m_info["pluvieux"],
            "tmax": tmax,
            "canicule_sup_30": (m_info["tranche"] == "canicule_sup_30"),
            "chaud_25_30": (m_info["tranche"] == "chaud_25_30"),
            "chaud_25": (tmax is not None and tmax >= 25.0),
            "tempere_16_25": (m_info["tranche"] == "tempere_16_25"),
            "frais_10_16": (m_info["tranche"] == "frais_10_16"),
            "froid_inf_10": (m_info["tranche"] == "froid_inf_10"),
            "froid_inf_16": (tmax is not None and tmax < 16.0),
            "pluie_5mm": m_info["pluvieux"],
            "vacances_periode": vcat,
            "vacances_ete": (vcat == "Vacances d'Été"),
            "vacances_toussaint": (vcat == "Vacances de la Toussaint"),
            "vacances_noel": (vcat == "Vacances de Noël"),
            "vacances_hiver": (vcat == "Vacances d'Hiver"),
            "vacances_printemps": (vcat == "Vacances de Printemps"),
            "scolaire_normal": (vcat == "Période Scolaire Normale"),
            "ferie_ouvert": (d in feries_dict),
            "veille_ferie": (d in veilles_feries),
            "jour_ordinaire": (d not in feries_dict and d not in veilles_feries),
            "septembre": (dt.month == 9),
            "septembre_chaud_25": (dt.month == 9 and tmax is not None and tmax >= 25.0)
        }
        contextes_dates[d] = ctx

    # Calcul des ratios d'élasticité observés / attendus par article et par famille
    conditions_cles = [
        "canicule_sup_30", "chaud_25_30", "chaud_25", "tempere_16_25", "frais_10_16", "froid_inf_10", "froid_inf_16", "pluie_5mm",
        "vacances_ete", "vacances_toussaint", "vacances_noel", "vacances_hiver", "vacances_printemps", "scolaire_normal",
        "veille_ferie", "septembre", "septembre_chaud_25"
    ]

    for (art, d), obs in ventes_art_date.items():
        ctx = contextes_dates.get(d)
        if not ctx: continue
        js = ctx["jour_semaine"]
        att = art_moy_js[art][js]
        if att <= 0: continue

        fam = classifier_famille(noms.get(art, art))
        for c in conditions_cles:
            if ctx.get(c):
                art_cond_stats[art][c]["obs"] += obs
                art_cond_stats[art][c]["att"] += att
                art_cond_stats[art][c]["nb"] += 1
                fam_cond_stats[fam][c]["obs"] += obs
                fam_cond_stats[fam][c]["att"] += att
                fam_cond_stats[fam][c]["nb"] += 1

    # Ratios consolidés par famille
    familles_ratios = {}
    for fam, cdict in fam_cond_stats.items():
        familles_ratios[fam] = {}
        for c, st in cdict.items():
            if st["att"] > 0 and st["nb"] >= 5:
                familles_ratios[fam][c] = round(st["obs"] / st["att"], 3)
            else:
                familles_ratios[fam][c] = 1.0

    print("Construction des synthèses temporelles (Année, Mois, Semaines, Jours)...")
    # 1. PAR ANNEE
    annees_raw = defaultdict(lambda: {"total": 0.0, "jours": 0, "mois": defaultdict(float)})
    for d, tot in ventes_totales_date.items():
        yr = d[:4]
        m = int(d[5:7])
        annees_raw[yr]["total"] += tot
        annees_raw[yr]["jours"] += 1
        annees_raw[yr]["mois"][m] += tot

    annees = {}
    for yr in sorted(annees_raw.keys()):
        st = annees_raw[yr]
        moy_j = round(st["total"] / st["jours"], 1) if st["jours"] else 0.0
        annees[yr] = {
            "annee": int(yr),
            "total_unites_vendues": round(st["total"], 1),
            "jours_observes": st["jours"],
            "moyenne_quotidienne": moy_j
        }

    # 2. PAR MOIS (1 a 12)
    mois_raw = defaultdict(lambda: {
        "total": 0.0, "jours": 0, "annees": defaultdict(lambda: {"total": 0.0, "jours": 0}),
        "familles": defaultdict(float)
    })
    for d, tot in ventes_totales_date.items():
        m = int(d[5:7])
        yr = d[:4]
        mois_raw[m]["total"] += tot
        mois_raw[m]["jours"] += 1
        mois_raw[m]["annees"][yr]["total"] += tot
        mois_raw[m]["annees"][yr]["jours"] += 1
        for fam, q in ventes_par_famille_date[d].items():
            mois_raw[m]["familles"][fam] += q

    mois = []
    for m in range(1, 13):
        st = mois_raw[m]
        moy_j = round(st["total"] / st["jours"], 1) if st["jours"] else 0.0
        part_pct = round((st["total"] / total_unites) * 100, 1) if total_unites else 0.0

        par_annee = {}
        for yr in annees_observees:
            yst = st["annees"].get(yr)
            if yst and yst["jours"] > 0:
                par_annee[yr] = {
                    "total_unites": round(yst["total"], 1),
                    "jours": yst["jours"],
                    "moyenne_jour": round(yst["total"] / yst["jours"], 1)
                }
            else:
                par_annee[yr] = None

        fam_triees = sorted(st["familles"].items(), key=lambda x: x[1], reverse=True)
        fam_pct = {f: round((q / st["total"]) * 100, 1) for f, q in fam_triees} if st["total"] else {}
        top_fam = fam_triees[0][0] if fam_triees else "inconnue"

        # Top articles du mois
        arts_m = sorted([(a, ventes_art_mois[a][m]) for a in ventes_art_total if ventes_art_mois[a][m] > 0],
                        key=lambda x: x[1], reverse=True)[:8]
        top_articles = [{"itm8": a, "libelle": noms.get(a, a), "volume": round(q, 1), "moyenne_jour": round(q / len(jours_art_mois[a][m]), 1) if jours_art_mois[a][m] else 0} for a, q in arts_m]

        mois.append({
            "mois_numero": m,
            "nom": NOMS_MOIS[m],
            "total_unites": round(st["total"], 1),
            "jours_observes": st["jours"],
            "moyenne_quotidienne": moy_j,
            "part_annuelle_pct": part_pct,
            "famille_dominante": top_fam,
            "repartition_familles_pct": fam_pct,
            "par_annee": par_annee,
            "top_articles": top_articles
        })

    # 3. PAR SEMAINE ISO (1 a 53)
    sem_raw = defaultdict(lambda: {"total": 0.0, "jours": 0, "annees": defaultdict(lambda: {"total": 0.0, "jours": 0})})
    for d, tot in ventes_totales_date.items():
        dt = date.fromisoformat(d)
        annee_iso, s_iso, _ = dt.isocalendar()
        sem_raw[s_iso]["total"] += tot
        sem_raw[s_iso]["jours"] += 1
        sem_raw[s_iso]["annees"][str(annee_iso)]["total"] += tot
        sem_raw[s_iso]["annees"][str(annee_iso)]["jours"] += 1

    semaines = []
    for s in range(1, 54):
        st = sem_raw[s]
        if st["jours"] > 0:
            moy_j = round(st["total"] / st["jours"], 1)
            indice = round(moy_j / moyenne_globale_jour, 3) if moyenne_globale_jour else 1.0
            par_annee = {}
            for yr in annees_iso_observees:
                yst = st["annees"].get(yr)
                if yst and yst["jours"] > 0:
                    par_annee[yr] = {
                        "total_unites": round(yst["total"], 1),
                        "jours": yst["jours"],
                        "moyenne_jour": round(yst["total"] / yst["jours"], 1)
                    }
                else:
                    par_annee[yr] = None

            semaines.append({
                "semaine_iso": s,
                "evenement_cle": "; ".join(
                    f"{d} : {feries_dict[d]}" for d in dates_toutes
                    if contextes_dates[d]["semaine_iso"] == s and d in feries_dict
                ),
                "total_unites": round(st["total"], 1),
                "jours_observes": st["jours"],
                "moyenne_quotidienne": moy_j,
                "indice_relatif": indice,
                "par_annee": par_annee
            })

    # 4. PAR JOUR DE SEMAINE (Lundi a Dimanche)
    js_raw = defaultdict(lambda: {"total": 0.0, "jours": 0})
    for d, tot in ventes_totales_date.items():
        js = date.fromisoformat(d).weekday()
        js_raw[js]["total"] += tot
        js_raw[js]["jours"] += 1

    somme_moy_hebdo = sum(round(js_raw[js]["total"] / js_raw[js]["jours"], 1) for js in range(7) if js_raw[js]["jours"])
    jours_semaine = []
    for js in range(7):
        st = js_raw[js]
        if st["jours"] > 0:
            moy_j = round(st["total"] / st["jours"], 1)
            pct_sem = round((moy_j / somme_moy_hebdo) * 100, 1) if somme_moy_hebdo else 0.0
            coeff_lundi = round(moy_j / (js_raw[0]["total"] / js_raw[0]["jours"]), 2) if js_raw[0]["jours"] else 1.0
            jours_semaine.append({
                "index_jour": js,
                "nom": NOMS_JOURS[js],
                "jours_observes": st["jours"],
                "total_unites": round(st["total"], 1),
                "moyenne_quotidienne": moy_j,
                "part_semaine_pct": pct_sem,
                "ratio_vs_lundi": coeff_lundi
            })

    # 5. METEO GLOBALE & TRANCHES
    tranches_meteo_raw = defaultdict(lambda: {"jours": 0, "total": 0.0, "familles": defaultdict(float)})
    pluie_raw = defaultdict(lambda: {"jours": 0, "total": 0.0, "familles": defaultdict(float)})

    for d, tot in ventes_totales_date.items():
        ctx = contextes_dates[d]
        tr = ctx["tranche_meteo"]
        tranches_meteo_raw[tr]["jours"] += 1
        tranches_meteo_raw[tr]["total"] += tot
        for fam, q in ventes_par_famille_date[d].items():
            tranches_meteo_raw[tr]["familles"][fam] += q

        if ctx["pluvieux"]:
            pluie_raw["pluie_5mm"]["jours"] += 1
            pluie_raw["pluie_5mm"]["total"] += tot
            for fam, q in ventes_par_famille_date[d].items():
                pluie_raw["pluie_5mm"]["familles"][fam] += q

    tranches_labels = [
        ("canicule_sup_30", "Forte chaleur (>= 30°C)"),
        ("chaud_25_30", "Chaleur modérée (25°C à 30°C)"),
        ("tempere_16_25", "Climat tempéré (16°C à 25°C)"),
        ("frais_10_16", "Temps frais (10°C à 16°C)"),
        ("froid_inf_10", "Grand froid (< 10°C)")
    ]

    meteo_synthese = []
    for code, libelle in tranches_labels:
        st = tranches_meteo_raw[code]
        if st["jours"] > 0:
            moy_j = round(st["total"] / st["jours"], 1)
            ind = round(moy_j / moyenne_globale_jour, 3) if moyenne_globale_jour else 1.0
            fam_ratios = {}
            for fam, q in st["familles"].items():
                fam_moy = q / st["jours"]
                ref_fam_moy = sum(ventes_par_famille_date[d][fam] for d in dates_toutes) / total_jours
                fam_ratios[fam] = round(fam_moy / ref_fam_moy, 2) if ref_fam_moy else 1.0

            meteo_synthese.append({
                "code": code,
                "label": libelle,
                "description": "Ventes observées dans cette tranche météo ; une comparaison ne démontre pas une cause.",
                "jours_observes": st["jours"],
                "moyenne_quotidienne": moy_j,
                "indice_vs_moyenne": ind,
                "elasticite_familles": fam_ratios
            })

    # Pluie
    st_p = pluie_raw["pluie_5mm"]
    if st_p["jours"] > 0:
        moy_jp = round(st_p["total"] / st_p["jours"], 1)
        ind_p = round(moy_jp / moyenne_globale_jour, 3) if moyenne_globale_jour else 1.0
        meteo_synthese.append({
            "code": "pluie_5mm",
            "label": "Jours de pluie significative (>= 5 mm)",
            "description": "Ventes observées les jours avec au moins 5 mm de pluie ; aucune cause de variation n'est déduite.",
            "jours_observes": st_p["jours"],
            "moyenne_quotidienne": moy_jp,
            "indice_vs_moyenne": ind_p,
            "elasticite_familles": {fam: round((q / st_p["jours"]) / (sum(ventes_par_famille_date[d][fam] for d in dates_toutes) / total_jours), 2) for fam, q in st_p["familles"].items()}
        })

    # 6. PAR VACANCES SCOLAIRES (Zone C)
    vac_raw = defaultdict(lambda: {"jours": 0, "total": 0.0, "familles": defaultdict(float)})
    for d, tot in ventes_totales_date.items():
        vcat = contextes_dates[d]["vacances_periode"]
        vac_raw[vcat]["jours"] += 1
        vac_raw[vcat]["total"] += tot
        for fam, q in ventes_par_famille_date[d].items():
            vac_raw[vcat]["familles"][fam] += q

    vacances_synthese = []
    moy_scolaire = (vac_raw["Période Scolaire Normale"]["total"] / vac_raw["Période Scolaire Normale"]["jours"]) if vac_raw["Période Scolaire Normale"]["jours"] else moyenne_globale_jour

    for vcat, st in sorted(vac_raw.items(), key=lambda x: x[1]["jours"], reverse=True):
        if not st["jours"]:
            continue
        moy_v = round(st["total"] / st["jours"], 1)
        diff_pct = round(((moy_v - moy_scolaire) / moy_scolaire) * 100, 1) if moy_scolaire else 0.0
        vacances_synthese.append({
            "periode": vcat,
            "jours_observes": st["jours"],
            "moyenne_quotidienne": moy_v,
            "ecart_vs_scolaire_pct": diff_pct,
            "repartition_familles": {f: round((q / st["total"]) * 100, 1) for f, q in st["familles"].items()} if st["total"] else {}
        })

    # 7. FERIES ET VEILLES DE FERIES
    ferie_raw = {
        "veilles_de_feries": {"label": "Veilles de jours fériés (J-1 & samedi avant lundi)", "jours": 0, "total": 0.0},
        "jours_feries_ouverts": {"label": "Jours fériés avec ventes observées", "jours": 0, "total": 0.0},
        "jours_ordinaires": {"label": "Jours d'ouverture ordinaires", "jours": 0, "total": 0.0}
    }
    for d, tot in ventes_totales_date.items():
        ctx = contextes_dates[d]
        if ctx["ferie_ouvert"]:
            k = "jours_feries_ouverts"
        elif ctx["veille_ferie"]:
            k = "veilles_de_feries"
        else:
            k = "jours_ordinaires"
        ferie_raw[k]["jours"] += 1
        ferie_raw[k]["total"] += tot

    feries_synthese = []
    moy_ord = ferie_raw["jours_ordinaires"]["total"] / ferie_raw["jours_ordinaires"]["jours"] if ferie_raw["jours_ordinaires"]["jours"] else moyenne_globale_jour
    for k, v in ferie_raw.items():
        moy_k = round(v["total"] / v["jours"], 1) if v["jours"] else 0.0
        diff_pct = round(((moy_k - moy_ord) / moy_ord) * 100, 1) if moy_ord else 0.0
        feries_synthese.append({
            "type": k,
            "label": v["label"],
            "jours_observes": v["jours"],
            "moyenne_quotidienne": moy_k,
            "ecart_vs_ordinaire_pct": diff_pct
        })

    print(f"Compilation des profils détaillés pour les {len(ventes_art_total)} articles vendus...")
    # 8. Profils individuels des articles présents dans la période
    articles_profils = {}
    for art, vol_tot in sorted(ventes_art_total.items(), key=lambda x: x[1], reverse=True):
        lib = noms.get(art, art)
        fam = classifier_famille(lib)
        nb_j_obs = len(jours_art_observes[art])
        moy_j_art = round(vol_tot / nb_j_obs, 2) if nb_j_obs else 0.0

        # Années
        par_yr = {yr: round(ventes_art_annee[art][yr], 1) for yr in annees_observees if yr in ventes_art_annee[art]}

        # Mois (1 à 12) avec historique annuel comparatif
        mois_art = {}
        for m in range(1, 13):
            q_m = ventes_art_mois[art][m]
            j_m = len(jours_art_mois[art][m])
            if q_m > 0:
                annees_m = {}
                for yr in annees_observees:
                    q_ym = ventes_art_annee_mois[art][yr][m]
                    j_ym = len(jours_art_annee_mois[art][yr][m])
                    if j_ym > 0:
                        annees_m[yr] = {
                            "volume": round(q_ym, 1),
                            "jours": j_ym,
                            "moyenne_jour": round(q_ym / j_ym, 2)
                        }
                    else:
                        annees_m[yr] = None

                mois_art[str(m)] = {
                    "volume": round(q_m, 1),
                    "jours": j_m,
                    "moyenne_jour": round(q_m / j_m, 2) if j_m else 0.0,
                    "part_annuelle_pct": round((q_m / vol_tot) * 100, 1) if vol_tot else 0.0,
                    "annees": annees_m
                }

        # Historique complet 12 mois par année
        hist_annuel = {}
        for yr in annees_observees:
            hist_annuel[yr] = {}
            for m in range(1, 13):
                q_ym = ventes_art_annee_mois[art][yr][m]
                j_ym = len(jours_art_annee_mois[art][yr][m])
                hist_annuel[yr][str(m)] = {
                    "volume": round(q_ym, 1) if j_ym > 0 else 0.0,
                    "jours": j_ym,
                    "moyenne_jour": round(q_ym / j_ym, 2) if j_ym > 0 else 0.0
                }

        # Mois de pleine saison
        meilleur_mois = max(range(1, 13), key=lambda m: ventes_art_mois[art][m]) if vol_tot > 0 else None
        nom_meilleur_mois = NOMS_MOIS[meilleur_mois] if meilleur_mois else ""

        # Comparaison historique des mois, ancrée à la dernière vente du jeu.
        # L'absence d'observation n'est ni une vente nulle ni une fin de saison.
        m_actuel, m_suiv = mois_reference, mois_suivant
        st_actuel, st_suiv = mois_art.get(str(m_actuel)), mois_art.get(str(m_suiv))
        moy_act = st_actuel["moyenne_jour"] if st_actuel else None
        moy_nxt = st_suiv["moyenne_jour"] if st_suiv else None
        diff_pct = (round((moy_nxt - moy_act) / moy_act * 100, 1)
                    if moy_act is not None and moy_act > 0 and moy_nxt is not None else None)
        nom_actuel, nom_suivant = NOMS_MOIS[m_actuel], NOMS_MOIS[m_suiv]
        if diff_pct is None:
            tendance, badge = "donnees_insuffisantes", "Données insuffisantes"
            diagnostic = (f"Comparaison historique {nom_actuel} / {nom_suivant} indisponible : "
                          "au moins un mois n'a pas d'observation de vente positive.")
        else:
            if meilleur_mois == m_actuel:
                tendance, badge = "pleine_saison", "★ Mois au volume historique maximal"
            elif diff_pct >= 25.0:
                tendance, badge = "forte_hausse", f"↗ Écart historique (+{diff_pct}%)"
            elif diff_pct >= 8.0:
                tendance, badge = "hausse", f"↗ Écart historique (+{diff_pct}%)"
            elif diff_pct <= -35.0:
                tendance, badge = "fin_saison", f"↘ Écart historique ({diff_pct}%)"
            elif diff_pct <= -8.0:
                tendance, badge = "baisse", f"↘ Écart historique ({diff_pct}%)"
            else:
                tendance, badge = "stable", "→ Moyennes historiques proches"
            diagnostic = (f"Sur les jours avec vente observée : {moy_act} /jour en {nom_actuel}, "
                          f"{moy_nxt} /jour en {nom_suivant} ({diff_pct:+g} %). "
                          "Comparaison historique, sans prévision ni cause démontrée.")

        saisonnalite_art = {
            "date_reference": date_reference,
            "annee_reference": annee_reference,
            "annee_mois_suivant": annee_suivante,
            "mois_actuel": m_actuel,
            "mois_suivant": m_suiv,
            "moyenne_mois_actuel": moy_act,
            "moyenne_mois_suivant": moy_nxt,
            "evolution_pct": diff_pct,
            "tendance": tendance,
            "badge": badge,
            "diagnostic": diagnostic
        }

        # Jour de semaine
        js_art = {}
        for js in range(7):
            q_js = ventes_art_js[art][js]
            nb_js = jours_art_js[art][js]
            if nb_js > 0:
                js_art[NOMS_JOURS[js]] = round(q_js / nb_js, 2)

        # Ratios d'élasticité pour chaque condition
        ratios_art = {}
        for c in conditions_cles:
            st = art_cond_stats[art][c]
            # Si au moins 10 occurrences et attendu significatif, ratio article ; sinon repli sur la famille
            if st["att"] >= 8.0 and st["nb"] >= 10:
                ratios_art[c] = round(st["obs"] / st["att"], 3)
            else:
                ratios_art[c] = familles_ratios.get(fam, {}).get(c, 1.0)

        # Semaines ISO : la semaine 53 et son année ISO restent distinctes.
        courbes_hebdo = {"moyenne": [None] * 53,
                         **{yr: [None] * 53 for yr in annees_iso_observees}}
        for s in range(1, 54):
            j_s = len(jours_art_semaine[art][s])
            if j_s > 0:
                courbes_hebdo["moyenne"][s - 1] = round(ventes_art_semaine[art][s] / j_s, 2)
            for yr in annees_iso_observees:
                j_ys = len(jours_art_annee_semaine[art][yr][s])
                if j_ys > 0:
                    courbes_hebdo[yr][s - 1] = round(ventes_art_annee_semaine[art][yr][s] / j_ys, 2)

        articles_profils[art] = {
            "itm8": art,
            "libelle": lib,
            "famille": fam,
            "volume_total_periode": round(vol_tot, 1),
            # Alias de lecture historique : seule periode décrit la durée réelle.
            "volume_total_2ans_demi": round(vol_tot, 1),
            "date_reference": date_reference,
            "annee_reference": annee_reference,
            "annees_semaines_iso": [int(yr) for yr in annees_iso_observees],
            "jours_observes": nb_j_obs,
            "moyenne_par_jour_actif": moy_j_art,
            "mois_pleine_saison": nom_meilleur_mois,
            "saisonnalite": saisonnalite_art,
            "ventes_par_annee": par_yr,
            "ventes_par_mois": mois_art,
            "historique_mensuel_par_annee": hist_annuel,
            "courbes_hebdo": courbes_hebdo,
            "ventes_quotidiennes": {d: round(q, 1) for d, q in sorted(ventes_art_jour[art].items())
                                     if int(d[:4]) == annee_reference},
            "moyenne_par_jour_semaine": js_art,
            "ratios_sensibilite": ratios_art
        }

    # Focus du mois de la dernière vente, sur les mêmes mois historiques disponibles.
    focus_dates = [d for d in dates_toutes if int(d[5:7]) == mois_reference]
    focus_moy = (round(sum(ventes_totales_date[d] for d in focus_dates) / len(focus_dates), 1)
                 if focus_dates else None)
    focus_chaud_dates = [d for d in focus_dates if contextes_dates[d]["chaud_25"]]
    focus_chaud_moy = (round(sum(ventes_totales_date[d] for d in focus_chaud_dates) / len(focus_chaud_dates), 1)
                       if focus_chaud_dates else None)
    focus_mois = {
        "date_reference": date_reference,
        "mois_numero": mois_reference,
        "annees_observees": sorted({int(d[:4]) for d in focus_dates}),
        "jours_observes": len(focus_dates),
        "moyenne_quotidienne": focus_moy,
        "jours_chauds_sup_25": len(focus_chaud_dates),
        "moyenne_jours_chauds": focus_chaud_moy,
        "ecart_jours_chauds_pct": (round((focus_chaud_moy - focus_moy) / focus_moy * 100, 1)
                                   if focus_moy and focus_chaud_moy is not None else None),
        "explication_metier": (
            f"{NOMS_MOIS[mois_reference]} : {len(focus_dates)} jours avec ventes observées, "
            f"moyenne {focus_moy} unités par jour actif. "
            "Les comparaisons historiques ne démontrent pas une cause météo ou une prévision."
            if focus_dates else "Aucune vente positive disponible : aucun mois de référence."
        )
    }

    # Consolidated JSON
    resultat = {
        "calcule_le": datetime.now().isoformat(),
        "description": "Analyse descriptive des ventes positives sur la période réellement disponible, y compris hors cadencier",
        "date_reference": date_reference,
        "annee_reference": annee_reference,
        "annees_semaines_iso": [int(yr) for yr in annees_iso_observees],
        "periode": {
            "date_debut": dates_toutes[0] if dates_toutes else "",
            "date_fin": dates_toutes[-1] if dates_toutes else "",
            "total_unites_vendues": round(total_unites, 1),
            "total_lignes_faits": len(ventes),
            "total_articles_analyses": len(articles_profils),
            "total_jours_avec_ventes": total_jours,
            "total_jours_ouverts": total_jours,  # Alias historique : aucune ouverture n’est déduite.
            "moyenne_quotidienne_globale": moyenne_globale_jour
        },
        "familles_ratios": familles_ratios,
        "annees": annees,
        "mois": mois,
        "semaines": semaines,
        "jours_semaine": jours_semaine,
        "meteo": meteo_synthese,
        "vacances": vacances_synthese,
        "feries_et_veilles": feries_synthese,
        "focus_mois_reference": focus_mois,
        "articles": articles_profils
    }

    ecrire_json(FICHIER_SORTIE, resultat)
    print(f"\n[SUCCÈS] Analyse terminée et sauvegardée dans : {FICHIER_SORTIE}")
    print(f"Articles avec ventes positives profilés : {len(articles_profils)}")
    print(f"Volume total analysé : {int(total_unites):,} unités sur {total_jours} jours de vente")
    return resultat


if __name__ == "__main__":
    analyser()
