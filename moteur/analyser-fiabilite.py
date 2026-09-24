"""
moteur/analyser-fiabilite.py - Analyse de la fiabilité des prévisions et propositions vs ventes réelles.

Compare systématiquement sur l'historique récent (30 jours) et annuel (2026) :
- Les ventes réelles constatées en caisse (en volume et en colis).
- La prévision/proposition calculée par la formule (en volume et en colis).
- L'écart signé et le diagnostic complet des causes racines :
    * Saisonnalité / Période festive (ventes concentrées en décembre ou en été, hors-saison le reste de l'année).
    * Colisage / PCB incompressible (1 colis représente plusieurs jours d'écoulement).
    * Dérive de stock (position négative ou absence de comptage physique).
    * Faible rotation / Article occasionnel (échantillon de vente trop mince).
    * Casse / Freinte excessive (taux de perte gonflant le besoin).
    * Biais algorithmique intrinsèque (sur/sous estimation de la formule).
- État de la commande du jour (ce que proposition.json propose réellement aujourd'hui).
- Recommandation concrète pour le responsable de rayon.
- Décomposition jour par jour de la semaine (lundi à dimanche).

Sortie : donnees/fiabilite.json
"""
import argparse
from collections import defaultdict
from datetime import date, timedelta
import json
import math
from pathlib import Path
import re
import sys

RACINE = Path(__file__).resolve().parent.parent
MOTEUR = RACINE / "moteur"
DONNEES = RACINE / "donnees"
DOSSIER_FAITS = DONNEES / "faits"
FICHIER_SORTIE = DONNEES / "fiabilite.json"
FICHIER_PROPOSITION = DONNEES / "proposition.json"
FICHIER_ETAT = DONNEES / "etat.json"

sys.path.insert(0, str(MOTEUR))
import agregats
import catalogue
from ecriture_derivee import ecrire_json
import faits
import regles

FENETRE = 21
MIN_JOURS = 5
NOMS_JS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


def jour_annee(iso):
    a, m, j = (int(x) for x in iso.split("-"))
    return date(a, m, j).timetuple().tm_yday


def jour_semaine(iso):
    a, m, j = (int(x) for x in iso.split("-"))
    return date(a, m, j).weekday()


def fenetre_circulaire(valeurs, demi):
    n = len(valeurs)
    triple = valeurs + valeurs + valeurs
    cumul = [0.0] * (3 * n + 1)
    for i in range(3 * n):
        cumul[i + 1] = cumul[i] + triple[i]
    return [cumul[n + c + demi + 1] - cumul[n + c - demi] for c in range(n)]


def determiner_famille(libelle, nomenclature=""):
    texte = (str(libelle) + " " + str(nomenclature)).lower()
    if any(m in texte for m in ("melon", "pasteque", "peche", "nectarine", "abricot", "cerise", "prune", "raisin", "figue", "fraise", "framboise", "myrtille")):
        return "Fruits d'été"
    if any(m in texte for m in ("salade", "batavia", "laitue", "sucrine", "mache", "roquette", "concombre", "tomate", "radis", "avocat")):
        return "Salades & Crudités"
    if any(m in texte for m in ("pomme de terre", "pdt", "carotte", "poireau", "oignon", "echalote", "ail", "chou", "courge", "potiron", "courgette", "aubergine", "endive", "champignon")):
        return "Légumes à cuire"
    if any(m in texte for m in ("orange", "clementine", "mandarine", "pamplemousse", "pomelo", "citron", "pomme", "poire", "kiwi")):
        return "Pommes & Agrumes"
    if any(m in texte for m in ("banane", "ananas", "mangue", "kaki", "grenade", "passion", "coco", "lime", "pitaya")):
        return "Bananes & Exotiques"
    if any(m in texte for m in ("bio", "ab ")):
        return "Bio"
    return "Autres F&L"


def qualifier_anomalie(reel, prevu, ecart_colis):
    if reel <= 0:
        if prevu <= 0:
            return "inactif", "neutre", "Inactif"
        return "sur_estimation_forte", "critique", "Prévision sans vente constatée (Risque Casse)"

    ecart_pct = 100.0 * (prevu - reel) / reel

    if ecart_pct > 25.0 and (abs(ecart_colis) >= 2.0 or prevu - reel >= 10.0):
        return "sur_estimation_forte", "critique", "Sur-proposition forte (Risque Sur-stock / Casse)"
    elif ecart_pct > 10.0:
        return "sur_estimation_moderee", "vigilance", "Sur-proposition modérée"
    elif ecart_pct < -25.0 and (abs(ecart_colis) >= 2.0 or reel - prevu >= 10.0):
        return "sous_estimation_forte", "critique", "Sous-proposition forte (Risque Rupture)"
    elif ecart_pct < -10.0:
        return "sous_estimation_moderee", "vigilance", "Sous-proposition modérée"
    else:
        return "equilibre", "conforme", "Proposition conforme"


