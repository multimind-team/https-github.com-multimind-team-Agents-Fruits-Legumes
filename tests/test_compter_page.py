import unittest
from pathlib import Path


RACINE = Path(__file__).resolve().parents[1]


class ComptagePageTests(unittest.TestCase):
    def test_bouton_envoyer_est_disponible_pendant_le_comptage(self):
        page = (RACINE / "app" / "compter.html").read_text(encoding="utf-8")
        debut = page.index('<div class="bas">')
        fin = page.index('</div>', debut)
        panneau_actif = page[debut:fin]
        self.assertIn('id="envoyer"', panneau_actif)
        self.assertIn('Envoyer mes comptages', panneau_actif)


if __name__ == "__main__":
    unittest.main()
