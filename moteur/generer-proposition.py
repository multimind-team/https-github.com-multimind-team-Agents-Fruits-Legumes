"""
Produit donnees/proposition.json : ce que l'écran de commande affiche.

Contient, pour chaque article : la quantité proposée, la position, la marge,
le montant, et de quoi expliquer le chiffre. Plus les totaux de la commande.

Les articles sont rangés Fruits non bio, Légumes non bio, puis Bio. À
l'intérieur de chaque groupe, ils restent dans l'ordre du cadencier
Webtelevente, celui de la tablette sur laquelle le responsable de rayon recopie.

LECTURE SEULE sur les carnets : ce programme n'en modifie aucun.
"""
import importlib.util
import json
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import agregats
import calendrier
import catalogue
import conditionnements
import regles
from ecriture_derivee import ecrire_json
from verrou_donnees import operation_donnees

RACINE = Path(__file__).resolve().parent.parent
CARMAUX = (44.052, 2.158)


def _charger(nom, fichier):
    chemin = Path(__file__).resolve().parent / fichier
    spec = importlib.util.spec_from_file_location(nom, chemin)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


calc = _charger("calc", "calculer-commande.py")
prop = _charger("prop", "proposer-commande.py")
ferie = _charger("ferie", "ouverture-jours-feries.py")

CORRECTION_JS = [0.953, 0.932, 0.931, 0.934, 0.925, 0.923, 1.047]
ORDRE_GROUPES_CADENCIER = {"fruits": 0, "legumes": 1, "bio": 2}


def cle_tri_cadencier(ligne):
    """Garde l'ordre Webtelevente à l'intérieur des trois groupes demandés."""
    return (ORDRE_GROUPES_CADENCIER.get(ligne.get("groupe"), 3),
            ligne.get("ordre", 99999), ligne.get("libelle", ""))

# Mesuré par calibrer-vacances.py, appliqué le 2026-09-04 avec l'accord du responsable de rayon.
# Une famille de vacances peut couvrir la date de commande OU celle de
# livraison sans couvrir l'autre (début/fin de période) : voir facteur_vacances().
FACTEURS_VACANCES = {
    "Noël": 1.162, "Toussaint": 1.045, "Été": 1.027,
    "Hiver": 1.002, "Printemps": 0.984, "Ascension": 0.901,
}


def date_de_calcul(etat, date_reference, maintenant=None):
    """Base de la commande, distincte du dernier mouvement reçu.

    Une livraison ou une mesure matinale de J ne clôture pas J : elle sert
    à commander le jour J. Le moteur de position conserve cette phase. Un
    ancien état sans cette information ne prouve rien au-delà des ventes.
    """
    base = etat.get("date_base_commande")
    if isinstance(base, str) and len(base) == 10:
        datetime.strptime(base, "%Y-%m-%d")
        maintenant = maintenant or datetime.now()
        aujourd_hui = maintenant.date().isoformat()
        # La clôture ne fait avancer que le cycle courant attesté par les
        # données ; elle ne rajeunit jamais un ancien carnet.
        if etat.get("calcule_jusquau") == aujourd_hui and (maintenant.hour, maintenant.minute) >= (9, 30):
            base = max(base, aujourd_hui)
        return base
    return date_reference


def facteur_vacances(date_iso, cal):
    nom = calendrier.ce_jour(date_iso, cal).get("vacances")
    return FACTEURS_VACANCES.get(calendrier.famille(nom), 1.0)


def meteo_prevue():
    """Prévision pour les prochains jours. En cas d'échec, on ne devine pas :
    le facteur vaut 1 et l'écran le dit."""
    url = (f"https://api.open-meteo.com/v1/forecast?latitude={CARMAUX[0]}&longitude={CARMAUX[1]}"
           "&daily=temperature_2m_max,precipitation_sum&forecast_days=5&timezone=Europe%2FParis")
    try:
        with urllib.request.urlopen(url, timeout=15) as reponse:
            d = json.load(reponse)["daily"]
        return {j: {"tmax": t, "pluie": p}
                for j, t, p in zip(d["time"], d["temperature_2m_max"], d["precipitation_sum"])}
    except Exception:
        return {}


