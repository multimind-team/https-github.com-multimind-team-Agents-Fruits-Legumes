import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

MOTEUR = Path(__file__).resolve().parents[1] / "moteur"
sys.path.insert(0, str(MOTEUR))
SPEC = importlib.util.spec_from_file_location("cadencier_du_jour", MOTEUR / "cadencier-du-jour.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class DernierCadencierTests(unittest.TestCase):
    def test_rapprochement_refuse_des_regles_illisibles(self):
        with patch.object(MODULE.catalogue, "noms", return_value={}), \
             patch("regles.charger", side_effect=ValueError("Carnet illisible")), \
             self.assertRaisesRegex(ValueError, "Carnet illisible"):
            MODULE.rapprocher([])

    def test_trouve_un_cadencier_webtelevente_avec_espaces_dans_le_nom(self):
        with tempfile.TemporaryDirectory() as tmp:
            dossier = Path(tmp)
            fichier = dossier / "2026-09-07-courrier" / "cadencier webtelevente 07.09.2026.xls"
            fichier.parent.mkdir()
            fichier.write_bytes(b"cadencier")

            self.assertEqual(MODULE.dernier_cadencier(dossier), fichier)

    def test_reconnait_les_groupes_du_cadencier_meme_quand_l_intitule_est_en_colonne_b(self):
        self.assertEqual(MODULE.groupe_de_ligne(["", "FRUITS"]), "fruits")
        self.assertEqual(MODULE.groupe_de_ligne(["", "LÉGUMES"]), "legumes")
        self.assertEqual(MODULE.groupe_de_ligne(["", "BIO"]), "bio")
        self.assertIsNone(MODULE.groupe_de_ligne(["GAMME PERMANENTE", ""]))


if __name__ == "__main__":
    unittest.main()
