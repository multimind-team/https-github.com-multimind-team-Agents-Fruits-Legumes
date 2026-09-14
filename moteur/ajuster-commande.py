"""
Ajuster une quantité de commande — proposer, ou corriger.

Le responsable de rayon, le 2026-09-03 : « J'aimerais que l'agent qui analyse les tendances
modifie ou demande à modifier les commandes en fonction de ses analyses. »

Jusqu'ici l'analyste voyait tout et ne pouvait rien faire : il écrivait « le
raisin part fort, tu vas manquer » et c'était tout. Cet outil lui donne les
deux gestes que le responsable de rayon demande.

DEUX GESTES, PAS UN

  --proposer   L'ajustement s'AFFICHE sur l'écran de commande, à côté de la
               quantité, avec sa raison. Le responsable de rayon voit « 8 colis — l'analyste
               suggère 11 : raisin +130 % » et décide d'un doigt.
               La commande n'est pas changée.

  (sans rien)  L'ajustement est APPLIQUÉ : c'est cette quantité qui s'affiche.
               La quantité d'origine reste visible et le motif aussi.

Lequel des deux ? Ce n'est pas à l'agent de choisir : c'est écrit dans
donnees/pouvoirs.json. Tant qu'un agent n'a pas le droit « commander », il ne
peut que proposer, même s'il est convaincu.

POURQUOI UN FICHIER À PART

Les ajustements vivent dans donnees/ajustements.jsonl, jamais dans
proposition.json. Ce dernier est réécrit en entier à chaque calcul : le
3 septembre 2026, un avertissement écrit dedans a été effacé par un simple
recalcul. Deux programmes n'écrivent pas dans le même fichier.

TROIS GARDE-FOUS

  1. un MOTIF obligatoire, qui dit ce qu'on a vu et ce qu'on en conclut ;
  2. une AMPLITUDE maximale : un agent ne peut pas tripler une commande ;
  3. un NOMBRE d'articles maximal par jour.

Usage :
  python moteur/ajuster-commande.py <article> <colis> --motif "..." --proposer
  python moteur/ajuster-commande.py <article> <colis> --motif "..."
  python moteur/ajuster-commande.py --liste          ce qui est proposé aujourd'hui
  python moteur/ajuster-commande.py --retirer <article> --motif "..."
"""
import argparse
import json
import math
import sys
from datetime import date, datetime
from pathlib import Path

MOTEUR = Path(__file__).resolve().parent
sys.path.insert(0, str(MOTEUR))
import journal_agents

RACINE = MOTEUR.parent
DONNEES = RACINE / "donnees"
FICHIER = DONNEES / "ajustements.jsonl"
PROPOSITION = DONNEES / "proposition.json"
POUVOIRS = DONNEES / "pouvoirs.json"


def proposition():
    if not PROPOSITION.exists():
        sys.exit("Aucune proposition de commande à ajuster.")
    return json.loads(PROPOSITION.read_text(encoding="utf-8"))


def lire(jour=None):
    """Les ajustements du jour. Le dernier écrit sur un article gagne, et un
    retrait est une ligne comme une autre — on n'efface jamais."""
    if not FICHIER.exists():
        return {}
    jour = jour or date.today().isoformat()
    par_article = {}
    with open(FICHIER, encoding="utf-8") as f:
        for ligne in f:
            if not ligne.strip():
                continue
            try:
                a = json.loads(ligne)
            except json.JSONDecodeError:
                continue
            if a.get("date_commande") != jour:
                continue
            if a.get("retire"):
                par_article.pop(a["article"], None)
            else:
                par_article[a["article"]] = a
    return par_article


def pouvoirs(agent):
    reglement = json.loads(POUVOIRS.read_text(encoding="utf-8"))
    profil = reglement.get("agents", {}).get(agent)
    if profil is None:
        sys.exit(f"Agent inconnu : « {agent} ». Ajoute-le dans donnees/pouvoirs.json.")
    return profil, reglement


