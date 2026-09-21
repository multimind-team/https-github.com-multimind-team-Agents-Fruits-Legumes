"""Détail en lecture seule du calcul de position, jamais un inventaire physique.

Le calcul pur du moteur décide de la base et des mouvements appliqués. Ce
module ne publie aucun état, ne prend aucun bail et ne change aucun réglage.
"""
from collections import Counter, defaultdict
from datetime import date
from functools import lru_cache
import importlib.util
import json
import math
from pathlib import Path
import unicodedata

import faits

FLUX = {"livraison": "livraisons", "vente": "ventes", "casse": "casse", "don": "dons"}
LIMITES = [
    "Cohérence physique non établie : ce détail reproduit le calcul sur les faits connus, sans certifier leur complétude ni la réalité du rayon.",
    "La position est un écart au rayon plein, pas un stock physique total ni une quantité vendable attestée.",
    "Une somme nulle signifie zéro parmi les faits appliqués connus ; elle ne prouve pas l'absence réelle de mouvement ni la présence de tous les documents.",
    "La phase matin/soir/avant-livraison est la convention du moteur ; 17 h ou la réception d'un mail ne prouvent pas que la livraison était physiquement comprise dans le comptage.",
    "Les équivalents en colis utilisent le PCB actuel pour l'affichage ; ils ne reconvertissent pas les comptages historiques.",
]


