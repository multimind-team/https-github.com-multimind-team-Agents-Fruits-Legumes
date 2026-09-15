"""
La marche arrière — défaire ce qu'un agent a fait.

Les agents sont autonomes : ils décident et ils appliquent. La contrepartie,
c'est que le responsable de rayon doit pouvoir dire « celle-là, non » et que ce soit défait en
dix secondes, sans rien comprendre à l'informatique.

Usage :
  python moteur/annuler.py --liste              les dernières actions
  python moteur/annuler.py --liste agent-donnees  celles d'un seul agent
  python moteur/annuler.py A-20260902-0007 --par <executant>
  python moteur/annuler.py --dernier --par <executant>
  ... avec --simuler pour voir sans rien changer

On n'efface jamais la ligne d'origine : annuler, c'est remettre les valeurs
d'avant et écrire une nouvelle ligne qui dit ce qu'on a remis, et pourquoi.
"""
import argparse
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import journal_agents as journal
import catalogue
import regles
from verrou_donnees import append_jsonl

RACINE = Path(__file__).resolve().parent.parent
DECISIONS = RACINE / "donnees" / "decisions.jsonl"
POUVOIRS = RACINE / "donnees" / "pouvoirs.json"

ABSENT = object()   # « ce champ n'existait pas avant » : il faudra l'effacer.


def libelles():
    """Les noms des articles, pris dans le catalogue de preparation-commande."""
    return catalogue.noms()


def lister(agent, limite):
    lignes = journal.lire(agent)
    deja = journal.actions_annulees()
    if not lignes:
        print(f"Aucune action enregistrée pour « {agent} ».")
        return
    print(f"{'numéro':<18} {'quand':<12} {'agent':<18} état      quoi")
    print("-" * 100)
    for l in lignes[-limite:]:
        heure = l["horodatage"][5:16].replace("T", " ")
        if l.get("resultat") == "echec":
            etat = "ECHEC"
        elif l["action"] in deja:
            etat = "annulée"
        elif l.get("annule_action"):
            etat = "annulation"
        elif l.get("annulable"):
            etat = "annulable"
        else:
            etat = "-"
        print(f"{l['action']:<18} {heure:<12} {l['agent']:<18} {etat:<9} {l['message'][:52]}")
    print("\nPour défaire :  python moteur/annuler.py <numéro> --par <executant>")


def valeur_actuelle(cfg, chg):
    if chg["champ"] == "groupes":
        return cfg.get("groupes", {}).get(chg["itm8"], ABSENT)
    return cfg.get("overrides", {}).get(chg["itm8"], {}).get(chg["champ"], ABSENT)


# Champ de réglage -> type de décision à écrire pour revenir en arrière.
TYPE_POUR_CHAMP = {"conditionnement": "conditionnement", "fournisseur": "fournisseur",
                   "unite": "unite", "promotion": "promotion"}


def decisions_inverses(cible, changements, numero, motif, par):
    """Annuler, c'est ajouter des lignes qui remettent les valeurs d'avant.

    On ne retire jamais une ligne du carnet : celle d'origine reste, avec son
    motif, et on écrit par-dessus ce qu'il faut pour revenir à l'état
    précédent. L'historique raconte alors ce qui s'est vraiment passé —
    y compris l'erreur et sa correction.
    """
    ecrites = []
    horodatage = datetime.now()
    for chg in changements:
        avant, champ = chg.get("avant"), chg["champ"]
        commun = {
            "action": numero,
            "annule": cible["action"],
            "valide_a_partir_de": date.today().isoformat(),
            "motif": motif,
            "auteur": par,
            "enregistre_le": horodatage.isoformat(timespec="seconds"),
        }
        if champ == "groupes":
            ligne = dict(commun, type="fusion", article=chg["itm8"],
                         principal=chg["itm8"], membres=avant or [])
        elif champ == "masque":
            ligne = dict(commun, article=chg["itm8"],
                         **({"type": "masquage", "valeur": True} if avant
                            else {"type": "demasquage"}))
        else:
            type_decision = TYPE_POUR_CHAMP.get(champ)
            if not type_decision:
                raise ValueError(f"Inverse non pris en charge : {champ}")
            ligne = dict(commun, type=type_decision, article=chg["itm8"])
            if avant is not None:
                ligne["valeur"] = avant
            else:
                # Pas de valeur d'avant : le réglage n'existait pas, on le retire.
                ligne["valeur"] = None
        ligne["id"] = f"{ligne['type']}:{chg['itm8']}:{numero}:{len(ecrites)}"
        ecrites.append(ligne)
    return ecrites


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("numero", nargs="?", help="le numéro de l'action à annuler")
    p.add_argument("--liste", nargs="?", const="tout", metavar="AGENT",
                   help="afficher les dernières actions")
    p.add_argument("--dernier", action="store_true",
                   help="annuler la dernière action annulable")
    p.add_argument("--limite", type=int, default=25)
    p.add_argument("--motif", default=None)
    p.add_argument("--par", help="exécutant déclaré (obligatoire pour annuler)")
    p.add_argument("--simuler", action="store_true")
    args = p.parse_args()

    if args.liste:
        lister(args.liste, args.limite)
        return

    if not args.numero and not args.dernier:
        p.print_help()
        return 1
    if args.simuler:
        return executer(args)
    with journal.verrou():
        return executer(args)


