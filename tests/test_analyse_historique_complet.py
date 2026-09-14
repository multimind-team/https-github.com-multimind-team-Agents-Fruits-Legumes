"""
tests/test_analyse_historique_complet.py - Validation de l'analyse multidimensionnelle 2.5 ans.
"""
import json
from pathlib import Path
import unittest

RACINE = Path(__file__).resolve().parent.parent
FICHIER_ANALYSE = RACINE / "donnees" / "analyse-ventes-annuelle-saisonniere.json"


class TestAnalyseHistoriqueComplet(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if not FICHIER_ANALYSE.exists():
            import sys
            sys.path.insert(0, str(RACINE / "moteur"))
            import importlib
            mod = importlib.import_module("analyser-historique-complet")
            mod.analyser()
        cls.data = json.loads(FICHIER_ANALYSE.read_text(encoding="utf-8"))

    def test_presence_sections_principales(self):
        attendu = ["periode", "annees", "mois", "semaines", "jours_semaine", "meteo", "vacances", "feries_et_veilles", "articles"]
        for cle in attendu:
            self.assertIn(cle, self.data, f"Clé manquante dans l'analyse : {cle}")

    def test_couverture_globale(self):
        periode = self.data["periode"]
        self.assertGreater(periode["total_unites_vendues"], 1_500_000)
        self.assertGreater(periode["total_lignes_faits"], 130_000)
        self.assertGreater(periode["total_jours_ouverts"], 800)
        self.assertGreater(periode["total_articles_analyses"], 500)

    def test_annees_presentes(self):
        annees = self.data["annees"]
        self.assertIn("2024", annees)
        self.assertIn("2025", annees)
        self.assertIn("2026", annees)
        self.assertGreater(annees["2025"]["total_unites_vendues"], 700_000)

    def test_douze_mois(self):
        mois = self.data["mois"]
        self.assertEqual(len(mois), 12)
        numeros = [m["mois_numero"] for m in mois]
        self.assertEqual(numeros, list(range(1, 13)))
        for m in mois:
            self.assertGreater(m["total_unites"], 50_000)
            self.assertIn("famille_dominante", m)
            self.assertIn("top_articles", m)

    def test_semaines_iso(self):
        semaines = self.data["semaines"]
        self.assertGreaterEqual(len(semaines), 52)
        sem_dict = {s["semaine_iso"]: s for s in semaines}
        # S18 (ponts de mai) doit être un des pics
        self.assertIn(18, sem_dict)
        self.assertGreater(sem_dict[18]["moyenne_quotidienne"], 2500)

    def test_rythme_jours_semaine(self):
        js = self.data["jours_semaine"]
        self.assertEqual(len(js), 7)
        js_dict = {j["nom"]: j for j in js}
        # Samedi doit dépasser le lundi
        self.assertGreater(js_dict["Samedi"]["moyenne_quotidienne"], js_dict["Lundi"]["moyenne_quotidienne"])
        self.assertGreater(js_dict["Samedi"]["part_semaine_pct"], 18.0)

    def test_meteo_tranches(self):
        meteo = self.data["meteo"]
        codes = [m["code"] for m in meteo]
        self.assertIn("canicule_sup_30", codes)
        self.assertIn("froid_inf_10", codes)
        self.assertIn("pluie_5mm", codes)

    def test_vacances_zone_c(self):
        vac = self.data["vacances"]
        periodes = [v["periode"] for v in vac]
        self.assertIn("Vacances d'Été", periodes)
        self.assertIn("Vacances de la Toussaint", periodes)
        self.assertIn("Vacances de Noël", periodes)

    def test_profils_tous_articles_inclus_hors_cadencier(self):
        articles = self.data["articles"]
        self.assertGreaterEqual(len(articles), 550)
        # Chaque article a son profil complet
        for art_id, art in list(articles.items())[:20]:
            self.assertIn("libelle", art)
            self.assertIn("volume_total_2ans_demi", art)
            self.assertIn("ventes_par_mois", art)
            self.assertIn("ratios_sensibilite", art)

    def test_saisonnalite_et_historique_annuel_article(self):
        articles = self.data["articles"]
        # Vérification sur la banane vrac
        self.assertIn("0000087004011", articles)
        banane = articles["0000087004011"]
        self.assertIn("saisonnalite", banane)
        sais = banane["saisonnalite"]
        self.assertEqual(sais["mois_actuel"], 9)
        self.assertEqual(sais["mois_suivant"], 10)
        self.assertIn("badge", sais)
        self.assertIn("diagnostic", sais)
        self.assertIn("historique_mensuel_par_annee", banane)
        self.assertIn("2024", banane["historique_mensuel_par_annee"])
        self.assertIn("2025", banane["historique_mensuel_par_annee"])
        self.assertIn("2026", banane["historique_mensuel_par_annee"])
        # Vérification détail par mois avec années
        m9 = banane["ventes_par_mois"]["9"]
        self.assertIn("annees", m9)
        self.assertIsNotNone(m9["annees"].get("2024"))

    def test_ventes_quotidiennes_2026(self):
        articles = self.data["articles"]
        self.assertIn("0000087004011", articles)
        banane = articles["0000087004011"]
        self.assertIn("ventes_quotidiennes_2026", banane)
        v26 = banane["ventes_quotidiennes_2026"]
        self.assertGreater(len(v26), 200)
        # Vérification d'une date spécifique connue (ex: 2026-09-07)
        self.assertIn("2026-09-07", v26)
        self.assertGreater(v26["2026-09-07"], 0)


if __name__ == "__main__":
    unittest.main()
