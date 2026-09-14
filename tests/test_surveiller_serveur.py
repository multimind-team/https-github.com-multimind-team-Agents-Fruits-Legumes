import importlib.util
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
SCRIPT = RACINE / "moteur" / "surveiller-serveur.py"


def charge_module():
    spec = importlib.util.spec_from_file_location("surveiller_serveur", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SurveillanceServeurTests(unittest.TestCase):
    def test_ne_redemarre_pas_quand_l_application_repond(self):
        module = charge_module()
        demarrages = []

        actif = module.veille_une_fois(
            verifie=lambda: True,
            demarre=lambda: demarrages.append(True),
        )

        self.assertTrue(actif)
        self.assertEqual(demarrages, [])

    def test_demarre_le_serveur_quand_le_controle_http_echoue(self):
        module = charge_module()
        demarrages = []

        actif = module.veille_une_fois(
            verifie=lambda: False,
            demarre=lambda: demarrages.append(True),
        )

        self.assertFalse(actif)
        self.assertEqual(demarrages, [True])


if __name__ == "__main__":
    unittest.main()
