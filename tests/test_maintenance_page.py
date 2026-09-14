import unittest
from pathlib import Path


RACINE = Path(__file__).resolve().parents[1]


class MaintenancePageTests(unittest.TestCase):
    def test_annonce_un_serveur_actif_lorsque_la_page_est_chargee(self):
        page = (RACINE / "app" / "maintenance.html").read_text(encoding="utf-8")

        self.assertIn('etat.textContent = "Serveur actif — socle en place"', page)
        self.assertIn('etat.textContent = "Serveur actif — données à initialiser"', page)
        self.assertNotIn('etat.textContent = "Projet non démarré"', page)


if __name__ == "__main__":
    unittest.main()
