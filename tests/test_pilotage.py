"""Contrat du cockpit sur fixtures temporaires ; aucune donnée métier réelle."""
from datetime import date
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "moteur"))
import pilotage


class PilotageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="pilotage-fixture-")
        self.addCleanup(self.temp.cleanup)
        self.d = Path(self.temp.name) / "donnees"
        (self.d / "faits").mkdir(parents=True)
        self.ecrire("agregats.json", {"articles": {
            "A": {"libelle": "Pommes", "conditionnement": 10},
            "B": {"libelle": "Salades", "conditionnement": 3}}})
        self.ecrire("proposition.json", {"date_commande": "2030-04-11", "lignes": [
            {"itm8": "A", "libelle": "Pommes", "conditionnement": 10, "unite": "kg", "propose_colis": 2},
            {"itm8": "B", "libelle": "Salades", "conditionnement": 3, "unite": "pièce", "propose_colis": 0}]})
        self.ecrire("etat.json", {"articles": {"A": {"position": 20, "mesuree_le": "2030-04-10"}}})
        self.ecrire("catalogue.json", {"articles": {}})
        self.ecrire("fiabilite.json", {"articles": [{"itm8": "A", "famille": "Pommes & Agrumes",
            "serie_recente_14j": [{"date": "2030-04-10", "reel": 999, "prevu": 777}],
            "annuel": {"prevu_unites": 888, "ecart_pct": 200}}]})
        self.ecrire("analyse-ventes-livraisons.json", {})
        self.ecrire("articles.json", {"articles": [{"itm8": "A"}]})

    def ecrire(self, nom, contenu):
        (self.d / nom).write_text(json.dumps(contenu, ensure_ascii=False), encoding="utf-8")

    def faits(self, lignes):
        (self.d / "faits/2030.jsonl").write_text("\n".join(json.dumps(x) for x in lignes)+"\n", encoding="utf-8")

    def fait(self, identifiant, code, flux, quantite, jour="2030-04-10", **autres):
        return {"id": identifiant, "article": code, "type": flux, "quantite": quantite,
                "date_source": jour, **autres}

    def construire(self, **options):
        return pilotage.construire(self.d, aujourd_hui="2030-04-11", **options)

    def test_unites_distinctes_converties_en_colis_et_prevision_absente(self):
        self.faits([self.fait("a", "A", "vente", 50), self.fait("b", "B", "vente", 6),
                    self.fait("c", "A", "livraison", 20)])
        r = self.construire(article="A")
        self.assertEqual(r["kpis"]["ventes_colis"], 7)
        self.assertEqual(r["kpis"]["livraisons_colis"], 2)
        self.assertIsNone(r["kpis"]["previsions_colis"])
        self.assertIsNone(r["kpis"]["conformite_pct"])
        self.assertTrue(all(p["previsions"] is None for p in r["chronologie"]))
        self.assertEqual(r["article"]["chronologie"][-1]["ventes"], 50)
        self.assertEqual(r["article"]["famille"], "Pommes & Agrumes")
        self.assertIn("rétrospectif", r["article"]["previsions_motif"])

    def test_zero_atteste_distinct_d_absence_article_et_absence_rayon(self):
        self.faits([self.fait("a", "A", "vente", 0), self.fait("b", "B", "vente", 3, "2030-04-09")])
        r = self.construire(article="A")
        serie = r["article"]["chronologie"]
        self.assertEqual(serie[-1]["ventes"], 0)
        self.assertTrue(serie[-1]["sans_vente_observee"])
        self.assertIsNone(serie[-2]["ventes"])
        self.assertFalse(serie[-2]["sans_vente_observee"])
        self.assertIsNone(serie[-3]["ventes"])
        self.assertEqual(r["article"]["jours_ventes_observes"], 1)
        self.assertEqual(r["article"]["profil_hebdomadaire"][date(2030, 4, 10).weekday()]["ventes_moyennes"], 0)

    def test_reception_date_effet_et_comptage_ne_rajeunissent_pas_ventes(self):
        self.faits([self.fait("a", "A", "vente", 10, "2030-04-08"),
                    self.fait("b", "A", "livraison", 20, "2030-04-06", date_effet="2030-04-08"),
                    self.fait("c", "A", "comptage", 30, "2030-04-11"),
                    self.fait("d", "A", "livraison", 30, "2030-04-11")])
        r = self.construire(horizon="3", article="A")
        self.assertEqual(r["periode"]["fin"], "2030-04-08")
        self.assertEqual(r["couverture"]["anciennete_jours"], 3)
        self.assertEqual(r["couverture"]["derniere_livraison"], "2030-04-11")
        self.assertEqual(r["article"]["livraisons_unites"], 20)
        self.assertEqual(r["article"]["chronologie"][-1]["livraisons"], 20)

    def test_annuel_dynamique_annee_bissextile_et_dates_reelles(self):
        self.faits([self.fait("a", "A", "vente", 10, "2028-01-01"),
                    self.fait("b", "A", "vente", 20, "2028-02-29"),
                    self.fait("c", "A", "vente", 40, "2027-12-31")])
        r = pilotage.construire(self.d, horizon="annee", aujourd_hui="2028-03-01", article="A")
        self.assertEqual(r["periode"], {"horizon": "annee", "debut": "2028-01-01", "fin": "2028-02-29", "jours": 60, "annee": 2028})
        self.assertEqual(r["article"]["ventes_unites"], 30)

    def test_lecture_ne_cree_ni_modifie_fichier_et_manquants_explicites(self):
        self.faits([self.fait("a", "A", "vente", 2)])
        (self.d / "analyse-ventes-livraisons.json").unlink()
        avant = {str(p.relative_to(self.d)): p.read_bytes() for p in self.d.rglob("*") if p.is_file()}
        r = self.construire()
        apres = {str(p.relative_to(self.d)): p.read_bytes() for p in self.d.rglob("*") if p.is_file()}
        self.assertEqual(avant, apres)
        self.assertIn("analyse-ventes-livraisons.json", r["couverture"]["fichiers_absents"])

    def test_doublon_unique_et_conflit_refuse(self):
        fait = self.fait("a", "A", "vente", 20)
        self.faits([fait, {**fait, "source": {"nom": "copie"}}])
        r = self.construire()
        self.assertEqual(r["kpis"]["ventes_colis"], 2)
        self.assertEqual(r["couverture"]["audit_faits"]["doublons_ignores"], 1)
        self.faits([fait, {**fait, "quantite": 21}])
        with self.assertRaisesRegex(ValueError, "conflit"):
            self.construire()

    def test_offres_regroupees_ne_doublent_pas_flux(self):
        self.ecrire("proposition.json", {"lignes": [
            {"itm8": "A", "conditionnement": 10, "unite": "kg"},
            {"itm8": "C", "article_stock": "A", "conditionnement": 5, "unite": "kg",
             "commande_groupe_portee_par": "A", "avertissement_contexte": "Offre secondaire"}]})
        self.faits([self.fait("a", "A", "vente", 20), self.fait("c", "C", "vente", 10)])
        r = self.construire(article="C")
        self.assertEqual(r["kpis"]["ventes_colis"], 3)
        self.assertEqual(r["article"]["ventes_colis"], 6)
        self.assertEqual(r["article"]["commande_groupe_portee_par"], "A")

    def test_annulation_fusion_et_pcb_personnalise(self):
        decisions = [
            {"id": "fusion", "type": "fusion", "principal": "A", "membres": ["B"]},
            {"id": "annulation", "type": "annulation", "annule": "fusion"},
            {"id": "pcb", "type": "conditionnement", "article": "A", "valeur": 10, "motif": "Colis pesé"}]
        (self.d / "decisions.jsonl").write_text("\n".join(json.dumps(d) for d in decisions), encoding="utf-8")
        self.faits([self.fait("a", "A", "vente", 10), self.fait("b", "B", "vente", 3)])
        r = self.construire(article="A")
        self.assertEqual(r["kpis"]["ventes_colis"], 2)
        self.assertTrue(r["article"]["conditionnement_personnalise"])
        self.assertEqual(r["article"]["decision_conditionnement"]["motif"], "Colis pesé")
        self.assertTrue(r["article"]["comptable"])
        self.assertTrue(r["article"]["conditionnement_editable"])

    def test_pcb_absent_ne_devient_pas_un_colis_et_stock_perdu(self):
        self.ecrire("agregats.json", {"articles": {"C": {"libelle": "Sans PCB"}}})
        self.ecrire("etat.json", {"articles": {"A": {"position": -100}}})
        self.faits([self.fait("c", "C", "vente", 50), self.fait("a", "A", "vente", 10)])
        r = self.construire(article="A")
        self.assertEqual(r["kpis"]["ventes_colis"], 1)
        self.assertEqual(r["kpis"]["articles_sans_pcb_exclus"], 1)
        self.assertTrue(r["article"]["position_perdue"])
        self.assertIsNone(next(a for a in r["articles"] if a["itm8"] == "C")["ventes_colis"])

    def test_signaux_25_pourcent_ne_sont_pas_preuves(self):
        self.faits([self.fait("av", "A", "vente", 10), self.fait("al", "A", "livraison", 20),
                    self.fait("bv", "B", "vente", 9), self.fait("bl", "B", "livraison", 3)])
        r = self.construire(article="A")
        self.assertEqual(r["kpis"]["risque_surstock"], 1)
        self.assertEqual(r["kpis"]["risque_rupture"], 1)
        self.assertEqual(r["article"]["signal"], "surstock_suspecte")
        self.assertIn("pas une preuve", r["article"]["diagnostic"])
        self.assertNotIn("structurelle", r["article"]["diagnostic"])

    def test_conversion_jus_oranges_sans_double_compte(self):
        orange = "0000087004386"
        self.ecrire("agregats.json", {"articles": {orange: {"conditionnement": 10}}})
        self.faits([self.fait("jus", "0000000008112", "vente", 5)])
        r = self.construire(article=orange)
        self.assertEqual(r["article"]["ventes_unites"], 10)
        self.assertEqual(r["kpis"]["ventes_colis"], 1)

    def test_jeu_vide_horizon_et_article_invalides(self):
        r = self.construire()
        self.assertIsNone(r["kpis"]["ventes_colis"])
        self.assertIsNone(r["couverture"]["derniere_vente"])
        self.assertEqual(len(r["chronologie"]), 14)
        with self.assertRaisesRegex(ValueError, "Horizon"):
            self.construire(horizon="9999")
        with self.assertRaisesRegex(ValueError, "Article inconnu"):
            self.construire(article="../../.env")
        json.dumps(r, allow_nan=False)

    def test_promotions_dates_explicites_dernier_commentaire_sans_zero_invente(self):
        decisions = [{"id": "promo1", "type": "contexte-terrain", "article": "A", "valeur": {
            "promo_debut": "2030-04-08", "promo_fin": "2030-04-10", "commentaire_promo": "Première note",
            "precommande_colis": 5, "prix_promo": 2.5, "unite_prix_promo": "kg"}},
            {"id": "promo2", "type": "contexte-terrain", "article": "A", "valeur": {
            "promo_debut": "2030-04-08", "promo_fin": "2030-04-10", "commentaire_promo": "Note enrichie",
            "precommande_colis": 5, "prix_promo": 2.5, "unite_prix_promo": "kg", "rupture_promo": "oui"}}]
        (self.d / "decisions.jsonl").write_text("\n".join(json.dumps(d) for d in decisions)+"\n", encoding="utf-8")
        self.faits([self.fait("a", "A", "vente", 10, "2030-04-01"),
                    self.fait("b", "A", "vente", 20, "2030-04-08"),
                    self.fait("c", "A", "vente", 0, "2030-04-10"),
                    self.fait("d", "A", "livraison", 30, "2030-04-08"),
                    self.fait("e", "A", "don", 2, "2030-04-09")])
        r = self.construire(article="A")
        campagnes = r["article"]["analyses_promotions"]
        self.assertEqual(len(campagnes), 1)
        p = campagnes[0]
        self.assertEqual(p["id"], "promo2")
        self.assertEqual(p["commentaire_promo"], "Note enrichie")
        self.assertEqual(p["jours_avant"], 1)
        self.assertEqual(p["jours_promo"], 2)
        self.assertEqual(p["jours_promo_attendus"], 3)
        self.assertEqual(p["ventes_promo_moyenne"], 10)
        self.assertEqual(p["pertes_promo"], 2)
        self.assertEqual(p["livraisons_promo"], 30)
        self.assertEqual(p["precommande_colis"], 5)
        self.assertIsNone(p["precommande_future"]["colis"])
        self.assertIn("sous-estimer la demande", p["bilan_auto"])
        self.assertTrue(all(set(c) == {"titre", "texte", "source"} for c in r["article"]["commentaires_auto"]))

    def test_promotions_baseline_comparable_jours_semaine_et_pas_rapprochement_nom(self):
        decisions = [{"id": "promo", "type": "contexte-terrain", "article": "A", "valeur": {
            "promo_debut": "2030-04-08", "promo_fin": "2030-04-08", "rupture_promo": "non"}}]
        (self.d / "decisions.jsonl").write_text(json.dumps(decisions[0])+"\n", encoding="utf-8")
        # 1er et 8 avril sont des lundis ; le mardi atypique ne doit pas
        # influer sur la comparaison complémentaire à jours de semaine égaux.
        self.faits([self.fait("a", "A", "vente", 10, "2030-04-01"),
                    self.fait("b", "A", "vente", 100, "2030-04-02"),
                    self.fait("c", "A", "vente", 20, "2030-04-08")])
        r = self.construire(article="A")
        p = r["article"]["analyses_promotions"][0]
        self.assertEqual(p["ventes_avant_moyenne"], 55)
        self.assertEqual(p["ventes_avant_moyenne_comparee"], 10)
        self.assertEqual(p["evolution_ajustee_jours_pct"], 100)
        self.assertEqual(next(a for a in r["articles"] if a["itm8"] == "B")["analyses_promotions"], [])

    def test_promotions_futures_et_anciennes_restent_distinctes(self):
        decisions = [{"id": "ancienne", "type": "contexte-terrain", "article": "A", "valeur": {
            "promo_debut": "2030-03-01", "promo_fin": "2030-03-03", "bilan_promo": "À conserver"}},
            {"id": "future", "type": "contexte-terrain", "article": "A", "valeur": {
            "promo_debut": "2030-04-15", "promo_fin": "2030-04-17"}}]
        (self.d / "decisions.jsonl").write_text("\n".join(json.dumps(d) for d in decisions)+"\n", encoding="utf-8")
        self.faits([self.fait("a", "A", "vente", 10)])
        r = self.construire(article="A")
        campagnes = r["article"]["analyses_promotions"]
        self.assertEqual(len(campagnes), 2)
        self.assertEqual(campagnes[0]["jours_promo_attendus"], 0)
        self.assertIsNone(campagnes[0]["ventes_promo"])
        self.assertIsNone(campagnes[0]["evolution_pct"])
        self.assertEqual(campagnes[1]["bilan_promo"], "À conserver")

    def test_changement_terrain_ulterieur_ne_recrit_pas_campagne(self):
        promo = {"promo_debut": "2030-03-01", "promo_fin": "2030-03-03", "debut": "2030-03-01",
                 "fin": "2030-03-03", "emplacement": "tg", "commentaire_promo": "Belle implantation"}
        decisions = [{"id": "promo", "type": "contexte-terrain", "article": "A",
                      "enregistre_le": "2030-02-28T12:00:00", "valeur": promo},
            {"id": "autre", "type": "contexte-terrain", "article": "A", "enregistre_le": "2030-04-10T12:00:00",
             "valeur": {**promo, "debut": "2030-04-10", "fin": "2030-04-20", "emplacement": "ilot"}},
            {"id": "bilan", "type": "contexte-terrain", "article": "A", "enregistre_le": "2030-04-10T13:00:00",
             "annotation_seule": True, "requete": {"observations_fournies": ["bilan_promo"]},
             "valeur": {**promo, "debut": "2030-04-10", "fin": "2030-04-20", "emplacement": "ilot",
                        "bilan_promo": "Retour promotion de mars"}}]
        (self.d / "decisions.jsonl").write_text("\n".join(json.dumps(d) for d in decisions)+"\n", encoding="utf-8")
        self.faits([self.fait("a", "A", "vente", 10)])
        campagne = self.construire(article="A")["article"]["analyses_promotions"][0]
        self.assertEqual(campagne["emplacement"], "tg")
        self.assertEqual(campagne["id"], "bilan")
        self.assertEqual(campagne["bilan_promo"], "Retour promotion de mars")
        self.assertEqual(campagne["commentaire_promo"], "Belle implantation")

    def test_ca_prix_historiques_couverture_partielle_et_retours_signes(self):
        self.ecrire("catalogue.json", {"articles": {"A": {"PRIX VENTE": 999}}})
        self.faits([self.fait("a", "A", "vente", 10, prix_vente_unitaire=2, prix_achat_unitaire=1),
                    self.fait("b", "A", "vente", 4),
                    self.fait("c", "A", "vente", -2, prix_vente_unitaire=2, prix_achat_unitaire=1),
                    self.fait("d", "B", "vente", 0, prix_vente_unitaire=0)])
        r = self.construire(article="A")
        self.assertEqual(r["kpis"]["ca_reconstitue_eur"], 16)
        self.assertEqual(r["kpis"]["ca_faits_documentes"], 3)
        self.assertEqual(r["kpis"]["ca_faits_ventes"], 4)
        self.assertEqual(r["kpis"]["ca_couverture_pct"], 75)
        self.assertEqual(r["article"]["ca_reconstitue_eur"], 16)
        self.assertEqual(r["article"]["ca_couverture_pct"], 66.667)
        self.assertEqual(r["article"]["chronologie"][-1]["ca_reconstitue_eur"], 16)
        self.assertIsNone(r["kpis"]["marge_eur"])
        self.assertIn("HT/TTC", r["kpis"]["marge_motif"])

    def test_ca_zero_distinct_absent_et_jus_non_multiplie(self):
        orange = "0000087004386"
        jus = "0000000008112"
        self.ecrire("agregats.json", {"articles": {orange: {"conditionnement": 10}}})
        self.faits([self.fait("jus", jus, "vente", 5, prix_vente_unitaire=3),
                    self.fait("a", "A", "vente", 8),
                    self.fait("b", "B", "vente", 2, prix_vente_unitaire=0)])
        r = self.construire(article=orange)
        self.assertEqual(r["kpis"]["ca_reconstitue_eur"], 15)
        self.assertEqual(r["article"]["ventes_unites"], 10)
        self.assertIsNone(r["article"]["ca_reconstitue_eur"])
        self.assertEqual(next(a for a in r["articles"] if a["itm8"] == jus)["ca_reconstitue_eur"], 15)
        self.assertIsNone(next(a for a in r["articles"] if a["itm8"] == "A")["ca_reconstitue_eur"])
        self.assertEqual(next(a for a in r["articles"] if a["itm8"] == "B")["ca_reconstitue_eur"], 0)

    def test_photos_dernieres_versions_date_declaree_sans_analyse_image(self):
        photos = [{"schema": 1, "type": "photo-contexte", "id": "photo:fixture", "revision": 1,
                   "date_photo": "2030-04-09T09:30", "itm8": "A", "titre": "Ancienne note", "commentaire": "Brouillon"},
                  {"schema": 1, "type": "photo-contexte", "id": "photo:fixture", "revision": 2,
                   "date_photo": "2030-04-08T10:25", "enregistre_le": "2030-04-11T23:00:00",
                   "date_exif": "2020:01:01 00:00:00", "itm8": "A", "titre": "TG déclarée", "commentaire": "Mise en avant",
                   "nom_fichier": "image_absente_interdite.jpg"},
                  {"schema": 1, "type": "photo-contexte", "id": "photo:rayon", "revision": 1,
                   "date_photo": "2030-04-08T08:00", "itm8": None, "titre": "Vue générale"},
                  {"schema": 1, "type": "photo-contexte", "id": "photo:autre", "revision": 1,
                   "date_photo": "2030-04-08T08:00", "itm8": "B", "titre": "Autre produit"}]
        chemin = self.d / "photos-contexte.jsonl"
        chemin.write_text("\n".join(json.dumps(p) for p in photos)+"\n", encoding="utf-8")
        avant = chemin.read_bytes()
        self.faits([self.fait("a", "A", "vente", 10)])
        r = self.construire(article="A")
        self.assertEqual(chemin.read_bytes(), avant)
        self.assertEqual(r["article"]["photos_contexte_nombre"], 1)
        evenements = r["article"]["evenements_contextuels"]
        self.assertEqual(len(evenements), 1)
        self.assertEqual(evenements[0]["date"], "2030-04-08")
        self.assertEqual(evenements[0]["date_photo"], "2030-04-08T10:25")
        self.assertEqual(evenements[0]["titre"], "TG déclarée")
        self.assertEqual(evenements[0]["source"], "photos-contexte.jsonl")
        self.assertEqual(evenements[0]["nature"], "declaration")
        self.assertEqual(r["article"]["chronologie"][-3]["evenements_contextuels"], evenements)
        commentaire = next(c for c in r["article"]["commentaires_auto"] if c["titre"] == "Contexte visuel daté")
        self.assertIn("aucune analyse visuelle", commentaire["texte"])

    def test_evenements_contexte_promotion_dates_et_references(self):
        decision = {"id": "contexte:fixture", "type": "contexte-terrain", "article": "A",
                    "enregistre_le": "2030-04-01T12:00:00", "valeur": {"debut": "2030-04-05", "fin": "2030-04-10",
                        "promo_debut": "2030-04-06", "promo_fin": "2030-04-09", "note": "TG prévue", "emplacement": "tg"}}
        (self.d / "decisions.jsonl").write_text(json.dumps(decision)+"\n", encoding="utf-8")
        self.faits([self.fait("a", "A", "vente", 10)])
        article = self.construire(article="A")["article"]
        evenements = article["evenements_contextuels"]
        self.assertEqual([e["type"] for e in evenements], ["debut-contexte", "debut-promotion", "fin-promotion", "fin-contexte"])
        self.assertEqual([e["date"] for e in evenements], ["2030-04-05", "2030-04-06", "2030-04-09", "2030-04-10"])
        self.assertTrue(all(e["reference"] == "contexte:fixture" for e in evenements))
        self.assertEqual(article["chronologie"][-1]["evenements_contextuels"][0]["type"], "fin-contexte")


if __name__ == "__main__":
    unittest.main()
