"""
Les briques de base du calcul de la commande.

Rien n'est inventé ici : la formule est celle du métier, écrite noir sur blanc
dans la documentation du calcul. Ce fichier la met en programme, une fois pour
toutes, et n'en bouge plus.

C'est volontairement la couche la plus bête et la plus stable du moteur :
moyennes de ventes, profil de la semaine, saisonnalité. Tout ce qui décide
quelque chose vit ailleurs (proposer-commande.py, generer-proposition.py).

LECTURE SEULE : ce programme ne modifie aucun carnet.
"""
import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import agregats
import faits
import regles

RACINE = Path(__file__).resolve().parent.parent
DOSSIER_FAITS = RACINE / "donnees" / "faits"

FENETRE_SAISON_JOURS = 21   # ± 21 jours autour du jour de l'année
MIN_JOURS_SAISON = 5        # en dessous, la prévision est 0 — jamais la moyenne annuelle
TAUX_PERTE_DEFAUT = 0.05    # quand l'article n'a aucun historique de pertes

# Cas particulier, ajouté ponctuellement le 2026-09-04 (pas un mécanisme
# général) : les oranges de la machine à jus ne passent jamais en caisse
# elles-mêmes, seule la vente du jus pressé se voit. On convertit donc les
# litres de jus vendus en kilos d'oranges équivalents pour que la commande
# d'oranges en tienne compte. Ratio mesuré par le responsable de rayon le 2026-08-31.
ORANGE_MACHINE_A_JUS = "0000087004386"       # ORANGE PETIT CALIBRE MACHINE A JUS
CONVERSION_JUS_VERS_ORANGE_KG = {
    "0000000008112": 2.0,    # JUS DE FRUIT FRAIS 1L    -> 2 kg d'oranges
    "0000000008111": 1.0,    # JUS DE FRUIT FRAIS 50CL  -> 1 kg d'oranges
}


def jour_de_lannee(date_iso):
    a, m, j = (int(x) for x in date_iso.split("-"))
    return date(a, m, j).timetuple().tm_yday


def lire_faits(bilan=None):
    yield from faits.lire(DOSSIER_FAITS, bilan=bilan)


def fenetre_circulaire(valeurs, demi_largeur):
    """Somme glissante qui boucle de la fin de l'année au début : le 5 janvier
    doit voir les ventes de fin décembre. Règle du métier, reprise telle quelle."""
    n = len(valeurs)
    triple = valeurs + valeurs + valeurs
    cumul = [0.0] * (3 * n + 1)
    for i in range(3 * n):
        cumul[i + 1] = cumul[i] + triple[i]
    return [cumul[n + c + demi_largeur + 1] - cumul[n + c - demi_largeur] for c in range(n)]


def construire_moyennes(jusqua=None):
    """Pour chaque article : la vente moyenne attendue pour chacun des 366 jours
    de l'année, et le taux de perte.

    Deux tableaux par article, remplis à partir des faits :
      - la quantité vendue ce jour de l'année, toutes années confondues ;
      - le nombre de JOURNÉES distinctes où l'article a été vu en vente
        (une seule fois par jour, même s'il y a dix lignes de caisse).
    """
    quantites = defaultdict(lambda: [0.0] * 366)
    journees = defaultdict(lambda: [0] * 366)
    vus_par_jour = defaultdict(set)
    total_vente = defaultdict(float)
    total_pertes = defaultdict(float)

    config = regles.charger()
    vers_principal = {m: p for p, membres in config.get("groupes", {}).items() for m in membres}

    for fait in lire_faits():
        article = vers_principal.get(fait["article"], fait["article"])
        # `jusqua` permet de refaire un calcul tel qu'il aurait ete fait a une
        # date passee, sans les donnees arrivees depuis. Indispensable pour
        # comparer a une proposition archivee.
        if jusqua and (fait.get("date_source") or "") > jusqua:
            continue
        if fait["type"] == "vente":
            jour = fait["date_source"]
            index = jour_de_lannee(jour) - 1
            quantites[article][index] += fait["quantite"]
            total_vente[article] += fait["quantite"]
            if article not in vus_par_jour[jour]:
                journees[article][index] += 1
                vus_par_jour[jour].add(article)
            # Les oranges de la machine a jus ne passent JAMAIS elles-memes en
            # caisse (documente ailleurs, cas normal) : leur consommation ne se
            # voit que dans les ventes de jus. Le responsable de rayon, 2026-09-04 : ~2 kg
            # d'oranges par litre de jus vendu (mesure le 2026-08-31 : 120 kg
            # presses pour 60,5 L vendus). Ajout ponctuel a cet article precis
            # -- pas un mecanisme general de conversion, voir A-FAIRE.md.
            equivalent_kg_orange = CONVERSION_JUS_VERS_ORANGE_KG.get(article)
            if equivalent_kg_orange:
                quantites[ORANGE_MACHINE_A_JUS][index] += fait["quantite"] * equivalent_kg_orange
                total_vente[ORANGE_MACHINE_A_JUS] += fait["quantite"] * equivalent_kg_orange
                if ORANGE_MACHINE_A_JUS not in vus_par_jour[jour]:
                    journees[ORANGE_MACHINE_A_JUS][index] += 1
                    vus_par_jour[jour].add(ORANGE_MACHINE_A_JUS)
        elif fait["type"] in ("casse", "don"):
            # Casse et don sont la meme chose : de la marchandise sortie sans
            # etre vendue. L'une est jetee, l'autre donnee aux Restos du Coeur.
            # Les deux comptent pareil dans le taux de perte (le responsable de rayon, 2026-09-02).
            total_pertes[article] += fait["quantite"]

    resultat = {}
    for article, qte_jours in quantites.items():
        somme_qte = fenetre_circulaire(qte_jours, FENETRE_SAISON_JOURS)
        somme_jours = fenetre_circulaire([float(x) for x in journees[article]], FENETRE_SAISON_JOURS)
        saison, fiable = [], []
        for i in range(366):
            if somme_jours[i] >= MIN_JOURS_SAISON:
                saison.append(round(somme_qte[i] / somme_jours[i], 2))
                fiable.append(1)
            else:
                # Trop peu de journées observées à cette période de l'année :
                # on ne suppose rien. Zéro, jamais la moyenne annuelle.
                saison.append(0.0)
                fiable.append(0)
        vendu, perdu = total_vente[article], total_pertes.get(article, 0.0)
        resultat[article] = {
            "saison": saison,
            "saisonFiable": fiable,
            "totalVente": round(vendu, 2),
            "totalPertes": round(perdu, 2),
            "tauxPerte": (perdu / (vendu + perdu)) if (vendu + perdu) > 0 else TAUX_PERTE_DEFAUT,
        }
    return resultat


def profil_hebdomadaire():
    """Quantité moyenne vendue par jour de semaine, tous articles confondus
    (0 = lundi … 6 = dimanche)."""
    par_jour = defaultdict(float)
    for fait in lire_faits():
        if fait["type"] == "vente":
            par_jour[fait["date_source"]] += fait["quantite"]
    totaux = [[0.0, 0] for _ in range(7)]
    for jour, quantite in par_jour.items():
        a, m, j = (int(x) for x in jour.split("-"))
        indice = date(a, m, j).weekday()
        totaux[indice][0] += quantite
        totaux[indice][1] += 1
    return [round(s / n, 1) if n else 0 for s, n in totaux]


# --- Contrôle du portage ----------------------------------------------------
