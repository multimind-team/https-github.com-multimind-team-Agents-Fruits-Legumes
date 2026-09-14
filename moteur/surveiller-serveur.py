"""Surveillance locale prudente ; respecte l'arrêt demandé et refuse les doublons."""
import argparse
import importlib.util
import logging
import sys
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
JOURNAL = RACINE / "surveillance-serveur.log"
_spec = importlib.util.spec_from_file_location("gestion_serveur", RACINE / "moteur" / "gerer-serveur.py")
gestion = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gestion)
application_repond = gestion.application_repond


def demarrer_serveur(port=8751):
    """N'agit que sur le projet, jamais sur un simple propriétaire du port."""
    return gestion.GestionServeur(RACINE, port).demarrer(automatique=True)


def veille_une_fois(verifie=None, demarre=None):
    """Compatibilité des tests purs ; le chemin réel impose aussi l'identité OS."""
    if verifie is None and demarre is None:
        return demarrer_serveur() == "actif"
    if (verifie or application_repond)():
        return True
    (demarre or demarrer_serveur)()
    return False


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--intervalle", type=int, default=30)
    parser.add_argument("--port", type=int, default=8751)
    parser.add_argument("--une-fois", action="store_true", help="Exécuter un seul cycle de surveillance.")
    args = parser.parse_args(argv)
    if args.intervalle < 5:
        parser.error("L'intervalle doit être d'au moins 5 secondes.")
    if not 1 <= args.port <= 65535:
        parser.error("Le port doit être compris entre 1 et 65535.")

    logger = logging.getLogger("preparation.surveillance")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    journal = logging.FileHandler(JOURNAL, mode="a", encoding="utf-8")
    journal.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(journal)
    try:
        with gestion.VerrouLocal(RACINE / ".surveillance-serveur.lock"):
            if (RACINE / ".serveur-arrete").exists():
                logger.info("Arrêt de maintenance conservé ; reprise par demarrer-serveur.bat.")
                return 0
            service = gestion.GestionServeur(RACINE, args.port)
            logger.info("Surveillance démarrée (contrôle toutes les %s secondes).", args.intervalle)
            while True:
                resultat = 0
                try:
                    etat = service.demarrer(automatique=True)
                    if etat == "maintenance":
                        logger.info("Arrêt de maintenance demandé ; surveillance arrêtée.")
                        return 0
                    if etat == "demarre":
                        logger.warning("Serveur relancé ; identité et réponse HTTP vérifiées.")
                except gestion.GestionErreur as erreur:
                    logger.warning("%s", erreur)
                    resultat = 1
                except Exception as erreur:
                    # Pas de commande, environnement, corps HTTP ou exception brute :
                    # les diagnostics persistants ne doivent pas diffuser de secrets.
                    logger.error("Erreur de surveillance (%s) ; aucune terminaison étrangère.", type(erreur).__name__)
                    resultat = 1
                if args.une_fois:
                    return resultat
                time.sleep(args.intervalle)
    except gestion.VerrouOccupe:
        logger.info("Surveillance déjà active ; cette instance quitte sans lancer de serveur.")
        return 0
    finally:
        logger.removeHandler(journal)
        journal.close()


if __name__ == "__main__":
    sys.exit(main())
