"""
Prépare la liste des articles à compter, pour l'écran de comptage.

Les ventes du jour en cours ne sont pas encore connues : elles n'arriveront que
demain matin, dans le mail. Sans correction, la position proposée à l'écran est
donc trop haute de toute une journée de ventes -- constaté par le responsable de rayon le
2026-09-02 en faisant son comptage du soir.

On retire donc une ESTIMATION des ventes des journées manquantes. Elle ne
touche jamais les carnets : elle ne sert qu'à afficher un point de départ
plus proche du réel. Ce que le responsable de rayon valide reste une mesure, pas une estimation.

Écrit donnees/articles.json : un article par entrée, avec ce qu'il faut pour
compter debout dans une chambre froide — le libellé, la taille du colis, la
dernière position connue et sa date.

Les articles sont classés par importance (chiffre d'affaires décroissant) :
les plus gros volumes en premier, pour que le comptage reste utile même
lorsqu'il est interrompu.

Chaque article porte `part_ca_cumulee` : la part du chiffre d'affaires du rayon
couverte une fois cet article compte. L'ecran l'affiche en continu, ce qui
permet au responsable de rayon de s'arreter quand il veut en sachant exactement ou il en est.

Pas de liste "20/80" separee : puisque les articles sont deja classes par
importance, s'arreter en cours de route donne automatiquement les plus gros
volumes (remarque du responsable de rayon le 2026-09-02). Un filtre en plus n'apporterait
rien qu'un ecran de plus.

Les articles sans vente depuis plus de 30 jours ne comptent pas dans ce calcul
de part : leur chiffre d'affaires cumule peut etre eleve alors qu'ils ne se
vendent plus du tout (cas de l'artichaut, hors saison).

LECTURE SEULE sur les carnets : ce programme n'en modifie aucun.
"""
import importlib.util
import json
from ecriture_derivee import ecrire_json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import agregats
import catalogue
import conditionnements
import regles

RACINE = Path(__file__).resolve().parent.parent

# Correction du biais par jour de semaine (voir calibrer-jour-semaine.py)
CORRECTION_JS = [0.953, 0.932, 0.931, 0.934, 0.925, 0.923, 1.047]


def _charger(nom, fichier):
    chemin = Path(__file__).resolve().parent / fichier
    spec = importlib.util.spec_from_file_location(nom, chemin)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def ventes_estimees_des_jours_manquants(aggregats, etat):
    """Ce qui s'est probablement vendu depuis la dernière journée connue.

    Règle du responsable de rayon (2026-09-02) : pour un
    article qui vient d'être compté, on ne retire JAMAIS les ventes du jour.
    Son comptage est fait le soir, rayon rempli : il contient déjà les ventes
    de sa propre journée. Seule la livraison suivante s'ajoute.

    L'estimation ne porte donc que sur les journées postérieures À LA FOIS à la
    dernière vente connue ET au dernier comptage de cet article. Sans ça, un
    article compté aujourd'hui verrait ses ventes déduites deux fois.

    Rend {code: quantité estimée}, et la liste des jours concernés.
    """
    calc = _charger("calc", "calculer-commande.py")
    moyennes = calc.construire_moyennes()

    # Dernier jour de vente réellement connu
    dernier = ""
    import faits
    for fait in faits.lire(RACINE / "donnees" / "faits"):
        if fait["type"] == "vente" and fait["date_source"] > dernier:
            dernier = fait["date_source"]
    if not dernier:
        return {}, []

    aujourdhui = date.today()
    debut = date(*(int(x) for x in dernier.split("-")))
    jours = []
    for n in range(1, (aujourdhui - debut).days + 1):
        j = date.fromordinal(debut.toordinal() + n)
        if j.weekday() == 6:      # dimanche : le rayon n'est pas travaillé
            continue
        jours.append(j)
    if not jours:
        return {}, []

    profil = aggregats.get("profil_hebdomadaire") or []
    moyenne_profil = (sum(profil) / 7) if profil else 0

    estimation = {}
    for code, donnees in moyennes.items():
        # Un comptage récent rend inutile — et faux — de déduire les ventes
        # des journées qu'il couvre déjà.
        compte_le = (etat.get(code) or {}).get("mesuree_le") or ""
        total = 0.0
        for j in jours:
            if compte_le and j.isoformat() <= compte_le:
                continue
            moyenne_jour = donnees["saison"][j.timetuple().tm_yday - 1]
            facteur = 1.0
            if moyenne_profil:
                facteur = (profil[j.weekday()] / moyenne_profil) * CORRECTION_JS[j.weekday()]
            total += moyenne_jour * facteur
        if total > 0:
            estimation[code] = round(total, 2)
    return estimation, [j.isoformat() for j in jours]


SEUIL_POSITION_PERDUE_COLIS = -10


def position_est_perdue(position_unites, conditionnement):
    """Au-delà du seuil, une position négative n'est plus exploitable."""
    return position_unites is not None and (position_unites / conditionnement) <= SEUIL_POSITION_PERDUE_COLIS


