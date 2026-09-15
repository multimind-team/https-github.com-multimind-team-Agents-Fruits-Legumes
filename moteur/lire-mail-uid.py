"""moteur/lire-mail-uid.py - Lit un message précis par son UID IMAP."""
import argparse
import email
from email.header import decode_header
import imaplib
import json
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config_courrier import charger_config_courrier
from courrier_fichiers import conserver_piece

RACINE = Path(__file__).resolve().parent.parent
CONFIG_PATH = RACINE / "donnees" / "courrier-config.json"


def dec(valeur):
    if not valeur:
        return ""
    morceaux = []
    for bout, encodage in decode_header(valeur):
        if isinstance(bout, bytes):
            morceaux.append(bout.decode(encodage or "utf-8", errors="replace"))
        else:
            morceaux.append(str(bout))
    return "".join(morceaux)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("uid", help="UID IMAP du message")
    parser.add_argument("--telecharger", action="store_true", help="Telecharger les pieces jointes")
    args = parser.parse_args()
    if not args.uid.isascii() or not args.uid.isdigit():
        parser.error("L'UID IMAP doit être un entier positif")

    cfg = charger_config_courrier(CONFIG_PATH)

    client = imaplib.IMAP4_SSL(cfg["imap_host"], cfg.get("imap_port", 993))
    try:
        client.login(cfg["utilisateur"], cfg["mot_de_passe"])
        client.select("INBOX", readonly=True)

        typ, data = client.uid("fetch", args.uid.encode("ascii"), "(BODY.PEEK[])")
        if typ != "OK" or not data or not data[0]:
            print(json.dumps({"erreur": "Message introuvable", "uid": args.uid}))
            return 1

        msg = email.message_from_bytes(data[0][1])
        de = dec(msg.get("From"))
        sujet = dec(msg.get("Subject"))
        date_msg = dec(msg.get("Date"))

        corps = ""
        pieces = []
        dest_rep = RACINE / "donnees" / "courrier" / f"uid-{args.uid}"

        for part in msg.walk():
            fn = part.get_filename()
            if fn:
                nom = dec(fn)
                payload = part.get_payload(decode=True) or b""
                pieces.append({"nom": nom, "taille": len(payload), "type": part.get_content_type()})
                if args.telecharger:
                    chemin, empreinte = conserver_piece(dest_rep, nom, payload)
                    pieces[-1].update(chemin=str(chemin), sha256=empreinte)
            elif part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True) or b""
                corps += payload.decode("utf-8", errors="replace")

        resultat = {
            "uid": args.uid,
            "de": de,
            "sujet": sujet,
            "date": date_msg,
            "corps": corps.strip(),
            "pieces_jointes": pieces,
        }
        try:
            print(json.dumps(resultat, indent=2, ensure_ascii=False))
        except UnicodeEncodeError:
            print(json.dumps(resultat, indent=2, ensure_ascii=True))
    finally:
        try:
            client.logout()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
