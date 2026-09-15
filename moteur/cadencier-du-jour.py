"""
Le cadencier du jour — la liste de ce qu'on peut commander AUJOURD'HUI.

Le responsable de rayon, le 2026-09-03 :

  « Le cadencier Webtelevente référence ce que je peux commander. Si un article
    n'est pas disponible, ce n'est pas la peine de me le proposer en commande. »

  « Je ne veux pas que tu prennes le cadencier Mercalys dans l'app mais le
    cadencier Webtelevente. J'ai l'impression que tu prends Mercalys et que tu
    retires tout ce que tu ne trouves pas dans Webtelevente : c'est une très
    mauvaise idée, tu risques de masquer un produit par erreur. De plus la liste
    doit être revue tous les jours : la sucrine X3 n'est pas dispo aujourd'hui
    mais le sera peut-être demain. »

DEUX CHOSES À NE PAS CONFONDRE

  masqué       = une DÉCISION durable du responsable de rayon : « je ne veux plus le
                 commander pour l'instant ». Elle vit dans le carnet des
                 décisions, elle a un motif, elle s'annule.

  indisponible = un ÉTAT DU JOUR : le fournisseur ne le propose pas ce matin.
                 Ça change tous les jours, ça ne se décide pas, et ça ne laisse
                 aucune trace dans les décisions.

Traiter la seconde comme la première ferait disparaître des articles pour de
bon à cause d'une rupture d'une journée. On ne masque donc JAMAIS un article
parce qu'il manque au cadencier du jour.

LE SENS DE LECTURE

On part du cadencier Webtelevente — c'est lui la liste — et on cherche ensuite
le code de chaque article pour retrouver son historique. Si on ne le trouve
pas, l'article reste dans la liste : il est commandable, c'est tout ce qui
compte. On dit simplement qu'on ne sait rien de ses ventes.

Jamais l'inverse. Partir de Mercalys et retirer ce qu'on ne retrouve pas
reviendrait à effacer par ignorance.

Usage :
  python moteur/cadencier-du-jour.py                le dernier cadencier reçu
  python moteur/cadencier-du-jour.py <fichier.xls>  un cadencier précis
  python moteur/cadencier-du-jour.py --resume       ce qu'on en sait
"""
import argparse
import json
from ecriture_derivee import ecrire_json
import re
import sys
from datetime import datetime
from pathlib import Path

MOTEUR = Path(__file__).resolve().parent
sys.path.insert(0, str(MOTEUR))
import catalogue
import journal_agents

RACINE = MOTEUR.parent
DONNEES = RACINE / "donnees"
FICHIER = DONNEES / "cadencier-du-jour.json"

# Une ligne indentée est une OFFRE du fournisseur, pas un article du magasin.
COLONNE_NOM = 0
COLONNE_PCB = 3
COLONNE_PRIX = 4
COLONNE_PVC = 6

# Les intitulés de section, qui ne sont ni des articles ni des offres.
SECTIONS = {"GAMME PERMANENTE", "GAMME COMPLEMENTAIRE", "GAMME COMPLÉMENTAIRE",
            "FRUITS", "LEGUMES", "LÉGUMES", "BIO", "4EME GAMME", "4ÈME GAMME"}


def groupe_de_ligne(ligne):
    """Lit les séparateurs Fruits/Légumes/Bio du cadencier Webtelevente.

    Dans le fichier fournisseur ils sont en colonne B, alors que les articles
    sont en colonne A. Cette information est donc conservée avec chaque article
    pour pouvoir présenter Fruits non bio, Légumes non bio, puis Bio sans
    toucher à l'ordre relatif de la tablette.
    """
    valeurs = {str(valeur or "").strip().upper() for valeur in ligne[:2]}
    if "BIO" in valeurs:
        return "bio"
    if "FRUITS" in valeurs:
        return "fruits"
    if "LEGUMES" in valeurs or "LÉGUMES" in valeurs:
        return "legumes"
    return None


def cle(texte):
    """Une clé de rapprochement tolérante : on ignore la ponctuation, les
    espaces et la casse. Deux libellés qui ne diffèrent que par un tiret ou un
    accent doivent se retrouver."""
    texte = (texte or "").upper()
    for avant, apres in (("É", "E"), ("È", "E"), ("Ê", "E"), ("À", "A"), ("Ç", "C")):
        texte = texte.replace(avant, apres)
    return re.sub(r"[^A-Z0-9]", "", texte)


