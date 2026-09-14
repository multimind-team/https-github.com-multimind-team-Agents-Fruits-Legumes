"""
moteur/dire.py - Permet à l'agent orchestrateur ou à un agent spécialisé
de publier une annonce ou une réponse directement dans le chat de l'application web.

Usage :
  python moteur/dire.py --auteur "Agent Orchestrateur" "Je prends la main sur la commande."
  python moteur/dire.py --auteur "Agent donnees" "Les fichiers du matin sont integres."
"""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
DONNEES = RACINE / "donnees"
REPONSES = DONNEES / "reponses.jsonl"


def publier(texte, auteur="Assistant", en_reponse_a=None, action=None):
    """Enregistre un message de l'agent dans donnees/reponses.jsonl pour l'application web."""
    DONNEES.mkdir(parents=True, exist_ok=True)
    maintenant = datetime.now().isoformat(timespec="seconds")
    identifiant = f"rep:{maintenant}:{os.urandom(3).hex()}"

    entree = {
        "id": identifiant,
        "ecrit_le": maintenant,
        "auteur": auteur,
        "texte": texte.strip(),
        "en_reponse_a": en_reponse_a,
    }
    if action:
        entree["action"] = action

    with open(REPONSES, "a", encoding="utf-8") as f:
        f.write(json.dumps(entree, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())

    try:
        print(f"[{auteur}] {texte}")
    except (UnicodeEncodeError, OSError):
        enc = getattr(sys.stdout, "encoding", None) or "utf-8"
        print(f"[{auteur}] {texte.encode(enc, errors='replace').decode(enc, errors='replace')}")
    return identifiant


def main():
    parser = argparse.ArgumentParser(description="Publier un message dans le chat web.")
    parser.add_argument("message", type=str, help="Le texte du message à afficher.")
    parser.add_argument("--auteur", type=str, default="Agent Orchestrateur", help="L'auteur du message.")
    parser.add_argument("--en-reponse-a", type=str, default=None, help="L'ID du message auquel on répond.")
    parser.add_argument("--action", type=str, default=None, help="Une étiquette d'action (ex: A-20260906-0001).")

    args = parser.parse_args()
    publier(args.message, auteur=args.auteur, en_reponse_a=args.en_reponse_a, action=args.action)


if __name__ == "__main__":
    main()
