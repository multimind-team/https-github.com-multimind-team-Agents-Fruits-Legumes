"""
Tests unitaires pour le module moteur/analyser-ventes-livraisons.py.
Vérifie la distinction entre journée atypique isolée (protection anti-rupture)
et sur-commande récurrente, ainsi que le respect des pouvoirs de l'agent.
"""
import importlib.util
import json
import math
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

RACINE = Path(__file__).resolve().parents[1]
MOTEUR = RACINE / "moteur"


def charger_module(nom, chemin):
    spec = importlib.util.spec_from_file_location(nom, chemin)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestAnalysteVentesLivraisons(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.racine_test = Path(self.temp_dir.name)

        # Création de l'arborescence de test
        self.donnees = self.racine_test / "donnees"
        self.donnees.mkdir()
        self.faits_dir = self.donnees / "faits"
        self.faits_dir.mkdir()

        # Copie de pouvoirs.json
        (self.donnees / "pouvoirs.json").write_bytes((RACINE / "donnees" / "pouvoirs.json").read_bytes())

        # Chargement du module
        self.mod = charger_module("analyser_ventes_livraisons_test", MOTEUR / "analyser-ventes-livraisons.py")
        self.mod.RACINE = self.racine_test
        self.mod.DONNEES = self.donnees
        self.mod.DOSSIER_FAITS = self.faits_dir
        self.mod.FICHIER_PROPOSITION = self.donnees / "proposition.json"
        self.mod.FICHIER_RAPPORT = self.donnees / "analyse-ventes-livraisons.json"
        self.mod.POUVOIRS_PATH = self.donnees / "pouvoirs.json"
        self.mod.FICHIER_METEO = self.donnees / "meteo-historique.json"
        self.mod.FICHIER_CALENDRIER = self.donnees / "calendrier.json"
        self.mod.FICHIER_OUVERTURES = self.donnees / "ouverture-jours-feries.json"
        self.mod.FICHIER_METEO.write_text(json.dumps({f"2026-09-{j:02d}": [24, 0] for j in range(1, 16)}), encoding="utf-8")
        self.mod.FICHIER_CALENDRIER.write_text(json.dumps({"feries": {}, "vacances": [
            {"debut": "2026-01-01", "fin": "2026-01-02", "nom": "Hiver"},
            {"debut": "2026-12-24", "fin": "2026-12-31", "nom": "Noël"}]}), encoding="utf-8")
        self.mod.FICHIER_OUVERTURES.write_text('{"jours": {}}', encoding="utf-8")
        (self.donnees / "agregats.json").write_text(json.dumps({
            "jours_ventes_integres": [f"2026-09-{j:02d}" for j in range(1, 12)]}), encoding="utf-8")
        self.catalogue_patch = patch.object(self.mod.catalogue, "articles", return_value={})
        self.catalogue_patch.start()
        self.addCleanup(self.catalogue_patch.stop)
        class JourFige(date):
            @classmethod
            def today(cls):
                return cls(2026, 9, 15)
        date_patch = patch.object(self.mod, "date", JourFige)
        date_patch.start()
        self.addCleanup(date_patch.stop)

    def creer_faits(self, faits_liste):
        fichier = self.faits_dir / "2026.jsonl"
        with open(fichier, "w", encoding="utf-8") as f:
            for item in faits_liste:
                f.write(json.dumps(item) + "\n")

    def creer_proposition(self, itm8, propose_colis, date_commande="2026-09-12"):
        prop = {
            "date_commande": date_commande,
            "date_reference": "2026-09-11",
            "lignes": [
                {
                    "itm8": itm8,
                    "libelle": "Article Test",
                    "propose_colis": propose_colis,
                    "conditionnement": 1.0,
                }
            ],
        }
        self.mod.FICHIER_PROPOSITION.write_text(json.dumps(prop), encoding="utf-8")

    def test_journee_atypique_isolee_anti_rupture(self):
        """
        Scénario 1 : 10 colis livrés, seulement 2 vendus le jour J.
        Mais c'est une mévente isolée.
        Règle anti-rupture : 0 réduction proposée, pas de risque de rupture le lendemain.
        """
        itm8 = "0000087009999"
        faits = [
            # Livraison de 10 colis le 2026-09-10
            {
                "type": "livraison",
                "article": itm8,
                "date_source": "2026-09-10",
                "colis": 10.0,
                "quantite": 10.0,
                "par_colis": 1.0,
            },
            # Seulement 2 unités vendues le 2026-09-10 (sous-écoulement ponctuel)
            {
                "type": "vente",
                "article": itm8,
                "date_source": "2026-09-10",
                "quantite": 2.0,
            },
        ]
        self.creer_faits(faits)
        self.creer_proposition(itm8, propose_colis=10.0)

        rapport = self.mod.analyser(fenetre_jours=7, seuil_ecoulement=0.50)

        # Vérification de la synthèse
        self.assertEqual(rapport["synthese"]["journees_isolees_sans_action"], 1)
        self.assertEqual(rapport["synthese"]["surcommandes_recurrentes_detectees"], 0)

        # Vérification de l'article dans les anomalies isolées
        anomalie = rapport["anomalies_isolees"][0]
        self.assertEqual(anomalie["itm8"], itm8)
        self.assertEqual(anomalie["statut"], "isole")
        self.assertIsNone(anomalie["ajustement_propose"])
        self.assertIn("AUCUNE réduction de commande n'est proposée", anomalie["motif_analyse"])
        self.assertIn("protéger le rayon contre toute rupture", anomalie["motif_analyse"])

    def test_surcommande_recurrente_avec_matelas_anti_rupture(self):
        """
        Scénario 2 : 2 livraisons consécutives avec sous-écoulement (< 50%).
        Exemple : 10 colis reçus, seulement 2 vendus à chaque fois.
        Proposition de réduction prudente avec matelas de sécurité (+25%), plafonnée à -30%.
        """
        itm8 = "0000087009999"
        faits = [
            # 1ère livraison : 10 reçus, 2 vendus
            {
                "type": "livraison",
                "article": itm8,
                "date_source": "2026-09-08",
                "colis": 10.0,
                "quantite": 10.0,
                "par_colis": 1.0,
            },
            {
                "type": "vente",
                "article": itm8,
                "date_source": "2026-09-08",
                "quantite": 2.0,
            },
            # 2ème livraison consécutive : 10 reçus, 2 vendus
            {
                "type": "livraison",
                "article": itm8,
                "date_source": "2026-09-10",
                "colis": 10.0,
                "quantite": 10.0,
                "par_colis": 1.0,
            },
            {
                "type": "vente",
                "article": itm8,
                "date_source": "2026-09-10",
                "quantite": 2.0,
            },
        ]
        self.creer_faits(faits)
        self.creer_proposition(itm8, propose_colis=10.0)

        rapport = self.mod.analyser(fenetre_jours=7, seuil_ecoulement=0.50)

        self.assertEqual(rapport["synthese"]["surcommandes_recurrentes_detectees"], 1)
        recurrent = rapport["anomalies_recurrentes"][0]
        self.assertEqual(recurrent["itm8"], itm8)
        self.assertEqual(recurrent["consecutive_faibles"], 2)

        ajust = recurrent["ajustement_propose"]
        self.assertIsNotNone(ajust)
        self.assertEqual(ajust["avant"], 10.0)
        # Baisse maximale autorisée : 30% -> 10 * 0.7 = 7 colis
        self.assertEqual(ajust["apres"], 7.0)
        self.assertLessEqual(ajust["baisse_pourcent"], 30.0)
        # Matelas anti-rupture : 2 ventes/j * 1.25 = 2.5 -> ceil = 3 colis
        self.assertEqual(ajust["buffer_anti_rupture"], 3.0)
        self.assertGreaterEqual(ajust["apres"], ajust["buffer_anti_rupture"])

    def test_respect_plafond_pouvoirs_commande_faible(self):
        """
        Scénario 3 : Article avec proposition initiale de 2 colis.
        Réduire d'1 colis ferait -50% (au-delà des 30% autorisés).
        Le système ne doit pas proposer une réduction illégale qui serait refusée par ajuster-commande.py.
        """
        itm8 = "0000087008888"
        faits = [
            {"type": "livraison", "article": itm8, "date_source": "2026-09-08", "colis": 2.0, "quantite": 2.0, "par_colis": 1.0},
            {"type": "vente", "article": itm8, "date_source": "2026-09-08", "quantite": 0.0},
            {"type": "livraison", "article": itm8, "date_source": "2026-09-10", "colis": 2.0, "quantite": 2.0, "par_colis": 1.0},
            {"type": "vente", "article": itm8, "date_source": "2026-09-10", "quantite": 0.0},
        ]
        self.creer_faits(faits)
        self.creer_proposition(itm8, propose_colis=2.0)

        rapport = self.mod.analyser(fenetre_jours=7, seuil_ecoulement=0.50)

        self.assertEqual(rapport["synthese"]["surcommandes_recurrentes_detectees"], 1)
        recurrent = rapport["anomalies_recurrentes"][0]
        # Vérification qu'aucun ajustement dépassant 30% n'est généré
        self.assertIsNone(recurrent["ajustement_propose"])
        self.assertIn("dépasserait le plafond d'ajustement autorisé de 30 %", recurrent["motif_analyse"])
        self.assertIn("Arbitrage manuel recommandé", recurrent["motif_analyse"])

    def test_sous_ecoulement_avec_causes_externes_bloque_reduction(self):
        """
        Scénario 4 : Sous-écoulement consécutif sur 2 réceptions, mais survenu lors d'un jour
        avec cause externe (pluie forte >= 5mm ou jour férié ou magasin fermé).
        Règle d'or : Interdiction absolue de réduire la commande ! La mévente est contextuelle
        et non structurelle. Une réduction créerait une rupture lors du retour à la normale.
        """
        itm8 = "0000087007777"
        # 1ère livraison : 10 reçus, 2 vendus
        # 2ème livraison : 10 reçus, 2 vendus le 2026-09-10 (jour de pluie à 15 mm)
        faits = [
            {"type": "livraison", "article": itm8, "date_source": "2026-09-08", "colis": 10.0, "quantite": 10.0, "par_colis": 1.0},
            {"type": "vente", "article": itm8, "date_source": "2026-09-08", "quantite": 2.0},
            {"type": "livraison", "article": itm8, "date_source": "2026-09-10", "colis": 10.0, "quantite": 10.0, "par_colis": 1.0},
            {"type": "vente", "article": itm8, "date_source": "2026-09-10", "quantite": 2.0},
        ]
        self.creer_faits(faits)
        self.creer_proposition(itm8, propose_colis=10.0)

        # Création d'un fichier météo de test avec 15 mm de pluie le 2026-09-10
        meteo_test = {"2026-09-10": [16.0, 15.0]}
        (self.donnees / "meteo-historique.json").write_text(json.dumps(meteo_test), encoding="utf-8")
        self.mod.FICHIER_METEO = self.donnees / "meteo-historique.json"

        rapport = self.mod.analyser(fenetre_jours=7, seuil_ecoulement=0.50)

        self.assertEqual(rapport["synthese"]["surcommandes_recurrentes_detectees"], 1)
        self.assertEqual(rapport["synthese"]["recurrentes_causes_externes_sans_baisse"], 1)
        recurrent = rapport["anomalies_recurrentes"][0]
        self.assertEqual(recurrent["itm8"], itm8)
        self.assertEqual(recurrent["statut"], "recurrent_cause_externe")
        self.assertIsNone(recurrent["ajustement_propose"])
        self.assertTrue(len(recurrent["causes_externes"]) >= 1)
        self.assertIn("Intempéries / Pluie (15 mm)", str(recurrent["causes_externes"]))
        self.assertIn("La mévente n'étant pas structurelle", recurrent["motif_analyse"])
        self.assertIn("commande actuelle de 10 colis maintenue pour garantir zéro rupture", recurrent["motif_analyse"])

    def faits_recurrents(self):
        return [{"type": "livraison", "article": "A", "date_source": jour, "colis": 10,
                 "quantite": 10, "par_colis": 1} for jour in ("2026-09-08", "2026-09-10")] + [
                {"type": "vente", "article": "A", "date_source": jour, "quantite": 2}
                for jour in ("2026-09-08", "2026-09-10")]

    def test_meteo_absente_suspend_baisse_recurrente(self):
        self.creer_faits(self.faits_recurrents())
        self.creer_proposition("A", 10)
        self.mod.FICHIER_METEO.unlink()
        resultat = self.mod.analyser()["anomalies_recurrentes"][0]
        self.assertEqual(resultat["statut"], "recurrent_contexte_incomplet")
        self.assertIsNone(resultat["ajustement_propose"])

    def test_journee_de_ventes_absente_suspend_baisse_recurrente(self):
        self.creer_faits(self.faits_recurrents())
        self.creer_proposition("A", 10)
        (self.donnees / "agregats.json").unlink()
        resultat = self.mod.analyser()["anomalies_recurrentes"][0]
        self.assertEqual(resultat["statut"], "recurrent_contexte_incomplet")
        self.assertIsNone(resultat["ajustement_propose"])

    def test_ventes_apres_reception_comptent_et_livraison_future_exclue(self):
        mouvements = self.faits_recurrents()
        # Entre deux réceptions, la vente du lendemain évite une fausse mévente.
        mouvements.append({"type": "vente", "article": "A", "date_source": "2026-09-09", "quantite": 8})
        # La réception du 15 ne doit jamais être comparée aux ventes du 14.
        mouvements.append({"type": "livraison", "article": "A", "date_source": "2026-09-14", "date_effet": "2026-09-15", "quantite": 100, "colis": 100, "par_colis": 1})
        self.creer_faits(mouvements)
        self.creer_proposition("A", 10)
        resultat = self.mod.analyser()
        self.assertEqual(resultat["anomalies_recurrentes"], [])
        isole = resultat["anomalies_isolees"][0]
        self.assertEqual(isole["receptions_observees"], 2)
        self.assertEqual(isole["derniere_reception"]["date"], "2026-09-10")


if __name__ == "__main__":
    unittest.main()
