"""Audit automatisé des colisages et des unités de mesure du magasin.

Détecte les colisages palette (ex. 60 filets pour PDT au lieu de caissette de 8)
et les unités contradictoires (ex. barquette/filet/sachet codé en kg dans Mercalys).
Génère donnees/audit-colisages.json et permet d'appliquer les corrections.
"""
import argparse
from datetime import datetime, date
import json
import math
from pathlib import Path
import re
import sys

RACINE = Path(__file__).resolve().parent.parent
DONNEES = RACINE / "donnees"

sys.path.insert(0, str(Path(__file__).resolve().parent))
import journal_agents as carnet_agents
import regles
from verrou_donnees import append_jsonl, verrou_donnees


def _clean_str(val):
    return str(val or "").strip()


def auditer(dossier=DONNEES):
    dossier = Path(dossier)
    fichier_cat = dossier / "catalogue.json"
    cat_data = json.loads(fichier_cat.read_text(encoding="utf-8-sig")) if fichier_cat.exists() else {}
    articles_cat = cat_data.get("articles", {})

    decisions_lignes = []
    fichier_dec = dossier / "decisions.jsonl"
    if fichier_dec.exists():
        with fichier_dec.open(encoding="utf-8-sig") as f:
            decisions_lignes = [json.loads(l) for l in f if l.strip()]

    # Dernières décisions effectives
    unite_dec = {}
    pcb_dec = {}
    for d in decisions_lignes:
        code = d.get("article")
        if not code:
            continue
        if d.get("type") == "unite":
            unite_dec[code] = d.get("valeur")
        elif d.get("type") == "conditionnement":
            try:
                val = float(d.get("valeur"))
                if math.isfinite(val) and val > 0:
                    pcb_dec[code] = val
            except (ValueError, TypeError):
                pass

    anomalies = []
    
    for code, art in sorted(articles_cat.items()):
        libelle = art.get("LIBELLE", "")
        lib_upper = libelle.upper()
        famille = art.get("NOMENCLATURE", "F&L").split(" ", 2)[-1] if " " in art.get("NOMENCLATURE", "") else "F&L"
        
        # Unité actuelle
        u_base = art.get("UNITE MESURE", "")
        u_actuelle = unite_dec.get(code) or (u_base.split(" ")[-1] if " " in u_base else u_base) or "kg"
        u_actuelle = u_actuelle.lower()
        if u_actuelle in ("pièce", "piece", "pieces"):
            u_actuelle = "pièce"

        # Colisage actuel
        pcb_actuel = pcb_dec.get(code) or art.get("CONDIT.BASE") or 1.0
        try:
            pcb_actuel = float(pcb_actuel)
        except (ValueError, TypeError):
            pcb_actuel = 1.0

        anomalie = None

        # Règle 1: Filets PDT (2kg, 2.5kg, 5kg) avec colisage palette (>= 25)
        if re.search(r"\bPDT\b|POMMES? DE TERRE", lib_upper):
            if any(k in lib_upper for k in ("2KG", "2 KG", "2,0KG", "2.0KG")):
                if pcb_actuel >= 25:
                    anomalie = {
                        "type": "colisage_palette",
                        "gravite": "critique",
                        "colisage_recommande": 8.0,
                        "unite_recommandee": "filet",
                        "motif": f"Colisage palette ({pcb_actuel:g} filets) dans Mercalys. Colisage caissette magasin standard = 8 filets (16 kg)."
                    }
            elif any(k in lib_upper for k in ("2.5KG", "2,5KG", "2.5 KG", "2,5 KG")):
                if pcb_actuel >= 25:
                    anomalie = {
                        "type": "colisage_palette",
                        "gravite": "critique",
                        "colisage_recommande": 6.0,
                        "unite_recommandee": "filet",
                        "motif": f"Colisage palette ({pcb_actuel:g} filets) dans Mercalys. Colisage caissette magasin standard = 6 filets (15 kg)."
                    }
            elif any(k in lib_upper for k in ("5KG", "5 KG")):
                if pcb_actuel >= 25:
                    anomalie = {
                        "type": "colisage_palette",
                        "gravite": "critique",
                        "colisage_recommande": 5.0,
                        "unite_recommandee": "filet",
                        "motif": f"Colisage palette ({pcb_actuel:g} filets) dans Mercalys. Colisage caissette magasin standard = 5 filets (25 kg)."
                    }
            elif "FILET" in lib_upper and u_actuelle == "kg":
                anomalie = {
                    "type": "unite_incoherente",
                    "gravite": "critique",
                    "colisage_recommande": pcb_actuel,
                    "unite_recommandee": "filet",
                    "motif": f"Filet de pomme de terre codé en kg dans Mercalys au lieu de l'unité filet."
                }

        # Règle 2: Agrumes en filet (Orange, Clémentine, Citron) avec colisage palette (>= 30)
        elif any(f in lib_upper for f in ("ORANGE", "CLEMENTINE", "MANDARINE", "CITRON")) and "FILET" in lib_upper:
            if pcb_actuel >= 30:
                recommande = 8.0 if ("3KG" in lib_upper or "3 KG" in lib_upper) else 9.0
                anomalie = {
                    "type": "colisage_palette",
                    "gravite": "critique",
                    "colisage_recommande": recommande,
                    "unite_recommandee": "filet",
                    "motif": f"Colisage palette ({pcb_actuel:g} filets) dans Mercalys. Colisage caissette standard = {recommande:g} filets."
                }
            elif u_actuelle == "kg":
                anomalie = {
                    "type": "unite_incoherente",
                    "gravite": "critique",
                    "colisage_recommande": pcb_actuel,
                    "unite_recommandee": "filet",
                    "motif": f"Agrume en filet vendu à la pièce/filet mais déclaré en kg dans Mercalys."
                }

        # Règle 3: Pommes/Fruits en sachet (ex: GALA SACHET 3KG avec 34 sachets)
        elif "SACHET" in lib_upper and pcb_actuel >= 25 and any(w in lib_upper for w in ("2KG", "3KG", "POMME")):
            anomalie = {
                "type": "colisage_palette",
                "gravite": "critique",
                "colisage_recommande": 6.0,
                "unite_recommandee": "sachet",
                "motif": f"Colisage palette ({pcb_actuel:g} sachets) dans Mercalys. Colisage caissette standard = 6 sachets (18 kg)."
            }

        # Règle 4: Produits pré-emballés déclarés avec l'unité 'kg' au lieu de l'unité physique
        if not anomalie:
            if ("BARQUETTE" in lib_upper or " BTE " in lib_upper or lib_upper.endswith(" BTE")) and u_actuelle == "kg":
                anomalie = {
                    "type": "unite_incoherente",
                    "gravite": "critique",
                    "colisage_recommande": pcb_actuel if pcb_actuel <= 25 else 10.0,
                    "unite_recommandee": "barquette",
                    "motif": f"Barquette pré-emballée vendue à l'unité mais encodée en kg dans Mercalys."
                }
            elif "FILET" in lib_upper and u_actuelle == "kg":
                anomalie = {
                    "type": "unite_incoherente",
                    "gravite": "critique",
                    "colisage_recommande": pcb_actuel if pcb_actuel <= 20 else 8.0,
                    "unite_recommandee": "filet",
                    "motif": f"Produit en filet vendu à la pièce mais encodé en kg dans Mercalys."
                }
            elif "SACHET" in lib_upper and u_actuelle == "kg":
                anomalie = {
                    "type": "unite_incoherente",
                    "gravite": "critique",
                    "colisage_recommande": pcb_actuel if pcb_actuel <= 25 else 10.0,
                    "unite_recommandee": "sachet",
                    "motif": f"Produit en sachet unitaire encodé en kg dans Mercalys."
                }
            elif "BOTTE" in lib_upper and u_actuelle == "kg":
                anomalie = {
                    "type": "unite_incoherente",
                    "gravite": "critique",
                    "colisage_recommande": pcb_actuel if pcb_actuel <= 25 else 10.0,
                    "unite_recommandee": "botte",
                    "motif": f"Produit en botte (poireau, asperge, carotte) encodé en kg dans Mercalys."
                }

        if anomalie:
            anomalies.append({
                "itm8": code,
                "libelle": libelle,
                "famille": famille,
                "colisage_actuel": pcb_actuel,
                "colisage_recommande": anomalie["colisage_recommande"],
                "unite_actuelle": u_actuelle,
                "unite_recommandee": anomalie["unite_recommandee"],
                "type_anomalie": anomalie["type"],
                "gravite": anomalie["gravite"],
                "motif_audit": anomalie["motif"],
            })

    synthese = {
        "total_anomalies": len(anomalies),
        "colisages_palette": sum(1 for a in anomalies if a["type_anomalie"] == "colisage_palette"),
        "unites_incoherentes": sum(1 for a in anomalies if a["type_anomalie"] == "unite_incoherente"),
    }

    rapport = {
        "ok": True,
        "date_audit": datetime.now().isoformat(timespec="seconds"),
        "total_articles_analyses": len(articles_cat),
        "synthese": synthese,
        "anomalies": anomalies
    }

    return rapport


