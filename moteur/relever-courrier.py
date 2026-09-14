"""Outil mécanique de relève du courrier électronique (IMAP).

Ce script est un connecteur réseau pur : il télécharge les pièces jointes brutes
sans aucune logique métier ni classification. L''analyse, la compréhension et la
qualification des fichiers sont assurées par l''agent courrier et l''agent orchestrateur.
"""
import argparse
import email
from email.header import decode_header
import imaplib
import json
import os
import re
from datetime import datetime
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
CONFIG_DEFAUT = RACINE / "donnees" / "courrier-config.json"


def decoder_entete(valeur):
    """Décode un en-tête MIME en chaîne UTF-8 standard."""
    if not valeur:
        return ""
    morceaux = []
    for bout, encodage in decode_header(valeur):
        if isinstance(bout, bytes):
            morceaux.append(bout.decode(encodage or "utf-8", errors="replace"))
        else:
            morceaux.append(str(bout))
    return "".join(morceaux)


def assainir_nom(nom):
    """Nettoie un nom de fichier pour éviter les chemins malveillants."""
    nom = Path(nom).name
    return re.sub(r'[\\/*?:"<>|]', "_", nom).strip()


def charger_configuration(chemin):
    with open(chemin, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def relever(config, simuler=False, marquer_lu=False, tous=False, limite=10, max_taille_mo=50, uid_cible=None):
    host = config["imap_host"]
    port = config.get("imap_port", 993)
    user = config["utilisateur"]
    mdp = config["mot_de_passe"]
    dossier = config.get("dossier", "INBOX")
    autorises = [a.lower().strip() for a in config.get("expediteurs_autorises", [])]
    dest_rep = RACINE / config.get("dossier_destination", "donnees/courrier")

    resultat = {
        "statut": "ok",
        "date_releve": datetime.now().isoformat(),
        "messages_traites": []
    }

    client = imaplib.IMAP4_SSL(host, port)
    try:
        client.login(user, mdp)
        client.select(dossier, readonly=simuler)

        if uid_cible:
            uids = [str(uid_cible).encode("ascii")]
        else:
            critere = "ALL" if tous else "UNSEEN"
            typ, donnees = client.uid("search", None, critere)
            if typ != "OK" or not donnees[0]:
                return resultat

            uids = donnees[0].split()
            uids.sort(key=lambda x: int(x) if x.isdigit() else x)
            if limite:
                uids = uids[-limite:]

        for uid_bytes in uids:
            uid_str = uid_bytes.decode("ascii")
            # Récupération rapide des en-têtes et de la taille sans télécharger tout le corps
            typ_h, donnees_h = client.uid("fetch", uid_bytes, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE MESSAGE-ID)] RFC822.SIZE)")
            if typ_h != "OK" or not donnees_h or not donnees_h[0]:
                continue

            entetes_bruts = donnees_h[0][1]
            taille = 0
            if len(donnees_h) > 1 and isinstance(donnees_h[1], bytes):
                m_taille = re.search(r'RFC822\.SIZE\s+(\d+)', donnees_h[1].decode("ascii", errors="ignore"))
                if m_taille:
                    taille = int(m_taille.group(1))

            msg_h = email.message_from_bytes(entetes_bruts)
            de = decoder_entete(msg_h.get("From", ""))
            sujet = decoder_entete(msg_h.get("Subject", ""))
            message_id = decoder_entete(msg_h.get("Message-ID", f"uid-{uid_str}"))
            date_brute = msg_h.get("Date", "")

            # Extraction de l'adresse email
            correspondance = re.search(r'[\w\.-]+@[\w\.-]+', de)
            email_expediteur = correspondance.group(0).lower() if correspondance else de.lower()

            if autorises and email_expediteur not in autorises:
                continue

            date_reception = datetime.now().strftime("%Y-%m-%d")
            rep_courrier = dest_rep / f"{assainir_nom(email_expediteur)}-{date_reception}"

            info_msg = {
                "uid": uid_str,
                "id": message_id,
                "de": de,
                "expediteur": email_expediteur,
                "sujet": sujet,
                "date": date_reception,
                "date_brute": date_brute,
                "taille_octets": taille,
                "pieces_jointes": []
            }

            if simuler:
                info_msg["statut"] = "simulation_entetes_validees"
                resultat["messages_traites"].append(info_msg)
                continue

            # Vérification de la taille maximale autorisée
            if taille > (max_taille_mo * 1024 * 1024):
                info_msg["erreur"] = f"Message ignoré : taille {taille // 1048576} Mo dépasse le plafond ({max_taille_mo} Mo)"
                resultat["messages_traites"].append(info_msg)
                continue

            typ_c, donnees_msg = client.uid("fetch", uid_bytes, "(BODY.PEEK[])")
            if typ_c != "OK" or not donnees_msg or not donnees_msg[0]:
                continue

            msg = email.message_from_bytes(donnees_msg[0][1])
            corps_texte = ""
            pieces = []

            for partie in msg.walk():
                content_type = partie.get_content_type()
                disposition = str(partie.get("Content-Disposition", ""))

                if content_type == "text/plain" and "attachment" not in disposition:
                    try:
                        payload = partie.get_payload(decode=True)
                        charset = partie.get_content_charset() or "utf-8"
                        corps_texte += payload.decode(charset, errors="replace") + "\n"
                    except Exception:
                        pass

                nom_fichier = partie.get_filename()
                if nom_fichier:
                    nom_fichier = decoder_entete(nom_fichier)
                    nom_propre = assainir_nom(nom_fichier)
                    contenu = partie.get_payload(decode=True)
                    pieces.append((nom_propre, contenu))

            info_msg["texte"] = corps_texte.strip()

            if pieces:
                rep_courrier.mkdir(parents=True, exist_ok=True)
                for nom_f, contenu_f in pieces:
                    if contenu_f is not None:
                        chemin_f = rep_courrier / nom_f
                        chemin_f.write_bytes(contenu_f)
                        info_msg["pieces_jointes"].append(str(chemin_f.resolve()))

            if marquer_lu:
                client.uid("store", uid_bytes, "+FLAGS", "\\Seen")

            resultat["messages_traites"].append(info_msg)

    finally:
        try:
            client.close()
        except Exception:
            pass
        try:
            client.logout()
        except Exception:
            pass

    return resultat


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=CONFIG_DEFAUT, type=Path, help="Fichier de configuration IMAP")
    parser.add_argument("--uid", type=str, default=None, help="UID spécifique du message à relever")
    parser.add_argument("--simuler", action="store_true", help="Lister les messages sans télécharger ni marquer comme lu")
    parser.add_argument("--marquer-lu", action="store_true", help="Marquer les messages téléchargés comme lus")
    parser.add_argument("--tous", action="store_true", help="Rechercher tous les messages (pas seulement les non-lus)")
    parser.add_argument("--limite", type=int, default=10, help="Nombre maximal de messages à relever")
    parser.add_argument("--max-mo", type=int, default=50, help="Taille maximale d'un e-mail en Mo")
    args = parser.parse_args()

    config = charger_configuration(args.config)
    res = relever(config, simuler=args.simuler, marquer_lu=args.marquer_lu, tous=args.tous, limite=args.limite, max_taille_mo=args.max_mo, uid_cible=args.uid)
    print(json.dumps(res, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
