"""Corrige uniquement la conversion d'un comptage explicitement confirmé.

Maintenance append-only, distincte de l'API des nouveaux relevés. Conserve
les colis, l'instant et la source de la mesure. Ne lance aucun recalcul.
Les autres écrivains de faits doivent rester inactifs : le verrou des agents
ne coordonne pas le verrou en mémoire de l'API comptages. La relecture avant
et après publication détecte les changements, sans promettre de transaction.
"""
import argparse
import copy
import hashlib
import json
import math
import os
import re
import sys
from contextlib import nullcontext
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import journal_agents as carnet_agents

RACINE = Path(__file__).resolve().parent.parent
DOSSIER_FAITS = RACINE / "donnees" / "faits"
POUVOIRS = RACINE / "donnees" / "pouvoirs.json"


def instantane():
    return {p: p.read_bytes() for p in sorted(DOSSIER_FAITS.glob("*.jsonl"))}


def lignes(snapshot):
    resultat = []
    for p, contenu in snapshot.items():
        for numero, ligne in enumerate(contenu.decode("utf-8").splitlines(), 1):
            if not ligne.strip():
                continue
            fait = json.loads(ligne)
            if not isinstance(fait, dict):
                raise ValueError(f"Objet JSON attendu : {p.name}:{numero}.")
            json.dumps(fait, allow_nan=False)  # Refuse aussi NaN/Infinity imbriqués.
            resultat.append((p, fait))
    return resultat