def executer(args):
    if not args.par:
        sys.exit("REFUSÉ : précise l’exécutant avec --par ; aucun rôle responsable par défaut.")

    # Le dernier statut fait foi, pas un ancien événement « ok ».
    lignes = list({l["action"]: l for l in journal.lire("tout")}.values())
    deja = journal.actions_annulees()

    if args.dernier:
        candidates = [l for l in lignes
                      if l.get("annulable") and l["action"] not in deja
                      and not l.get("annule_action")]
        if not candidates:
            sys.exit("Rien à annuler : aucune action annulable en attente.")
        cible = candidates[-1]
    elif args.numero:
        trouvees = [l for l in lignes if l["action"] == args.numero]
        if not trouvees:
            sys.exit(f"Numéro inconnu : {args.numero}. "
                     "Voir la liste avec : python moteur/annuler.py --liste")
        cible = trouvees[-1]
    else:
        sys.exit("REFUSÉ : indique une action ou --dernier.")

    if cible["action"] in deja:
        sys.exit(f"{cible['action']} a déjà été annulée. Rien à faire.")
    if cible.get("resultat") != "ok" or not cible.get("annulable"):
        sys.exit(f"{cible['action']} n'est pas annulable automatiquement "
                 f"(« {cible['message']} »). Elle n'a rien changé dans la "
                 "configuration, ou elle a touché autre chose que les réglages "
                 "d'articles. À défaire à la main.")

    noms = libelles()
    cfg = regles.charger()
    changements = cible.get("changements", [])
    if not changements or any(
            c.get("champ") not in journal.CHAMPS_RESTAURABLES or not c.get("itm8")
            or "avant" not in c or "apres" not in c for c in changements):
        sys.exit("REFUSÉ : aucun inverse complet pris en charge ; action non annulable.")
    droits = []
    for chg in changements:
        champ = chg.get("champ")
        droits.append("rapprocher" if champ == "groupes" else
                      ("masquer" if chg.get("avant") else "demasquer") if champ == "masque"
                      else champ)
    journal.verifier_pouvoirs(args.par, droits, POUVOIRS)

    print(f"Action  {cible['action']}  du {cible['horodatage'][:16].replace('T', ' à ')}")
    print(f"Agent   {cible['agent']}")
    print(f"Quoi    {cible['message']}")
    if cible.get("motif"):
        print(f"Motif   {cible['motif'][:200]}")
    print("\nCe qui va être remis comme avant :")

    dernieres = {}
    for decision in regles.decisions():
        champ = "groupes" if decision.get("type") == "fusion" else regles.CHAMPS.get(decision.get("type"))
        article = decision.get("principal") or decision.get("article")
        dernieres[(article, champ)] = decision.get("action")
    inverse = []
    def normaliser(valeur, champ):
        if valeur is ABSENT or valeur is None or valeur is False or (champ == "groupes" and valeur == []):
            return None
        return valeur

    for chg in changements:
        if dernieres.get((chg["itm8"], chg["champ"])) != cible["action"]:
            sys.exit(f"REFUSÉ : conflit sur {chg['itm8']} / {chg['champ']} : une autre décision fait foi.")
        actuelle = valeur_actuelle(cfg, chg)
        nom = noms.get(chg["itm8"], chg["itm8"])
        if normaliser(actuelle, chg["champ"]) != normaliser(chg["apres"], chg["champ"]):
            sys.exit(f"REFUSÉ : conflit sur {chg['itm8']} / {chg['champ']} : modifié depuis. Rien n'est écrit.")
        etat = ""
        print(f"  {nom} — {chg['champ']} : "
              f"{chg.get('apres')} -> {chg.get('avant')}{etat}")
        inverse.append({"itm8": chg["itm8"], "champ": chg["champ"],
                        "avant": None if actuelle is ABSENT else actuelle,
                        "apres": chg.get("avant")})

    if args.simuler:
        print("\nSIMULATION — rien n'a été écrit.")
        return

    motif = args.motif or (f"Annulation demandée par {args.par} de l'action "
                           f"{cible['action']} ({cible['message']}). "
                           "Les valeurs d'avant ont été remises à l'identique.")
    numero = journal.numero_action()
    lignes_inverses = decisions_inverses(cible, changements, numero, motif, args.par)

    append_jsonl(DECISIONS, lignes_inverses)

    # On vérifie que l'état reconstitué est bien celui d'avant : une annulation
    # qui se croit faite sans l'être serait pire que pas d'annulation du tout.
    attendu = regles.charger()
    erreurs = []
    for chg in changements:
        obtenue = valeur_actuelle(attendu, chg)
        voulue = chg.get("avant")
        if obtenue is ABSENT:
            obtenue = None
        if obtenue != (voulue if voulue not in ([],) else None) and not (
                chg["champ"] == "groupes" and not obtenue and not voulue):
            erreurs.append(f"{chg['itm8']} / {chg['champ']} vaut {obtenue!r} au lieu de {voulue!r}")
    if erreurs:
        journal.echec(args.par, "Annulation non vérifiée", action=numero,
                      details={"cible": cible["action"], "erreurs": erreurs})
        sys.exit("ÉCHEC : décisions inverses écrites mais restauration non vérifiée. " + "; ".join(erreurs))

    journal.enregistrer(
        agent=args.par, action=numero,
        message=f"Annulation de {cible['action']} : {cible['message']}",
        motif=motif,
        changements=inverse,
        annule_action=cible["action"],
        details={"agent_origine": cible["agent"], "demande_par": args.par,
                 "decisions": [l["id"] for l in lignes_inverses]},
    )

    print(f"\n  C'est défait. Annulation enregistrée sous {numero}.")
    print( "  La ligne d'origine reste dans le carnet : on n'efface jamais,")
    print( "  on écrit par-dessus ce qu'il faut pour revenir en arrière.")
    print( "\n  Penser à relancer : calculer-position.py, preparer-liste-comptage.py")


if __name__ == "__main__":
    main()
