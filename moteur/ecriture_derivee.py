"""Publication atomique de JSON complets, jamais des carnets JSONL.

Le temporaire est voisin de la cible (même volume Windows). Une interruption
avant os.replace conserve la dernière version valide. Cela n'est pas une
transaction entre plusieurs fichiers ni un verrou entre producteurs.
"""
import json
import os
from pathlib import Path
import tempfile
import time
from datetime import datetime
from verrou_donnees import identifiant_operation


def ecrire_json(chemin, contenu, *, indent=1, avec_operation=True):
    chemin = Path(chemin)
    if chemin.suffix.lower() != '.json':
        raise ValueError('Publication réservée aux JSON complets ; jamais aux carnets JSONL.')
    # Les réglages sources ne portent pas l'identifiant d'une passe de calcul.
    operation = identifiant_operation(chemin.parent) if avec_operation else None
    if operation and isinstance(contenu, dict):
        contenu = {**contenu, '_operation_id': operation}
    texte = json.dumps(contenu, ensure_ascii=False, indent=indent, allow_nan=False)
    temporaire = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='\n',
                                         dir=chemin.parent, prefix=chemin.name + '.',
                                         suffix='.tmp', delete=False) as flux:
            temporaire = Path(flux.name)
            flux.write(texte)
            flux.flush()
            os.fsync(flux.fileno())
        fin = time.monotonic() + 1
        while True:
            try:
                os.replace(temporaire, chemin)
                break
            except PermissionError:
                # Lecture brève du statut (consultable durant le calcul), ou
                # antivirus Windows : garder l'ancien JSON jusqu'au replace.
                if os.name != "nt" or time.monotonic() >= fin:
                    raise
                time.sleep(.01)
    finally:
        if temporaire is not None:
            temporaire.unlink(missing_ok=True)


def publier_etat_calcul(dossier, etat, origine, message=""):
    """Expose une passe complète, sans promettre un rollback des fichiers."""
    ecrire_json(Path(dossier) / "recalcul.json", {
        "etat": etat, "origine": origine,
        "operation_id": identifiant_operation(dossier),
        "modifie_le": datetime.now().isoformat(timespec="seconds"),
        "message": message,
    })
