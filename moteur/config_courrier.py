"""Lecture sécurisée de la configuration du courrier électronique.

Les paramètres généraux (hôtes, ports, dossiers) sont lus dans donnees/courrier-config.json.
Le mot de passe secret est OBLIGATOIREMENT lu depuis le fichier local .env (ou variable
d'environnement MONRAYON_EMAIL_PASSWORD), garantissant qu'aucun secret ne fuite dans Git.
"""
import json
import os
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
CONFIG_PATH = RACINE / "donnees" / "courrier-config.json"
ENV_PATH = RACINE / ".env"


def charger_env_local():
    """Charge les paires CLE=VALEUR du fichier .env sans bibliothèque externe."""
    if not ENV_PATH.is_file():
        return {}
    vars_env = {}
    for ligne in ENV_PATH.read_text(encoding="utf-8").splitlines():
        ligne = ligne.strip()
        if not ligne or ligne.startswith("#") or "=" not in ligne:
            continue
        cle, valeur = ligne.split("=", 1)
        vars_env[cle.strip()] = valeur.strip()
    return vars_env


def charger_config_courrier(chemin=None):
    """Charge la configuration et injecte le mot de passe depuis .env / variables d'env."""
    fichier = Path(chemin) if chemin else CONFIG_PATH
    config = {}
    if fichier.is_file():
        try:
            config = json.loads(fichier.read_text(encoding="utf-8-sig"))
        except Exception:
            pass

    env_local = charger_env_local()

    # Priorité pour l'utilisateur
    utilisateur = (
        os.environ.get("MONRAYON_EMAIL_USER")
        or env_local.get("MONRAYON_EMAIL_USER")
        or config.get("utilisateur", "")
    )
    # Priorité pour le mot de passe (secret absolu : toujours .env en premier)
    mot_de_passe = (
        os.environ.get("MONRAYON_EMAIL_PASSWORD")
        or env_local.get("MONRAYON_EMAIL_PASSWORD")
        or config.get("mot_de_passe", "")
    )

    config["utilisateur"] = utilisateur
    config["mot_de_passe"] = mot_de_passe
    return config
