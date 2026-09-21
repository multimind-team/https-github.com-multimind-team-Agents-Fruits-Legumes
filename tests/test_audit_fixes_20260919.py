"""
Tests de non-régression validant l'ensemble des corrections de l'audit du 19 septembre 2026 :
- Division par zéro (tauxPerte 100%)
- Intégration de la demande du dimanche matin pour la commande du week-end
- Blocage des positions aberrantes (<= -15 colis sans comptage du jour)
- Normalisation des codes Excel numériques (flottants et entiers courts)
- Détection des conflits sur l'heure physique dans la signature des faits
- Normalisation des fuseaux horaires vers l'heure locale Europe/Paris
- Simulation de facture directe sans écriture sur disque et support multi-dates
"""
import json
import shutil
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import sys
RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "moteur"))

import importlib.util

def _charger(nom, fichier):
    spec = importlib.util.spec_from_file_location(nom, RACINE / "moteur" / fichier)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

calc = _charger("calc", "calculer-commande.py")
prop = _charger("prop", "proposer-commande.py")
intf = _charger("intf", "integrer-fichiers.py")
pos = _charger("pos", "calculer-position.py")
import faits
import facture_directe


class AuditFixes20260919Tests(unittest.TestCase):

    def test_division_par_zero_taux_perte_securise(self):
        """Défaut 4 : un article avec vendu=0 et casse>0 ne doit pas crasher le calcul."""
        moyennes = {"art1": {"saison": [10.0] * 366, "tauxPerte": 1.0}}
        positions = {"art1": {"position": 5.0, "mesuree_le": "2026-09-19"}}
        mercalys = {"art1": {"CONDIT.BASE": 1, "LIBELLE": "Test"}}
        res = prop.proposer("2026-09-18", moyennes, positions, {}, mercalys, {}, [100] * 7, {})
        self.assertGreater(res["lignes"]["art1"]["demande"], 0)
        self.assertGreater(res["lignes"]["art1"]["propose_colis"], 0)

    def test_integration_demande_dimanche_matin(self):
        """Risque R1 : commande du samedi vers lundi inclut la demande du dimanche matin."""
        # profil hebdomadaire avec dimanche à ~25% du samedi
        profil = [2000, 2000, 2000, 2000, 2000, 3000, 600]
        moyennes = {"art1": {"saison": [10.0] * 366, "tauxPerte": 0.05}}
        mercalys = {"art1": {"CONDIT.BASE": 1, "LIBELLE": "Test"}}

        # Samedi 19/09 -> Lundi 21/09 (dimanche 20/09 intermédiaire)
        res_samedi = prop.proposer("2026-09-18", moyennes, {"art1": {"position": 0, "mesuree_le": "2026-09-19"}},
                                   {}, mercalys, {}, profil, {})
        self.assertEqual(res_samedi["date_commande"], "2026-09-19")
        self.assertEqual(res_samedi["date_livraison"], "2026-09-21")

        # Lundi 21/09 -> Mardi 22/09 (aucun jour intermédiaire)
        res_lundi = prop.proposer("2026-09-20", moyennes, {"art1": {"position": 0, "mesuree_le": "2026-09-21"}},
                                  {}, mercalys, {}, profil, {})
        self.assertEqual(res_lundi["date_commande"], "2026-09-21")
        self.assertEqual(res_lundi["date_livraison"], "2026-09-22")

        # La demande samedi -> lundi doit strictement dépasser lundi -> mardi car elle couvre le dimanche matin
        self.assertGreater(res_samedi["lignes"]["art1"]["demande"], res_lundi["lignes"]["art1"]["demande"])

    def test_blocage_positions_aberrantes(self):
        """Risque R2 : une position <= -15 colis avec comptage ancien est bloquée à 0."""
        moyennes = {"art1": {"saison": [10.0] * 366, "tauxPerte": 0.05}}
        mercalys = {"art1": {"CONDIT.BASE": 1, "LIBELLE": "Test"}}
        profil = [1000] * 7

        # Position -45 colis comptée il y a 4 jours : bloquée
        pos_ancienne = {"art1": {"position": -45.0, "mesuree_le": "2026-09-15"}}
        res_bloque = prop.proposer("2026-09-18", moyennes, pos_ancienne, {}, mercalys, {}, profil, {})
        self.assertTrue(res_bloque["lignes"]["art1"]["position_bloquee"])
        self.assertEqual(res_bloque["lignes"]["art1"]["propose_colis"], 0.0)

        # Si le responsable a recompté AUJOURD'HUI même avec -45 colis : débloqué
        pos_aujourdhui = {"art1": {"position": -45.0, "mesuree_le": "2026-09-19"}}
        res_debloque = prop.proposer("2026-09-18", moyennes, pos_aujourdhui, {}, mercalys, {}, profil, {})
        self.assertFalse(res_debloque["lignes"]["art1"]["position_bloquee"])
        self.assertGreater(res_debloque["lignes"]["art1"]["propose_colis"], 0.0)

    def test_normalisation_codes_excel(self):
        """Défaut 7 : les codes numériques ou flottants Excel sont normalisés sans perte."""
        self.assertEqual(intf.nettoyer_code_article(49), ("0000000000049", False))
        self.assertEqual(intf.nettoyer_code_article("0000000000049"), ("0000000000049", False))
        self.assertEqual(intf.nettoyer_code_article(87010624.0), ("87010624", False))
        self.assertEqual(intf.nettoyer_code_article("87010624.0"), ("87010624", False))
        self.assertEqual(intf.nettoyer_code_article("Nombre de Lignes : 161"), (None, True))
        self.assertEqual(intf.nettoyer_code_article("Total général"), (None, True))

    def test_signature_fait_detecte_conflit_heure_physique(self):
        """Défaut 6 : deux faits identiques sauf heure de saisie physique doivent être en conflit."""
        f1 = {"id": "c1", "type": "comptage", "article": "123", "quantite": 10,
              "source": {"saisi_le": "2026-09-18T08:00:00"}}
        f2 = {"id": "c1", "type": "comptage", "article": "123", "quantite": 10,
              "source": {"saisi_le": "2026-09-18T18:00:00"}}
        f3 = {"id": "c1", "type": "comptage", "article": "123", "quantite": 10,
              "source": {"saisi_le": "2026-09-18T08:00:00", "autre": "test"}}
        self.assertNotEqual(faits.signature(f1), faits.signature(f2))
        self.assertEqual(faits.signature(f1), faits.signature(f3))

    def test_normalisation_fuseaux_horaires(self):
        """Défaut 5 : UTC 15:30Z et local 17:30+02:00 doivent donner la phase soir (17h30 Europe/Paris)."""
        f_utc = {"source": {"saisi_le": "2026-09-18T15:30:00Z"}, "date_effet": "2026-09-18"}
        f_local = {"source": {"saisi_le": "2026-09-18T17:30:00+02:00"}, "date_effet": "2026-09-18"}
        self.assertEqual(pos.moment_du_comptage(f_utc), "soir")
        self.assertEqual(pos.moment_du_comptage(f_local), "soir")
        self.assertEqual(pos.heure_physique(f_utc), "17:30:00")
        self.assertEqual(pos.heure_physique(f_local), "17:30:00")

    def test_facture_simulation_sans_ecriture_et_multi_dates(self):
        """Défauts 8, 9, 10 : simulation pure sans écriture et support multi-dates."""
        with tempfile.TemporaryDirectory() as tmp:
            racine = Path(tmp)
            dossier = racine / "documents-partages" / "calcul-marge-pomona"
            dossier.mkdir(parents=True)
            source_modele = RACINE / "documents-partages" / "calcul-marge-pomona" / "Calcul marge Pomona - Original.xlsx"
            shutil.copy2(source_modele, dossier / "Calcul marge Pomona - Original.xlsx")

            cible = facture_directe.choisir_classeur(racine, "2026-09-20")
            self.assertFalse(cible.is_file(), "choisir_classeur ne doit pas écrire sur disque")

            facture = {"date_reception": "2026-09-20", "fournisseur": "POMONA", "bordereau": "1", "lignes": []}
            facture_directe.importer_facture(racine, cible, facture, simuler=True, classeur_seul=True)
            self.assertFalse(cible.is_file(), "importer_facture simuler ne doit pas écrire sur disque")

            # Import réel date 1
            f1 = {"date_reception": "2026-09-20", "fournisseur": "POMONA", "bordereau": "1", "lignes": [
                {"article": "0000087004011", "produit": "Banane", "quantite": 10, "pu": 1.5, "colis": 1,
                 "montant_ht": 15, "numero": 1, "unite_uf": "KG"}
            ]}
            b1 = facture_directe.importer_facture(racine, cible, f1, simuler=False, classeur_seul=True)
            self.assertTrue(cible.is_file())
            self.assertEqual(b1["lignes_marge_nouvelles"], 1)

            # Import réel date 2 dans le même fichier
            f2 = {"date_reception": "2026-09-21", "fournisseur": "POMONA", "bordereau": "2", "lignes": [
                {"article": "0000087004011", "produit": "Banane", "quantite": 5, "pu": 1.5, "colis": 1,
                 "montant_ht": 7.5, "numero": 1, "unite_uf": "KG"}
            ]}
            b2 = facture_directe.importer_facture(racine, cible, f2, simuler=False, classeur_seul=True)
            self.assertEqual(b2["lignes_marge_nouvelles"], 1)


if __name__ == "__main__":
    unittest.main()
