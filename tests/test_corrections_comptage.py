import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MOTEUR = Path(__file__).resolve().parents[1] / "moteur"
SPEC = importlib.util.spec_from_file_location("calculer_position", MOTEUR / "calculer-position.py")
CALCUL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CALCUL)


class CorrectionsComptageTests(unittest.TestCase):
    def test_correction_append_only_remplace_la_position_sans_effacer_le_comptage(self):
        with tempfile.TemporaryDirectory() as repertoire:
            dossier = Path(repertoire)
            (dossier / "2026.jsonl").write_text(
                "\n".join([
                    json.dumps({"id": "comptage:2026-09-07:123:saisie", "type": "comptage", "article": "123", "date_source": "2026-09-07", "date_effet": "2026-09-07", "quantite": 12, "horodatage": "2026-09-07T19:00:00"}),
                    json.dumps({"id": "correction-comptage:abc", "type": "correction-comptage", "cible_id": "comptage:2026-09-07:123:saisie", "article": "123", "date_source": "2026-09-07", "date_effet": "2026-09-07", "quantite": 24, "horodatage": "2026-09-07T19:05:00"}),
                ]) + "\n", encoding="utf-8"
            )
            ancien = CALCUL.DOSSIER_FAITS
            try:
                CALCUL.DOSSIER_FAITS = dossier
                resultat = CALCUL.calculer()
            finally:
                CALCUL.DOSSIER_FAITS = ancien

        self.assertEqual(resultat["123"]["position"], 24)


if __name__ == "__main__":
    unittest.main()
