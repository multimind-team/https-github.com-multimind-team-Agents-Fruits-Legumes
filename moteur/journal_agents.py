"""
Le journal des agents — qui a fait quoi, pourquoi, et comment revenir en arrière.

Chaque agent a son propre carnet dans donnees/journaux/<agent>.jsonl, et tout
est aussi recopié dans donnees/journaux/tout.jsonl pour avoir la vue d'ensemble
dans l'ordre du temps.

Trois principes :

  1. Chaque action porte un NUMERO unique et lisible (A-20260902-0007). C'est
     ce numéro que le responsable de rayon donne pour dire « annule celle-là ».
  2. Chaque action enregistre l'AVANT et l'APRES de tout ce qu'elle change.
     Sans l'avant, on ne peut pas revenir en arrière.
  3. On n'efface jamais rien. Annuler, c'est ajouter une ligne qui remet les
     valeurs d'avant, pas gommer la ligne d'origine.

Une action qui échoue est écrite quand même, avec son erreur : un agent
autonome qui se plante en silence est plus dangereux qu'un agent qui ne fait
rien.
"""
import json
import os
import traceback
import errno
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
JOURNAUX = RACINE / "donnees" / "journaux"

# Ces noms de champs sont ceux des réglages d'un article. Un changement
# n'est annulable automatiquement que s'il porte sur l'un d'eux.
CHAMPS_RESTAURABLES = {"groupes", "masque", "promotion", "conditionnement",
                       "fournisseur", "unite"}


_MUTEX = threading.RLock()
_VERROUS_THREAD = threading.local()


