"""Un libellé prolongé par BIO ne désigne pas l'article conventionnel."""
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "moteur"))
spec = importlib.util.spec_from_file_location(
    "cadencier_bio", Path(__file__).resolve().parents[1] / "moteur/cadencier-du-jour.py")
CAD = importlib.util.module_from_spec(spec)
spec.loader.exec_module(CAD)


class RapprochementBioTests(unittest.TestCase):
    def test_prefixe_conventionnel_ne_valide_pas_son_homonyme_bio(self):
        noms = {"0000087004327": "PASTEQUE MINI PIECE"}
        lignes = [{"nom": "PASTEQUE MINI PIECE", "groupe": "fruits"},
                  {"nom": "PASTEQUE MINI PIECE BIO ITM", "groupe": "bio"}]
        with patch.object(CAD.catalogue, "noms", return_value=noms):
            CAD.rapprocher(lignes)
        self.assertEqual(lignes[0]["article"], "0000087004327")
        self.assertIsNone(lignes[1]["article"])
        self.assertNotEqual(lignes[1]["rapprochement"], "sûr")

    def test_prefixe_bio_atteste_et_nom_exact_restent_reconnus(self):
        noms = {"0000087004327": "PASTEQUE MINI PIECE", "0000087004999": "PASTEQUE MINI PIECE BIO"}
        lignes = [{"nom": "PASTEQUE MINI PIECE BIO ITM", "groupe": "bio"},
                  {"nom": "PASTEQUE MINI PIECE", "groupe": "fruits"}]
        with patch.object(CAD.catalogue, "noms", return_value=noms):
            CAD.rapprocher(lignes)
        self.assertEqual(lignes[0]["article"], "0000087004999")
        self.assertEqual(lignes[1]["article"], "0000087004327")


if __name__ == "__main__":
    unittest.main()
