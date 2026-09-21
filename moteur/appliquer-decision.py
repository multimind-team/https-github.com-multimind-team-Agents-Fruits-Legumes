"""
Applique une décision sur les articles — dans les carnets de preparation-commande.

Une décision s'inscrit ici, et nulle part ailleurs :

  - donnees/decisions.jsonl        le carnet vivant, une ligne par décision,
                                   jamais effacée, toujours datée et expliquée ;
  - donnees/journaux/<agent>.jsonl le journal de l'agent, avec l'avant et
                                   l'après de chaque changement, ce qui rend la
                                   marche arrière possible (voir annuler.py).

Cet outil remplace les scripts jetables écrits un par un le 2 septembre 2026
(melon.py, bananes_ruban.py, pdt_frite.py...). C'est lui que les agents
appellent : ils décident, il exécute.

Deux conditions à toute décision :
  1. un MOTIF — sans pourquoi, pas de changement ;
  2. le DROIT de la prendre — donnees/pouvoirs.json dit qui peut quoi, et
     l'outil refuse le reste, même à un agent convaincu d'avoir raison.

Usage :
  python moteur/appliquer-decision.py rapprocher <principal> <membre> --motif "..."
  python moteur/appliquer-decision.py demasquer   <article>            --motif "..."
  python moteur/appliquer-decision.py masquer     <article>            --motif "..."
  python moteur/appliquer-decision.py promotion   <article> <oui|non>  --motif "..."
  python moteur/appliquer-decision.py conditionnement <article> <n>    --motif "..."
  python moteur/appliquer-decision.py fournisseur <article> <nom>      --motif "..."

Ajouter --simuler pour voir ce qui serait fait, sans rien écrire.

Un article du cadencier Webtelevente sans code connu (rapprochement "inconnu"
ou "ambigu" dans cadencier-du-jour.py) ne peut pas être masqué par code : il
n'en a pas. Utiliser "nom:<NOM EXACT DU CADENCIER>" comme <article> à la
place — generer-proposition.py sait lire cette forme (décidé le 2026-09-04).
"""
import argparse
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import journal_agents as carnet_agents
import catalogue
import regles
from verrou_donnees import append_jsonl

RACINE = Path(__file__).resolve().parent.parent
DECISIONS = RACINE / "donnees" / "decisions.jsonl"
POUVOIRS = RACINE / "donnees" / "pouvoirs.json"


def verifier_pouvoirs(agent, action):
    """Même garde-fou pour appliquer et annuler, sur le rôle déclaré."""
    carnet_agents.verifier_pouvoirs(agent, [action], POUVOIRS)


def libelles():
    """Les noms des articles, pris dans le catalogue de preparation-commande."""
    return catalogue.noms()


def ecrire_decision(ligne):
    """Le carnet vivant : on ajoute, on n'efface jamais, on ne réécrit jamais."""
    append_jsonl(DECISIONS, [ligne])


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("action", choices=["rapprocher", "demasquer", "masquer", "promotion",
                                      "conditionnement", "fournisseur", "unite"])
    p.add_argument("article")
    p.add_argument("valeur", nargs="?")
    p.add_argument("--motif", required=True,
                   help="POURQUOI ce changement. Obligatoire : une décision sans motif "
                        "ne permet pas de reconstituer les faits plus tard.")
    p.add_argument("--auteur", default="agent-rayon")
    p.add_argument("--simuler", action="store_true")
    args = p.parse_args()
    if args.simuler:
        return executer(args)
    with carnet_agents.verrou():
        return executer(args)