def verifier(agent, article, avant, apres, applique, jour=None):
    """Le frein à main, version commande. Une quantité, c'est de l'argent."""
    profil, _ = pouvoirs(agent)
    autorisees = profil.get("peut_seul", [])
    tout = "*" in autorisees

    if applique and not tout and "commander" not in autorisees:
        sys.exit(f"REFUSÉ : « {agent} » n'a pas le droit de CHANGER une commande.\n"
                 "Il peut seulement la proposer : relance avec --proposer.\n"
                 "Pour lui accorder ce droit, ajoute « commander » à ses pouvoirs "
                 "dans donnees/pouvoirs.json.")
    if not applique and not tout and not {"commander", "proposer-commande"} & set(autorisees):
        sys.exit(f"REFUSÉ : « {agent} » n'a pas le droit de proposer un ajustement "
                 "de commande.")

    if not math.isfinite(avant) or not math.isfinite(apres):
        sys.exit("REFUSÉ : les quantités avant et après doivent être des nombres finis.")

    limite = profil.get("ajustement_max_pourcent", 30)
    if not tout and avant > 0:
        ecart = abs(apres - avant) / avant * 100
        if ecart > limite:
            sys.exit(f"REFUSÉ : passer de {avant:g} à {apres:g} colis fait "
                     f"{ecart:.0f} % d'écart, au-delà des {limite} % autorisés pour "
                     f"« {agent} ».\nUn écart pareil se discute avec le responsable de rayon, il ne "
                     "se décide pas seul.")
    if not tout and avant == 0 and apres > profil.get("ajustement_max_depuis_zero", 3):
        sys.exit(f"REFUSÉ : l'article n'était pas commandé du tout. « {agent} » ne "
                 f"peut pas en demander plus de {profil.get('ajustement_max_depuis_zero', 3)} "
                 "colis d'un coup.")

    plafond = profil.get("ajustements_max_par_jour", 10)
    deja = len(lire(jour))
    if not tout and deja >= plafond:
        sys.exit(f"REFUSÉ : {deja} article(s) déjà ajustés pour cette commande, c'est le "
                 f"maximum pour « {agent} » ({plafond}).\nAu-delà, ce n'est plus un "
                 "ajustement : c'est un désaccord de fond avec le calcul, et ça se "
                 "dit au responsable de rayon.")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("article", nargs="?")
    p.add_argument("colis", nargs="?", type=float)
    p.add_argument("--motif", help="ce que tu as vu, et ce que tu en conclus")
    p.add_argument("--proposer", action="store_true",
                   help="suggérer sans changer la commande")
    p.add_argument("--retirer", metavar="ARTICLE", help="annuler un ajustement")
    p.add_argument("--liste", action="store_true")
    p.add_argument("--agent", default="agent-tendances")
    args = p.parse_args()

    prop = proposition()
    lignes = {l["itm8"]: l for l in prop["lignes"]}
    jour = prop["date_commande"]
    try:
        if date.fromisoformat(jour).isoformat() != jour:
            raise ValueError
    except (TypeError, ValueError):
        sys.exit("Date de commande invalide : format AAAA-MM-JJ attendu.")

    if args.liste:
        courants = lire(jour)
        if not courants:
            print(f"Aucun ajustement pour la commande du {jour}.")
            return 0
        print(f"Commande du {jour} — {len(courants)} ajustement(s) :\n")
        for code, a in courants.items():
            etat = "APPLIQUÉ" if a["applique"] else "proposé"
            print(f"  {a['libelle'][:34]:36} {a['avant']:>5g} -> {a['apres']:<5g} colis "
                  f"[{etat}]  par {a['agent']}")
            print(f"      {a['motif'][:100]}")
        return 0

    if args.retirer:
        code = args.retirer
        courants = lire(jour)
        if code not in courants:
            sys.exit(f"Aucun ajustement en cours sur {code}.")
        if not args.motif or len(args.motif.strip()) < 20:
            sys.exit("Dis pourquoi tu retires cet ajustement (--motif).")
        # Retirer une commande appliquée la change aussi. Le simple droit de
        # proposer ne suffit donc pas ; les profils de lecture ne retirent rien.
        profil, _ = pouvoirs(args.agent)
        autorisees = set(profil.get("peut_seul", []))
        requis = {"commander"} if courants[code].get("applique") else {"commander", "proposer-commande"}
        if "*" not in autorisees and not autorisees & requis:
            sys.exit(f"REFUSÉ : « {args.agent} » n'a pas le droit de retirer cet ajustement.")
        with open(FICHIER, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "date_commande": jour, "article": code, "retire": True,
                "motif": args.motif.strip(), "agent": args.agent,
                "enregistre_le": datetime.now().isoformat(timespec="seconds"),
            }, ensure_ascii=False) + "\n")
        print(f"Ajustement retiré sur {courants[code]['libelle']}.")
        return 0

    if not args.article or args.colis is None:
        p.print_help()
        return 1
    if not args.motif or len(args.motif.strip()) < 30:
        sys.exit("Motif trop court. Dis ce que tu as VU (les chiffres) et ce que tu "
                 "en CONCLUS. Le responsable de rayon doit pouvoir juger sans rouvrir les données.")

    ligne = lignes.get(args.article)
    if not ligne:
        sys.exit(f"L'article {args.article} n'est pas dans la commande du {jour}.")
    if ligne.get("promotion"):
        sys.exit("Cet article est en promotion : il est précommandé par le chef de "
                 "rayon, on n'y touche pas en quotidien.")

    avant = float(ligne["propose_colis"])
    apres = round(args.colis, 2)
    if apres < 0:
        sys.exit("Une commande ne peut pas être négative.")
    if apres == avant:
        sys.exit(f"C'est déjà la quantité proposée ({avant:g} colis). Rien à faire.")

    applique = not args.proposer
    verifier(args.agent, args.article, avant, apres, applique, jour=jour)

    numero = journal_agents.numero_action()
    enregistrement = {
        "date_commande": jour,
        "article": args.article,
        "libelle": ligne["libelle"],
        "avant": avant,
        "apres": apres,
        "applique": applique,
        "motif": args.motif.strip(),
        "agent": args.agent,
        "action": numero,
        "enregistre_le": datetime.now().isoformat(timespec="seconds"),
    }
    FICHIER.parent.mkdir(parents=True, exist_ok=True)
    with open(FICHIER, "a", encoding="utf-8") as f:
        f.write(json.dumps(enregistrement, ensure_ascii=False, allow_nan=False) + "\n")

    journal_agents.enregistrer(
        agent=args.agent, action=numero,
        message=(f"{'Commande ajustée' if applique else 'Ajustement proposé'} : "
                 f"{ligne['libelle']} {avant:g} -> {apres:g} colis"),
        motif=args.motif.strip(),
        changements=[{"itm8": args.article, "champ": "commande",
                      "avant": avant, "apres": apres}],
        annulable=False,       # se défait avec --retirer, pas avec annuler.py
        details={"date_commande": jour, "applique": applique})

    ecart = f"{(apres - avant) / avant * 100:+.0f} %" if avant else "nouvel article"
    print(f"{'APPLIQUÉ' if applique else 'PROPOSÉ'} — {ligne['libelle']}")
    print(f"  {avant:g} -> {apres:g} colis  ({ecart})")
    print(f"  action {numero}")
    if applique:
        print("\n  L'écran de commande affiche cette quantité, avec la quantité")
        print("  d'origine et ton motif juste en dessous.")
    else:
        print("\n  L'écran de commande garde la quantité calculée et affiche ta")
        print("  suggestion à côté. Le responsable de rayon l'accepte d'un doigt, ou l'ignore.")
    print(f"  Pour revenir en arrière : python moteur/ajuster-commande.py "
          f"--retirer {args.article} --motif \"...\"")
    return 0


if __name__ == "__main__":
    sys.exit(main())
