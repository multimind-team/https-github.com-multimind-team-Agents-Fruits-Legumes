"""L'outil de récupération manuel refuse toute saisie non vérifiable."""
import argparse
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

MOTEUR = Path(__file__).resolve().parents[1] / 'moteur'
sys.path.insert(0, str(MOTEUR))
spec = importlib.util.spec_from_file_location('livraison_manuelle', MOTEUR / 'enregistrer-livraison-directe.py')
MODULE = importlib.util.module_from_spec(spec)
spec.loader.exec_module(MODULE)


class LivraisonManuelleTests(unittest.TestCase):
    def test_livraisons_forcees_distinctes_sans_collision_d_identifiant(self):
        with tempfile.TemporaryDirectory() as temp:
            dossier = Path(temp) / 'faits'
            with patch.object(MODULE, 'DOSSIER_FAITS', dossier), \
                 patch.object(MODULE.catalogue, 'fiche', return_value={'LIBELLE': 'TEST'}), \
                 patch.object(MODULE.catalogue, 'unite', return_value='1 Pièce'), \
                 patch.object(sys, 'argv', ['outil', '0000087004029', '2', '--fournisseur', 'TEST', '--motif', 'Autre livraison prouvée', '--date', '2026-09-09', '--forcer']), \
                 contextlib.redirect_stdout(io.StringIO()):
                MODULE.main()
                original = (dossier / '2026.jsonl').read_bytes()
                MODULE.main()
                MODULE.main()
            lignes = [json.loads(l) for l in (dossier / '2026.jsonl').read_text(encoding='utf8').splitlines()]
            self.assertTrue((dossier / '2026.jsonl').read_bytes().startswith(original))
            self.assertEqual(len({l['id'] for l in lignes}), 3)

    def test_saisies_incoherentes_refusees_avant_toute_ecriture(self):
        cas = [(['--date', '2026-02-30'], '2'), (['--date', '2026-9-09'], '2'),
               (['--date', '../2026'], '2'), ([], 'nan'), ([], 'inf'), ([], '-2'),
               ([], '0'), (['--colis', '-3'], '2'), (['--colis', 'nan'], '2'),
               (['--colis', '0'], '2')]
        for options, quantite in cas:
            with self.subTest(options=options, quantite=quantite), tempfile.TemporaryDirectory() as temp:
                dossier = Path(temp) / 'faits'
                with patch.object(MODULE, 'DOSSIER_FAITS', dossier), \
                     patch.object(MODULE.catalogue, 'fiche', return_value={'LIBELLE': 'TEST'}), \
                     patch.object(MODULE.catalogue, 'unite', return_value='1 Pièce'), \
                     patch.object(sys, 'argv', ['outil', '0000087004029', quantite, '--fournisseur', 'TEST', '--motif', 'Preuve de test', *options]), \
                     contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit):
                        MODULE.main()
                    self.assertFalse(dossier.exists(), 'Une saisie refusée ne doit ouvrir aucun carnet')

    def test_dedoublonnage_lit_le_json_independamment_des_espaces(self):
        with tempfile.TemporaryDirectory() as temp:
            fichier = Path(temp) / 'faits.jsonl'
            fichier.write_text(json.dumps({'id': 'livraison:test'}, separators=(',', ':')) + '\n', encoding='utf8')
            self.assertTrue(MODULE.deja_enregistre(fichier, 'livraison:test'))
            self.assertFalse(MODULE.deja_enregistre(fichier, 'livraison:autre'))


if __name__ == '__main__':
    unittest.main()