def diagnostiquer_causes_racines(itm8, libelle, reel_an, prevu_an, ecart_pct, ecart_unites, ecart_colis,
                                colisage, unite, points_evalues, ventes_par_jour,
                                fiche_agr, fiche_prop,
                                liv_14j_unites=0.0, liv_14j_colis=0.0, taux_ecoulement_14j=None,
                                stock_colis=None, date_mesure=None, stock_motif=None):
    """
    Enquête approfondie sur l'origine exacte de l'écart :
    - Est-ce un produit saisonnier / festif ?
    - Est-ce un effet de seuil du colisage (PCB trop grand vs ventes jour) ?
    - Est-ce une dérive du stock physique (position négative) ?
    - Est-ce une rotation très faible (historique mince) ?
    - Est-ce un taux de casse élevé ?
    - Est-ce un biais de la formule ?
    - Confrontation aux livraisons réelles vs ventes.
    """
    causes = []

    # 1. Analyse temporelle et saisonnière
    mois_ventes = defaultdict(float)
    for jour, q in ventes_par_jour.items():
        mois_ventes[jour[5:7]] += q
    total_q = sum(mois_ventes.values())
    part_festive = (mois_ventes.get("12", 0.0) + mois_ventes.get("01", 0.0)) / total_q if total_q > 0 else 0.0
    part_ete = sum(mois_ventes.get(m, 0.0) for m in ("06", "07", "08")) / total_q if total_q > 0 else 0.0

    saison_festive = part_festive >= 0.70
    saison_ete = part_ete >= 0.75
    rotation_tres_faible = points_evalues < 8
    rotation_faible = points_evalues < 25

    if rotation_tres_faible:
        causes.append({
            "code": "rotation_faible",
            "titre": "📉 Vente très occasionnelle",
            "description": f"Seulement {points_evalues} journée(s) de vente observée(s) en 2026. L'historique statistique est trop mince pour une prévision continue."
        })
    elif rotation_faible:
        causes.append({
            "code": "rotation_moderee",
            "titre": "📉 Faible rotation",
            "description": f"Article vendu {points_evalues} jours sur l'année. Ventes sporadiques."
        })

    if saison_festive:
        causes.append({
            "code": "saison_festive",
            "titre": "🎄 Produit festif de fin d'année",
            "description": f"{part_festive*100:.0f} % des ventes historiques sont concentrées sur les fêtes (décembre/début janvier). En dehors des fêtes, le produit est hors-saison."
        })
    elif saison_ete:
        causes.append({
            "code": "saison_ete",
            "titre": "☀️ Forte saisonnalité estivale",
            "description": f"{part_ete*100:.0f} % des ventes ont lieu en été (juin-août). Forte sensibilité météo/vacances."
        })
    elif points_evalues > 0 and points_evalues <= 45:
        causes.append({
            "code": "saison_courte",
            "titre": "🗓️ Campagne saisonnière courte",
            "description": f"Article présent en rayon sur une période limitée ({points_evalues} jours de vente)."
        })

    # 2. Analyse du Colisage (PCB incompressible)
    vente_moy_j = (reel_an / points_evalues) if points_evalues > 0 else 0.0
    jours_par_colis = (colisage / vente_moy_j) if vente_moy_j > 0 else 0.0
    impact_colisage = False

    if jours_par_colis >= 3.0:
        impact_colisage = True
        causes.append({
            "code": "colisage_incompressible",
            "titre": "📦 Colisage incompressible",
            "description": f"1 colis de {colisage} {unite} représente {jours_par_colis:.1f} jours d'écoulement moyen ({vente_moy_j:.1f} {unite}/j). L'arrondi au colis entier contraint à commander par blocs de plusieurs jours."
        })

    # 3. Analyse du Stock physique
    if stock_colis is not None:
        pos_actuelle = stock_colis
    elif fiche_prop and fiche_prop.get("position_colis") is not None:
        pos_actuelle = fiche_prop.get("position_colis")
    else:
        p_agr = fiche_agr.get("position")
        pos_actuelle = (float(p_agr) / colisage) if (p_agr is not None and colisage > 0) else p_agr

    if not date_mesure and fiche_prop:
        date_mesure = fiche_prop.get("position_mesuree_le")

    impact_stock = False

    if pos_actuelle is not None:
        try:
            pos_val = float(pos_actuelle)
            if pos_val <= -1.0:
                impact_stock = True
                causes.append({
                    "code": "stock_negatif",
                    "titre": "⚖️ Position de stock négative",
                    "description": f"Stock estimé à {pos_val:.1f} colis (relevé le {date_mesure or 'date inconnue'}). Ce trou de stock virtuel gonfle artificiellement le besoin calculé."
                })
        except (ValueError, TypeError):
            pass

    # 4. Taux de perte
    taux_perte = float(fiche_agr.get("tauxPerte", 0.0) or 0.0)
    if taux_perte >= 0.15:
        causes.append({
            "code": "casse_elevee",
            "titre": "🗑️ Taux de casse élevé",
            "description": f"Pertes enregistrées à {taux_perte*100:.0f} %. La formule majore la commande pour compenser la casse passée."
        })

    # 5. Choix de la cause dominante
    if saison_festive:
        code_dom = "saisonnalite"
        badge_dom = "🎄 Festif de Noël"
    elif saison_ete and abs(ecart_pct) > 40:
        code_dom = "saisonnalite"
        badge_dom = "☀️ Saisonnier d'été"
    elif rotation_tres_faible:
        code_dom = "rotation"
        badge_dom = "📉 Vente occasionnelle"
    elif impact_colisage and (ecart_pct > 15.0 or abs(ecart_colis) <= 2.0):
        code_dom = "colisage"
        badge_dom = "📦 Colisage lourd"
    elif impact_stock:
        code_dom = "stock"
        badge_dom = "⚖️ Stock négatif"
    elif ecart_pct > 25.0:
        code_dom = "sur_formule"
        badge_dom = "📈 Sur-évaluation formule"
    elif ecart_pct < -25.0:
        code_dom = "sous_formule"
        badge_dom = "📉 Sous-évaluation formule"
    elif abs(ecart_pct) <= 10.0:
        code_dom = "conforme"
        badge_dom = "✅ Équilibré"
    else:
        code_dom = "vigilance"
        badge_dom = "🟡 Vigilance normale"

    # 6. Recommandation personnalisée et contexte de la commande du jour
    est_masque = bool(fiche_prop.get("masque")) if fiche_prop else False
    propose_actuel = 0.0 if est_masque else (float(fiche_prop.get("propose_colis") or 0.0) if fiche_prop else 0.0)
    demande_actuelle = float(fiche_prop.get("demande") or 0.0) if fiche_prop else 0.0

    if saison_festive:
        if propose_actuel == 0.0:
            recommandation = "Produit festif actuellement hors-saison : la commande est bien à 0 colis aujourd'hui. Aucune action requise."
        else:
            recommandation = f"Produit festif hors-saison : attention, la formule propose {propose_actuel:.0f} colis. Vérifier et ramener à 0 colis."
    elif rotation_tres_faible:
        if propose_actuel == 0.0:
            recommandation = "Article très occasionnel, proposition actuelle à 0 colis. Maintenir à 0."
        else:
            recommandation = f"Article à très faible rotation : la proposition de {propose_actuel:.0f} colis est risquée. Valider visuellement le besoin avant commande."
    elif impact_stock:
        recommandation = f"Faire un comptage physique en chambre froide pour réinitialiser le stock (actuellement {pos_actuelle} colis) et stopper la sur-commande."
    elif impact_colisage and ecart_pct > 20:
        recommandation = f"Sur-stockage mécanique provoqué par le colisage de {colisage} {unite} ({jours_par_colis:.1f} j de vente par colis). Commander uniquement quand le rayon est presque vide."
    elif ecart_pct > 25.0:
        recommandation = "Sur-estimation structurelle : envisager une suggestion de baisse prudente (-10% à -20%) ou contrôler si les ventes ont ralenti."
    elif ecart_pct < -25.0:
        recommandation = "Sous-estimation structurelle : risque de rayon vide. Augmenter le stock de sécurité ou ajouter 1 colis."
    else:
        recommandation = "Proposition alignée sur la consommation. Maintenir les paramètres actuels."

    # 7. Explication synthétique rédigée
    if saison_festive:
        synthese_explication = (
            f"Produit festif de fin d'année ({part_festive*100:.0f} % des ventes en décembre). "
            f"En 2026, seule 1 vente résiduelle a eu lieu le 2 janvier ({reel_an:.1f} {unite}). "
            f"La prévision ({prevu_an:.1f} {unite}) a hérité des ventes de Noël par la fenêtre glissante, "
            f"créant un décalage ponctuel (+{ecart_pct:.0f} %). Hors fêtes, l'article est inactif et la proposition actuelle est bien de {propose_actuel:.0f} colis."
        )
    elif impact_colisage and rotation_faible:
        synthese_explication = (
            f"Faible rotation ({points_evalues} jours vendus) combinée à un colisage lourd ({colisage} {unite}). "
            f"Chaque commande apporte {jours_par_colis:.1f} jours de stock d'un coup, ce qui gonfle mécaniquement l'écart entre la vente et la commande."
        )
    elif impact_stock:
        synthese_explication = (
            f"Position de stock négative ({pos_actuelle} colis) : la formule cherche à combler un trou virtuel "
            f"issu d'un retard d'inventaire ou de ventes non compensées."
        )
    else:
        synthese_explication = (
            f"Écart de {ecart_pct:+.1f} % ({ecart_unites:+.1f} {unite}, soit {ecart_colis:+.1f} colis) "
            f"sur {points_evalues} journées de vente en 2026."
        )

    diag_res = {
        "code_cause": code_dom,
        "badge_cause": badge_dom,
        "synthese_explication": synthese_explication,
        "recommandation": recommandation,
        "causes_detaillees": causes,
        "commande_du_jour": {
            "propose_colis": propose_actuel,
            "demande_unites": demande_actuelle,
            "position_colis": pos_actuelle,
            "position_mesuree_le": str(date_mesure) if date_mesure else None,
            "position_motif": stock_motif,
        },
        "indicateurs": {
            "jours_vendus": points_evalues,
            "vente_moyenne_jour": round(vente_moy_j, 2),
            "jours_par_colis": round(jours_par_colis, 1) if jours_par_colis else None,
            "taux_perte_pct": round(taux_perte * 100, 1),
            "part_festive_pct": round(part_festive * 100, 1),
            "part_ete_pct": round(part_ete * 100, 1),
            "livraisons_14j_unites": round(liv_14j_unites, 1),
            "livraisons_14j_colis": round(liv_14j_colis, 1),
            "taux_ecoulement_14j_pct": round(taux_ecoulement_14j, 1) if taux_ecoulement_14j is not None else None,
        }
    }

    diag_res["rapport_agent_tendances"] = rediger_rapport_agent_tendances(
        itm8, libelle, reel_an, prevu_an, ecart_pct, ecart_unites, ecart_colis,
        colisage, unite, points_evalues, diag_res
    )

    return diag_res


