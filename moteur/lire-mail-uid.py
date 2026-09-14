"""moteur/lire-mail-uid.py - Lit un message précis par son UID IMAP."""
import argparse
import email
from email.header import decode_header
import imaplib
import json
from pathlib import Path

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

    with open(CONFIG_PATH, "r", encoding="utf-8-sig") as f:
        cfg = json.load(f)

    client = imaplib.IMAP4_SSL(cfg["imap_host"], cfg.get("imap_port", 993))
    try:
        client.login(cfg["utilisateur"], cfg["mot_de_passe"])
        client.select("INBOX", readonly=True)

        typ, data = client.uid("fetch", args.uid.encode("ascii"), "(RFC822)")
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
                    dest_rep.mkdir(parents=True, exist_ok=True)
                    (dest_rep / nom).write_bytes(payload)
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
        print(json.dumps(resultat, indent=2, ensure_ascii=False))
    finally:
        try:
            client.logout()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    main()