def executer(args):
    if len(args.motif.strip()) < 30:
        sys.exit("Motif trop court. Explique la cause ET la conséquence, pas seulement l'action.")

    # Les pouvoirs se vérifient avant tout, y compris avant une simulation :
    # un agent doit se heurter au mur au moment où il essaie, pas après.
    verifier_pouvoirs(args.auteur, args.action)

    noms = libelles()
    nom = noms.get(args.article, args.article)
    avant_tout = regles.charger()          # l'état d'avant, reconstitué
    surcharge = avant_tout["overrides"].get(args.article, {})
    aujourdhui = date.today().isoformat()
    changements = []
    lignes = []                            # les décisions à écrire

    def decider(type_decision, article, valeur=None, membres=None):
        ligne = {

            "type": type_decision,
            "article": article,
            "valide_a_partir_de": aujourdhui,
            "motif": args.motif,
            "auteur": args.auteur,
            "enregistre_le": datetime.now().isoformat(timespec="seconds"),
        }
        if membres is not None:
            ligne["principal"] = article
            ligne["membres"] = membres
        if valeur is not None:
            ligne["valeur"] = valeur
        lignes.append(ligne)
        return ligne

    if args.action == "rapprocher":
        if not args.valeur:
            sys.exit("Il faut le code du membre à rapprocher.")
        membre = args.valeur
        # Le membre ne doit pas rester dans un autre groupe : le groupe qui le
        # perd est réécrit en entier, avec ses deux listes complètes — c'est la
        # seule forme qu'annuler.py sait remettre en place.
        for principal, liste in list(avant_tout["groupes"].items()):
            if membre in liste and principal != args.article:
                reste = [m for m in liste if m != membre]
                decider("fusion", principal, membres=reste)
                changements.append({"itm8": principal, "champ": "groupes",
                                    "avant": list(liste), "apres": reste})
        avant = avant_tout["groupes"].get(args.article, [])
        apres = sorted(set(avant + [membre]))
        decider("fusion", args.article, membres=apres)
        changements.append({"itm8": args.article, "champ": "groupes",
                            "avant": avant, "apres": apres})
        # Un membre ne doit pas faire une ligne de commande à part.
        avant_masque = avant_tout["overrides"].get(membre, {}).get("masque")
        if not avant_masque:
            decider("masquage", membre, valeur=True)
            changements.append({"itm8": membre, "champ": "masque",
                                "avant": avant_masque, "apres": True})
        resume = f"{nom} (principal) <- {noms.get(membre, membre)}"

    elif args.action in ("demasquer", "masquer"):
        avant = surcharge.get("masque")
        masquer = args.action == "masquer"
        decider("masquage" if masquer else "demasquage", args.article,
                valeur=True if masquer else None)
        changements.append({"itm8": args.article, "champ": "masque",
                            "avant": avant, "apres": True if masquer else None})
        resume = f"{nom} : {args.action}"

    elif args.action == "promotion":
        actif = (args.valeur or "oui").lower() in ("oui", "true", "1")
        avant = surcharge.get("promotion")
        decider("promotion", args.article, valeur=True if actif else None)
        changements.append({"itm8": args.article, "champ": "promotion",
                            "avant": avant, "apres": True if actif else None})
        # Un article en promotion est précommandé par le chef de rayon : il doit
        # rester visible, jamais commandé en quotidien (règle du responsable de rayon).
        if actif and surcharge.get("masque"):
            decider("demasquage", args.article)
            changements.append({"itm8": args.article, "champ": "masque",
                                "avant": True, "apres": None})
        resume = f"{nom} : promotion {'activée' if actif else 'retirée'}"

    elif args.action == "conditionnement":
        if not args.valeur:
            sys.exit("Il faut le nombre d'unités par colis.")
        avant = surcharge.get("conditionnement")
        decider("conditionnement", args.article, valeur=str(args.valeur))
        changements.append({"itm8": args.article, "champ": "conditionnement",
                            "avant": avant, "apres": str(args.valeur)})
        resume = f"{nom} : colis de {args.valeur}"

    elif args.action == "fournisseur":
        if not args.valeur:
            sys.exit("Il faut le nom du fournisseur.")
        avant = surcharge.get("fournisseur")
        decider("fournisseur", args.article, valeur=args.valeur)
        changements.append({"itm8": args.article, "champ": "fournisseur",
                            "avant": avant, "apres": args.valeur})
        resume = f"{nom} : fournisseur {args.valeur}"

    elif args.action == "unite":
        if not args.valeur:
            sys.exit("Il faut l'unité de vente (ex: barquette, kg, pièce).")
        avant = surcharge.get("unite")
        decider("unite", args.article, valeur=str(args.valeur))
        changements.append({"itm8": args.article, "champ": "unite",
                            "avant": avant, "apres": str(args.valeur)})
        resume = f"{nom} : unité {args.valeur}"

    if args.simuler:
        print("SIMULATION — rien n'a été écrit\n")
        print(" ", resume)
        for c in changements:
            print("   ", c)
        return

    # Le numéro est réservé AVANT d'écrire quoi que ce soit : si ça casse en
    # cours de route, l'échec porte le même numéro et on sait où chercher.
    numero = carnet_agents.numero_action()
    try:
        for indice, ligne in enumerate(lignes):
            ligne["id"] = f"{ligne['type']}:{ligne['article']}:{numero}:{indice}"
            ligne["action"] = numero
            ecrire_decision(ligne)
        carnet_agents.enregistrer(
            agent=args.auteur, action=numero, message=resume, motif=args.motif,
            changements=changements,
            details={"decisions": [l["id"] for l in lignes],
                     "commande": " ".join(sys.argv[1:])},
        )
    except Exception as erreur:
        carnet_agents.echec(args.auteur, f"Échec : {resume}", erreur,
                            action=numero, details={"changements": changements})
        raise

    print(resume)
    for c in changements:
        print("   ", c)
    print(f"\n  numéro d'action : {numero}")
    print(f"  carnet vivant   : {len(lignes)} ligne(s) ajoutée(s)")
    print(f"  journal         : {args.auteur}")
    print(f"\n  Pour défaire : python moteur/annuler.py {numero} --par {args.auteur}")
    print( "  Penser à relancer : calculer-position.py, preparer-liste-comptage.py")


if __name__ == "__main__":
    main()
