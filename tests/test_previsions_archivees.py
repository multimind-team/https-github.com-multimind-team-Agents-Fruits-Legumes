"""Archives prospectives sur fichiers temporaires uniquement."""
from datetime import datetime
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "moteur"))
import previsions_archivees as archives
import pilotage


class PrevisionsArchiveesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="previsions-fixture-")
        self.addCleanup(self.temp.cleanup)
        self.d = Path(self.temp.name) / "donnees"
        self.d.mkdir()

    def proposition(self, q=12, **ligne):
        return {"genere_le": "1999-01-01", "date_commande": "2030-04-10", "lignes": [{
            "itm8": "A", "unite": "kg", "conditionnement": 10,
            "previsions_journalieres": {"2030-04-09": 80, "2030-04-10": 90, "2030-04-11": q}, **ligne}]}

    def test_futur_seulement_heure_reelle_pas_genere_le(self):
        r = archives.archiver(self.d, self.proposition(), datetime(2030, 4, 10, 22))
        self.assertEqual(r, {"ajoutes": 1, "ignores_passe": 2})
        lu = archives.lire(self.d)
        self.assertEqual(set(lu), {("A", "2030-04-11")})
        self.assertTrue(lu[("A", "2030-04-11")]["enregistre_le"].startswith("2030-04-10T22:"))

    def test_ajout_immuable_dernier_snapshot_sans_doublon(self):
        archives.archiver(self.d, self.proposition(12), datetime(2030, 4, 9, 12))
        carnet = self.d / "previsions/2030.jsonl"
        original = carnet.read_bytes()
        r = archives.archiver(self.d, self.proposition(12), datetime(2030, 4, 9, 13))
        self.assertEqual(r["ajoutes"], 0)
        self.assertEqual(carnet.read_bytes(), original)
        archives.archiver(self.d, self.proposition(15), datetime(2030, 4, 10, 23, 59))
        self.assertTrue(carnet.read_bytes().startswith(original))
        self.assertEqual(archives.lire(self.d)[("A", "2030-04-11")]["quantite"], 15)
        archives.archiver(self.d, self.proposition(99), datetime(2030, 4, 11, 0))
        self.assertEqual(archives.lire(self.d)[("A", "2030-04-11")]["quantite"], 15)

    def test_archive_tardive_falsifiee_refusee_et_quantite_non_finie(self):
        archives.archiver(self.d, self.proposition(), datetime(2030, 4, 10, 22))
        chemin = self.d / "previsions/2030.jsonl"
        item = json.loads(chemin.read_text(encoding="utf-8"))
        item["enregistre_le"] = "2030-04-11T00:00:00"
        chemin.write_text(json.dumps(item)+"\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "pendant ou après"):
            archives.lire(self.d)
        with self.assertRaisesRegex(ValueError, "non finie"):
            archives.archiver(self.d, self.proposition(float("inf")), datetime(2030, 4, 10, 22))

    def test_offres_secondaires_sans_double_archive(self):
        prop = self.proposition(12, article_stock="P", commande_groupe_portee_par="A")
        prop["lignes"].append({**prop["lignes"][0], "itm8": "B"})
        archives.archiver(self.d, prop, datetime(2030, 4, 10, 22))
        self.assertEqual(set(archives.lire(self.d)), {("P", "2030-04-11")})

    def test_lecture_absence_ne_cree_rien(self):
        avant = list(self.d.iterdir())
        self.assertEqual(archives.lire(self.d), {})
        self.assertEqual(list(self.d.iterdir()), avant)

    def test_pilotage_ne_compare_que_paires_observees_et_unites_identiques(self):
        archives.archiver(self.d, self.proposition(12), datetime(2030, 4, 10, 22))
        (self.d / "faits").mkdir()
        faits = [{"id": "a", "type": "vente", "article": "A", "date_source": "2030-04-11", "quantite": 10},
                 {"id": "b", "type": "vente", "article": "A", "date_source": "2030-04-12", "quantite": 50}]
        (self.d / "faits/2030.jsonl").write_text("\n".join(json.dumps(f) for f in faits)+"\n", encoding="utf-8")
        prop = self.proposition()
        (self.d / "proposition.json").write_text(json.dumps(prop), encoding="utf-8")
        r = pilotage.construire(self.d, article="A", aujourd_hui="2030-04-13")
        self.assertEqual(r["kpis"]["paires_previsions"], 1)
        self.assertEqual(r["kpis"]["conformite_previsions_pct"], 100)
        self.assertEqual(r["kpis"]["ventes_comparees_colis"], 1)
        self.assertEqual(r["kpis"]["previsions_comparees_colis"], 1.2)
        self.assertIsNone(r["kpis"]["conformite_commandes_pct"])
        self.assertEqual(r["article"]["chronologie"][-2]["previsions"], 12)
        self.assertIsNone(r["article"]["chronologie"][-1]["previsions"])
        prop["lignes"][0]["unite"] = "pièce"
        (self.d / "proposition.json").write_text(json.dumps(prop), encoding="utf-8")
        r = pilotage.construire(self.d, article="A", aujourd_hui="2030-04-13")
        self.assertEqual(r["kpis"]["paires_previsions"], 0)
        self.assertIsNone(r["kpis"]["previsions_colis"])
        self.assertTrue(any("unité ancienne" in x for x in r["limites"]))


if __name__ == "__main__":
    unittest.main()