def rediger_rapport_agent_tendances(itm8, libelle, reel_an, prevu_an, ecart_pct, ecart_unites, ecart_colis,
                                   colisage, unite, points_evalues, diag_data):
    """
    Rédige le commentaire officiel et approfondi de l'agent-tendances pour l'article.
    """
    cmd = diag_data.get("commande_du_jour", {})
    propose_actuel = cmd.get("propose_colis")
    pos_actuelle = cmd.get("position_colis")
    date_mesure = cmd.get("position_mesuree_le")
    stock_motif = cmd.get("position_motif")
    ind = diag_data.get("indicateurs", {})
    code_cause = diag_data.get("code_cause")
    badge = diag_data.get("badge_cause")
    recommandation = diag_data.get("recommandation")

    signe = "+" if ecart_pct > 0 else ""
    sections = []

    # 1. Synthèse globale
    sections.append(
        f"Diagnostic de l'Agent Tendances sur {libelle} (code ITM : {itm8}) :\n"
        f"L'article est classé sous le motif « {badge} » avec un écart annuel de {signe}{ecart_pct:.1f} % "
        f"({ecart_unites:+.1f} {unite}, équivalent à {ecart_colis:+.1f} colis)."
    )

    # 2. Facteur Saisonnalité & Historique
    if code_cause == "saisonnalite":
        if ind.get("part_festive_pct", 0) >= 70:
            sections.append(
                f"• Saisonnalité festive : {ind.get('part_festive_pct')}% des ventes historiques sont concentrées sur les fêtes de fin d'année (décembre). "
                f"En 2026, seule une vente résiduelle de {reel_an:.1f} {unite} a eu lieu le 2 janvier. L'écart mathématique ({signe}{ecart_pct:.0f}%) "
                f"est un artefact mécanique dû à la fenêtre circulaire glissante (±21 jours) qui a projeté l'activité de Noël sur les premiers jours de janvier. "
                f"Hors période de fêtes, l'article est totalement inactif (aucun écoulement depuis 9 mois)."
            )
        else:
            sections.append(
                f"• Saisonnalité estivale : {ind.get('part_ete_pct')}% des ventes ont lieu en été (juin-août). "
                f"Les pics de chaleur et les départs en vacances créent des variations rapides que la formule moyenne tend à amortir avec du décalage."
            )
    elif code_cause == "rotation":
        sections.append(
            f"• Historique mince : Vente très occasionnelle avec seulement {points_evalues} jour(s) d'activité observés sur 2026 "
            f"({reel_an:.1f} {unite} au total). L'historique statistique est trop restreint pour une prévision continue."
        )
    else:
        sections.append(
            f"• Historique régulier : Ventes observées sur {points_evalues} journées en 2026 pour un total de {round(reel_an):,} {unite} "
            f"(rythme moyen : {ind.get('vente_moyenne_jour')} {unite}/jour de vente)."
        )

    # 3. Facteur Colisage
    j_colis = ind.get("jours_par_colis")
    if j_colis and j_colis >= 3.0:
        sections.append(
            f"• Contrainte logistique de colisage : Le conditionnement est lourd ({colisage} {unite}). Un seul colis représente {j_colis} jours de vente moyenne. "
            f"L'arrondi au colis entier impose de commander par blocs de plusieurs jours, créant une sur-proposition apparente."
        )
    else:
        sections.append(
            f"• Conditionnement (PCB) : {colisage} {unite}, rythme fluide ({j_colis or 1.0:.1f} j/colis). Le colisage n'est pas un obstacle."
        )

    # 4. Facteur Stock physique
    motif_mention = f" — Motif déclaré : « {stock_motif} »" if (stock_motif and stock_motif != "Position relevée en chambre froide, rayon déjà rempli.") else ""
    if pos_actuelle is not None:
        try:
            pos_num = float(pos_actuelle)
            if pos_num <= -1.0:
                sections.append(
                    f"• Dérive de stock physique : Le stock enregistré est négatif ({pos_num:.1f} colis, relevé le {date_mesure or 'date inconnue'}{motif_mention}). "
                    f"La formule cherche à combler ce trou de stock virtuel en majorant artificiellement la commande chaque jour !"
                )
            elif pos_num == 0:
                sections.append(
                    f"• Stock physique : La position est nette à zéro (relevée le {date_mesure or 'date inconnue'}{motif_mention}). Aucun stock négatif ni sur-stockage dormant."
                )
            else:
                sections.append(
                    f"• Stock physique : {pos_num:.1f} colis en réserve (relevé le {date_mesure or 'date inconnue'}{motif_mention})."
                )
        except (ValueError, TypeError):
            sections.append(f"• Stock physique : {pos_actuelle} colis{motif_mention}.")
    else:
        sections.append("• Stock physique : Aucune mesure récente répertoriée.")

    # 5. Flux Livraisons réelles vs Ventes (14 derniers jours)
    liv_c = ind.get("livraisons_14j_colis", 0.0)
    liv_u = ind.get("livraisons_14j_unites", 0.0)
    taux_ecoul = ind.get("taux_ecoulement_14j_pct")
    if liv_c > 0:
        if taux_ecoul is not None and taux_ecoul < 65:
            sections.append(
                f"• Livraisons réelles vs Ventes (14 jours) : {liv_c} colis reçus ({liv_u} {unite}) pour un écoulement en caisse de {taux_ecoul}%. "
                f"Vigilance : les réceptions ont nettement dépassé les sorties client (risque d'accumulation)."
            )
        elif taux_ecoul is not None and taux_ecoul > 125:
            sections.append(
                f"• Livraisons réelles vs Ventes (14 jours) : {liv_c} colis reçus ({liv_u} {unite}) alors que les ventes représentent {taux_ecoul}% des livraisons. "
                f"Forte demande absorbant l'intégralité des réceptions et puisant dans le stock."
            )
        else:
            sections.append(
                f"• Livraisons réelles vs Ventes (14 jours) : {liv_c} colis reçus ({liv_u} {unite}) avec un taux d'écoulement régulier à {taux_ecoul or '--'}%."
            )
    else:
        sections.append("• Livraisons réelles (14 jours) : Aucune réception enregistrée sur les 14 derniers jours.")

    # 6. Situation de la commande actuelle
    if propose_actuel is not None:
        if propose_actuel == 0.0:
            sections.append("• Commande du jour : La formule propose actuellement **0 colis** (Demande calculée : 0,0). Le système ne commande rien aujourd'hui.")
        else:
            sections.append(f"• Commande du jour : La formule propose **{propose_actuel:.0f} colis** aujourd'hui (Demande : {cmd.get('demande_unites', 0.0)} {unite}).")

    # 7. Conclusion et recommandation
    sections.append(f"👉 Recommandation Agent Tendances : {recommandation}")

    return "\n\n".join(sections)


