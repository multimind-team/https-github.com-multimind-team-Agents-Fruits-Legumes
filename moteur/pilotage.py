"""Module de pilotage : lecture des faits et des sorties existantes, sans recalcul publié.

Les volumes du rayon sont des équivalents de colis au PCB ACTUEL, non des
colis historiques réceptionnés. Une absence de fait reste inconnue. Les
prévisions rétrospectives de fiabilite.json ne sont pas des prévisions archivées.
"""
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from functools import lru_cache
import importlib.util
import json
import math
from pathlib import Path
import unicodedata

import faits
import previsions_archivees
import rapprochement_position

JOURS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
FLUX = {"vente": "ventes", "livraison": "livraisons", "casse": "pertes", "don": "pertes"}
ABSENCE_PREVISIONS = ("Aucune prévision journalière archivée avant les ventes n'est disponible. "
                     "Le calcul rétrospectif de fiabilite.json n'est pas une prévision enregistrée à l'époque.")
MARGE_INDISPONIBLE = ("Marge indisponible : les bases HT/TTC et la TVA des prix historiques de vente "
                     "et d'achat ne sont pas attestées dans les faits.")


def _nombre(valeur):
    if isinstance(valeur, bool):
        return None
    try:
        n = float(valeur)
        return n if math.isfinite(n) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _arrondi(n):
    return round(n, 3) if n is not None else None


def _date(valeur):
    try:
        return date.fromisoformat(str(valeur)[:10])
    except (TypeError, ValueError):
        return None


def _json(dossier, nom, manquants):
    chemin = dossier / nom
    if not chemin.exists():
        manquants.append(nom)
        return {}
    try:
        contenu = json.loads(chemin.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"Lecture impossible de {nom} ; aucune donnée n'a été modifiée.") from exc
    if not isinstance(contenu, dict):
        raise ValueError(f"Format non reconnu pour {nom}.")
    return contenu


def _jsonl(chemin):
    if not chemin.exists():
        return []
    try:
        with chemin.open(encoding="utf-8-sig") as flux:
            lignes = [json.loads(ligne) for ligne in flux if ligne.strip()]
        if any(not isinstance(ligne, dict) for ligne in lignes):
            raise ValueError("Objet JSON attendu")
        return lignes
    except (OSError, ValueError) as exc:
        raise ValueError(f"Carnet illisible : {chemin.name}.") from exc


def _decisions_effectives(dossier, jour):
    """Relit les décisions effectives, avec les annulations du moteur.

    Le chemin est explicite : aucune modification des globals de regles.py
    (le serveur est multithread) et aucune écriture ou acquisition de bail.
    """
    decisions = _jsonl(dossier / "decisions.jsonl")
    effectives = [d for d in decisions if not d.get("valide_a_partir_de")
                 or str(d["valide_a_partir_de"]) <= jour]
    annulees = {d.get("annule") for d in effectives if d.get("type") == "annulation"}
    actions = {d["annule_action"] for d in _jsonl(dossier / "journaux/tout.jsonl")
               if d.get("annule_action") and d.get("resultat") == "ok"
               and str(d.get("horodatage", ""))[:10] <= jour}
    return [d for d in effectives if d.get("type") != "annulation"
            and d.get("id") not in annulees and d.get("action") not in actions]


def _groupes(decisions):
    groupes = {}
    for d in decisions:
        if d.get("type") != "fusion":
            continue
        principal = d.get("principal") or d.get("article")
        if principal and d.get("membres"):
            groupes[principal] = d["membres"]
        elif principal:
            groupes.pop(principal, None)
    return {membre: principal for principal, membres in groupes.items() for membre in membres}


def _index(valeur, cle="itm8"):
    if isinstance(valeur, dict):
        return {str(k): v for k, v in valeur.items() if isinstance(v, dict)}
    return {str(v[cle]): v for v in valeur or [] if isinstance(v, dict) and v.get(cle)}


def _jours(debut, fin):
    return [(debut + timedelta(days=i)).isoformat() for i in range(max(0, (fin-debut).days + 1))]


def _somme(observations):
    valeurs = [v for v in observations if v is not None]
    return sum(valeurs) if valeurs else None


def _serie(donnees, jours, previsions=None):
    previsions = previsions or {}
    return [{"date": jour, "jour": JOURS[date.fromisoformat(jour).weekday()],
             **{flux: _arrondi(donnees.get(jour, {}).get(flux)) for flux in ("ventes", "livraisons", "pertes")},
             "previsions": _arrondi(previsions.get(jour)),
             "sans_vente_observee": donnees.get(jour, {}).get("ventes") == 0,
             "ventes_absentes": "ventes" not in donnees.get(jour, {})}
            for jour in jours]


def _causes(ligne, observations):
    causes = []
    stock = ligne["stock_colis"]
    if stock is None:
        causes.append({"code": "stock_inconnu", "libelle": "Stock à vérifier", "preuve": "Position physique indisponible ; un comptage est nécessaire."})
    elif stock < 0:
        causes.append({"code": "stock_negatif", "libelle": "Stock négatif", "preuve": f"Position calculée : {stock:g} colis. Le signe ne prouve pas une rupture physique."})
    pcb = ligne["colisage"]
    ventes = [v["ventes"] for v in observations.values() if "ventes" in v]
    moyenne = sum(ventes) / len(ventes) if ventes else None
    if pcb and moyenne and moyenne > 0 and pcb / moyenne >= 3:
        causes.append({"code": "colisage_lourd", "libelle": "Colisage à examiner", "preuve": f"Un colis représente {pcb/moyenne:.1f} journées avec vente enregistrée sur la période."})
    if ligne["avertissements_conditionnement"]:
        causes.append({"code": "colisage_incertain", "libelle": "Colisage à vérifier", "preuve": " / ".join(ligne["avertissements_conditionnement"])})
    if len(ventes) >= 5 and moyenne is not None and pcb and 0 <= moyenne < pcb / 7:
        causes.append({"code": "faible_rotation", "libelle": "Faible rotation observée", "preuve": "Moins d'un septième de colis vendu par journée enregistrée ; disponibilité en rayon à vérifier."})
    if ligne["signal"] in ("surstock_suspecte", "rupture_suspectee"):
        causes.append({"code": "ecart_flux", "libelle": "Écart de flux à expliquer", "preuve": "Les livraisons et les ventes diffèrent sur la période ; stock de départ, dates et complétude peuvent l'expliquer."})
    if not ventes:
        causes.append({"code": "ventes_absentes", "libelle": "Ventes non documentées", "preuve": "Aucun fait de vente pour cet article dans la période ; cela ne prouve pas zéro vente."})
    return causes


