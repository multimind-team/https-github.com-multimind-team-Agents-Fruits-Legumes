"""Publication atomique de JSON dérivés, jamais des carnets JSONL.

Le temporaire est voisin de la cible (même volume Windows). Une interruption
avant os.replace conserve la dernière version valide. Cela n'est pas une
transaction entre plusieurs fichiers ni un verrou entre producteurs.
"""
import json
import os
from pathlib import Path
import tempfile


def ecrire_json(chemin, contenu, *, indent=1):
    chemin = Path(chemin)
    if chemin.suffix.lower() != '.json':
        raise ValueError('Publication réservée aux JSON dérivés ; jamais aux carnets JSONL.')
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
        os.replace(temporaire, chemin)
    finally:
        if temporaire is not None:
            temporaire.unlink(missing_ok=True)
