"""Exécute unittest dans une copie jetable sans secrets ni accès mail.

Usage : py -3.14 -B tests/lancer_tests_isoles.py [tests/test_x.py ...]
        py -3.14 -B tests/lancer_tests_isoles.py --navigateur [--sortie <dossier>]
Sans argument, lance toute la suite. Les serveurs de fixtures restent locaux.
"""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

RACINE = Path(__file__).resolve().parents[1]

GARDE = r'''
import ipaddress, os, pathlib, socket, sys
_racine = pathlib.Path(os.environ["PREPARATION_TEST_SANDBOX"]).resolve()
_protege = pathlib.Path(os.environ["PREPARATION_TEST_ORIGINAL"]).resolve()
def _est_original(chemin):
    if not isinstance(chemin, (str, bytes, os.PathLike)):
        return False
    try:
        return pathlib.Path(os.fsdecode(chemin)).resolve().is_relative_to(_protege)
    except (ValueError, OSError):
        return False
def _audit(evenement, args):
    if evenement == "open":
        nom, mode, flags = args
        if _est_original(nom) and pathlib.Path(os.fsdecode(nom)).name == ".env":
            raise PermissionError("Test : lecture des secrets de l'installation originale interdite")
        ecriture = (isinstance(mode, str) and any(c in mode for c in "wax+")) or bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
        if ecriture and _est_original(nom):
            raise PermissionError("Test : écriture dans l'installation originale interdite")
    if evenement in {"os.remove", "os.rmdir", "os.mkdir", "os.rename", "os.link", "os.symlink", "os.chmod", "os.utime", "shutil.rmtree"}:
        if any(_est_original(v) for v in args[:2]):
            raise PermissionError("Test : modification de l'installation originale interdite")
    if evenement in {"socket.connect", "socket.bind"}:
        adresse = args[1]
        if isinstance(adresse, tuple):
            hote = adresse[0]
            try:
                local = hote == "localhost" or ipaddress.ip_address(hote).is_loopback
            except ValueError:
                local = False
            if not local:
                raise PermissionError("Test : connexion ou écoute externe interdite")
            if evenement == "socket.connect" and adresse[1] == 8751:
                raise PermissionError("Test : connexion au serveur de production interdite")
sys.addaudithook(_audit)
'''


def ignorer_prives(dossier, noms):
    """Ne transporte ni identifiants de courrier ni traces privées dans les copies."""
    exclus = {".git", ".venv", "node_modules", "__pycache__", "scratch", "courrier",
              "courrier-config.json", ".sentinelle-evenements.json", ".courrier_uids_connus.json"}
    return [n for n in noms if n in exclus or n == ".env" or (n.startswith(".env.") and n != ".env.example")
            or n.endswith((".pyc", ".log", ".lock"))]


def neutraliser_courrier(copie):
    donnees = Path(copie) / "donnees"
    if donnees.is_dir():
        (donnees / "courrier-config.json").write_text(
            '{"mot_de_passe":"","actif":false}', encoding="utf-8")


def principal(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tests", nargs="*")
    parser.add_argument("--navigateur", action="store_true")
    parser.add_argument("--sortie", type=Path)
    args = parser.parse_args(argv)
    if args.navigateur and args.tests:
        parser.error("--navigateur ne se combine pas avec une liste de tests unitaires")
    if args.sortie and not args.navigateur:
        parser.error("--sortie est réservé au parcours navigateur")
    with tempfile.TemporaryDirectory(prefix="preparation-tests-") as temporaire:
        base = Path(temporaire)
        copie = base / "projet"
        shutil.copytree(RACINE, copie, ignore=ignorer_prives)
        neutraliser_courrier(copie)
        garde = base / "garde"
        garde.mkdir()
        (garde / "sitecustomize.py").write_text(GARDE, encoding="utf-8")
        temporaires = base / "temporaires"
        temporaires.mkdir()
        environnement = os.environ.copy()
        for nom in tuple(environnement):
            if any(secret in nom.upper() for secret in ("PASSWORD", "MOT_DE_PASSE", "SMTP", "IMAP", "GMAIL")):
                environnement.pop(nom)
        environnement.update(PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1",
                             PREPARATION_TEST_SANDBOX=str(base),
                             PREPARATION_TEST_ORIGINAL=str(RACINE),
                             TEMP=str(temporaires), TMP=str(temporaires), TMPDIR=str(temporaires))
        environnement["PYTHONPATH"] = os.pathsep.join([str(garde), str(copie / "moteur"), str(copie / "tests")])
        if args.navigateur:
            commande = [sys.executable, "-B", "tests/e2e_application.py"]
            sortie = args.sortie.resolve() if args.sortie else Path(tempfile.gettempdir()) / "preparation-audit/navigateur"
            commande += ["--sortie", str(sortie)]
        else:
            commande = [sys.executable, "-B", "-m", "unittest"]
            commande += args.tests or ["discover", "-s", "tests"]
        print("Tests dans une copie temporaire ; données originales protégées, réseau externe bloqué.", flush=True)
        return subprocess.run(commande, cwd=copie, env=environnement).returncode


if __name__ == "__main__":
    raise SystemExit(principal())
