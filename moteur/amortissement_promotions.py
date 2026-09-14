"""
moteur/amortissement-promotions.py - Gestion de l'amortissement et de la désescalade en fin de promotion.

Règles métier :
1. PENDANT LA PROMOTION (du début jusqu'à l'avant-dernier jour) :
   L'offre prospectus stimule les ventes.
2. À J-1 DU DERNIER JOUR (livraison le dernier jour de la promo) :
   La commande ne doit couvrir strictement que la dernière journée de l'opération,
   sans constituer de stock pour le lendemain.
   -> Facteur d'amortissement : 0.80 sur la commande.
3. LE DERNIER JOUR DE LA PROMOTION (livraison le lendemain, après la fin de l'offre) :
   Le produit repasse au tarif normal. Les ventes chutent brutalement (« trou post-promo »).
   La commande doit éviter tout sur-stockage post-catalogue.
   -> Facteur d'amortissement : 0.70 sur la commande standard et neutralisation des volumes promo.
"""
from datetime import date, datetime, timedelta
import json
from pathlib import Path
import re

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
                    "statut_corresp": corresp.get("statut", "confirme")
                }
    return par_itm8


def evaluer_amortissement(itm8, date_commande, date_livraison, offres=None):
    """
    Évalue si un article est concerné par une fin de promotion et quel facteur d'amortissement appliquer.

    Retourne :
    {
        "en_fin_promo": bool,
        "phase": "dernier_jour" | "post_promo" | "en_cours" | "hors_promo",
        "facteur_amortissement": float (ex: 0.80, 0.70 ou 1.0),
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

    debut = info["debut"]
    fin = info["fin"]
    nom = info["nom_offre"]

    # Cas 1 : Livraison après la fin de promo (commande passée le dernier jour ou juste après)
    if date_commande == fin or (date_livraison > fin and date_commande <= fin):
        return {
            "en_fin_promo": True,
            "phase": "post_promo",
            "facteur_amortissement": 0.70,
            "motif": f"Fin de promo le {fin} ({nom}) : amortissement post-catalogue appliqué (-30%) pour éponger les stocks.",
            "fin_promo": fin,
            "nom_offre": nom
        }

    # Cas 2 : Livraison le dernier jour de la promo (commande passée la veille de la fin)
    if date_livraison == fin:
        return {
            "en_fin_promo": True,
            "phase": "dernier_jour",
            "facteur_amortissement": 0.80,
            "motif": f"Dernier jour promo ({fin}) : commande limitée à la couverture du jour sans stock résiduel.",
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
