"""
Le calendrier — jours fériés, vacances scolaires, ponts.

Ce qui fait vendre ou pas vendre un rayon de fruits et légumes ne tient pas
qu'à la météo. Un 15 août, une semaine de vacances de la Toussaint, un pont de
l'Ascension : les clients ne sont pas là, ou ils sont là autrement.

Deux sources, deux natures :

  - les JOURS FÉRIÉS se calculent. Pâques donne l'Ascension, le lundi de
    Pentecôte et le lundi de Pâques ; le reste est à date fixe. Aucune source
    extérieure n'est nécessaire, donc rien ne peut tomber en panne.

  - les VACANCES SCOLAIRES se récupèrent une fois auprès du ministère
    (data.education.gouv.fr), puis sont gardées dans donnees/calendrier.json.
    Carmaux dépend de l'académie de TOULOUSE, donc de la ZONE C.

Attention à ne pas confondre deux choses différentes :

  - un jour férié où le magasin est FERMÉ (1er janvier, 1er mai, 25 décembre) :
    ni commande ni livraison, le calcul saute au jour suivant ;
  - un jour férié où le magasin est OUVERT (15 août, Ascension, 14 juillet) :
    on vend, mais pas comme un jour normal. C'est un fait à connaître, pas une
    fermeture.

Usage :
  python moteur/calendrier.py                 ce qui vient dans les 15 jours
  python moteur/calendrier.py --recharger     va rechercher les vacances
  python moteur/calendrier.py 2026-08-15      ce que dit le calendrier ce jour-là
"""
import json
from ecriture_derivee import ecrire_json
import sys
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
FICHIER = RACINE / "donnees" / "calendrier.json"

ZONE = "Zone C"                 # Carmaux -> académie de Toulouse
ACADEMIE = "Toulouse"

# Les trois jours où le magasin ferme vraiment (regle.md).
FERMETURE = {"01-01", "05-01", "12-25"}


