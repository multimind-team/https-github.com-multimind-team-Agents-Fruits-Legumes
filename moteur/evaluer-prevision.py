"""
Mesure la qualité de la prévision de vente sur l'historique réel.

Question posée : quand la formule annonce « cet article va se vendre à 12 kg
demain », que s'est-il réellement vendu ?

C'est le cœur du calcul : si la prévision de vente est bonne, la commande a des
chances de l'être. Si elle est mauvaise, tout le reste s'écroule.

Précaution importante — on ne triche pas : pour évaluer la prévision d'un jour,
la journée testée est RETIRÉE de la moyenne qui sert à la prédire. Sans ça, on
prédirait avec une moyenne qui contient déjà la réponse.

Le facteur météo n'est pas appliqué ici (il demanderait l'historique météo jour
par jour) ; il ne joue de toute façon qu'en été et de moins de 10 %.

LECTURE SEULE.
"""
import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import agregats
import catalogue
import regles

RACINE = Path(__file__).resolve().parent.parent
DOSSIER_FAITS = RACINE / "donnees" / "faits"

FENETRE = 21
MIN_JOURS = 5


def jour_annee(iso):
    a, m, j = (int(x) for x in iso.split("-"))
    return date(a, m, j).timetuple().tm_yday


def jour_semaine(iso):
    a, m, j = (int(x) for x in iso.split("-"))
    return date(a, m, j).weekday()


def lire_faits(bilan=None):
    import faits
    yield from faits.lire(DOSSIER_FAITS, bilan=bilan)


def fenetre_circulaire(valeurs, demi):
    n = len(valeurs)
    triple = valeurs + valeurs + valeurs
    cumul = [0.0] * (3 * n + 1)
    for i in range(3 * n):
        cumul[i + 1] = cumul[i] + triple[i]
    return [cumul[n + c + demi + 1] - cumul[n + c - demi] for c in range(n)]


def main():
    # --- Ventes réelles, par article et par jour --------------------------
    ventes = defaultdict(dict)          # article -> {jour: quantité}
    quantites = defaultdict(lambda: [0.0] * 366)
    journees = defaultdict(lambda: [0] * 366)
    vus = defaultdict(set)

    for fait in lire_faits():
        if fait["type"] != "vente":
            continue
        article, jour, q = fait["article"], fait["date_source"], fait["quantite"]
        ventes[article][jour] = ventes[article].get(jour, 0.0) + q
        i = jour_annee(jour) - 1
        quantites[article][i] += q
        if article not in vus[jour]:
            journees[article][i] += 1
            vus[jour].add(article)

    # --- Profil hebdomadaire (tous articles confondus) --------------------
    total_par_jour = defaultdict(float)
    for article, jours in ventes.items():
        for jour, q in jours.items():
            total_par_jour[jour] += q
    cumul = [[0.0, 0] for _ in range(7)]
    for jour, q in total_par_jour.items():
        cumul[jour_semaine(jour)][0] += q
        cumul[jour_semaine(jour)][1] += 1
    profil = [(s / n) if n else 0 for s, n in cumul]
    moyenne_profil = sum(profil) / 7
    facteur_js = [p / moyenne_profil if moyenne_profil else 1 for p in profil]

    # --- Articles actifs uniquement ---------------------------------------
    config = regles.charger()
    aggregats = agregats.charger()
    masques = {k for k, v in config.get("overrides", {}).items() if v.get("masque")}
    actifs = {k for k in aggregats["articles"] if k not in masques}
    libelles = {str(a.get("CODE ITM")): (a.get("LIBELLE") or "").strip()
                for a in list(catalogue.articles().values()) if a.get("CODE ITM")}

    # --- Évaluation --------------------------------------------------------
    total_reel = total_prevu = total_erreur = 0.0
    par_js = defaultdict(lambda: [0.0, 0.0])       # jour semaine -> [réel, prévu]
    par_article = defaultdict(lambda: [0.0, 0.0, 0.0])  # article -> [réel, prévu, erreur]
    nb_points = 0

    for article in actifs:
        if article not in ventes:
            continue
        somme_q = fenetre_circulaire(quantites[article], FENETRE)
        somme_n = fenetre_circulaire([float(x) for x in journees[article]], FENETRE)
        for jour, reel in ventes[article].items():
            if jour < "2026-01-01":
                continue  # on évalue sur l'année en cours
            i = jour_annee(jour) - 1
            # On retire la journée testée de sa propre moyenne.
            q = somme_q[i] - reel
            n = somme_n[i] - 1
            if n < MIN_JOURS:
                prevu = 0.0
            else:
                prevu = (q / n) * facteur_js[jour_semaine(jour)]
            erreur = abs(prevu - reel)
            total_reel += reel
            total_prevu += prevu
            total_erreur += erreur
            nb_points += 1
            js = jour_semaine(jour)
            par_js[js][0] += reel
            par_js[js][1] += prevu
            a = par_article[article]
            a[0] += reel; a[1] += prevu; a[2] += erreur

    noms_js = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
    print("QUALITE DE LA PREVISION DE VENTE — annee 2026, articles actifs\n")
    print(f"  couples article/jour evalues : {nb_points}")
    print(f"  vendu reellement             : {round(total_reel):>10} unites")
    print(f"  prevu par la formule         : {round(total_prevu):>10} unites")
    biais = 100 * (total_prevu - total_reel) / total_reel if total_reel else 0
    print(f"  biais global                 : {biais:>+9.1f} %   (positif = la formule commande trop)")
    print(f"  erreur moyenne               : {100*total_erreur/total_reel:>9.1f} %   (part du volume mal anticipee)")

    print("\n  Par jour de la semaine :")
    print(f"    {'jour':10} {'reel':>10} {'prevu':>10} {'ecart':>8}")
    for js in range(7):
        r, p = par_js[js]
        if r:
            print(f"    {noms_js[js]:10} {round(r):>10} {round(p):>10} {100*(p-r)/r:>+7.1f} %")

    print("\n  Les 12 articles ou la formule se trompe le plus (en volume) :")
    classement = sorted(par_article.items(), key=lambda kv: -kv[1][2])[:12]
    print(f"    {'article':>16} {'reel':>9} {'prevu':>9} {'ecart':>8}  libelle")
    for code, (r, p, e) in classement:
        ecart = 100 * (p - r) / r if r else 0
        print(f"    {code:>16} {round(r):>9} {round(p):>9} {ecart:>+7.1f} %  {libelles.get(code,'')[:30]}")


if __name__ == "__main__":
    main()
