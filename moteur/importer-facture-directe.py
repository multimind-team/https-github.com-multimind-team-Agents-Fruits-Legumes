"""Importe une facture TerreAzur/Pomona déjà extraite et contrôlée par les agents.

L'entrée est un JSON structuré produit après lecture de toutes les pages du
bordereau. Ce programme refuse les montants, codes ou quantités ambigus ; il
ne lance aucune OCR et ne déduit jamais une ligne manquante.
"""
import sys

# Le CLI ne laisse pas de cache Python, y compris lors de --simuler sans -B.
sys.dont_write_bytecode = True

import argparse
import json
from pathlib import Path

from facture_directe import (FactureInvalide, choisir_classeur,
                            importer_facture, valider_facture)

RACINE = Path(__file__).resolve().parent.parent
MAPPINGS = RACINE / "donnees" / "fournisseurs" / "codes-terreazur.json"



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("json_facture", help="JSON de lignes extraites et relues")
    parser.add_argument("--marge", type=Path, help="Classeur existant, préfixé MMYY de la facture")
    parser.add_argument("--simuler", action="store_true")
    parser.add_argument("--classeur-seul", action="store_true",
                        help="Préparer uniquement A/C/F dans le classeur, sans lire ni écrire le stock")
    args = parser.parse_args()
    if args.classeur_seul and args.marge is None:
        parser.error("--classeur-seul exige --marge : choisir explicitement le classeur de travail")
    try:
        donnees = json.loads(Path(args.json_facture).read_text(encoding="utf-8"))
        correspondances = json.loads(MAPPINGS.read_text(encoding="utf-8")).get("codes", {})
        facture = valider_facture(donnees, correspondances)
        marge = choisir_classeur(RACINE, facture["date_reception"], args.marge)
        jour = facture["date_reception"][8:10]
        bilan = importer_facture(RACINE, marge, facture, simuler=args.simuler,
                                 classeur_seul=args.classeur_seul)
        if args.simuler:
            resultat = {"simulation": True, "lignes": len(facture["lignes"]), "jour": jour,
                        "stock": "non écrit", "marge": str(marge), **bilan}
        else:
            resultat = {"simulation": False, "lignes": len(facture["lignes"]),
                        "marge": str(marge), **bilan}
        if args.classeur_seul:
            resultat.update(classeur_seul=True, stock="non écrit")
    except (OSError, json.JSONDecodeError, FactureInvalide) as erreur:
        print(f"REFUSÉ : {erreur}", file=sys.stderr)
        return 2
    print(json.dumps(resultat, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
