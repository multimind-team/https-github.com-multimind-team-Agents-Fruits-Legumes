"""
Les tendances — ce qui change dans le rayon, et pourquoi peut-être.

Ce programme MESURE. Il compare ce qui s'est vendu ces derniers jours à ce qu'on
attendait à cette période de l'année, et il pose à côté les trois choses qui
expliquent le plus souvent un écart : la météo, les vacances scolaires, les
jours fériés.

Il ne conclut pas. Écrire « les tomates baissent parce qu'il a plu » est un
raisonnement, pas une mesure — et c'est le travail de l'agent analyste, qui lit
ce que ce programme a calculé et le met en mots pour le responsable de rayon.

Le partage est le même que pour l'intégration des fichiers (règle du responsable de rayon,
2026-09-03) : le programme fait le geste répétitif, l'agent analyse, vérifie,
et alerte quand il ne comprend pas.

Ce qui est mesuré :

  - la vente des 7 derniers jours contre la vente ATTENDUE à cette période
    (jamais contre « la semaine dernière » : en fruits et légumes, la saison
    explique la moitié des écarts) ;
  - les articles qui se sont arrêtés net, et ceux qui démarrent ;
  - la météo des 7 jours passés et des 7 à venir ;
  - ce que le calendrier annonce : fériés, vacances, ponts.

Usage :
  python moteur/tendances.py              mesure et écrit donnees/tendances.json
  python moteur/tendances.py --jours 14   sur deux semaines
"""
import argparse
import json
from ecriture_derivee import ecrire_json
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

MOTEUR = Path(__file__).resolve().parent
sys.path.insert(0, str(MOTEUR))
import agregats
import calendrier
import catalogue
import regles

RACINE = MOTEUR.parent
DONNEES = RACINE / "donnees"
FICHIER = DONNEES / "tendances.json"

# En dessous, un écart en pourcentage ne veut rien dire : passer de 2 à 4 unités
# fait +100 % et ne signifie rien pour un rayon.
VENTE_MINIMALE = 20          # unités sur la période, pour être comparé
ECART_NOTABLE = 0.25         # 25 % d'écart avec l'attendu
ARRET_JOURS = 10             # plus rien vendu depuis 10 jours = arrêt


def jour_de_lannee(iso):
    a, m, j = (int(x) for x in iso.split("-"))
    return date(a, m, j).timetuple().tm_yday


def decaler(iso, n):
    a, m, j = (int(x) for x in iso.split("-"))
    return (date(a, m, j) + timedelta(days=n)).isoformat()


def ventes_par_jour(depuis):
    """Ce qui s'est réellement vendu, article par article, jour par jour."""
    reel = defaultdict(lambda: defaultdict(float))
    import faits
    for fait in faits.lire(DONNEES / "faits"):
        if fait["type"] != "vente":
            continue
        jour = fait.get("date_source") or ""
        if jour >= depuis:
            reel[fait["article"]][jour] += fait["quantite"]
    return reel


def meteo(du, au):
    fichier = DONNEES / "meteo-historique.json"
    if not fichier.exists():
        return []
    brut = json.loads(fichier.read_text(encoding="utf-8"))
    jours = []
    for jour, valeurs in sorted(brut.items()):
        if du <= jour <= au and isinstance(valeurs, list) and len(valeurs) >= 2:
            jours.append({"date": jour, "temperature_max": valeurs[0], "pluie_mm": valeurs[1]})
    return jours