def sauvegarder_rapport(rapport, dossier=DONNEES):
    chemin = Path(dossier) / "audit-colisages.json"
    chemin.write_text(json.dumps(rapport, ensure_ascii=False, indent=1), encoding="utf-8")
    return chemin


def appliquer_corrections(anomalies, auteur="agent-donnees", dossier=DONNEES):
    dossier = Path(dossier)
    carnet = dossier / "decisions.jsonl"
    lignes = []
    maintenant = datetime.now().astimezone().isoformat(timespec="seconds")
    jour = date.today().isoformat()
    
    numero_action = carnet_agents.numero_action()

    for i, a in enumerate(anomalies):
        code = a["itm8"]
        lib = a["libelle"]
        motif = a["motif_audit"]

        # 1. Décision d'unité si changement
        if a["unite_actuelle"] != a["unite_recommandee"]:
            lignes.append({
                "id": f"unite:{code}:{numero_action}:{len(lignes)}",
                "type": "unite",
                "article": code,
                "valeur": a["unite_recommandee"],
                "valide_a_partir_de": jour,
                "motif": f"Audit automatisé colisage/unité : {motif}",
                "auteur": auteur,
                "enregistre_le": maintenant,
                "action": numero_action
            })

        # 2. Décision de conditionnement si changement
        if a["colisage_actuel"] != a["colisage_recommande"]:
            lignes.append({
                "id": f"conditionnement:{code}:{numero_action}:{len(lignes)}",
                "type": "conditionnement",
                "article": code,
                "valeur": str(a["colisage_recommande"]),
                "valide_a_partir_de": jour,
                "motif": f"Audit automatisé colisage/unité : {motif}",
                "auteur": auteur,
                "enregistre_le": maintenant,
                "action": numero_action
            })

    if lignes:
        with verrou_donnees(dossier):
            append_jsonl(carnet, lignes)

    return len(lignes), numero_action


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--appliquer", action="store_true", help="Applique automatiquement les corrections détectées dans decisions.jsonl")
    p.add_argument("--code", help="Cibler un code ITM8 spécifique")
    p.add_argument("--auteur", default="agent-donnees", help="Auteur des décisions")
    args = p.parse_args()

    rapport = auditer()
    if args.code:
        rapport["anomalies"] = [a for a in rapport["anomalies"] if a["itm8"] == args.code]
        rapport["synthese"]["total_anomalies"] = len(rapport["anomalies"])

    sauvegarder_rapport(rapport)
    print(f"Audit terminé : {rapport['synthese']['total_anomalies']} anomalie(s) détectée(s) sur {rapport['total_articles_analyses']} articles.")
    for a in rapport["anomalies"]:
        print(f" - [{a['itm8']}] {a['libelle']} : {a['colisage_actuel']} {a['unite_actuelle']} -> {a['colisage_recommande']} {a['unite_recommandee']} ({a['motif_audit']})")

    if args.appliquer:
        nb, action = appliquer_corrections(rapport["anomalies"], auteur=args.auteur)
        print(f"\n{nb} décision(s) enregistrée(s) sous l'action {action}.")
        # Relancer audit après application
        nouveau_rapport = auditer()
        sauvegarder_rapport(nouveau_rapport)


if __name__ == "__main__":
    main()
