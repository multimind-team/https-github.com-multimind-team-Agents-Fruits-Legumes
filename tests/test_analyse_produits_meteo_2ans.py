"""
tests/test_analyse_produits_meteo_2ans.py - Vérifie la présence et la cohérence des profils 2.5 ans.
"""
import json
from pathlib import Path
import unittest

RACINE = Path(__file__).resolve().parent.parent
FICHIER_PROFILS = RACINE / "donnees" / "profils-produits-sensibilites.json"


class TestAnalyseProduitsMeteo2Ans(unittest.TestCase):

    def test_fichier_profils_existe_et_rempli(self):
        self.assertTrue(FICHIER_PROFILS.exists(), "profils-produits-sensibilites.json doit exister")
        data = json.loads(FICHIER_PROFILS.read_text(encoding="utf-8"))

        self.assertIn("articles", data)
        self.assertIn("familles", data)
        self.assertGreater(data["nombre_articles_profils"], 300)
        self.assertGreater(data["nombre_ventes_analysees"], 100000)

        # Vérification des familles clés
        familles = data["familles"]
        self.assertIn("fruits_ete", familles)
        self.assertIn("salades_crudites", familles)
        self.assertIn("legumes_a_cuire", familles)

        # Vérification des tendances métier prouvées
        # 1. Fruits d'été et salades stimulés par la chaleur (ratio > 1.10)
        self.assertGreater(familles["fruits_ete"]["chaud_25"], 1.10)
        self.assertGreater(familles["salades_crudites"]["chaud_25"], 1.10)

        # 2. Légumes à cuire ralentis par la chaleur (ratio < 0.95)
        self.assertLess(familles["legumes_a_cuire"]["chaud_25"], 0.95)

        # 3. Effet veille de jour férié positif sur toutes les familles majeures (> 1.10)
        self.assertGreater(familles["fruits_ete"]["veille_ferie"], 1.10)
        self.assertGreater(familles["salades_crudites"]["veille_ferie"], 1.10)
        self.assertGreater(familles["legumes_a_cuire"]["veille_ferie"], 1.10)


if __name__ == "__main__":
    unittest.main()
