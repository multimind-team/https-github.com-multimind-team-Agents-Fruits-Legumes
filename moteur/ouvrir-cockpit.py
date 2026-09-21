"""Ouvre le cockpit dans une fenêtre dédiée, après vérification du serveur local."""
from pathlib import Path
import ctypes
import os
import subprocess
import sys
import urllib.request
import webbrowser

RACINE = Path(__file__).resolve().parents[1]
URL = "http://127.0.0.1:8751/app/cockpit.html"


def main():
    resultat = subprocess.run(
        [sys.executable, "-B", str(RACINE / "moteur/gerer-serveur.py"), "demarrer"],
        cwd=RACINE, capture_output=True, text=True, encoding="utf-8", errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), timeout=90)
    if resultat.returncode:
        raise RuntimeError("Le serveur local n'a pas pu démarrer. Consultez le journal gestion-serveur.log dans le dossier de l'application.")
    with urllib.request.urlopen(URL, timeout=15) as reponse:
        if reponse.status != 200:
            raise RuntimeError("Le cockpit n'est pas accessible sur le serveur local.")
    navigateurs = [Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / "Microsoft/Edge/Application/msedge.exe",
                   Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Microsoft/Edge/Application/msedge.exe",
                   Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Google/Chrome/Application/chrome.exe"]
    navigateur = next((p for p in navigateurs if p.is_file()), None)
    if navigateur:
        subprocess.Popen([str(navigateur), "--app=" + URL, "--new-window", "--window-size=1440,960"], cwd=RACINE)
    else:
        webbrowser.open(URL, new=1)


if __name__ == "__main__":
    try:
        main()
    except Exception as erreur:
        ctypes.windll.user32.MessageBoxW(None, str(erreur), "Cockpit Fruits et Légumes", 0x10)
        raise SystemExit(1)