def facteur_meteo(prevision, jour):
    """Module la demande globale selon la météo réelle prévue (chaleur ou forte pluie).
    Opère toute l'année, y compris lors des chaleurs tardives de septembre ou des coups de froid."""
    if not prevision:
        return 1.0
    facteur = 1.0
    if (prevision.get("pluie") or 0) >= 10:
        facteur *= 0.901
    if (prevision.get("tmax") or 0) >= 25:
        facteur *= 1.076
    return facteur


def calculer_profils_meteo_articles(prevision, date_cmd, date_liv):
    """Calcule le coefficient météo spécifique de chaque produit d'après ses 2.5 ans d'historique."""
    profils_file = RACINE / "donnees" / "profils-produits-sensibilites.json"
    if not profils_file.exists() or not prevision:
        return {}
    try:
        data = json.loads(profils_file.read_text(encoding="utf-8"))
        articles = data.get("articles", {})
        prev_cmd = prevision.get(date_cmd, {})
        prev_liv = prevision.get(date_liv, {})

        def coeff_jour(ratios, prev_info):
            tmax = prev_info.get("tmax") or 0.0
            pluie = prev_info.get("pluie") or 0.0
            r_t = 1.0
            if tmax >= 30.0:
                r_t = ratios.get("chaud_30", 1.0)
            elif tmax >= 25.0:
                r_t = ratios.get("chaud_25", 1.0)
            elif 0.0 < tmax < 10.0:
                r_t = ratios.get("froid_10", 1.0)
            elif 0.0 < tmax < 16.0:
                r_t = ratios.get("frais_16", 1.0)
            r_p = 1.0
            if pluie >= 5.0:
                r_p = ratios.get("pluie_5mm", 1.0)
            return max(0.4, min(2.5, r_t * r_p))

        res = {}
        for itm8, art_info in articles.items():
            ratios = art_info.get("ratios", {})
            f_cmd = coeff_jour(ratios, prev_cmd)
            f_liv = coeff_jour(ratios, prev_liv)
            res[itm8] = {"f_meteo_cmd": f_cmd, "f_meteo_liv": f_liv}
        return res
    except Exception:
        return {}


