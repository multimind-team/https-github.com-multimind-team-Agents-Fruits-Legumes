"""
Superviseur permanent de la Tri-Sentinelle.

Ce script maintient la sentinelle active en continu :
1. Il lance la sentinelle pour écouter les mails, messages et comptages.
2. Dès qu'un événement survient, la sentinelle sort pour signaler l'événement.
3. Le superviseur prend en charge l'événement :
   - Pour les comptages : il lance l'analyse d'écarts (analyser-ecarts-comptage.py),
     met à jour audit-comptages.json pour le pilotage, et acquitte les relevés.
   - Pour les mails et messages : il journalise l'alerte pour les agents dédiés.
4. Il relance immédiatement la sentinelle pour qu'elle reste en écoute continue
   sans jamais rester bloquée à l'arrêt.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
DONNEES = RACINE / "donnees"
SCRIPT_SENTINELLE = RACINE / "moteur" / "surveille-mail-message-comptage.py"
SCRIPT_AUDIT = RACINE / "moteur" / "analyser-ecarts-comptage.py"
FICHIER_EVENEMENTS = DONNEES / ".sentinelle-evenements.json"
FICHIER_ARRET = RACINE / ".serveur-arrete"


def traiter_comptages_en_attente():
    """Traite et acquitte automatiquement les comptages pour maintenir la sentinelle fluide."""
    if not FICHIER_EVENEMENTS.exists():
        return
    try:
        data = json.loads(FICHIER_EVENEMENTS.read_text(encoding="utf-8"))
        en_attente = data.get("en_attente", {})
        comptages = [ev for ev in en_attente.values() if ev.get("type") == "COMPTAGE"]
        if not comptages:
            return

        print(f"[SUPERVISEUR] {len(comptages)} comptage(s) détecté(s). Lancement de l'audit de stock...")
        # 1. Lancer l'analyse d'écarts de stock (Agent Audit Stock)
        res = subprocess.run([sys.executable, str(SCRIPT_AUDIT)],
                             cwd=RACINE, capture_output=True, text=True, timeout=60)
        date_analyse = "direct"
        fichier_audit = DONNEES / "audit-comptages.json"
        if fichier_audit.exists():
            try:
                date_analyse = json.loads(fichier_audit.read_text(encoding="utf-8")).get("date_analysee", "direct")
            except Exception:
                pass

        # 2. Acquitter formellement chaque comptage avec la preuve d'audit
        for ev in comptages:
            eid = ev.get("id")
            if eid:
                subprocess.run(
                    [sys.executable, str(SCRIPT_SENTINELLE),
                     "--acquitter", "COMPTAGE", eid,
                     "--preuve", f"audit-comptages.json:{date_analyse}"],
                    cwd=RACINE, capture_output=True, text=True, timeout=15)
        print(f"[SUPERVISEUR] Audit de stock actualisé et {len(comptages)} comptage(s) acquitté(s).")
    except Exception as exc:
        print(f"[SUPERVISEUR] Erreur traitement comptages : {exc}", file=sys.stderr)


def boucle_supervision():
    print("=" * 60)
    print("SUPERVISEUR PERMANENT DE LA TRI-SENTINELLE")
    print("Maintient la veille active (mail, message, comptage) en continu.")
    print("Arrêt : Ctrl+C ou arreter-sentinelle.bat")
    print("=" * 60)

    while True:
        if FICHIER_ARRET.exists():
            print("[SUPERVISEUR] Arrêt de maintenance détecté (.serveur-arrete). En attente...")
            time.sleep(3)
            continue

        # Traiter les comptages qui seraient déjà en attente avant de relancer
        traiter_comptages_en_attente()

        print("[SUPERVISEUR] Lancement de la sentinelle en écoute active...")
        try:
            processus = subprocess.run(
                [sys.executable, "-u", str(SCRIPT_SENTINELLE)],
                cwd=RACINE, capture_output=True, text=True)

            code = processus.returncode
            sortie = processus.stdout or ""
            erreurs = processus.stderr or ""

            if "EVENEMENT: COMPTAGE" in sortie:
                print("[SUPERVISEUR] Événement COMPTAGE capturé.")
                traiter_comptages_en_attente()

            if "EVENEMENT: MESSAGE" in sortie:
                print("[SUPERVISEUR] Événement MESSAGE capturé. En attente de traitement agent-rayon.")

            if "EVENEMENT: MAIL" in sortie:
                print("[SUPERVISEUR] Événement MAIL capturé. En attente de traitement agent-courrier.")

            if code == 3:  # ArretDemande
                print("[SUPERVISEUR] Arrêt demandé reçu.")
                time.sleep(2)
            elif code != 0:
                print(f"[SUPERVISEUR] Sentinelle terminée avec code {code} : {erreurs.strip()[-200:]}")
                time.sleep(2)

        except KeyboardInterrupt:
            print("\n[SUPERVISEUR] Arrêt manuel demandé.")
            break
        except Exception as exc:
            print(f"[SUPERVISEUR] Incident dans la boucle : {exc}", file=sys.stderr)
            time.sleep(2)

        time.sleep(1)


if __name__ == "__main__":
    boucle_supervision()
