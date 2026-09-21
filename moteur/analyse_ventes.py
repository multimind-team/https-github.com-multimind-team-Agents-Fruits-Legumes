"""Matrice commerciale datée pour exploration locale, sans écriture ni réseau."""
from datetime import date, timedelta
from pathlib import Path
import re

import pilotage

FLUX = ("ventes", "livraisons", "pertes")
INCONNUES = {"", "?", "inconnu", "inconnue", "unite inconnue"}


def _date_stricte(valeur, nom):
    if not isinstance(valeur, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", valeur):
        raise ValueError(f"{nom} doit être une date AAAA-MM-JJ.")
    try:
        return date.fromisoformat(valeur)
    except ValueError as exc:
        raise ValueError(f"{nom} est une date invalide.") from exc


def _annee_precedente(jour):
    try:
        return jour.replace(year=jour.year - 1)
    except ValueError:
        if jour.month == 2 and jour.day == 29:
            return jour.replace(year=jour.year - 1, day=28)
        raise


def _dans(jour, periode):
    return bool(periode["debut"] and periode["debut"] <= jour <= periode["fin"])


def construire(donnees, debut=None, fin=None, comparaison="precedente", aujourd_hui=None):
    """Une ligne par code commercial canonique et date, sans zéro inventé.

    Les sommes physiques du cockpit sont préservées. Cette vue réutilise le
    second agrégat commercial du même lecteur de faits, avant conversion jus.
    """
    if comparaison not in ("precedente", "annee_precedente", "aucune"):
        raise ValueError("Comparaison attendue : precedente, annee_precedente ou aucune.")
    if (debut is None) != (fin is None):
        raise ValueError("Renseigner ensemble les dates de début et de fin.")
    maintenant = _date_stricte(aujourd_hui, "Aujourd'hui") if aujourd_hui is not None else date.today()
    if debut is not None:
        date_debut, date_fin = _date_stricte(debut, "Début"), _date_stricte(fin, "Fin")
        if date_fin < date_debut:
            raise ValueError("La date de fin doit suivre ou égaler la date de début.")
        if (date_fin - date_debut).days + 1 > 3660:
            raise ValueError("La période est limitée à 3660 jours (environ dix ans).")
    dossier = Path(donnees)
    # Métadonnées et diagnostics existants : aucune position recalculée, car
    # aucun article n'est sélectionné dans cette lecture de pilotage.
    catalogue = pilotage.construire(dossier, horizon="14", aujourd_hui=maintenant.isoformat())
    decisions = pilotage._decisions_effectives(dossier, maintenant.isoformat())
    groupes = pilotage._groupes(decisions)
    groupes.update({l["itm8"]: l["article_stock"] for l in catalogue["articles"]
                    if l["itm8"] != l["article_stock"]})
    _, _, _, jours_flux, audit, anomalies, monetaire, commerciaux = pilotage._flux_en_cache(
        str(dossier.resolve()), maintenant.isoformat(), tuple(sorted(groupes.items())), pilotage._signature_faits(dossier))
    derniere = max(jours_flux["ventes"], default=None)
    premiere = min(jours_flux["ventes"], default=None)
    if debut is None:
        date_fin = date.fromisoformat(derniere) if derniere else maintenant
        date_debut = date_fin - timedelta(days=13)
    nb_jours = (date_fin - date_debut).days + 1
    periode = {"debut": date_debut.isoformat(), "fin": date_fin.isoformat(), "jours": nb_jours}
    precedente = {"mode": comparaison, "debut": None, "fin": None, "jours": 0}
    try:
        if comparaison == "precedente":
            autre_fin = date_debut - timedelta(days=1)
            autre_debut = autre_fin - timedelta(days=nb_jours - 1)
        elif comparaison == "annee_precedente":
            autre_debut, autre_fin = _annee_precedente(date_debut), _annee_precedente(date_fin)
        if comparaison != "aucune":
            precedente.update(debut=autre_debut.isoformat(), fin=autre_fin.isoformat(), jours=(autre_fin-autre_debut).days+1)
    except (ValueError, OverflowError) as exc:
        raise ValueError("La période de comparaison sort du calendrier disponible.") from exc

    metas, aliases = {}, {}
    for ligne in catalogue["articles"]:
        code = ligne["article_stock"]
        aliases[ligne["itm8"]] = code
        if code not in metas or ligne["itm8"] == code:
            metas[code] = ligne
    campagnes = {}
    for code, lignes in pilotage._campagnes(decisions).items():
        canonique = groupes.get(code, code)
        for c in lignes:
            cle = (c["debut"], c["fin"])
            campagnes.setdefault(canonique, {})[cle] = {"debut": c["debut"], "fin": c["fin"],
                "annulee": bool(c.get("annuler")), "source": "declaration_contexte", "reference": c.get("id")}
    articles = []
    for code in sorted(set(metas) | set(commerciaux) | set(monetaire)):
        meta = metas.get(code, {})
        articles.append({"itm8": code, "article_stock": code, "libelle": meta.get("libelle") or code,
            "famille": meta.get("famille") or "Autres F&L", "famille_source": "classement courant du pilotage, non historisé",
            "unite": meta.get("unite") or "unité inconnue", "colisage": meta.get("colisage"),
            "masque": bool(meta.get("masque")), "codes_regroupes": sorted(c for c, p in aliases.items() if p == code),
            "campagnes": sorted(campagnes.get(code, {}).values(), key=lambda c: (c["debut"], c["fin"]))})
    metadata = {a["itm8"]: a for a in articles}
    lignes = []
    couverture = {"premiere_vente": premiere, "derniere_vente": derniere,
        "derniere_livraison": max(jours_flux["livraisons"], default=None),
        "faits_unite_inconnue": 0, "faits_unite_incompatible": 0, "ca_faits_ventes": 0, "ca_faits_documentes": 0,
        "jours_ventes_observes": 0, "jours_attendus": nb_jours,
        "mouvements_invalides": anomalies, "doublons_ignores": audit.get("doublons_ignores", 0),
        "fichiers_absents": catalogue["couverture"]["fichiers_absents"]}
    for code in sorted(set(commerciaux) | set(monetaire)):
        meta = metadata[code]
        pcb = pilotage._nombre(meta["colisage"])
        pcb = pcb if pcb is not None and pcb > 0 else None
        unite = pilotage._unite_comparable(meta["unite"])
        for jour in sorted(set(commerciaux.get(code, {})) | set(monetaire.get(code, {}))):
            if not (_dans(jour, periode) or _dans(jour, precedente)):
                continue
            source = commerciaux.get(code, {}).get(jour, {})
            ligne = {"date": jour, "itm8": code, "faits_unite_inconnue": 0, "faits_unite_incompatible": 0}
            for flux in FLUX:
                valeur = pilotage._nombre(source.get(flux))
                unites = source.get("_unites", {}).get(flux, {})
                inconnues = sum(n for u, n in unites.items() if u in INCONNUES or unite in INCONNUES)
                incompatibles = sum(n for u, n in unites.items() if u not in INCONNUES and unite not in INCONNUES and u != unite)
                ligne[flux] = pilotage._arrondi(valeur)
                ligne[flux + "_colis"] = pilotage._arrondi(valeur / pcb) if valeur is not None and pcb and not inconnues and not incompatibles else None
                ligne["faits_unite_inconnue"] += inconnues
                ligne["faits_unite_incompatible"] += incompatibles
            ligne["unites_fiables"] = ligne["faits_unite_inconnue"] == ligne["faits_unite_incompatible"] == 0
            valeur = monetaire.get(code, {}).get(jour, {})
            ligne.update(ca_reconstitue_eur=round(valeur["ca"], 2) if "ca" in valeur else None,
                         ca_faits_ventes=valeur.get("faits_ventes", 0), ca_faits_documentes=valeur.get("faits_documentes", 0))
            ligne["promo_documentee"] = any(c["debut"] <= jour <= c["fin"] for c in meta["campagnes"])
            lignes.append(ligne)
            if _dans(jour, periode):
                for champ in ("faits_unite_inconnue", "faits_unite_incompatible", "ca_faits_ventes", "ca_faits_documentes"):
                    couverture[champ] += ligne[champ]
    lignes.sort(key=lambda l: (l["date"], l["itm8"]))
    couverture["jours_ventes_observes"] = sum(_dans(j, periode) for j in jours_flux["ventes"])
    couverture["ca_couverture_pct"] = round(100 * couverture["ca_faits_documentes"] / couverture["ca_faits_ventes"], 3) if couverture["ca_faits_ventes"] else None
    couverture["lignes_retournees"] = len(lignes)
    limites = [
        "Ventes commerciales des codes caisse, avant conversion jus vers oranges : le CA et le volume de jus restent sur le code vendu. Le détail de position conserve séparément sa consommation physique d'oranges.",
        "Une ligne absente ou une valeur null signifie données absentes ; seul un fait explicite peut documenter zéro. La présence d'un fichier rayon ne prouve pas la complétude par article.",
        "Les quantités sont les sommes numériques des faits. Les colis équivalents au PCB actuel sont indisponibles pour un flux avec unité source inconnue ou incompatible ; aucune unité historique n'est inventée.",
        "Le CA utilise seulement quantité et prix unitaire du même fait historique, sans prix actuel ; il reste reconstitué et partiellement couvert, pas un total commercial certifié.",
        pilotage.MARGE_INDISPONIBLE,
        "Une promo documentée est une déclaration datée, y compris une consigne ensuite annulée, pas une preuve que l'offre a eu lieu. Sans déclaration, le statut promotion reste inconnu.",
        "Les regroupements de codes, familles, masquages et PCB sont ceux du référentiel courant ; ils ne constituent pas un historique de ces classements.",
        "Les périodes sélectionnée et comparée utilisent les mêmes codes et PCB courants. Les bornes d'année précédente sont décalées d'un an civil, avec le 29 février ramené au 28 février ; les durées peuvent différer.",
        "Les compteurs de couverture concernent la période sélectionnée avant filtrage dans l'interface ; aucune comparaison ne démontre une causalité.",
    ]
    if date_fin > maintenant:
        limites.append("La période comporte des jours futurs : aucun mouvement futur n'est inclus comme vente réalisée.")
    return {"ok": True, "periode": periode, "comparaison": precedente, "couverture": couverture,
            "articles": articles, "jours": lignes, "nature_flux": "ventes_commerciales", "limites": limites}