def lire_cadencier(chemin):
    """Rend la liste des articles DISPONIBLES, dans l'ordre du fichier.

    Un article a une ligne à lui (sans indentation) ; les lignes indentées en
    dessous sont les offres du fournisseur. Pas d'offre = pas disponible
    aujourd'hui, et l'article n'entre pas dans la liste.
    """
    if chemin.suffix.lower() == ".xls":
        import xlrd
        feuille = xlrd.open_workbook(str(chemin)).sheet_by_index(0)
        lignes = [[feuille.cell_value(r, c) for c in range(feuille.ncols)]
                  for r in range(feuille.nrows)]
    else:
        import openpyxl
        classeur = openpyxl.load_workbook(chemin, read_only=True, data_only=True)
        lignes = [list(r) for r in classeur.active.iter_rows(values_only=True)]
        classeur.close()

    date_cadencier = None
    groupe_courant = None
    articles, courant = [], None
    for ligne in lignes:
        brut = str(ligne[COLONNE_NOM] or "")
        nom = brut.strip()
        groupe = groupe_de_ligne(ligne)
        if groupe:
            groupe_courant = groupe
            continue
        if not nom:
            continue
        if date_cadencier is None:
            m = re.search(r"CADENCIER DU (\d{2})/(\d{2})/(\d{4})", nom.upper())
            if m:
                date_cadencier = f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
                continue
        if nom.upper() in SECTIONS or nom.upper().startswith("CADENCIER DU"):
            continue

        if not brut.startswith("  "):
            courant = {"nom": nom, "rang": len(articles), "offres": [],
                       "groupe": groupe_courant or "inconnu"}
            articles.append(courant)
        elif courant is not None:
            pcb = ligne[COLONNE_PCB] if len(ligne) > COLONNE_PCB else None
            if pcb in (None, ""):
                continue          # une ligne indentée sans colisage n'est pas une offre
            courant["offres"].append({
                "libelle": nom,
                "par_colis": float(pcb) if str(pcb).replace(".", "").isdigit() else pcb,
                "prix_achat": ligne[COLONNE_PRIX] if len(ligne) > COLONNE_PRIX else None,
                "prix_vente_conseille": ligne[COLONNE_PVC] if len(ligne) > COLONNE_PVC else None,
            })

    # Seuls les articles qui ont au moins une offre sont commandables aujourd'hui.
    disponibles = [a for a in articles if a["offres"]]
    for rang, a in enumerate(disponibles):
        a["rang"] = rang          # l'ordre de la tablette, une fois les vides retirés
    return date_cadencier, disponibles, [a["nom"] for a in articles if not a["offres"]]


def rapprocher(disponibles):
    """Retrouve le code de chaque article, pour aller chercher son historique.

    Un article qu'on ne sait pas rapprocher RESTE dans la liste : il est
    commandable, c'est ce qui compte. On dit seulement qu'on ne connaît pas son
    passé, et l'agent ira voir.
    """
    noms = catalogue.noms()
    par_cle = {}
    for code, nom in noms.items():
        k = cle(nom)
        if k:
            par_cle.setdefault(k, []).append(code)

    import regles
    config = regles.charger()
    groupes = config.get("groupes", {})
    vers_principal = {m: p for p, ms in groupes.items() for m in ms}

    rapproches = ambigus = inconnus = 0
    for a in disponibles:
        k = cle(a["nom"])
        codes = par_cle.get(k)
        if not codes:
            # Le libellé du magasin est souvent tronqué (30 caractères) :
            # on accepte qu'il soit le début du nom du cadencier.
            codes = [c for kk, lst in par_cle.items()
                     if len(kk) >= 14 and k.startswith(kk) for c in lst]
            # Le suffixe BIO n'est pas un détail de libellé : sinon l'article
            # bio hérite du stock et de la commande de son homonyme conventionnel.
            bio = bool(re.search(r"\bBIO\b", a["nom"], re.IGNORECASE))
            codes = [c for c in codes
                     if bool(re.search(r"\bBIO\b", noms[c], re.IGNORECASE)) == bio]
        if not codes:
            a["article"] = None
            a["rapprochement"] = "inconnu"
            inconnus += 1
        elif len(codes) == 1:
            a["article"] = codes[0]
            a["rapprochement"] = "sûr"
            rapproches += 1
        else:
            principaux = {vers_principal.get(c, c) for c in codes}
            if len(principaux) == 1:
                a["article"] = list(principaux)[0]
                a["rapprochement"] = "sûr"
                rapproches += 1
            else:
                a["article"] = None
                a["candidats"] = codes
                a["rapprochement"] = "ambigu"
                ambigus += 1
    return rapproches, ambigus, inconnus


