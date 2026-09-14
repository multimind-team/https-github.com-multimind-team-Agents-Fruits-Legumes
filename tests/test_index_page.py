import unittest
from pathlib import Path


RACINE = Path(__file__).resolve().parent.parent


class AccueilPageTests(unittest.TestCase):
    def test_echappe_les_textes_externes_avant_leur_affichage_html(self):
        page = (RACINE / "app" / "index.html").read_text(encoding="utf-8")

        self.assertIn("function texteSecurise", page)
        self.assertIn("gras(e.texte)", page)
        self.assertIn("texteSecurise(e.auteur)", page)
        self.assertIn("texteSecurise(e.texte)", page)
        self.assertIn("texteSecurise(e.action)", page)


if __name__ == "__main__":
    unittest.main()
