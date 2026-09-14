import importlib.util
import sys
import unittest
from pathlib import Path

MOTEUR = Path(__file__).resolve().parents[1] / "moteur"
sys.path.insert(0, str(MOTEUR))
SPEC = importlib.util.spec_from_file_location("preparer_liste_comptage", MOTEUR / "preparer-liste-comptage.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PositionPerdueTests(unittest.TestCase):
    def test_marque_la_position_perdue_a_partir_de_moins_dix_colis(self):
        self.assertFalse(MODULE.position_est_perdue(-9.9, 1))
        self.assertTrue(MODULE.position_est_perdue(-10, 1))


if __name__ == "__main__":
    unittest.main()
