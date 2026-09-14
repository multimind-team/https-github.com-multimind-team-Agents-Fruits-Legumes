"""Publication des dérivés, tests d'interruption sur chemins temporaires."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'moteur'))
import ecriture_derivee


class PublicationAtomiqueTests(unittest.TestCase):
    def test_publication_valide_est_relue_et_sans_fichier_temporaire(self):
        with tempfile.TemporaryDirectory() as repertoire:
            cible = Path(repertoire) / 'etat.json'
            contenu = {'articles': {'123': {'position': 1.5}}, 'texte': 'éprouvé'}
            ecriture_derivee.ecrire_json(cible, contenu)
            self.assertEqual(json.loads(cible.read_text(encoding='utf-8')), contenu)
            self.assertEqual(list(cible.parent.iterdir()), [cible])

    def test_sync_interrompue_conserve_l_ancienne_version(self):
        with tempfile.TemporaryDirectory() as repertoire:
            cible = Path(repertoire) / 'etat.json'
            cible.write_text('{"ancien": true}', encoding='utf-8')
            avant = cible.read_bytes()
            with patch.object(ecriture_derivee.os, 'fsync', side_effect=OSError('disque indisponible')):
                with self.assertRaisesRegex(OSError, 'disque indisponible'):
                    ecriture_derivee.ecrire_json(cible, {'nouveau': True})
            self.assertEqual(cible.read_bytes(), avant)
            self.assertEqual(list(cible.parent.iterdir()), [cible])

    def test_nombre_non_fini_ne_detruit_pas_l_ancienne_version(self):
        with tempfile.TemporaryDirectory() as repertoire:
            cible = Path(repertoire) / 'etat.json'
            cible.write_text('{"ancien": true}', encoding='utf-8')
            avant = cible.read_bytes()
            with self.assertRaises(ValueError):
                ecriture_derivee.ecrire_json(cible, {'position': float('nan')})
            self.assertEqual(cible.read_bytes(), avant)
            self.assertEqual(list(cible.parent.iterdir()), [cible])

    def test_rejet_explicite_des_carnets_jsonl(self):
        with tempfile.TemporaryDirectory() as repertoire:
            cible = Path(repertoire) / '2026.jsonl'
            cible.write_text('{"id": "immuable"}\n', encoding='utf-8')
            avant = cible.read_bytes()
            with self.assertRaisesRegex(ValueError, 'JSONL'):
                ecriture_derivee.ecrire_json(cible, {'interdit': True})
            self.assertEqual(cible.read_bytes(), avant)


if __name__ == '__main__':
    unittest.main()
