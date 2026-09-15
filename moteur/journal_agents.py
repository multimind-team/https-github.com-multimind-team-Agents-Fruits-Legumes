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
import traceback
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
JOURNAUX = RACINE / "donnees" / "journaux"

# Ces noms de champs sont ceux des réglages d'un article. Un changement
# n'est annulable automatiquement que s'il porte sur l'un d'eux.
CHAMPS_RESTAURABLES = {"groupes", "masque", "promotion", "conditionnement",
                       "fournisseur", "unite"}


from verrou_donnees import append_jsonl, verrou_donnees


@contextmanager
def verrou(timeout=120):
    """Verrou partagé avec les importeurs, l'API et les producteurs dérivés."""
    with verrou_donnees(JOURNAUX.parent, timeout=timeout):
        yield


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


def lire_fichier(fichier):
    """Lit entièrement un carnet d'objets JSON ; une erreur n'efface pas une décision.

    Un carnet absent et les lignes vides sont normaux. Une dernière ligne JSON
    complète sans saut final reste lisible ; append_jsonl refuse de la prolonger.
    Les anciens formats d'objet restent acceptés, sans inventer de champs.
    """
    fichier = Path(fichier)
    try:
        flux = fichier.open(encoding="utf-8")
    except FileNotFoundError:
        return []
    lignes = []
    with flux:
        for numero, ligne in enumerate(flux, 1):
            if not ligne.strip():
                continue
            try:
                objet = json.loads(ligne)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Carnet illisible ({fichier.name}), ligne {numero} : JSON invalide. "
                                 "Aucun résultat partiel utilisé ; fichier conservé.") from exc
            if not isinstance(objet, dict):
                raise ValueError(f"Carnet illisible ({fichier.name}), ligne {numero} : objet JSON attendu. "
                                 "Aucun résultat partiel utilisé ; fichier conservé.")
            lignes.append(objet)
    return lignes


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
            for ligne in lire_fichier(fichier):
                numero = ligne.get("action", "")
                if numero.startswith(f"A-{jour}-"):
                    dernier = max(dernier, int(numero.rsplit("-", 1)[1]))
        numero = f"A-{jour}-{dernier + 1:04d}"
        append_jsonl(reservations, [{"action": numero}])
        return numero


def _ecrire(agent, ligne):
    with verrou():
        for cible in (agent, "tout"):
            append_jsonl(_fichier(cible), [ligne])


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
    lignes = lire_fichier(_fichier(agent))
    return lignes[-limite:] if limite else lignes


def actions_annulees(agent="tout", date_calcul=None):
    """Les numéros d'action déjà annulés — on n'annule pas deux fois."""
    jour = date_calcul.isoformat() if hasattr(date_calcul, "isoformat") else date_calcul
    return {l["annule_action"] for l in lire(agent)
            if l.get("annule_action") and l.get("resultat") == "ok"
            and (jour is None or l.get("horodatage", "")[:10] <= jour)}
