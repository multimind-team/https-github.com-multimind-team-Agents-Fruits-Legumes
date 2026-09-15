"""Historique calculé sur fixtures, jamais sur les données de l'installation."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "moteur"))
spec = importlib.util.spec_from_file_location(
    "historique_dates_reelles", RACINE / "moteur/analyser-historique-complet.py")
historique = importlib.util.module_from_spec(spec)
spec.loader.exec_module(historique)


class HistoriqueDatesReellesTests(unittest.TestCase):
    def analyser_fixture(self, lignes, *, calendrier=None, meteo=None):
        ventes = [{"type": "vente", "article": "FIXTURE-A", "date_source": jour,
                   "quantite": quantite} for jour, quantite in lignes]
        with tempfile.TemporaryDirectory(prefix="historique-fixture-") as dossier:
            sortie = Path(dossier) / "donnees/analyse.json"
            self.assertFalse(sortie.is_relative_to(RACINE))
            sortie.parent.mkdir()
            with patch.object(historique, "charger_donnees", return_value=(
                    meteo or {}, calendrier or {}, {"FIXTURE-A": "Produit fixture"}, ventes)), \
                    patch.object(historique, "FICHIER_SORTIE", sortie), \
                    contextlib.redirect_stdout(io.StringIO()):
                resultat = historique.analyser()
            publie = json.loads(sortie.read_text(encoding="utf-8"))
            # Le producteur peut ajouter une identité technique à la copie publiée.
            for cle, valeur in resultat.items():
                self.assertEqual(publie[cle], valeur)
            return resultat

    def test_annees_observees_et_quotidien_de_la_derniere_vente(self):
        r = self.analyser_fixture([
            ("2029-03-07", 9), ("2019-03-02", 4), ("2026-09-01", 30),
            ("2029-03-07", 3), ("2029-03-02", 6)])
        self.assertEqual(r["annee_reference"], 2029)
        self.assertEqual(r["date_reference"], "2029-03-07")
        self.assertEqual(r["periode"]["date_debut"], "2019-03-02")
        self.assertEqual(r["periode"]["date_fin"], "2029-03-07")
        self.assertEqual(set(r["annees"]), {"2019", "2026", "2029"})
        p = r["articles"]["FIXTURE-A"]
        self.assertEqual(p["annee_reference"], 2029)
        self.assertEqual(p["ventes_quotidiennes"], {"2029-03-02": 6, "2029-03-07": 12})
        self.assertNotIn("ventes_quotidiennes_2026", p)
        self.assertEqual(set(p["historique_mensuel_par_annee"]), {"2019", "2026", "2029"})
        self.assertEqual(set(p["ventes_par_mois"]["3"]["annees"]), {"2019", "2026", "2029"})
        self.assertEqual(p["volume_total_periode"], 52)
        self.assertEqual(p["volume_total_2ans_demi"], p["volume_total_periode"])
        self.assertEqual(p["saisonnalite"]["mois_actuel"], 3)
        self.assertEqual(p["saisonnalite"]["mois_suivant"], 4)

    def test_semaine_iso_53_et_debut_annee_rattache_annee_iso_precedente(self):
        r = self.analyser_fixture([
            ("2020-12-28", 7), ("2020-12-31", 13),
            ("2021-01-01", 5), ("2021-01-04", 11)])
        semaines = {s["semaine_iso"]: s for s in r["semaines"]}
        self.assertEqual(set(semaines), {1, 53})
        self.assertEqual(semaines[53]["total_unites"], 25)
        self.assertEqual(semaines[53]["par_annee"]["2020"]["jours"], 3)
        self.assertIsNone(semaines[53]["par_annee"]["2021"])
        self.assertEqual(semaines[1]["par_annee"]["2021"]["total_unites"], 11)
        hebdo = r["articles"]["FIXTURE-A"]["courbes_hebdo"]
        self.assertEqual(len(hebdo["moyenne"]), 53)
        self.assertEqual(hebdo["2020"][52], 8.33)
        self.assertEqual(hebdo["2021"][0], 11)
        self.assertIsNone(hebdo["2021"][52])
        self.assertIsNone(hebdo["moyenne"][20])
        # Le quotidien reste civil : le 1er janvier appartient au quotidien 2021.
        self.assertEqual(r["articles"]["FIXTURE-A"]["ventes_quotidiennes"],
                         {"2021-01-01": 5, "2021-01-04": 11})

    def test_annee_iso_absente_des_annees_civiles_reste_visible(self):
        r = self.analyser_fixture([("2021-01-01", 7)])
        self.assertEqual(set(r["annees"]), {"2021"})
        self.assertEqual(r["annees_semaines_iso"], [2020])
        self.assertEqual(r["articles"]["FIXTURE-A"]["courbes_hebdo"]["2020"][52], 7)

    def test_transition_decembre_janvier_referencee_sans_prevision_inventee(self):
        r = self.analyser_fixture([("2027-01-10", 14), ("2027-12-15", 10)])
        s = r["articles"]["FIXTURE-A"]["saisonnalite"]
        self.assertEqual((s["mois_actuel"], s["mois_suivant"]), (12, 1))
        self.assertEqual(s["annee_mois_suivant"], 2028)
        self.assertEqual(s["evolution_pct"], 40)
        self.assertIn("Décembre", s["diagnostic"])
        self.assertIn("Janvier", s["diagnostic"])
        self.assertIn("sans prévision", s["diagnostic"])
        self.assertNotIn("septembre", s["diagnostic"].lower())
        focus = r["focus_mois_reference"]
        self.assertEqual(focus["mois_numero"], 12)
        self.assertEqual(focus["moyenne_quotidienne"], 10)
        self.assertIsNone(focus["ecart_jours_chauds_pct"])
        self.assertNotIn("-11", focus["explication_metier"])
        self.assertNotIn("focus_septembre_automne", r)

    def test_mois_absent_ne_devient_pas_baisse_de_cent_pourcent(self):
        r = self.analyser_fixture([("2030-06-02", 12)])
        s = r["articles"]["FIXTURE-A"]["saisonnalite"]
        self.assertEqual((s["mois_actuel"], s["mois_suivant"]), (6, 7))
        self.assertIsNone(s["evolution_pct"])
        self.assertIsNone(s["moyenne_mois_suivant"])
        self.assertEqual(s["tendance"], "donnees_insuffisantes")

    def test_fetes_hebdomadaires_proviennent_du_calendrier_date(self):
        r = self.analyser_fixture([("2027-05-03", 12)], calendrier={
            "feries": {"2027-05-03": "Fête fixture"}, "vacances": []})
        self.assertEqual(r["semaines"][0]["evenement_cle"], "2027-05-03 : Fête fixture")

    def test_periode_vide_ne_prend_pas_la_date_du_pc(self):
        r = self.analyser_fixture([])
        self.assertIsNone(r["annee_reference"])
        self.assertIsNone(r["date_reference"])
        self.assertEqual(r["articles"], {})
        self.assertEqual(r["annees"], {})
        self.assertEqual(r["semaines"], [])
        self.assertIsNone(r["focus_mois_reference"]["mois_numero"])
        self.assertEqual(r["periode"]["total_jours_avec_ventes"], 0)

    def test_sections_et_totaux_avec_contextes_attestes_en_fixture(self):
        lignes = [("2032-12-24", 4), ("2032-12-25", 6), ("2032-12-26", 8)]
        r = self.analyser_fixture(lignes, calendrier={
            "feries": {"2032-12-25": "Noël fixture"},
            "vacances": [{"debut": "2032-12-20", "fin": "2033-01-02", "nom": "Vacances de Noël"}]},
            meteo={"2032-12-24": [31, 0], "2032-12-25": [5, 7], "2032-12-26": [20, 0]})
        for cle in ("periode", "annees", "mois", "semaines", "jours_semaine",
                    "meteo", "vacances", "feries_et_veilles", "articles"):
            self.assertIn(cle, r)
        self.assertEqual(r["periode"]["total_unites_vendues"], 18)
        self.assertEqual(r["periode"]["total_lignes_faits"], 3)
        self.assertEqual(r["periode"]["total_jours_avec_ventes"], 3)
        self.assertEqual([m["mois_numero"] for m in r["mois"]], list(range(1, 13)))
        self.assertEqual(r["mois"][11]["total_unites"], 18)
        self.assertEqual(r["annees"]["2032"]["total_unites_vendues"], 18)
        self.assertEqual(sum(j["total_unites"] for j in r["jours_semaine"]), 18)
        self.assertEqual(sum(s["total_unites"] for s in r["semaines"]), 18)
        meteo = {m["code"]: m for m in r["meteo"]}
        self.assertEqual(meteo["canicule_sup_30"]["jours_observes"], 1)
        self.assertEqual(meteo["froid_inf_10"]["moyenne_quotidienne"], 6)
        self.assertEqual(meteo["pluie_5mm"]["jours_observes"], 1)
        self.assertEqual(r["vacances"][0]["periode"], "Vacances de Noël")
        self.assertEqual(r["vacances"][0]["jours_observes"], 3)
        self.assertEqual(r["vacances"][0]["moyenne_quotidienne"], 6)


if __name__ == "__main__":
    unittest.main()
