"""
Recalcule la position de chaque article à partir des carnets, et écrit
donnees/etat.json.

Méthode (voir le-metier.md section 3 et contrat-echange.md) :
  - on part de la DERNIÈRE position mesurée pour l'article ;
  - on applique ensuite les mouvements STRICTEMENT postérieurs à cette date :
    les livraisons ajoutent, les ventes, la casse et les dons retirent ;
  - un article sans aucune position mesurée n'a PAS de position. On écrit
    "inconnue", jamais zéro : zéro voudrait dire « rayon plein, réserve vide »,
    ce qui est une affirmation, pas une absence d'information.

Pourquoi « strictement postérieurs » : la position est relevée le soir, rayon
déjà rempli et livraison du matin déjà rangée. Elle contient donc déjà tous les
mouvements de sa propre journée. Les re-déduire les compterait deux fois — c'est
exactement le genre d'erreur qui fait passer un melon de 25 à −12 colis.

MAIS il y a un deuxième cas, donné par le responsable de rayon le 2026-09-03 :

  « Si je mets le stock à jour entre le moment où je t'envoie le mail et 9h20
    le lendemain, il faudra soustraire la casse, les dons et les ventes du
    lendemain, car ça voudra dire que j'ai modifié le stock APRÈS avoir mis la
    livraison dans la chambre froide. »

Autrement dit, un comptage fait le MATIN ne contient pas la même chose qu'un
comptage fait le SOIR :

  comptage du soir   -> tout le jour est dedans : la livraison rangée le matin
                        ET les ventes de la journée. On n'applique rien du jour.
  comptage du matin  -> la livraison du jour est dedans (il vient de la ranger),
                        mais le magasin n'a pas encore vendu. Il faut donc
                        soustraire les ventes, la casse et les dons de ce
                        jour-là quand ils arriveront, sans jamais rajouter la
                        livraison qu'il a déjà comptée.

C'est pour ça qu'on regarde l'HEURE du comptage, et pas seulement sa date.

"""
import json
from ecriture_derivee import ecrire_json
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import agregats
import faits
import catalogue
import conditionnements
import regles

RACINE = Path(__file__).resolve().parent.parent
DOSSIER_FAITS = RACINE / "donnees" / "faits"

AJOUTE = {"livraison"}
RETIRE = {"vente", "casse", "don"}

# Cas particulier, ajouté ponctuellement le 2026-09-04 (même règle que dans
# calculer-commande.py, pas un mécanisme général) : les oranges de la machine
# à jus ne passent jamais elles-mêmes en caisse, seule la vente du jus pressé
# se voit. Le responsable de rayon : « quand on vend 1L de jus il faut enlever 2 kg à l'orange,
# 50cl -> 1 kg » — la POSITION doit baisser tout de suite, pas seulement la
# prévision de la prochaine commande.
ORANGE_MACHINE_A_JUS = "0000087004386"       # ORANGE PETIT CALIBRE MACHINE A JUS
CONVERSION_JUS_VERS_ORANGE_KG = {
    "0000000008112": 2.0,    # JUS DE FRUIT FRAIS 1L    -> 2 kg d'oranges
    "0000000008111": 1.0,    # JUS DE FRUIT FRAIS 50CL  -> 1 kg d'oranges
}

# Règle d'or du comptage en chambre froide (consigne responsable rayon) :
# 1. Entre 17h00 la veille et la réception du mail du lendemain matin :
#    La livraison du matin n'est pas encore entrée en chambre froide,
#    donc elle n'est PAS comptée dans le stock mesuré.
#    - Saisi après 17h00 : comptage du "soir" (clôture de la journée passée).
#      La livraison du lendemain n'y est pas et s'ajoutera au matin.
#    - Saisi le matin AVANT la réception du mail : comptage "avant-livraison".
#      La livraison du matin n'y est pas et DOIT s'ajouter au stock dès son arrivée.
# 2. À partir de la réception du mail le matin :
#    Les palettes sont déchargées et la marchandise est rangée en rayon et chambre froide.
#    La modification du stock INCLUT DÉJÀ la livraison.
#    - Comptage "matin" (après livraison) : la livraison du jour ne s'ajoute pas une 2e fois.
HEURE_DEBUT_SOIR = "17:00:00"
HEURE_MAIL_DEFAUT = "06:30:00"
FICHIER_RECEPTIONS = RACINE / "donnees" / "receptions-courrier.json"