def paques(annee):
    """Le calcul de Gauss. Pâques commande l'Ascension et la Pentecôte, donc
    trois des onze jours fériés de l'année bougent avec lui."""
    a = annee % 19
    b, c = divmod(annee, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mois, jour = divmod(h + l - 7 * m + 114, 31)
    return date(annee, mois, jour + 1)


def jours_feries(annee):
    """Les onze jours fériés français, avec leur nom."""
    p = paques(annee)
    return {
        date(annee, 1, 1): "Jour de l'an",
        p + timedelta(days=1): "Lundi de Pâques",
        date(annee, 5, 1): "Fête du travail",
        date(annee, 5, 8): "Victoire 1945",
        p + timedelta(days=39): "Ascension",
        p + timedelta(days=50): "Lundi de Pentecôte",
        date(annee, 7, 14): "Fête nationale",
        date(annee, 8, 15): "Assomption",
        date(annee, 11, 1): "Toussaint",
        date(annee, 11, 11): "Armistice 1918",
        date(annee, 12, 25): "Noël",
    }


def recharger_vacances(annees=(2024, 2025, 2026, 2027)):
    """Va chercher les vacances scolaires au ministère, une bonne fois.
    Si le réseau ne répond pas, on garde ce qu'on avait : mieux vaut un
    calendrier un peu vieux que pas de calendrier du tout."""
    url = ("https://data.education.gouv.fr/api/explore/v2.1/catalog/datasets/"
           "fr-en-calendrier-scolaire/records?" + urllib.parse.urlencode({
               "where": f"location='{ACADEMIE}' and start_date>='{min(annees)}-01-01'",
               "limit": 100, "order_by": "start_date"}))
    with urllib.request.urlopen(url, timeout=30) as reponse:
        donnees = json.load(reponse)
    periodes = []
    for x in donnees.get("results", []):
        if ZONE not in (x.get("zones") or ""):
            continue
        periodes.append({
            "nom": x.get("description"),
            "debut": str(x.get("start_date"))[:10],
            "fin": str(x.get("end_date"))[:10],
        })
    return periodes


def construire(recharger=False):
    ancien = {}
    if FICHIER.exists():
        try:
            ancien = json.loads(FICHIER.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            ancien = {}

    periodes = ancien.get("vacances") or []
    erreur = None
    if recharger or not periodes:
        try:
            periodes = recharger_vacances()
        except Exception as e:          # réseau coupé, site en panne, format changé
            erreur = f"{type(e).__name__} : {e}"

    feries = {}
    for annee in range(2024, 2028):
        for jour, nom in jours_feries(annee).items():
            feries[jour.isoformat()] = nom

    contenu = {
        "_lisez_moi": ("Jours feries (calcules, jamais en panne) et vacances scolaires "
                       "de la zone C (ministere). Sert a expliquer pourquoi une "
                       "journee ne ressemble pas aux autres."),
        "zone": ZONE, "academie": ACADEMIE,
        "mis_a_jour": datetime.now().isoformat(timespec="seconds"),
        "feries": dict(sorted(feries.items())),
        "jours_de_fermeture": sorted(FERMETURE),
        "vacances": periodes,
    }
    if erreur:
        contenu["derniere_erreur"] = erreur
    ecrire_json(FICHIER, contenu)
    return contenu, erreur


def charger():
    if not FICHIER.exists():
        return construire()[0]
    return json.loads(FICHIER.read_text(encoding="utf-8"))


def famille(nom):
    """Regroupe les périodes qui se ressemblent. « Vacances d'Été » et « Vacances
    d'été » doivent compter ensemble. Sert au calibrage (calibrer-vacances.py)
    et à l'application du facteur (generer-proposition.py) — une seule liste
    de familles pour les deux, pour ne jamais les laisser diverger."""
    if not nom:
        return None
    n = nom.lower()
    for cle in ("noël", "noel", "hiver", "printemps", "été", "ete", "toussaint",
                "ascension"):
        if cle in n:
            return {"noel": "Noël", "noël": "Noël", "ete": "Été", "été": "Été"}.get(cle, cle.capitalize())
    return nom


def ce_jour(jour_iso, cal=None):
    """Ce que le calendrier dit d'une journée : férié ? vacances ? fermeture ?"""
    cal = cal or charger()
    quoi = {"date": jour_iso, "ferie": None, "ferme": False, "vacances": None}
    quoi["ferie"] = cal["feries"].get(jour_iso)
    quoi["ferme"] = jour_iso[5:] in set(cal.get("jours_de_fermeture", []))
    for v in cal.get("vacances", []):
        if v["debut"] <= jour_iso <= v["fin"]:
            quoi["vacances"] = v["nom"]
            break
    a, m, j = (int(x) for x in jour_iso.split("-"))
    quoi["jour_semaine"] = ["lundi", "mardi", "mercredi", "jeudi",
                            "vendredi", "samedi", "dimanche"][date(a, m, j).weekday()]
    return quoi


def prochains(jours=15, depuis=None):
    """Ce qui arrive : utile pour prévenir avant, pas après."""
    cal = charger()
    debut = date.fromisoformat(depuis) if depuis else date.today()
    a_venir = []
    for n in range(jours):
        j = (debut + timedelta(days=n)).isoformat()
        q = ce_jour(j, cal)
        if q["ferie"] or q["vacances"] or q["ferme"]:
            a_venir.append(q)
    return a_venir


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--recharger" in sys.argv:
        contenu, erreur = construire(recharger=True)
        if erreur:
            print(f"Vacances non rechargées ({erreur}).")
            print("On garde ce qu'on avait. Les jours fériés, eux, sont calculés.")
        print(f"{len(contenu['feries'])} jours fériés, "
              f"{len(contenu['vacances'])} périodes de vacances ({contenu['zone']}).")
    elif args:
        for jour in args:
            q = ce_jour(jour)
            print(f"\n{jour} — {q['jour_semaine']}")
            print(f"  férié     : {q['ferie'] or 'non'}")
            print(f"  magasin   : {'FERMÉ' if q['ferme'] else 'ouvert'}")
            print(f"  vacances  : {q['vacances'] or 'non'}")
    else:
        a_venir = prochains()
        if not a_venir:
            print("Rien de particulier dans les 15 prochains jours.")
        for q in a_venir:
            marques = [x for x in (q["ferie"], q["vacances"],
                                   "MAGASIN FERMÉ" if q["ferme"] else None) if x]
            print(f"  {q['date']}  {q['jour_semaine']:9} {' · '.join(marques)}")
