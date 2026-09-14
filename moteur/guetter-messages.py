"""
moteur/guetter-messages.py - Sentinelle silencieuse des messages du rayon.

Ce script s'exécute en tâche de fond sur le PC local (0 token).
Il écoute le carnet `donnees/messages.jsonl`. Dès qu'un nouveau message
arrive depuis l'application smartphone du responsable de rayon, il affiche
le contenu du message et se termine avec le code 0.

La fin du processus réveille immédiatement l'agent orchestrateur dans Antigravity.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
DONNEES = RACINE / "donnees"
MESSAGES_PATH = DONNEES / "messages.jsonl"


def charger_identifiants_connus(chemin):
    """Charge l'ensemble des identifiants de messages déjà présents."""
    connus = set()
    if not chemin.exists():
        return connus
    try:
        with open(chemin, "r", encoding="utf-8", errors="replace") as f:
            for ligne in f:
                ligne = ligne.strip()
                if not ligne:
                    continue
                try:
                    obj = json.loads(ligne)
                    if "id" in obj:
                        connus.add(obj["id"])
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return connus


def guetter(chemin=MESSAGES_PATH, intervalle=1.0, timeout=None):
    """Attend l'arrivée d'un nouveau message et l'affiche avant de sortir."""
    connus = charger_identifiants_connus(chemin)
    print(f"GUETTER: Surveillance active de {chemin.name} ({len(connus)} messages existants ignores).", flush=True)

    debut = time.time()
    while True:
        if timeout and (time.time() - debut) > timeout:
            print("GUETTER: Timeout atteint sans nouveau message.", flush=True)
            return 0

        time.sleep(intervalle)

        if not chemin.exists():
            continue

        try:
            nouveaux = []
            with open(chemin, "r", encoding="utf-8", errors="replace") as f:
                for ligne in f:
                    ligne = ligne.strip()
                    if not ligne:
                        continue
                    try:
                        obj = json.loads(ligne)
                        identifiant = obj.get("id")
                        if identifiant and identifiant not in connus:
                            nouveaux.append(obj)
                            connus.add(identifiant)
                    except json.JSONDecodeError:
                        continue

            if nouveaux:
                print(f"NOUVEAU_MESSAGE_RAYON: {len(nouveaux)} message(s) recu(s) !", flush=True)
                for msg in nouveaux:
                    print(json.dumps(msg, ensure_ascii=False), flush=True)
                return 0
        except OSError:
            pass


def main():
    parser = argparse.ArgumentParser(description="Guetter les nouveaux messages du rayon.")
    parser.add_argument("--fichier", type=Path, default=MESSAGES_PATH, help="Chemin vers messages.jsonl")
    parser.add_argument("--intervalle", type=float, default=1.0, help="Intervalle d'écoute en secondes")
    parser.add_argument("--timeout", type=float, default=None, help="Délai maximum en secondes (optionnel)")
    args = parser.parse_args()

    return guetter(chemin=args.fichier, intervalle=args.intervalle, timeout=args.timeout)


if __name__ == "__main__":
    sys.exit(main() or 0)