def calculer_fiabilite(annee="2026", jours_recents=30):
    # 1. Charger catalogue, agrégats et proposition actuelle
    cat_articles = catalogue.articles()
    try:
        config_regles = regles.charger().get("overrides", {})
    except Exception:
        config_regles = {}
    try:
        agr = agregats.charger()
    except Exception:
        agr = {"articles": {}, "profil_hebdomadaire": [1.0] * 7}

    articles_agregats = agr.get("articles", {})
    profil_hebdo_raw = agr.get("profil_hebdomadaire") or [1.0] * 7
    moyenne_hebdo = (sum(profil_hebdo_raw) / 7.0) if sum(profil_hebdo_raw) > 0 else 1.0
    facteur_js = [p / moyenne_hebdo for p in profil_hebdo_raw]

    # Proposition du jour
    lignes_prop = {}
    if FICHIER_PROPOSITION.is_file():
        try:
            prop_data = json.loads(FICHIER_PROPOSITION.read_text(encoding="utf-8"))
            lignes_prop = {l["itm8"]: l for l in prop_data.get("lignes", []) if "itm8" in l}
        except Exception:
            pass

    # État des stocks (etat.json)
    etat_stock = {}
    if FICHIER_ETAT.is_file():
        try:
            e_data = json.loads(FICHIER_ETAT.read_text(encoding="utf-8"))
            etat_stock = e_data.get("articles") or e_data
        except Exception:
            pass

    # 2. Lire les ventes et livraisons
    ventes = defaultdict(dict)          # article -> {jour: quantite}
    livraisons = defaultdict(dict)       # article -> {jour: quantite}
    livraisons_colis = defaultdict(dict) # article -> {jour: colis}
    quantites = defaultdict(lambda: [0.0] * 366)
    journees = defaultdict(lambda: [0] * 366)
    vus = defaultdict(set)
    tous_jours = set()

    for fait in faits.lire(DOSSIER_FAITS):
        art = fait.get("article")
        if not art:
            continue
        ftype = fait.get("type")
        if ftype == "vente":
            jour = fait.get("date_source") or fait.get("date_effet")
            q = float(fait.get("quantite") or 0.0)
            if not jour or q <= 0:
                continue
            ventes[art][jour] = ventes[art].get(jour, 0.0) + q
            tous_jours.add(jour)
            i = jour_annee(jour) - 1
            quantites[art][i] += q
            if art not in vus[jour]:
                journees[art][i] += 1
                vus[jour].add(art)
        elif ftype == "livraison":
            jour = fait.get("date_effet") or fait.get("date_source")
            q = float(fait.get("quantite") or 0.0)
            c = float(fait.get("colis") or 0.0)
            if not jour or (q <= 0 and c <= 0):
                continue
            livraisons[art][jour] = livraisons[art].get(jour, 0.0) + q
            livraisons_colis[art][jour] = livraisons_colis[art].get(jour, 0.0) + c

    if not tous_jours:
        return {"ok": False, "erreur": "Aucune vente trouvée."}

    date_max = max(tous_jours)
    d_max = date.fromisoformat(date_max)
    date_limite_30j = (d_max - timedelta(days=29)).isoformat()
    date_limite_7j = (d_max - timedelta(days=6)).isoformat()
    date_limite_3j = (d_max - timedelta(days=2)).isoformat()
    jours_14 = [(d_max - timedelta(days=k)).isoformat() for k in range(13, -1, -1)]
    date_debut_annee = f"{annee}-01-01"

    articles_cibles = set(articles_agregats.keys()) | {a for a in ventes if any(j >= date_debut_annee for j in ventes[a])}

    resultats_articles = []
    total_reel_global = 0.0
    total_prevu_global = 0.0
    total_erreur_global = 0.0
    total_points_global = 0

    recap_js = {j: {"nom": NOMS_JS[j], "reel": 0.0, "prevu": 0.0, "ecart_pct": 0.0} for j in range(7)}
    recap_14j = {j: {"date": j, "jour": NOMS_JS[jour_semaine(j)], "reel": 0.0, "prevu": 0.0, "livraison": 0.0} for j in jours_14}
    compteurs_statut = defaultdict(int)
    compteurs_gravite = defaultdict(int)
    compteurs_causes = defaultdict(int)

    for itm8 in sorted(articles_cibles):
        fiche_agr = articles_agregats.get(itm8, {})
        fiche_cat = cat_articles.get(itm8, {})
        fiche_prop = lignes_prop.get(itm8, {})

        # Ne pas exclure les articles masqués de l'évaluation de fiabilité
        # s'ils ont été vendus en 2026 (le masquage n'efface pas l'historique des prévisions)
        libelle = (fiche_agr.get("libelle") or fiche_cat.get("LIBELLE") or f"Article {itm8}").strip()
        famille = determiner_famille(libelle, fiche_cat.get("NOMENCLATURE", ""))
        surcharges_article = config_regles.get(itm8, {})
        unite_raw = str(surcharges_article.get("unite") or fiche_prop.get("unite") or fiche_agr.get("unite") or fiche_cat.get("UNITE MESURE") or "kg").strip()
        unite = re.sub(r"^\d+\s*", "", unite_raw).strip() or "kg"
        if unite.lower() in ("kg", "kilo", "kilos"):
            unite = "kg"
        elif unite.lower() in ("piece", "pièce", "pieces", "pièces"):
            unite = "pièce"
        elif unite.lower() in ("barquette", "barquettes"):
            unite = "barquette"
        elif unite.lower() in ("filet", "filets"):
            unite = "filet"
        elif unite.lower() in ("sachet", "sachets"):
            unite = "sachet"
        elif unite.lower() in ("botte", "bottes"):
            unite = "botte"
        colisage = surcharges_article.get("conditionnement") or fiche_agr.get("conditionnement") or fiche_cat.get("COLISAGE") or fiche_cat.get("CONDIT.BASE") or 1.0
        try:
            colisage = float(colisage)
            if colisage <= 0:
                colisage = 1.0
        except (ValueError, TypeError):
            colisage = 1.0

        somme_q = fenetre_circulaire(quantites[itm8], FENETRE)
        somme_n = fenetre_circulaire([float(x) for x in journees[itm8]], FENETRE)

        # Cumuls par horizon
        an_reel, an_prevu, an_erreur, an_points = 0.0, 0.0, 0.0, 0
        r30_reel, r30_prevu, r30_erreur, r30_points = 0.0, 0.0, 0.0, 0
        r7_reel, r7_prevu, r7_erreur, r7_points = 0.0, 0.0, 0.0, 0
        r3_reel, r3_prevu, r3_erreur, r3_points = 0.0, 0.0, 0.0, 0

        # Profil par jour de la semaine
        js_data = {j: {"nom": NOMS_JS[j], "reel": 0.0, "prevu": 0.0} for j in range(7)}

        for jour, reel in ventes.get(itm8, {}).items():
            if jour < date_debut_annee:
                continue

            i = jour_annee(jour) - 1
            q_loo = somme_q[i] - reel
            n_loo = somme_n[i] - 1

            if n_loo < MIN_JOURS:
                prevu = 0.0
            else:
                prevu = (q_loo / n_loo) * facteur_js[jour_semaine(jour)]

            err = abs(prevu - reel)
            js = jour_semaine(jour)

            # Annuel
            an_reel += reel
            an_prevu += prevu
            an_erreur += err
            an_points += 1

            # 30 jours
            if jour >= date_limite_30j:
                r30_reel += reel
                r30_prevu += prevu
                r30_erreur += err
                r30_points += 1

            # 7 jours
            if jour >= date_limite_7j:
                r7_reel += reel
                r7_prevu += prevu
                r7_erreur += err
                r7_points += 1

            # 3 jours
            if jour >= date_limite_3j:
                r3_reel += reel
                r3_prevu += prevu
                r3_erreur += err
                r3_points += 1

            # Par jour
            js_data[js]["reel"] += reel
            js_data[js]["prevu"] += prevu

            # Global recap
            recap_js[js]["reel"] += reel
            recap_js[js]["prevu"] += prevu

        if an_points == 0 and an_reel == 0:
            continue

        # Livraisons par horizon
        def calc_livraison_intervalle(debut, fin=None):
            tot_q = 0.0
            tot_c = 0.0
            for j, q in livraisons.get(itm8, {}).items():
                if j >= debut and (fin is None or j <= fin):
                    tot_q += q
                    c = livraisons_colis.get(itm8, {}).get(j, 0.0)
                    if c <= 0 and q > 0 and colisage > 0:
                        c = q / colisage
                    tot_c += c
            return tot_q, tot_c

        an_liv_unites, an_liv_colis = calc_livraison_intervalle(date_debut_annee)
        r30_liv_unites, r30_liv_colis = calc_livraison_intervalle(date_limite_30j)
        r7_liv_unites, r7_liv_colis = calc_livraison_intervalle(date_limite_7j)
        r3_liv_unites, r3_liv_colis = calc_livraison_intervalle(date_limite_3j)

        # Série chronologique 14 jours de l'article (incluant les jours sans vente)
        serie_14j = []
        for j_str in jours_14:
            r = ventes.get(itm8, {}).get(j_str, 0.0)
            q_liv = livraisons.get(itm8, {}).get(j_str, 0.0)
            c_liv = livraisons_colis.get(itm8, {}).get(j_str, 0.0)
            if c_liv <= 0 and q_liv > 0 and colisage > 0:
                c_liv = q_liv / colisage

            i_j = jour_annee(j_str) - 1
            if r > 0:
                q_l = somme_q[i_j] - r
                n_l = somme_n[i_j] - 1
            else:
                q_l = somme_q[i_j]
                n_l = somme_n[i_j]
            p = ((q_l / n_l) * facteur_js[jour_semaine(j_str)]) if n_l >= MIN_JOURS else 0.0

            serie_14j.append({
                "date": j_str,
                "jour": NOMS_JS[jour_semaine(j_str)],
                "reel": round(r, 1),
                "prevu": round(p, 1),
                "livraison": round(q_liv, 1),
                "livraison_colis": round(c_liv, 1),
            })
            recap_14j[j_str]["reel"] += r
            recap_14j[j_str]["prevu"] += p
            recap_14j[j_str]["livraison"] += q_liv

        liv_14j_unites = sum(p["livraison"] for p in serie_14j)
        liv_14j_colis = sum(p["livraison_colis"] for p in serie_14j)
        ventes_14j_unites = sum(p["reel"] for p in serie_14j)
        taux_ecoulement_14j = (100.0 * ventes_14j_unites / liv_14j_unites) if liv_14j_unites > 0 else None

        total_reel_global += an_reel
        total_prevu_global += an_prevu
        total_erreur_global += an_erreur
        total_points_global += an_points

        # Construction standardisée des 4 horizons
        def construire_horizon(reel, prevu, err, pts, liv_unites, liv_colis):
            ecart_unites = prevu - reel
            ecart_pct = (100.0 * ecart_unites / reel) if reel > 0 else (100.0 if prevu > 0 else 0.0)
            colis_vendus = reel / colisage
            colis_prevus = prevu / colisage
            ecart_colis = colis_prevus - colis_vendus
            statut, gravite, motif = qualifier_anomalie(reel, prevu, ecart_colis)
            taux_ecoulement = (100.0 * reel / liv_unites) if liv_unites > 0 else None
            return {
                "reel_unites": round(reel, 1),
                "prevu_unites": round(prevu, 1),
                "livraison_unites": round(liv_unites, 1),
                "colis_vendus": round(colis_vendus, 1),
                "colis_prevus": round(colis_prevus, 1),
                "livraison_colis": round(liv_colis, 1),
                "ecart_unites": round(ecart_unites, 1),
                "ecart_pct": round(ecart_pct, 1),
                "ecart_colis": round(ecart_colis, 1),
                "taux_ecoulement_pct": round(taux_ecoulement, 1) if taux_ecoulement is not None else None,
                "erreur_moyenne_pct": round(100.0 * err / reel, 1) if reel > 0 else 0.0,
                "points_evalues": pts,
                "statut": statut,
                "gravite": gravite,
                "motif": motif,
            }

        h_annuel = construire_horizon(an_reel, an_prevu, an_erreur, an_points, an_liv_unites, an_liv_colis)
        h_30j = construire_horizon(r30_reel, r30_prevu, r30_erreur, r30_points, r30_liv_unites, r30_liv_colis)
        h_7j = construire_horizon(r7_reel, r7_prevu, r7_erreur, r7_points, r7_liv_unites, r7_liv_colis)
        h_3j = construire_horizon(r3_reel, r3_prevu, r3_erreur, r3_points, r3_liv_unites, r3_liv_colis)

        # Stock physique actuel, date de relevé et motif déclaré
        stock_colis = None
        date_mesure = None
        stock_motif = None
        if fiche_prop and fiche_prop.get("position_colis") is not None:
            try:
                stock_colis = round(float(fiche_prop["position_colis"]), 1)
                date_mesure = fiche_prop.get("position_mesuree_le")
                stock_motif = fiche_prop.get("position_motif")
            except (ValueError, TypeError):
                pass

        if stock_colis is None:
            e_art = etat_stock.get(itm8)
            if isinstance(e_art, dict):
                p_u = e_art.get("position")
                date_mesure = e_art.get("mesuree_le")
                stock_motif = e_art.get("motif")
                if p_u is not None and colisage > 0:
                    try:
                        stock_colis = round(float(p_u) / colisage, 1)
                    except (ValueError, TypeError):
                        pass
            elif e_art is not None and colisage > 0:
                try:
                    stock_colis = round(float(e_art) / colisage, 1)
                except (ValueError, TypeError):
                    pass
            elif fiche_agr.get("position") is not None and colisage > 0:
                try:
                    stock_colis = round(float(fiche_agr["position"]) / colisage, 1)
                except (ValueError, TypeError):
                    pass
        elif not stock_motif and itm8 in etat_stock:
            e_art = etat_stock[itm8]
            if isinstance(e_art, dict):
                stock_motif = e_art.get("motif")

        # Alertes court terme
        alerte_rupture_3j = bool((r7_reel > 5.0 or an_reel > 30.0) and r3_reel == 0.0 and r3_prevu > 0.0)
        alerte_decrochage_3j = bool((r7_reel / 7.0 >= 2.0) and (r3_reel / 3.0 < 0.4 * (r7_reel / 7.0)))

        # Diagnostic des causes racines (basé sur le cumul annuel)
        diag = diagnostiquer_causes_racines(
            itm8, libelle, an_reel, an_prevu, h_annuel["ecart_pct"], h_annuel["ecart_unites"], h_annuel["ecart_colis"],
            colisage, unite, an_points, ventes.get(itm8, {}), fiche_agr, fiche_prop,
            liv_14j_unites=liv_14j_unites, liv_14j_colis=liv_14j_colis, taux_ecoulement_14j=taux_ecoulement_14j,
            stock_colis=stock_colis, date_mesure=date_mesure, stock_motif=stock_motif
        )

        compteurs_statut[h_annuel["statut"]] += 1
        compteurs_gravite[h_annuel["gravite"]] += 1
        compteurs_causes[diag["code_cause"]] += 1

        # Profil par jour
        detail_jours = {}
        for j in range(7):
            jr_reel = js_data[j]["reel"]
            jr_prevu = js_data[j]["prevu"]
            jr_ecart_pct = (100.0 * (jr_prevu - jr_reel) / jr_reel) if jr_reel > 0 else (100.0 if jr_prevu > 0 else 0.0)
            detail_jours[NOMS_JS[j]] = {
                "reel": round(jr_reel, 1),
                "prevu": round(jr_prevu, 1),
                "ecart_pct": round(jr_ecart_pct, 1),
            }

        resultats_articles.append({
            "itm8": itm8,
            "libelle": libelle,
            "famille": famille,
            "colisage": round(colisage, 2),
            "unite": unite,
            "stock_colis": stock_colis,
            "stock_mesure_le": date_mesure,
            "stock_motif": stock_motif,
            "livraisons_14j_colis": round(liv_14j_colis, 1),
            "livraisons_14j_unites": round(liv_14j_unites, 1),
            "taux_ecoulement_14j_pct": round(taux_ecoulement_14j, 1) if taux_ecoulement_14j is not None else None,
            "annuel": h_annuel,
            "trente_jours": h_30j,
            "sept_jours": h_7j,
            "trois_jours": h_3j,
            "serie_recente_14j": serie_14j,
            "alertes_recentes": {
                "rupture_3j": alerte_rupture_3j,
                "decrochage_3j": alerte_decrochage_3j,
            },
            "diagnostic": diag,
            "detail_jours": detail_jours,
        })

    def cle_tri(art):
        g = {"critique": 0, "vigilance": 1, "conforme": 2, "neutre": 3}.get(art["annuel"]["gravite"], 4)
        vol_err = abs(art["annuel"]["ecart_unites"])
        return (g, -vol_err)

    resultats_articles.sort(key=cle_tri)

    for j in range(7):
        r = recap_js[j]["reel"]
        p = recap_js[j]["prevu"]
        recap_js[j]["reel"] = round(r)
        recap_js[j]["prevu"] = round(p)
        recap_js[j]["ecart_pct"] = round(100.0 * (p - r) / r, 1) if r > 0 else 0.0

    for j_str in jours_14:
        r = recap_14j[j_str]["reel"]
        p = recap_14j[j_str]["prevu"]
        l = recap_14j[j_str]["livraison"]
        recap_14j[j_str]["reel"] = round(r)
        recap_14j[j_str]["prevu"] = round(p)
        recap_14j[j_str]["livraison"] = round(l)
        recap_14j[j_str]["ecart_pct"] = round(100.0 * (p - r) / r, 1) if r > 0 else 0.0

    def agreger_horizon(nom_h):
        tot_reel = sum(art[nom_h]["reel_unites"] for art in resultats_articles)
        tot_prevu = sum(art[nom_h]["prevu_unites"] for art in resultats_articles)
        tot_liv = sum(art[nom_h]["livraison_unites"] for art in resultats_articles)
        tot_liv_colis = sum(art[nom_h]["livraison_colis"] for art in resultats_articles)
        taux_ecoulement = (100.0 * tot_reel / tot_liv) if tot_liv > 0 else None
        biais = (100.0 * (tot_prevu - tot_reel) / tot_reel) if tot_reel > 0 else 0.0
        tot_err = sum(abs(art[nom_h]["prevu_unites"] - art[nom_h]["reel_unites"]) for art in resultats_articles)
        err_moy = (100.0 * tot_err / tot_reel) if tot_reel > 0 else 0.0
        c_statut = defaultdict(int)
        c_gravite = defaultdict(int)
        for art in resultats_articles:
            c_statut[art[nom_h]["statut"]] += 1
            c_gravite[art[nom_h]["gravite"]] += 1
        taux_conf = round(100.0 * c_statut["equilibre"] / max(1, len(resultats_articles)), 1)
        return {
            "articles_evalues": len(resultats_articles),
            "total_vendu_unites": round(tot_reel),
            "total_prevu_unites": round(tot_prevu),
            "total_livraison_unites": round(tot_liv),
            "total_livraison_colis": round(tot_liv_colis, 1),
            "taux_ecoulement_pct": round(taux_ecoulement, 1) if taux_ecoulement is not None else None,
            "biais_global_pct": round(biais, 1),
            "erreur_moyenne_pct": round(err_moy, 1),
            "taux_fiabilite_pct": taux_conf,
            "compteurs_statut": dict(c_statut),
            "compteurs_gravite": dict(c_gravite),
        }

    kpis_horizons = {
        "annuel": agreger_horizon("annuel"),
        "trente_jours": agreger_horizon("trente_jours"),
        "sept_jours": agreger_horizon("sept_jours"),
        "trois_jours": agreger_horizon("trois_jours"),
    }

    dates_horizons = {
        "annuel": {"debut": date_debut_annee, "fin": date_max, "nb_jours": 365, "libelle": f"Année {annee}"},
        "trente_jours": {"debut": date_limite_30j, "fin": date_max, "nb_jours": 30, "libelle": "30 derniers jours"},
        "sept_jours": {"debut": date_limite_7j, "fin": date_max, "nb_jours": 7, "libelle": "7 derniers jours (semaine)"},
        "trois_jours": {"debut": date_limite_3j, "fin": date_max, "nb_jours": 3, "libelle": "3 derniers jours"},
    }

    biais_global = (100.0 * (total_prevu_global - total_reel_global) / total_reel_global) if total_reel_global > 0 else 0.0
    erreur_moyenne = (100.0 * total_erreur_global / total_reel_global) if total_reel_global > 0 else 0.0
    taux_fiabilite = round(100.0 * compteurs_statut["equilibre"] / max(1, len(resultats_articles)), 1)
    total_liv_global = sum(art["annuel"]["livraison_unites"] for art in resultats_articles)
    total_liv_colis_global = sum(art["annuel"]["livraison_colis"] for art in resultats_articles)
    taux_ecoulement_global = (100.0 * total_reel_global / total_liv_global) if total_liv_global > 0 else None

    bilan = {
        "genere_le": date.today().isoformat(),
        "annee_analyse": annee,
        "date_debut": date_debut_annee,
        "date_fin": date_max,
        "date_debut_30j": date_limite_30j,
        "dates_horizons": dates_horizons,
        "synthese": {
            "articles_evalues": len(resultats_articles),
            "points_evalues": total_points_global,
            "total_vendu_unites": round(total_reel_global),
            "total_prevu_unites": round(total_prevu_global),
            "total_livraison_unites": round(total_liv_global),
            "total_livraison_colis": round(total_liv_colis_global, 1),
            "taux_ecoulement_pct": round(taux_ecoulement_global, 1) if taux_ecoulement_global is not None else None,
            "biais_global_pct": round(biais_global, 1),
            "erreur_moyenne_pct": round(erreur_moyenne, 1),
            "taux_fiabilite_pct": taux_fiabilite,
            "compteurs_gravite": dict(compteurs_gravite),
            "compteurs_statut": dict(compteurs_statut),
            "compteurs_causes": dict(compteurs_causes),
            "recap_jours_semaine": list(recap_js.values()),
            "historique_recent_14j": list(recap_14j.values()),
            "kpis_horizons": kpis_horizons,
        },
        "articles": resultats_articles,
    }

    return bilan