def ligne_connue(itm8, calcul, mercalys, config, etat, article, offre, agr=None, eval_promo=None, alerte_marge=None):
    """Un article du cadencier qu'on sait rattacher : quantité calculée.

    Le prix d'achat prioritaire vient du cadencier Webtelevente du jour ; le
    prix de vente, du dernier fichier de vente reçu (agregats.py le calcule depuis les
    colonnes "Valeur prix achat"/"Valeur prix vente"). catalogue.json ne sert
    plus que de dernier recours, si aucune des deux sources n'a de valeur.
    """
    reference = mercalys.get(itm8, {})
    surcharge = config["overrides"].get(itm8, {})
    agr = agr or {}
    try:
        achat = float(reference.get("PRIX ACHAT BRUT") or 0)
        vente = float(reference.get("PRIX VENTE") or 0)
    except (TypeError, ValueError):
        achat = vente = 0.0
    # Le vrai prix de vente : le dernier connu depuis le fichier de vente.
    if agr.get("dernierPrixVente"):
        vente = agr["dernierPrixVente"]
    # Le prix d'achat du jour vient du cadencier : c'est celui qu'on paiera.
    # À défaut (article pas dans le cadencier aujourd'hui), le dernier prix
    # d'achat vu dans le fichier de vente précède le référentiel.
    if offre.get("prix_achat"):
        try:
            achat = float(offre["prix_achat"])
        except (TypeError, ValueError):
            pass
    elif agr.get("dernierPrixAchatVente"):
        achat = agr["dernierPrixAchatVente"]
    marge = (100 * (vente - achat) / vente) if vente else 0.0
    colis = calcul["propose_colis"]

    # Une fin de prospectus est un repère, jamais une autorisation de baisse.
    # Toute réduction passe par les suggestions contrôlées et le bouton Suivre.
    fin_promo_appliquee = False
    motif_fin_promo = None
    if eval_promo and eval_promo.get("en_fin_promo"):
        fin_promo_appliquee = True
        motif_fin_promo = eval_promo.get("motif")

    return {
        "itm8": itm8,
        "libelle": article["nom"],
        "ordre": article["rang"],
        "groupe": article.get("groupe", "inconnu"),
        "fournisseur": (surcharge.get("fournisseur")
                        or (reference.get("FOURNISSEUR") or "").strip().split(" ", 1)[-1]).strip(),
        "propose_colis": colis,
        "conditionnement": calcul["conditionnement"],
        "unite": (surcharge.get("unite")
                  or " ".join((reference.get("UNITE MESURE") or "").split(" ")[1:]) or "unité"),
        "position_colis": (round(calcul["position_unites"] / calcul["conditionnement"], 1)
                           if calcul["position_unites"] is not None else None),
        "position_mesuree_le": etat["articles"].get(itm8, {}).get("mesuree_le"),
        "position_unites": calcul["position_unites"],
        "demande": calcul["demande"],
        "previsions_journalieres": calcul.get("previsions_journalieres", {}),
        "vente_moyenne_jour": calcul["vente_moyenne_jour"],
        "vente_moyenne_saison": calcul.get("vente_moyenne_saison", calcul["vente_moyenne_jour"]),
        "vente_moyenne_14j": calcul.get("vente_moyenne_14j"),
        "ponderation_14j": calcul.get("ponderation_14j", 0.0),
        "taux_perte": calcul["taux_perte"],
        "prix_achat": achat,
        "prix_vente": vente,
        "marge_pct": round(marge, 1),
        "montant_achat": round(colis * calcul["conditionnement"] * achat, 2),
        "promotion": calcul["promotion"],
        "fin_promotion": fin_promo_appliquee,
        "motif_fin_promotion": motif_fin_promo,
        "alerte_marge": alerte_marge,
        "position_bloquee": calcul["position_bloquee"],
        "contexte_terrain": calcul.get("contexte_terrain"),
        "connu": True,
    }


def ligne_inconnue(article, offre, alerte_marge=None, etat=None):
    """Un article commandable qu'on ne sait pas encore rattacher.

    Il APPARAÎT quand même : le responsable de rayon veut voir tout ce qu'il peut commander,
    c'est le but de l'application. On ne propose simplement aucune quantité —
    on ne sait rien de ses ventes, et inventer un chiffre serait pire que rien.
    """
    try:
        achat = float(offre.get("prix_achat") or 0)
    except (TypeError, ValueError):
        achat = 0.0
    try:
        vente = float(offre.get("prix_vente_conseille") or 0)
    except (TypeError, ValueError):
        vente = 0.0
    try:
        par_colis = float(offre.get("par_colis") or 1) or 1
    except (TypeError, ValueError):
        par_colis = 1.0

    code_etat = article.get("article") or ("nom:" + article["nom"])
    pos_info = (etat or {}).get("articles", {}).get(code_etat) or {}
    pos_colis = None
    pos_date = None
    if pos_info.get("position") is not None and par_colis:
        pos_colis = round(pos_info["position"] / par_colis, 1)
        pos_date = pos_info.get("mesuree_le")

    return {
        # Sans code, on utilise "nom:<NOM>" — la même convention qu'attend
        # appliquer-decision.py pour masquer un article sans code connu.
        "itm8": code_etat,
        "libelle": article["nom"],
        "ordre": article["rang"],
        "groupe": article.get("groupe", "inconnu"),
        "fournisseur": "",
        "propose_colis": 0.0,
        "conditionnement": par_colis,
        "unite": "unité",
        "position_colis": pos_colis,
        "position_mesuree_le": pos_date,
        "vente_moyenne_jour": 0.0,
        "vente_moyenne_saison": 0.0,
        "vente_moyenne_14j": None,
        "ponderation_14j": 0.0,
        "taux_perte": 0.0,
        "prix_achat": achat,
        "prix_vente": vente,
        "marge_pct": round((100 * (vente - achat) / vente) if vente else 0.0, 1),
        "montant_achat": 0.0,
        "promotion": False,
        "fin_promotion": False,
        "alerte_marge": alerte_marge,
        "position_bloquee": False,
        "connu": False,
        "offre": offre.get("libelle", ""),
    }


