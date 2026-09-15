"""Régressions audit F08/F11/F12/F13 ; uniquement fixtures et répertoires temporaires."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

MOTEUR = Path(__file__).resolve().parents[1] / "moteur"
sys.path.insert(0, str(MOTEUR))


def charger(nom):
    spec = importlib.util.spec_from_file_location("audit_regression_" + nom.replace("-", "_"), MOTEUR / (nom + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


POSITION = charger("calculer-position")
AUDIT = charger("analyser-ecarts-comptage")
CATALOGUE = charger("importer-catalogue-mercalys")
ANALYSE = charger("analyser-ventes-livraisons")


def fait(identifiant, type_fait, jour, quantite, article="A", heure="18:00:00", **extra):
    return {"id": identifiant, "type": type_fait, "article": article,
            "date_effet": jour, "date_source": jour, "quantite": quantite,
            "horodatage": jour + "T" + heure, **extra}


class ChronologieAuditTests(unittest.TestCase):
    def test_seuil_soir_exactement_17h(self):
        for heure in ("16:49:00", "16:50:00", "16:59:59", "17:00:00"):
            with self.subTest(heure=heure):
                attendu = "soir" if heure == "17:00:00" else "matin"
                mesure = fait("c", "comptage", "2026-09-11", 5, heure=heure)
                self.assertEqual(POSITION.moment_du_comptage(mesure), attendu)
                self.assertEqual(AUDIT.moment_du_comptage(mesure), attendu)

    def test_comptage_matin_ninclut_pas_ventes_ulterieures(self):
        base = fait("c0", "comptage", "2026-09-10", 10)
        livraison = fait("l1", "livraison", "2026-09-11", 5)
        cible = fait("c1", "comptage", "2026-09-11", 15, heure="08:00:00")
        vente = fait("v1", "vente", "2026-09-11", 4)
        historique = [base, livraison, cible, vente]
        info = POSITION.position_avant_comptage(cible, historique, {}, {})
        self.assertEqual(info["position"], 15)
        self.assertEqual([m["id"] for m in info["mouvements_appliques"]], ["l1"])
        self.assertEqual(POSITION.calculer_depuis_faits(historique, {}, {})["A"]["position"], 11)

    def test_conversion_corrigee_preserve_la_phase_avant_et_apres_17h(self):
        for heure, attendu, moment, nombre in (("16:58:54", -37, "matin", 2),
                                               ("17:00:00", -35, "soir", 1)):
            with self.subTest(heure=heure):
                base = fait("c0", "comptage", "2026-09-07", -260, heure=heure,
                            source={"saisi_le": "2026-09-07T" + heure})
                # La correction est enregistrée le soir, sans déplacer le relevé.
                correction = fait("corr0", "correction-comptage", "2026-09-07", -32,
                                  heure="19:00:00", cible_id="c0")
                historique = [base, fait("v0", "vente", "2026-09-07", 2),
                              fait("v1", "vente", "2026-09-08", 3), correction]
                etat = POSITION.calculer_depuis_faits(historique, {}, {})["A"]
                self.assertEqual(etat["position"], attendu)
                self.assertEqual(etat["moment_mesure"], moment)
                self.assertEqual(etat["mouvements_depuis"], nombre)
                self.assertEqual(etat["mesuree_le"], "2026-09-07")
                cible = fait("c1", "comptage", "2026-09-09", attendu)
                avant = POSITION.position_avant_comptage(cible, [*historique, cible], {}, {})
                self.assertEqual(avant["position"], attendu)
                self.assertEqual(len(avant["mouvements_appliques"]), nombre)

    def test_avant_livraison_et_absence_de_base(self):
        base = fait("c0", "comptage", "2026-09-10", 10)
        livraison = fait("l1", "livraison", "2026-09-11", 5)
        cible = fait("c1", "comptage", "2026-09-11", 10, heure="05:00:00")
        self.assertEqual(POSITION.position_avant_comptage(cible, [base, livraison, cible], {}, {})["position"], 10)
        with patch.object(AUDIT.regles, "charger", return_value={}):
            info = AUDIT.auditer_un_comptage(cible, [livraison, cible], {}, {}, {})
        self.assertEqual(info["statut"], "inconnu")
        self.assertIsNone(info["ecart"]["unites"])
        self.assertIn("Aucun stock antérieur", AUDIT.formater_message_chat({"resultats": [info]}))

    def test_correction_conserve_linstant_et_corrige_base_precedente(self):
        base = fait("c0", "comptage", "2026-09-10", 8)
        corr_base = fait("corr0", "correction-comptage", "2026-09-10", 10, cible_id="c0")
        livraison = fait("l1", "livraison", "2026-09-11", 5)
        cible = fait("c1", "comptage", "2026-09-11", 12, heure="08:00:00")
        vente = fait("v1", "vente", "2026-09-11", 4)
        corr = fait("corr1", "correction-comptage", "2026-09-11", 15, cible_id="c1")
        info = POSITION.position_avant_comptage(corr, [base, corr_base, livraison, cible, vente, corr], {}, {})
        self.assertEqual(info["position"], 15)

    def test_groupes_et_oranges_partagent_le_calcul_canonique(self):
        base = fait("c0", "comptage", "2026-09-10", 10, article="B")
        vente = fait("v1", "vente", "2026-09-11", 4)
        cible = fait("c1", "comptage", "2026-09-11", 6)
        self.assertEqual(POSITION.position_avant_comptage(cible, [base, vente, cible], {"groupes": {"A": ["A", "B"]}}, {})["position"], 6)
        orange = POSITION.ORANGE_MACHINE_A_JUS
        base = fait("o0", "comptage", "2026-09-10", 10, article=orange)
        vente_jus = fait("j1", "vente", "2026-09-11", 2, article="0000000008112")
        cible = fait("o1", "comptage", "2026-09-11", 6, article=orange)
        self.assertEqual(POSITION.position_avant_comptage(cible, [base, vente_jus, cible], {}, {})["position"], 6)

    def test_heure_physique_precede_envoi_differe(self):
        soir = fait("c0", "comptage", "2026-09-11", 9)
        matin_envoye_tard = fait("c1", "comptage", "2026-09-11", 10, heure="19:00:00", source={"saisi_le": "2026-09-11T08:00:00"})
        resultat = POSITION.calculer_depuis_faits([soir, matin_envoye_tard], {}, {})
        self.assertEqual(resultat["A"]["position"], 9)


class ImportCatalogueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dossier = Path(self.tmp.name)
        self.sortie = self.dossier / "catalogue.json"
        self.initial = {"derniere_maj": "2026-09-10", "ordre_webtelevente": {"ancien": 4},
                        "articles": {"ancien": {"LIBELLE": "Conserver historique"}}}
        self.sortie.write_text(json.dumps(self.initial), encoding="utf-8")

    def creer_source(self, nom="cadencier 11.09.2026.xlsx", prix=2, jour="11/09/2026"):
        from openpyxl import Workbook
        source = self.dossier / nom
        wb = Workbook()
        wb.active.append(["Date d'application :" + jour])
        wb.active.append(["CODE ITM", "LIBELLE", "CONDIT.BASE", "UNITE MESURE", "PRIX ACHAT BRUT", "PRIX VENTE"])
        wb.active.append(["0000087004011", "BANANE", 18, "2 kg", prix, 3])
        wb.active.append(["Nombre de lignes : :000001"])
        wb.save(source)
        wb.close()
        return source

    def test_simulation_fusion_sans_perte_et_cache(self):
        source = self.creer_source()
        avant = self.sortie.read_bytes()
        simulation = CATALOGUE.importer([source], sortie=self.sortie)
        self.assertTrue(simulation["ok"], simulation)
        self.assertEqual(self.sortie.read_bytes(), avant)
        with patch.object(CATALOGUE.catalogue, "FICHIER", self.sortie):
            self.assertNotIn("0000087004011", CATALOGUE.catalogue.noms())
            reel = CATALOGUE.importer([source], sortie=self.sortie, simuler=False)
            self.assertTrue(reel["ecrit"])
            self.assertEqual(CATALOGUE.catalogue.noms()["0000087004011"], "BANANE")
            self.assertEqual(CATALOGUE.catalogue.ordre_webtelevente(), {"ancien": 4})
            self.assertIn("ancien", CATALOGUE.catalogue.articles())
            # Simule un remplacement par un autre processus, sans cache_clear.
            donnees = json.loads(self.sortie.read_text(encoding="utf-8"))
            donnees["articles"]["0000087004011"]["LIBELLE"] = "BANANE BIO"
            self.sortie.write_text(json.dumps(donnees), encoding="utf-8")
            self.assertEqual(CATALOGUE.catalogue.noms()["0000087004011"], "BANANE BIO")

    def test_fichier_ancien_ou_invalide_refuse_sans_ecriture(self):
        for prix, jour in ((-3, "11/09/2026"), (2, "09/09/2026")):
            with self.subTest(prix=prix, jour=jour):
                source = self.creer_source(prix=prix, jour=jour)
                avant = self.sortie.read_bytes()
                resultat = CATALOGUE.importer([source], sortie=self.sortie, simuler=False)
                self.assertFalse(resultat["ok"])
                self.assertEqual(self.sortie.read_bytes(), avant)

    def test_lot_contradictoire_refuse_integralement(self):
        source = self.creer_source()
        autre = self.creer_source("autre.xlsx", prix=4)
        avant = self.sortie.read_bytes()
        resultat = CATALOGUE.importer([source, autre], sortie=self.sortie, simuler=False)
        self.assertFalse(resultat["ok"])
        self.assertEqual(self.sortie.read_bytes(), avant)


class ContextesTests(unittest.TestCase):
    def test_livraison_date_effet_et_ventes_date_source(self):
        source = [fait("l1", "livraison", "2026-09-15", 7, date_source="2026-09-14"),
                  fait("v1", "vente", "2026-09-14", 8.74)]
        import faits
        with patch.object(faits, "lire", return_value=iter(source)):
            livraisons, _, ventes, _ = ANALYSE.charger_faits_recents("2026-09-14")
        self.assertEqual(dict(livraisons["A"]), {"2026-09-15": 7})
        self.assertEqual(dict(ventes["A"]), {"2026-09-14": 8.74})

    def test_meteo_absente_et_fermeture_exceptionnelle(self):
        cal = {"feries": {}, "vacances": [{"debut": "2026-01-01", "fin": "2027-01-01", "nom": ""}]}
        info = ANALYSE.qualifier_contexte_jour("2026-09-11", cal, {}, {"jours": {}})
        self.assertFalse(info["contexte_verifie"])
        self.assertIsNone(info["pluie_mm"])
        info = ANALYSE.qualifier_contexte_jour("2026-09-11", cal, {"2026-09-11": [24, 0]}, {"jours": {"2026-09-11": {"statut": "ferme"}}})
        self.assertTrue(info["contexte_verifie"])
        self.assertTrue(info["ferme"])
        self.assertTrue(info["causes"])


if __name__ == "__main__":
    unittest.main()