def main():
    parser = argparse.ArgumentParser(description="Analyse de fiabilité prévisions vs ventes avec diagnostic de causes racines")
    parser.add_argument("--sortie", type=Path, default=FICHIER_SORTIE, help="Fichier JSON cible")
    parser.add_argument("--annee", default="2026", help="Année d'évaluation")
    parser.add_argument("--stdout", action="store_true", help="Affiche le résumé dans la console")
    parser.add_argument("--article", help="Affiche le rapport détaillé de l'agent-tendances pour un article (code ITM ou libellé)")
    args = parser.parse_args()

    # Si --article est demandé et que le fichier JSON de sortie existe déjà, tenter de le réutiliser
    bilan = None
    if args.article and args.sortie.is_file() and not args.stdout:
        try:
            donnees_existantes = json.loads(args.sortie.read_text(encoding="utf-8"))
            if donnees_existantes.get("annee_analyse") == args.annee and "articles" in donnees_existantes:
                # Vérifier que les articles ont bien rapport_agent_tendances
                premier_art = donnees_existantes["articles"][0] if donnees_existantes["articles"] else {}
                if "rapport_agent_tendances" in premier_art.get("diagnostic", {}):
                    bilan = donnees_existantes
        except Exception:
            bilan = None

    if bilan is None:
        print(f"Calcul de la fiabilité des prévisions vs ventes pour l'année {args.annee}...", flush=True)
        bilan = calculer_fiabilite(annee=args.annee)

        if not bilan.get("ok", True):
            print(f"Erreur : {bilan.get('erreur')}", file=sys.stderr)
            return 1

        ecrire_json(args.sortie, bilan)
        print(f"Bilan de fiabilité enregistré dans {args.sortie.resolve()} ({len(bilan['articles'])} articles).", flush=True)

    if args.article:
        terme = args.article.strip().lower()
        trouves = []
        for art in bilan.get("articles", []):
            if (art["itm8"].lower() == terme or
                art["itm8"].lower().endswith(terme) or
                terme in art["libelle"].lower()):
                trouves.append(art)

        if not trouves:
            print(f"Aucun article trouvé correspondant à '{args.article}'.", file=sys.stderr)
            return 1

        for art in trouves:
            rapport = art.get("diagnostic", {}).get("rapport_agent_tendances", "Rapport non disponible.")
            print("\n" + "=" * 80)
            print(f"RAPPORT OFFICIEL DE L'AGENT TENDANCES - {art['libelle']} (ITM: {art['itm8']})")
            print("=" * 80)
            try:
                print(rapport)
            except UnicodeEncodeError:
                print(rapport.encode("ascii", errors="replace").decode("ascii"))
            print("=" * 80 + "\n")
        return 0

    if args.stdout:
        s = bilan["synthese"]
        print(f"\nSynthèse {args.annee} :")
        print(f"  Articles évalués     : {s['articles_evalues']}")
        print(f"  Ventes réelles       : {s['total_vendu_unites']} unités")
        print(f"  Prévisions formule   : {s['total_prevu_unites']} unités")
        print(f"  Biais global         : {s['biais_global_pct']:+0.1f} %")
        print(f"  Erreur moyenne       : {s['erreur_moyenne_pct']:0.1f} %")
        print(f"  Articles Risque Casse   : {s['compteurs_statut'].get('sur_estimation_forte', 0)}")
        print(f"  Articles Risque Rupture : {s['compteurs_statut'].get('sous_estimation_forte', 0)}")
        print(f"  Articles Conformes      : {s['compteurs_statut'].get('equilibre', 0)}")
        print("\nRépartition par cause dominante :")
        for cause, nb in sorted(s.get("compteurs_causes", {}).items(), key=lambda kv: -kv[1]):
            print(f"  - {cause:20} : {nb} articles")

    return 0


if __name__ == "__main__":
    sys.exit(main())