def _diagnostic(ligne, periode):
    phrases = [f"Du {periode['debut']} au {periode['fin']}, "]
    ventes = ligne["ventes_unites"]
    livraison = ligne["livraisons_unites"]
    if ventes is None:
        phrases[-1] += "aucune vente de cet article n'est documentée."
    else:
        phrases[-1] += f"{ventes:g} {ligne['unite']} de ventes sont enregistrées sur {ligne['jours_ventes_observes']} jour(s)."
    if livraison is not None:
        phrases.append(f"Les réceptions enregistrées représentent {livraison:g} {ligne['unite']}.")
    else:
        phrases.append("Aucune réception n'est documentée dans cet intervalle.")
    if ligne["signal"] in ("surstock_suspecte", "rupture_suspectee"):
        phrases.append("L'écart de flux est un signal à examiner avec le stock de départ et les fichiers reçus, pas une preuve de casse ou de rupture.")
    if ligne["stock_colis"] is None or ligne["stock_colis"] < 0:
        phrases.append("Un comptage et le contrôle des mouvements récents permettront de fiabiliser la position.")
    if ligne["jours_ventes_observes"] < periode["jours"]:
        phrases.append("Les journées sans fait article restent inconnues, même lorsqu'un fichier de ventes existe pour le rayon.")
    phrases.append("Ce diagnostic automatique explicite les données disponibles ; aucune baisse de commande n'est appliquée.")
    return " ".join(phrases)


def _unite_comparable(valeur):
    texte = unicodedata.normalize("NFKD", str(valeur or "").lower())
    texte = "".join(c for c in texte if not unicodedata.combining(c)).strip()
    return "piece" if texte in ("piece", "pieces") else texte


def _campagnes(decisions):
    """Une campagne explicitement datée par article, dernière version conservée.

    Aucun rapprochement de libellé prospectus. Une annulation de consigne
    conserve l'historique de la campagne et son état déclaré.
    """
    campagnes = {}
    observations_promo = ("commentaire_promo", "objectif_promo", "bilan_promo",
                         "precommande_colis", "rupture_promo", "prix_promo", "unite_prix_promo")
    for decision in decisions:
        contexte = decision.get("valeur")
        if decision.get("type") != "contexte-terrain" or not isinstance(contexte, dict):
            continue
        debut, fin = _date(contexte.get("promo_debut")), _date(contexte.get("promo_fin"))
        if not debut or not fin or fin < debut or not decision.get("article"):
            continue
        cle = (str(decision["article"]), debut.isoformat(), fin.isoformat())
        terrain_debut, terrain_fin = _date(contexte.get("debut")), _date(contexte.get("fin"))
        instant = _date(decision.get("enregistre_le"))
        # L'emplacement de septembre ne décrit pas une promotion de mai dont
        # les dates restent dans le formulaire. Seul un contexte contemporain
        # recouvrant l'offre renseigne son implantation historique.
        contemporain = bool(terrain_debut and terrain_fin and terrain_debut <= fin and terrain_fin >= debut
                            and instant and instant <= fin)
        precedent = campagnes.get(cle)
        if precedent is None:
            campagnes[cle] = {**contexte, "id": decision.get("id"), "debut": debut.isoformat(),
                "fin": fin.isoformat(), "enregistre_le": decision.get("enregistre_le"),
                "emplacement": contexte.get("emplacement") if contemporain else None,
                "annuler": bool(contexte.get("annuler") and contemporain)}
            continue
        modifies = [champ for champ in observations_promo if champ in contexte and contexte[champ] != precedent.get(champ)]
        requete = decision.get("requete") or {}
        if "observations_fournies" in requete:
            modifies = [champ for champ in modifies if champ in requete["observations_fournies"]]
        if modifies:
            precedent.update({champ: contexte[champ] for champ in modifies})
            precedent.update(id=decision.get("id"), enregistre_le=decision.get("enregistre_le"))
        if contemporain:
            precedent["emplacement"] = contexte.get("emplacement")
            precedent["annuler"] = bool(contexte.get("annuler"))
    resultat = defaultdict(list)
    for (code, debut, fin), campagne in campagnes.items():
        resultat[code].append(campagne)
    return resultat


def _bilan_intervalle(observations, debut, fin):
    jours = _jours(debut, fin)
    lignes = [observations[j] for j in jours if j in observations]
    valeurs = [ligne["ventes"] for ligne in lignes if "ventes" in ligne]
    return {"jours": len(valeurs), "jours_attendus": len(jours),
            "moyenne": _arrondi(sum(valeurs)/len(valeurs)) if valeurs else None,
            **{f: _arrondi(_somme(l.get(f) for l in lignes)) for f in ("ventes", "livraisons", "pertes")}}


