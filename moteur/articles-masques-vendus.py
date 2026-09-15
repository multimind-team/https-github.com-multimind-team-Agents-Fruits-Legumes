"""
Les articles masqués qui continuent de se vendre.

Un article masqué n'apparaît jamais dans la proposition de commande. S'il
continue de passer en caisse, il se vide sans jamais être réapprovisionné,
et personne ne le voit puisqu'il est invisible.

Ce script prépare le dossier de chaque cas — ventes, livraisons, code jumeau
possible — pour que le responsable de rayon tranche article par article. Il ne décide rien.

Écrit donnees/masques-vendus.json et affiche le détail.

LECTURE SEULE.
"""
from ecriture_derivee import ecrire_json
import sys
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import agregats
import catalogue
import regles

RACINE = Path(__file__).resolve().parent.parent
DOSSIER_FAITS = RACINE / "donnees" / "faits"

DEPUIS = "2026-08-01"
VIDES = {"vrac", "piece", "pieces", "kg", "france", "petit", "prix", "itm", "mmp",
         "de", "du", "la", "le", "les", "a", "en", "et", "cat", "import"}


def sans_accent(t):
    return "".join(c for c in unicodedata.normalize("NFD", t or "")
                   if unicodedata.category(c) != "Mn").lower()


def mots(t):
    return {m for m in re.split(r"[^a-z0-9]+", sans_accent(t)) if m and m not in VIDES and len(m) > 1}


def main():
    aggregats = agregats.charger()
    config = regles.charger()
    overrides = config.get("overrides", {})
    masques = {k for k, v in overrides.items() if v.get("masque")}
    groupes = config.get("groupes", {})
    relies = set(groupes) | {m for ms in groupes.values() for m in ms}
    libelles = {str(a["CODE ITM"]): (a.get("LIBELLE") or "").strip()
                for a in list(catalogue.articles().values()) if a.get("CODE ITM")}

    vendu_recent = defaultdict(float)
    vendu_total = defaultdict(float)
    derniere_vente = defaultdict(str)
    livre_colis = defaultdict(float)
    derniere_livraison = defaultdict(str)
    import faits
    for fait in faits.lire(DOSSIER_FAITS):
        code, jour = fait["article_source"], fait["date_source"]
        if fait["type"] == "vente" and fait["quantite"] > 0:
            vendu_total[code] += fait["quantite"]
            if jour >= DEPUIS:
                vendu_recent[code] += fait["quantite"]
            if jour > derniere_vente[code]:
                derniere_vente[code] = jour
        elif fait["type"] == "livraison":
            livre_colis[code] += fait.get("colis") or 0
            if jour > derniere_livraison[code]:
                derniere_livraison[code] = jour

    cas = []
    for code in masques:
        if vendu_recent.get(code, 0) <= 0:
            continue
        nom = libelles.get(code, code)
        cherches = mots(nom)

        # Un jumeau possible : même produit, actif, qui se vend bien
        jumeaux = []
        for autre, autre_nom in libelles.items():
            if autre == code or autre in masques:
                continue
            if vendu_recent.get(autre, 0) < 10:
                continue
            communs = cherches & mots(autre_nom)
            if not communs:
                continue
            produit = sans_accent(nom).split()[0] if nom.split() else ""
            produit_autre = sans_accent(autre_nom).split()[0] if autre_nom.split() else ""
            if produit and produit_autre and produit != produit_autre:
                continue
            jumeaux.append((len(communs) / max(1, len(cherches)), vendu_recent[autre], autre, autre_nom))
        jumeaux.sort(reverse=True)

        cas.append({
            "itm8": code,
            "libelle": nom,
            "vendu_depuis_aout": round(vendu_recent[code], 1),
            "vendu_total": round(vendu_total[code], 1),
            "derniere_vente": derniere_vente[code],
            "livre_colis": livre_colis.get(code, 0),
            "derniere_livraison": derniere_livraison.get(code) or None,
            "deja_relie": code in relies,
            "fournisseur": (overrides.get(code, {}).get("fournisseur") or "").strip(),
            "jumeau": ({"itm8": jumeaux[0][2], "libelle": jumeaux[0][3],
                        "vendu_depuis_aout": round(jumeaux[0][1], 1),
                        "livre_colis": livre_colis.get(jumeaux[0][2], 0)} if jumeaux else None),
        })

    cas.sort(key=lambda c: -c["vendu_depuis_aout"])
    for rang, c in enumerate(cas, 1):
        c["rang"] = rang

    ecrire_json(RACINE / "donnees" / "masques-vendus.json", {"depuis": DEPUIS, "cas": cas})

    print(f"{len(cas)} articles masques qui se vendent encore (depuis le {DEPUIS})\n")
    for c in cas:
        j = c["jumeau"]
        print(f"  {c['rang']:>2}. {c['libelle'][:34]:36} {c['vendu_depuis_aout']:>8} vendu"
              f"   {c['livre_colis']:>4g} colis recus"
              f"   {'RELIE' if c['deja_relie'] else ''}")
        if j:
            print(f"      jumeau possible : {j['libelle'][:34]:36} {j['vendu_depuis_aout']:>8} vendu"
                  f"   {j['livre_colis']:g} colis")


if __name__ == "__main__":
    main()