def preparer(args, snapshot):
    if not re.fullmatch(r"comptage:[0-9]{4}-[0-9]{2}-[0-9]{2}:[0-9]{13}:saisie", args.cible_id):
        raise ValueError("Identifiant invalide : comptage:AAAA-MM-JJ:<code exact à 13 chiffres>:saisie attendu.")
    toutes = lignes(snapshot)
    cibles = [(p, f) for p, f in toutes if f.get("id") == args.cible_id]
    if len(cibles) != 1:
        raise ValueError("Le comptage cible doit exister exactement une fois.")
    chemin, original = cibles[0]
    if original.get("type") != "comptage" or original.get("mesure") != "position":
        raise ValueError("La cible doit être un comptage original de position.")
    jour = original.get("date_source")
    if not isinstance(jour, str) or date.fromisoformat(jour).isoformat() != jour:
        raise ValueError("Date du comptage invalide.")
    if original.get("date_effet") != jour or original.get("id") != f"comptage:{jour}:{original.get('article')}:saisie":
        raise ValueError("Dates ou identifiant du comptage incohérents.")
    heure = original.get("horodatage")
    source = original.get("source")
    if (not isinstance(heure, str) or "T" not in heure or not isinstance(source, dict)
            or source.get("origine") != "app/compter.html" or not isinstance(source.get("saisi_le"), str)):
        raise ValueError("Heure et source du comptage requises ; ne pas les deviner.")
    instant = datetime.fromisoformat(heure)
    if instant.date().isoformat() != jour or datetime.fromisoformat(source["saisi_le"]) != instant:
        raise ValueError("Heure originale et source de saisie incohérentes.")
    for champ, attendu, nom in (("colis", args.colis, "colis"),
                                ("conditionnement", args.ancien_conditionnement, "ancien conditionnement"),
                                ("quantite", args.ancienne_quantite, "ancienne quantité")):
        valeur = original.get(champ)
        if type(valeur) not in (int, float) or not math.isfinite(valeur):
            raise ValueError(f"{nom} : le fait original doit contenir un nombre fini.")
        if valeur != attendu:
            raise ValueError(f"{nom} ne correspond pas au fait original ; rien corrigé.")
    if original["conditionnement"] <= 0 or round(original["colis"] * original["conditionnement"], 3) != original["quantite"]:
        raise ValueError("Ancienne quantité incohérente avec colis × ancien conditionnement.")
    quantite = round(original["colis"] * args.conditionnement, 3)
    if not math.isfinite(quantite):
        raise ValueError("Quantité convertie non finie.")
    correction = copy.deepcopy(original)
    identite = json.dumps([args.cible_id, args.conditionnement], ensure_ascii=False)
    identifiant = "correction-comptage:conversion:" + hashlib.sha256(identite.encode()).hexdigest()[:24]
    for _, autre in toutes:
        if autre.get("id") in (args.cible_id, identifiant):
            continue
        if autre.get("type") == "correction-comptage" and autre.get("cible_id") == args.cible_id:
            raise ValueError("Correction existante en conflit : ne pas écraser une autre correction.")
        if autre.get("article") != original["article"] or autre.get("type") not in ("comptage", "correction-comptage"):
            continue
        autre_jour = autre.get("date_effet") or autre.get("date_source")
        if not isinstance(autre_jour, str) or date.fromisoformat(autre_jour).isoformat() != autre_jour:
            raise ValueError("Autre comptage de date incertaine : contrôle manuel requis.")
        if autre_jour < jour:
            continue
        autre_heure = autre.get("horodatage") or (autre.get("source") or {}).get("saisi_le") or (autre.get("source") or {}).get("horodatage")
        if (autre_jour > jour or not autre_heure
                or datetime.fromisoformat(autre_heure).astimezone() >= instant.astimezone()):
            raise ValueError("Comptage postérieur ou simultané : correction historique non sûre.")
    correction.update({
        "id": identifiant, "type": "correction-comptage", "cible_id": args.cible_id,
        "origine_mesure": "correction-conversion-comptage",
        "conditionnement": args.conditionnement,
        "quantite": quantite,
        "auteur": args.auteur, "motif": args.motif,
        "enregistre_le": datetime.now().isoformat(timespec="seconds"),
        "conversion_comptage": {
            "nature": "conversion-sans-nouveau-releve",
            "confirmation": args.confirmation,
            "reference_confirmation": args.reference_confirmation,
            "avant": {k: copy.deepcopy(original[k]) for k in
                      ("quantite", "conditionnement", "colis", "enregistre_le")},
            "empreinte_original_sha256": hashlib.sha256(json.dumps(
                original, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest(),
        },
    })
    existantes = [f for _, f in toutes if f.get("id") == identifiant]
    if existantes:
        if len(existantes) != 1:
            raise ValueError("Correction dupliquée : contrôle manuel nécessaire.")
        ancienne = existantes[0]
        sans_audit = lambda f: {k: v for k, v in f.items() if k not in ("action", "enregistre_le")}
        if sans_audit(ancienne) != sans_audit(correction):
            raise ValueError("Correction existante en conflit avec la demande.")
        return chemin, ancienne, True
    return chemin, correction, False


def verifier_traces(correction):
    for auteur in (correction["auteur"], "tout"):
        traces = carnet_agents.lire(auteur)
        if not any(l.get("action") == correction.get("action")
                   and l.get("details", {}).get("correction_id") == correction["id"]
                   and l.get("resultat") == "ok" for l in traces):
            raise ValueError("Trace de correction absente après relecture ; fait conservé, reprise manuelle de l'audit nécessaire.")


def executer(args):
    if args.auteur != "agent-rayon":
        raise ValueError("Cette maintenance confirmée doit être signée agent-rayon.")
    if not args.ecrivains_inactifs:
        raise ValueError("Attester l'absence d'autres écrivains de faits pendant la maintenance.")
    for champ in ("conditionnement", "ancien_conditionnement", "ancienne_quantite", "colis"):
        if not math.isfinite(getattr(args, champ)):
            raise ValueError(f"{champ} doit être un nombre fini.")
    if args.conditionnement <= 0 or args.ancien_conditionnement <= 0:
        raise ValueError("Le conditionnement doit être strictement positif.")
    if not args.confirmation.strip():
        raise ValueError("Confirmation explicite obligatoire.")
    if not args.reference_confirmation.strip():
        raise ValueError("Référence de confirmation obligatoire.")
    if len(args.motif.strip()) < 30:
        raise ValueError("Motif trop court : préciser conversion, sans nouveau relevé.")
    contexte = nullcontext() if args.simuler else carnet_agents.verrou()
    with contexte:
        carnet_agents.verifier_pouvoirs(args.auteur, ["conditionnement"], POUVOIRS)
        avant = instantane()
        chemin, correction, deja = preparer(args, avant)
        if deja:
            verifier_traces(correction)
            return {"statut": "deja-applique", "action": correction["action"],
                    "correction": correction, "ecritures": 0, "verifie": True}
        if args.simuler:
            return {"statut": "simulation", "correction": correction, "ecritures": 0}
        action = carnet_agents.numero_action()
        correction["action"] = action
        try:
            if instantane() != avant:
                raise ValueError("Conflit : carnets modifiés depuis la lecture ; rien ajouté.")
            separateur = b"\n" if avant[chemin] and not avant[chemin].endswith(b"\n") else b""
            ajout = separateur + (json.dumps(correction, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
            with chemin.open("ab") as flux:
                flux.write(ajout)
                flux.flush()
                os.fsync(flux.fileno())
            attendu = dict(avant)
            attendu[chemin] += ajout
            if instantane() != attendu:
                raise ValueError("Conflit après écriture : vérifier les carnets, ne pas réessayer aveuglément.")
            # Relecture du JSON exact et du préfixe immutable avant toute réussite.
            if json.loads(chemin.read_bytes().splitlines()[-1]) != correction:
                raise ValueError("Correction non retrouvée à la relecture.")
            carnet_agents.enregistrer(
                agent=args.auteur, action=action,
                message=f"Conversion du comptage {args.cible_id} corrigée sans nouveau relevé",
                motif=args.motif, annulable=False,
                changements=[{"itm8": correction["article"], "champ": "conversion-comptage",
                              "avant": correction["conversion_comptage"]["avant"],
                              "apres": {k: correction[k] for k in ("quantite", "conditionnement", "colis")}}],
                details={"cible_id": args.cible_id, "correction_id": correction["id"],
                         "confirmation": args.confirmation, "reference_confirmation": args.reference_confirmation},
            )
            verifier_traces(correction)
        except Exception as erreur:
            carnet_agents.echec(args.auteur, "Échec de correction de conversion de comptage", erreur,
                                action=action, details={"cible_id": args.cible_id, "correction_id": correction["id"]})
            raise
        return {"statut": "applique", "action": action, "correction": correction, "verifie": True}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("cible_id")
    p.add_argument("conditionnement", type=float)
    p.add_argument("--ancien-conditionnement", type=float, required=True)
    p.add_argument("--ancienne-quantite", type=float, required=True)
    p.add_argument("--colis", type=float, required=True)
    p.add_argument("--auteur", required=True)
    p.add_argument("--motif", required=True)
    p.add_argument("--confirmation", required=True)
    p.add_argument("--reference-confirmation", required=True)
    p.add_argument("--ecrivains-inactifs", action="store_true",
                   help="Atteste que les autres écrivains de faits restent inactifs pendant la maintenance.")
    p.add_argument("--simuler", action="store_true")
    args = p.parse_args()
    try:
        print(json.dumps(executer(args), ensure_ascii=False, allow_nan=False))
    except (ValueError, OSError, KeyError) as erreur:
        p.exit(1, f"REFUS / ÉCHEC : {erreur}\n")


if __name__ == "__main__":
    main()
