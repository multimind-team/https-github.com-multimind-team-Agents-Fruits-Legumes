"""
Tests unitaires pour l'agent-audit-stock et la sentinelle unifiée :
1. moteur/analyser-ecarts-comptage.py
   - Règle des 17h / matin avant réception du mail
   - Casse et démarque périssable non enregistrée
   - Inversion de scan en caisse / codes jumeaux
   - Anomalie de livraison / surplus
2. moteur/surveille-mail-message-comptage.py
   - Détection des comptages chambre froide
   - Détection des messages chat
   - Mode passif et filtre d'idempotence
"""
import importlib.util
import json
from pathlib import Path
import tempfile
from unittest.mock import patch
import unittest

RACINE = Path(__file__).resolve().parents[1]
MOTEUR = RACINE / "moteur"


def charger_module(nom, chemin):
    spec = importlib.util.spec_from_file_location(nom, chemin)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestAuditStock(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.racine_test = Path(self.temp_dir.name)

        self.donnees = self.racine_test / "donnees"
        self.donnees.mkdir()
        self.faits_dir = self.donnees / "faits"
        self.faits_dir.mkdir()

        # Copie de pouvoirs.json
        (self.donnees / "pouvoirs.json").write_bytes((RACINE / "donnees" / "pouvoirs.json").read_bytes())

        # Chargement des modules à tester
        self.mod_audit = charger_module("analyser_ecarts_comptage_test", MOTEUR / "analyser-ecarts-comptage.py")
        self.mod_audit.RACINE = self.racine_test
        self.mod_audit.DONNEES = self.donnees
        self.mod_audit.DOSSIER_FAITS = self.faits_dir
        self.mod_audit.FICHIER_AUDIT = self.donnees / "audit-comptages.json"
        self.mod_audit.FICHIER_RECEPTIONS = self.donnees / "receptions-courrier.json"

        self.mod_sentinelle = charger_module("surveille_sentinelle_test", MOTEUR / "surveille-mail-message-comptage.py")
        self.mod_sentinelle.RACINE = self.racine_test
        self.mod_sentinelle.DONNEES = self.donnees
        self.mod_sentinelle.DOSSIER_FAITS = self.faits_dir
        self.mod_sentinelle.MESSAGES_PATH = self.donnees / "messages.jsonl"

    def ecrire_faits(self, annee, faits_liste):
        fichier = self.faits_dir / f"{annee}.jsonl"
        with open(fichier, "w", encoding="utf-8") as f:
            for f_item in faits_liste:
                f.write(json.dumps(f_item, ensure_ascii=False) + "\n")

    def test_moment_du_comptage_17h_et_matin(self):
        """Vérifie la qualification temporelle du comptage."""
        # Cas 1 : Comptage le soir à 18h15
        fait_soir = {
            "type": "comptage",
            "article": "1001",
            "enregistre_le": "2026-09-11T18:15:00",
            "date_effet": "2026-09-11"
        }
        moment = self.mod_audit.moment_du_comptage(fait_soir)
        self.assertEqual(moment, "soir")

        # Cas 2 : Comptage le matin à 06:10 avant mail reçu à 06:45
        heures_mail = {"2026-09-12": "06:45:00"}
        fait_matin = {
            "type": "comptage",
            "article": "1001",
            "horodatage": "2026-09-12T06:10:00",
            "date_effet": "2026-09-12"
        }
        moment = self.mod_audit.moment_du_comptage(fait_matin, heures_mail)
        self.assertEqual(moment, "avant-livraison")

        # Cas 3 : Comptage le matin à 08:30 après mail reçu à 06:45
        fait_apres = {
            "type": "comptage",
            "article": "1001",
            "horodatage": "2026-09-12T08:30:00",
            "date_effet": "2026-09-12"
        }
        moment = self.mod_audit.moment_du_comptage(fait_apres, heures_mail)
        self.assertEqual(moment, "matin")

    def test_regle_17h_livraison_quai_detectee(self):
        """Vérifie la détection de la livraison quai non comptée en chambre froide."""
        # Un comptage du soir (ou matin avant livraison) indique 2 colis (10 unités).
        # La livraison enregistrée pour le 2026-09-11 est de 8 colis (40 unités).
        # Théorique = 50 unités (10 colis), Physique = 10 unités (2 colis) -> écart -40 unités (-8 colis).
        faits = [
            # Stock initial veille
            {"id": "cpt-0", "type": "comptage", "date_effet": "2026-09-10", "article": "1001", "colis": 2, "quantite": 10},
            # Livraison du matin
            {"id": "liv-1", "type": "livraison", "date_effet": "2026-09-11", "article": "1001", "colis": 8, "quantite": 40},
            # Nouveau comptage fait le soir à 18h00 : le responsable n'a compté que ce qu'il a vu en chambre
            {
                "id": "cpt-1",
                "type": "comptage",
                "date_effet": "2026-09-11",
                "article": "1001",
                "libelle": "MELON CHARENTAIS",
                "colis": 2,
                "quantite": 10,
                "unite": "pieces",
                "colisage": 5.0,
                "horodatage": "2026-09-11T18:00:00"
            }
        ]
        self.ecrire_faits(2026, faits)

        rapport = self.mod_audit.analyser_comptages_recents(date_cible="2026-09-11")
        self.assertEqual(len(rapport["resultats"]), 1)
        analyse = rapport["resultats"][0]

        # La règle 17h / livraison quai doit être dans les causes identifiées
        causes = [c["type"] for c in analyse.get("causes_identifiees", [])]
        self.assertIn("regle_17h_livraison_matin", causes)

    def test_casse_non_enregistree_produit_perissable(self):
        """Vérifie qu'un déficit sur un produit périssable sans démarque récente signale la casse non saisie."""
        faits = [
            {"id": "cpt-0", "type": "comptage", "date_effet": "2026-09-10", "article": "2001", "colis": 10, "quantite": 50},
            {"id": "vte-1", "type": "vente", "date_effet": "2026-09-11", "article": "2001", "colis": 2, "quantite": 10},
            # Théorique = 40 unités. Comptage physique = 20 unités (déficit de 20 unités / 4 colis)
            # Pas de livraison le jour même pour exclure la règle 17h
            {
                "id": "cpt-1",
                "type": "comptage",
                "date_effet": "2026-09-11",
                "article": "2001",
                "libelle": "FRAISE RONDE BARQUETTE",
                "colis": 4,
                "quantite": 20,
                "unite": "barquettes",
                "colisage": 5.0,
                "horodatage": "2026-09-11T14:00:00"
            }
        ]
        self.ecrire_faits(2026, faits)

        rapport = self.mod_audit.analyser_comptages_recents(date_cible="2026-09-11")
        self.assertEqual(len(rapport["resultats"]), 1)
        analyse = rapport["resultats"][0]

        causes = [c["type"] for c in analyse.get("causes_identifiees", [])]
        self.assertIn("casse_non_enregistree", causes)
        self.assertIn("fraise", analyse["explication_responsable"].lower())

    def test_inversion_codes_jumeaux(self):
        """Vérifie la détection de confusion entre articles jumeaux."""
        faits = [
            {"id": "cpt-0", "type": "comptage", "date_effet": "2026-09-10", "article": "3001", "colis": 5, "quantite": 25},
            # Comptage physique avec déficit
            {
                "id": "cpt-1",
                "type": "comptage",
                "date_effet": "2026-09-11",
                "article": "3001",
                "libelle": "TOMATE RONDE EN GRAPPE VRAC",
                "colis": 2,
                "quantite": 10,
                "unite": "kg",
                "colisage": 5.0,
                "horodatage": "2026-09-11T14:00:00"
            }
        ]
        self.ecrire_faits(2026, faits)

        catalogue_mock = {
            "3001": {"code": "3001", "LIBELLE": "TOMATE RONDE EN GRAPPE VRAC"},
            "3002": {"code": "3002", "LIBELLE": "TOMATE RONDE VRAC"}
        }

        with patch.object(self.mod_audit.catalogue, "articles", return_value=catalogue_mock):
            rapport = self.mod_audit.analyser_comptages_recents(date_cible="2026-09-11")
            analyse = rapport["resultats"][0]
            causes = [c["type"] for c in analyse.get("causes_identifiees", [])]
            self.assertIn("code_jumeau_caisse", causes)

    def test_surveille_sentinelle_evenements(self):
        """Vérifie la détection des comptages et messages par la sentinelle."""
        # 1. Test détection nouveaux comptages
        chemin_faits = self.faits_dir / "2026.jsonl"
        self.ecrire_faits(2026, [
            {"id": "cpt-1", "type": "comptage", "article": "1001", "colis": 3},
            {"id": "vte-1", "type": "vente", "article": "1001", "colis": 1}
        ])

        connus = self.mod_sentinelle.charger_identifiants_comptages(chemin_faits)
        self.assertEqual(connus, {"cpt-1"})

        # Pas de nouveau comptage
        nouveaux, connus = self.mod_sentinelle.verifier_nouveaux_comptages(chemin_faits, connus)
        self.assertIsNone(nouveaux)

        # Ajout d'un nouveau comptage
        with open(chemin_faits, "a", encoding="utf-8") as f:
            f.write(json.dumps({"id": "cpt-2", "type": "comptage", "article": "2002", "colis": 5}) + "\n")

        nouveaux, connus = self.mod_sentinelle.verifier_nouveaux_comptages(chemin_faits, connus)
        self.assertIsNotNone(nouveaux)
        self.assertEqual(len(nouveaux), 1)
        self.assertEqual(nouveaux[0]["id"], "cpt-2")
        self.assertNotIn("cpt-2", connus)  # Détecter n'acquitte pas le traitement.
        reprise, _ = self.mod_sentinelle.verifier_nouveaux_comptages(chemin_faits, connus)
        self.assertEqual(reprise, nouveaux)
        with patch.object(self.mod_sentinelle, "DONNEES", self.donnees):
            self.mod_sentinelle.enregistrer_evenements([("COMPTAGE", nouveaux[0])])
            self.assertIn("COMPTAGE:cpt-2", self.mod_sentinelle.charger_file()["en_attente"])
            self.mod_sentinelle.acquitter("COMPTAGE", "cpt-2", "controle:fixture-verifiee")
            self.assertIn("COMPTAGE:cpt-2", self.mod_sentinelle.charger_file()["acquittes"])

        # 2. Test détection nouveaux messages du rayon
        msg_file = self.donnees / "messages.jsonl"
        with open(msg_file, "w", encoding="utf-8") as f:
            f.write(json.dumps({"id": "msg-1", "texte": "Bonjour"}) + "\n")

        connus_msg = self.mod_sentinelle.charger_identifiants_messages(msg_file)
        self.assertEqual(connus_msg, {"msg-1"})

        # Ajout d'un message
        with open(msg_file, "a", encoding="utf-8") as f:
            f.write(json.dumps({"id": "msg-2", "texte": "Plus de salade"}) + "\n")

        nouveaux_msg, connus_msg = self.mod_sentinelle.verifier_nouveaux_messages(msg_file, connus_msg)
        self.assertIsNotNone(nouveaux_msg)
        self.assertEqual(len(nouveaux_msg), 1)
        self.assertEqual(nouveaux_msg[0]["id"], "msg-2")
        self.assertNotIn("msg-2", connus_msg)


if __name__ == "__main__":
    unittest.main()

