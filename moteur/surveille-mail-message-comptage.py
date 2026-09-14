"""
moteur/surveille-mail-message-comptage.py - Sentinelle passive unifiée (0 token).

Ce script s'exécute en tâche de fond sur le PC local (0 token consommé).
Il surveille simultanément :
1. L'arrivée de nouveaux courriels sur la boîte Gmail (IMAP).
2. L'arrivée de nouveaux messages envoyés depuis l'application mobile (donnees/messages.jsonl).
3. L'arrivée de nouveaux comptages envoyés depuis la chambre froide (donnees/faits/AAAA.jsonl).

Dès qu'un événement survient :
- Il identifie la nature exacte de l'événement :
  * EVENEMENT: MAIL
  * EVENEMENT: MESSAGE
  * EVENEMENT: COMPTAGE
- Il affiche les détails essentiels.
- Il met à jour les registres d'identification.
- Il se termine immédiatement avec le code 0.

La fin du processus réveille instantanément l'agent dans Antigravity, qui prend
le relais selon la nature de l'événement :
- Mail : intégration des flux, contrôle et note du matin.
- Message : réponse de l'agent rayon dans le chat.
- Comptage : audit et explication des écarts par agent-audit-stock.
Puis l'agent relance la sentinelle.
"""
import argparse
from datetime import datetime, date
import email
from email.header import decode_header
import imaplib
import json
import os
from pathlib import Path
import sys
import time

RACINE = Path(__file__).resolve().parent.parent
DONNEES = RACINE / "donnees"
DOSSIER_FAITS = DONNEES / "faits"
CONFIG_PATH = DONNEES / "courrier-config.json"
REGISTRE_UIDS = DONNEES / ".courrier_uids_connus.json"
MESSAGES_PATH = DONNEES / "messages.jsonl"


def decoder_entete(valeur):
    """Décode un en-tête MIME en chaîne standard."""
    if not valeur:
        return ""
    morceaux = []
    for bout, encodage in decode_header(valeur):
        if isinstance(bout, bytes):
            morceaux.append(bout.decode(encodage or "utf-8", errors="replace"))
        else:
            morceaux.append(str(bout))
    return "".join(morceaux)


