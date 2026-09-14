"""Exécute les tests avec refus des écritures projet et lectures de secrets.

py -3.14 -B tests/verifier_factures_isolees.py [--tous]
Les subprocess des autres suites ne reprennent pas le hook ; --tous reste une
vérification supplémentaire, pas une sandbox OS.
"""
import os
from pathlib import Path
import sys
import unittest

RACINE = Path(__file__).resolve().parents[1]


def garde(event, args):
    chemins = ()
    if event == "open":
        chemin, mode, flags = args
        if isinstance(chemin, (str, bytes, os.PathLike)):
            cible = Path(os.fsdecode(chemin))
            if cible.name == ".env" or ("credentials" in cible.name.lower() and
                                          cible.suffix.lower() not in (".py", ".pyc")):
                raise AssertionError("Lecture de secrets interdite pendant les tests")
        if ((mode and any(c in mode for c in "wax+")) or
                flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC)):
            chemins = (chemin,)
    elif event in ("os.remove", "os.rmdir", "os.mkdir", "os.chmod", "os.utime"):
        chemins = (args[0],)
    elif event == "os.rename":
        chemins = args[:2]
    elif event == "socket.connect":
        adresse = args[1]
        if isinstance(adresse, tuple) and (adresse[0] not in ("127.0.0.1", "::1", "localhost") or
                                          adresse[1] in (25, 465, 587)):
            raise AssertionError("Connexion externe/SMTP interdite pendant les tests")
    for chemin in chemins:
        if isinstance(chemin, (str, bytes, os.PathLike)):
            cible = Path(os.fsdecode(chemin)).resolve()
            if cible == RACINE or RACINE in cible.parents:
                raise AssertionError(f"Écriture dans le projet réel interdite : {cible}")


def main():
    sys.dont_write_bytecode = True
    sys.addaudithook(garde)
    motifs = (["test*.py"] if "--tous" in sys.argv else
              ["test_facture_directe*.py", "test_envoi_classeur*.py", "test_envoyer_classeur_marge.py"])
    suite = unittest.TestSuite()
    for motif in motifs:
        suite.addTests(unittest.defaultTestLoader.discover(str(RACINE / "tests"), pattern=motif))
    resultat = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if resultat.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