def _analyses_promotions(campagnes, observations, fin_donnees, unite):
    analyses = []
    for c in sorted(campagnes, key=lambda c: c["debut"], reverse=True):
        debut, fin = _date(c["debut"]), _date(c["fin"])
        avant = _bilan_intervalle(observations, debut-timedelta(days=28), debut-timedelta(days=1))
        pendant = _bilan_intervalle(observations, debut, min(fin, fin_donnees))
        reference_par_jour = defaultdict(list)
        for jour in _jours(debut-timedelta(days=28), debut-timedelta(days=1)):
            if "ventes" in observations.get(jour, {}):
                reference_par_jour[date.fromisoformat(jour).weekday()].append(observations[jour]["ventes"])
        jours_promo_observes = [date.fromisoformat(j).weekday() for j in _jours(debut, min(fin, fin_donnees))
                               if "ventes" in observations.get(j, {})]
        baseline_comparee = (sum(sum(reference_par_jour[j])/len(reference_par_jour[j]) for j in jours_promo_observes)
            / len(jours_promo_observes) if jours_promo_observes and all(reference_par_jour[j] for j in jours_promo_observes) else None)
        evolution = (100*(pendant["moyenne"]/avant["moyenne"]-1)
                     if avant["moyenne"] is not None and avant["moyenne"] > 0 and pendant["moyenne"] is not None else None)
        evolution_jours = (100*(pendant["moyenne"]/baseline_comparee-1)
                          if baseline_comparee is not None and baseline_comparee > 0 and pendant["moyenne"] is not None else None)
        bilan = (f"Promotion déclarée du {c['debut']} au {c['fin']}. "
                 f"Avant : {avant['jours']}/28 jours avec vente enregistrée. "
                 f"Pendant : {pendant['jours']}/{pendant['jours_attendus']} jours écoulés avec vente enregistrée. ")
        if evolution is not None:
            bilan += (f"Le rythme observé passe de {avant['moyenne']:g} à {pendant['moyenne']:g} {unite} "
                      f"par jour documenté ({evolution:+.1f} %). Cette variation apparente ne prouve pas l'effet de la promotion. ")
        else:
            bilan += "Les données disponibles ne permettent pas de calculer une évolution du rythme de vente. "
        if evolution_jours is not None:
            bilan += f"À répartition comparable des jours de semaine, la variation observée est de {evolution_jours:+.1f} %. "
        if c.get("rupture_promo") == "oui":
            bilan += "Une rupture a été déclarée : les ventes observées peuvent sous-estimer la demande. "
        elif c.get("rupture_promo", "inconnue") == "inconnue":
            bilan += "La disponibilité du produit pendant l'offre reste à documenter. "
        if c.get("annuler"):
            bilan += "La consigne liée a été annulée ; vérifier que cette promotion a effectivement eu lieu. "
        limites = ["Moyennes sur les seuls jours documentés ; un jour absent ne vaut pas zéro vente.",
                   "La période de référence correspond aux 28 jours précédant l'offre.",
                   "Prix, emplacement, météo, saison, disponibilité et calendrier peuvent expliquer la variation ; aucune causalité n'est établie.",
                   "La précommande renseignée est une information humaine ; elle ne prouve ni la réception ni la vente."]
        analyses.append({"id": c.get("id"), "debut": c["debut"], "fin": c["fin"],
            "jours_avant": avant["jours"], "jours_promo": pendant["jours"],
            "jours_avant_attendus": avant["jours_attendus"], "jours_promo_attendus": pendant["jours_attendus"],
            "ventes_avant_moyenne": avant["moyenne"], "ventes_promo_moyenne": pendant["moyenne"],
            "ventes_avant_moyenne_comparee": _arrondi(baseline_comparee), "evolution_ajustee_jours_pct": _arrondi(evolution_jours),
            "ventes_promo": pendant["ventes"], "livraisons_promo": pendant["livraisons"],
            "pertes_promo": pendant["pertes"], "evolution_pct": _arrondi(evolution),
            "bilan_auto": bilan.strip(), "limites": limites, "unite": unite,
            "precommande_colis": _nombre(c.get("precommande_colis")),
            "prix_promo": _nombre(c.get("prix_promo")), "unite_prix_promo": c.get("unite_prix_promo"),
            "rupture_promo": c.get("rupture_promo") or "inconnue",
            "commentaire_promo": c.get("commentaire_promo") or "", "bilan_promo": c.get("bilan_promo") or "",
            "objectif_promo": c.get("objectif_promo") or "", "annulee": bool(c.get("annuler")),
            "emplacement": c.get("emplacement"), "enregistre_le": c.get("enregistre_le"),
            "precommande_future": {"statut": "historique_insuffisant", "colis": None,
                "motif": "Au moins deux promotions comparables documentées, leur disponibilité, un prix et la durée de la future offre sont nécessaires avant de chiffrer une précommande."}})
    for cible in analyses:
        # Même prix/unité, emplacement et durée, données complètes, absence de
        # rupture déclarée : base de discussion, jamais une commande déduite.
        comparables = [a for a in analyses if a is not cible and a["fin"] < cible["debut"]
            and not a["annulee"] and a["rupture_promo"] == "non"
            and a["jours_promo"] > 0 and a["jours_promo"] == a["jours_promo_attendus"]
            and a["fin"] <= fin_donnees.isoformat()
            and a["prix_promo"] is not None and a["prix_promo"] == cible["prix_promo"]
            and a["unite_prix_promo"] is not None and a["unite_prix_promo"] == cible["unite_prix_promo"]
            and a["emplacement"] is not None and a["emplacement"] == cible["emplacement"]
            and (_date(a["fin"])-_date(a["debut"])) == (_date(cible["fin"])-_date(cible["debut"]))]
        if len(comparables) >= 2 and cible["prix_promo"] is not None and cible["debut"] > fin_donnees.isoformat():
            cible["precommande_future"] = {"statut": "a_etudier", "colis": None,
                "campagnes_comparables": len(comparables),
                "motif": "Plusieurs offres documentées sont comparables. Le stock vendable au démarrage, les réceptions déjà prévues et la capacité de présentation restent à valider pour chiffrer la précommande."}
    return analyses