def date_du_nom(chemin):
    """La date écrite dans le nom du fichier, pas celle du dossier : les mails
    n'arrivent pas dans l'ordre — celui du 02/09 est arrivé après celui du 03."""
    m = re.search(r"(\d{2})[.\-](\d{2})[.\-](\d{4})", chemin.name)
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else ""


def dernier_cadencier(dossier_courrier=None):
    """Trouve le dernier cadencier Webtelevente, quel que soit son séparateur."""
    dossier_courrier = Path(dossier_courrier or DONNEES / "courrier")
    fichiers = [
        fichier for fichier in dossier_courrier.rglob("*.xls*")
        if re.match(r"^cadencier[-_ ]+webtelevente(?:[-_ ]|$)", fichier.name, re.IGNORECASE)
    ]
    if not fichiers:
        sys.exit("Aucun cadencier Webtelevente reçu. L'agent orchestrateur doit d'abord relever les mails "
                 "et ranger les pièces jointes utiles.")
    return max(fichiers, key=lambda f: (date_du_nom(f), f.stat().st_mtime))


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("fichier", nargs="?")
    p.add_argument("--resume", action="store_true")
    args = p.parse_args()

    if args.resume:
        if not FICHIER.exists():
            sys.exit("Aucun cadencier du jour enregistré.")
        c = json.loads(FICHIER.read_text(encoding="utf-8"))
        print(f"Cadencier du {c['date_cadencier']} — {len(c['articles'])} articles commandables")
        print(f"  rapprochés : {c['rapprochement']['surs']} · "
              f"ambigus : {c['rapprochement']['ambigus']} · "
              f"inconnus : {c['rapprochement']['inconnus']}")
        print(f"  indisponibles ce jour-là : {len(c['indisponibles'])}")
        return 0

    chemin = Path(args.fichier) if args.fichier else dernier_cadencier()
    date_cadencier, disponibles, indisponibles = lire_cadencier(chemin)
    surs, ambigus, inconnus = rapprocher(disponibles)

    contenu = {
        "_lisez_moi": ("Ce qu'on peut commander AUJOURD'HUI, dans l'ordre de la "
                       "tablette. Refait a chaque cadencier recu : un article "
                       "absent aujourd'hui peut revenir demain, il n'est jamais "
                       "masque pour autant."),
        "date_cadencier": date_cadencier,
        "fichier": chemin.name,
        "lu_le": datetime.now().isoformat(timespec="seconds"),
        "rapprochement": {"surs": surs, "ambigus": ambigus, "inconnus": inconnus},
        "articles": disponibles,
        "indisponibles": indisponibles,
    }
    ecrire_json(FICHIER, contenu)

    print(f"Cadencier Webtelevente du {date_cadencier}  ({chemin.name})")
    print(f"  {len(disponibles)} articles commandables aujourd'hui")
    print(f"  {len(indisponibles)} articles listés mais SANS offre — pas commandables ce jour")
    print()
    print(f"  Rapprochement avec ce que le magasin connaît :")
    print(f"    sûr     : {surs}")
    print(f"    ambigu  : {ambigus}   (plusieurs codes possibles)")
    print(f"    inconnu : {inconnus}   (commandable, mais aucun historique)")
    if inconnus:
        print("\n  Les articles sans historique restent proposables : ils sont")
        print("  commandables, c'est ce qui compte. L'agent doit juste dire qu'on")
        print("  ne sait rien de leurs ventes.")

    journal_agents.enregistrer(
        agent="agent-donnees",
        message=f"Cadencier du jour lu : {len(disponibles)} articles commandables",
        motif=("Le cadencier Webtelevente dit ce qu'on peut commander aujourd'hui. "
               "Un article absent n'est pas masque : il sera peut-etre la demain."),
        annulable=False,
        details={"date_cadencier": date_cadencier, "fichier": chemin.name,
                 "commandables": len(disponibles), "sans_offre": len(indisponibles),
                 "rapprochement": contenu["rapprochement"]})
    return 0


if __name__ == "__main__":
    sys.exit(main())
