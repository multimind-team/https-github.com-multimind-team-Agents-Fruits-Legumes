"""
Les agrégats — ce que preparation-commande sait de chaque article, calculé chez lui.

Pour chaque article : la vente moyenne attendue à cette période de l'année, le
taux de perte, la dernière vente, la dernière livraison, la position du jour.
C'est la matière du calcul de commande.

Avant le 2026-09-03, tout ça venait de `aggregats.json`, un fichier calculé par
les carnets du rayon. L'application doit tout avoir en propre : elle ne doit
tout avoir en propre. Ce fichier-ci remplace le sien, à partir des seuls
carnets de preparation-commande :

    faits/*.jsonl  +  catalogue.json  +  decisions  ->  agregats.json

Le calcul est celui du métier, décrit dans la documentation du calcul, déjà porté et
vérifié article par article.

Usage :
    python moteur/agregats.py            recalcule donnees/agregats.json
    python moteur/agregats.py <code>     ce qu'on sait d'un article

    import agregats
    agregats.charger()["articles"]["0000087010624"]
"""
import importlib.util
import json
from ecriture_derivee import ecrire_json
from verrou_donnees import operation_donnees
import sys
from datetime import date, datetime
from pathlib import Path

MOTEUR = Path(__file__).resolve().parent
sys.path.insert(0, str(MOTEUR))
import catalogue
import conditionnements
import faits
import regles

RACINE = MOTEUR.parent
DONNEES = RACINE / "donnees"
FICHIER = DONNEES / "agregats.json"
DOSSIER_FAITS = DONNEES / "faits"


def _module(nom_fichier):
    """Charge un script du moteur dont le nom contient un tiret."""
    chemin = MOTEUR / nom_fichier
    spec = importlib.util.spec_from_file_location(chemin.stem.replace("-", "_"), chemin)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def lire_faits(bilan=None):
    yield from faits.lire(DOSSIER_FAITS, bilan=bilan)


def date_reference():
    """Le dernier jour pour lequel on a des ventes. C'est « aujourd'hui » du
    point de vue des données, qui n'est pas toujours le vrai aujourd'hui : les
    fichiers arrivent parfois avec un jour de retard."""
    derniere = ""
    for fait in lire_faits():
        if fait["type"] == "vente":
            jour = fait.get("date_source") or ""
            if jour > derniere:
                derniere = jour
    return derniere or date.today().isoformat()


