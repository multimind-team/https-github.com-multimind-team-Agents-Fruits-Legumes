"""Tests isolés pour l'enregistrement des modifications de commande et entraînement IA."""
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
RACINE = Path(__file__).resolve().parents[1]
MOTEUR = RACINE / "moteur"
if str(MOTEUR) not in sys.path:
    sys.path.insert(0, str(MOTEUR))

import enregistrer_modifications_commande as emc


class EnregistrerModificationsCommandeTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.dossier = Path(self.temp_dir.name)
        
        # Données de test
        self.proposition_test = {
            "date_commande": "2026-09-24",
            "date_livraison": "2026-09-25",
            "date_reference": "2026-09-22",
            "meteo_livraison": {"tmax": 32.2, "pluie": 0.0},
            "facteurs": {"jour_semaine_livraison": 1.15, "meteo": 1.25},
            "lignes": [
                {
                    "itm8": "0000087003034",
                    "libelle": "MELON GROS CALIBRE PIECE",
                    "groupe": "fruits",
                    "fournisseur": "SCAFRUIT",
                    "propose_colis": 33.0,
                    "conditionnement": 9.0,
                    "unite": "Pièce",
                    "position_colis": 1.8,
                    "position_unites": 16.0,
                    "demande": 313.33,
                    "vente_moyenne_jour": 85.79,
                    "taux_perte": 0.001,
                    "prix_achat": 2.55,
                    "prix_vente": 3.96,
                    "marge_pct": 35.6,
                    "previsions_journalieres": {"2026-09-24": 142.5, "2026-09-25": 170.8},
                    "promotion": False,
                    "fin_promotion": False,
                }
            ]
        }
        (self.dossier / "proposition.json").write_text(json.dumps(self.proposition_test), encoding="utf-8")
        (self.dossier / "pouvoirs.json").write_bytes((RACINE / "donnees" / "pouvoirs.json").read_bytes())

    def test_archive_proposition_base(self):
        cible = emc.archiver_proposition_base(self.dossier)
        self.assertTrue(cible.exists())
        self.assertEqual(cible.name, "proposition-2026-09-24.json")
        archive = json.loads(cible.read_text(encoding="utf-8"))
        self.assertEqual(archive["date_commande"], "2026-09-24")
        self.assertEqual(len(archive["lignes"]), 1)

    def test_enregistrer_modification_et_entrainement(self):
        res = emc.enregistrer_modification(
            "0000087003034", 9.0,
            motif="Sur-commande algorithmique melon : 9 colis suffisent pour la météo réelle.",
            agent="responsable-rayon",
            source="app/commander.html",
            dossier_donnees=self.dossier
        )
        self.assertTrue(res["ok"])
        self.assertEqual(res["avant"], 33.0)
        self.assertEqual(res["apres"], 9.0)

        # Vérifier ajustements.jsonl
        fic_ajust = self.dossier / "ajustements.jsonl"
        self.assertTrue(fic_ajust.exists())
        lignes_ajust = [json.loads(l) for l in fic_ajust.read_text(encoding="utf-8").splitlines() if l.strip()]
        self.assertEqual(len(lignes_ajust), 1)
        self.assertEqual(lignes_ajust[0]["article"], "0000087003034")
        self.assertEqual(lignes_ajust[0]["avant"], 33.0)
        self.assertEqual(lignes_ajust[0]["apres"], 9.0)
        self.assertTrue(lignes_ajust[0]["applique"])
        self.assertEqual(lignes_ajust[0]["agent"], "responsable-rayon")

        # Vérifier entrainement-ajustements.jsonl
        fic_train = self.dossier / "entrainement-ajustements.jsonl"
        self.assertTrue(fic_train.exists())
        lignes_train = [json.loads(l) for l in fic_train.read_text(encoding="utf-8").splitlines() if l.strip()]
        self.assertEqual(len(lignes_train), 1)
        t = lignes_train[0]
        self.assertEqual(t["schema"], 1)
        self.assertEqual(t["article"], "0000087003034")
        self.assertEqual(t["propose_ia_colis"], 33.0)
        self.assertEqual(t["choix_humain_colis"], 9.0)
        self.assertEqual(t["ecart_colis"], -24.0)
        self.assertEqual(t["type_ajustement"], "baisse")
        self.assertEqual(t["vente_moyenne_jour"], 85.79)
        self.assertEqual(t["conditionnement"], 9.0)
        self.assertEqual(t["meteo_livraison"]["tmax"], 32.2)
        self.assertEqual(t["auteur"], "responsable-rayon")


if __name__ == "__main__":
    unittest.main()
