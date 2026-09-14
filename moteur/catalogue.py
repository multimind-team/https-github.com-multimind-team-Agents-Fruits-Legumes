"""
Le catalogue — la fiche de chaque article du rayon.

Son nom, son nom en caisse, son prix, son conditionnement, son fournisseur,
son unité de mesure. C'est la carte d'identité des articles, et elle vit
maintenant dans preparation-commande : donnees/catalogue.json.

Avant le 2026-09-03, tout le moteur allait la chercher dans le cadencier de la
ailleurs. L'application part de zéro et doit tout avoir en propre : elle doit
pouvoir fonctionner seule le jour où elle sera
opérationnel. Ce qui doit disparaître ne peut pas rester une source.

Le catalogue est mis à jour par l'import contrôlé des cadenciers reçus par
mail. On ajoute les articles nouveaux, on actualise les prix, on ne supprime
jamais un article qu'on a connu — son historique en dépend.

Usage :
    import catalogue
    catalogue.noms()["0000087010624"]        ->  "PDT NR FRITE 2KG ITM"
    catalogue.fiche("0000087010624")         ->  toute la ligne du cadencier
    catalogue.prix("0000087010624")          ->  le prix de vente
"""
import json
from functools import lru_cache
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
FICHIER = RACINE / "donnees" / "catalogue.json"


@lru_cache(maxsize=1)
def charger():
    if not FICHIER.exists():
        raise SystemExit(
            "Catalogue introuvable (donnees/catalogue.json).\n"
            "C'est la fiche de tous les articles : sans lui, rien ne peut être "
            "nommé ni commandé. À reconstruire depuis le dernier cadencier Mercalys reçu, ou "
            "depuis le dernier cadencier reçu par mail.")
    return json.loads(FICHIER.read_text(encoding="utf-8"))


def articles():
    """Tous les articles connus : {code: fiche}."""
    return charger()["articles"]


def fiche(code):
    return articles().get(str(code), {})


@lru_cache(maxsize=1)
def noms():
    """{code: nom lisible}. Le nom du cadencier, pas celui de la caisse."""
    return {code: (a.get("LIBELLE") or "").strip() for code, a in articles().items()}


def nom(code):
    return noms().get(str(code), str(code))


def nom_caisse(code):
    """Le nom que voit la caissière — c'est lui qui trahit les codes jumeaux."""
    return (fiche(code).get("LIBELLE CAISSE") or "").strip()


def prix(code):
    try:
        return float(fiche(code).get("PRIX VENTE") or 0)
    except (TypeError, ValueError):
        return 0.0


def conditionnement_cadencier(code):
    """Le conditionnement ANNONCÉ par le cadencier. Ce n'est pas forcément le
    bon : quand le responsable de rayon a tranché autrement, c'est la décision qui gagne
    (regles.charger()). Voir la règle du box et de la caissette."""
    try:
        return float(fiche(code).get("CONDIT.BASE") or 0) or None
    except (TypeError, ValueError):
        return None


def unite(code):
    return (fiche(code).get("UNITE MESURE") or "").strip()


def ordre_webtelevente():
    """L'ordre dans lequel les articles défilent sur la tablette de commande.
    L'écran de commande de preparation-commande suit le même, pour que le responsable de rayon recopie sans
    chercher."""
    return charger().get("ordre_webtelevente", {})


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        for code in sys.argv[1:]:
            f = fiche(code)
            if not f:
                print(f"{code} : inconnu au catalogue")
                continue
            print(f"\n{code}  {nom(code)}")
            print(f"  en caisse       : {nom_caisse(code)}")
            print(f"  prix de vente   : {prix(code)} €")
            print(f"  conditionnement : {conditionnement_cadencier(code)}")
            print(f"  unité           : {unite(code)}")
            print(f"  fournisseur     : {f.get('FOURNISSEUR')}")
    else:
        c = charger()
        print(f"{len(c['articles'])} articles")
        print(f"cadencier du {c.get('derniere_maj')}, repris le {c.get('repris_le', '?')[:10]}")
