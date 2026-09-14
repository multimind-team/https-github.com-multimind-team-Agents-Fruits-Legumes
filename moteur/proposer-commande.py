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
FRAICHEUR_COMPTAGE_JOURS = 7
PLANCHER_POSITION_COLIS = -10    # seuil inclus ; affichage distinct de l'exception de mesure fraîche


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
             profil, facteurs_meteo, correction=None, feries=(), *, conditionnements=None):
    """Rend la quantité à commander pour chaque article, en unités et en colis.

    `conditionnements` vient de conditionnements.charger : {code: sélection}.
    Sans mapping, conserver le chemin historique ; avec mapping, la décision
    valide reste prioritaire et un PCB injecté invalide est refusé.
    """
    date_commande = prochain_jour_valide(date_reference, feries)
    date_livraison = prochain_jour_valide(date_commande, feries)
    jour_cmd = calc.jour_de_lannee(date_commande) - 1
    jour_liv = calc.jour_de_lannee(date_livraison) - 1

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

    overrides = config.get("overrides", {})
    lignes = {}
    for itm8, reference in mercalys.items():
        donnees = moyennes.get(itm8)
        if donnees is None:
            continue
        surcharge = overrides.get(itm8, {})

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

        # Modulation météo par profil article si disponible
        art_meteo = (facteurs_meteo.get("profils_articles") or {}).get(itm8, {})
        f_m_cmd = art_meteo.get("f_meteo_cmd", f_meteo_cmd)
        f_m_liv = art_meteo.get("f_meteo_liv", f_meteo_liv)

        demande_cmd = moy_cmd * f_m_cmd * f_ferie_cmd * f_vacances_cmd * f_js_cmd
        demande_liv = moy_liv * f_m_liv * f_ferie_liv * f_vacances_liv * f_js_liv
        demande = (demande_cmd + demande_liv) / (1 - taux_perte)

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
        #
        # SAUF si le responsable de rayon vient de compter cet article : une valeur qu'il a
        # mesuree lui-meme fait foi, aussi basse soit-elle. Ce cas
        # etait reconnu au champ "stock" de la configuration (une saisie
        # manuelle) ; ce champ n'existe plus depuis que preparation-commande reconstitue
        # ses reglages, on regarde donc la date du comptage, ce qui est plus
        # juste : ce n'est pas la saisie qui compte, c'est sa fraicheur.
        mesure = positions.get(itm8, {})
        comptee_recemment = (mesure.get("mesuree_le") or "") >= decaler(date_commande,
                                                                       -FRAICHEUR_COMPTAGE_JOURS)
        position_bloquee = (not comptee_recemment) and \
            position / conditionnement <= PLANCHER_POSITION_COLIS

        brute = 0.0 if (promotion or position_bloquee) else max(0.0, demande - position)

        derniere = dernieres_livraisons.get(itm8)
        pas_livre_recemment = (not derniere) or jours_entre(derniere, date_commande) > SEUIL_LIVRAISON_RECENTE
        if promotion or position_bloquee:
            quantite = 0.0
        elif pas_livre_recemment and brute > 0:
            quantite = -(-brute // conditionnement) * conditionnement      # arrondi au colis SUPERIEUR
        else:
            quantite = round(brute / conditionnement) * conditionnement    # arrondi au colis LE PLUS PROCHE

        lignes[itm8] = {
            "libelle": (reference.get("LIBELLE") or "").strip(),
            "propose_unites": round(quantite, 2),
            "propose_colis": round(quantite / conditionnement, 2),
            "conditionnement": conditionnement,
            "position_unites": round(position, 2) if position_connue else None,
            "demande": round(demande, 3),
            "vente_moyenne_jour": moy_liv,
            "taux_perte": round(taux_perte, 3),
            "promotion": promotion,
            "position_bloquee": position_bloquee,
        }
    return {"date_commande": date_commande, "date_livraison": date_livraison,
            "facteurs": {"meteo": f_meteo, "ferie": f_ferie, "vacances": f_vacances,
                         "jour_semaine_commande": round(f_js_cmd, 4),
                         "jour_semaine_livraison": round(f_js_liv, 4)},
            "lignes": lignes}