@contextmanager
def verrou(timeout=30):
    """Verrou coopératif réentrant : threads ET processus, stdlib seulement.

    Sérialise le contrôle des plafonds, le calcul d'avant/après et les ajouts.
    Ce n'est ni une authentification OS, ni une transaction multi-fichiers.
    """
    cle = str(JOURNAUX.resolve())
    with _MUTEX:
        tenus = getattr(_VERROUS_THREAD, "tenus", set())
        if cle in tenus:
            yield
            return
        JOURNAUX.mkdir(parents=True, exist_ok=True)
        with open(JOURNAUX / ".ecriture.lock", "a+b") as fichier:
            fin = time.monotonic() + timeout
            while True:
                try:
                    fichier.seek(0)
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(fichier.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(fichier.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError as erreur:
                    if erreur.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                        raise
                    if time.monotonic() >= fin:
                        raise TimeoutError("Écriture occupée : aucun changement appliqué par cet appel.") from erreur
                    time.sleep(0.02)
            _VERROUS_THREAD.tenus = tenus
            tenus.add(cle)
            try:
                yield
            finally:
                tenus.remove(cle)
                fichier.seek(0)
                if os.name == "nt":
                    msvcrt.locking(fichier.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(fichier.fileno(), fcntl.LOCK_UN)


def verifier_pouvoirs(agent, actions, fichier):
    """Contrat coopératif : contrôle le rôle déclaré, pas l'identité OS.

    Le caller qui écrit doit garder le verrou pendant contrôle et écriture.
    """
    if not fichier.exists():
        raise SystemExit("Fichier des pouvoirs introuvable : par précaution, rien n'est appliqué.")
    reglement = json.loads(fichier.read_text(encoding="utf-8"))
    profil = reglement.get("agents", {}).get(agent)
    if profil is None:
        raise SystemExit(f"REFUSÉ : agent inconnu « {agent} ».")
    autorisees = set(profil.get("peut_seul", []))
    for action in actions:
        if "*" not in autorisees and action not in autorisees:
            raise SystemExit(f"REFUSÉ : « {agent} » n'a pas le droit de faire « {action} » tout seul.")
    prefixe = datetime.now().strftime("A-%Y%m%d-")
    etats = {l["action"]: l for l in lire() if l.get("action")}
    faites = [l for l in etats.values() if l["action"].startswith(prefixe)
              and l.get("resultat") == "ok"]
    par_agent = sum(l.get("agent") == agent for l in faites)
    plafond = profil.get("plafond_par_jour", 0)
    if plafond <= 0 or par_agent >= plafond:
        raise SystemExit(f"REFUSÉ : plafond quotidien atteint pour « {agent} » ({plafond}).")
    global_max = reglement.get("plafond_par_jour_tous_agents", 999)
    if agent != "responsable-rayon" and len(faites) >= global_max:
        raise SystemExit(f"REFUSÉ : plafond global quotidien atteint ({global_max}).")


def _fichier(agent):
    return JOURNAUX / f"{agent}.jsonl"


def numero_action():
    """Réserve durablement un numéro, même si l'action n'est jamais publiée.

    Les trous après interruption sont normaux. Les anciens journaux restent
    inchangés ; le carnet technique .numeros.jsonl est lui aussi append-only.
    """
    with verrou():
        jour = datetime.now().strftime("%Y%m%d")
        reservations = JOURNAUX / ".numeros.jsonl"
        dernier = 0
        for fichier in (_fichier("tout"), reservations):
            if not fichier.exists():
                continue
            with open(fichier, encoding="utf-8") as f:
                for ligne in f:
                    try:
                        numero = json.loads(ligne).get("action", "")
                        if numero.startswith(f"A-{jour}-"):
                            dernier = max(dernier, int(numero.rsplit("-", 1)[1]))
                    except (json.JSONDecodeError, ValueError):
                        continue
        numero = f"A-{jour}-{dernier + 1:04d}"
        with open(reservations, "a", encoding="utf-8") as f:
            f.write(json.dumps({"action": numero}) + "\n")
            f.flush()
            os.fsync(f.fileno())
        return numero


def _ecrire(agent, ligne):
    with verrou():
        for cible in (agent, "tout"):
            with open(_fichier(cible), "a", encoding="utf-8") as f:
                f.write(json.dumps(ligne, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())   # un agent tourne sans surveillance :
                                       # la trace doit survivre à une coupure.


def enregistrer(agent, message, motif=None, changements=None, details=None,
                action=None, annulable=None, annule_action=None):
    """Écrit une action réussie. Renvoie son numéro.

    changements : liste de {"itm8", "champ", "avant", "apres"}.
                  C'est ce qui rend l'annulation possible.
    """
    changements = changements or []
    restaurable = bool(changements) and all(
        c.get("champ") in CHAMPS_RESTAURABLES and c.get("itm8")
        and "avant" in c and "apres" in c for c in changements)
    annulable = restaurable and annulable is not False
    ligne = {
        "action": action or numero_action(),
        "horodatage": datetime.now().isoformat(timespec="seconds"),
        "agent": agent,
        "resultat": "ok",
        "message": message,
        "motif": motif,
        "changements": changements,
        "annulable": annulable,
    }
    if annule_action:
        ligne["annule_action"] = annule_action
    if details:
        ligne["details"] = details
    _ecrire(agent, ligne)
    return ligne["action"]


def echec(agent, message, exception=None, details=None, action=None):
    """Écrit une action qui a échoué. À appeler dans tout `except`.
    Un agent autonome doit laisser une trace de ses plantages."""
    ligne = {
        "action": action or numero_action(),
        "horodatage": datetime.now().isoformat(timespec="seconds"),
        "agent": agent,
        "resultat": "echec",
        "message": message,
        "erreur": str(exception) if exception else None,
        "trace": traceback.format_exc() if exception else None,
        "annulable": False,
    }
    if details:
        ligne["details"] = details
    _ecrire(agent, ligne)
    return ligne["action"]


def lire(agent="tout", limite=None):
    """Relit un journal, du plus ancien au plus récent."""
    fichier = _fichier(agent)
    if not fichier.exists():
        return []
    lignes = []
    with open(fichier, encoding="utf-8") as f:
        for ligne in f:
            ligne = ligne.strip()
            if ligne:
                try:
                    lignes.append(json.loads(ligne))
                except json.JSONDecodeError:
                    continue
    return lignes[-limite:] if limite else lignes


def actions_annulees(agent="tout", date_calcul=None):
    """Les numéros d'action déjà annulés — on n'annule pas deux fois."""
    jour = date_calcul.isoformat() if hasattr(date_calcul, "isoformat") else date_calcul
    return {l["annule_action"] for l in lire(agent)
            if l.get("annule_action") and l.get("resultat") == "ok"
            and (jour is None or l.get("horodatage", "")[:10] <= jour)}
