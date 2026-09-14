"""
tests/test_analyser_marges_mercuriale.py - Tests unitaires de la surveillance des prix et marges.
"""
from pathlib import Path
import sys
import unittest

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "moteur"))
import analyser_marges_mercuriale as amm


class TestAnalyserMargesMercuriale(unittest.TestCase):

    def test_detection_hausse_et_marge(self):
        cadencier_test = {
            "date_cadencier": "2026-09-12",
            "articles": [
                {
                    "nom": "COURGETTE FILET 1KG",
                    "article": "0000087765013",
                    "offres": [
                        {
                            "libelle": "COURGETTE FILET 1KG",
                            "prix_achat": 1.50,
                            "prix_vente_conseille": 1.70  # Marge = (1.70 - 1.50) / 1.70 = 11.7% (< 20%)
                        }
                    ]
                },
                {
                    "nom": "MELON CHARENTAIS",
                    "article": "0000087003306",
                    "offres": [
                        {
                            "libelle": "MELON PIECE",
                            "prix_achat": 2.20,           # Était à 1.50 -> +46.6%
                            "prix_vente_conseille": 3.00
                        }
                    ]
                }
            ]
        }

        histo_test = {
            "prix_par_article": {
                "0000087003306": [
                    {"date": "2026-09-11", "prix_achat": 1.50}
                ],
                "0000087765013": [
                    {"date": "2026-09-11", "prix_achat": 1.45}
                ]
            }
        }

        rapport = amm.analyser_cadencier(cadencier_test, histo_test)
        alertes = {a["itm8"]: a for a in rapport["alertes"]}

        # Melon : alerte hausse brutale
        self.assertIn("0000087003306", alertes)
        self.assertGreater(alertes["0000087003306"]["hausse_pct"], 15.0)

        # Courgette : alerte marge faible
        self.assertIn("0000087765013", alertes)
        self.assertLess(alertes["0000087765013"]["taux_marge"], 20.0)


if __name__ == "__main__":
    unittest.main()