def groupes_du_cadencier(cadencier, config):
    """Source physique et ligne porteuse du besoin, sans changer les identifiants.

    Une fusion est déjà une décision métier : ses ventes et comptages sont
    calculés sous le principal. Les offres gardent chacune leur code/PCB/prix.
    Le besoin automatique porte sur le principal actif s'il est présent,
    sinon sur un unique alias actif. Plusieurs alias sans principal actif
    exigent un choix du responsable : aucune priorité commerciale inventée.
    """
    vers_principal = {m: p for p, membres in config.get("groupes", {}).items() for m in membres}
    candidats = {}
    overrides = config.get("overrides", {})
    for index, article in enumerate((cadencier or {}).get("articles", [])):
        code = article.get("article")
        if not code or overrides.get(code, {}).get("masque"):
            continue
        principal = vers_principal.get(code, code)
        candidats.setdefault(principal, []).append((index, code))
    porteurs = {}
    for principal, offres in candidats.items():
        propre = [o for o in offres if o[1] == principal]
        porteurs[principal] = (propre[0] if len(propre) == 1 else
                               offres[0] if len(offres) == 1 else None)
    return vers_principal, porteurs


def rattacher_donnees_groupes(cadencier, config, mercalys, selections, moyennes,
                             positions, livraisons, profils):
    """Projette en mémoire les calculs du principal vers les codes commandables.

    Aucun carnet ni dictionnaire reçu n'est modifié. Le PCB, l'unité et le
    fournisseur restent ceux du code de l'offre. Seule la promotion déjà
    précommandée du groupe se partage ; son masquage reste strictement local.
    """
    vers_principal, porteurs = groupes_du_cadencier(cadencier, config)
    config = {**config, "overrides": {c: dict(v) for c, v in config.get("overrides", {}).items()}}
    selections, moyennes = dict(selections), dict(moyennes)
    positions, livraisons, profils = dict(positions), dict(livraisons), dict(profils)
    for article in (cadencier or {}).get("articles", []):
        code = article.get("article")
        principal = vers_principal.get(code)
        if not principal or code == principal:
            continue
        propres = config["overrides"].get(code, {})
        partages = {k: v for k, v in config["overrides"].get(principal, {}).items() if k == "promotion"}
        config["overrides"][code] = {**partages, **propres}
        selections[code] = conditionnements.selectionner(
            article, config["overrides"][code], mercalys.get(code) or mercalys.get(principal))
        for destination in (moyennes, positions, livraisons, profils):
            if principal in destination:
                destination[code] = destination[principal]
            else:
                destination.pop(code, None)
    return config, selections, moyennes, positions, livraisons, profils, vers_principal, porteurs