def construire(jusqua=None):
    """Tout ce qu'on sait de chaque article, à partir des seuls carnets."""
    commande = _module("calculer-commande.py")
    moyennes = commande.construire_moyennes(jusqua=jusqua)

    config = regles.charger()
    surcharges = config.get("overrides", {})
    masques = {code for code, s in surcharges.items() if s.get("masque")}
    noms = catalogue.noms()
    selections = conditionnements.charger(DONNEES.parent, config, catalogue.articles())

    derniere_vente, derniere_livraison, ca = {}, {}, {}
    # Le vrai prix de vente, pas celui figé dans catalogue.json (une photo du
    # 3 septembre, jamais remise à jour depuis) : celui du fichier de vente le
    # plus récent qui en donne un. Le responsable de rayon, 2026-09-04 : « le prix de vente à
    # prendre dans le fichier de vente, pour calculer la marge sur les vrais
    # prix ». integrer-fichiers.py calcule ce prix unitaire depuis les colonnes
    # "Valeur prix achat"/"Valeur prix vente" du fichier, quand elles existent.
    dernier_prix_vente, dernier_prix_achat_vente = {}, {}
    vers_principal = {m: p for p, membres in config.get("groupes", {}).items() for m in membres}
    audit_faits = {}
    jours_ventes = set()
    for fait in lire_faits(bilan=audit_faits):
        if jusqua and (fait.get("date_source") or "") > jusqua:
            continue
        article = vers_principal.get(fait["article"], fait["article"])
        jour = fait.get("date_source") or ""
        if fait["type"] == "vente" and jour:
            jours_ventes.add(jour)
        if fait["type"] == "vente" and fait["quantite"] > 0:
            if jour > derniere_vente.get(article, ""):
                derniere_vente[article] = jour
            ca[article] = ca.get(article, 0.0) + fait["quantite"] * catalogue.prix(article)
            if fait.get("prix_vente_unitaire") and jour >= dernier_prix_vente.get(article, ("",))[0]:
                dernier_prix_vente[article] = (jour, fait["prix_vente_unitaire"])
            if fait.get("prix_achat_unitaire") and jour >= dernier_prix_achat_vente.get(article, ("",))[0]:
                dernier_prix_achat_vente[article] = (jour, fait["prix_achat_unitaire"])
        elif fait["type"] == "livraison":
            effet = fait.get("date_effet") or jour
            if effet > derniere_livraison.get(article, ("", 0))[0]:
                derniere_livraison[article] = (effet, fait.get("colis") or 0)

    positions = {}
    etat = DONNEES / "etat.json"
    if etat.exists():
        contenu = json.loads(etat.read_text(encoding="utf-8"))
        for code, valeur in (contenu.get("articles") or contenu).items():
            if isinstance(valeur, dict):
                positions[code] = valeur.get("position", valeur.get("stock"))
            else:
                positions[code] = valeur

    articles = {}
    for code in set(list(moyennes) + list(noms)):
        base = moyennes.get(code, {})
        livraison = derniere_livraison.get(code, ("", 0))
        articles[code] = {
            "libelle": noms.get(code, code),
            "saison": base.get("saison", [0.0] * 366),
            "saisonFiable": base.get("saisonFiable", [0] * 366),
            "totalVente": base.get("totalVente", 0.0),
            "totalPertes": base.get("totalPertes", 0.0),
            "tauxPerte": base.get("tauxPerte", commande.TAUX_PERTE_DEFAUT),
            "totalCA": round(ca.get(code, 0.0), 2),
            "derniereDateVente": derniere_vente.get(code),
            "derniereLivraison": livraison[0] or None,
            "derniereLivraisonColis": livraison[1],
            "dernierPrixVente": dernier_prix_vente.get(code, ("", None))[1],
            "dernierPrixVenteLe": dernier_prix_vente.get(code, ("", None))[0] or None,
            "dernierPrixAchatVente": dernier_prix_achat_vente.get(code, ("", None))[1],
            "position": positions.get(code),
            "masque": code in masques,
            "conditionnement": (selections[code]["conditionnement"] if code in selections else
                                surcharges.get(code, {}).get("conditionnement")
                                or catalogue.conditionnement_cadencier(code)),
            "fournisseur": surcharges.get(code, {}).get("fournisseur")
                           or (catalogue.fiche(code).get("FOURNISSEUR") or "").strip() or None,
            "promotion": bool(surcharges.get(code, {}).get("promotion")),
        }

    reference = jusqua or date_reference()
    return {
        "_lisez_moi": ("Ce que preparation-commande sait de chaque article, calcule a partir de ses "
                       "propres carnets. Refait par agregats.py."),
        "calcule_le": datetime.now().isoformat(timespec="seconds"),
        "date_reference": reference,
        "jours_ventes_integres": sorted(jours_ventes),
        "audit_faits": audit_faits,
        "profil_hebdomadaire": commande.profil_hebdomadaire(),
        # L'ordre de la tablette de commande : l'écran de preparation-commande suit le même,
        # pour que le responsable de rayon recopie sans avoir à chercher ses articles.
        "ordre_webtelevente": catalogue.ordre_webtelevente(),
        # La date de la dernière livraison reçue, par article. Une simple date :
        # c'est la forme qu'attend le calcul de commande.
        "dernieres_livraisons": {code: a["derniereLivraison"]
                                 for code, a in articles.items() if a["derniereLivraison"]},
        "articles": articles,
    }


@operation_donnees(lambda: FICHIER.parent)
def ecrire(jusqua=None):
    contenu = construire(jusqua)
    ecrire_json(FICHIER, contenu, indent=None)
    return contenu


def charger():
    if not FICHIER.exists():
        return ecrire()
    return json.loads(FICHIER.read_text(encoding="utf-8"))


def vente_attendue(code, jour_iso, agr=None):
    """La vente moyenne attendue pour cet article ce jour-là. Zéro hors saison :
    on ne suppose jamais la moyenne annuelle (MIN_JOURS_SAISON)."""
    agr = agr or charger()
    article = agr["articles"].get(code)
    if not article:
        return 0.0
    a, m, j = (int(x) for x in jour_iso.split("-"))
    index = date(a, m, j).timetuple().tm_yday - 1
    return article["saison"][index] if article["saisonFiable"][index] else 0.0


if __name__ == "__main__":
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        agr = charger()
        for code in sys.argv[1:]:
            a = agr["articles"].get(code)
            if not a:
                print(f"{code} : inconnu")
                continue
            jour = agr["date_reference"]
            print(f"\n{code}  {a['libelle']}")
            print(f"  vente attendue aujourd'hui : {vente_attendue(code, jour, agr)}")
            print(f"  vendu en tout              : {a['totalVente']}  ({a['totalCA']} €)")
            print(f"  taux de perte              : {a['tauxPerte']:.1%}")
            print(f"  dernière vente             : {a['derniereDateVente']}")
            print(f"  dernière livraison         : {a['derniereLivraison']} "
                  f"({a['derniereLivraisonColis']} colis)")
            print(f"  position                   : {a['position']}")
            print(f"  colis de                   : {a['conditionnement']}")
            print(f"  masqué                     : {'oui' if a['masque'] else 'non'}")
    else:
        contenu = ecrire()
        print(f"{len(contenu['articles'])} articles agrégés")
        print(f"date de référence : {contenu['date_reference']}")
        print(f"profil de la semaine : {contenu['profil_hebdomadaire']}")
        print(f"écrit dans {FICHIER.relative_to(RACINE)} "
              f"({FICHIER.stat().st_size / 1048576:.1f} Mo)")
