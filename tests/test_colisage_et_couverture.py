"""Régressions des colis réellement commandés et du stock recompté, sans écritures métier."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime, date

MOTEUR = Path(__file__).resolve().parents[1] / "moteur"
sys.path.insert(0, str(MOTEUR))


def charger(nom):
    spec = importlib.util.spec_from_file_location(nom, MOTEUR / (nom + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERER = charger("generer-proposition")
LISTE = charger("preparer-liste-comptage")
FILET = charger("filet-de-securite")


class DateFigee(datetime):
    @classmethod
    def now(cls):
        return cls(2026, 9, 9, 19, 0)


class ColisageEtCouvertureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.racine = Path(self.temp.name)
        (self.racine / "donnees").mkdir()
        self.references = {
            "ORANGE": {"CODE ITM": "ORANGE", "LIBELLE": "ORANGE DESSERT VRAC", "CONDIT.BASE": 1, "UNITE MESURE": "2 kg"},
            "PDT": {"CODE ITM": "PDT", "LIBELLE": "PDT PRINCESSE AMANDINE 2KG", "CONDIT.BASE": 65, "UNITE MESURE": "2 pièce"},
        }
        self.positions = {c: {"position": 0, "mesuree_le": "2026-09-07", "moment_mesure": "soir"} for c in self.references}
        self.moyennes = {c: {"saison": [8.5] * 366, "tauxPerte": 0} for c in self.references}
        self.agr = {"date_reference": "2026-09-04", "articles": {c: {"totalCA": 1, "derniereDateVente": "2026-09-04"} for c in self.references}}
        self.cadencier = {"date_cadencier": "2026-09-07", "articles": [
            {"article": "ORANGE", "nom": "ORANGE DESSERT VRAC", "rang": 0, "groupe": "fruits", "offres": [{"par_colis": 8, "prix_achat": 1.79}]},
            {"article": "PDT", "nom": "PDT PRINCESSE AMANDINE 2KG", "rang": 1, "groupe": "legumes", "offres": [{"par_colis": 65, "prix_achat": 2}, {"par_colis": 8, "prix_achat": 3.89}]},
        ]}
        self.config = {"overrides": {}}

    def ecrire(self, nom, contenu):
        (self.racine / "donnees" / (nom + ".json")).write_text(json.dumps(contenu), encoding="utf-8")

    def generer(self):
        self.ecrire("cadencier-du-jour", self.cadencier)
        self.ecrire("etat", {"calcule_jusquau": "2026-09-09", "date_base_commande": "2026-09-08", "articles": self.positions})
        with contextlib.ExitStack() as pile:
            for module in (GENERER, LISTE):
                pile.enter_context(patch.object(module, "RACINE", self.racine))
            pile.enter_context(patch.object(GENERER, "datetime", DateFigee))
            pile.enter_context(patch.object(GENERER.agregats, "charger", return_value=self.agr))
            pile.enter_context(patch.object(GENERER.regles, "charger", return_value=self.config))
            pile.enter_context(patch.object(GENERER.catalogue, "articles", return_value=self.references))
            pile.enter_context(patch.object(GENERER.ferie, "dates_fermees", return_value=set()))
            pile.enter_context(patch.object(GENERER.ferie, "facteur", return_value=1))
            pile.enter_context(patch.object(GENERER.calendrier, "charger", return_value={"feries": {}}))
            pile.enter_context(patch.object(GENERER, "meteo_prevue", return_value={}))
            pile.enter_context(patch.object(GENERER.calc, "construire_moyennes", return_value=self.moyennes))
            pile.enter_context(patch.object(LISTE, "ventes_estimees_des_jours_manquants", return_value=({}, [])))
            pile.enter_context(contextlib.redirect_stdout(io.StringIO()))
            GENERER.main()
            LISTE.main()
        return json.loads((self.racine / "donnees/proposition.json").read_text(encoding="utf-8"))

    def test_orange_et_caissette_offre_prix_et_detail_sont_coherents(self):
        p = self.generer()
        orange, pdt = p["lignes"]
        self.assertEqual(orange["conditionnement"], 8)
        self.assertEqual(orange["propose_colis"], 3)
        self.assertEqual(pdt["conditionnement"], 8)
        self.assertEqual(pdt["prix_achat"], 3.89)
        self.assertEqual(pdt["montant_achat"], 93.36)
        self.assertEqual(orange["demande"], 17)
        self.assertEqual(orange["position_unites"], 0)
        self.assertEqual(orange["source_conditionnement"], "cadencier")

    def test_liste_comptage_utilise_le_meme_colis_que_la_commande(self):
        self.positions["ORANGE"]["position"] = 16
        self.generer()
        articles = json.loads((self.racine / "donnees/articles.json").read_text(encoding="utf-8"))["articles"]
        orange = next(a for a in articles if a["itm8"] == "ORANGE")
        self.assertEqual(orange["conditionnement"], 8)
        self.assertEqual(orange["derniere_position_colis"], 2)

    def test_decision_colisage_appliquee_aussi_aux_articles_non_rapproches(self):
        for code in (None, "CODE_SANS_HISTORIQUE"):
            with self.subTest(code=code):
                self.cadencier["articles"] = [{"article": code, "nom": "ARTICLE TEST", "rang": 1,
                    "groupe": "fruits", "offres": [{"par_colis": 6, "prix_achat": 2}]}]
                identifiant = code or "nom:ARTICLE TEST"
                self.config["overrides"][identifiant] = {"conditionnement": "8"}
                ligne = self.generer()["lignes"][0]
                self.assertEqual(ligne["conditionnement"], 8)
                self.assertEqual(ligne["source_conditionnement"], "decision")
                self.assertEqual(ligne["propose_colis"], 0)
                self.assertIsNone(ligne["position_colis"])
                self.assertTrue(any("prix non apparié" in a for a in ligne["avertissements_conditionnement"]))

    def test_masques_exclus_aussi_du_nombre_articles_a_commander(self):
        self.config["overrides"]["PDT"] = {"masque": True}
        p = self.generer()
        self.assertEqual(p["totaux"]["articles_a_commander"], 1)
        self.assertEqual(p["totaux"]["montant_achat"], p["lignes"][0]["montant_achat"])

    def test_couverture_distingue_comptages_et_statistiques_et_inconnus(self):
        self.cadencier["articles"].append({"article": None, "nom": "INCONNU", "rang": 2, "groupe": "legumes", "offres": [{"par_colis": 6, "prix_achat": 2}]})
        p = self.generer()
        self.assertEqual(p["couverture_stock"]["dernier_comptage_le"], "2026-09-07")
        self.assertEqual(p["couverture_stock"]["articles_dernier_comptage"], 2)
        self.assertEqual(p["couverture_stock"]["articles_sans_position_connus"], 0)
        self.assertEqual(p["couverture_stock"]["articles_sans_mapping"], 1)
        self.assertEqual(p["couverture_stock"]["statistiques_ventes_jusquau"], "2026-09-04")
        class JourFige(date):
            @classmethod
            def today(cls):
                return cls(2026, 9, 9)
        with patch.object(FILET, "PROPOSITION", self.racine / "donnees/proposition.json"), patch.object(FILET, "date", JourFige), patch.object(FILET, "jour_de_commande", return_value="2026-09-10"):
            etat, message, _ = FILET.etat_proposition()
        self.assertEqual(etat, "donnees-en-retard")
        self.assertIn("fichier des ventes", message)
        self.assertIn("intégration", message)
        self.assertNotIn("Statistiques de ventes", message)
        self.assertNotIn("n'est vérifiée que jusqu'au", message)

    def test_un_export_recent_ne_comble_pas_les_journees_absentes(self):
        self.agr["date_reference"] = "2026-09-08"
        self.agr["jours_ventes_integres"] = ["2026-09-03", "2026-09-04", "2026-09-08"]
        self.positions["PDT"]["mesuree_le"] = "2026-09-02"
        p = self.generer()
        self.assertEqual(p["lignes"][0]["sorties_couvertes_jusquau"], "2026-09-08")
        self.assertEqual(p["lignes"][1]["sorties_couvertes_jusquau"], "2026-09-04")
        self.assertEqual(p["date_stock_verifiee"], "2026-09-04")
        self.assertEqual(p["couverture_stock"]["articles_sorties_a_verifier"], 1)
        self.assertEqual(p["couverture_stock"]["sorties_attendues_jusquau"], "2026-09-08")


if __name__ == "__main__":
    unittest.main()
