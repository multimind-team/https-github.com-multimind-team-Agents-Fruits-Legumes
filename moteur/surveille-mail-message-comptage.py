"""Sentinelle locale : file durable, détection sans acquittement implicite.

Le processus signale EVENEMENT puis sort. Le réveil de l'agent dépend du
superviseur externe ; ce script ne crée ni agent, ni automatisation.
Après traitement vérifié seulement : --acquitter TYPE ID --preuve REFERENCE.
Sans acquittement, l'événement reste disponible au redémarrage.
"""
import argparse
from datetime import datetime, date
import email
from email.header import decode_header
import hashlib
import imaplib
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config_courrier import charger_config_courrier
from ecriture_derivee import ecrire_json
from verrou_donnees import verrou_donnees

RACINE = Path(__file__).resolve().parent.parent
DONNEES = RACINE / "donnees"
DOSSIER_FAITS = DONNEES / "faits"
CONFIG_PATH = DONNEES / "courrier-config.json"
REGISTRE_UIDS = DONNEES / ".courrier_uids_connus.json"  # Ancien registre conservé, pas un acquittement.
MESSAGES_PATH = DONNEES / "messages.jsonl"
TYPES_COMPTAGE = {"comptage", "correction-comptage"}


def decoder_entete(valeur):
    morceaux = []
    for bout, encodage in decode_header(valeur or ""):
        morceaux.append(bout.decode(encodage or "utf-8", errors="replace")
                        if isinstance(bout, bytes) else str(bout))
    return "".join(morceaux)


def lire_jsonl(chemin):
    chemin = Path(chemin)
    if not chemin.exists():
        return []
    objets = []
    with chemin.open(encoding="utf-8") as flux:
        for numero, ligne in enumerate(flux, 1):
            if not ligne.strip():
                continue
            try:
                objet = json.loads(ligne)
                if not isinstance(objet, dict):
                    raise ValueError("objet attendu")
            except ValueError as erreur:
                raise ValueError(f"{chemin.name} ligne {numero} illisible : {erreur}") from erreur
            objets.append(objet)
    return objets


def charger_identifiants_messages(chemin=MESSAGES_PATH):
    return {o["id"] for o in lire_jsonl(chemin) if o.get("id")}


def verifier_nouveaux_messages(chemin, connus_messages):
    nouveaux = [o for o in lire_jsonl(chemin) if o.get("id") and o["id"] not in connus_messages]
    return nouveaux or None, set(connus_messages)


def chemin_faits_annee():
    return DOSSIER_FAITS / f"{date.today().year}.jsonl"


def charger_identifiants_comptages(chemin=None):
    return {o["id"] for o in lire_jsonl(chemin or chemin_faits_annee())
            if o.get("type") in TYPES_COMPTAGE and o.get("id")}


def verifier_nouveaux_comptages(chemin, connus_comptages):
    nouveaux = [o for o in lire_jsonl(chemin) if o.get("type") in TYPES_COMPTAGE
                and o.get("id") and o["id"] not in connus_comptages]
    return nouveaux or None, set(connus_comptages)


def verifier_boite_mail(config, connus_uids):
    """UID qualifié par compte, dossier et UIDVALIDITY, sans le marquer traité."""
    client = imaplib.IMAP4_SSL(config["imap_host"], config.get("imap_port", 993), timeout=15)
    try:
        client.login(config["utilisateur"], config["mot_de_passe"])
        dossier = config.get("dossier", "INBOX")
        typ, _ = client.select(dossier, readonly=True)
        if typ != "OK":
            raise ValueError("Dossier IMAP inaccessible")
        _, validite = client.response("UIDVALIDITY")
        if not validite or not validite[0]:
            raise ValueError("UIDVALIDITY absent : identité IMAP non vérifiable")
        scope = hashlib.sha256(json.dumps([config["imap_host"], config["utilisateur"],
            dossier, validite[0].decode("ascii")]).encode()).hexdigest()[:20]
        typ, donnees = client.uid("search", None, "ALL")
        if typ != "OK":
            raise ValueError("Recherche IMAP échouée")
        nouveaux = []
        for uid in sorted((donnees[0] or b"").split(), key=int):
            identifiant = scope + ":" + uid.decode("ascii")
            if identifiant in connus_uids:
                continue
            typ, reponse = client.uid("fetch", uid, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE MESSAGE-ID)])")
            if typ != "OK" or not reponse or not isinstance(reponse[0], tuple):
                raise ValueError("En-têtes IMAP indisponibles ; message non acquitté")
            msg = email.message_from_bytes(reponse[0][1])
            nouveaux.append({"id": identifiant, "uid": uid.decode("ascii"),
                "de": decoder_entete(msg.get("From")), "sujet": decoder_entete(msg.get("Subject")),
                "date": decoder_entete(msg.get("Date")), "message_id": decoder_entete(msg.get("Message-ID"))})
        return nouveaux or None, set(connus_uids)
    finally:
        try:
            client.logout()
        except Exception:
            pass


