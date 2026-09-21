"""Analyse commerciale paramétrable, fixtures isolées et HTTP éphémère."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "moteur"))
import analyse_ventes
import pilotage
import test_serveur_securite as serveur_fixture


class AnalyseVentesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="analyse-ventes-fixture-")
        self.addCleanup(self.temp.cleanup)
        self.d = Path(self.temp.name) / "donnees"
        (self.d / "faits").mkdir(parents=True)
        self.ecrire("proposition.json", {"lignes": [
            {"itm8": "A", "libelle": "Pommes", "conditionnement": 10, "unite": "kg"},
            {"itm8": "B", "libelle": "Salades", "conditionnement": 3, "unite": "pièce"}]})

    def ecrire(self, nom, valeur):
        (self.d / nom).write_text(json.dumps(valeur), encoding="utf-8")

    def fait(self, identifiant, quantite, jour="2030-04-10", article="A", type="vente", **champs):
        return {"id": identifiant, "article": article, "type": type, "quantite": quantite,
                "date_source": jour, "unite": "kg", **champs}

    def faits(self, lignes):
        (self.d / "faits/2030.jsonl").write_text("\n".join(json.dumps(l) for l in lignes)+"\n", encoding="utf-8")

    def construire(self, **options):
        return analyse_ventes.construire(self.d, aujourd_hui="2030-04-11", **options)

    def test_defaut_14jours_et_precedente_calendaires(self):
        self.faits([self.fait("a", 10), self.fait("b", 3, "2030-04-01"), self.fait("c", 9, "2030-03-20")])
        r = self.construire()
        self.assertEqual(r["periode"], {"debut": "2030-03-28", "fin": "2030-04-10", "jours": 14})
        self.assertEqual(r["comparaison"], {"mode": "precedente", "debut": "2030-03-14", "fin": "2030-03-27", "jours": 14})
        self.assertEqual(r["couverture"]["premiere_vente"], "2030-03-20")
        self.assertEqual(r["couverture"]["derniere_vente"], "2030-04-10")
        self.assertEqual(r["couverture"]["jours_ventes_observes"], 2)
        self.assertEqual(len(r["jours"]), 3)

    def test_sparse_null_et_zero_atteste_restent_distincts(self):
        self.faits([self.fait("zero", 0, prix_vente_unitaire=2),
                    self.fait("livraison", 20, "2030-04-09", type="livraison"),
                    self.fait("casse", 1, type="casse"), self.fait("don", 2, type="don")])
        r = self.construire(debut="2030-04-08", fin="2030-04-10", comparaison="aucune")
        self.assertEqual(len(r["jours"]), 2)
        self.assertEqual(r["jours"][0]["date"], "2030-04-09")
        self.assertIsNone(r["jours"][0]["ventes"])
        self.assertIsNone(r["jours"][0]["ca_reconstitue_eur"])
        self.assertEqual(r["jours"][1]["ventes"], 0)
        self.assertEqual(r["jours"][1]["ventes_colis"], 0)
        self.assertEqual(r["jours"][1]["ca_reconstitue_eur"], 0)
        self.assertEqual(r["jours"][1]["pertes"], 3)
        self.assertEqual(r["comparaison"]["jours"], 0)

    def test_ca_historique_partiel_retours_sans_prix_courant(self):
        self.ecrire("catalogue.json", {"articles": {"A": {"PRIX VENTE": 999}}})
        self.faits([self.fait("a", 10, prix_vente_unitaire=2), self.fait("b", -2, prix_vente_unitaire=2), self.fait("c", 4)])
        r = self.construire(comparaison="aucune")
        self.assertEqual(r["jours"][0]["ventes"], 12)
        self.assertEqual(r["jours"][0]["ca_reconstitue_eur"], 16)
        self.assertEqual(r["jours"][0]["ca_faits_documentes"], 2)
        self.assertEqual(r["jours"][0]["ca_faits_ventes"], 3)
        self.assertEqual(r["couverture"]["ca_couverture_pct"], 66.667)
        self.assertIn("HT/TTC", " ".join(r["limites"]))

    def test_annee_precedente_29_fevrier_et_union_sans_trou_artificiel(self):
        self.faits([self.fait("a", 10, "2028-02-29"), self.fait("b", 20, "2027-02-28"), self.fait("c", 30, "2027-07-01")])
        r = self.construire(debut="2028-02-29", fin="2028-02-29", comparaison="annee_precedente")
        self.assertEqual(r["comparaison"], {"mode": "annee_precedente", "debut": "2027-02-28", "fin": "2027-02-28", "jours": 1})
        self.assertEqual([l["date"] for l in r["jours"]], ["2027-02-28", "2028-02-29"])

    def test_dates_strictes_horizon_et_comparaison_invalides(self):
        for options in [
            {"debut": "2030-04-01"}, {"debut": "20300401", "fin": "2030-04-10"},
            {"debut": "2030-02-30", "fin": "2030-04-10"}, {"debut": "2030-04-11", "fin": "2030-04-10"},
            {"debut": "2000-01-01", "fin": "2030-01-01"}, {"comparaison": "inventee"},
            {"debut": "0001-01-01", "fin": "0001-01-01", "comparaison": "precedente"},
        ]:
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.construire(**options)
        r = self.construire(debut="2000-01-01", fin="2010-01-01", comparaison="aucune")
        self.assertGreater(r["periode"]["jours"], 3650)

    def test_unites_sources_douteuses_empechent_conversion_colis_par_flux(self):
        self.faits([self.fait("inconnu", 7, unite="inconnue"), self.fait("piece", 2, type="livraison", unite="piece"),
                    self.fait("casse", 1, type="casse")])
        r = self.construire(comparaison="aucune")
        ligne = r["jours"][0]
        self.assertEqual(ligne["ventes"], 7)
        self.assertIsNone(ligne["ventes_colis"])
        self.assertIsNone(ligne["livraisons_colis"])
        self.assertEqual(ligne["pertes_colis"], .1)
        self.assertFalse(ligne["unites_fiables"])
        self.assertEqual(r["couverture"]["faits_unite_inconnue"], 1)
        self.assertEqual(r["couverture"]["faits_unite_incompatible"], 1)

    def test_promotions_filtrent_article_jour_seulement_dates_documentees(self):
        decisions = [{"id": "campagne", "type": "contexte-terrain", "article": "A", "valeur": {
            "promo_debut": "2030-04-09", "promo_fin": "2030-04-10"}}]
        (self.d / "decisions.jsonl").write_text(json.dumps(decisions[0])+"\n", encoding="utf-8")
        self.faits([self.fait("avant", 10, "2030-04-08"), self.fait("pendant", 20),
                    self.fait("autre", 3, article="B", unite="piece")])
        r = self.construire(comparaison="aucune")
        self.assertEqual([l["promo_documentee"] for l in r["jours"]], [False, True, False])
        a = next(a for a in r["articles"] if a["itm8"] == "A")
        self.assertEqual(a["campagnes"][0]["reference"], "campagne")
        self.assertIn("statut promotion reste inconnu", " ".join(r["limites"]))

    def test_groupes_et_doublons_une_ligne_canonique(self):
        self.ecrire("proposition.json", {"lignes": [
            {"itm8": "A", "conditionnement": 10, "unite": "kg"},
            {"itm8": "C", "article_stock": "A", "conditionnement": 5, "unite": "kg"}]})
        autre = self.fait("c", 4, article="C", prix_vente_unitaire=3)
        self.faits([self.fait("a", 6, prix_vente_unitaire=2), autre, {**autre, "source": {"nom": "copie"}}])
        r = self.construire(comparaison="aucune")
        self.assertEqual(len(r["jours"]), 1)
        self.assertEqual(r["jours"][0]["ventes_colis"], 1)
        self.assertEqual(r["jours"][0]["ca_reconstitue_eur"], 24)
        self.assertEqual(r["couverture"]["doublons_ignores"], 1)
        self.assertEqual(r["articles"][0]["codes_regroupes"], ["A", "C"])

    def test_jus_conserve_ventes_commerciales_ca_et_cockpit_physique(self):
        jus, orange = "0000000008112", "0000087004386"
        self.ecrire("proposition.json", {"lignes": [
            {"itm8": jus, "conditionnement": 6, "unite": "piece", "libelle": "Jus 1L"},
            {"itm8": orange, "conditionnement": 10, "unite": "kg", "libelle": "Orange machine"}]})
        self.faits([self.fait("jus", 3, article=jus, unite="piece", prix_vente_unitaire=4)])
        r = self.construire(comparaison="aucune")
        self.assertEqual(len(r["jours"]), 1)
        self.assertEqual(r["jours"][0]["itm8"], jus)
        self.assertEqual(r["jours"][0]["ventes"], 3)
        self.assertEqual(r["jours"][0]["ventes_colis"], .5)
        self.assertEqual(r["jours"][0]["ca_reconstitue_eur"], 12)
        physique = pilotage.construire(self.d, article=orange, aujourd_hui="2030-04-11")
        self.assertEqual(physique["article"]["ventes_unites"], 6)

    def test_lecture_seule_vide_et_cache_non_modifie(self):
        self.faits([self.fait("a", 10)])
        avant = {str(p.relative_to(self.d)): p.read_bytes() for p in self.d.rglob("*") if p.is_file()}
        r = self.construire()
        r["jours"][0]["ventes"] = 999
        self.assertEqual(self.construire()["jours"][0]["ventes"], 10)
        apres = {str(p.relative_to(self.d)): p.read_bytes() for p in self.d.rglob("*") if p.is_file()}
        self.assertEqual(avant, apres)
        self.faits([])
        vide = self.construire()
        self.assertEqual(vide["jours"], [])
        self.assertIsNone(vide["couverture"]["premiere_vente"])
        self.assertIsNone(vide["couverture"]["ca_couverture_pct"])
        json.dumps(vide, allow_nan=False)


class AnalyseVentesHTTPTests(unittest.TestCase):
    setUp = serveur_fixture.ServeurIsoleTests.setUp
    fermer = serveur_fixture.ServeurIsoleTests.fermer
    ecrire = serveur_fixture.ServeurIsoleTests.ecrire
    requete = serveur_fixture.ServeurIsoleTests.requete

    def test_get_head_provenance_et_aucune_ecriture_metier(self):
        fait = {"id": "vente:fixture", "article": serveur_fixture.CODE, "type": "vente", "date_source": "2026-01-03", "quantite": 12, "unite": "piece"}
        self.ecrire("donnees/faits/2026.jsonl", json.dumps(fait)+"\n")
        url = "/api/analyse-ventes?debut=2026-01-01&fin=2026-01-04&comparaison=aucune"
        avant = (self.root / "donnees/faits/2026.jsonl").read_bytes()
        statut, corps, headers = self.requete("GET", url)
        self.assertEqual(statut, 200, corps)
        self.assertEqual(json.loads(corps)["jours"][0]["ventes_colis"], 1)
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(self.requete("HEAD", url)[1], b"")
        self.assertEqual(self.requete("GET", url, headers={"Host": "evil.test"})[0], 403)
        self.assertEqual(self.requete("POST", "/api/analyse-ventes", {})[0], 404)
        self.assertEqual(avant, (self.root / "donnees/faits/2026.jsonl").read_bytes())
        self.recalc_mock.assert_not_called()

    def test_parametres_invalides_http400(self):
        self.ecrire("donnees/faits/2026.jsonl", "")
        for query in ["debut=", "debut=2026-01-01", "debut=20260101&fin=2026-01-03", "comparaison=inconnue",
                      "debut=2026-01-01&debut=2026-01-02&fin=2026-01-03", "article=secret"]:
            with self.subTest(query=query):
                self.assertEqual(self.requete("GET", "/api/analyse-ventes?"+query)[0], 400)


if __name__ == "__main__":
    unittest.main()
