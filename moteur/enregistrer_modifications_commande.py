"""
Enregistrement des modifications de commande et constitution de la base d'entraînement IA.

Ce module remplit deux missions indissociables (Contrat CP-04 - Documentation IA Ch. 24.3) :
1. Archiver la proposition algorithmique originale avant tout choix humain.
2. Enregistrer chaque modification manuelle avec son contexte décisionnel complet
   (météo, jour, stock, ventes, prix, prévisions, motif) dans le carnet d'entraînement
   donnees/entrainement-ajustements.jsonl pour l'apprentissage futur des modèles d'IA.
"""
from datetime import date, datetime
import json
import math
from pathlib import Path
import sys
import uuid

RACINE = Path(__file__).resolve().parent.parent
MOTEUR = RACINE / "moteur"
DONNEES = RACINE / "donnees"

if str(MOTEUR) not in sys.path:
    sys.path.insert(0, str(MOTEUR))

import journal_agents
from verrou_donnees import append_jsonl, verrou_donnees


def archiver_proposition_base(dossier_donnees=None):
    """Archive la proposition calculée du jour dans donnees/propositions/."""
    dossier = Path(dossier_donnees) if dossier_donnees else DONNEES
    fichier_prop = dossier / "proposition.json"
    if not fichier_prop.exists():
        raise FileNotFoundError("Aucune proposition.json trouvée à archiver.")
    
    with verrou_donnees(dossier):
        prop = json.loads(fichier_prop.read_text(encoding="utf-8"))
        date_cmd = prop.get("date_commande") or date.today().isoformat()
        dossier_archives = dossier / "propositions"
        dossier_archives.mkdir(parents=True, exist_ok=True)
        
        cible = dossier_archives / f"proposition-{date_cmd}.json"
        if not cible.exists():
            # Ne jamais écraser la baseline originale si elle est déjà gelée
            cible.write_text(json.dumps(prop, ensure_ascii=False, indent=1), encoding="utf-8")
        
        # S'assurer également que les prévisions journalières sont archivées
        try:
            from previsions_archivees import archiver as archiver_prev
            archiver_prev(dossier, prop)
        except Exception:
            pass
            
        return cible


