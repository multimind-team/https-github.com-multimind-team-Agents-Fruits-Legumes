"""Envoie le classeur de marge Pomona comme vraie pièce jointe MIME."""

import argparse
import json
import os
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]



def lit_env_mail():
    """Lit la configuration mail locale (courrier-config.json ou variables d'environnement), sans l'afficher."""
    config_locale = RACINE / "donnees" / "courrier-config.json"
    if config_locale.is_file():
        import json
        cfg = json.loads(config_locale.read_text(encoding="utf-8-sig"))
        return {
            "EMAIL_ADDRESS": cfg.get("utilisateur", ""),
            "EMAIL_PASSWORD": cfg.get("mot_de_passe", ""),
            "EMAIL_SMTP_HOST": cfg.get("smtp_host", "smtp.gmail.com"),
            "EMAIL_SMTP_PORT": str(cfg.get("smtp_port", 587)),
        }
    valeurs = {
        "EMAIL_ADDRESS": os.environ.get("EMAIL_ADDRESS", ""),
        "EMAIL_PASSWORD": os.environ.get("EMAIL_PASSWORD", ""),
        "EMAIL_SMTP_HOST": os.environ.get("EMAIL_SMTP_HOST", "smtp.gmail.com"),
        "EMAIL_SMTP_PORT": os.environ.get("EMAIL_SMTP_PORT", "587"),
    }
    requis = ("EMAIL_ADDRESS", "EMAIL_PASSWORD", "EMAIL_SMTP_HOST")
    manquants = [cle for cle in requis if not valeurs.get(cle)]
    if manquants:
        raise ValueError("Configuration e-mail incomplète : " + ", ".join(manquants))
    return valeurs


def construit_message(expediteur, destinataire, classeur, sujet, corps):
    """Construit un e-mail MIME avec une copie binaire exacte du classeur."""
    classeur = Path(classeur)
    if not classeur.is_file():
        raise FileNotFoundError(f"Classeur absent : {classeur}")
    message = EmailMessage()
    message["From"] = expediteur
    message["To"] = destinataire
    message["Subject"] = sujet
    message.set_content(corps)
    message.add_attachment(
        classeur.read_bytes(),
        maintype="application",
        subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=classeur.name,
    )
    return message


def envoie_message(configuration, message):
    """Envoie par SMTP, avec TLS explicite hors port SMTPS 465."""
    port = int(configuration.get("EMAIL_SMTP_PORT", "587"))
    contexte = ssl.create_default_context()
    if port == 465:
        client = smtplib.SMTP_SSL(configuration["EMAIL_SMTP_HOST"], port, timeout=30,
                                  context=contexte)
    else:
        client = smtplib.SMTP(configuration["EMAIL_SMTP_HOST"], port, timeout=30)
    with client:
        if port != 465:
            client.starttls(context=contexte)
        client.login(configuration["EMAIL_ADDRESS"], configuration["EMAIL_PASSWORD"])
        refus = client.send_message(message)
    if refus:
        raise RuntimeError("SMTP a refusé au moins un destinataire")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destinataire", default="PDV11768@mousquetaires.com",
                        help="Adresse destinataire (par défaut : PDV11768@mousquetaires.com)")
    parser.add_argument("--classeur", type=Path, required=True,
                        help="Chemin exact du classeur mensuel validé par l'import facture")
    parser.add_argument("--sujet", default="Calcul de marge Pomona")
    parser.add_argument("--simuler", action="store_true")
    args = parser.parse_args()

    configuration = lit_env_mail()
    message = construit_message(
        configuration["EMAIL_ADDRESS"],
        args.destinataire,
        args.classeur,
        args.sujet,
        "Bonjour,\n\nVeuillez trouver en pièce jointe le classeur de calcul de marge Pomona.\n",
    )
    if not args.simuler:
        envoie_message(configuration, message)
    print(json.dumps({
        "succes": True,
        "simulation": args.simuler,
        "fichier_joint": args.classeur.name,
        "smtp_accepte": not args.simuler,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
