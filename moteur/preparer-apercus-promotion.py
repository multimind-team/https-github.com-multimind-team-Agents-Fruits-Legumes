"""Crée les images des pages vérifiées d'un prospectus pour la page Promotions."""
import argparse
import json
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "moteur"))
import promotions


def relatif_au_projet(chemin):
    return Path(chemin).resolve().relative_to(RACINE).as_posix()


def main():
    parser = argparse.ArgumentParser(description="Rendre les pages F&L lues d'un prospectus en images.")
    parser.add_argument("prospectus", type=Path, help="PDF prospectus à rendre")
    parser.add_argument("--pages", type=int, nargs="+", required=True, help="Numéros des pages effectivement lues")
    parser.add_argument("--catalogue", type=Path, default=RACINE / "donnees" / "promotions.json")
    args = parser.parse_args()

    source = args.prospectus.resolve()
    catalogue = args.catalogue.resolve()
    destination = source.parent / "apercus" / source.stem
    apercus = promotions.rendre_apercus(source, args.pages, destination)

    donnees = promotions.charger(catalogue)
    donnees.setdefault("source", {})["apercus"] = [relatif_au_projet(chemin) for chemin in apercus]
    catalogue.write_text(json.dumps(donnees, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"pages": args.pages, "apercus": donnees["source"]["apercus"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
