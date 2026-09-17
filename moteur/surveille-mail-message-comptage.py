"""Sentinelle locale : file durable, détection sans acquittement implicite.

Le processus signale EVENEMENT puis sort. Le réveil de l'agent dépend du
superviseur externe ; ce script ne crée ni agent, ni automatisation.
Après traitement vérifié seulement : --acquitter TYPE ID --preuve REFERENCE.
Sans acquittement, l'événement reste disponible au redémarrage.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, date
import email
from email.header import decode_header
import errno
import hashlib
import imaplib
import json
import math
import os
from pathlib import Path
import sys
import threading
import time
import uuid

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


class SentinelleDejaActive(RuntimeError):
    """Une autre instance détient le verrou de cette installation."""


class ArretDemande(RuntimeError):
    """Le gestionnaire a demandé l'arrêt, sans acquitter d'événement."""


def chemin_etat_sentinelle():
    return Path(DONNEES).resolve() / ".sentinelle-etat.json"


def chemin_verrou_sentinelle():
    return Path(DONNEES).resolve().parent / ".sentinelle.lock"


def verifier_arret():
    if (Path(DONNEES).resolve().parent / ".serveur-arrete").exists():
        raise ArretDemande()


@contextmanager
def verrou_sentinelle():
    """Singleton OS non bloquant ; ne supprime jamais le fichier verrouillé.

    Ce verrou n'est ni réentrant ni hérité des calculs : une seule surveillance
    doit détenir son propre descripteur. Les acquittements ne le prennent pas.
    """
    chemin = chemin_verrou_sentinelle()
    chemin.parent.mkdir(parents=True, exist_ok=True)
    with chemin.open("a+b") as flux:
        try:
            flux.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(flux.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(flux.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            if exc.errno in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                raise SentinelleDejaActive("Une sentinelle est déjà active.") from None
            raise
        try:
            yield
        finally:
            flux.seek(0)
            if os.name == "nt":
                msvcrt.locking(flux.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(flux.fileno(), fcntl.LOCK_UN)


def nombre_positif_fini(valeur):
    try:
        nombre = float(valeur)
    except (TypeError, ValueError, OverflowError):
        raise ValueError("Un nombre fini strictement positif est requis.") from None
    if isinstance(valeur, bool) or not math.isfinite(nombre) or nombre <= 0:
        raise ValueError("Un nombre fini strictement positif est requis.")
    return nombre


class SuiviSentinelle:
    """État privé minimal, sans événements, configuration ni texte d'exception.

    Le battement reste actif pendant une lecture IMAP ou un parcours de carnet.
    Il prouve l'existence du processus ; les dates par source prouvent les
    vérifications achevées. Ce fil auxiliaire s'arrête avec cette exécution.
    """

    def __init__(self, intervalle):
        self._mutex = threading.RLock()
        self._fin = threading.Event()
        self._erreur_publication = False
        self._intervalle = max(1.0, min(5.0, intervalle))
        maintenant = datetime.now().astimezone().isoformat(timespec="seconds")
        self.contenu = {
            "version": 1, "pid": os.getpid(), "id_execution": uuid.uuid4().hex,
            "demarre_le": maintenant, "battement_le": maintenant,
            "termine_le": None, "etat": "demarrage", "erreur": None,
            "sources": {nom: {"etat": "non_verifie", "derniere_verification_le": None,
                               "dernier_succes_le": None, "erreur": None}
                        for nom in ("mail", "messages", "comptages")},
        }
        chemin_etat_sentinelle().parent.mkdir(parents=True, exist_ok=True)
        self.publier("demarrage")
        self._fil = threading.Thread(target=self._battre, name="battement-sentinelle", daemon=True)
        self._fil.start()

    def publier(self, etat=None, *, termine=False, erreur=None):
        with self._mutex:
            maintenant = datetime.now().astimezone().isoformat(timespec="seconds")
            self.contenu["battement_le"] = maintenant
            if etat is not None:
                self.contenu.update(etat=etat, erreur=erreur)
            if termine:
                self.contenu["termine_le"] = maintenant
            ecrire_json(chemin_etat_sentinelle(), self.contenu, avec_operation=False)

    def source(self, nom, etat, erreur=None):
        with self._mutex:
            maintenant = datetime.now().astimezone().isoformat(timespec="seconds")
            source = self.contenu["sources"][nom]
            source.update(etat=etat, derniere_verification_le=maintenant, erreur=erreur)
            if etat == "ok":
                source["dernier_succes_le"] = maintenant
            self.publier()

    def _battre(self):
        while not self._fin.wait(self._intervalle):
            try:
                self.publier()
            except Exception:
                self._erreur_publication = True
                self._fin.set()
                return

    def verifier_publication(self):
        if self._erreur_publication:
            raise OSError("Suivi de la sentinelle indisponible.")

    def fermer(self):
        self._fin.set()
        self._fil.join()


def configuration_mail():
    """Distingue absence/désactivation et configuration illisible sans exposer ses valeurs."""
    if not CONFIG_PATH.exists():
        return None
    brut = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
    if not isinstance(brut, dict):
        raise ValueError("Configuration courrier invalide.")
    if "actif" in brut and not isinstance(brut["actif"], bool):
        raise ValueError("Activation courrier invalide.")
    if brut.get("actif") is False:
        return None
    config = charger_config_courrier(CONFIG_PATH)
    if not all(isinstance(config.get(cle), str) and config[cle].strip()
               for cle in ("imap_host", "utilisateur", "mot_de_passe")):
        return None
    return config


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


def verifier_boite_mail(config, connus_uids, verifier_arret=None):
    """UID qualifié par compte, dossier et UIDVALIDITY, sans le marquer traité."""
    if verifier_arret:
        verifier_arret()
    client = imaplib.IMAP4_SSL(config["imap_host"], config.get("imap_port", 993), timeout=15)
    try:
        if verifier_arret:
            verifier_arret()
        client.login(config["utilisateur"], config["mot_de_passe"])
        if verifier_arret:
            verifier_arret()
        dossier = config.get("dossier", "INBOX")
        typ, _ = client.select(dossier, readonly=True)
        if typ != "OK":
            raise ValueError("Dossier IMAP inaccessible")
        if verifier_arret:
            verifier_arret()
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
            if verifier_arret:
                verifier_arret()
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


def _surveiller(suivi, intervalle_mail, intervalle_rapide, timeout, une_fois):
    debut, dernier_mail = time.monotonic(), None
    cache = {}
    erreurs_signalees = set()
    print("SENTINELLE : attente d'événements ; acquittement explicite après traitement.", flush=True)
    while True:
        verifier_arret()
        suivi.verifier_publication()
        file = charger_file()
        connus = set(file["acquittes"]) | set(file["en_attente"])
        evenements = []
        erreurs_locales = {}
        chemins = [("MESSAGE", MESSAGES_PATH)]
        try:
            chemins.extend(("COMPTAGE", p) for p in sorted(DOSSIER_FAITS.glob("*.jsonl")))
        except OSError:
            erreurs_locales["comptages"] = "Lecture des comptages indisponible."
        for type_evt, chemin in chemins:
            verifier_arret()
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
            except (OSError, ValueError):
                nom = "messages" if type_evt == "MESSAGE" else "comptages"
                erreurs_locales[nom] = "Lecture des messages indisponible." if nom == "messages" else "Lecture des comptages indisponible."
        for nom in ("messages", "comptages"):
            suivi.source(nom, "erreur" if nom in erreurs_locales else "ok", erreurs_locales.get(nom))
        maintenant = time.monotonic()
        if dernier_mail is None or maintenant - dernier_mail >= intervalle_mail:
            dernier_mail = maintenant
            try:
                config = configuration_mail()
                if config is None:
                    suivi.source("mail", "non_configure")
                else:
                    messages, _ = verifier_boite_mail(config, {c[5:] for c in connus if c.startswith("MAIL:")},
                                                       verifier_arret=verifier_arret)
                    evenements.extend(("MAIL", message) for message in messages or [])
                    suivi.source("mail", "ok")
            except ArretDemande:
                raise
            except Exception:
                suivi.source("mail", "erreur", "Vérification du courrier indisponible.")
        verifier_arret()
        suivi.verifier_publication()
        if evenements:
            file = enregistrer_evenements(evenements)
        erreurs = [s["erreur"] for s in suivi.contenu["sources"].values() if s["etat"] == "erreur"]
        for erreur in erreurs:
            if erreur not in erreurs_signalees:
                print("ERREUR SENTINELLE : " + erreur, file=sys.stderr, flush=True)
        erreurs_signalees = set(erreurs)
        verifier_arret()
        if file["en_attente"]:
            suivi.publier("evenements", termine=True)
            for evenement in file["en_attente"].values():
                print("EVENEMENT: " + evenement["type"], flush=True)
                print(json.dumps(evenement, ensure_ascii=True), flush=True)
            return 0
        if une_fois or (timeout is not None and time.monotonic() - debut >= timeout):
            suivi.publier("erreur" if erreurs else "arrete", termine=True,
                          erreur="Une source de surveillance est indisponible." if erreurs else None)
            return 2 if erreurs else 0
        suivi.publier("erreur" if erreurs else "ecoute",
                      erreur="Une source de surveillance est indisponible." if erreurs else None)
        fin_attente = time.monotonic() + max(0.1, intervalle_rapide)
        if timeout is not None:
            fin_attente = min(fin_attente, debut + timeout)
        while time.monotonic() < fin_attente:
            verifier_arret()
            suivi.verifier_publication()
            time.sleep(min(0.2, max(0.0, fin_attente - time.monotonic())))


def surveiller(intervalle_mail=30.0, intervalle_rapide=2.0, timeout=None, une_fois=False):
    intervalle_mail = nombre_positif_fini(intervalle_mail)
    intervalle_rapide = nombre_positif_fini(intervalle_rapide)
    timeout = nombre_positif_fini(timeout) if timeout is not None else None
    suivi = None
    try:
        with verrou_sentinelle():
            try:
                suivi = SuiviSentinelle(intervalle_rapide)
                return _surveiller(suivi, intervalle_mail, intervalle_rapide, timeout, une_fois)
            except (ArretDemande, KeyboardInterrupt):
                if suivi:
                    try:
                        suivi.publier("arrete", termine=True)
                    except Exception:
                        print("ERREUR SENTINELLE : arrêt demandé, état final indisponible.", file=sys.stderr, flush=True)
                return 3
            except Exception:
                print("ERREUR SENTINELLE : surveillance indisponible ; aucun acquittement effectué.", file=sys.stderr, flush=True)
                if suivi:
                    try:
                        suivi.publier("erreur", termine=True, erreur="Surveillance indisponible.")
                    except Exception:
                        pass  # Le stderr reste disponible si le disque refuse aussi le statut.
                return 2
            finally:
                if suivi:
                    suivi.fermer()
    except SentinelleDejaActive:
        print("ERREUR SENTINELLE : une sentinelle est déjà active.", file=sys.stderr, flush=True)
        return 4
    except OSError:
        print("ERREUR SENTINELLE : suivi ou verrou de surveillance indisponible.", file=sys.stderr, flush=True)
        return 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--intervalle-mail", type=nombre_positif_fini, default=30)
    parser.add_argument("--intervalle-rapide", type=nombre_positif_fini, default=2)
    parser.add_argument("--timeout", type=nombre_positif_fini)
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