def charger_heures_reception_mail():
    """Charge les heures exactes de réception des mails de livraison du matin."""
    if FICHIER_RECEPTIONS.exists():
        try:
            with open(FICHIER_RECEPTIONS, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def lire_faits(bilan=None):
    yield from faits.lire(DOSSIER_FAITS, bilan=bilan)


def lire_conditionnements():
    """Le conditionnement sert uniquement à convertir en colis pour l'affichage.
    Il n'entre jamais dans le carnet des faits (contrat-echange.md)."""
    config = regles.charger()
    selections = conditionnements.charger(RACINE, config, catalogue.articles())
    return {code: selection["conditionnement"] for code, selection in selections.items()}


def moment_du_comptage(fait, heures_mail=None):
    """Détermine le moment du comptage selon la règle métier :

    - « soir » : saisi après 17h00. Toute la journée écoulée est dedans.
                 La livraison du lendemain n'y est pas et s'ajoutera.
    - « avant-livraison » : saisi le matin AVANT la réception du mail de livraison.
                            La livraison du jour n'est pas encore entrée en chambre
                            froide, elle devra donc s'ajouter à ce stock.
    - « matin » : saisi le matin APRÈS la réception du mail. La livraison est
                  déjà rangée, elle ne s'ajoute pas une 2e fois.
    """
    # L'heure physique de saisie prévaut sur l'horodatage technique d'enregistrement
    val_heure = (fait.get("source") or {}).get("saisi_le") or fait.get("horodatage") or fait.get("enregistre_le")
    if not val_heure or "T" not in str(val_heure):
        return "soir"

    try:
        heure_str = str(val_heure).split("T")[1][:8]
    except (ValueError, IndexError):
        return "soir"

    # Comptage de fin de journée / soir (dès 16h50 / 17h00) : toute la journée écoulée est dedans
    if heure_str >= "16:50:00":
        return "soir"

    jour = fait.get("date_effet") or fait.get("date_source")
    heure_mail = (heures_mail or {}).get(jour, HEURE_MAIL_DEFAUT)

    if heure_str < heure_mail:
        return "avant-livraison"

    return "matin"


def a_appliquer(jour, type_fait, depart):
    """Ce mouvement est-il DÉJÀ contenu dans le comptage, ou faut-il l'appliquer ?"""
    if jour > depart["date"]:
        return True                      # après le jour du comptage : toujours appliqué
    if jour < depart["date"]:
        return False                     # avant : déjà dedans

    # Même jour que le comptage :
    moment = depart.get("moment")
    if moment == "soir":
        # Compté le soir (après 17h00) : toute la journée écoulée est déjà dedans.
        return False

    if moment == "avant-livraison":
        # Compté le matin AVANT la réception du mail :
        # La livraison n'est pas encore entrée en chambre froide -> DOIT s'ajouter !
        # Les sorties de la journée n'ont pas encore eu lieu -> DOIVENT être déduites.
        return True

    # moment == "matin" (compté le matin APRÈS la réception du mail) :
    # La livraison est déjà rangée en chambre froide et au rayon -> NE PAS l'ajouter une 2e fois !
    # Mais les sorties de la journée n'ont pas encore eu lieu -> elles seront déduites quand le fichier arrivera.
    return type_fait not in AJOUTE


def calculer(jusqua=None):
    heures_mail = charger_heures_reception_mail()
    config = regles.charger()
    vers_principal = {m: p for p, membres in config.get("groupes", {}).items() for m in membres}
    derniere_position = {}
    comptages = {}
    mouvements = defaultdict(list)
    libelles = {}

    for fait in lire_faits():
        jour = fait.get("date_effet") or fait.get("date_source")
        if not jour or (jusqua and jour > jusqua):
            continue
        article = vers_principal.get(fait["article"], fait["article"])
        if fait.get("libelle"):
            libelles.setdefault(article, fait["libelle"])
        if fait["type"] == "comptage":
            horodatage = fait.get("horodatage") or (fait.get("source") or {}).get("horodatage")
            heure = str(horodatage).split("T", 1)[-1][:8] if horodatage and "T" in str(horodatage) else "23:59:59"
            position = {
                "date": jour, "valeur": fait["quantite"],
                "origine": fait.get("origine_mesure", "?"),
                "moment": moment_du_comptage(fait, heures_mail), "heure": heure,
            }
            comptages[fait.get("id")] = (article, position)
            precedente = derniere_position.get(article)
            if precedente is None or (jour, heure) >= (precedente["date"], precedente["heure"]):
                derniere_position[article] = position
        elif fait["type"] == "correction-comptage":
            cible = comptages.get(fait.get("cible_id"))
            if cible and cible[0] == article:
                position = cible[1]
                # Corriger une saisie ne change ni la date ni l'heure de la
                # mesure réelle. L'heure de correction est une trace d'audit.
                position.update({
                    "valeur": fait["quantite"],
                    "origine": fait.get("origine_mesure", "correction-comptage"),
                })
        else:
            mouvements[article].append((jour, fait["type"], fait["quantite"]))
            if fait["type"] == "vente":
                equivalent_kg = CONVERSION_JUS_VERS_ORANGE_KG.get(article)
                if equivalent_kg:
                    mouvements[ORANGE_MACHINE_A_JUS].append(
                        (jour, "vente", fait["quantite"] * equivalent_kg))

    etat = {}
    for article in set(list(mouvements) + list(derniere_position)):
        depart = derniere_position.get(article)
        if depart is None:
            etat[article] = {"position": None, "mesuree_le": None,
                             "raison": "aucune position jamais mesurée pour cet article",
                             "libelle": libelles.get(article, "")}
            continue
        total = depart["valeur"]
        depuis = 0
        for jour, type_fait, quantite in mouvements[article]:
            if not a_appliquer(jour, type_fait, depart):
                continue
            depuis += 1
            total += quantite if type_fait in AJOUTE else -quantite
        etat[article] = {"position": round(total, 3), "mesuree_le": depart["date"],
                         "moment_mesure": depart["moment"],
                         "origine_mesure": depart["origine"],
                         "mouvements_depuis": depuis,
                         "libelle": libelles.get(article, "")}
    return etat


def derniere_date_connue():
    """Le jour le plus récent présent dans les carnets. C'est jusque-là que
    l'état doit être calculé — sinon un comptage fait ce soir serait ignoré,
    parce que les fichiers du magasin en sont encore à la veille."""
    derniere = ""
    for fait in lire_faits():
        jour = fait.get("date_effet") or fait.get("date_source") or ""
        if jour > derniere:
            derniere = jour
    return derniere or None


def main():
    date_reference = agregats.charger()["date_reference"]
    conditionnements = lire_conditionnements()
    heures_mail = charger_heures_reception_mail()

    # L'état courant va jusqu'au dernier jour connu des carnets, pas jusqu'à la
    # date de référence : les positions comptées aujourd'hui comptent.
    jusqua = derniere_date_connue() or date_reference
    etat = calculer(jusqua=jusqua)
    mesurees = {k: v for k, v in etat.items() if v["position"] is not None}

    # Un événement du matin de J sert à la commande de J, pas celle de J+1.
    # Ce repère date la commande, il ne certifie PAS la complétude du stock.
    bases = [date_reference] if date_reference else []
    for fait in lire_faits():
        jour = fait.get("date_effet") or fait.get("date_source")
        type_fait = fait.get("type")
        if not jour or type_fait not in AJOUTE | RETIRE | {"comptage"}:
            continue
        if type_fait in AJOUTE or (type_fait == "comptage" and moment_du_comptage(fait, heures_mail) in ("matin", "avant-livraison")):
            jour = (date.fromisoformat(jour) - timedelta(days=1)).isoformat()
        bases.append(jour)

    sortie = {
        "calcule_jusquau": jusqua,
        "date_base_commande": max(bases) if bases else None,
        "date_reference": date_reference,
        "reconstruit_le": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "articles": etat,
    }
    ecrire_json(RACINE / "donnees" / "etat.json", sortie)

    print(f"Position calculée jusqu'au {jusqua}")
    print(f"  articles avec une position : {len(mesurees)}")
    print(f"  articles sans position     : {len(etat) - len(mesurees)}")

    # Le détail de ce qui a servi : c'est la question que le responsable de rayon pose quand
    # une position le surprend — « elle date de quand, et de quoi ? »
    du_matin = sum(1 for v in mesurees.values() if v.get("moment_mesure") in ("matin", "avant-livraison"))
    if du_matin:
        print(f"  dont comptées le matin     : {du_matin}  "
              "(ventes du jour soustraites, livraison déjà rangée ou à ajouter)")

    anciennes = sorted(mesurees.items(), key=lambda x: x[1]["mesuree_le"])[:5]
    if anciennes:
        print("\n  Les positions les plus vieilles — à recompter en premier :")
        for code, v in anciennes:
            print(f"    {v['mesuree_le']}  {code}  {v['libelle'][:34]:36} "
                  f"{v['position']:>9.2f}  ({v['mouvements_depuis']} mouvements depuis)")


if __name__ == "__main__":
    main()
