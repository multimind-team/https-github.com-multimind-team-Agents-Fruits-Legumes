"""
Le facteur chaleur doit-il s'appliquer hors juin-juillet-août ?

La règle héritée ne l'applique que de juin à août. Or Carmaux a connu 28 jours à 25 °C ou
plus en dehors de ces trois mois (avril, mai, septembre, octobre) — et il est
annoncé 37 °C les 4 et 5 septembre 2026.

Question posée : un jour chaud vend-il plus, quel que soit le mois ?

Méthode : pour chaque journée, on compare les ventes réelles à ce que la
formule prévoyait SANS aucun facteur météo. Si les jours chauds vendent
systématiquement plus que prévu, l'effet existe et doit être appliqué.

La journée testée est retirée de sa propre moyenne — on ne prédit pas avec la
réponse.

LECTURE SEULE.
"""
import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import agregats
import regles

RACINE = Path(__file__).resolve().parent.parent
DOSSIER_FAITS = RACINE / "donnees" / "faits"

FENETRE = 21
MIN_JOURS = 5
SEUIL_CHAUD = 25.0
SEUIL_PLUIE = 10.0
CORRECTION_JS = [0.953, 0.932, 0.931, 0.934, 0.925, 0.923, 1.047]


def jour_annee(iso):
    a, m, j = (int(x) for x in iso.split("-"))
    return date(a, m, j).timetuple().tm_yday


def jour_semaine(iso):
    a, m, j = (int(x) for x in iso.split("-"))
    return date(a, m, j).weekday()


def fenetre_circulaire(valeurs, demi):
    n = len(valeurs)
    triple = valeurs + valeurs + valeurs
    cumul = [0.0] * (3 * n + 1)
    for i in range(3 * n):
        cumul[i + 1] = cumul[i] + triple[i]
    return [cumul[n + c + demi + 1] - cumul[n + c - demi] for c in range(n)]


def main():
    meteo = json.loads((RACINE / "donnees" / "meteo-historique.json").read_text(encoding="utf-8"))

    ventes = defaultdict(dict)
    quantites = defaultdict(lambda: [0.0] * 366)
    journees = defaultdict(lambda: [0] * 366)
    vus = defaultdict(set)
    import faits
    for fait in faits.lire(DOSSIER_FAITS):
        if fait["type"] != "vente":
            continue
        a, j, q = fait["article"], fait["date_source"], fait["quantite"]
        ventes[a][j] = ventes[a].get(j, 0.0) + q
        i = jour_annee(j) - 1
        quantites[a][i] += q
        if a not in vus[j]:
            journees[a][i] += 1
            vus[j].add(a)

    # profil hebdomadaire
    total_jour = defaultdict(float)
    for jours in ventes.values():
        for j, q in jours.items():
            total_jour[j] += q
    cumul = [[0.0, 0] for _ in range(7)]
    for j, q in total_jour.items():
        cumul[jour_semaine(j)][0] += q
        cumul[jour_semaine(j)][1] += 1
    profil = [(s / n) if n else 0 for s, n in cumul]
    moyenne = sum(profil) / 7
    facteur_js = [(p / moyenne) * CORRECTION_JS[i] if moyenne else 1 for i, p in enumerate(profil)]

    config = regles.charger()
    aggregats = agregats.charger()
    masques = {k for k, v in config.get("overrides", {}).items() if v.get("masque")}
    actifs = {k for k in aggregats["articles"] if k not in masques}

    # prevu / reel par journee, sans aucun facteur meteo
    par_jour = defaultdict(lambda: [0.0, 0.0])
    for article in actifs:
        if article not in ventes:
            continue
        somme_q = fenetre_circulaire(quantites[article], FENETRE)
        somme_n = fenetre_circulaire([float(x) for x in journees[article]], FENETRE)
        for j, reel in ventes[article].items():
            i = jour_annee(j) - 1
            q, n = somme_q[i] - reel, somme_n[i] - 1
            prevu = 0.0 if n < MIN_JOURS else (q / n) * facteur_js[jour_semaine(j)]
            par_jour[j][0] += reel
            par_jour[j][1] += prevu

    groupes = {"chaud ETE (juin-aout)": [], "chaud HORS ETE": [],
               "normal ETE (juin-aout)": [], "normal HORS ETE": []}
    for j, (reel, prevu) in par_jour.items():
        info = meteo.get(j)
        if not info or not prevu or jour_semaine(j) == 6:
            continue          # dimanche a part : demi-journee
        tmax = info[0]
        if tmax is None:
            continue
        ete = 6 <= int(j[5:7]) <= 8
        chaud = tmax >= SEUIL_CHAUD
        cle = ("chaud " if chaud else "normal ") + ("ETE (juin-aout)" if ete else "HORS ETE")
        groupes[cle].append(reel / prevu)

    print("Les jours chauds vendent-ils plus que prevu ?")
    print("(rapport ventes reelles / ventes prevues sans facteur meteo)\n")
    print(f"  {'situation':26} {'jours':>6} {'rapport':>9}   effet")
    reperes = {}
    for cle, valeurs in groupes.items():
        if not valeurs:
            continue
        moy = sum(valeurs) / len(valeurs)
        reperes[cle] = moy
        print(f"  {cle:26} {len(valeurs):>6} {moy:>9.3f}   {100*(moy-1):>+6.1f} %")

    print("\n  Ce qu'il faut comparer :")
    for saison in ("ETE (juin-aout)", "HORS ETE"):
        c, n = reperes.get("chaud " + saison), reperes.get("normal " + saison)
        if c and n:
            print(f"    {saison:18} : chaud vend {100*(c/n-1):+.1f} % de plus qu'un jour normal"
                  f"   -> facteur {c/n:.3f}")
    print(f"\n  Facteur applique aujourd'hui : 1.076, et SEULEMENT de juin a aout.")


if __name__ == "__main__":
    main()
