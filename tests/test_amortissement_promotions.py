"""
tests/test_amortissement_promotions.py - Tests unitaires du module d'amortissement en fin de promo.
"""
from pathlib import Path
import sys
import unittest

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "moteur"))
import amortissement_promotions as ap


class TestAmortissementPromotions(unittest.TestCase):

    def setUp(self):
        self.fausses_offres = [
            {
                "nom": "Banane Cavendish",
                "debut": "2026-09-15",
                "fin": "2026-09-19",
                "correspondances": [
                    {"itm8": "0000087004011", "libelle": "BANANE VRAC", "statut": "confirme"}
                ]
            }
        ]

    def test_hors_promo_avant(self):
        # Avant le début de la promo
        res = ap.evaluer_amortissement("0000087004011", "2026-09-12", "2026-09-14", self.fausses_offres)
        self.assertFalse(res["en_fin_promo"])
        self.assertEqual(res["phase"], "hors_promo")
        self.assertEqual(res["facteur_amortissement"], 1.0)

    def test_promo_en_cours(self):
        # En plein milieu de la promo (cmd 15, liv 16)
        res = ap.evaluer_amortissement("0000087004011", "2026-09-15", "2026-09-16", self.fausses_offres)
        self.assertFalse(res["en_fin_promo"])
        self.assertEqual(res["phase"], "en_cours")
        self.assertEqual(res["facteur_amortissement"], 1.0)

    def test_dernier_jour_promo(self):
        # Commande le 18 pour livraison le 19 (dernier jour de la promo)
        res = ap.evaluer_amortissement("0000087004011", "2026-09-18", "2026-09-19", self.fausses_offres)
        self.assertTrue(res["en_fin_promo"])
        self.assertEqual(res["phase"], "dernier_jour")
        self.assertEqual(res["facteur_amortissement"], 1.0)
        self.assertIn("Dernier jour promo", res["motif"])

    def test_post_promo(self):
        # Commande le 19 (dernier jour de promo) pour livraison le 21 (lundi hors promo)
        res = ap.evaluer_amortissement("0000087004011", "2026-09-19", "2026-09-21", self.fausses_offres)
        self.assertTrue(res["en_fin_promo"])
        self.assertEqual(res["phase"], "post_promo")
        self.assertEqual(res["facteur_amortissement"], 1.0)
        self.assertIn("Fin de promo", res["motif"])

    def test_article_inconnu(self):
        res = ap.evaluer_amortissement("9999999999999", "2026-09-19", "2026-09-21", self.fausses_offres)
        self.assertFalse(res["en_fin_promo"])
        self.assertEqual(res["phase"], "hors_promo")
        self.assertEqual(res["facteur_amortissement"], 1.0)

    def test_correspondance_non_confirmee_sans_effet(self):
        for statut in (None, "a_confirmer", "refuse"):
            with self.subTest(statut=statut):
                self.fausses_offres[0]["correspondances"][0]["statut"] = statut
                res = ap.evaluer_amortissement("0000087004011", "2026-09-19", "2026-09-21", self.fausses_offres)
                self.assertFalse(res["en_fin_promo"])
                self.assertEqual(res["facteur_amortissement"], 1.0)


if __name__ == "__main__":
    unittest.main()