def charger_file():
    chemin = DONNEES / ".sentinelle-evenements.json"
    if not chemin.exists():
        return {"version": 1, "en_attente": {}, "acquittes": {}}
    resultat = json.loads(chemin.read_text(encoding="utf-8"))
    if (resultat.get("version") != 1 or not isinstance(resultat.get("en_attente"), dict)
            or not isinstance(resultat.get("acquittes"), dict)):
        raise ValueError("Registre sentinelle invalide : aucune remise à zéro automatique")
    return resultat


def enregistrer_evenements(evenements):
    with verrou_donnees(DONNEES):
        file = charger_file()
        for type_evenement, objet in evenements:
            cle = type_evenement + ":" + str(objet["id"])
            if cle not in file["acquittes"]:
                file["en_attente"].setdefault(cle, {"type": type_evenement, "id": str(objet["id"]),
                    "detecte_le": datetime.now().isoformat(timespec="seconds"), "contenu": objet})
        ecrire_json(DONNEES / ".sentinelle-evenements.json", file)
        return file


def acquitter(type_evenement, identifiant, preuve):
    if not preuve or not preuve.strip():
        raise ValueError("Référence du traitement vérifié obligatoire")
    with verrou_donnees(DONNEES):
        file = charger_file()
        cle = type_evenement + ":" + identifiant
        if cle not in file["en_attente"]:
            if cle in file["acquittes"]:
                return file["acquittes"][cle]
            raise ValueError("Événement inconnu : aucun acquittement")
        trace = {"traite_le": datetime.now().isoformat(timespec="seconds"), "preuve": preuve}
        file["acquittes"][cle] = trace
        del file["en_attente"][cle]
        ecrire_json(DONNEES / ".sentinelle-evenements.json", file)
        return trace


def surveiller(intervalle_mail=30.0, intervalle_rapide=2.0, timeout=None, une_fois=False):
    config = charger_config_courrier(CONFIG_PATH) if CONFIG_PATH.exists() else None
    debut, dernier_mail = time.monotonic(), None
    cache = {}
    print("SENTINELLE : attente d'événements ; acquittement explicite après traitement.", flush=True)
    while True:
        file = charger_file()
        connus = set(file["acquittes"]) | set(file["en_attente"])
        evenements, erreurs = [], []
        chemins = [("MESSAGE", MESSAGES_PATH)] + [("COMPTAGE", p) for p in sorted(DOSSIER_FAITS.glob("*.jsonl"))]
        for type_evt, chemin in chemins:
            try:
                signature = (chemin.stat().st_mtime_ns, chemin.stat().st_size) if chemin.exists() else None
                if cache.get(chemin) != signature or chemin not in cache:
                    objets = lire_jsonl(chemin)
                    for objet in objets:
                        if type_evt == "COMPTAGE" and objet.get("type") not in TYPES_COMPTAGE:
                            continue
                        if objet.get("id") and type_evt + ":" + str(objet["id"]) not in connus:
                            evenements.append((type_evt, objet))
                    cache[chemin] = signature
            except (OSError, ValueError) as erreur:
                erreurs.append(str(erreur))
        maintenant = time.monotonic()
        if config and (dernier_mail is None or maintenant - dernier_mail >= intervalle_mail):
            dernier_mail = maintenant
            try:
                messages, _ = verifier_boite_mail(config, {c[5:] for c in connus if c.startswith("MAIL:")})
                evenements.extend(("MAIL", message) for message in messages or [])
            except Exception as erreur:
                erreurs.append("Vérification IMAP : " + str(erreur))
        if evenements:
            file = enregistrer_evenements(evenements)
        for erreur in erreurs:
            print("ERREUR SENTINELLE : " + erreur, file=sys.stderr, flush=True)
        if file["en_attente"]:
            for evenement in file["en_attente"].values():
                print("EVENEMENT: " + evenement["type"], flush=True)
                print(json.dumps(evenement, ensure_ascii=True), flush=True)
            return 0
        if une_fois or (timeout is not None and time.monotonic() - debut >= timeout):
            return 2 if erreurs else 0
        time.sleep(max(0.1, intervalle_rapide))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--intervalle-mail", type=float, default=30)
    parser.add_argument("--intervalle-rapide", type=float, default=2)
    parser.add_argument("--timeout", type=float)
    parser.add_argument("--verifier-maintenant", action="store_true")
    parser.add_argument("--acquitter", nargs=2, metavar=("TYPE", "ID"))
    parser.add_argument("--preuve", help="Référence du message de réponse ou du contrôle achevé")
    args = parser.parse_args()
    if args.acquitter:
        type_evt, identifiant = args.acquitter
        if type_evt not in {"MAIL", "MESSAGE", "COMPTAGE"}:
            parser.error("TYPE doit être MAIL, MESSAGE ou COMPTAGE")
        print(json.dumps(acquitter(type_evt, identifiant, args.preuve), ensure_ascii=True))
        return 0
    return surveiller(args.intervalle_mail, args.intervalle_rapide, args.timeout, args.verifier_maintenant)


if __name__ == "__main__":
    raise SystemExit(main())
