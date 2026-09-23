"""Repères de fin de promotion, sans réduction automatique de commande.

Seules les correspondances confirmées portent le repère FIN PROMO. Le facteur
reste neutre : une baisse exige la vérification des ventes et du contexte externe,
puis le circuit de suggestion/validation de ajuster-commande.py.
"""
import json
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
DONNEES = RACINE / "donnees"
FICHIER_PROMOTIONS = DONNEES / "promotions.json"


def charger_promotions(chemin=None):
    chemin = chemin or FICHIER_PROMOTIONS
    if not chemin.exists():
        return []
    try:
        data = json.loads(chemin.read_text(encoding="utf-8"))
        return data.get("offres", [])
    except Exception:
        return []


def index_promotions_par_itm8(offres):
    """Indexe les offres par code itm8."""
    par_itm8 = {}
    for offre in offres:
        debut = offre.get("debut")
        fin = offre.get("fin")
        nom_offre = offre.get("nom", "")
        for corresp in offre.get("correspondances", []):
            itm8 = corresp.get("itm8")
            if itm8:
                par_itm8[str(itm8)] = {
                    "nom_offre": nom_offre,
                    "debut": debut,
                    "fin": fin,
                    "statut_corresp": corresp.get("statut", "a_confirmer")
                }
    return par_itm8


def evaluer_amortissement(itm8, date_commande, date_livraison, offres=None):
    """
    Évalue le repère de fin de promotion ; le facteur reste toujours neutre.

    Retourne :
    {

    Retourne :
    {
        "en_fin_promo": bool,
        "phase": "dernier_jour" | "post_promo" | "en_cours" | "hors_promo",
        "facteur_amortissement": 1.0,
        "motif": str ou None,
        "fin_promo": str ou None,
        "nom_offre": str ou None
    }
    """
    if offres is None:
        offres = charger_promotions()
    index = index_promotions_par_itm8(offres)
    info = index.get(str(itm8))
    if not info or not info.get("debut") or not info.get("fin"):
        return {
            "en_fin_promo": False,
            "phase": "hors_promo",
            "facteur_amortissement": 1.0,
            "motif": None,
            "fin_promo": None,
            "nom_offre": None
        }

    statut = str(info.get("statut_corresp", "")).lower().strip()
    if statut not in ("confirme", "confirmee", "confirmé", "confirmée"):
        return {"en_fin_promo": False, "phase": "a_confirmer",
                "facteur_amortissement": 1.0, "motif": None,
                "fin_promo": info["fin"], "nom_offre": info["nom_offre"]}

    debut = info["debut"]
    fin = info["fin"]
    nom = info["nom_offre"]

    from datetime import date
    try:
        d_cmd = date.fromisoformat(date_commande)
        d_fin = date.fromisoformat(fin)
        jours_apres_fin = (d_cmd - d_fin).days
    except Exception:
        jours_apres_fin = 999

    # Cas 1 : Livraison après la fin de promo ou dans la fenêtre de sortie de promo (jusqu'à 7 jours post-promo)
    if date_commande == fin or (date_livraison > fin and date_commande <= fin) or (1 <= jours_apres_fin <= 7):
        return {
            "en_fin_promo": True,
            "phase": "post_promo",
            "facteur_amortissement": 1.0,
            "motif": f"Offre {nom} terminée le {fin}. Prévision calée sur les ventes de référence hors-promo (semaine S-1 pré-prospectus) pour éviter les à-coups et la sur-commande post-promo.",
            "fin_promo": fin,
            "nom_offre": nom
        }

    # Cas 2 : Livraison le dernier jour de la promo (commande passée la veille de la fin)
    if date_livraison == fin:
        return {
            "en_fin_promo": True,
            "phase": "dernier_jour",
            "facteur_amortissement": 1.0,
            "motif": f"Dernier jour de promotion ({fin}, {nom}). Quantité de transition maintenue ; retour aux ventes normales S-1 dès la prochaine livraison.",
            "fin_promo": fin,
            "nom_offre": nom
        }

    # Cas 3 : Promotion active en cours
    if debut <= date_livraison <= fin:
        return {
            "en_fin_promo": False,
            "phase": "en_cours",
            "facteur_amortissement": 1.0,
            "motif": f"Promotion en cours jusqu'au {fin} ({nom}).",
            "fin_promo": fin,
            "nom_offre": nom
        }

    return {
        "en_fin_promo": False,
        "phase": "hors_promo",
        "facteur_amortissement": 1.0,
        "motif": None,
        "fin_promo": None,
        "nom_offre": None
    }
