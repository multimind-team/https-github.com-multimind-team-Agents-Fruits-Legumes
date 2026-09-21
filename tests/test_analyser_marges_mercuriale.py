"""
tests/test_analyser_marges_mercuriale.py - Tests unitaires de la surveillance des prix et marges.
"""
from pathlib import Path
import sys
import unittest
import json
import tempfile
from copy import deepcopy
from unittest.mock import patch

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "moteur"))
import analyser_marges_mercuriale as amm


class TestAnalyserMargesMercuriale(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        dossier = Path(self.temp.name)
        for nom, valeur in {
            "DONNEES": dossier,
            "FICHIER_HISTO_PRIX": dossier / "historique.json",
            "FICHIER_ALERTES": dossier / "alertes.json",
            "FICHIER_CADENCIER": dossier / "cadencier.json",
            "FICHIER_AGREGATS": dossier / "agregats.json",
        }.items():
            remplacement = patch.object(amm, nom, valeur)
            remplacement.start()
            self.addCleanup(remplacement.stop)

    @patch.object(amm.catalogue, "prix", return_value=0.0)
    def test_detection_hausse_et_marge(self, mock_prix):
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

        original = deepcopy(histo_test)
        rapport = amm.analyser_cadencier(cadencier_test, histo_test)
        self.assertEqual(histo_test, original)
        publie = json.loads(amm.FICHIER_ALERTES.read_text(encoding="utf-8"))
        self.assertTrue(publie.pop("_operation_id"))
        self.assertEqual(publie, rapport)
        self.assertEqual(json.loads(amm.FICHIER_HISTO_PRIX.read_text(encoding="utf-8"))["prix_par_article"]["0000087003306"][-1]["prix_achat"], 2.2)
        alertes = {a["itm8"]: a for a in rapport["alertes"]}

        # Melon : alerte hausse brutale
        self.assertIn("0000087003306", alertes)
        self.assertGreater(alertes["0000087003306"]["hausse_pct"], 15.0)

        # Courgette : alerte marge faible (repli sur PVC car pas de prix catalogue)
        self.assertIn("0000087765013", alertes)
        self.assertLess(alertes["0000087765013"]["taux_marge"], 20.0)

    def test_priorite_prix_catalogue_sur_pvc(self):
        """Vérifie que le prix réel catalogue en caisse prime sur le PVC Scafruit (ex: Concombre à 1.19 € vs 0.93 €)."""
        cadencier_concombre = {
            "date_cadencier": "2026-09-19",
            "articles": [
                {
                    "nom": "CONCOMBRE PIECE",
                    "article": "0000087004593",
                    "offres": [
                        {
                            "libelle": "CONCOMBRE PIECE",
                            "prix_achat": 0.88,
                            "prix_vente_conseille": 0.93  # PVC Scafruit = 5.3% (< 20%) -> fausse alerte si utilisé
                        }
                    ]
                }
            ]
        }
        with patch.object(amm.catalogue, "prix", return_value=1.19):
            rapport = amm.analyser_cadencier(cadencier_concombre, {})
            # Avec le prix catalogue réel de 1.19 €, marge = (1.19 - 0.88) / 1.19 = 26.1% (> 20%)
            # L'alerte ne doit pas se déclencher
            alertes = {a["itm8"]: a for a in rapport["alertes"]}
            self.assertNotIn("0000087004593", alertes)

    def test_priorite_prix_ventes_reelles(self):
        """Vérifie que le prix de vente constaté lors des ventes quotidiennes est pris en compte."""
        cadencier_test = {
            "date_cadencier": "2026-09-19",
            "articles": [
                {
                    "nom": "CHOU BLANC PIECE",
                    "article": "0000087003050",
                    "offres": [
                        {
                            "libelle": "CHOU BLANC PIECE",
                            "prix_achat": 2.50,
                            "prix_vente_conseille": 2.80
                        }
                    ]
                }
            ]
        }
        agregats_test = {
            "0000087003050": {
                "dernierPrixVente": 3.29,
                "dernierPrixVenteLe": "2026-09-18"
            }
        }
        with patch.object(amm.catalogue, "prix", return_value=2.99):
            rapport = amm.analyser_cadencier(cadencier_test, {}, agregats_articles=agregats_test)
            # Constaté 3.29 € prime sur catalogue 2.99 € -> Marge = (3.29 - 2.50) / 3.29 = 24.0% (> 20%)
            alertes = {a["itm8"]: a for a in rapport["alertes"]}
            self.assertNotIn("0000087003050", alertes)

    def test_detection_fin_promotion_marge_realisee(self):
        """Vérifie la détection et la contextualisation d'une fin de promotion (ex: Banane à 0.90 € -> 1.29 €)."""
        cadencier_test = {
            "date_cadencier": "2026-09-19",
            "articles": [
                {
                    "nom": "BANANE VRAC",
                    "article": "0000087004011",
                    "offres": [
                        {
                            "libelle": "BANANE VRAC",
                            "prix_achat": 1.29,
                            "prix_vente_conseille": 1.99
                        }
                    ]
                }
            ]
        }
        histo_test = {
            "prix_par_article": {
                "0000087004011": [
                    {"date": "2026-09-18", "prix_achat": 0.90}
                ]
            }
        }
        promos_test = {
            "offres": [
                {
                    "nom": "Banane Cavendish",
                    "debut": "2026-09-15",
                    "fin": "2026-09-19",
                    "correspondances": [
                        {"itm8": "0000087004011", "libelle": "BANANE VRAC"}
                    ]
                }
            ]
        }
        with patch.object(amm.catalogue, "prix", return_value=0.99):
            rapport = amm.analyser_cadencier(cadencier_test, histo_test, promotions=promos_test)
            alertes = {a["itm8"]: a for a in rapport["alertes"]}
            self.assertIn("0000087004011", alertes)
            banane = alertes["0000087004011"]
            self.assertTrue(banane.get("contexte_promo"))
            self.assertEqual(banane.get("type_alerte"), "fin_promo")
            self.assertEqual(banane.get("gravite"), "avertissement")
            self.assertEqual(banane.get("marge_promo_realisee"), 9.1)
            self.assertIn("Fin de promo", banane.get("recommandation"))


if __name__ == "__main__":
    unittest.main()
