"""
Tests unitaires : analyseur de fiabilité prévisions vs ventes réelles et page PC fiabilite.html.
"""
import importlib.util
import json
from pathlib import Path
import unittest

RACINE = Path(__file__).resolve().parent.parent
MOTEUR = RACINE / "moteur"
DONNEES = RACINE / "donnees"
APP = RACINE / "app"

def _charger_module(nom_module, chemin):
    spec = importlib.util.spec_from_file_location(nom_module, chemin)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestAnalyserFiabilite(unittest.TestCase):

    def test_serveur_allowlists_contiennent_fiabilite(self):
        serveur = _charger_module("serveur", MOTEUR / "serveur.py")
        self.assertIn("/app/fiabilite.html", serveur.APP_PUBLIQUE)
        self.assertIn("fiabilite.json", serveur.DONNEES_PUBLIQUES)

    def test_aucune_navigation_mobile_ne_pointe_vers_fiabilite(self):
        for nom in ("index.html", "commander.html", "compter.html", "maintenance.html"):
            chemin = APP / nom
            if chemin.is_file():
                contenu = chemin.read_text(encoding="utf-8")
                self.assertNotIn("fiabilite.html", contenu, f"{nom} ne doit pas contenir de bouton/lien vers fiabilite.html")

    def test_qualifier_anomalie_seuils_metier(self):
        af = _charger_module("analyser_fiabilite", MOTEUR / "analyser-fiabilite.py")

        # Sur-estimation forte
        statut, gravite, _ = af.qualifier_anomalie(reel=100.0, prevu=140.0, ecart_colis=4.0)
        self.assertEqual(statut, "sur_estimation_forte")
        self.assertEqual(gravite, "critique")

        # Sous-estimation forte
        statut, gravite, _ = af.qualifier_anomalie(reel=100.0, prevu=60.0, ecart_colis=-4.0)
        self.assertEqual(statut, "sous_estimation_forte")
        self.assertEqual(gravite, "critique")

        # Équilibré / conforme
        statut, gravite, _ = af.qualifier_anomalie(reel=100.0, prevu=102.0, ecart_colis=0.2)
        self.assertEqual(statut, "equilibre")
        self.assertEqual(gravite, "conforme")

        # Sur-estimation modérée
        statut, gravite, _ = af.qualifier_anomalie(reel=100.0, prevu=115.0, ecart_colis=1.0)
        self.assertEqual(statut, "sur_estimation_moderee")
        self.assertEqual(gravite, "vigilance")

        # Sous-estimation modérée
        statut, gravite, _ = af.qualifier_anomalie(reel=100.0, prevu=85.0, ecart_colis=-1.0)
        self.assertEqual(statut, "sous_estimation_moderee")
        self.assertEqual(gravite, "vigilance")

    def test_structure_fiabilite_json(self):
        fichier = DONNEES / "fiabilite.json"
        self.assertTrue(fichier.is_file(), "donnees/fiabilite.json doit exister")
        donnees = json.loads(fichier.read_text(encoding="utf-8"))

        self.assertIn("synthese", donnees)
        self.assertIn("articles", donnees)
        s = donnees["synthese"]
        self.assertGreater(s["articles_evalues"], 50)
        self.assertGreater(s["total_vendu_unites"], 1000)
        self.assertIn("kpis_horizons", s)
        self.assertIn("trois_jours", s["kpis_horizons"])
        self.assertIn("sept_jours", s["kpis_horizons"])
        self.assertIn("trente_jours", s["kpis_horizons"])
        self.assertIn("annuel", s["kpis_horizons"])
        self.assertIn("historique_recent_14j", s)
        self.assertEqual(len(s["historique_recent_14j"]), 14)

        # Vérifier structure d'un article
        art = donnees["articles"][0]
        self.assertIn("itm8", art)
        self.assertIn("libelle", art)
        self.assertIn("famille", art)
        self.assertIn("colisage", art)
        self.assertIn("stock_colis", art)
        self.assertIn("livraisons_14j_colis", art)
        self.assertIn("annuel", art)
        self.assertIn("livraison_unites", art["annuel"])
        self.assertIn("livraison_colis", art["annuel"])
        self.assertIn("trente_jours", art)
        self.assertIn("sept_jours", art)
        self.assertIn("trois_jours", art)
        self.assertIn("serie_recente_14j", art)
        self.assertEqual(len(art["serie_recente_14j"]), 14)
        self.assertIn("livraison", art["serie_recente_14j"][0])
        self.assertIn("livraison", s["historique_recent_14j"][0])
        self.assertIn("alertes_recentes", art)
        self.assertIn("diagnostic", art)
        self.assertIn("detail_jours", art)
        self.assertEqual(len(art["detail_jours"]), 7)

        # Vérifier que le diagnostic contient bien les causes racines
        diag = art["diagnostic"]
        self.assertIn("code_cause", diag)
        self.assertIn("badge_cause", diag)
        self.assertIn("synthese_explication", diag)
        self.assertIn("recommandation", diag)
        self.assertIn("causes_detaillees", diag)
        self.assertIn("commande_du_jour", diag)
        self.assertIn("rapport_agent_tendances", diag)

        # Cas spécifique : Pitaya Rose Vrac (0000087003040)
        pitayas = [a for a in donnees["articles"] if a["itm8"] == "0000087003040"]
        self.assertTrue(len(pitayas) > 0, "Pitaya Rose Vrac doit être présent dans l'analyse")
        p = pitayas[0]
        p_diag = p["diagnostic"]
        self.assertEqual(p_diag["code_cause"], "saisonnalite")
        self.assertIn("festif", p_diag["badge_cause"].lower())
        self.assertIn("décembre", p_diag["synthese_explication"].lower())
        self.assertEqual(p_diag["commande_du_jour"]["propose_colis"], 0.0)
        self.assertIn("rapport_agent_tendances", p_diag)
        rapport = p_diag["rapport_agent_tendances"]
        self.assertIn("Agent Tendances", rapport)
        self.assertIn("0000087003040", rapport)
        self.assertIn("PITAYA ROSE VRAC", rapport)

    def test_page_fiabilite_html_structure(self):
        html = (APP / "fiabilite.html").read_text(encoding="utf-8")
        self.assertIn("Fiabilité des Prévisions vs Ventes Réelles", html)
        self.assertIn("kpi-biais", html)
        self.assertIn("kpi-casse", html)
        self.assertIn("kpi-rupture", html)
        self.assertIn("recherche-article", html)
        self.assertIn("donnees/fiabilite.json", html)
        self.assertIn("modale-liste-causes", html)
        self.assertIn("modale-recommandation", html)
        self.assertIn("facteur-colisage", html)
        self.assertIn("facteur-stock", html)
        self.assertIn("facteur-livraison", html)
        self.assertIn("modale-bloc-agent", html)
        self.assertIn("modale-texte-agent", html)

        # Nouveaux horizons et graphiques
        self.assertIn("btn-periode-3j", html)
        self.assertIn("btn-periode-7j", html)
        self.assertIn("btn-periode-30j", html)
        self.assertIn("btn-periode-annuel", html)
        self.assertIn("panneau-graphiques", html)
        self.assertIn("conteneur-svg-14j", html)
        self.assertIn("conteneur-causes-jauges", html)
        self.assertIn("modale-svg-article", html)

        # Affichage et modification interactive du stock
        self.assertIn("Stock (colis)", html)
        self.assertIn("input-stock-modale", html)
        self.assertIn("cell-stock-container", html)
        self.assertIn("activerEditionStock", html)
        self.assertIn("sauvegarderComptage", html)
        self.assertIn("/api/comptages", html)
        self.assertIn("alerte-stock-graphique", html)
        self.assertIn("toast-notification", html)

        # Affichage des livraisons réelles
        self.assertIn("Livraisons", html)
        self.assertIn("pastille-legende violet", html)
        self.assertIn("badge-ecoulement", html)


if __name__ == "__main__":
    unittest.main()
