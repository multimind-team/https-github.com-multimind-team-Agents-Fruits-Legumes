"""Prévisions de ventes conservées avant le jour observé, en ajout seul.

Ce carnet analytique est distinct des faits de stock. Aucune commande passée
ne peut servir à le remplir rétroactivement. Lecture pure ; écriture seulement
sur appel explicite du générateur, après publication de la proposition.
"""
from datetime import date, datetime
import hashlib
import json
import math
from pathlib import Path

from verrou_donnees import append_jsonl, verrou_donnees


def _instant(valeur):
    if isinstance(valeur, str):
        valeur = datetime.fromisoformat(valeur)
    if not isinstance(valeur, datetime):
        raise ValueError("Horodatage de prévision invalide.")
    # Les dates de ventes sont des dates civiles magasin. L'heure locale de
    # cette installation, également utilisée par le moteur, fait référence.
    return valeur.astimezone()


def _jour(valeur):
    if not isinstance(valeur, str) or len(valeur) != 10:
        raise ValueError("Date de prévision invalide.")
    return date.fromisoformat(valeur)


def _quantite(valeur):
    if isinstance(valeur, bool) or not isinstance(valeur, (int, float)):
        raise ValueError("La prévision doit être une quantité numérique.")
    try:
        n = float(valeur)
    except (ValueError, OverflowError):
        raise ValueError("Quantité de prévision non finie.") from None
    if not math.isfinite(n) or n < 0:
        raise ValueError("Quantité de prévision négative ou non finie.")
    return n


def lire(donnees):
    """Dernière prévision valide enregistrée AVANT chaque journée civile.

    Retourne {(article_stock, date): snapshot}. Le lecteur refuse les archives
    incohérentes et ne crée aucun dossier, fichier ou verrou technique.
    """
    resultat, connus = {}, {}
    for chemin in sorted((Path(donnees) / "previsions").glob("*.jsonl")):
        with chemin.open(encoding="utf-8") as flux:
            for numero, ligne in enumerate(flux, 1):
                if not ligne.strip():
                    continue
                try:
                    item = json.loads(ligne)
                    if not isinstance(item, dict) or item.get("schema") != 1:
                        raise ValueError("Schéma non reconnu")
                    identifiant, article = item.get("id"), item.get("article")
                    if not isinstance(identifiant, str) or not identifiant or not isinstance(article, str) or not article:
                        raise ValueError("Identité absente")
                    jour, instant = _jour(item["date"]), _instant(item["enregistre_le"])
                    _quantite(item["quantite"])
                    if instant.date() >= jour:
                        raise ValueError("Prévision enregistrée pendant ou après le jour prévu")
                    signature = json.dumps(item, sort_keys=True, allow_nan=False)
                    if identifiant in connus and connus[identifiant] != signature:
                        raise ValueError("Identifiant de prévision contradictoire")
                    connus[identifiant] = signature
                    cle = (article, item["date"])
                    precedent = resultat.get(cle)
                    if precedent is None or instant >= _instant(precedent["enregistre_le"]):
                        resultat[cle] = item
                except (ValueError, TypeError, KeyError, OverflowError) as exc:
                    raise ValueError(f"Archive de prévisions invalide ({chemin.name}:{numero}) : {exc}.") from exc
    return resultat


def archiver(donnees, proposition, maintenant=None):
    """Ajoute les prévisions futures du calcul qui vient d'être publié.

    `maintenant` est injectable pour les fixtures ; en production l'horloge
    réelle d'écriture est utilisée, jamais la date déclarée par la proposition.
    """
    dossier = Path(donnees)
    instant = _instant(maintenant if maintenant is not None else datetime.now().astimezone())
    horodatage = instant.isoformat(timespec="microseconds")
    candidats, ignores_passe = {}, 0
    for ligne in proposition.get("lignes", []):
        offre = ligne.get("itm8")
        if not offre:
            continue
        porteur = ligne.get("commande_groupe_portee_par")
        if porteur and porteur != offre:
            continue
        article = ligne.get("article_stock") or offre
        serie = ligne.get("previsions_journalieres") or {}
        if not isinstance(serie, dict):
            raise ValueError("Prévisions journalières invalides.")
        for iso, quantite in serie.items():
            jour = _jour(iso)
            if jour <= instant.date():
                ignores_passe += 1
                continue
            q = _quantite(quantite)
            item = {"schema": 1, "type": "prevision-vente", "article": article,
                    "offre": offre, "date": iso, "quantite": q,
                    "unite": ligne.get("unite"), "conditionnement": ligne.get("conditionnement"),
                    "enregistre_le": horodatage, "calcul_genere_le": proposition.get("genere_le"),
                    "date_commande": proposition.get("date_commande"),
                    "operation": proposition.get("_operation_id")}
            cle = (article, iso)
            if cle in candidats and candidats[cle]["quantite"] != q:
                raise ValueError("Prévisions contradictoires entre deux offres du même stock.")
            candidats[cle] = item
    if not candidats:
        return {"ajoutes": 0, "ignores_passe": ignores_passe}
    with verrou_donnees(dossier):
        precedents = lire(dossier)
        ajoutes = []
        for cle, item in sorted(candidats.items()):
            precedent = precedents.get(cle)
            champs = ("quantite", "unite", "conditionnement", "offre")
            if precedent and all(precedent.get(c) == item.get(c) for c in champs):
                continue
            empreinte = hashlib.sha256(json.dumps(item, sort_keys=True, allow_nan=False).encode("utf-8")).hexdigest()
            item["id"] = "prevision:" + empreinte
            ajoutes.append(item)
        append_jsonl(dossier / "previsions" / f"{instant.year}.jsonl", ajoutes)
    return {"ajoutes": len(ajoutes), "ignores_passe": ignores_passe}
