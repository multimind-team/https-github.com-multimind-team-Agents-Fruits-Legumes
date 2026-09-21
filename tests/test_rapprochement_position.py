"""Rapprochement en lecture seule : fixtures, sans données ni serveur réels."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "moteur"))
import pilotage
import rapprochement_position as rapprochement


class RapprochementPositionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="rapprochement-fixture-")
        self.addCleanup(self.temp.cleanup)
        self.d = Path(self.temp.name) / "donnees"
        (self.d / "faits").mkdir(parents=True)
        self.etat = {"calcule_jusquau": "2030-04-10", "reconstruit_le": "2030-04-11T06:00:00",
                     "articles": {"A": {"position": 13, "mesuree_le": "2030-04-10"}}}

    def fait(self, identifiant, type_fait, quantite, jour="2030-04-10", article="A", **champs):
        return {"id": identifiant, "type": type_fait, "article": article, "quantite": quantite,
                "date_source": jour, "unite": "kg", **champs}

    def base(self, identifiant="base", quantite=20, heure="07:00:00", jour="2030-04-10", **champs):
        return self.fait(identifiant, "comptage", quantite, jour,
                         horodatage=f"{jour}T{heure}", origine_mesure="ecran-comptage", **champs)

    def ecrire(self, lignes):
        (self.d / "faits/2030.jsonl").write_text("\n".join(json.dumps(l) for l in lignes)+"\n", encoding="utf-8")

    def construire(self, **options):
        args = {"donnees": self.d, "article_stock": "A", "groupes": {}, "etat": self.etat,
                "unite": "kg", "conditionnement": 10, "aujourd_hui": "2030-04-11"}
        args.update(options)
        return rapprochement.construire(**args)

    def codes(self, resultat):
        return {a["code"] for a in resultat["avertissements"]}

    def test_matin_soir_avant_livraison_reproduisent_flux_moteur(self):
        for heure, phase, attendu, recus, sorties in [
            ("05:00:00", "avant-livraison", 43, 30, 7),
            ("07:00:00", "matin", 13, 0, 7),
            ("18:00:00", "soir", 20, 0, 0),
        ]:
            with self.subTest(phase=phase):
                self.ecrire([self.base(heure=heure), self.fait("l", "livraison", 30),
                             self.fait("v", "vente", 4), self.fait("c", "casse", 1), self.fait("d", "don", 2)])
                r = self.construire()
                self.assertEqual(r["base"]["moment"], phase)
                self.assertEqual(r["position_recalculee"], attendu)
                self.assertEqual(r["totaux"]["livraisons"], recus)
                self.assertEqual(sum(r["totaux"][f] for f in ("ventes", "casse", "dons")), sorties)
                self.assertEqual(r["coherence_physique"], "non_etablie")
                self.assertIn("17 h", " ".join(r["limites"]))

    def test_heures_mail_explicites_source_physique_et_faits_jour_suivant(self):
        (self.d / "receptions-courrier.json").write_text('{"2030-04-09":"09:00:00"}', encoding="utf-8")
        self.ecrire([self.base(jour="2030-04-09", heure="20:00:00", source={"saisi_le": "2030-04-09T08:00:00"}),
                     self.fait("l", "livraison", 10, "2030-04-09"),
                     self.fait("v", "vente", 4), self.fait("c", "casse", 1), self.fait("d", "don", 2)])
        r = self.construire()
        self.assertEqual(r["base"]["heure"], "08:00:00")
        self.assertEqual(r["base"]["moment"], "avant-livraison")
        self.assertEqual(r["position_recalculee"], 23)
        self.assertEqual([j["position_fin"] for j in r["jours"]], [30, 23])
        self.assertEqual(r["jours"][1]["references"]["ventes"], ["v"])

    def test_correction_retenue_garde_date_heure_et_reference_originales(self):
        self.ecrire([self.base(), self.fait("correction", "correction-comptage", 30,
            cible_id="base", horodatage="2030-04-11T19:30:00", origine_mesure="ecran-comptage-correction"),
            self.fait("l", "livraison", 10), self.fait("v", "vente", 4)])
        r = self.construire()
        self.assertEqual(r["base"]["quantite"], 30)
        self.assertEqual(r["base"]["date"], "2030-04-10")
        self.assertEqual(r["base"]["heure"], "07:00:00")
        self.assertEqual(r["base"]["reference_correction"], "correction")
        self.assertEqual(r["base"]["nature"], "terrain_declare")
        self.assertEqual(r["position_recalculee"], 26)

    def test_correction_ancienne_ne_devient_pas_derniere_base(self):
        self.ecrire([self.base("ancien", 100, jour="2030-04-08"), self.base("recent", 20),
                     self.fait("corr-ancienne", "correction-comptage", 900, "2030-04-08", cible_id="ancien"),
                     self.fait("v", "vente", 4)])
        r = self.construire()
        self.assertEqual(r["base"]["id"], "recent")
        self.assertFalse(r["base"]["corrigee"])
        self.assertEqual(r["position_recalculee"], 16)

    def test_doublon_ignore_et_conflit_refuse(self):
        vente = self.fait("v", "vente", 7)
        self.ecrire([self.base(), vente, {**vente, "source": {"fichier": "C:/prive/ne-pas-publier.xlsx"}}])
        r = self.construire()
        self.assertEqual(r["totaux"]["ventes"], 7)
        self.assertEqual(r["audit_lecture"]["doublons_ignores"], 1)
        self.assertNotIn("prive", json.dumps(r))
        self.ecrire([self.base(), vente, {**vente, "quantite": 8}])
        with self.assertRaisesRegex(ValueError, "conflit"):
            self.construire()

    def test_base_absente_ne_devient_pas_zero_et_dates_flux_restent_visibles(self):
        self.ecrire([self.fait("v", "vente", 7), self.fait("l", "livraison", 10, "2030-04-09")])
        r = self.construire()
        self.assertEqual(r["statut"], "sans_base")
        self.assertIsNone(r["position_recalculee"])
        self.assertIsNone(r["totaux"]["ventes"])
        self.assertEqual(r["jours"], [])
        self.assertEqual(r["dernieres_dates_flux"]["ventes"], "2030-04-10")
        self.assertIn("base_absente", self.codes(r))

    def test_unites_inconnues_incompatibles_et_base_forcee_signalees(self):
        base = {**self.base(), "origine_mesure": "position-forcee"}
        self.ecrire([base, self.fait("v", "vente", 7, unite="inconnue"), self.fait("c", "casse", 1, unite="piece")])
        r = self.construire()
        self.assertEqual(r["position_recalculee"], 12)
        self.assertEqual(r["base"]["nature"], "position_forcee")
        self.assertTrue({"base_forcee", "unites_inconnues", "unites_incompatibles"} <= self.codes(r))
        self.assertEqual(r["coherence_physique"], "non_etablie")

    def test_groupes_partagent_base_et_flux_sans_double_compte(self):
        self.ecrire([self.base(article="C"), self.fait("v-a", "vente", 3), self.fait("v-c", "vente", 4, article="C")])
        r = self.construire(groupes={"C": "A"})
        self.assertEqual(r["position_recalculee"], 13)
        self.assertEqual(r["totaux"]["ventes"], 7)
        self.assertEqual(r["totaux"]["mouvements"], 2)
        self.assertIn("stock_partage", self.codes(r))

    def test_conversion_jus_explicite_et_references_sources(self):
        orange = "0000087004386"
        self.ecrire([self.base(article=orange), self.fait("jus", "vente", 3, article="0000000008112", unite="piece")])
        r = self.construire(article_stock=orange)
        self.assertEqual(r["position_recalculee"], 14)
        self.assertEqual(r["totaux"]["ventes"], 6)
        self.assertEqual(r["conversions"][0]["coefficient"], 2)
        self.assertEqual(r["conversions"][0]["quantite_source"], 3)
        self.assertEqual(r["jours"][0]["references"]["ventes"], ["jus"])
        self.assertIn("conversion_jus", self.codes(r))

    def test_comparaison_publiee_et_bornes_differentes(self):
        self.ecrire([self.base(), self.fait("v", "vente", 7)])
        self.assertEqual(self.construire()["comparaison"]["statut"], "identique")
        self.etat["articles"]["A"]["position"] = 10
        r = self.construire()
        self.assertEqual(r["comparaison"]["statut"], "ecart")
        self.assertEqual(r["comparaison"]["ecart_unites"], 3)
        self.etat["calcule_jusquau"] = "2030-04-09"
        self.assertEqual(self.construire()["comparaison"]["statut"], "bornes_differentes")

    def test_absence_flux_zero_somme_connue_et_futur_non_applique(self):
        self.ecrire([self.base(), self.fait("future", "vente", 999, "2030-04-12")])
        r = self.construire()
        self.assertEqual(r["totaux"]["ventes"], 0)
        self.assertEqual(r["totaux"]["nombres"]["ventes"], 0)
        self.assertIsNone(r["dernieres_dates_flux"]["ventes"])
        self.assertEqual(r["position_recalculee"], 20)
        self.assertIn("faits_futurs", self.codes(r))

    def test_aucune_ecriture_aucun_cli_aucune_mutation_globals(self):
        self.ecrire([self.base(), self.fait("v", "vente", 7)])
        moteur = rapprochement._moteur()
        originaux = (moteur.RACINE, moteur.DOSSIER_FAITS, moteur.FICHIER_RECEPTIONS)
        avant = {str(p.relative_to(self.d)): p.read_bytes() for p in self.d.rglob("*") if p.is_file()}
        with patch.object(moteur, "calculer", side_effect=AssertionError("Lecture implicite interdite")), \
             patch.object(moteur, "main", side_effect=AssertionError("Publication interdite")), \
             patch.object(moteur.regles, "charger", side_effect=AssertionError("Globals interdits")):
            r = self.construire()
        apres = {str(p.relative_to(self.d)): p.read_bytes() for p in self.d.rglob("*") if p.is_file()}
        self.assertEqual(avant, apres)
        self.assertEqual(originaux, (moteur.RACINE, moteur.DOSSIER_FAITS, moteur.FICHIER_RECEPTIONS))
        json.dumps(r, allow_nan=False)

    def test_pilotage_detail_avec_releve_recent_preserve_graphique_14j(self):
        self.ecrire([self.fait("v", "vente", 7), self.base(jour="2030-04-11")])
        (self.d / "proposition.json").write_text(json.dumps({"lignes": [{"itm8": "A", "unite": "kg", "conditionnement": 10}]}), encoding="utf-8")
        (self.d / "etat.json").write_text(json.dumps(self.etat), encoding="utf-8")
        r = pilotage.construire(self.d, article="A", aujourd_hui="2030-04-11")
        detail = r["article"]["rapprochement_position"]
        self.assertEqual(detail["base"]["date"], "2030-04-11")
        self.assertEqual(detail["position_recalculee"], 20)
        self.assertEqual(len(r["article"]["chronologie"]), 14)
        self.assertEqual(r["article"]["chronologie"][-1]["date"], "2030-04-10")
        self.assertTrue(all("rapprochement_position" not in ligne for ligne in r["articles"]))


if __name__ == "__main__":
    unittest.main()
