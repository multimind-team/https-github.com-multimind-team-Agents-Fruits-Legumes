import unittest
from pathlib import Path


RACINE = Path(__file__).resolve().parent.parent


class CommanderPageTests(unittest.TestCase):
    def test_echappe_les_champs_importes_avant_affichage_html(self):
        page = (RACINE / "app" / "commander.html").read_text(encoding="utf-8")

        self.assertIn("function texteSecurise", page)
        self.assertIn("texteSecurise(l.libelle)", page)
        self.assertIn("texteSecurise(l.unite)", page)
        self.assertIn("texteSecurise(l.fournisseur)", page)
        self.assertIn("texteSecurise(a.motif)", page)
        self.assertIn("texteSecurise(detail)", page)

    def test_utilise_le_jour_attendu_du_filet_apres_la_cloture(self):
        page = (RACINE / "app" / "commander.html").read_text(encoding="utf-8")

        self.assertIn("fraicheur.jour_de_commande_attendu", page)

    def test_ne_garde_pas_un_jour_attendu_devenu_perime_apres_la_cloture(self):
        page = (RACINE / "app" / "commander.html").read_text(encoding="utf-8")

        self.assertIn("function jourAttenduActuel", page)
        self.assertIn("const jourAttendu = jourAttenduActuel();", page)
        self.assertNotIn(
            "const jourAttendu = (fraicheur && fraicheur.jour_de_commande_attendu) || aujourdhui;",
            page,
        )

    def test_affiche_toujours_le_badge_promo_sans_statut_a_confirmer(self):
        page = (RACINE / "app" / "commander.html").read_text(encoding="utf-8")

        self.assertIn('const etiquettePromo = promo ? \'<div class="badge-promo">PROMO</div>\' : "";', page)
        self.assertNotIn("PROMO — À CONFIRMER", page)


if __name__ == "__main__":
    unittest.main()
