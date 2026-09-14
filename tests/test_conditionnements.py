"""Sélection colis/prix : fixtures seules, aucun carnet métier modifié."""
import importlib.util
import json
import math
from pathlib import Path
import tempfile
import unittest

MOTEUR = Path(__file__).resolve().parents[1] / "moteur"


def module(fichier):
    chemin = MOTEUR / fichier
    assert chemin.exists(), f"Module de sélection manquant : {fichier}"
    spec = importlib.util.spec_from_file_location("test_" + fichier.replace("-", "_"), chemin)
    resultat = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(resultat)
    return resultat


def offre(pcb, prix=3.89):
    return {"par_colis": pcb, "prix_achat": prix,
            "libelle": "offre fournisseur exacte", "prix_vente_conseille": 4.99}


class SelectionTests(unittest.TestCase):
    def selectionner(self, *args, **kwargs):
        return module("conditionnements.py").selectionner(*args, **kwargs)

    def test_orange_dessert_pcb_du_jour_prioritaire_sur_mercalys_un(self):
        achat = offre(8, 1.7899999618530273)
        resultat = self.selectionner({"nom": "ORANGE DESSERT VRAC", "offres": [achat]},
                                    reference={"CONDIT.BASE": 1})
        self.assertEqual(resultat["conditionnement"], 8.0)
        self.assertIsInstance(resultat["conditionnement"], float)
        self.assertEqual(resultat["source_conditionnement"], "cadencier")
        self.assertIs(resultat["offre"], achat)
        self.assertIsInstance(resultat["avertissements"], list)

    def test_caissette_uniquement_pour_les_paires_metier_attestees(self):
        for nom, pcbs, attendu in [
            ("PDT PRINCESSE AMANDINE 2KG", [65, 8], 8),
            ("ORANGE DESSERT FILET 2KG", [90, 9], 9),
            ("PDT PRINCESSE AMANDINE 2KG", [65, 9], 65),
            ("TOMATE", [65, 8], 65),
            ("ORANGE DESSERT VRAC", [90, 9], 90),
            ("CAROTTE", [12, 6], 12),
        ]:
            with self.subTest(nom=nom, pcbs=pcbs):
                offres = [offre(pcb, 2.0 + i) for i, pcb in enumerate(pcbs)]
                resultat = self.selectionner({"nom": nom, "offres": offres})
                self.assertEqual(resultat["conditionnement"], float(attendu))
                self.assertIs(resultat["offre"], offres[pcbs.index(attendu)])
                if attendu != pcbs[0]:
                    self.assertEqual(resultat["source_conditionnement"], "cadencier_caissette")
                else:
                    self.assertTrue(resultat["avertissements"])

    def test_surcharge_prioritaire_et_prix_de_loffre_correspondante(self):
        offres = [offre(65, 2.1), offre(8, 3.890000104904175)]
        for pcb, index, conflit in [(8, 1, False), (65, 0, False), (5, 0, True)]:
            with self.subTest(pcb=pcb):
                resultat = self.selectionner(
                    {"nom": "PDT PRINCESSE AMANDINE 2KG", "offres": offres},
                    surcharge={"conditionnement": str(pcb)}, reference={"CONDIT.BASE": 1})
                self.assertEqual(resultat["conditionnement"], float(pcb))
                self.assertEqual(resultat["source_conditionnement"], "decision")
                self.assertIs(resultat["offre"], offres[index])
                self.assertEqual(bool(resultat["avertissements"]), conflit)
                if conflit:
                    self.assertIn("contradiction", " ".join(resultat["avertissements"]).lower())

    def test_nombres_non_finis_non_positifs_et_booleens_refuses(self):
        invalides = [None, "", "inconnu", "8,5", 0, -8, True, False,
                     float("nan"), float("inf"), float("-inf"), "NaN", "Infinity", 10 ** 400]
        for valeur in invalides:
            with self.subTest(valeur=repr(valeur)):
                bon = offre(8)
                decision = self.selectionner({"offres": [bon]}, {"conditionnement": valeur})
                self.assertEqual(decision["conditionnement"], 8.0)
                self.assertNotEqual(decision["source_conditionnement"], "decision")
                self.assertTrue(decision["avertissements"])
                pcb = self.selectionner({"offres": [offre(valeur), bon]})
                self.assertEqual(pcb["conditionnement"], 8.0)
                self.assertIs(pcb["offre"], bon)
                self.assertTrue(pcb["avertissements"])
                reference = self.selectionner(None, reference={"CONDIT.BASE": valeur})
                self.assertEqual(reference["conditionnement"], 1.0)
                self.assertEqual(reference["source_conditionnement"], "inconnu")
                self.assertTrue(reference["avertissements"])
                self.assertTrue(math.isfinite(reference["conditionnement"]))

    def test_colisage_absent_repli_explicite_sans_fabriquer_le_prix(self):
        sans_pcb = {"prix_achat": 3.490000009536743, "libelle": "FILET 5 Kg"}
        for article in [None, {}, {"offres": []}, {"offres": [sans_pcb]}]:
            with self.subTest(article=article):
                resultat = self.selectionner(article)
                self.assertEqual(resultat["conditionnement"], 1.0)
                self.assertEqual(resultat["source_conditionnement"], "inconnu")
                self.assertTrue(resultat["avertissements"])
                self.assertTrue(all(isinstance(a, str) for a in resultat["avertissements"]))
                self.assertEqual(resultat["offre"], sans_pcb if article and article.get("offres") else {})
        mercalys = self.selectionner({"offres": [sans_pcb]}, reference={"CONDIT.BASE": "6.5"})
        self.assertEqual(mercalys["conditionnement"], 6.5)
        self.assertEqual(mercalys["source_conditionnement"], "mercalys")
        self.assertIs(mercalys["offre"], sans_pcb)
        decision = self.selectionner(None, {"conditionnement": "5"})
        self.assertEqual(decision["conditionnement"], 5.0)
        self.assertEqual(decision["source_conditionnement"], "decision")
        self.assertEqual(decision["offre"], {})
        self.assertTrue(decision["avertissements"])


