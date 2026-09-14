import importlib.util
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

MOTEUR = Path(__file__).resolve().parents[1] / "moteur"
SPEC = importlib.util.spec_from_file_location("promotions", MOTEUR / "promotions.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PromotionsTests(unittest.TestCase):
    def test_calcul_le_mardi_strictement_suivant_le_telechargement(self):
        self.assertEqual(MODULE.mardi_suivant(date(2026, 9, 5)), date(2026, 9, 8))
        self.assertEqual(MODULE.mardi_suivant(date(2026, 9, 8)), date(2026, 9, 15))

    def test_page_promotion_affiche_des_images_et_non_un_iframe_pdf(self):
        page = (MOTEUR.parent / "app" / "promo.html").read_text(encoding="utf-8")
        self.assertIn('id="apercus-prospectus"', page)
        self.assertNotIn('<iframe class="prospectus"', page)

    def test_rend_les_pages_lues_du_prospectus_en_images(self):
        import fitz

        with tempfile.TemporaryDirectory() as tmp:
            dossier = Path(tmp)
            source = dossier / "prospectus.pdf"
            document = fitz.open()
            document.new_page()
            document.save(source)
            document.close()

            apercus = MODULE.rendre_apercus(source, [1], dossier / "apercus")

            self.assertEqual([chemin.name for chemin in apercus], ["page-1.png"])
            self.assertTrue(apercus[0].is_file())
            self.assertGreater(apercus[0].stat().st_size, 0)

    def test_affiche_des_le_samedi_precedent_avant_le_debut_de_l_offre(self):
        promotion = {
            "visible_a_partir": "2026-09-05",
            "debut": "2026-09-08",
            "fin": "2026-09-12",
        }
        self.assertTrue(MODULE.est_affichable(promotion, date(2026, 9, 5)))
        self.assertTrue(MODULE.est_affichable(promotion, date(2026, 9, 12)))
        self.assertFalse(MODULE.est_affichable(promotion, date(2026, 9, 13)))

    def test_refuse_un_article_sans_statut_de_correspondance(self):
        with self.assertRaises(ValueError):
            MODULE.valider({"offres": [{"nom": "COURGETTE"}]})

    def test_charge_le_catalogue_sans_inventer_de_code_article(self):
        donnees = {
            "offres": [{
                "nom": "COURGETTE",
                "visible_a_partir": "2026-09-05",
                "debut": "2026-09-08",
                "fin": "2026-09-12",
                "correspondances": [{"itm8": "0000087004067", "statut": "a_confirmer"}],
            }]
        }
        with tempfile.TemporaryDirectory() as tmp:
            chemin = Path(tmp) / "promotions.json"
            chemin.write_text(json.dumps(donnees), encoding="utf-8")
            charge = MODULE.charger(chemin)
        self.assertEqual(charge["offres"][0]["correspondances"][0]["itm8"], "0000087004067")


if __name__ == "__main__":
    unittest.main()