def enregistrer_modification(article_itm8, quantite_colis, motif=None, agent="responsable-rayon",
                             source="app/commander.html", dossier_donnees=None):
    """Enregistre un ajustement de commande et génère la ligne d'entraînement IA."""
    dossier = Path(dossier_donnees) if dossier_donnees else DONNEES
    if not isinstance(article_itm8, str) or not article_itm8.strip():
        raise ValueError("Code article ITM8 invalide.")
    article_itm8 = article_itm8.strip()

    try:
        colis = float(quantite_colis)
    except (TypeError, ValueError):
        raise ValueError("La quantité en colis doit être un nombre.")
    if not math.isfinite(colis) or colis < 0:
        raise ValueError("La quantité en colis doit être un nombre fini positif ou nul.")

    fichier_prop = dossier / "proposition.json"
    if not fichier_prop.exists():
        raise FileNotFoundError("proposition.json introuvable.")

    with verrou_donnees(dossier):
        # 1. Vérifier ou archiver la baseline
        archiver_proposition_base(dossier)

        prop = json.loads(fichier_prop.read_text(encoding="utf-8"))
        lignes = {l.get("itm8"): l for l in prop.get("lignes", []) if l.get("itm8")}
        ligne = lignes.get(article_itm8)
        if not ligne:
            raise ValueError(f"Article {article_itm8} introuvable dans la proposition.")

        date_commande = prop.get("date_commande") or date.today().isoformat()
        date_livraison = prop.get("date_livraison") or date_commande
        date_ref = prop.get("date_reference") or ""

        avant = float(ligne.get("propose_colis") or 0.0)
        apres = round(colis, 2)
        ecart = round(apres - avant, 2)
        ratio = round(apres / avant, 4) if avant > 0 else (None if apres == 0 else 999.0)

        if apres == 0 and avant > 0:
            type_ajust = "annulation"
        elif apres < avant:
            type_ajust = "baisse"
        elif apres > avant:
            type_ajust = "hausse"
        else:
            type_ajust = "maintien"

        motif_final = (motif.strip() if (motif and motif.strip())
                       else f"Ajustement manuel responsable de rayon ({avant:g} -> {apres:g} colis)")

        # Numéro d'action auditable
        try:
            action_id = journal_agents.numero_action()
        except Exception:
            action_id = f"A-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:4]}"

        maintenant_iso = datetime.now().isoformat(timespec="seconds")

        # 2. Entrée standard dans ajustements.jsonl (utilisée par commander.html & recalcul)
        entree_ajustement = {
            "date_commande": date_commande,
            "article": article_itm8,
            "libelle": ligne.get("libelle") or article_itm8,
            "avant": avant,
            "apres": apres,
            "applique": True,
            "motif": motif_final,
            "agent": agent,
            "action": action_id,
            "enregistre_le": maintenant_iso,
        }
        append_jsonl(dossier / "ajustements.jsonl", [entree_ajustement])

        # 3. Entrée enrichie dans entrainement-ajustements.jsonl pour l'apprentissage IA
        entree_entrainement = {
            "schema": 1,
            "id": f"entrainement:{date_commande}:{article_itm8}:{datetime.now().strftime('%Y%m%dT%H%M%S')}:{uuid.uuid4().hex[:6]}",
            "horodatage": maintenant_iso,
            "date_commande": date_commande,
            "date_livraison": date_livraison,
            "date_reference_ventes": date_ref,
            "article": article_itm8,
            "article_stock": ligne.get("article_stock") or article_itm8,
            "libelle": ligne.get("libelle") or article_itm8,
            "famille": ligne.get("groupe") or "inconnu",
            "fournisseur": ligne.get("fournisseur") or "inconnu",
            "conditionnement": float(ligne.get("conditionnement") or 1.0),
            "unite": str(ligne.get("unite") or "colis"),
            "position_stock_colis": ligne.get("position_colis"),
            "position_stock_unites": ligne.get("position_unites"),
            "vente_moyenne_jour": ligne.get("vente_moyenne_jour"),
            "taux_perte": ligne.get("taux_perte"),
            "demande_calculee_moteur": ligne.get("demande"),
            "previsions_journalieres": ligne.get("previsions_journalieres") or {},
            "propose_ia_colis": avant,
            "choix_humain_colis": apres,
            "ecart_colis": ecart,
            "ratio_humain_ia": ratio,
            "type_ajustement": type_ajust,
            "prix_achat": ligne.get("prix_achat"),
            "prix_vente": ligne.get("prix_vente"),
            "marge_pct": ligne.get("marge_pct"),
            "promotion": bool(ligne.get("promotion")),
            "fin_promotion": bool(ligne.get("fin_promotion")),
            "motif_fin_promotion": ligne.get("motif_fin_promotion"),
            "alerte_marge": ligne.get("alerte_marge"),
            "alerte_fusion": ligne.get("alerte_fusion"),
            "meteo_livraison": prop.get("meteo_livraison") or {},
            "facteurs_moteur": prop.get("facteurs") or {},
            "motif": motif_final,
            "auteur": agent,
            "action": action_id,
            "source": source,
        }
        append_jsonl(dossier / "entrainement-ajustements.jsonl", [entree_entrainement])

        # 4. Traçabilité dans le journal des agents
        try:
            journal_agents.enregistrer(
                agent=agent,
                action=action_id,
                message=f"Commande ajustée : {ligne.get('libelle')} {avant:g} -> {apres:g} colis",
                motif=motif_final,
                changements=[{"itm8": article_itm8, "champ": "commande", "avant": avant, "apres": apres}],
                annulable=False,
                details={"date_commande": date_commande, "applique": True, "source": source}
            )
        except Exception:
            pass

    return {
        "ok": True,
        "date_commande": date_commande,
        "article": article_itm8,
        "libelle": ligne.get("libelle") or article_itm8,
        "avant": avant,
        "apres": apres,
        "action": action_id,
        "ajustement": entree_ajustement,
        "entrainement": entree_entrainement,
    }


def enregistrer_lot_ajustements(ajustements_liste, agent="responsable-rayon",
                                source="app/commander.html", dossier_donnees=None):
    """Enregistre un ensemble d'ajustements pour une commande."""
    if not isinstance(ajustements_liste, list):
        raise ValueError("Liste d'ajustements attendue.")
    resultats = []
    for item in ajustements_liste:
        if not isinstance(item, dict):
            continue
        itm8 = item.get("itm8") or item.get("article")
        colis = item.get("colis") if item.get("colis") is not None else item.get("apres")
        motif = item.get("motif")
        if itm8 and colis is not None:
            res = enregistrer_modification(itm8, colis, motif=motif, agent=agent,
                                           source=source, dossier_donnees=dossier_donnees)
            resultats.append(res)
    return resultats