def _commentaires(ligne):
    stock = ("Position indisponible : un comptage est nécessaire." if ligne["stock_colis"] is None else
             f"Position calculée de {ligne['stock_colis']:g} colis à partir du relevé du {ligne['stock_mesure_le'] or 'jour inconnu'}. "
             + ("Position perdue : afficher -- et recompter. " if ligne["position_perdue"] else "")
             + (ligne["stock_motif"] or "Motif du relevé non renseigné."))
    pcb = (f"Colis actuel : {ligne['colisage']:g} {ligne['unite']}. " if ligne["colisage"] else "Colisage actuel inconnu. ")
    if ligne["conditionnement_personnalise"]:
        pcb += "Réglage personnalisé : " + str(ligne["decision_conditionnement"].get("motif") or "motif non renseigné") + ". "
    pcb += " ".join(ligne["avertissements_conditionnement"])
    commentaires = [{"titre": "Position et comptage", "texte": stock, "source": "etat.json / proposition.json"},
        {"titre": "Ventes et réceptions", "texte": ligne["diagnostic"], "source": "faits/*.jsonl"},
        {"titre": "Conditionnement", "texte": pcb.strip(), "source": "proposition.json / decisions.jsonl"},
        {"titre": "Comparaison des prévisions", "texte": (
            f"{ligne['paires_previsions']} paire(s) article/jour avec prévision antérieure et vente observée ; "
            f"{ligne['conformite_previsions_pct']:g} % dans la bande ±25 %." if ligne["paires_previsions"] else ABSENCE_PREVISIONS),
         "source": "previsions/*.jsonl / faits/*.jsonl"}]
    if ligne["article_stock"] != ligne["itm8"] or ligne["commande_groupe_ambigue"] or ligne["avertissement_contexte"]:
        commentaires.append({"titre": "Codes et commande partagés", "texte": str(ligne["avertissement_contexte"] or
            f"Ce code lit le stock {ligne['article_stock']}. La commande est portée par {ligne['commande_groupe_portee_par'] or 'une offre restant à choisir'} ; contrôler la fiche porteuse avant d'appliquer un contexte."),
            "source": "proposition.json"})
    return commentaires


def _photos_contextuelles(dossier):
    """Métadonnées publiées uniquement ; ne lit jamais les fichiers image."""
    dernieres = {}
    for photo in _jsonl(dossier / "photos-contexte.jsonl"):
        if photo.get("type") != "photo-contexte":
            continue
        identifiant = photo.get("id")
        if not isinstance(identifiant, str) or not identifiant:
            raise ValueError("Une photo de contexte n'a pas d'identifiant exploitable.")
        try:
            if not isinstance(photo.get("date_photo"), str) or len(photo["date_photo"]) < 16 or photo["date_photo"][10] != "T":
                raise ValueError("Date et heure locales attendues")
            horodatage = datetime.fromisoformat(photo["date_photo"])
            # Le contrat est une date locale saisie à la minute. Un décalage
            # explicite éventuellement fourni est conservé, jamais inventé.
            date_photo = horodatage.isoformat(timespec="minutes")
        except (ValueError, TypeError, KeyError) as exc:
            raise ValueError("La date déclarée d'une photo de contexte est invalide.") from exc
        dernieres[identifiant] = {**photo, "date_photo": date_photo}
    par_code = defaultdict(list)
    for photo in dernieres.values():
        if photo.get("itm8"):
            par_code[str(photo["itm8"])].append(photo)
    return par_code


def _evenements_contextuels(code, decisions, campagnes, photos):
    evenements, periodes = [], {}
    for decision in decisions:
        contexte = decision.get("valeur")
        if (decision.get("type") != "contexte-terrain" or str(decision.get("article")) != code
                or not isinstance(contexte, dict)):
            continue
        debut, fin = _date(contexte.get("debut")), _date(contexte.get("fin"))
        if debut and fin:
            periodes[(debut.isoformat(), fin.isoformat())] = decision
    for (debut, fin), decision in periodes.items():
        contexte = decision["valeur"]
        commentaire = str(contexte.get("note") or decision.get("motif") or "")
        if contexte.get("annuler"):
            commentaire = "Consigne annulée ; dates initialement déclarées. " + commentaire
        for jour, type_, titre in ((debut, "debut-contexte", "Début de consigne déclaré"),
                                   (fin, "fin-contexte", "Dernier jour de consigne déclaré")):
            evenements.append({"date": jour, "type": type_, "titre": titre, "commentaire": commentaire,
                "source": "decisions.jsonl", "reference": decision.get("id"),
                "photo_id": None, "date_photo": None, "nature": "declaration"})
    for campagne in campagnes:
        for champ, type_, titre in (("debut", "debut-promotion", "Début de promotion déclaré"),
                                    ("fin", "fin-promotion", "Dernier jour de promotion déclaré")):
            evenements.append({"date": campagne[champ], "type": type_, "titre": titre,
                "commentaire": str(campagne.get("commentaire_promo") or campagne.get("objectif_promo") or ""),
                "source": "decisions.jsonl", "reference": campagne.get("id"),
                "photo_id": None, "date_photo": None, "nature": "declaration"})
    for photo in photos:
        evenements.append({"date": photo["date_photo"][:10], "type": "photo",
            "titre": photo.get("titre") or "Photo de contexte datée", "commentaire": str(photo.get("commentaire") or photo.get("changement") or ""),
            "source": "photos-contexte.jsonl", "reference": photo["id"], "photo_id": photo["id"],
            "date_photo": photo["date_photo"], "nature": "declaration"})
    return sorted(evenements, key=lambda e: (e["date"], e["date_photo"] or "", e["type"]))


def _valorisation(monetaire, jours):
    lignes = [monetaire[j] for j in jours if j in monetaire]
    nombres = sum(l.get("faits_ventes", 0) for l in lignes)
    documentes = sum(l.get("faits_documentes", 0) for l in lignes)
    montant = _somme(l.get("ca") for l in lignes)
    return {"ca_reconstitue_eur": round(montant, 2) if montant is not None else None,
            "ca_faits_documentes": documentes, "ca_faits_ventes": nombres,
            "ca_couverture_pct": _arrondi(100*documentes/nombres) if nombres else None,
            "marge_eur": None, "marge_motif": MARGE_INDISPONIBLE}


def _signature_faits(dossier):
    return tuple((p.name, p.stat().st_mtime_ns, p.stat().st_size) for p in sorted((dossier / "faits").glob("*.jsonl")))


