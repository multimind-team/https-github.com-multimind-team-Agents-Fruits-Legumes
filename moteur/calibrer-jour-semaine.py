"""
Corrige le décalage systématique de la prévision selon le jour de la semaine.

Constat du 2 septembre 2026 : la formule prévoit 5 à 7,5 % de trop du lundi au
samedi, et 5 % de trop peu le dimanche.

Méthode honnête, en deux temps séparés :
  1. on CALIBRE la correction sur 2024-2025 ;
  2. on la VALIDE sur 2026, des données que la calibration n'a jamais vues.

Sans cette séparation, on ne ferait que se donner raison sur les mêmes chiffres.

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
NOMS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


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


def charger():
    ventes = defaultdict(dict)
    quantites = defaultdict(lambda: [0.0] * 366)
    journees = defaultdict(lambda: [0] * 366)
    vus = defaultdict(set)
    import faits
    for fait in faits.lire(DOSSIER_FAITS):
        if fait["type"] != "vente":
            continue
        article, jour, q = fait["article"], fait["date_source"], fait["quantite"]
        ventes[article][jour] = ventes[article].get(jour, 0.0) + q
        i = jour_annee(jour) - 1
        quantites[article][i] += q
        if article not in vus[jour]:
            journees[article][i] += 1
            vus[jour].add(article)
    return ventes, quantites, journees


def facteurs_profil(ventes):
    total = defaultdict(float)
    for jours in ventes.values():
        for jour, q in jours.items():
            total[jour] += q
    cumul = [[0.0, 0] for _ in range(7)]
    for jour, q in total.items():
        cumul[jour_semaine(jour)][0] += q
        cumul[jour_semaine(jour)][1] += 1
    profil = [(s / n) if n else 0 for s, n in cumul]
    moyenne = sum(profil) / 7
    return [p / moyenne if moyenne else 1 for p in profil]


def mesurer(ventes, quantites, journees, actifs, facteurs, debut, fin, correction=None):
    """Retourne (réel, prévu, erreur absolue, détail par jour de semaine)."""
    reel_total = prevu_total = erreur_total = 0.0
    par_js = defaultdict(lambda: [0.0, 0.0])
    for article in actifs:
        if article not in ventes:
            continue
        somme_q = fenetre_circulaire(quantites[article], FENETRE)
        somme_n = fenetre_circulaire([float(x) for x in journees[article]], FENETRE)
        for jour, reel in ventes[article].items():
            if not (debut <= jour <= fin):
                continue
            i = jour_annee(jour) - 1
            q, n = somme_q[i] - reel, somme_n[i] - 1
            js = jour_semaine(jour)
            prevu = 0.0 if n < MIN_JOURS else (q / n) * facteurs[js]
            if correction:
                prevu *= correction[js]
            reel_total += reel
            prevu_total += prevu
            erreur_total += abs(prevu - reel)
            par_js[js][0] += reel
            par_js[js][1] += prevu
    return reel_total, prevu_total, erreur_total, par_js


def main():
    ventes, quantites, journees = charger()
    facteurs = facteurs_profil(ventes)

    config = regles.charger()
    aggregats = agregats.charger()
    masques = {k for k, v in config.get("overrides", {}).items() if v.get("masque")}
    actifs = {k for k in aggregats["articles"] if k not in masques}

    # --- 1. CALIBRATION sur 2024-2025 ------------------------------------
    _, _, _, par_js = mesurer(ventes, quantites, journees, actifs, facteurs,
                              "2024-01-01", "2025-12-31")
    correction = []
    print("CALIBRATION sur 2024-2025 (donnees d'apprentissage)\n")
    print(f"  {'jour':10} {'reel':>10} {'prevu':>10} {'ecart':>8}   correction")
    for js in range(7):
        r, p = par_js[js]
        c = (r / p) if p else 1.0
        correction.append(c)
        print(f"  {NOMS[js]:10} {round(r):>10} {round(p):>10} {100*(p-r)/r if r else 0:>+7.1f} %   x {c:.3f}")

    # --- 2. VALIDATION sur 2026 -------------------------------------------
    print("\n\nVALIDATION sur 2026 (donnees jamais vues par la calibration)\n")
    for titre, corr in (("SANS correction", None), ("AVEC correction", correction)):
        r, p, e, detail = mesurer(ventes, quantites, journees, actifs, facteurs,
                                  "2026-01-01", "2026-12-31", correction=corr)
        print(f"  {titre}")
        print(f"     biais global   : {100*(p-r)/r:>+7.1f} %")
        print(f"     erreur moyenne : {100*e/r:>7.1f} %")
        pires = max(abs(100*(d[1]-d[0])/d[0]) for d in detail.values() if d[0])
        print(f"     pire jour      : {pires:>7.1f} % d'ecart")
        print()

    r, p, e, detail = mesurer(ventes, quantites, journees, actifs, facteurs,
                              "2026-01-01", "2026-12-31", correction=correction)
    print("  Detail 2026 apres correction :")
    print(f"    {'jour':10} {'reel':>10} {'prevu':>10} {'ecart':>8}")
    for js in range(7):
        rr, pp = detail[js]
        if rr:
            print(f"    {NOMS[js]:10} {round(rr):>10} {round(pp):>10} {100*(pp-rr)/rr:>+7.1f} %")

    print("\n  Facteurs finaux a utiliser (jour de semaine x correction) :")
    for js in range(7):
        print(f"    {NOMS[js]:10} {facteurs[js]:.4f} x {correction[js]:.4f} = {facteurs[js]*correction[js]:.4f}")


if __name__ == "__main__":
    main()
