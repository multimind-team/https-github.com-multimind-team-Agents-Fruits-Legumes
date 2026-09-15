"""
moteur/analyser-marges-mercuriale.py - Analyse des variations de prix d'achat et protection de la marge.

Ce module examine chaque matin les prix d'achat du cadencier Webtelevente (mercuriale centrale) :
1. Il compare le prix d'achat brut du jour au prix d'achat précédent et à la moyenne récente.
2. Il calcule le taux de marge brute théorique prévisionnel : (PV - PA) / PV.
3. Il détecte les dérives critiques :
   - Hausse brutale du prix d'achat (>= +15 % ou +20 %).
   - Marge dégradée (< 20 %) ou vente à perte (PA > PV).
4. Il enregistre les alertes dans donnees/alertes-marges.json pour affichage dans la Note du matin
   et sur l'écran de commande, permettant au responsable d'ajuster le prix de vente en caisse.

Usage :
  python moteur/analyser-marges-mercuriale.py
"""
from datetime import date, datetime, timedelta
from copy import deepcopy
import json
import math
from pathlib import Path
import re
import sys

RACINE = Path(__file__).resolve().parent.parent
DONNEES = RACINE / "donnees"
FICHIER_CADENCIER = DONNEES / "cadencier-du-jour.json"
FICHIER_HISTO_PRIX = DONNEES / "historique-prix-achat.json"
FICHIER_ALERTES = DONNEES / "alertes-marges.json"

sys.path.insert(0, str(RACINE / "moteur"))
import catalogue
from ecriture_derivee import ecrire_json
from verrou_donnees import operation_donnees


SEUIL_HAUSSE_ALERTE = 15.0     # +15 % d'augmentation
SEUIL_MARGE_MINIMALE = 20.0    # 20 % de taux de marque minimum souhaité en F&L