@lru_cache(maxsize=2)
def _flux_en_cache(dossier_texte, aujourd_hui, groupes_tries, signature):
    """Cache mémoire de sommes, invalidé dès qu'un carnet ou regroupement change.

    Rien n'est écrit sur disque. Le lecteur commun conserve le contrôle des
    doublons et conflits à chaque version du carnet. Aucun JSONL brut n'est
    conservé en mémoire au-delà de sa lecture.
    """
    dossier, maintenant, groupes = Path(dossier_texte), date.fromisoformat(aujourd_hui), dict(groupes_tries)
    audit = {}
    mouvements = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
    commerciaux = defaultdict(lambda: defaultdict(lambda: {"_unites": defaultdict(Counter)}))
    monetaire = defaultdict(lambda: defaultdict(dict))
    noms_faits, unites_faits, jours_flux = {}, {}, defaultdict(set)
    anomalies = 0
    spec = importlib.util.spec_from_file_location("_pilotage_calcul", Path(__file__).with_name("calculer-commande.py"))
    calcul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(calcul)
    conversion = calcul.CONVERSION_JUS_VERS_ORANGE_KG
    for fait in faits.lire(dossier / "faits", bilan=audit):
        flux = FLUX.get(fait.get("type"))
        if flux is None:
            continue
        jour = _date((fait.get("date_effet") or fait.get("date_source")) if flux == "livraisons"
                     else (fait.get("date_source") or fait.get("date_effet")))
        q = _nombre(fait.get("quantite"))
        code_source = fait.get("article")
        if not jour or q is None or not code_source:
            anomalies += 1
            continue
        if jour > maintenant:
            continue
        code = groupes.get(str(code_source), str(code_source))
        iso = jour.isoformat()
        # Analyse commerciale : conserver la vente du produit caisse avant
        # de produire séparément la consommation physique jus -> oranges.
        commercial = commerciaux[code][iso]
        commercial[flux] = commercial.get(flux, 0.0) + q
        commercial["_unites"][flux][_unite_comparable(fait.get("unite"))] += 1
        if code == str(code_source):
            noms_faits[code] = fait.get("libelle") or code
            unites_faits[code] = fait.get("unite")
        if flux == "ventes":
            # Valorisation avant la conversion physique jus -> oranges : le
            # CA demeure sur le code vendu, sans multiplication des euros.
            valeur = monetaire[code][jour.isoformat()]
            valeur["faits_ventes"] = valeur.get("faits_ventes", 0) + 1
            prix = _nombre(fait.get("prix_vente_unitaire"))
            if prix is not None and math.isfinite(q * prix):
                valeur["ca"] = valeur.get("ca", 0.0) + q * prix
                valeur["faits_documentes"] = valeur.get("faits_documentes", 0) + 1
        if flux == "ventes" and code in conversion:
            q *= conversion[code]
            code = calcul.ORANGE_MACHINE_A_JUS
        mouvements[code][iso][flux] += q
        jours_flux[flux].add(iso)
        if code == str(code_source):
            noms_faits[code] = fait.get("libelle") or code
            unites_faits[code] = fait.get("unite")
    # Empêche les accès aux articles absents de modifier le cache partagé.
    mouvements = {c: {j: dict(v) for j, v in jours.items()} for c, jours in mouvements.items()}
    monetaire = {c: dict(jours) for c, jours in monetaire.items()}
    commerciaux = {c: {j: {**v, "_unites": {f: dict(u) for f, u in v["_unites"].items()}}
                       for j, v in jours.items()} for c, jours in commerciaux.items()}
    return mouvements, noms_faits, unites_faits, jours_flux, audit, anomalies, monetaire, commerciaux