class ChargementTests(unittest.TestCase):
    def test_code_repete_ne_remplace_pas_silencieusement_loffre(self):
        selections = module("conditionnements.py")
        with tempfile.TemporaryDirectory() as repertoire:
            racine = Path(repertoire)
            (racine / "donnees").mkdir()
            fichier = racine / "donnees/cadencier-du-jour.json"
            articles = [
                {"article": "0000087004327", "nom": "PASTEQUE MINI PIECE", "offres": [offre(7, 2.55)]},
                {"article": "0000087004327", "nom": "PASTEQUE MINI PIECE BIO ITM", "offres": [offre(8, 3.29)]},
            ]
            fichier.write_text(json.dumps({"articles": articles}), encoding="utf-8")
            resultat = selections.charger(racine, {}, {})["0000087004327"]
            self.assertEqual(resultat["conditionnement"], 7.0)
            self.assertEqual(resultat["offre"], articles[0]["offres"][0])
            self.assertTrue(any("plusieurs articles" in a for a in resultat["avertissements"]))
            fichier.write_text("{invalide", encoding="utf-8")
            with self.assertRaises(json.JSONDecodeError):
                selections.charger(racine, {}, {})

    def test_charger_lit_racine_sans_ecrire_et_sans_cache(self):
        selections = module("conditionnements.py")
        self.assertTrue(hasattr(selections, "charger"), "API charger manquante")
        with tempfile.TemporaryDirectory() as repertoire:
            racine = Path(repertoire)
            (racine / "donnees").mkdir()
            fichier = racine / "donnees/cadencier-du-jour.json"
            config = {"overrides": {"amandine": {"conditionnement": 8}}}
            mercalys = {"orange": {"CONDIT.BASE": 1}, "absent": {"CONDIT.BASE": 6}}
            avant_config = json.dumps(config)
            avant_mercalys = json.dumps(mercalys)
            resultat = selections.charger(racine, config, mercalys)
            self.assertEqual(set(resultat), {"orange", "absent"})
            self.assertEqual(resultat["absent"]["conditionnement"], 6.0)
            self.assertFalse(fichier.exists())
            self.assertEqual(list((racine / "donnees").iterdir()), [])
            articles = [
                {"article": "orange", "nom": "ORANGE DESSERT VRAC", "offres": [offre(8, 1.79)]},
                {"article": "amandine", "nom": "PDT PRINCESSE AMANDINE 2KG", "offres": [offre(65, 2), offre(8, 3)]},
                {"article": None, "nom": "INCONNU", "offres": [offre(4)]},
            ]
            fichier.write_text(json.dumps({"articles": articles}), encoding="utf-8")
            avant = fichier.read_bytes()
            resultat = selections.charger(racine, config, mercalys)
            self.assertEqual(set(resultat), {"orange", "amandine", "absent"})
            self.assertEqual(resultat["orange"]["conditionnement"], 8.0)
            self.assertEqual(resultat["amandine"]["offre"], articles[1]["offres"][1])
            self.assertEqual(resultat["amandine"]["source_conditionnement"], "decision")
            self.assertEqual(fichier.read_bytes(), avant)
            self.assertEqual(json.dumps(config), avant_config)
            self.assertEqual(json.dumps(mercalys), avant_mercalys)
            self.assertEqual(list((racine / "donnees").iterdir()), [fichier])
            articles[0]["offres"][0]["par_colis"] = 9
            fichier.write_text(json.dumps({"articles": articles}), encoding="utf-8")
            self.assertEqual(selections.charger(racine, config, mercalys)["orange"]["conditionnement"], 9.0)