def charger_uids_connus():
    """Charge l'ensemble des UIDs déjà vus dans la boîte mail."""
    if REGISTRE_UIDS.exists():
        try:
            with open(REGISTRE_UIDS, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except (json.JSONDecodeError, OSError):
            pass
    return set()


def sauvegarder_uids_connus(uids):
    """Sauvegarde la liste des UIDs connus."""
    try:
        with open(REGISTRE_UIDS, "w", encoding="utf-8") as f:
            json.dump(sorted(list(uids), key=lambda x: int(x) if x.isdigit() else x), f)
    except OSError:
        pass


def initialiser_uids_si_vide(client):
    """Si le registre n'existe pas encore, enregistre tous les messages actuels comme déjà connus."""
    connus = charger_uids_connus()
    if not connus:
        typ, donnees = client.uid("search", None, "ALL")
        if typ == "OK" and donnees[0]:
            connus = {u.decode("ascii") for u in donnees[0].split()}
            sauvegarder_uids_connus(connus)
            print(f"SURVEILLE: Initialisation du registre mail avec {len(connus)} messages existants.", flush=True)
    return connus


def verifier_boite_mail(config, connus_uids):
    """Vérifie la boîte mail une fois. Retourne (nouveaux_details, connus_uids)."""
    host = config["imap_host"]
    port = config.get("imap_port", 993)
    user = config["utilisateur"]
    mdp = config["mot_de_passe"]
    dossier = config.get("dossier", "INBOX")

    client = imaplib.IMAP4_SSL(host, port, timeout=15)
    try:
        client.login(user, mdp)
        client.select(dossier, readonly=True)

        if not connus_uids:
            connus_uids = initialiser_uids_si_vide(client)

        typ, donnees = client.uid("search", None, "ALL")
        if typ != "OK" or not donnees[0]:
            return None, connus_uids

        actuels = {u.decode("ascii") for u in donnees[0].split()}
        nouveaux_uids = actuels - connus_uids

        if not nouveaux_uids:
            return None, connus_uids

        nouveaux_details = []
        for uid_str in sorted(nouveaux_uids, key=lambda x: int(x) if x.isdigit() else x):
            typ_h, donnees_h = client.uid("fetch", uid_str.encode("ascii"), "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE MESSAGE-ID)])")
            de, sujet, date_msg = "Inconnu", "Sans sujet", ""
            if typ_h == "OK" and donnees_h and donnees_h[0]:
                entetes_bruts = donnees_h[0][1]
                if isinstance(entetes_bruts, bytes):
                    msg_h = email.message_from_bytes(entetes_bruts)
                    de = decoder_entete(msg_h.get("From", ""))
                    sujet = decoder_entete(msg_h.get("Subject", ""))
                    date_msg = decoder_entete(msg_h.get("Date", ""))
            nouveaux_details.append({
                "uid": uid_str,
                "de": de,
                "sujet": sujet,
                "date": date_msg,
            })
            connus_uids.add(uid_str)

        sauvegarder_uids_connus(connus_uids)
        return nouveaux_details, connus_uids
    finally:
        try:
            client.logout()
        except Exception:
            pass


def charger_identifiants_messages(chemin=MESSAGES_PATH):
    """Charge l'ensemble des identifiants de messages du chat déjà présents."""
    connus = set()
    if not chemin.exists():
        return connus
    try:
        with open(chemin, "r", encoding="utf-8", errors="replace") as f:
            for ligne in f:
                ligne = ligne.strip()
                if not ligne:
                    continue
                try:
                    obj = json.loads(ligne)
                    identifiant = obj.get("id")
                    if identifiant:
                        connus.add(identifiant)
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return connus


def verifier_nouveaux_messages(chemin, connus_messages):
    """Vérifie si de nouvelles lignes sont apparues dans messages.jsonl."""
    if not chemin.exists():
        return None, connus_messages

    nouveaux = []
    try:
        with open(chemin, "r", encoding="utf-8", errors="replace") as f:
            for ligne in f:
                ligne = ligne.strip()
                if not ligne:
                    continue
                try:
                    obj = json.loads(ligne)
                    identifiant = obj.get("id")
                    if identifiant and identifiant not in connus_messages:
                        nouveaux.append(obj)
                        connus_messages.add(identifiant)
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass

    if nouveaux:
        return nouveaux, connus_messages
    return None, connus_messages


def chemin_faits_annee():
    annee = date.today().year
    return DOSSIER_FAITS / f"{annee}.jsonl"


def charger_identifiants_comptages(chemin=None):
    """Charge l'ensemble des IDs de comptages existants."""
    chemin = chemin or chemin_faits_annee()
    connus = set()
    if not chemin.exists():
        return connus
    try:
        with open(chemin, "r", encoding="utf-8", errors="replace") as f:
            for ligne in f:
                if not ligne.strip():
                    continue
                if '"type": "comptage"' in ligne or '"type":"comptage"' in ligne:
                    try:
                        obj = json.loads(ligne)
                        if obj.get("type") == "comptage":
                            c_id = obj.get("id")
                            if c_id:
                                connus.add(c_id)
                    except json.JSONDecodeError:
                        pass
    except OSError:
        pass
    return connus


def verifier_nouveaux_comptages(chemin, connus_comptages):
    """Vérifie si de nouveaux comptages sont apparus dans faits/AAAA.jsonl."""
    if not chemin.exists():
        return None, connus_comptages

    nouveaux = []
    try:
        with open(chemin, "r", encoding="utf-8", errors="replace") as f:
            for ligne in f:
                if not ligne.strip():
                    continue
                if '"type": "comptage"' in ligne or '"type":"comptage"' in ligne:
                    try:
                        obj = json.loads(ligne)
                        if obj.get("type") == "comptage":
                            c_id = obj.get("id")
                            if c_id and c_id not in connus_comptages:
                                nouveaux.append(obj)
                                connus_comptages.add(c_id)
                    except json.JSONDecodeError:
                        pass
    except OSError:
        pass

    if nouveaux:
        return nouveaux, connus_comptages
    return None, connus_comptages


def surveiller(intervalle_mail=30.0, intervalle_rapide=2.0, timeout=None):
    """Boucle unifiée de surveillance passive tri-événements (0 token)."""
    config_mail = None
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8-sig") as f:
                config_mail = json.load(f)
        except Exception as e:
            print(f"SURVEILLE: Avertissement - impossible de charger {CONFIG_PATH} ({e})", file=sys.stderr)

    connus_uids = charger_uids_connus() if config_mail else set()
    connus_messages = charger_identifiants_messages(MESSAGES_PATH)
    chemin_faits = chemin_faits_annee()
    connus_comptages = charger_identifiants_comptages(chemin_faits)

    cible_mail = config_mail["utilisateur"] if config_mail else "Désactivée"
    print(f"SURVEILLE-MAIL-MESSAGE-COMPTAGE: Actif.", flush=True)
    print(f"  - Surveillance Mail : {cible_mail} (intervalle: {intervalle_mail}s)", flush=True)
    print(f"  - Surveillance Chat : {MESSAGES_PATH.name} ({len(connus_messages)} messages existants ignores, intervalle: {intervalle_rapide}s)", flush=True)
    print(f"  - Surveillance Comptage : {chemin_faits.name} ({len(connus_comptages)} comptages existants ignores, intervalle: {intervalle_rapide}s)", flush=True)

    debut = time.time()
    dernier_check_mail = 0.0

    while True:
        maintenant = time.time()
        if timeout and (maintenant - debut) > timeout:
            print("SURVEILLE: Timeout atteint sans nouvel événement.", flush=True)
            return 0

        # 1. Vérification des messages du rayon (prioritaire et rapide)
        try:
            nouveaux_msg, connus_messages = verifier_nouveaux_messages(MESSAGES_PATH, connus_messages)
            if nouveaux_msg:
                print("\nEVENEMENT: MESSAGE", flush=True)
                print(f"NOUVEAU_MESSAGE_RAYON: {len(nouveaux_msg)} message(s) recu(s) !", flush=True)
                for msg in nouveaux_msg:
                    ident = msg.get("id")
                    print(f"- ID: {ident} | Date: {msg.get('ecrit_le') or msg.get('recu_le')} | Texte: {msg.get('texte')}", flush=True)
                    if ident:
                        try:
                            import dire
                            dire.publier("Message en cours de traitement...", auteur="Assistant", en_reponse_a=ident)
                        except Exception:
                            pass
                return 0
        except Exception as err:
            print(f"SURVEILLE: Erreur vérification message ({err})", flush=True)

        # 2. Vérification des comptages en chambre froide (prioritaire et rapide)
        try:
            nouveaux_cpt, connus_comptages = verifier_nouveaux_comptages(chemin_faits, connus_comptages)
            if nouveaux_cpt:
                print("\nEVENEMENT: COMPTAGE", flush=True)
                print(f"NOUVEAU_COMPTAGE: {len(nouveaux_cpt)} comptage(s) recu(s) depuis la chambre froide !", flush=True)
                for cpt in nouveaux_cpt:
                    print(f"- Article: {cpt.get('article')} | Libelle: {cpt.get('libelle')} | {cpt.get('colis')} colis ({cpt.get('quantite')} {cpt.get('unite', 'unites')})", flush=True)
                return 0
        except Exception as err:
            print(f"SURVEILLE: Erreur vérification comptage ({err})", flush=True)

        # 3. Vérification des courriels IMAP
        if config_mail and (maintenant - dernier_check_mail) >= intervalle_mail:
            dernier_check_mail = maintenant
            try:
                nouveaux_mails, connus_uids = verifier_boite_mail(config_mail, connus_uids)
                if nouveaux_mails:
                    print("\nEVENEMENT: MAIL", flush=True)
                    print(f"NOUVEAU_MAIL_RECU: {len(nouveaux_mails)} mail(s) detecte(s) !", flush=True)
                    for m in nouveaux_mails:
                        print(f"- UID {m['uid']} | De: {m['de']} | Sujet: {m['sujet']}", flush=True)
                    return 0
            except Exception as err:
                print(f"SURVEILLE: Erreur réseau IMAP temporaire ({err}), nouvelle tentative au prochain cycle...", flush=True)

        time.sleep(intervalle_rapide)


def main():
    parser = argparse.ArgumentParser(description="Surveiller la boîte mail, le chat et les comptages pour réveil de l'agent.")
    parser.add_argument("--intervalle-mail", type=float, default=30.0, help="Intervalle entre chaque vérification mail en secondes (défaut: 30s)")
    parser.add_argument("--intervalle-rapide", type=float, default=2.0, help="Intervalle entre chaque vérification chat/comptage en secondes (défaut: 2s)")
    parser.add_argument("--timeout", type=float, default=None, help="Délai maximum d'écoute en secondes (optionnel)")
    parser.add_argument("--verifier-maintenant", action="store_true", help="Vérifie immédiatement une fois et sort")
    args = parser.parse_args()

    if args.verifier_maintenant:
        return surveiller(intervalle_mail=0, intervalle_rapide=0, timeout=1)

    return surveiller(intervalle_mail=args.intervalle_mail, intervalle_rapide=args.intervalle_rapide, timeout=args.timeout)


if __name__ == "__main__":
    sys.exit(main() or 0)