def main():
    aggregats = agregats.charger()
    config = regles.charger()
    etat_path = RACINE / "donnees" / "etat.json"
    etat = json.loads(etat_path.read_text(encoding="utf-8"))["articles"] if etat_path.exists() else {}
    estimation, jours_estimes = ventes_estimees_des_jours_manquants(aggregats, etat)

    overrides = config.get("overrides", {})
    masques = {k for k, v in overrides.items() if v.get("masque")}
    mercalys = {str(a.get("CODE ITM")): a for a in list(catalogue.articles().values())
                if a.get("CODE ITM")}
    selections = conditionnements.charger(RACINE, config, mercalys)

    articles = []
    for code, donnees in aggregats["articles"].items():
        if code in masques:
            continue
        reference = mercalys.get(code, {})
        surcharge = overrides.get(code, {})

        selection = selections.get(code) or conditionnements.selectionner(None, surcharge, reference)
        conditionnement = selection["conditionnement"]

        unite = (surcharge.get("unite") or "").strip()
        if not unite:
            brut = (reference.get("UNITE MESURE") or "").strip()
            unite = " ".join(brut.split(" ")[1:]) or "unité"

        position = etat.get(code, {})
        # On retire l'estimation des ventes pas encore connues : sans ça, la
        # valeur proposée à l'écran est trop haute de toute une journée.
        brute = position.get("position")
        vendu_estime = estimation.get(code, 0.0) if brute is not None else 0.0
        corrigee = (brute - vendu_estime) if brute is not None else None
        # Sous -10 colis, ce n'est plus une position, c'est le signe qu'on a
        # perdu le fil. Proposer -61 colis a l'ecran
        # ne servirait a rien : mieux vaut ne rien proposer et laisser compter.
        perdue = position_est_perdue(corrigee, conditionnement)
        if perdue:
            corrigee = None
        articles.append({
            "itm8": code,
            "libelle": (reference.get("LIBELLE") or position.get("libelle") or "").strip() or code,
            "fournisseur": (surcharge.get("fournisseur") or
                            (reference.get("FOURNISSEUR") or "").strip().split(" ", 1)[-1]).strip(),
            "conditionnement": conditionnement,
            "source_conditionnement": selection["source_conditionnement"],
            "avertissements_conditionnement": selection["avertissements"],
            "unite": unite,
            "derniere_position_unites": corrigee,
            "derniere_position_colis": (round(corrigee / conditionnement, 1)
                                        if corrigee is not None else None),
            "position_avant_estimation": brute,
            "position_perdue": perdue,
            "ventes_estimees_retirees": round(vendu_estime, 2) if vendu_estime else 0,
            "mesuree_le": position.get("mesuree_le"),
            "ca": donnees.get("totalCA") or 0,
        })

    # --- Part du chiffre d'affaires couverte au fil du comptage -----------
    RECENCE_MAX_JOURS = 30
    reference = aggregats.get("date_reference")

    def jours_depuis(iso):
        if not iso or not reference:
            return 9999
        from datetime import date as _d
        a1, m1, j1 = (int(x) for x in iso.split("-"))
        a2, m2, j2 = (int(x) for x in reference.split("-"))
        return (_d(a2, m2, j2) - _d(a1, m1, j1)).days

    vendus_recemment = {a["itm8"] for a in articles
                        if jours_depuis(aggregats["articles"][a["itm8"]].get("derniereDateVente")) <= RECENCE_MAX_JOURS}
    ca_total = sum(a["ca"] for a in articles if a["itm8"] in vendus_recemment)

    articles.sort(key=lambda a: -a["ca"])
    cumul = 0.0
    for rang, article in enumerate(articles, 1):
        if article["itm8"] in vendus_recemment:
            cumul += article["ca"]
        article["rang"] = rang
        article["part_ca_cumulee"] = round(100 * cumul / ca_total, 1) if ca_total else 0
        del article["ca"]

    sortie = {
        "genere_le": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "date_reference": aggregats.get("date_reference"),
        "jours_de_vente_estimes": jours_estimes,

        "articles": articles,
    }
    ecrire_json(RACINE / "donnees" / "articles.json", sortie)

    avec = sum(1 for a in articles if a["derniere_position_colis"] is not None)
    perdues = sum(1 for a in articles if a.get("position_perdue"))
    if perdues:
        print(f"{perdues} article(s) sans position credible : rien ne sera propose, "
              "il faudra les compter.")
    if jours_estimes:
        n = sum(1 for a in articles if a.get("ventes_estimees_retirees"))
        print(f"Ventes estimees retirees pour {len(jours_estimes)} journee(s) "
              f"pas encore connue(s) ({', '.join(jours_estimes)}) sur {n} articles.\n")
    print(f"{len(articles)} articles a compter (actifs, classes par importance)")
    print(f"   dont {avec} avec une position deja connue")
    for seuil in (50, 80, 95):
        n = next((a["rang"] for a in articles if a["part_ca_cumulee"] >= seuil), len(articles))
        print(f"   {seuil} % du chiffre d'affaires atteint au {n}e article")
    print("\n   Les 5 premiers :")
    for a in articles[:5]:
        p = a["derniere_position_colis"]
        print(f"     {a['rang']:>3}. {a['libelle'][:32]:34} {a['part_ca_cumulee']:>5} % du CA cumule"
              f"   derniere position : {p if p is not None else '-'}")


if __name__ == "__main__":
    main()
