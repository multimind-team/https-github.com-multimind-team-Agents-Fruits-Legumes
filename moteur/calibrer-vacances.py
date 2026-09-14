"""
Les vacances scolaires et les jours fériés changent-ils les ventes du rayon ?

Le responsable de rayon, le 2026-09-03 : « Comment ça, rien sur les vacances scolaires ? Les
vacances influent forcément sur les ventes. »

Il a raison de le penser, et c'est bien pour ça qu'il faut le MESURER plutôt que
de le supposer : si l'effet existe, on veut savoir de combien, et à quelles
vacances. Toutes ne se ressemblent pas — la Toussaint dans une petite ville du
Tarn n'est pas le mois d'août.

Méthode, la même que pour la météo (calibrer-meteo.py), pour que les deux
résultats soient comparables :

  pour chaque journée, on compare les ventes réelles à ce que la formule
  prévoyait SANS aucun facteur vacances. Si les journées de vacances vendent
  systématiquement plus (ou moins) que prévu, l'effet existe.

La journée testée est retirée de sa propre moyenne — on ne prédit pas avec la
réponse. Le jour de la semaine, lui, est corrigé : sinon on mesurerait le fait
que les vacances contiennent autant de samedis que le reste de l'année.

LECTURE SEULE. Ce programme ne change rien : il dit ce qu'il trouve, et c'est
Le responsable de rayon qui décide si le calcul doit en tenir compte.
"""
import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import agregats
import calendrier
import regles

RACINE = Path(__file__).resolve().parent.parent
DOSSIER_FAITS = RACINE / "donnees" / "faits"

FENETRE = 21
MIN_JOURS = 5
CORRECTION_JS = [0.953, 0.932, 0.931, 0.934, 0.925, 0.923, 1.047]
MIN_OBSERVATIONS = 10          # en dessous, on ne conclut pas


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


famille = calendrier.famille   # une seule liste de familles, voir calendrier.py


def main():
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
    facteur_js = [(p / moyenne) * CORRECTION_JS[i] if moyenne else 1
                  for i, p in enumerate(profil)]

    config = regles.charger()
    agr = agregats.charger()
    masques = {k for k, v in config.get("overrides", {}).items() if v.get("masque")}
    actifs = {k for k in agr["articles"] if k not in masques}

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

    cal = calendrier.charger()
    groupes = defaultdict(list)
    for j, (reel, prevu) in par_jour.items():
        if not prevu or jour_semaine(j) == 6:
            continue                      # dimanche à part : demi-journée
        contexte = calendrier.ce_jour(j, cal)
        if contexte["ferme"]:
            continue                      # magasin fermé : rien à comparer
        rapport = reel / prevu
        if contexte["ferie"]:
            # Un jour férié à quasi rien vendu n'est pas un jour creux : c'est
            # un jour où le magasin était fermé sans qu'on le sache. On l'écarte
            # au lieu de le laisser fausser la moyenne (lundi de Pâques 2025 :
            # 2 unités vendues sur la journée).
            if rapport < 0.05:
                groupes["  ! férié à ~0 vente (fermeture ?)"].append(rapport)
                continue
            groupes["JOUR FÉRIÉ (magasin ouvert)"].append(rapport)
            # Le jour de la semaine change tout : un férié en milieu de semaine
            # se vide, un férié le vendredi ou le samedi reste un jour de
            # courses. Mesuré le 2026-09-03.
            debut = jour_semaine(j) <= 3          # lundi -> jeudi
            groupes["  · férié lundi-jeudi" if debut
                    else "  · férié vendredi-samedi"].append(rapport)
        if contexte["vacances"]:
            groupes["VACANCES — toutes"].append(rapport)
            groupes[f"  · {famille(contexte['vacances'])}"].append(rapport)
        else:
            groupes["HORS vacances"].append(rapport)

    print("Les vacances scolaires changent-elles les ventes ?")
    print("(ventes réelles ÷ ventes prévues sans facteur vacances, zone C)\n")
    print(f"  {'situation':32} {'jours':>6} {'rapport':>9}   effet")
    print("  " + "-" * 62)
    reperes = {}
    for cle in sorted(groupes, key=lambda c: (c.startswith("  ·"), c)):
        valeurs = groupes[cle]
        moy = sum(valeurs) / len(valeurs)
        reperes[cle] = (moy, len(valeurs))
        fiable = "" if len(valeurs) >= MIN_OBSERVATIONS else "   (trop peu de jours)"
        print(f"  {cle:32} {len(valeurs):>6} {moy:>9.3f}   {100 * (moy - 1):>+6.1f} %{fiable}")

    print("\n  Ce qu'il faut comparer :")
    hors = reperes.get("HORS vacances")
    vac = reperes.get("VACANCES — toutes")
    if hors and vac:
        ecart = (vac[0] / hors[0] - 1) * 100
        print(f"    vacances contre hors vacances : {ecart:+.1f} %")
        if abs(ecart) < 2:
            print("    -> l'écart est trop faible pour être appliqué au calcul.")
        else:
            print(f"    -> effet réel : un facteur de {vac[0] / hors[0]:.3f} se justifierait.")
    ferie = reperes.get("JOUR FÉRIÉ (magasin ouvert)")
    if ferie and hors:
        ecart = (ferie[0] / hors[0] - 1) * 100
        etat = "" if ferie[1] >= MIN_OBSERVATIONS else "  (à confirmer, peu de jours)"
        print(f"    jour férié ouvert contre jour normal : {ecart:+.1f} %{etat}")

    print("\n  Rappel : ce programme ne change rien. Il mesure.")
    print("  C'est le responsable de rayon qui décide si le calcul doit en tenir compte.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
