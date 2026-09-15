import importlib.util
import sys
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

MOTEUR = Path(__file__).resolve().parents[1] / "moteur"
sys.path.insert(0, str(MOTEUR))
SPEC = importlib.util.spec_from_file_location("integrer_fichiers", MOTEUR / "integrer-fichiers.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class FichiersManquantsParJourTests(unittest.TestCase):
    def test_colisages_refusent_un_carnet_de_decisions_illisible(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(MODULE, "DONNEES", Path(tmp)), \
             patch.object(MODULE.regles, "charger", side_effect=ValueError("Carnet illisible")), \
             self.assertRaisesRegex(ValueError, "Carnet illisible"):
            MODULE.charger_colisages_vrac()

    def test_colisages_refusent_un_cadencier_tronque_sans_le_modifier(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(MODULE, "DONNEES", Path(tmp)):
            fichier = Path(tmp) / "cadencier-du-jour.json"
            fichier.write_bytes(b'{"articles":')
            with self.assertRaises(json.JSONDecodeError):
                MODULE.charger_colisages_vrac()
            self.assertEqual(fichier.read_bytes(), b'{"articles":')

    def test_decision_colisage_invalide_ne_retombe_pas_sur_le_cadencier(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(MODULE, "DONNEES", Path(tmp)):
            (Path(tmp) / "cadencier-du-jour.json").write_text(json.dumps(
                {"articles": [{"article": "TEST", "offres": [{"par_colis": 12}]}]}), encoding="utf-8")
            for valeur in ("illisible", -1, 0, True, float("nan"), float("inf")):
                with self.subTest(valeur=valeur), patch.object(MODULE.regles, "charger", return_value={
                        "overrides": {"TEST": {"conditionnement": valeur}}}), \
                     self.assertRaisesRegex(ValueError, "Colisage de décision invalide"):
                    MODULE.charger_colisages_vrac()

    def test_ne_signale_pas_l_absence_de_casse_ou_de_don(self):
        resume = [
            {"fichier": "Vente-06-09-2026.xlsx", "type": "vente"},
            {"fichier": "Casse-06-09-2026.xlsx", "type": "casse"},
            {"fichier": "Vente-07-09-2026.xlsx", "type": "vente"},
            {"fichier": "Casse-07-09-2026.xlsx", "type": "casse"},
            {"fichier": "Don-07-09-2026.xlsx", "type": "don"},
            {"fichier": "Livraison-07-09-2026.xlsx", "type": "livraison"},
        ]
        self.assertEqual(
            MODULE.types_absents_par_jour(resume),
            {"2026-09-06": {"livraison"}},
        )

    def test_lit_la_date_d_un_export_non_detaille_limite_a_un_seul_jour(self):
        periode = MODULE.periode_selection([
            ["Sélection de données : Du 07/09/2026 Au 07/09/2026"],
        ])

        self.assertEqual(periode, ("2026-09-07", "2026-09-07"))


class TypeDuFichierTests(unittest.TestCase):
    def test_reconnait_les_exports_merc_alys_avec_un_espace_apres_le_type(self):
        self.assertEqual(MODULE.type_du_fichier("vente 07.09.2026.xlsx"), "vente")
        self.assertEqual(MODULE.type_du_fichier("casse 07.09.2026.xlsx"), "casse")
        self.assertEqual(MODULE.type_du_fichier("livraison 07.09.2026.xlsx"), "livraison")


class AlerteChatTests(unittest.TestCase):
    def test_resum_e_les_erreurs_d_import_pour_le_chat(self):
        message = MODULE.message_alerte_chat([
            {"genre": "colonnes-manquantes", "sujet": "vente 07.09.2026.xlsx"},
            {"genre": "fichier-absent", "sujet": "don (2026-09-07)"},
        ], 75)

        self.assertIn("Import incomplet", message)
        self.assertIn("75 mouvements intégrés", message)
        self.assertIn("vente 07.09.2026.xlsx", message)
        self.assertIn("don (2026-09-07)", message)


if __name__ == "__main__":
    unittest.main()