def construire(donnees, horizon="14", article=None, aujourd_hui=None):
    """Retourne un document JSON sérialisable, en lecture seule et sans réseau.

    Les horizons récents finissent au dernier jour de ventes constatées (jamais
    au jour d'un comptage). L'annuel porte sur cette année de référence explicite.
    """
    dossier = Path(donnees)
    maintenant = _date(aujourd_hui) if aujourd_hui is not None else date.today()
    if maintenant is None:
        raise ValueError("Date courante invalide")
    horizon = str(horizon)
    if horizon == "annuel":
        horizon = "annee"
    if horizon not in ("3", "7", "14", "30", "annee"):
        raise ValueError("Horizon attendu : 3, 7, 14, 30 ou annee.")
    manquants = []
    agregats = _json(dossier, "agregats.json", manquants)
    proposition = _json(dossier, "proposition.json", manquants)
    etat = _json(dossier, "etat.json", manquants)
    catalogue = _json(dossier, "catalogue.json", manquants)
    fiabilite = _json(dossier, "fiabilite.json", manquants)
    analyse = _json(dossier, "analyse-ventes-livraisons.json", manquants)
    comptages = _index(_json(dossier, "articles.json", manquants).get("articles", []))
    agr = _index(agregats.get("articles", {}))
    prop = _index(proposition.get("lignes", []))
    occurrences_prop = Counter(str(p.get("itm8")) for p in proposition.get("lignes", []) if isinstance(p, dict))
    positions = _index(etat.get("articles", {}))
    cat = _index(catalogue.get("articles", {}))
    fia = _index(fiabilite.get("articles", []))
    decisions = _decisions_effectives(dossier, maintenant.isoformat())
    campagnes = _campagnes(decisions)
    photos = _photos_contextuelles(dossier)
    groupes = _groupes(decisions)
    pcb_decisions = {}
    unite_decisions = {}
    for decision in decisions:
        if decision.get("type") == "conditionnement" and decision.get("article"):
            pcb_decisions[decision["article"]] = decision
        elif decision.get("type") == "unite" and decision.get("article"):
            unite_decisions[decision["article"]] = decision
    # Les lignes d'offre portent explicitement le code du stock partagé.
    groupes.update({code: ligne["article_stock"] for code, ligne in prop.items()
                    if ligne.get("article_stock") and ligne["article_stock"] != code})
    archives = previsions_archivees.lire(dossier)
    mouvements, noms_faits, unites_faits, jours_flux, audit, anomalies, monetaire, _commerciaux = _flux_en_cache(
        str(dossier.resolve()), maintenant.isoformat(), tuple(sorted(groupes.items())), _signature_faits(dossier))
    archives_par_code = defaultdict(dict)
    for (code, iso), snapshot in archives.items():
        archives_par_code[code][iso] = snapshot
    derniere_vente = max(jours_flux["ventes"], default=None)
    fin = date.fromisoformat(derniere_vente) if derniere_vente else maintenant
    debut = date(fin.year, 1, 1) if horizon == "annee" else fin - timedelta(days=int(horizon)-1)
    jours = _jours(debut, fin)
    jours14 = _jours(fin-timedelta(days=13), fin)
    periode = {"horizon": horizon, "debut": debut.isoformat(), "fin": fin.isoformat(),
               "jours": len(jours), "annee": fin.year}
    codes = set(agr) | set(prop) | set(positions) | set(mouvements) | set(monetaire)
    codes |= set(cat)
    lignes, matrice, global_jours = [], {}, defaultdict(lambda: defaultdict(list))
    exclus_colis, totaux_flux = set(), defaultdict(list)
    predictions_par_code, paires, conformes, previsions_unite_incompatible = {}, 0, 0, 0
    ventes_comparees, previsions_comparees = [], []
    for code in sorted(codes):
        canonical = groupes.get(code, code)
        fiche = prop.get(code, {})
        position = positions.get(canonical, {})
        catalogue_article = cat.get(code, {})
        detail_fia = fia.get(canonical, {})
        pcb = _nombre(fiche.get("conditionnement", agr.get(code, {}).get("conditionnement")))
        if pcb is None:
            pcb = _nombre(catalogue_article.get("CONDIT.BASE"))
        if code in pcb_decisions:
            pcb_dec = _nombre(pcb_decisions[code].get("valeur"))
            if pcb_dec is not None and pcb_dec > 0:
                pcb = pcb_dec
        if pcb is not None and pcb <= 0:
            pcb = None
        libelle = fiche.get("libelle") or agr.get(code, {}).get("libelle") or catalogue_article.get("LIBELLE") or noms_faits.get(code) or code
        unite = (unite_decisions.get(code, {}).get("valeur")
                 or unite_decisions.get(canonical, {}).get("valeur")
                 or fiche.get("unite")
                 or detail_fia.get("unite")
                 or catalogue_article.get("UNITE MESURE")
                 or unites_faits.get(code)
                 or "unité inconnue")
        if isinstance(unite, str) and unite[:1].isdigit() and " " in unite:
            unite = unite.split(" ", 1)[1]
        prevus = {iso: snap["quantite"] for iso, snap in archives_par_code[canonical].items()
                  if _unite_comparable(snap.get("unite")) == _unite_comparable(unite)
                  and _unite_comparable(unite) not in ("", "inconnue", "unite inconnue")}
        predictions_par_code[code] = prevus
        stock_unites = _nombre(position.get("position"))
        if stock_unites is None:
            stock_unites = _nombre(fiche.get("position_unites"))
        stock_colis = stock_unites / pcb if pcb and stock_unites is not None else None
        position_perdue = bool(stock_colis is not None and stock_colis <= -10)
        observees = {jour: mouvements[canonical][jour] for jour in jours if jour in mouvements.get(canonical, {})}
        sommes = {f: _somme(d.get(f) for d in observees.values()) for f in ("ventes", "livraisons", "pertes")}
        ventes, livres = sommes["ventes"], sommes["livraisons"]
        ecart = 100 * (livres-ventes) / ventes if ventes is not None and ventes > 0 and livres is not None else None
        signal = "donnees_insuffisantes"
        if ecart is not None:
            signal = "surstock_suspecte" if ecart > 25 else "rupture_suspectee" if ecart < -25 else "flux_proches"
        elif ventes == 0 and livres is not None and livres > 0:
            signal = "surstock_suspecte"
        ligne = {"itm8": code, "article_stock": canonical, "libelle": libelle,
                 "famille": detail_fia.get("famille") or fiche.get("groupe") or "Autres F&L",
                 "unite": unite, "colisage": pcb,
                 "stock_unites": _arrondi(stock_unites), "stock_colis": _arrondi(stock_colis),
                 "position_perdue": position_perdue,
                 "stock_mesure_le": position.get("mesuree_le") or fiche.get("position_mesuree_le"),
                 "stock_motif": position.get("motif") or "",
                 "propose_colis": _nombre(fiche.get("propose_colis")),
                 "comptable": code in comptages or code in prop or (bool(pcb) and (code in cat or code in positions or code in agr)),
                 "conditionnement_editable": (occurrences_prop.get(code, 0) <= 1 and bool(pcb)
                    and isinstance(libelle, str) and bool(libelle.strip())
                    and not any(ord(c) < 32 or ord(c) == 127 for c in libelle)),
                 "commande_groupe_portee_par": fiche.get("commande_groupe_portee_par"),
                 "commande_groupe_ambigue": bool(fiche.get("commande_groupe_ambigue")),
                 "avertissement_contexte": fiche.get("avertissement_contexte"),
                 "date_commande": proposition.get("date_commande"),
                 "source_conditionnement": fiche.get("source_conditionnement"),
                 "avertissements_conditionnement": fiche.get("avertissements_conditionnement") or [],
                 "masque": bool(fiche.get("masque", agr.get(code, {}).get("masque", False))),
                 "jours_ventes_observes": sum("ventes" in v for v in observees.values()),
                 "ecart_pct": _arrondi(ecart), "signal": signal,
                 "taux_ecoulement_pct": _arrondi(100 * ventes / livres) if ventes is not None and livres and livres > 0 else None,
                 **{f+"_unites": _arrondi(v) for f, v in sommes.items()},
                 **{f+"_colis": _arrondi(v/pcb) if pcb and v is not None else None for f, v in sommes.items()}}
        decision_pcb = pcb_decisions.get(code, {})
        ligne["conditionnement_personnalise"] = bool(_nombre(decision_pcb.get("valeur")))
        ligne["decision_conditionnement"] = ({"id": decision_pcb.get("id"),
            "motif": decision_pcb.get("motif"), "valeur": decision_pcb.get("valeur"),
            "enregistre_le": decision_pcb.get("enregistre_le")} if ligne["conditionnement_personnalise"] else None)
        prevu = _somme(prevus.get(j) for j in jours)
        ligne["previsions_unites"] = _arrondi(prevu)
        ligne["previsions_colis"] = _arrondi(prevu/pcb) if prevu is not None and pcb else None
        couples = [(observees[j]["ventes"], prevus[j]) for j in jours
                   if j in prevus and "ventes" in observees.get(j, {}) and observees[j]["ventes"] >= 0]
        ligne["paires_previsions"] = len(couples)
        nb_conformes = sum((abs(prevision-vente) <= vente*.25 if vente > 0 else prevision == 0)
                           for vente, prevision in couples)
        ligne["conformite_previsions_pct"] = _arrondi(100 * nb_conformes / len(couples)) if couples else None
        ligne["causes"] = _causes(ligne, observees)
        ligne["diagnostic"] = _diagnostic(ligne, periode)
        ligne.update(_valorisation(monetaire.get(canonical, {}), jours))
        ligne["commentaires_auto"] = _commentaires(ligne)
        ligne["photos_contexte_nombre"] = len(photos.get(code, []))
        if ligne["photos_contexte_nombre"]:
            dates_photos = sorted(p["date_photo"][:10] for p in photos[code])
            ligne["commentaires_auto"].append({"titre": "Contexte visuel daté", "source": "photos-contexte.jsonl",
                "texte": f"{ligne['photos_contexte_nombre']} photo(s) liée(s) à cet article, datées du {dates_photos[0]} au {dates_photos[-1]} par le responsable. "
                         "Consulter les photos et leurs commentaires. Ces dates sont déclarées ; aucune analyse visuelle automatique ni mesure de stock n'a été effectuée."})
        ligne["commentaires_auto"].append({"titre": "Chiffre d'affaires et marge", "source": "faits/*.jsonl / prix_vente_unitaire daté",
            "texte": ((f"CA reconstitué : {ligne['ca_reconstitue_eur']:.2f} €, sur {ligne['ca_faits_documentes']}/{ligne['ca_faits_ventes']} faits de vente documentés. "
                       "Les prix historiques sont arrondis à quatre décimales ; le total est une reconstitution partielle. ")
                      if ligne["ca_reconstitue_eur"] is not None else "Aucun prix historique exploitable pour valoriser les ventes de cette période. ") + MARGE_INDISPONIBLE})
        ligne["analyses_promotions"] = _analyses_promotions(campagnes.get(code, []), mouvements.get(canonical, {}), fin, unite)
        lignes.append(ligne)
        # Offres secondaires : le détail conserve le code commandable, le
        # total rayon utilise le stock canonique une seule fois.
        if canonical != code:
            continue
        paires += len(couples)
        conformes += nb_conformes
        previsions_unite_incompatible += sum(iso in jours and iso not in prevus for iso in archives_par_code[code])
        for cause in ligne["causes"][:1]:
            item = matrice.setdefault(cause["code"], {"code": cause["code"], "libelle": cause["libelle"], "nombre": 0})
            item["nombre"] += 1
        if not pcb:
            if observees:
                exclus_colis.add(code)
            continue
        for flux, valeur in sommes.items():
            if valeur is not None:
                totaux_flux[flux].append(valeur / pcb)
        if prevu is not None:
            totaux_flux["previsions"].append(prevu / pcb)
        ventes_comparees.extend(v/pcb for v, p in couples)
        previsions_comparees.extend(p/pcb for v, p in couples)
        for jour in jours14:
            for flux, valeur in mouvements.get(code, {}).get(jour, {}).items():
                global_jours[jour][flux].append(valeur / pcb)
            if jour in prevus:
                global_jours[jour]["previsions"].append(prevus[jour] / pcb)
    if article is not None and str(article) not in codes:
        raise ValueError("Article inconnu dans le module de pilotage.")
    canoniques = [l for l in lignes if l["itm8"] == l["article_stock"]]
    total_ventes, total_livraisons = _somme(totaux_flux["ventes"]), _somme(totaux_flux["livraisons"])
    kpis = {"articles": len(lignes), "articles_stock_distincts": len(canoniques),
            "ventes_colis": _arrondi(total_ventes), "livraisons_colis": _arrondi(total_livraisons),
            "pertes_colis": _arrondi(_somme(totaux_flux["pertes"])),
            "previsions_colis": _arrondi(_somme(totaux_flux["previsions"])),
            "conformite_pct": _arrondi(100 * conformes/paires) if paires else None,
            "conformite_previsions_pct": _arrondi(100 * conformes/paires) if paires else None,
            "conformite_commandes_pct": None,
            "paires_previsions": paires, "paires_conformes": conformes,
            "observations_ventes": sum(l["jours_ventes_observes"] for l in canoniques),
            "ventes_comparees_colis": _arrondi(_somme(ventes_comparees)),
            "previsions_comparees_colis": _arrondi(_somme(previsions_comparees)),
            "taux_ecoulement_pct": _arrondi(100*total_ventes/total_livraisons) if total_ventes is not None and total_livraisons and total_livraisons > 0 else None,
            "risque_surstock": sum(l["signal"] == "surstock_suspecte" for l in canoniques),
            "risque_rupture": sum(l["signal"] == "rupture_suspectee" for l in canoniques),
            "unite": "colis équivalents au PCB actuel", "articles_sans_pcb_exclus": len(exclus_colis)}
    ca = _somme(monetaire[c][j].get("ca") for c in monetaire for j in jours if j in monetaire[c])
    ca_n = sum(l["ca_faits_documentes"] for l in canoniques)
    ca_total = sum(l["ca_faits_ventes"] for l in canoniques)
    kpis.update(ca_reconstitue_eur=round(ca, 2) if ca is not None else None,
                ca_faits_documentes=ca_n, ca_faits_ventes=ca_total,
                ca_couverture_pct=_arrondi(100*ca_n/ca_total) if ca_total else None,
                marge_eur=None, marge_motif=MARGE_INDISPONIBLE)
    limites = [ABSENCE_PREVISIONS if not archives else
               "Les prévisions archivées sont les dernières publiées avant chaque journée civile. Aucun historique antérieur n'est reconstitué.",
               "La conformité des commandes est indisponible : les quantités validées dans l'outil fournisseur ne sont pas récupérées.",
               "Les volumes globaux sont des colis équivalents au PCB actuel ; ce ne sont pas les colis historiques reçus.",
               "Une absence de fait reste inconnue. Les sommes portent sur les mouvements enregistrés ; leur complétude n'est pas certifiée.",
               "Le ratio ventes/livraisons n'inclut pas le stock initial et peut dépasser 100 %. Les seuils ±25 % signalent un écart, sans prouver casse ou rupture."]
    limites.extend(["Le CA est reconstitué uniquement avec les prix des faits datés, arrondis à quatre décimales à l'import ; couverture mesurée en nombre de faits et montant distinct du total commercial certifié. Aucun prix courant n'est utilisé.",
                    MARGE_INDISPONIBLE])
    if archives:
        limites.append("La conformité des prévisions mesure les paires article/jour avec vente enregistrée et prévision archivée, dans ±25 % des ventes ; pour zéro vente, seule une prévision nulle est conforme.")
    if previsions_unite_incompatible:
        limites.append(f"{previsions_unite_incompatible} prévision(s) exclue(s) : unité ancienne absente ou différente de l'unité courante.")
    if exclus_colis:
        limites.append(f"{len(exclus_colis)} article(s) avec mouvements exclus des totaux de colis : PCB actuel inconnu.")
    if anomalies:
        limites.append(f"{anomalies} mouvement(s) illisible(s) exclus : date, code ou quantité invalide.")
    if manquants:
        limites.append("Sources absentes : " + ", ".join(manquants) + ".")
    selection = next((l.copy() for l in lignes if l["itm8"] == str(article)), None)
    if selection:
        selection["rapprochement_position"] = rapprochement_position.construire(
            dossier, selection["article_stock"], groupes, etat, selection["unite"],
            selection["colisage"], maintenant.isoformat())
        observations = mouvements.get(selection["article_stock"], {})
        prevus = predictions_par_code[selection["itm8"]]
        selection["chronologie"] = _serie(observations, jours14, prevus)
        selection["evenements_contextuels"] = [e for e in _evenements_contextuels(
            selection["itm8"], decisions, campagnes.get(selection["itm8"], []), photos.get(selection["itm8"], []))
            if e["date"] in jours14]
        for jour in selection["chronologie"]:
            jour["evenements_contextuels"] = [e for e in selection["evenements_contextuels"] if e["date"] == jour["date"]]
            jour.update(_valorisation(monetaire.get(selection["article_stock"], {}), [jour["date"]]))
        selection["chronologie_unite"] = selection["unite"]
        selection["profil_hebdomadaire"] = []
        for indice, nom in enumerate(JOURS):
            valeurs = [observations[j]["ventes"] for j in jours if date.fromisoformat(j).weekday() == indice
                       and "ventes" in observations.get(j, {})]
            pairs_jour = [(observations[j]["ventes"], prevus[j]) for j in jours
                          if date.fromisoformat(j).weekday() == indice and j in prevus
                          and "ventes" in observations.get(j, {})]
            selection["profil_hebdomadaire"].append({"jour": nom,
                "ventes_moyennes": _arrondi(sum(valeurs)/len(valeurs)) if valeurs else None,
                "ventes_comparees_moyennes": _arrondi(sum(v for v, p in pairs_jour)/len(pairs_jour)) if pairs_jour else None,
                "previsions_moyennes": _arrondi(sum(p for v, p in pairs_jour)/len(pairs_jour)) if pairs_jour else None,
                "observations": len(valeurs), "paires_previsions": len(pairs_jour)})
        selection["previsions_motif"] = (ABSENCE_PREVISIONS if not prevus else
            "Prévisions de ventes avant pertes, stock et arrondi ; dernière publication avant chaque journée. Profil prévu calculé uniquement sur les paires observées.")
        selection["analyse_existante"] = next((a for a in analyse.get("anomalies_recurrentes", [])
            if a.get("itm8") == selection["article_stock"]), None)
        if selection["analyse_existante"]:
            selection["analyse_existante"] = {"periode": analyse.get("periode"),
                "statut": selection["analyse_existante"].get("statut"),
                "verifications_manquantes": selection["analyse_existante"].get("verifications_manquantes", []),
                "source": "analyse-ventes-livraisons.json"}
    return {"ok": True, "genere_le": datetime.now().isoformat(timespec="seconds"),
            "periode": periode, "date_commande": proposition.get("date_commande"),
            "couverture": {"derniere_vente": derniere_vente,
                "derniere_livraison": max(jours_flux["livraisons"], default=None),
                "jours_ventes_observes": sum(j in jours_flux["ventes"] for j in jours),
                "jours_attendus": len(jours), "anciennete_jours": (maintenant-fin).days if derniere_vente else None,
                "fichiers_absents": manquants, "mouvements_invalides": anomalies,
                "previsions_archivees": len(archives), "paires_previsions": paires,
                "agregats_calcules_le": agregats.get("calcule_le"), "audit_faits": audit,
                "fiabilite_generee_le": fiabilite.get("genere_le")},
            "kpis": kpis, "chronologie": [{"date": jour,
                **{f: _arrondi(_somme(global_jours[jour][f])) for f in ("ventes", "livraisons", "pertes", "previsions")}} for jour in jours14],
            "chronologie_unite": kpis["unite"], "chronologie_jours": 14,
            "chronologie_source": "Carnets de faits : date source des sorties, date d'effet des réceptions.",
            "articles": lignes, "causes": sorted(matrice.values(), key=lambda c: -c["nombre"]),
            "article": selection, "limites": limites}