class PropositionTests(unittest.TestCase):
    def proposer(self, selections=None, surcharge=None, position=0, recente=True, date="2026-09-07"):
        prop = module("proposer-commande.py")
        self.assertIn("conditionnements", __import__("inspect").signature(prop.proposer).parameters,
                      "Injection des conditionnements manquante")
        return prop.proposer(
            date, {"orange": {"tauxPerte": 0.05, "saison": [8.43] * 366}},
            {"orange": {"position": position, "mesuree_le": date}},
            {"overrides": {"orange": surcharge or {}}}, {"orange": {"CONDIT.BASE": 1}},
            {"orange": date} if recente else {}, None, {}, conditionnements=selections)["lignes"]["orange"]

    def test_proposer_utilise_le_pcb_selectionne_et_garde_la_formule(self):
        selection = module("conditionnements.py").selectionner({"offres": [offre(8)]})
        ligne = self.proposer({"orange": selection})
        self.assertEqual(ligne["conditionnement"], 8.0)
        self.assertEqual(ligne["propose_colis"], 2.0)
        self.assertEqual(ligne["propose_unites"], 16.0)
        self.assertEqual(ligne["demande"], 17.747)
        self.assertEqual(self.proposer({"orange": selection}, recente=False)["propose_colis"], 3.0)
        self.assertEqual(self.proposer({"orange": selection}, position=-24)["propose_colis"], 5.0)
        self.assertEqual(self.proposer({"orange": selection}, surcharge={"promotion": True})["propose_colis"], 0.0)
        self.assertGreater(self.proposer({"orange": selection}, surcharge={"promotion": True},
                                       date="2026-09-11")["propose_colis"], 0.0)

    def test_priorite_decision_et_compatibilite_sans_mapping(self):
        selection = module("conditionnements.py").selectionner({"offres": [offre(8)]})
        self.assertEqual(self.proposer({"orange": selection}, surcharge={"conditionnement": 5})["conditionnement"], 5.0)
        self.assertEqual(self.proposer()["conditionnement"], 1.0)
        self.assertEqual(self.proposer(surcharge={"conditionnement": 6})["conditionnement"], 6.0)
        self.assertEqual(self.proposer({})["conditionnement"], 1.0)

    def test_mapping_malforme_refuse_avant_le_calcul(self):
        for valeur in [0, -8, True, float("nan"), float("inf"), "NaN", None]:
            with self.subTest(valeur=valeur), self.assertRaisesRegex(ValueError, "[Cc]onditionnement"):
                self.proposer({"orange": {"conditionnement": valeur}})


if __name__ == "__main__":
    unittest.main()
