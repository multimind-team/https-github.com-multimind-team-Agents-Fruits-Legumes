"""
Enregistrer au stock une livraison qui n'arrive JAMAIS par les fichiers
Livraison-*.xlsx — Pomona, TerreAzur, Garrigues, Pouget, Cabanes... tout
fournisseur en circuit direct.

Pourquoi ce programme existe (trouvé le 2026-09-04) : seul Scafruit alimente
le stock automatiquement, via les fichiers reçus par mail et lus par
integrer-fichiers.py. Les livraisons des autres fournisseurs arrivent en
photo de bordereau papier — l'agent courrier les lit, les note dans la note du
matin, remplit le calcul de marge Pomona... mais jusqu'ici, RIEN n'ajoutait
la quantité livrée à la position de l'article. Résultat concret : la laitue
feuille de chêne affichait -4 colis alors qu'elle venait d'être livrée par
Pomona le matin même. 15 des 16 produits d'un même bordereau étaient dans le
même cas, certains depuis des semaines (jusqu'à -185 colis).

Ce programme comble le trou, ligne par ligne, comme appliquer-decision.py
comble les décisions : on écrit un vrai mouvement de livraison dans
donnees/faits/<année>.jsonl (append-only, jamais réécrit), avec la quantité
réelle et le motif de la correction. calculer-position.py le lira comme
n'importe quel autre mouvement au prochain recalcul.

CE N'EST TOUJOURS PAS AUTOMATIQUE — quelqu'un (l'agent courrier, ou
Le responsable de rayon) doit lancer ce programme pour chaque ligne d'un bordereau, avec la
vraie quantité lue dessus (jamais devinée). Une vraie automatisation
demanderait de lire le bordereau tout seul, ce qui n'est pas fait.

Usage :
  python moteur/enregistrer-livraison-directe.py <itm8> <quantite> \\
      --fournisseur POMONA --motif "..." [--colis N] [--date AAAA-MM-JJ] \\
      [--bordereau "numéro"]

  quantite : la vraie quantité livrée, dans l'unité de l'article (kg ou
             pièces selon le catalogue) — JAMAIS un nombre de colis.
  --colis  : optionnel, pour la traçabilité (combien de colis physiques).
"""
import argparse
import json
import math
import re
import sys
import uuid
from datetime import date as date_cls
from pathlib import Path

MOTEUR = Path(__file__).resolve().parent
sys.path.insert(0, str(MOTEUR))
import catalogue
from verrou_donnees import append_jsonl, operation_donnees

RACINE = MOTEUR.parent
DOSSIER_FAITS = RACINE / "donnees" / "faits"


def unite_sans_quantite(code):
    """catalogue.unite() renvoie '2 kg' ou '1 Pièce' — on ne garde que le mot,
    comme le font les vrais fichiers de livraison Scafruit."""
    brute = catalogue.unite(code)
    return re.sub(r"^\d+\s*", "", brute).strip() or "inconnue"


def deja_enregistre(fichier, identifiant):
    if not fichier.exists():
        return False
    with open(fichier, encoding="utf-8") as f:
        for ligne in f:
            if ligne.strip() and json.loads(ligne).get("id") == identifiant:
                return True
    return False


@operation_donnees(lambda: DOSSIER_FAITS.parent)
def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("itm8")
    p.add_argument("quantite", type=float)
    p.add_argument("--fournisseur", required=True,
                   help="POMONA, GARRIGUES, POUGET, CABANES... (voir moteur/regles.py)")
    p.add_argument("--motif", required=True,
                   help="Pourquoi cette livraison n'a pas été enregistrée autrement, "
                        "et d'où vient la quantité.")
    p.add_argument("--colis", type=float, default=None,
                   help="Nombre de colis physiques, pour la traçabilité seulement.")
    p.add_argument("--date", default=None,
                   help="Date de réception (AAAA-MM-JJ). Par défaut : aujourd'hui.")
    p.add_argument("--bordereau", default=None, help="Numéro du bordereau, si connu.")
    p.add_argument("--forcer", action="store_true",
                   help="Enregistrer même si un mouvement identique existe déjà "
                        "pour cet article, ce fournisseur et cette date.")
    args = p.parse_args()

    if not re.fullmatch(r"[0-9]{13}", args.itm8):
        p.error("Le code article doit comporter exactement 13 chiffres, sans espace.")
    jour = args.date or date_cls.today().isoformat()
    try:
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", jour):
            raise ValueError
        date_cls.fromisoformat(jour)
    except ValueError:
        p.error("La date de réception doit être une date civile valide AAAA-MM-JJ.")
    if not math.isfinite(args.quantite) or args.quantite <= 0:
        p.error("La quantité livrée doit être un nombre fini strictement positif.")
    if args.colis is not None and (not math.isfinite(args.colis) or args.colis <= 0):
        p.error("Le nombre de colis doit être fini et strictement positif, ou omis s'il est inconnu.")
    for champ, valeur in (("fournisseur", args.fournisseur), ("motif", args.motif)):
        if not valeur.strip() or any(ord(c) < 32 for c in valeur):
            p.error(f"Le {champ} doit être renseigné sans caractère de contrôle.")
    if args.colis and not math.isfinite(args.quantite / args.colis):
        p.error("Le conditionnement calculé n'est pas un nombre fini.")

    fiche = catalogue.fiche(args.itm8)
    if not fiche:
        sys.exit(f"Article inconnu du catalogue : {args.itm8}. "
                 "Impossible d'enregistrer une livraison pour un code qui n'existe pas — "
                 "s'il vient d'un bordereau fournisseur, il faut d'abord le rapprocher "
                 "(appliquer-decision.py rapprocher) ou vérifier le code magasin.")

    libelle = (fiche.get("LIBELLE") or args.itm8).strip()
    unite = unite_sans_quantite(args.itm8)
    par_colis = round(args.quantite / args.colis, 3) if args.colis else None

    identifiant = f"livraison:{jour}:{args.itm8}:direct-{args.fournisseur.lower()}"
    fichier = DOSSIER_FAITS / f"{jour[:4]}.jsonl"
    doublon = deja_enregistre(fichier, identifiant)

    if doublon and not args.forcer:
        sys.exit(f"Déjà enregistré : {identifiant}\n"
                 "Si c'est une VRAIE deuxième livraison le même jour, relance avec --forcer "
                 "(la trace gardera les deux, jamais une écrasée par l'autre).")

    motif_complet = args.motif
    if args.bordereau:
        motif_complet += f" (bordereau {args.bordereau})"

    fait = {
        "id": identifiant if not doublon else f"{identifiant}-{uuid.uuid4().hex}",
        "type": "livraison",
        "date_source": jour,
        "date_effet": jour,
        "article": args.itm8,
        "article_source": args.itm8,
        "quantite": args.quantite,
        "unite": unite,
        "libelle": libelle,
        "colis": args.colis,
        "par_colis": par_colis,
        "source": {"origine": f"manuel/{args.fournisseur.lower()}", "motif": motif_complet},
    }

    DOSSIER_FAITS.mkdir(parents=True, exist_ok=True)
    append_jsonl(fichier, [fait])

    print(f"OK : {libelle} — {args.quantite} {unite} ajoutés au stock "
          f"({args.fournisseur}, {jour}).")
    print("  Penser à relancer : moteur/agregats.py, moteur/calculer-position.py, "
          "moteur/generer-proposition.py")


if __name__ == "__main__":
    main()
