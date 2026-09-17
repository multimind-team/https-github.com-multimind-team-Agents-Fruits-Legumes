import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "moteur"))

import saisonnalite_masquage


class SaisonnaliteMasquageTests(unittest.TestCase):
    def test_analyse_recommandations_reelles(self):
        rec = saisonnalite_masquage.analyser_recommandations(RACINE)
        self.assertIsNotNone(rec)
        self.assertIn("a_demasquer", rec)
        self.assertIn("a_masquer", rec)
        self.assertGreater(len(rec["a_demasquer"]), 0)
        self.assertGreater(len(rec["a_masquer"]), 0)

        # Vérification des potimarrons / butternuts dans les articles à démasquer
        demasques_codes = {item["itm8"]: item for item in rec["a_demasquer"]}
        noms_demasques = " ".join(item["libelle"].lower() for item in rec["a_demasquer"])
        self.assertTrue(
            "potimarron" in noms_demasques or "butternut" in noms_demasques,
            "Les potimarrons ou butternuts doivent être suggérés au démasquage"
        )
        for itm, item in demasques_codes.items():
            if "potimarron" in item["libelle"].lower():
                self.assertIn("quand", item)
                self.assertTrue(len(item["quand"]) > 0)
                self.assertIn("maintenant", item["quand"].lower())

        # Vérification des melons dans les articles à masquer
        noms_masques = " ".join(item["libelle"].lower() for item in rec["a_masquer"])
        self.assertTrue(
            "melon" in noms_masques,
            "Les melons doivent être suggérés au masquage pour fin de saison"
        )
        masques_codes = {item["itm8"]: item for item in rec["a_masquer"]}
        for itm, item in masques_codes.items():
            if "melon piece" in item["libelle"].lower():
                self.assertIn("quand", item)
                self.assertIn("semaine", item["quand"].lower())
                self.assertLessEqual(item["evolution_pct"], -35.0)

    def test_synthese_note_du_matin(self):
        rec = saisonnalite_masquage.analyser_recommandations(RACINE)
        points = saisonnalite_masquage.synthese_note_du_matin(rec)
        self.assertEqual(len(points), 2)
        for pt in points:
            self.assertEqual(pt["gravite"], "attention")
            self.assertIn("heure", pt)
            self.assertIn("texte", pt)

        texte_demasquer = points[0]["texte"]
        texte_masquer = points[1]["texte"]

        self.assertIn("démasquer", texte_demasquer)
        self.assertIn("Dès maintenant", texte_demasquer)

        self.assertIn("masquer", texte_masquer)
        self.assertIn("Dès maintenant", texte_masquer)

    def test_sauvegarde_et_format_json(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_racine = Path(temp_dir)
            (temp_racine / "donnees").mkdir()
            rec = {
                "calcule_le": "2026-09-17T04:00:00",
                "date_reference": "2026-09-15",
                "a_demasquer": [{"itm8": "0000087004764", "libelle": "POTIMARRON PIECE", "quand": "Dès maintenant", "priorite": 1}],
                "a_masquer": [{"itm8": "0000087003306", "libelle": "MELON PIECE", "quand": "Dès maintenant", "priorite": 1}]
            }
            saisonnalite_masquage.sauvegarder_recommandations(rec, temp_racine)
            fichier = temp_racine / "donnees" / "recommandations-saisonnieres.json"
            self.assertTrue(fichier.exists())
            lu = json.loads(fichier.read_text(encoding="utf-8"))
            self.assertEqual(lu["a_demasquer"][0]["libelle"], "POTIMARRON PIECE")
            self.assertEqual(lu["a_masquer"][0]["libelle"], "MELON PIECE")


if __name__ == "__main__":
    unittest.main()