def charger_historique_prix():
    if FICHIER_HISTO_PRIX.exists():
        try:
            return json.loads(FICHIER_HISTO_PRIX.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


@operation_donnees(lambda: DONNEES)
def analyser_cadencier(cadencier=None, historique=None):
    if cadencier is None:
        cadencier = json.loads(FICHIER_CADENCIER.read_text(encoding="utf-8")) if FICHIER_CADENCIER.exists() else {}
    historique = historique if historique is not None else charger_historique_prix()

    date_cadencier = cadencier.get("date_cadencier") or date.today().isoformat()
    articles_cadencier = cadencier.get("articles", [])

    alertes = []
    prix_a_jour = deepcopy(historique.get("prix_par_article", {}))

    for a in articles_cadencier:
        itm8 = a.get("article")
        nom = a.get("nom", "Article sans nom")
        offres = a.get("offres", [])
        if not itm8 or not offres:
            continue

        # On retient la première offre active
        offre = offres[0]
        pa = offre.get("prix_achat")
        pvc = offre.get("prix_vente_conseille")
        if pa is None or pa <= 0:
            continue
        pa = round(float(pa), 3)

        # Prix de vente de référence (PVC du cadencier ou prix catalogue)
        pv = None
        if pvc is not None and float(pvc) > 0:
            pv = round(float(pvc), 2)
        else:
            pv_cat = catalogue.prix(itm8)
            if pv_cat:
                try:
                    pv = round(float(pv_cat), 2)
                except (ValueError, TypeError):
                    pass

        # Historique de cet article
        histo_art = prix_a_jour.get(str(itm8), [])
        dernier_pa = histo_art[-1]["prix_achat"] if histo_art else None
        date_dernier = histo_art[-1]["date"] if histo_art else None

        # Si le prix précédent est le même jour, on regarde l'avant-dernier
        if date_dernier == date_cadencier and len(histo_art) >= 2:
            dernier_pa = histo_art[-2]["prix_achat"]
            date_dernier = histo_art[-2]["date"]

        hausse_pct = None
        if dernier_pa and dernier_pa > 0 and date_dernier != date_cadencier:
            hausse_pct = round(((pa - dernier_pa) / dernier_pa) * 100.0, 1)

        # Calcul taux de marge : (PV - PA) / PV
        taux_marge = None
        if pv and pv > 0:
            taux_marge = round(((pv - pa) / pv) * 100.0, 1)

        # Détection d'anomalie
        est_alerte = False
        motifs = []
        gravite = "info"

        if hausse_pct is not None and hausse_pct >= SEUIL_HAUSSE_ALERTE:
            est_alerte = True
            gravite = "avertissement"
            motifs.append(f"Hausse d'achat de +{hausse_pct:.1f}% ({pa:.2f} € vs {dernier_pa:.2f} € le {date_dernier})")

        if pv and pa > pv:
            est_alerte = True
            gravite = "critique"
            motifs.append(f"Vente à perte potentielle (Achat {pa:.2f} € > Vente {pv:.2f} €)")
        elif taux_marge is not None and taux_marge < SEUIL_MARGE_MINIMALE:
            est_alerte = True
            if gravite != "critique":
                gravite = "avertissement"
            motifs.append(f"Marge brute faible ({taux_marge:.1f}% < seuil {SEUIL_MARGE_MINIMALE}%)")

        if est_alerte:
            recommandation = "Ajuster le prix de vente en caisse pour protéger la marge."
            if pv and pa > pv:
                recommandation = "URGENT : Rehausser immédiatement le prix de vente en caisse."
            alertes.append({
                "itm8": itm8,
                "nom": nom,
                "prix_achat_actuel": pa,
                "prix_achat_precedent": dernier_pa,
                "date_prix_precedent": date_dernier,
                "hausse_pct": hausse_pct,
                "prix_vente": pv,
                "taux_marge": taux_marge,
                "gravite": gravite,
                "motifs": motifs,
                "recommandation": recommandation
            })

        # Mettre à jour l'historique
        if not histo_art or histo_art[-1]["date"] != date_cadencier:
            histo_art.append({"date": date_cadencier, "prix_achat": pa})
            # On conserve les 30 derniers relevés
            prix_a_jour[str(itm8)] = histo_art[-30:]
        else:
            histo_art[-1]["prix_achat"] = pa
            prix_a_jour[str(itm8)] = histo_art

    rapport = {
        "calcule_le": datetime.now().isoformat(),
        "date_cadencier": date_cadencier,
        "nombre_articles_analyses": len(articles_cadencier),
        "nombre_alertes": len(alertes),
        "alertes": sorted(alertes, key=lambda x: (x["gravite"] != "critique", -(x.get("hausse_pct") or 0)))
    }

    # Sauvegarder l'historique actualisé
    nouveau_histo = {
        "mis_a_jour_le": datetime.now().isoformat(),
        "prix_par_article": prix_a_jour
    }
    ecrire_json(FICHIER_HISTO_PRIX, nouveau_histo)
    ecrire_json(FICHIER_ALERTES, rapport)
    return rapport


def main():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    print("Analyse des prix d'achat et des marges sur le cadencier du jour...")
    rapport = analyser_cadencier()
    alertes = rapport["alertes"]
    print(f"  Articles analyses : {rapport['nombre_articles_analyses']}")
    print(f"  Alertes detectees : {len(alertes)}")
    if not alertes:
        print("  Aucune hausse brutale ni anomalie de marge détectée.")
        return 0

    print("\n--- ALERTES PRIX & MARGES ---")
    for a in alertes[:15]:
        symb = "[CRITIQUE]" if a["gravite"] == "critique" else "[ATTENTION]"
        print(f"{symb} {a['nom']} ({a['itm8']})")
        for m in a["motifs"]:
            print(f"    - {m}")
        print(f"    -> Action conseillée : {a['recommandation']}")
    return 0


if __name__ == "__main__":
    main()
