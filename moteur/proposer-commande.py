"""
La proposition de commande complète.

Formule (voir le-calcul.md) :

    demandeAujourdhui = venteMoyenne[jour commande]  x meteo x ferie x jourSemaine
    demandeLivraison  = venteMoyenne[jour livraison] x meteo x ferie x jourSemaine
    quantite = max(0, (demandeAujourdhui + demandeLivraison) / (1 - tauxPerte) - position)
    puis arrondi au colis

Ce n'est pas « tenir deux jours » : la position date de la veille au soir, il
faut donc lui retirer ce qui sera vendu aujourd'hui avant de s'en servir.

Lancé sans argument, le script se contrôle lui-même : il recalcule une
proposition de référence et
compare article par article. Tant que les deux ne concordent pas, le portage
est faux.

LECTURE SEULE.
"""
import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import importlib.util


def _charger(nom, fichier):
    chemin = Path(__file__).resolve().parent / fichier
    spec = importlib.util.spec_from_file_location(nom, chemin)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


calc = _charger("calc", "calculer-commande.py")
pos = _charger("pos", "calculer-position.py")

sys.path.insert(0, str(Path(__file__).resolve().parent))
import agregats
import catalogue
import regles

RACINE = Path(__file__).resolve().parent.parent

JOURS_FERIES_FERMETURE = {"01-01", "05-01", "12-25"}
SEUIL_LIVRAISON_RECENTE = 7      # jours
# Au-dela, un comptage est trop vieux pour justifier a lui seul une position
# tres negative : on redemande au responsable de rayon de recompter plutot que de commander.
FRAICHEUR_COMPTAGE_JOURS = 2
PLANCHER_POSITION_COLIS = -10    # seuil inclus ; affichage distinct de l'exception de mesure fraîche
POIDS_VENTES_14J = 0.50


def est_dimanche(iso):
    a, m, j = (int(x) for x in iso.split("-"))
    return date(a, m, j).weekday() == 6


def ajouter_jours(iso, n):
    a, m, j = (int(x) for x in iso.split("-"))
    return (date(a, m, j) + timedelta(days=n)).isoformat()


def decaler(date_iso, jours):
    a, m, j = (int(x) for x in date_iso.split("-"))
    return (date(a, m, j) + timedelta(days=jours)).isoformat()


def jours_entre(debut, fin):
    a1, m1, j1 = (int(x) for x in debut.split("-"))
    a2, m2, j2 = (int(x) for x in fin.split("-"))
    return (date(a2, m2, j2) - date(a1, m1, j1)).days


def prochain_jour_valide(iso, feries):
    """Ni dimanche, ni jour de fermeture : rien n'est commandé ni livré."""
    jour = ajouter_jours(iso, 1)
    for _ in range(10):
        if est_dimanche(jour) or jour[5:] in JOURS_FERIES_FERMETURE or jour in feries:
            jour = ajouter_jours(jour, 1)
        else:
            return jour
    return jour


def facteur_jour_semaine(iso, profil, correction):
    if not profil or len(profil) != 7:
        return 1.0
    moyenne = sum(profil) / 7
    if not moyenne:
        return 1.0
    a, m, j = (int(x) for x in iso.split("-"))
    i = date(a, m, j).weekday()
    return (profil[i] / moyenne) * (correction[i] if correction else 1.0)