def meteo_a_venir():
    """La prévision, si elle est joignable. Sans réseau, on s'en passe : ce
    n'est pas une raison pour ne rien dire du reste."""
    try:
        import importlib.util
        chemin = MOTEUR / "generer-proposition.py"
        spec = importlib.util.spec_from_file_location("gp", chemin)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        prevision = module.meteo_prevue() or {}
        jours = []
        for j, v in sorted(prevision.items()):
            # La prévision arrive en {"tmax":…, "pluie":…} ; l'historique, lui,
            # est une liste [tmax, pluie]. On accepte les deux formes.
            if isinstance(v, dict):
                jours.append({"date": j, "temperature_max": v.get("tmax"),
                              "pluie_mm": v.get("pluie")})
            elif isinstance(v, (list, tuple)) and len(v) >= 2:
                jours.append({"date": j, "temperature_max": v[0], "pluie_mm": v[1]})
        return jours[:7]
    except Exception:
        return []


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--jours", type=int, default=7, help="longueur de la période observée")
    args = p.parse_args()

    agr = agregats.charger()
    articles = agr["articles"]
    fin = agr["date_reference"]
    debut = decaler(fin, -(args.jours - 1))

    config = regles.charger()
    masques = {c for c, s in config["overrides"].items() if s.get("masque")}
    reel = ventes_par_jour(debut)
    cal = calendrier.charger()

    # Les jours de la période, avec ce que le calendrier en dit : un dimanche ou
    # un jour de fermeture ne doit pas être compté comme une journée molle.
    jours_periode = [decaler(debut, n) for n in range(args.jours)]
    contexte_jours = [calendrier.ce_jour(j, cal) for j in jours_periode]
    jours_ouvres = [c for c in contexte_jours
                    if c["jour_semaine"] != "dimanche" and not c["ferme"]]

    hausses, baisses, arrets, demarrages = [], [], [], []
    total_reel = total_attendu = 0.0

    for code, donnees in articles.items():
        if code in masques:
            continue
        vendu = sum(reel.get(code, {}).values())
        attendu = 0.0
        for c in jours_ouvres:
            index = jour_de_lannee(c["date"]) - 1
            if donnees["saisonFiable"][index]:
                attendu += donnees["saison"][index]
        total_reel += vendu
        total_attendu += attendu

        derniere = donnees.get("derniereDateVente")
        nom = donnees["libelle"] or code

        # Un arrêt net : il vendait, il ne vend plus. Ce n'est pas un écart,
        # c'est une disparition — et ça se voit en rayon avant les chiffres.
        if derniere and donnees["totalVente"] > 200:
            depuis = (date.fromisoformat(fin) - date.fromisoformat(derniere)).days
            if depuis >= ARRET_JOURS:
                arrets.append({"article": code, "nom": nom,
                               "derniere_vente": derniere, "jours_sans_vente": depuis})
                continue

        if vendu >= VENTE_MINIMALE and attendu == 0:
            demarrages.append({"article": code, "nom": nom, "vendu": round(vendu, 1)})
            continue
        if attendu < VENTE_MINIMALE and vendu < VENTE_MINIMALE:
            continue

        ecart = (vendu - attendu) / attendu if attendu else 0
        if abs(ecart) < ECART_NOTABLE:
            continue
        ligne = {"article": code, "nom": nom,
                 "vendu": round(vendu, 1), "attendu": round(attendu, 1),
                 "ecart_pourcent": round(ecart * 100, 1),
                 "position": donnees.get("position")}
        (hausses if ecart > 0 else baisses).append(ligne)

    hausses.sort(key=lambda x: -x["ecart_pourcent"])
    baisses.sort(key=lambda x: x["ecart_pourcent"])
    arrets.sort(key=lambda x: -x["jours_sans_vente"])

    ecart_rayon = ((total_reel - total_attendu) / total_attendu * 100) if total_attendu else 0

    # Analyse Ventes vs Livraisons avec protection anti-rupture
    analyse_vl = None
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("avl", MOTEUR / "analyser-ventes-livraisons.py")
        mod_avl = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod_avl)
        analyse_vl = mod_avl.analyser(fenetre_jours=args.jours)
    except Exception:
        pass

    contenu = {
        "_lisez_moi": ("Ce que les chiffres montrent, sans interpretation. C'est "
                       "l'agent tendances qui explique et alerte."),
        "calcule_le": datetime.now().isoformat(timespec="seconds"),
        "periode": {"du": debut, "au": fin, "jours": args.jours,
                    "jours_ouvres": len(jours_ouvres)},
        "rayon": {"vendu": round(total_reel, 1), "attendu": round(total_attendu, 1),
                  "ecart_pourcent": round(ecart_rayon, 1)},
        "meteo_passee": meteo(debut, fin),
        "meteo_a_venir": meteo_a_venir(),
        "calendrier_periode": [c for c in contexte_jours if c["ferie"] or c["vacances"]],
        "calendrier_a_venir": calendrier.prochains(15, depuis=fin),
        "hausses": hausses[:15],
        "baisses": baisses[:15],
        "arrets": arrets[:10],
        "demarrages": demarrages[:10],
        "ventes_vs_livraisons": {
            "journees_isolees_sans_action": analyse_vl["synthese"]["journees_isolees_sans_action"] if analyse_vl else 0,
            "surcommandes_recurrentes": analyse_vl["synthese"]["surcommandes_recurrentes_detectees"] if analyse_vl else 0,
            "anomalies_recurrentes": [
                {
                    "itm8": item["itm8"],
                    "libelle": item["libelle"],
                    "motif": item["motif_analyse"],
                    "ajustement": item.get("ajustement_propose"),
                    "statut": item.get("statut"),
                }
                for item in (analyse_vl.get("anomalies_recurrentes", []) if analyse_vl else [])
            ],
        } if analyse_vl else None,
    }
    ecrire_json(FICHIER, contenu)

    print(f"Période du {debut} au {fin} ({len(jours_ouvres)} jours ouvrés)")
    print(f"  Rayon : {total_reel:.0f} vendus pour {total_attendu:.0f} attendus "
          f"({ecart_rayon:+.1f} %)")
    if contenu["meteo_passee"]:
        t = [m["temperature_max"] for m in contenu["meteo_passee"]]
        pluie = sum(m["pluie_mm"] for m in contenu["meteo_passee"])
        print(f"  Météo : {min(t):.0f}° à {max(t):.0f}°, {pluie:.0f} mm de pluie")
    for titre, lot, cle in (("HAUSSES", hausses, "ecart_pourcent"),
                            ("BAISSES", baisses, "ecart_pourcent")):
        if lot:
            print(f"\n  {titre}")
            for x in lot[:6]:
                print(f"    {x['nom'][:34]:36} {x['vendu']:>7.0f} vendu "
                      f"({x['attendu']:.0f} attendu)  {x[cle]:+.0f} %")
    if arrets:
        print("\n  ARRÊTS")
        for x in arrets[:5]:
            print(f"    {x['nom'][:34]:36} rien vendu depuis {x['jours_sans_vente']} jours")
    if demarrages:
        print("\n  DÉMARRAGES")
        for x in demarrages[:5]:
            print(f"    {x['nom'][:34]:36} {x['vendu']:>7.0f} vendus, aucun historique")
    if analyse_vl and analyse_vl.get("anomalies_recurrentes"):
        print("\n  SUR-COMMANDES RÉCURRENTES (VENTES VS LIVRAISONS)")
        for item in analyse_vl["anomalies_recurrentes"][:5]:
            p = item.get("ajustement_propose")
            txt_prop = f"{p['avant']} -> {p['apres']} colis (-{p['baisse_pourcent']} %)" if p else "0 baisse (anti-rupture/plafond)"
            print(f"    {item['libelle'][:34]:36} {item['consecutive_faibles']} livr. mévente | {txt_prop}")
    if contenu["calendrier_a_venir"]:
        print("\n  À VENIR")
        for c in contenu["calendrier_a_venir"][:6]:
            marques = [m for m in (c["ferie"], c["vacances"],
                                   "MAGASIN FERMÉ" if c["ferme"] else None) if m]
            print(f"    {c['date']}  {c['jour_semaine']:9} {' · '.join(marques)}")
    print(f"\n  Écrit dans {FICHIER.relative_to(RACINE)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