@lru_cache(maxsize=1)
def _moteur():
    spec = importlib.util.spec_from_file_location("_rapprochement_calcul_position", Path(__file__).with_name("calculer-position.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _nombre(valeur):
    if isinstance(valeur, bool):
        return None
    try:
        n = float(valeur)
        return n if math.isfinite(n) else None
    except (ValueError, TypeError, OverflowError):
        return None


def _arrondi(valeur):
    nombre = _nombre(valeur)
    return round(nombre, 3) if nombre is not None else None


def _jour(fait):
    return fait.get("date_effet") or fait.get("date_source")


def _date(valeur):
    try:
        return date.fromisoformat(valeur).isoformat() if isinstance(valeur, str) else None
    except ValueError:
        return None


def _unite(valeur):
    texte = unicodedata.normalize("NFKD", str(valeur or "").lower())
    texte = "".join(c for c in texte if not unicodedata.combining(c)).strip()
    aliases = {"pieces": "piece", "kilogramme": "kg", "kilogrammes": "kg", "kgs": "kg"}
    texte = aliases.get(texte, texte)
    return None if texte in ("", "?", "inconnu", "inconnue", "unite inconnue") else texte


def construire(donnees, article_stock, groupes, etat, unite, conditionnement, aujourd_hui):
    """Relit les faits uniques et appelle uniquement calculer_depuis_faits.

    `groupes` est la table membre -> principal explicitement construite par
    pilotage. La sélection conserve l'ordre des carnets et leurs corrections.
    Les dates futures ne deviennent pas des mouvements physiques courants.
    """
    dossier, code = Path(donnees), str(article_stock)
    maintenant = _date(aujourd_hui)
    if maintenant is None:
        raise ValueError("Date de rapprochement invalide")
    moteur = _moteur()
    pcb = _nombre(conditionnement)
    if pcb is not None and pcb <= 0:
        pcb = None
    publie = (etat.get("articles") or {}).get(code) or {}
    position_publiee = _nombre(publie.get("position"))
    resultat = {
        "statut": "sans_base", "article_stock": code, "unite": unite,
        "conditionnement": pcb, "coherence_physique": "non_etablie",
        "definition": "Position = écart au rayon plein ; ce n'est pas un stock physique total.",
        "base": None, "totaux": {**{f: None for f in FLUX.values()}, "net": None,
                                  "mouvements": 0, "nombres": {f: 0 for f in FLUX.values()}},
        "position_recalculee": None, "position_recalculee_colis": None,
        "position_publiee": _arrondi(position_publiee),
        "position_publiee_colis": _arrondi(position_publiee / pcb) if position_publiee is not None and pcb else None,
        "bornes": {"debut": None, "fin": None, "dernier_mouvement_applique": None},
        "comparaison": {"statut": "indisponible", "ecart_unites": None, "ecart_colis": None,
                        "borne_recalcul": None, "borne_publication": etat.get("calcule_jusquau"),
                        "reconstruit_le": etat.get("reconstruit_le"), "mesuree_le": publie.get("mesuree_le")},
        "jours": [], "dernieres_dates_flux": {f: None for f in FLUX.values()},
        "conversions": [], "avertissements": [], "limites": list(LIMITES),
    }

    def alerte(cle, message, nombre=None):
        valeur = {"code": cle, "message": message}
        if nombre is not None:
            valeur["nombre"] = nombre
        resultat["avertissements"].append(valeur)

    config_groupes = defaultdict(list)
    for membre, principal in groupes.items():
        config_groupes[str(principal)].append(str(membre))
    config = {"groupes": dict(config_groupes)}
    selection, audit, derniere = [], {}, None
    futurs = 0
    # faits.lire demeure l'unique autorité pour dédupliquer les IDs ; un
    # conflit interrompt la lecture et n'est pas masqué par ce détail.
    for fait in faits.lire(dossier / "faits", bilan=audit):
        jour = _jour(fait)
        valide = _date(jour)
        if valide and valide <= maintenant:
            derniere = max(derniere or valide, valide)
        canonique = groupes.get(str(fait.get("article")), str(fait.get("article")))
        concerne = canonique == code or (code == moteur.ORANGE_MACHINE_A_JUS
            and fait.get("type") == "vente" and canonique in moteur.CONVERSION_JUS_VERS_ORANGE_KG)
        if not concerne or fait.get("type") not in set(FLUX) | {"comptage", "correction-comptage"}:
            continue
        if valide and valide > maintenant:
            futurs += 1
            continue
        if not valide or _nombre(fait.get("quantite")) is None or not isinstance(fait.get("quantite"), (int, float)):
            resultat["statut"] = "erreur"
            alerte("fait_invalide", "Un fait de cet article a une date ou une quantité invalide ; le rapprochement n'est pas calculable.")
            return resultat
        selection.append(fait)
        flux = FLUX.get(fait.get("type"))
        if flux:
            resultat["dernieres_dates_flux"][flux] = max(resultat["dernieres_dates_flux"][flux] or valide, valide)
    resultat["bornes"]["fin"] = derniere
    resultat["comparaison"]["borne_recalcul"] = derniere
    resultat["audit_lecture"] = {k: audit.get(k, 0) for k in ("faits_uniques", "doublons_ignores", "sans_id")}
    resultat["audit_lecture"]["perimetre"] = "ensemble_des_carnets"
    if futurs:
        alerte("faits_futurs", "Des faits datés après aujourd'hui sont exclus du rapprochement courant.", futurs)
    if config_groupes.get(code):
        alerte("stock_partage", "Les codes explicitement regroupés partagent la même base et les mêmes mouvements.")
    heures_mail = {}
    chemin_mail = dossier / "receptions-courrier.json"
    try:
        if chemin_mail.exists():
            heures_mail = json.loads(chemin_mail.read_text(encoding="utf-8-sig"))
        if not isinstance(heures_mail, dict) or any(not isinstance(v, str) for v in heures_mail.values()):
            raise ValueError("Heures invalides")
        calcule = moteur.calculer_depuis_faits(selection, config, heures_mail, jusqua=derniere, details=True).get(code, {})
    except (ValueError, TypeError, KeyError, OverflowError, OSError):
        resultat["statut"] = "erreur"
        alerte("calcul_indisponible", "Le calcul détaillé ou ses repères horaires ne sont pas lisibles ; aucun état n'a été modifié.")
        return resultat
    depart = calcule.get("depart")
    if not depart:
        alerte("base_absente", "Aucune base de position n'est disponible pour cet article ; les flux connus ne permettent pas d'inventer une position initiale.")
        return resultat

    base_originale, correction = None, None
    # Rejoue uniquement l'identité de la correction effective ; sa quantité
    # et la sélection de la base proviennent déjà du moteur, sans autre règle.
    for fait in selection:
        if fait.get("type") == "comptage" and fait.get("id") == depart.get("id"):
            base_originale, correction = fait, None
        elif base_originale is not None and fait.get("type") == "correction-comptage" and fait.get("cible_id") == depart.get("id"):
            correction = fait
    base_originale = base_originale or {}
    origine_initiale = base_originale.get("origine_mesure", "?")
    forcee = "forcee" in (_unite(origine_initiale) or "")
    nature = "position_forcee" if forcee else "terrain_declare" if origine_initiale in ("ecran-comptage", "saisie-app", "conversation-responsable") else "non_etablie"
    resultat["base"] = {"id": depart.get("id"), "reference_correction": correction.get("id") if correction else None,
        "date": depart["date"], "heure": depart.get("heure"), "moment": depart.get("moment"),
        "origine": depart.get("origine"), "origine_initiale": origine_initiale,
        "quantite": _arrondi(depart["valeur"]), "quantite_colis": _arrondi(depart["valeur"] / pcb) if pcb else None,
        "motif": depart.get("motif"), "nature": nature, "corrigee": correction is not None}
    resultat["bornes"]["debut"] = depart["date"]
    if nature != "terrain_declare":
        alerte("base_forcee" if forcee else "base_non_terrain", "La base est une position forcée ou d'origine non établie ; elle ne doit pas être présentée comme le dernier inventaire terrain.")
    if not moteur.normaliser_heure_magasin((base_originale.get("source") or {}).get("saisi_le") or base_originale.get("horodatage") or base_originale.get("enregistre_le")):
        alerte("heure_absente", "Heure physique absente : le moteur applique sa convention par défaut, sans preuve de l'ordre comptage/réception.")

    appliques = calcule.get("mouvements_appliques", [])
    unite_cible = _unite(unite)
    unites_inconnues, unites_incompatibles = 0, 0
    base_effective = correction or base_originale
    jours = {}
    total = {f: 0.0 for f in FLUX.values()}
    nombres = Counter()
    for indice, fait in enumerate([base_effective, *appliques]):
        unite_fait = _unite(fait.get("unite"))
        est_conversion = indice > 0 and code == moteur.ORANGE_MACHINE_A_JUS and fait.get("article_source") in moteur.CONVERSION_JUS_VERS_ORANGE_KG
        if not unite_fait or not unite_cible:
            unites_inconnues += 1
        elif not est_conversion and unite_fait != unite_cible:
            unites_incompatibles += 1
    for fait in appliques:
        flux, q, jour = FLUX[fait["type"]], fait["quantite"], _jour(fait)
        ligne = jours.setdefault(jour, {"date": jour, **{f: 0.0 for f in FLUX.values()},
                                      "variation": 0.0, "references": {f: [] for f in FLUX.values()}})
        ligne[flux] += q
        ligne["variation"] += q if flux == "livraisons" else -q
        ligne["references"][flux].append(fait.get("id"))
        total[flux] += q
        nombres[flux] += 1
        source = fait.get("article_source")
        if code == moteur.ORANGE_MACHINE_A_JUS and source in moteur.CONVERSION_JUS_VERS_ORANGE_KG:
            coef = moteur.CONVERSION_JUS_VERS_ORANGE_KG[source]
            resultat["conversions"].append({"reference": fait.get("id"), "date": jour, "article_source": source,
                "quantite_source": _arrondi(q / coef), "unite_source": fait.get("unite"),
                "coefficient": coef, "quantite_appliquee": _arrondi(q), "unite_calcul": "kg"})
    if unites_inconnues:
        alerte("unites_inconnues", "La base ou des mouvements appliqués ont une unité inconnue. Le calcul reproduit le moteur, mais leur compatibilité physique n'est pas démontrée.", unites_inconnues)
    if unites_incompatibles:
        alerte("unites_incompatibles", "Des unités de la base ou des mouvements diffèrent de l'unité affichée. Le calcul numérique du moteur ne valide pas leur addition physique.", unites_incompatibles)
    if resultat["conversions"]:
        alerte("conversion_jus", "Des ventes de jus sont converties en consommation d'oranges selon les coefficients fixes du moteur ; vérifier les unités sources et la réalité de cette consommation.", len(resultat["conversions"]))
    resultant = _nombre(calcule.get("position"))
    if resultant is None or any(_nombre(v) is None for v in total.values()) or any(_nombre(l["variation"]) is None for l in jours.values()):
        resultat["statut"] = "erreur"
        alerte("resultat_invalide", "Le résultat numérique n'est pas fini ; aucun rapprochement valide n'est disponible.")
        return resultat
    position_courante = depart["valeur"]
    for jour in sorted(jours):
        ligne = jours[jour]
        position_courante += ligne["variation"]
        resultat["jours"].append({**ligne, **{f: _arrondi(ligne[f]) for f in FLUX.values()},
                                  "variation": _arrondi(ligne["variation"]), "position_fin": _arrondi(position_courante)})
    resultat["statut"] = "disponible"
    resultat["totaux"] = {**{f: _arrondi(total[f]) for f in FLUX.values()},
        "net": _arrondi(total["livraisons"] - total["ventes"] - total["casse"] - total["dons"]),
        "mouvements": len(appliques), "nombres": {f: nombres[f] for f in FLUX.values()}}
    resultat["bornes"]["dernier_mouvement_applique"] = max(jours, default=None)
    resultat["position_recalculee"] = resultant
    resultat["position_recalculee_colis"] = _arrondi(resultant / pcb) if pcb else None
    if position_publiee is not None:
        ecart = round(resultant - position_publiee, 3)
        comparaison = resultat["comparaison"]
        comparaison.update(ecart_unites=ecart, ecart_colis=_arrondi(ecart / pcb) if pcb else None)
        if not _date(etat.get("calcule_jusquau")):
            comparaison["statut"] = "indisponible"
        elif derniere != etat["calcule_jusquau"]:
            comparaison["statut"] = "bornes_differentes"
        else:
            comparaison["statut"] = "identique" if ecart == 0 else "ecart"
    return resultat
