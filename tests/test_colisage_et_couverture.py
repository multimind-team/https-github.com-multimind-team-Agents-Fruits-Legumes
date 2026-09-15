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
                self.assertTrue(any("Contradiction de colisage" in a for a in ligne["avertissements_conditionnement"]))
                self.assertEqual(ligne["prix_achat"], 2)

    def test_generation_fin_promotion_garde_quantite_et_montant(self):
        initiale = self.generer()
        offre = {"nom": "Orange", "debut": "2026-09-01",
                 "fin": initiale["date_livraison"],
                 "correspondances": [{"itm8": "ORANGE", "statut": "confirme"}]}
        self.ecrire("promotions", {"offres": [offre]})
        finale = self.generer()
        self.assertTrue(finale["lignes"][0]["fin_promotion"])
        self.assertEqual(finale["lignes"][0]["propose_colis"], initiale["lignes"][0]["propose_colis"])
        self.assertEqual(finale["totaux"]["montant_achat"], initiale["totaux"]["montant_achat"])

    def test_masques_exclus_aussi_du_nombre_articles_a_commander(self):
        self.config["overrides"]["PDT"] = {"masque": True}
        p = self.generer()
        self.assertEqual(p["totaux"]["articles_a_commander"], 1)
        self.assertEqual(p["totaux"]["montant_achat"], p["lignes"][0]["montant_achat"])

    def ajouter_alias_orange(self, code="ORANGE_ALIAS", pcb=6, achat=2):
        self.references[code] = {"CODE ITM": code, "LIBELLE": code,
                                 "CONDIT.BASE": 1, "UNITE MESURE": "2 kg"}
        self.config.setdefault("groupes", {}).setdefault("ORANGE", []).append(code)
        return {"article": code, "nom": code, "rang": 0, "groupe": "fruits",
                "offres": [{"par_colis": pcb, "prix_achat": achat}]}

    def test_alias_unique_recoit_stock_demande_prix_et_couverture_du_groupe(self):
        alias = self.ajouter_alias_orange()
        self.cadencier["articles"][0] = alias
        self.positions["ORANGE"]["position"] = 4
        self.agr["articles"]["ORANGE"]["dernierPrixVente"] = 3.69
        p = self.generer()
        ligne = p["lignes"][0]
        self.assertEqual(ligne["itm8"], "ORANGE_ALIAS")
        self.assertEqual(ligne["article_stock"], "ORANGE")
        self.assertTrue(ligne["connu"])
        self.assertEqual(ligne["position_unites"], 4)
        self.assertEqual(ligne["position_colis"], 0.7)
        self.assertEqual(ligne["position_mesuree_le"], "2026-09-07")
        self.assertEqual(ligne["demande"], 17)
        self.assertEqual(ligne["conditionnement"], 6)
        self.assertEqual(ligne["propose_colis"], 3)
        self.assertEqual(ligne["montant_achat"], 36)
        self.assertEqual(ligne["prix_vente"], 3.69)
        self.assertEqual(ligne["sorties_couvertes_jusquau"], "2026-09-07")
        self.assertEqual(ligne["commande_groupe_portee_par"], "ORANGE_ALIAS")
        self.assertFalse(ligne["commande_groupe_ambigue"])
        self.assertEqual(p["couverture_stock"]["articles_sans_mapping"], 0)
        self.assertEqual(p["couverture_stock"]["articles_sans_position"], 0)
        self.assertEqual(p["couverture_stock"]["articles_dernier_comptage"], 2)
        self.assertNotIn("ORANGE_ALIAS", self.positions)
        self.assertNotIn("ORANGE_ALIAS", self.moyennes)

    def test_principal_present_porte_seul_besoin_sans_doubler_les_alias(self):
        alias = self.ajouter_alias_orange()
        alias["rang"] = -1
        self.cadencier["articles"].insert(0, alias)
        p = self.generer()
        lignes = {l["itm8"]: l for l in p["lignes"]}
        self.assertEqual([l["itm8"] for l in p["lignes"]], ["ORANGE_ALIAS", "ORANGE", "PDT"])
        self.assertEqual(lignes["ORANGE"]["propose_colis"], 3)
        secondaire = lignes["ORANGE_ALIAS"]
        self.assertEqual(secondaire["propose_colis"], 0)
        self.assertEqual(secondaire["montant_achat"], 0)
        self.assertTrue(secondaire["connu"])
        self.assertEqual(secondaire["demande"], 17)
        self.assertEqual(secondaire["commande_groupe_portee_par"], "ORANGE")
        self.assertIn("une seule fois", secondaire["motif_commande_groupe"])
        self.assertFalse(secondaire["commande_groupe_ambigue"])
        self.assertEqual(p["totaux"]["colis"], lignes["ORANGE"]["propose_colis"] + lignes["PDT"]["propose_colis"])

    def test_plusieurs_alias_sans_principal_exigent_un_choix_sans_repartir(self):
        alias1 = self.ajouter_alias_orange("ALIAS1", 6, 2)
        alias2 = self.ajouter_alias_orange("ALIAS2", 10, 5)
        self.cadencier["articles"] = [alias1, alias2]
        self.positions["ORANGE"]["position"] = 4
        p = self.generer()
        self.assertEqual(p["totaux"]["colis"], 0)
        self.assertEqual(p["totaux"]["montant_achat"], 0)
        self.assertEqual([l["conditionnement"] for l in p["lignes"]], [6, 10])
        self.assertEqual([l["prix_achat"] for l in p["lignes"]], [2, 5])
        for l in p["lignes"]:
            self.assertEqual(l["position_unites"], 4)
            self.assertTrue(l["connu"])
            self.assertEqual(l["demande"], 17)
            self.assertEqual(l["propose_colis"], 0)
            self.assertTrue(l["commande_groupe_ambigue"])
            self.assertIsNone(l["commande_groupe_portee_par"])
            self.assertIn("Choisissez", l["motif_commande_groupe"])

    def test_principal_masque_alias_unique_et_decision_propre_conserves(self):
        alias = self.ajouter_alias_orange(pcb=6)
        alias["offres"].append({"par_colis": 4, "prix_achat": 5})
        self.config["overrides"]["ORANGE"] = {"masque": True, "conditionnement": "8", "unite": "kg"}
        self.config["overrides"]["ORANGE_ALIAS"] = {"conditionnement": "4", "fournisseur": "DIRECT"}
        self.cadencier["articles"].append(alias)
        p = self.generer()
        lignes = {l["itm8"]: l for l in p["lignes"]}
        self.assertTrue(lignes["ORANGE"]["masque"])
        l = lignes["ORANGE_ALIAS"]
        self.assertFalse(l["masque"])
        self.assertEqual(l["conditionnement"], 4)
        self.assertEqual(l["prix_achat"], 5)
        self.assertEqual(l["propose_colis"], 5)
        self.assertEqual(l["montant_achat"], 100)
        self.assertEqual(l["fournisseur"], "DIRECT")
        self.assertEqual(l["unite"], "kg")
        self.assertEqual(l["commande_groupe_portee_par"], "ORANGE_ALIAS")
        self.assertNotIn("masque", self.config["overrides"]["ORANGE_ALIAS"])

    def test_alias_sans_decision_garde_pcb_offre_malgre_reglage_du_principal(self):
        self.cadencier["articles"] = [self.ajouter_alias_orange(pcb=6, achat=2)]
        self.config["overrides"]["ORANGE"] = {"conditionnement": "8", "fournisseur": "DIRECT"}
        l = self.generer()["lignes"][0]
        self.assertEqual(l["conditionnement"], 6)
        self.assertEqual(l["prix_achat"], 2)
        self.assertEqual(l["propose_colis"], 3)
        self.assertEqual(l["montant_achat"], 36)
        self.assertEqual(l["source_conditionnement"], "cadencier")
        self.assertEqual(l["avertissements_conditionnement"], [])
        self.assertNotEqual(l["fournisseur"], "DIRECT")
        self.assertNotIn("ORANGE_ALIAS", self.config["overrides"])

    def test_alias_sans_profil_garde_position_reelle_sans_inventer_ventes(self):
        self.cadencier["articles"] = [self.ajouter_alias_orange()]
        self.moyennes.pop("ORANGE")
        self.positions["ORANGE"]["position"] = 12
        l = self.generer()["lignes"][0]
        self.assertFalse(l["connu"])
        self.assertEqual(l["position_colis"], 2)
        self.assertEqual(l["position_mesuree_le"], "2026-09-07")
        self.assertEqual(l["propose_colis"], 0)
        self.assertEqual(l["article_stock"], "ORANGE")

    def test_alias_reutilise_recence_livraison_et_promotion_du_principal(self):
        self.cadencier["articles"] = [self.ajouter_alias_orange()]
        self.moyennes["ORANGE"]["saison"] = [1] * 366
        self.agr["dernieres_livraisons"] = {"ORANGE": "2026-09-08"}
        l = self.generer()["lignes"][0]
        self.assertEqual(l["demande"], 2)
        self.assertEqual(l["propose_colis"], 0)  # livraison récente : arrondi au plus proche
        self.agr["dernieres_livraisons"] = {}
        self.assertEqual(self.generer()["lignes"][0]["propose_colis"], 1)
        self.config["overrides"]["ORANGE"] = {"promotion": True}
        l = self.generer()["lignes"][0]
        self.assertTrue(l["promotion"])
        self.assertEqual(l["propose_colis"], 0)

    def test_principal_masque_et_plusieurs_alias_ne_designent_aucune_offre(self):
        self.cadencier["articles"] += [self.ajouter_alias_orange("ALIAS1"), self.ajouter_alias_orange("ALIAS2")]
        self.config["overrides"]["ORANGE"] = {"masque": True}
        p = self.generer()
        for l in p["lignes"]:
            if l["itm8"].startswith("ALIAS"):
                self.assertTrue(l["commande_groupe_ambigue"])
                self.assertEqual(l["propose_colis"], 0)

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