@operation_donnees(lambda: RACINE / "donnees")
def main():
    aggregats = agregats.charger()
    config = regles.charger()
    etat = json.loads((RACINE / "donnees" / "etat.json").read_text(encoding="utf-8"))
    fichier_cadencier = RACINE / "donnees" / "cadencier-du-jour.json"
    cadencier = (json.loads(fichier_cadencier.read_text(encoding="utf-8"))
                 if fichier_cadencier.exists() else None)

    date_reference = aggregats["date_reference"]
    date_calcul = date_de_calcul(etat, date_reference)
    mercalys = {str(a["CODE ITM"]): a for a in list(catalogue.articles().values())
                if a.get("CODE ITM")}
    masques = {k for k, v in config.get("overrides", {}).items() if v.get("masque")}
    # Le PCB et le prix doivent appartenir à la même offre commandable.
    # Mercalys peut annoncer 1 kg ou un box alors qu'on commande une caissette.
    selections = conditionnements.charger(RACINE, config, mercalys)

    # Un jour férié variable confirmé FERMÉ par le responsable de rayon (ouverture-jours-feries.py)
    # se saute exactement comme les 3 fermetures fixes.
    feries_fermees = ferie.dates_fermees()
    date_commande = prop.prochain_jour_valide(date_calcul, feries_fermees)
    date_livraison = prop.prochain_jour_valide(date_commande, feries_fermees)
    prevision = meteo_prevue()

    # Facteurs distincts pour jour de commande et jour de livraison (le-calcul.md)
    # Plus de min() appliqué aveuglément aux deux jours (ANO-01, ANO-02, ANO-03).
    f_ferie_cmd = ferie.facteur(date_commande)
    f_ferie_liv = ferie.facteur(date_livraison)
    cal = calendrier.charger()
    f_vacances_cmd = facteur_vacances(date_commande, cal)
    f_vacances_liv = facteur_vacances(date_livraison, cal)
    f_meteo_cmd = facteur_meteo(prevision.get(date_commande), date_commande)
    f_meteo_liv = facteur_meteo(prevision.get(date_livraison), date_livraison)
    profils_meteo = calculer_profils_meteo_articles(prevision, date_commande, date_livraison)

    # Chargement des alertes de marge et des offres de promotion
    try:
        import amortissement_promotions as ap
        offres_promos = ap.charger_promotions(RACINE / "donnees" / "promotions.json")
    except ImportError:
        ap = None
        offres_promos = []
    fic_marges = RACINE / "donnees" / "alertes-marges.json"
    alertes_marges = {}
    if fic_marges.exists():
        try:
            m_data = json.loads(fic_marges.read_text(encoding="utf-8"))
            for a in m_data.get("alertes", []):
                if a.get("itm8"):
                    alertes_marges[str(a["itm8"])] = a
        except Exception:
            pass

    moyennes = calc.construire_moyennes()
    positions = etat["articles"]  # conserve notamment mesuree_le pour l'exception de comptage récent
    config, selections, moyennes, positions, dernieres_livraisons, profils_meteo, vers_principal, porteurs = rattacher_donnees_groupes(
        cadencier, config, mercalys, selections, moyennes, positions,
        aggregats.get("dernieres_livraisons", {}), profils_meteo)
    etat_affichage = {**etat, "articles": positions}

    from contexte_terrain import charger as charger_contextes
    contextes = charger_contextes(RACINE / "donnees")["articles"]
    resultat = prop.proposer(
        date_calcul, moyennes, positions, config, mercalys,
        dernieres_livraisons, aggregats.get("profil_hebdomadaire"),
        {
            "meteo": f_meteo_liv,
            "meteo_cmd": f_meteo_cmd,
            "meteo_liv": f_meteo_liv,
            "profils_articles": profils_meteo,
            "ferie": min(f_ferie_cmd, f_ferie_liv),
            "ferie_cmd": f_ferie_cmd,
            "ferie_liv": f_ferie_liv,
            "vacances": min(f_vacances_cmd, f_vacances_liv),
            "vacances_cmd": f_vacances_cmd,
            "vacances_liv": f_vacances_liv,
        },
        CORRECTION_JS, feries=feries_fermees, conditionnements=selections, contextes=contextes)

    # LA LISTE VIENT DU CADENCIER DU JOUR, pas de ce que le magasin connaît.
    # Le responsable de rayon, le 2026-09-03 : « le cadencier Webtelevente référence ce que je
    # peux commander » et « je veux toute la liste du cadencier dans l'app pour
    # connaître tous les produits que je peux commander : c'est le but de
    # l'application ».
    #
    # On part donc de lui, dans son ordre, et on va chercher ensuite ce qu'on
    # sait de chaque article. Un article qu'on ne sait pas rattacher reste dans
    # la liste, sans quantité calculée : il est commandable, c'est ce qui compte.
    lignes = []
    total_achat = total_vente = total_colis = 0.0

    if cadencier:
        for index, article in enumerate(cadencier["articles"]):
            itm8 = article.get("article")
            principal = vers_principal.get(itm8, itm8)
            selection = selections.get(itm8) or conditionnements.selectionner(
                article, config["overrides"].get(itm8 or ("nom:" + article["nom"])))
            offre = selection["offre"]
            # Un article "inconnu" ou "ambigu" n'a pas de code : on ne peut
            # pas le masquer par code, alors on le masque par son nom exact
            # du cadencier (décision "nom:<NOM>", voir appliquer-decision.py).
            # Depuis le 2026-09-04 : un article masqué reste dans la liste,
            # marqué "masque": true — l'écran de commande a besoin de le
            # montrer dans son onglet "Produits masqués".
            est_masque = bool((itm8 and itm8 in masques)
                              or (not itm8 and f"nom:{article['nom']}" in masques))
            eval_p = ap.evaluer_amortissement(itm8, date_commande, date_livraison, offres_promos) if (ap and itm8) else None
            alerte_m = alertes_marges.get(str(itm8)) if itm8 else None
            if itm8 and itm8 in resultat["lignes"]:
                calcul = resultat["lignes"][itm8]
                porteur = porteurs.get(principal)
                if principal in porteurs and (porteur is None or index != porteur[0]):
                    calcul = {**calcul, "propose_colis": 0.0, "propose_unites": 0.0,
                              "previsions_journalieres": {}}
                ligne = ligne_connue(itm8, calcul, mercalys,
                                     config, etat_affichage, article, offre,
                                     aggregats.get("articles", {}).get(principal),
                                     eval_promo=eval_p, alerte_marge=alerte_m)
            else:
                ligne = ligne_inconnue(article, offre, alerte_marge=alerte_m, etat=etat_affichage)
                # Les décisions par nom s'appliquent aussi sans historique/mapping.
                # Le prix reste celui de l'offre sélectionnée et son éventuel
                # défaut d'appariement est déclaré juste après.
                ligne["conditionnement"] = selection["conditionnement"]
                code_etat = article.get("article") or ("nom:" + article["nom"])
                pos_info = positions.get(code_etat) or {}
                if pos_info.get("position") is not None and ligne["conditionnement"]:
                    ligne["position_colis"] = round(pos_info["position"] / ligne["conditionnement"], 1)
                    ligne["position_mesuree_le"] = pos_info.get("mesuree_le")
            ligne["source_conditionnement"] = selection["source_conditionnement"]
            ligne["avertissements_conditionnement"] = selection["avertissements"]
            ligne["masque"] = est_masque
            if not ligne.get("connu") and ligne["itm8"] in contextes and not contextes[ligne["itm8"]].get("annuler"):
                ligne["avertissement_contexte"] = (
                    "Consigne enregistrée ; aucun calcul automatique disponible pour cet article sans profil de ventes. "
                    "Renseigne la quantité de commande après vérification du stock.")
            if itm8 and (itm8 in vers_principal or itm8 in config.get("groupes", {})):
                ligne["article_stock"] = principal
                porteur = porteurs.get(principal)
                ligne["commande_groupe_portee_par"] = porteur[1] if porteur else None
                ligne["commande_groupe_ambigue"] = principal in porteurs and porteur is None and not est_masque
                if ligne["commande_groupe_ambigue"]:
                    ligne["motif_commande_groupe"] = (
                        f"Plusieurs articles actifs partagent le stock {principal}, sans ligne principale active. "
                        "Choisissez avec le responsable l’article à commander : aucune quantité automatique "
                        "n’est répartie entre ces offres. Les quantités manuelles restent conservées.")
                if porteur and index != porteur[0] and not est_masque:
                    nom_porteur = cadencier["articles"][porteur[0]]["nom"]
                    ligne["motif_commande_groupe"] = (
                        f"Même stock et mêmes ventes que {nom_porteur} ({porteur[1]}). "
                        "Le besoin automatique est proposé une seule fois sur cette autre ligne. "
                        "Vérifiez le total du groupe si vous changez une quantité manuellement.")
                    if itm8 in contextes and not contextes[itm8].get("annuler"):
                        ligne["avertissement_contexte"] = (
                            f"La consigne terrain est portée par cette offre secondaire. "
                            f"Le besoin est calculé sur {porteur[1]} : reporte la consigne sur cette fiche "
                            "si elle concerne le stock commun.")
                membres_grp = config.get("groupes", {}).get(principal, [])
                if membres_grp and porteur and index == porteur[0]:
                    details_membres = []
                    pb_marge = []
                    pa_p = ligne.get("prix_achat")
                    pv_p = ligne.get("prix_vente")
                    for m in membres_grp:
                        ref_m = mercalys.get(m, {})
                        pv_m = ref_m.get("PRIX VENTE") or ref_m.get("PVC")
                        nom_m = ref_m.get("LIBELLE", m)
                        pv_txt = f"PV caisse {pv_m:.2f} €" if pv_m is not None else "PV caisse non renseigné"
                        details_membres.append(f"{nom_m} ({m}, {pv_txt})")
                        if pv_m is not None and pa_p and pv_m <= pa_p:
                            pb_marge.append(f"Risque de vente à perte ! Le prix en caisse de {nom_m} ({pv_m:.2f} €) est inférieur ou égal au prix d'achat cadencier ({pa_p:.2f} €).")
                        elif pv_m is not None and pv_p and abs(pv_m - pv_p) > 0.05:
                            pb_marge.append(f"Écart de prix : {pv_m:.2f} € en caisse vs {pv_p:.2f} € au catalogue.")
                    alerte_txt = (
                        f"Rapprochement de références : les ventes en caisse passent sous {', '.join(details_membres)}, "
                        f"alors que la commande s'effectue sous {ligne['libelle']} ({principal})."
                    )
                    if pb_marge:
                        alerte_txt += " ⚠️ " + " ".join(pb_marge) + " À contrôler d'urgence en rayon/caisse."
                    ligne["alerte_fusion"] = alerte_txt
            lignes.append(ligne)
        for l in lignes:
            if l["masque"]:
                continue       # ne compte ni dans les totaux ni dans "à commander"
            total_achat += l["montant_achat"]
            total_vente += (l["propose_colis"] or 0) * l["conditionnement"] * l["prix_vente"]
            total_colis += l["propose_colis"] or 0
        lignes.sort(key=cle_tri_cadencier)
    else:
        # Pas encore de cadencier du jour : on retombe sur ce que le magasin
        # connaît, pour ne jamais laisser l'écran vide.
        ordre = aggregats.get("ordre_webtelevente") or {}
        for itm8, calcul in resultat["lignes"].items():
            faux = {"nom": calcul["libelle"], "rang": ordre.get(itm8, 99999)}
            ligne = ligne_connue(itm8, calcul, mercalys, config, etat, faux, {},
                                 aggregats.get("articles", {}).get(itm8))
            ligne["masque"] = itm8 in masques
            lignes.append(ligne)
        lignes.sort(key=cle_tri_cadencier)
        for l in lignes:
            if l["masque"]:
                continue
            total_achat += l["montant_achat"]
            total_vente += (l["propose_colis"] or 0) * l["conditionnement"] * l["prix_vente"]
            total_colis += l["propose_colis"] or 0


    # Contrôle article par article : une livraison récente ne couvre pas les
    # ventes manquantes depuis la mesure. Un recomptage ne remet à niveau que
    # l'article réellement compté, jamais tous ses voisins.
    couvertures = []
    sans_position = sans_mapping = sans_position_connus = a_verifier = 0
    dernier_comptage = max((v.get("mesuree_le") or "" for v in etat["articles"].values()), default="")
    articles_dernier_comptage = sum(
        1 for v in etat["articles"].values() if dernier_comptage and v.get("mesuree_le") == dernier_comptage)
    veille_commande = prop.decaler(date_commande, -1)
    # Après 9h30 la proposition passe à demain, mais les ventes d'aujourd'hui
    # ne sont exportées que demain. Ne pas signaler tout le rayon en retard.
    sorties_attendues = min(veille_commande, prop.decaler(datetime.now().date().isoformat(), -1))
    jours_ventes = (set(aggregats["jours_ventes_integres"])
                   if "jours_ventes_integres" in aggregats else None)
    for ligne in lignes:
        if ligne.get("masque"):
            continue
        mesure = etat["articles"].get(ligne.get("article_stock") or ligne["itm8"], {})
        mesure_le = mesure.get("mesuree_le") or ""
        if not ligne.get("connu") or ligne["itm8"].startswith("nom:"):
            sans_mapping += 1
        if mesure.get("position") is None or not mesure_le:
            sans_position += 1
            if ligne.get("connu") and not ligne["itm8"].startswith("nom:"):
                sans_position_connus += 1
            ligne["sorties_couvertes_jusquau"] = None
            continue
        if mesure_le and mesure.get("moment_mesure") in ("matin", "avant-livraison"):
            mesure_le = prop.decaler(mesure_le, -1)
        if jours_ventes is None:
            couverture = max(date_reference or "", mesure_le)  # ancien format dérivé
        else:
            # Un nouvel export ne bouche pas un trou antérieur. Le comptage
            # remplace les mouvements précédents, pas les journées suivantes.
            couverture = mesure_le
            suivant = prop.decaler(couverture, 1)
            while suivant in jours_ventes:
                couverture = suivant
                suivant = prop.decaler(couverture, 1)
        ligne["sorties_couvertes_jusquau"] = couverture or None
        couvertures.append(couverture)
        a_verifier += couverture < sorties_attendues

    sortie = {
        "date_commande": date_commande,
        "date_livraison": date_livraison,
        "date_reference": date_reference,
        "audit_faits": aggregats.get("audit_faits", {}),
        "date_stock": etat.get("calcule_jusquau"),
        "date_base_commande": date_calcul,
        "date_stock_verifiee": min(couvertures) if couvertures else date_reference,
        "couverture_stock": {
            "articles_avec_position": len(couvertures),
            "articles_sorties_a_verifier": a_verifier,
            "articles_sans_position": sans_position,
            "articles_sans_position_connus": sans_position_connus,
            "articles_sans_mapping": sans_mapping,
            "dernier_comptage_le": dernier_comptage or None,
            "articles_dernier_comptage": articles_dernier_comptage,
            "sorties_attendues_jusquau": sorties_attendues,
            "statistiques_ventes_jusquau": date_reference,
        },
        "genere_le": datetime.now().isoformat(timespec="seconds"),
        "meteo_livraison": prevision.get(date_livraison),
        "meteo_disponible": bool(prevision),
        "facteurs": resultat["facteurs"],
        "totaux": {
            "articles": len(lignes),
            "articles_a_commander": sum(1 for l in lignes if not l["masque"] and l["propose_colis"] > 0),
            "colis": round(total_colis, 1),
            "montant_achat": round(total_achat, 2),
            "montant_vente": round(total_vente, 2),
            "marge_pct": round(100 * (total_vente - total_achat) / total_vente, 2) if total_vente else 0,
        },
        "lignes": lignes,
    }
    ecrire_json(RACINE / "donnees" / "proposition.json", sortie)
    # Une prévision n'est comparable qu'archivée avant le jour observé. Ce
    # carnet commence aux prochains calculs, sans reconstituer artificiellement
    # des prévisions pour les ventes déjà connues.
    from previsions_archivees import archiver
    # ecrire_json ajoute l'identifiant du lot à sa copie. Relire la publication
    # atomique sous le verrou pour archiver sa provenance exacte.
    publiee = json.loads((RACINE / "donnees" / "proposition.json").read_text(encoding="utf-8"))
    archiver(RACINE / "donnees", publiee)

    t = sortie["totaux"]
    print(f"Proposition du {date_commande} (livraison le {date_livraison})")
    print(f"  meteo prevue    : {sortie['meteo_livraison'] or 'indisponible'}")
    print(f"  facteurs        : {resultat['facteurs']}")
    print(f"  articles        : {t['articles']} dont {t['articles_a_commander']} a commander")
    print(f"  colis           : {t['colis']}")
    print(f"  montant d'achat : {t['montant_achat']} EUR")
    print(f"  marge           : {t['marge_pct']} %")
    print("\n  Les 8 premiers, dans l'ordre de la tablette :")
    for l in [x for x in lignes if x["propose_colis"] > 0][:8]:
        print(f"    {l['libelle'][:30]:32} {l['propose_colis']:>5} colis"
              f"   position {str(l['position_colis']):>6}   marge {l['marge_pct']:>5} %")


if __name__ == "__main__":
    main()
