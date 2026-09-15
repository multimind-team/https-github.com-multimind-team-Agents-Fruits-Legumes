"""Traite un lot de pièces jointes relevé par l'agent orchestrateur.

Le modèle fournit les chemins locaux des pièces jointes, l'identifiant du mail,
sa date et l'expéditeur. Ce script assure le rangement idempotent et lance les
outils déterministes pour les exports magasin. Les factures directes sont
laissées à ``importer-facture-directe.py`` après extraction et contrôle des
lignes : elles ne sont jamais devinées depuis un nom de fichier.

Une relance rejoue l'import (déduplication des faits par ID), le recalcul et la
note, sans réindexer les pièces connues. Pas de nouvel acquittement persistant
qui pourrait confondre une copie reçue et un traitement réellement achevé.
Codes retour : 0 = succès complet/plan de simulation,
1 = données en retard, 2 = échec technique, 3 = éléments à vérifier. Une note est
tentée même après un échec ; sa réussite ne masque jamais l'échec précédent.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

from courrier_pipeline import actions_a_executer, classer_fichier, commandes_a_lancer, ranger_pieces_jointes
from verrou_donnees import verrou_donnees, environnement_verrou
from ecriture_derivee import publier_etat_calcul

RACINE = Path(__file__).resolve().parent.parent


def lancer(commande, simuler):
    if simuler:
        return {"commande": commande, "code": None, "sortie": "SIMULATION", "statut": "simulation"}
    racine = Path(commande[2]).resolve().parent.parent
    recalcul = Path(commande[2]).name == "filet-de-securite.py"
    fraicheur = racine / "donnees/fraicheur.json"
    try:
        avant = fraicheur.stat().st_mtime_ns if recalcul and fraicheur.exists() else None
        resultat = subprocess.run(commande, cwd=racine, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=900,
                                  env=environnement_verrou(racine / "donnees"))
    except (OSError, subprocess.TimeoutExpired) as erreur:
        return {"commande": commande, "code": 124 if isinstance(erreur, subprocess.TimeoutExpired) else 127,
                "statut": "echec-technique", "sortie": str(erreur)}
    reponse = {"commande": commande, "code": resultat.returncode,
               "sortie": ((resultat.stdout or "") + (resultat.stderr or "")).strip(),
               "statut": "ok" if resultat.returncode == 0 else "echec-technique"}
    if Path(commande[2]).name in {"integrer-fichiers.py", "importer-catalogue-mercalys.py"}:
        try:
            bilan = json.loads(resultat.stdout)
            if not isinstance(bilan, dict):
                raise ValueError("Le bilan d'import doit être un objet JSON")
            reponse["bilan_import"] = bilan
            if resultat.returncode in (0, 3) and (bilan.get("a_verifier") or bilan.get("erreurs")
                    or bilan.get("statut") == "a-verifier" or bilan.get("ok") is False):
                reponse["statut"] = "a-verifier"
        except (ValueError, TypeError) as erreur:
            reponse["statut"] = "echec-technique"
            reponse["erreur"] = "Bilan d'import absent ou illisible : " + str(erreur)
    if recalcul:
        # Le code 1 seul est ambigu ; ne jamais utiliser un ancien constat.
        reponse["statut"] = "echec-technique"
        try:
            if fraicheur.stat().st_mtime_ns == avant:
                raise ValueError("Le recalcul n'a pas renouvelé fraicheur.json")
            constat = json.loads(fraicheur.read_text(encoding="utf-8"))
            reponse["fraicheur"] = constat
            if constat.get("calculs_en_echec") == []:
                if resultat.returncode == 1 and constat.get("etat") == "donnees-en-retard":
                    reponse["statut"] = "donnees-en-retard"
                elif resultat.returncode == 0 and constat.get("etat") == "a-jour":
                    reponse["statut"] = "ok"
        except (OSError, ValueError, AttributeError) as erreur:
            reponse["erreur"] = str(erreur)
    return reponse


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pieces_jointes", nargs="+", help="Chemins des pièces jointes reçues")
    parser.add_argument("--mail-id", required=True, help="Message-ID du mail source")
    parser.add_argument("--date", required=True, help="Date de réception AAAA-MM-JJ")
    parser.add_argument("--expediteur", required=True)
    parser.add_argument("--simuler", action="store_true")
    parser.add_argument("--racine", default=RACINE, type=Path,
                        help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.simuler:
        return executer_lot(args)
    with verrou_donnees(args.racine.resolve() / "donnees"):
        return executer_lot(args)


def executer_lot(args):

    racine = args.racine.resolve()
    resultats = []
    bloque = False
    try:
        rangement = ranger_pieces_jointes(racine, args.mail_id, args.date, args.expediteur,
                                          [Path(p) for p in args.pieces_jointes], simuler=args.simuler)
        actions = actions_a_executer(rangement["classes"], rangement["nouveaux"])
        dossiers = sorted({Path(f).parent for f in rangement["fichiers"]
                           if classer_fichier(f) == "mouvement"})
    except (OSError, ValueError) as erreur:
        rangement, actions, dossiers = None, ["note"], []
        bloque = True
        resultats.append({"etape": "rangement", "code": 2, "statut": "echec-technique",
                          "sortie": str(erreur)})
    if actions:
        calcul_prevu = "recalculer" in actions and not args.simuler
        if calcul_prevu:
            publier_etat_calcul(racine / "donnees", "en-cours", "courrier")
        for commande in commandes_a_lancer(racine, dossiers, actions,
                                           fichiers=(rangement or {}).get("fichiers", [])):
            if bloque and Path(commande[2]).name != "note-du-matin.py":
                resultat = {"commande": commande, "code": None, "statut": "non-execute",
                            "sortie": "Étape dépendante non exécutée : une étape précédente a échoué."}
            else:
                resultat = lancer(commande, args.simuler)
            resultats.append(resultat)
            bloque = bloque or resultat["statut"] == "echec-technique"
        if calcul_prevu:
            incomplet = any(r["statut"] == "a-verifier" for r in resultats)
            publier_etat_calcul(racine / "donnees", "echec" if bloque or incomplet else "termine", "courrier",
                               "Une étape du lot a échoué." if bloque else
                               "Import incomplet : éléments à vérifier dans le compte rendu." if incomplet else "")

    statuts = {r["statut"] for r in resultats}
    a_verifier = [{"fichier": f, "type": classer_fichier(f)} for f in (rangement or {}).get("fichiers", [])
                  if classer_fichier(f) not in {"mouvement", "cadencier"}]
    for resultat in resultats:
        bilan = resultat.get("bilan_import", {})
        a_verifier.extend(bilan.get("a_verifier") or [])
        a_verifier.extend(bilan.get("erreurs") or [])
        if resultat["statut"] == "a-verifier" and not (bilan.get("a_verifier") or bilan.get("erreurs")):
            a_verifier.append({"etape": Path(resultat["commande"][2]).name,
                              "message": "Import incomplet : consulter le bilan"})
    statut = ("echec-technique" if bloque else "donnees-en-retard" if "donnees-en-retard" in statuts
              else "simulation" if args.simuler else "a-verifier" if a_verifier else "ok")
    sortie = {
        "statut": statut,
        "succes": statut == "ok",
        "rangement": rangement,
        "actions": actions,
        "resultats": resultats,
        "a_verifier": a_verifier,
        "facture_directe": (
            "à extraire et valider avec importer-facture-directe.py"
            if "facture-directe" in actions else None
        ),
    }
    print(json.dumps(sortie, ensure_ascii=True, indent=1))
    return (2 if statut == "echec-technique" else 1 if statut == "donnees-en-retard"
            else 3 if statut == "a-verifier" else 0)


if __name__ == "__main__":
    sys.exit(main())
