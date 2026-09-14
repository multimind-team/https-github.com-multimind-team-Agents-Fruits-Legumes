"""Lecture idempotente des carnets immuables. Aucune écriture ni suppression.

Un ID est un fait unique. Seule la provenance `source` peut varier entre ses
copies ; tout autre écart est ambigu et interrompt le calcul avant publication.
Les emplacements des doublons restent disponibles dans le bilan de lecture.
"""
import json
from pathlib import Path


def signature(fait):
    contenu = {k: v for k, v in fait.items() if k != 'source'}
    return json.dumps(contenu, sort_keys=True, ensure_ascii=False, allow_nan=False)


def lire(dossier, bilan=None):
    bilan = bilan if bilan is not None else {}
    bilan.update(lignes_lues=0, faits_uniques=0, doublons_ignores=0, sans_id=0, doublons=[])
    connus = {}
    for chemin in sorted(Path(dossier).glob('*.jsonl')):
        with chemin.open(encoding='utf-8') as flux:
            for numero, ligne in enumerate(flux, 1):
                if not ligne.strip():
                    continue
                fait = json.loads(ligne)
                bilan['lignes_lues'] += 1
                identifiant = fait.get('id')
                emplacement = {'fichier': chemin.name, 'ligne': numero}
                if identifiant:
                    empreinte = signature(fait)
                    precedent = connus.get(identifiant)
                    if precedent is not None:
                        if precedent[0] != empreinte:
                            raise ValueError(f"Fait {identifiant} en conflit : {precedent[1]} / {emplacement}. Carnets conservés ; correction explicite requise.")
                        bilan['doublons_ignores'] += 1
                        bilan['doublons'].append({'id': identifiant, 'premier': precedent[1], 'ignore': emplacement})
                        continue
                    connus[identifiant] = (empreinte, emplacement)
                else:
                    # Sans identité on ne fusionne jamais deux mesures ressemblantes.
                    bilan['sans_id'] += 1
                bilan['faits_uniques'] += 1
                yield fait