def proposer(date_reference, moyennes, positions, config, mercalys, dernieres_livraisons,
             profil, facteurs_meteo, correction=None, feries=(), *, conditionnements=None, contextes=None):
    """Rend la quantité à commander pour chaque article, en unités et en colis.

    `conditionnements` vient de conditionnements.charger : {code: sélection}.
    Sans mapping, conserver le chemin historique ; avec mapping, la décision
    valide reste prioritaire et un PCB injecté invalide est refusé.
    """
    date_commande = prochain_jour_valide(date_reference, feries)
    date_livraison = prochain_jour_valide(date_commande, feries)
    jour_cmd = calc.jour_de_lannee(date_commande) - 1
    jour_liv = calc.jour_de_lannee(date_livraison) - 1

    # Jours d'ouverture intermédiaires entre commande et livraison (ex: dimanche matin pour commande samedi -> livraison lundi)
    jours_intermediaires = []
    courant = ajouter_jours(date_commande, 1)
    while courant < date_livraison:
        if courant[5:] not in JOURS_FERIES_FERMETURE and courant not in feries:
            jours_intermediaires.append(courant)
        courant = ajouter_jours(courant, 1)

    f_meteo = facteurs_meteo.get("meteo", 1) or 1
    f_meteo_cmd = facteurs_meteo.get("meteo_cmd", f_meteo) or 1
    f_meteo_liv = facteurs_meteo.get("meteo_liv", f_meteo) or 1
    f_ferie = facteurs_meteo.get("ferie", 1) or 1
    f_ferie_cmd = facteurs_meteo.get("ferie_cmd", f_ferie) or 1
    f_ferie_liv = facteurs_meteo.get("ferie_liv", f_ferie) or 1
    f_vacances = facteurs_meteo.get("vacances", 1) or 1
    f_vacances_cmd = facteurs_meteo.get("vacances_cmd", f_vacances) or 1
    f_vacances_liv = facteurs_meteo.get("vacances_liv", f_vacances) or 1
    f_js_cmd = facteur_jour_semaine(date_commande, profil, correction)
    f_js_liv = facteur_jour_semaine(date_livraison, profil, correction)

    poids_14j_config = float(config.get("poids_ventes_14j", POIDS_VENTES_14J))
    overrides = config.get("overrides", {})
    lignes = {}
    for itm8, reference in mercalys.items():
        donnees = moyennes.get(itm8)
        if donnees is None:
            continue
        surcharge = overrides.get(itm8, {})
        from contexte_terrain import actif as contexte_actif, coefficient as coefficient_terrain, effectif as contexte_effectif
        contexte = (contextes or {}).get(itm8, {})

        if conditionnements is None:
            try:
                conditionnement = float(surcharge.get("conditionnement") or reference.get("CONDIT.BASE") or 1) or 1
            except (TypeError, ValueError):
                conditionnement = 1.0
        else:
            from conditionnements import _positif_fini, selectionner
            decision = _positif_fini(surcharge.get("conditionnement"))
            if decision is not None:
                conditionnement = decision
            elif itm8 in conditionnements:
                selection = conditionnements[itm8]
                conditionnement = (_positif_fini(selection.get("conditionnement"))
                                   if isinstance(selection, dict) else None)
                if conditionnement is None:
                    raise ValueError(f"Conditionnement sélectionné invalide pour {itm8}")
            else:
                conditionnement = selectionner(None, surcharge, reference)["conditionnement"]

        taux_perte = donnees["tauxPerte"]
        moy_cmd = donnees["saison"][jour_cmd]
        moy_liv = donnees["saison"][jour_liv]
        moy_14j = donnees.get("moyenne_14j")

        # Pondération sur les 14 derniers jours réels
        poids_14j_effectif = poids_14j_config if (moy_14j is not None and moy_14j > 0) else 0.0

        def ajuster_moyenne(moy_saison):
            if poids_14j_effectif > 0:
                if moy_saison > 0:
                    return (1.0 - poids_14j_effectif) * moy_saison + poids_14j_effectif * moy_14j
                return moy_14j
            return moy_saison

        moy_cmd_pond = ajuster_moyenne(moy_cmd)
        moy_liv_pond = ajuster_moyenne(moy_liv)

        # Modulation météo par profil article si disponible
        art_meteo = (facteurs_meteo.get("profils_articles") or {}).get(itm8, {})
        f_m_cmd = art_meteo.get("f_meteo_cmd", f_meteo_cmd)
        f_m_liv = art_meteo.get("f_meteo_liv", f_meteo_liv)

        coeff_cmd = coefficient_terrain(contexte, date_commande)
        coeff_liv = coefficient_terrain(contexte, date_livraison)
        demande_cmd = moy_cmd_pond * f_m_cmd * f_ferie_cmd * f_vacances_cmd * f_js_cmd * coeff_cmd
        demande_liv = moy_liv_pond * f_m_liv * f_ferie_liv * f_vacances_liv * f_js_liv * coeff_liv
        previsions_journalieres = {date_commande: demande_cmd, date_livraison: demande_liv}

        demande_inter = 0.0
        for d_inter in jours_intermediaires:
            j_inter = calc.jour_de_lannee(d_inter) - 1
            moy_inter = donnees["saison"][j_inter]
            moy_inter_pond = ajuster_moyenne(moy_inter)
            f_js_inter = facteur_jour_semaine(d_inter, profil, correction)
            f_m_inter = art_meteo.get("f_meteo_liv", f_meteo_liv)
            prev_inter = (moy_inter_pond * f_m_inter * f_ferie_liv * f_vacances_liv * f_js_inter
                          * coefficient_terrain(contexte, d_inter))
            demande_inter += prev_inter
            previsions_journalieres[d_inter] = prev_inter

        diviseur = max(0.1, 1.0 - min(float(taux_perte), 0.90))
        demande = (demande_cmd + demande_inter + demande_liv) / diviseur

        position = positions.get(itm8, {}).get("position")
        position_connue = position is not None
        position = position or 0.0

        # Une promotion est precommandee par le chef de rayon : rien a commander
        # en quotidien. Sauf si la livraison tombe un lundi, la promo (mardi ->
        # samedi) etant alors deja finie.
        livraison_lundi = date(*(int(x) for x in date_livraison.split("-"))).weekday() == 0
        promotion = bool(surcharge.get("promotion")) and not livraison_lundi

        # Position tres negative : ce n'est plus une mesure, c'est le signe
        # qu'on a perdu le fil. On n'affiche pas de chiffre et on ne commande pas.
        mesure = positions.get(itm8, {})
        date_mesure = (mesure.get("mesuree_le") or "")
        pos_colis = position / conditionnement
        comptee_recemment = date_mesure >= decaler(date_commande, -FRAICHEUR_COMPTAGE_JOURS)
        if pos_colis <= -15.0:
            # Position aberrante (<= -15 colis) : un comptage ancien ne suffit pas,
            # il faut un comptage physique du jour même pour débloquer.
            position_bloquee = date_mesure < date_commande
        else:
            position_bloquee = (not comptee_recemment) and pos_colis <= PLANCHER_POSITION_COLIS

        contexte_liv = contexte_effectif(contexte, date_livraison)
        applique_liv = contexte_actif(contexte_liv, date_livraison)
        arret_terrain = applique_liv and contexte_liv.get("statut") in {"fin-saison", "rupture-fournisseur"}
        # Le minimum vise le stock restant après l'horizon. Il ne fabrique pas
        # de ventes pour une réimplantation ; sa date cible doit être atteinte.
        minimum = float(contexte_liv.get("stock_min_colis", 0)) if applique_liv else 0.0
        if contexte_liv.get("statut") == "reimplantation" and (contexte_liv.get("date_cible") or "9999") > date_livraison:
            minimum = 0.0
        bloquee = promotion or position_bloquee or arret_terrain
        brute = 0.0 if bloquee else max(0.0, demande + minimum * conditionnement - position)

        derniere = dernieres_livraisons.get(itm8)
        pas_livre_recemment = (not derniere) or jours_entre(derniere, date_commande) > SEUIL_LIVRAISON_RECENTE
        if bloquee:
            quantite = 0.0
        elif pas_livre_recemment and brute > 0:
            quantite = -(-brute // conditionnement) * conditionnement      # arrondi au colis SUPERIEUR
        else:
            quantite = round(brute / conditionnement) * conditionnement    # arrondi au colis LE PLUS PROCHE
        if minimum > 0 and not bloquee:
            # Un arrondi au plus proche ne doit pas casser le plancher humain.
            quantite = max(quantite, -(-brute // conditionnement) * conditionnement)

        lignes[itm8] = {
            "libelle": (reference.get("LIBELLE") or "").strip(),
            "propose_unites": round(quantite, 2),
            "propose_colis": round(quantite / conditionnement, 2),
            "conditionnement": conditionnement,
            "position_unites": round(position, 2) if position_connue else None,
            "demande": round(demande, 3),
            # Ventes attendues par date, avant pertes et avant déduction du
            # stock ; seul cet objet peut alimenter les comparaisons futures.
            "previsions_journalieres": {j: round(v, 3) for j, v in sorted(previsions_journalieres.items())},
            "vente_moyenne_jour": round(moy_liv_pond, 2),
            "vente_moyenne_saison": round(moy_liv, 2),
            "vente_moyenne_14j": round(moy_14j, 2) if moy_14j is not None else None,
            "ponderation_14j": round(poids_14j_effectif, 2),
            "taux_perte": round(taux_perte, 3),
            "promotion": promotion,
            "position_bloquee": position_bloquee,
            "contexte_terrain": ({"id": contexte_liv.get("id"), "revision": contexte_liv.get("revision"),
                                 "coefficient_commande": coeff_cmd, "coefficient_livraison": coeff_liv,
                                 "stock_min_colis": minimum, "arret_commande": arret_terrain,
                                 "statut": contexte_liv.get("statut"), "maturite": contexte_liv.get("maturite"),
                                 "debut": contexte_liv.get("debut"), "fin": contexte_liv.get("fin")}
                                if contexte else None),
        }
    return {"date_commande": date_commande, "date_livraison": date_livraison,
            "facteurs": {"meteo": f_meteo, "ferie": f_ferie, "vacances": f_vacances,
                         "jour_semaine_commande": round(f_js_cmd, 4),
                         "jour_semaine_livraison": round(f_js_liv, 4)},
            "lignes": lignes}
