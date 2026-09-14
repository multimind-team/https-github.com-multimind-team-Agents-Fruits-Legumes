"""
Cherche les articles livrés sous un code, mais vendus sous un autre.

C'est le défaut le plus coûteux du rayon : un article reçoit de la marchandise
sous un code qui n'est jamais passé en caisse, pendant que le code réellement
vendu ne reçoit jamais rien. Résultat : une position qui descend sans fin d'un
côté, une marchandise invisible de l'autre — et une commande gonflée pour rien.

Le melon, le citron vrac, les bananes et le haricot coco ont tous été trouvés
comme ça, un par un. Ce script les cherche tous d'un coup.

Il ne décide rien : il prépare de quoi trancher en dix secondes par article.

LECTURE SEULE.
"""
import json
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

VIDES = {"vrac", "piece", "pieces", "kg", "france", "petit", "prix", "itm", "mmp",
         "de", "du", "la", "le", "les", "a", "en", "et", "cat", "import", "1", "2"}


def sans_accent(t):
    return "".join(c for c in unicodedata.normalize("NFD", t or "")
                   if unicodedata.category(c) != "Mn").lower()


def mots(t):
    return {m for m in re.split(r"[^a-z0-9]+", sans_accent(t)) if m and m not in VIDES and len(m) > 1}


def main():
    aggregats = agregats.charger()
    config = regles.charger()
    masques = {k for k, v in config.get("overrides", {}).items() if v.get("masque")}
    groupes = config.get("groupes", {})
    deja_relies = set(groupes) | {m for ms in groupes.values() for m in ms}
    libelles = {str(a["CODE ITM"]): (a.get("LIBELLE") or "").strip()
                for a in list(catalogue.articles().values()) if a.get("CODE ITM")}

    # Ce que chaque code a reçu et vendu, sur toute la période connue
    livre = defaultdict(float)
    livre_colis = defaultdict(float)
    vendu = defaultdict(float)
    derniere_vente = {}
    # Un code absent du cadencier Mercalys n'a pas de libelle -- mais le fichier
    # de livraison, lui, en porte un. Sans ca, 6 cas sur 9 restaient anonymes.
    libelles_livraison = {}
    import faits
    for fait in faits.lire(DOSSIER_FAITS):
        code = fait["article_source"]
        if fait["type"] == "livraison":
            livre[code] += fait["quantite"]
            livre_colis[code] += fait.get("colis") or 0
            if fait.get("libelle"):
                libelles_livraison.setdefault(code, fait["libelle"].strip())
        elif fait["type"] == "vente":
            vendu[code] += fait["quantite"]
            jour = fait["date_source"]
            if jour > derniere_vente.get(code, ""):
                derniere_vente[code] = jour

    # Les suspects : livrés, mais jamais (ou presque) vendus
    suspects = [c for c in livre
                if livre_colis[c] >= 1 and vendu.get(c, 0) <= 1 and c not in deja_relies]

    print(f"{len(suspects)} article(s) recoivent de la marchandise sans jamais etre vendus.\n")
    print("Pour chacun : le code le plus probable sous lequel il est reellement vendu.\n")

    # Cas connu, documente : les oranges de la machine a jus ne passent JAMAIS
    # en caisse (elles partent a la presse). Ce n'est pas un code jumeau.
    ORANGE_MACHINE_A_JUS = "0000087004386"

    for code in sorted(suspects, key=lambda c: -livre_colis[c]):
        if code == ORANGE_MACHINE_A_JUS:
            continue
        nom = libelles.get(code) or libelles_livraison.get(code) or code
        cherches = mots(nom)
        if not cherches:
            continue

        # Un bon jumeau : libellé proche, bien vendu, et lui jamais livré.
        candidats = []
        for autre, autre_nom in libelles.items():
            if autre == code or autre in deja_relies or autre in masques:
                continue
            if vendu.get(autre, 0) < 10:
                continue
            mots_autre = mots(autre_nom)
            communs = cherches & mots_autre
            if not communs:
                continue
            # Le premier mot d'un libelle est le produit (COURGETTE, RADIS...).
            # Sans lui en commun, un "rouge" partage ne veut rien dire : le
            # radis rouge n'est pas le poivron rouge.
            produit = sans_accent(nom).split()[0] if nom.split() else ""
            produit_autre = sans_accent(autre_nom).split()[0] if autre_nom.split() else ""
            if produit and produit_autre and produit != produit_autre:
                continue
            part = len(communs) / len(cherches)
            jamais_livre = livre_colis.get(autre, 0) == 0
            candidats.append((part, jamais_livre, vendu[autre], autre, autre_nom))
        candidats.sort(reverse=True)

        print(f"  {'='*66}")
        origine = "" if libelles.get(code) else "  (libelle lu sur le bon de livraison)"
        print(f"  LIVRE   {nom[:44]:46} {code}{origine}")
        print(f"          {livre_colis[code]:g} colis recus ({livre[code]:g} unites), "
              f"{vendu.get(code,0):g} vendu")
        if not candidats:
            print("  VENDU   aucun candidat trouve — a regarder a la main")
            continue
        for part, jamais, qte, autre, autre_nom in candidats[:2]:
            marque = "  <-- probablement celui-la" if (part >= 0.5 and jamais) else ""
            print(f"  VENDU ? {autre_nom[:44]:46} {autre}")
            print(f"          {qte:g} vendu, {livre_colis.get(autre,0):g} colis recus"
                  f"{'  (JAMAIS livre)' if jamais else ''}{marque}")


if __name__ == "__main__":
    main()
