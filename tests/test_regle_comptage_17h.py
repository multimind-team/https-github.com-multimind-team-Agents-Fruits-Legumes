"""
tests/test_regle_comptage_17h.py - Vérifie la règle métier pour compter la chambre froide :
- Entre 17h00 et la réception du mail du lendemain matin :
  la livraison du matin n'est pas encore entrée en chambre froide (non comptée dans le stock).
- Après la réception du mail du matin :
  la modification du stock inclut la livraison.
"""
import unittest
import importlib.util
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
MOTEUR = RACINE / "moteur"
sys.path.insert(0, str(MOTEUR))

spec = importlib.util.spec_from_file_location("calc_pos", MOTEUR / "calculer-position.py")
pos = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pos)


class TestRegleComptage17h(unittest.TestCase):

    def test_comptage_soir_apres_17h(self):
        """Un comptage fait après 17h00 est un comptage du soir."""
        fait = {
            "type": "comptage",
            "date_effet": "2026-09-11",
            "horodatage": "2026-09-11T18:30:00"
        }
        moment = pos.moment_du_comptage(fait)
        self.assertEqual(moment, "soir")

        depart = {"date": "2026-09-11", "moment": moment, "valeur": 10.0}
        # Même jour (2026-09-11) : rien du jour ne s'applique (tout est déjà dedans)
        self.assertFalse(pos.a_appliquer("2026-09-11", "livraison", depart))
        self.assertFalse(pos.a_appliquer("2026-09-11", "vente", depart))
        # Lendemain (2026-09-12) : la nouvelle livraison s'applique
        self.assertTrue(pos.a_appliquer("2026-09-12", "livraison", depart))

    def test_comptage_matin_avant_reception_mail(self):
        """Un comptage fait le matin AVANT la réception du mail n'a pas la livraison.
        La livraison du jour DOIT donc s'ajouter."""
        fait = {
            "type": "comptage",
            "date_effet": "2026-09-12",
            "horodatage": "2026-09-12T05:30:00"
        }
        heures_mail = {"2026-09-12": "06:15:00"}
        moment = pos.moment_du_comptage(fait, heures_mail)
        self.assertEqual(moment, "avant-livraison")

        depart = {"date": "2026-09-12", "moment": moment, "valeur": 10.0}
        # La livraison du jour même n'était pas dedans : elle doit s'appliquer (s'ajouter)
        self.assertTrue(pos.a_appliquer("2026-09-12", "livraison", depart))
        # Les sorties de la journée n'étaient pas dedans non plus : elles doivent s'appliquer (se déduire)
        self.assertTrue(pos.a_appliquer("2026-09-12", "vente", depart))

    def test_comptage_matin_apres_reception_mail(self):
        """Un comptage fait le matin APRÈS la réception du mail a déjà la livraison rangée.
        La livraison du jour NE DOIT PAS s'ajouter une seconde fois."""
        fait = {
            "type": "comptage",
            "date_effet": "2026-09-12",
            "horodatage": "2026-09-12T07:15:00"
        }
        heures_mail = {"2026-09-12": "06:15:00"}
        moment = pos.moment_du_comptage(fait, heures_mail)
        self.assertEqual(moment, "matin")

        depart = {"date": "2026-09-12", "moment": moment, "valeur": 15.0}
        # La livraison du jour même est déjà rangée : elle NE DOIT PAS s'appliquer
        self.assertFalse(pos.a_appliquer("2026-09-12", "livraison", depart))
        # Les sorties de la journée ne sont pas encore dedans : elles doivent s'appliquer (se déduire)
        self.assertTrue(pos.a_appliquer("2026-09-12", "vente", depart))


if __name__ == "__main__":
    unittest.main()
