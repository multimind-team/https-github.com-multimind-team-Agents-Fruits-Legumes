"""Régressions métier de l'audit, exclusivement sur des fixtures isolées."""
import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

MOTEUR = Path(__file__).resolve().parents[1] / "moteur"
sys.path.insert(0, str(MOTEUR))


def charger(fichier):
    spec = importlib.util.spec_from_file_location("audit_" + fichier.replace("-", "_"), MOTEUR / fichier)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


POSITION = charger("calculer-position.py")
GENERER = charger("generer-proposition.py")
PROP = charger("proposer-commande.py")
IMPORT = charger("integrer-fichiers.py")


def fait(identifiant, type_fait, jour, quantite, **champs):
    return {"id": identifiant, "type": type_fait, "article": "123", "date_source": jour,
            "date_effet": jour, "quantite": quantite, **champs}


class RejeuComptagesTests(unittest.TestCase):
    def calculer(self, faits):
        with patch.object(POSITION, "lire_faits", return_value=iter(faits)):
            return POSITION.calculer()["123"]

    def test_ancienne_mesure_ajoutee_apres_la_mesure_du_soir_ne_gagne_pas(self):
        resultat = self.calculer([
            fait("soir", "comptage", "2026-09-07", 30, horodatage="2026-09-07T19:00:00"),
            fait("matin", "comptage", "2026-09-07", 20, horodatage="2026-09-07T08:00:00"),
            fait("r1", "correction-comptage", "2026-09-07", 25, cible_id="matin",
                 horodatage="2026-09-08T19:00:00"),
        ])
        self.assertEqual(resultat["position"], 30)

    def test_corrections_repetent_la_racine_sans_reactiver_un_ancien_comptage(self):
        resultat = self.calculer([
            fait("c1", "comptage", "2026-09-07", 20, horodatage="2026-09-07T08:00:00"),
            fait("r1", "correction-comptage", "2026-09-07", 25, cible_id="c1"),
            fait("r2", "correction-comptage", "2026-09-07", 27, cible_id="c1"),
            fait("v1", "vente", "2026-09-07", 3),
        ])
        self.assertEqual(resultat["position"], 24)
        resultat = self.calculer([
            fait("c1", "comptage", "2026-09-07", 20),
            fait("c2", "comptage", "2026-09-08", 40),
            fait("r1", "correction-comptage", "2026-09-09", 25, cible_id="c1"),
        ])
        self.assertEqual(resultat["position"], 40)

    def test_corriger_un_comptage_matinal_le_soir_garde_le_moment_initial(self):
        resultat = self.calculer([
            fait("c1", "comptage", "2026-09-07", 20, horodatage="2026-09-07T08:00:00"),
            fait("v1", "vente", "2026-09-07", 3),
            fait("r1", "correction-comptage", "2026-09-07", 25, cible_id="c1",
                 horodatage="2026-09-08T19:00:00"),
        ])
        self.assertEqual(resultat["position"], 22)
        self.assertEqual(resultat["moment_mesure"], "matin")


class DatesCommandeTests(unittest.TestCase):
    def test_etat_distingue_mesure_du_soir_et_livraison_du_matin(self):
        for mouvements, attendue in [
            ([fait("c", "comptage", "2026-09-07", 20), fait("l", "livraison", "2026-09-09", 5)], "2026-09-08"),
            ([fait("c", "comptage", "2026-09-09", 20, horodatage="2026-09-09T08:00:00")], "2026-09-08"),
            ([fait("c", "comptage", "2026-09-09", 20, horodatage="2026-09-09T19:00:00")], "2026-09-09"),
        ]:
            with self.subTest(base=attendue, faits=mouvements), tempfile.TemporaryDirectory() as repertoire:
                racine = Path(repertoire)
                (racine / "donnees").mkdir()
                with patch.object(POSITION, "RACINE", racine), \
                     patch.object(POSITION, "lire_faits", side_effect=lambda: iter(mouvements)), \
                     patch.object(POSITION.agregats, "charger", return_value={"date_reference": "2026-09-04"}), \
                     patch.object(POSITION, "lire_conditionnements", return_value={}):
                    POSITION.main()
                etat = json.loads((racine / "donnees/etat.json").read_text(encoding="utf-8"))
                self.assertEqual(etat.get("date_base_commande"), attendue)

    def test_livraison_du_matin_ne_bascule_pas_la_commande_au_lendemain(self):
        # Un état au 09/09 MATIN, pas une clôture du 09/09.
        etat = {"calcule_jusquau": "2026-09-09", "date_base_commande": "2026-09-08"}
        base = GENERER.date_de_calcul(etat, "2026-09-04", maintenant=datetime(2026, 9, 9, 6, 27))
        self.assertEqual(PROP.prochain_jour_valide(base, ()), "2026-09-09")

    def test_apres_neuf_heures_trente_le_cycle_courant_passe_au_lendemain(self):
        etat = {"calcule_jusquau": "2026-09-09", "date_base_commande": "2026-09-08"}
        base = GENERER.date_de_calcul(etat, "2026-09-04", maintenant=datetime(2026, 9, 9, 9, 30))
        self.assertEqual(PROP.prochain_jour_valide(base, ()), "2026-09-10")

    def test_un_maximum_de_faits_sans_phase_ne_prouve_pas_une_journee_close(self):
        self.assertEqual(GENERER.date_de_calcul({"calcule_jusquau": "2026-09-09"}, "2026-09-04"),
                         "2026-09-04")


class GenerationPropositionTests(unittest.TestCase):
    def generer(self, positions, config=None, publication_echoue=False):
        with tempfile.TemporaryDirectory() as repertoire:
            racine = Path(repertoire)
            (racine / "donnees").mkdir()
            etat = {"calcule_jusquau": "2026-09-09", "date_base_commande": "2026-09-08", "articles": positions}
            (racine / "donnees/etat.json").write_text(json.dumps(etat), encoding="utf-8")
            mercalys = {c: {"CODE ITM": c, "LIBELLE": c, "CONDIT.BASE": 1} for c in positions}
            moyennes = {c: {"saison": [1] * 366, "tauxPerte": 0} for c in positions}
            agr = {"date_reference": "2026-09-04", "articles": {},
                   "audit_faits": {"doublons_ignores": 1, "doublons": [{"id": "copie"}]}}
            class DateFigee(datetime):
                @classmethod
                def now(cls):
                    return cls(2026, 9, 9, 6, 27)

            with patch.object(GENERER, "RACINE", racine), \
                 patch.object(GENERER, "datetime", DateFigee), \
                 patch.object(GENERER.agregats, "charger", return_value=agr), \
                 patch.object(GENERER.regles, "charger", return_value=config or {"overrides": {}}), \
                 patch.object(GENERER.catalogue, "articles", return_value=mercalys), \
                 patch.object(GENERER.ferie, "dates_fermees", return_value=set()), \
                 patch.object(GENERER.ferie, "facteur", return_value=1), \
                 patch.object(GENERER.calendrier, "charger", return_value={"feries": {}}), \
                 patch.object(GENERER, "meteo_prevue", return_value={}), \
                 patch.object(GENERER.calc, "construire_moyennes", return_value=moyennes):
                if publication_echoue:
                    cible = racine / "donnees/proposition.json"
                    ancien = '{"ancienne": true}'
                    cible.write_text(ancien, encoding="utf-8")
                    with patch('os.replace', side_effect=OSError('publication interrompue')):
                        with self.assertRaisesRegex(OSError, 'publication interrompue'):
                            GENERER.main()
                    self.assertEqual(cible.read_text(encoding="utf-8"), ancien)
                    self.assertEqual(sorted(p.name for p in cible.parent.iterdir()
                                            if p.name != '.operations.lock'), ['etat.json', 'proposition.json'])
                else:
                    GENERER.main()
            return json.loads((racine / "donnees/proposition.json").read_text(encoding="utf-8"))

    def test_position_moins_dix_est_le_seuil_et_la_mesure_recente_est_transmise(self):
        prop = self.generer({"123": {"position": -9.9, "mesuree_le": "2026-08-01", "moment_mesure": "soir"}})
        self.assertFalse(prop["lignes"][0]["position_bloquee"])
        prop = self.generer({"123": {"position": -10, "mesuree_le": "2026-08-01", "moment_mesure": "soir"}})
        self.assertTrue(prop["lignes"][0]["position_bloquee"])
        prop = self.generer({"123": {"position": -10, "mesuree_le": "2026-09-07", "moment_mesure": "soir"}})
        self.assertFalse(prop["lignes"][0]["position_bloquee"])
        self.assertGreater(prop["lignes"][0]["propose_colis"], 0)

    def test_echec_publication_preserve_la_derniere_proposition_valide(self):
        self.generer({"123": {"position": 12, "mesuree_le": "2026-09-09", "moment_mesure": "matin"}}, publication_echoue=True)

    def test_proposition_transmet_le_bilan_des_doublons_sans_les_cacher(self):
        prop = self.generer({"123": {"position": 12, "mesuree_le": "2026-09-09", "moment_mesure": "matin"}})
        self.assertEqual(prop.get("audit_faits", {}).get("doublons_ignores"), 1)

    def test_livraison_recente_ne_prouve_pas_les_sorties_depuis_un_comptage(self):
        prop = self.generer({"123": {"position": 12, "mesuree_le": "2026-09-07", "moment_mesure": "soir"}})
        self.assertEqual(prop["date_commande"], "2026-09-09")
        self.assertEqual(prop.get("date_stock_verifiee"), "2026-09-07")
        self.assertEqual(prop["date_stock"], "2026-09-09")

    def test_les_produits_sans_position_ne_vieillissent_pas_le_stock_compte(self):
        prop = self.generer({"123": {"position": 12, "mesuree_le": "2026-09-09", "moment_mesure": "matin"},
                             "nom:INCONNU": {"position": None, "mesuree_le": None}})
        self.assertEqual(prop.get("date_stock_verifiee"), "2026-09-08")
        self.assertEqual(prop.get("couverture_stock", {}).get("articles_sans_position"), 1)

    def test_un_comptage_du_matin_couvre_la_veille_mais_pas_tout_le_rayon(self):
        prop = self.generer({"123": {"position": 12, "mesuree_le": "2026-09-09", "moment_mesure": "matin"}})
        self.assertEqual(prop.get("date_stock_verifiee"), "2026-09-08")
        prop = self.generer({"123": {"position": 12, "mesuree_le": "2026-09-09", "moment_mesure": "matin"},
                             "456": {"position": 20, "mesuree_le": "2026-09-07", "moment_mesure": "soir"}})
        self.assertEqual(prop.get("date_stock_verifiee"), "2026-09-07")


class NoteMetierTests(unittest.TestCase):
    def test_ne_signale_pas_position_perdue_avant_moins_dix_colis(self):
        note = charger("note-du-matin.py")
        for position, attendue in [(-9.9, False), (-10, True)]:
            with self.subTest(position=position), tempfile.TemporaryDirectory() as repertoire:
                racine = Path(repertoire)
                (racine / "donnees").mkdir()
                (racine / "donnees/etat.json").write_text(json.dumps({"articles": {"123": {"position": position}}}), encoding="utf-8")
                with patch.object(note, "RACINE", racine), \
                     patch.object(note.agregats, "charger", return_value={"date_reference": "2026-09-08", "articles": {"123": {}}}), \
                     patch.object(note.regles, "charger", return_value={"overrides": {}}), \
                     patch.object(note.catalogue, "articles", return_value={"123": {"CODE ITM": "123", "CONDIT.BASE": 1}}), \
                     patch.object(note, "lire_faits", return_value=[]):
                    note.main()
                texte = (racine / "donnees/note-du-matin.json").read_text(encoding="utf-8")
                self.assertEqual("position trop basse" in texte, attendue)


class ValidationImportsTests(unittest.TestCase):
    def convertir(self, nom, colonnes, lignes, entete=()):
        alertes = []
        with patch.object(IMPORT, "lire_tableau", return_value=(colonnes, lignes, entete)):
            resultat = IMPORT.convertir(Path(nom), {}, {"0000087001234"},
                                        lambda *args: alertes.append(args))
        return resultat, alertes

    def test_ecarte_le_jour_de_generation_incomplet_sans_decaler_les_ids(self):
        resultat, alertes = self.convertir("Vente-09-09-2026.xlsx",
            ["ITM8 Prio", "Date", "Quantité"],
            [["0000087001234", "09/09/2026", 3], ["0000087001234", "08/09/2026", 4]],
            [["PDV: 11768 Date : 09/09/2026 Heure : 13:38:00"]])
        self.assertEqual(len(resultat), 1)
        self.assertEqual(resultat[0]["date_effet"], "2026-09-08")
        self.assertTrue(resultat[0]["id"].endswith(":1"))
        self.assertTrue(any(a[0] == "journee-incomplete" for a in alertes))

    def test_refuse_les_dates_impossibles_et_ne_tronque_pas_un_suffixe_invalide(self):
        for valeur in ["31/02/2026", "2026-02-30", "2026-09-08invalide"]:
            with self.subTest(date=valeur):
                resultat, alertes = self.convertir("Vente-09-09-2026.xlsx",
                    ["ITM8 Prio", "Date", "Quantité"], [["0000087001234", valeur, 3]])
                self.assertEqual(resultat, [])
                self.assertTrue(alertes)

    def test_ne_devine_jamais_un_conditionnement_de_livraison(self):
        for valeur in [None, "", "illisible", 0, -2, float("nan")]:
            with self.subTest(conditionnement=valeur):
                resultat, alertes = self.convertir("Livraison-08-09-2026.xlsx",
                    ["Code ITM", "Qté cmdée (nbre colis)", "Cond. de base"],
                    [["0000087001234", 2, valeur]])
                self.assertEqual(resultat, [])
                self.assertTrue(alertes)
        resultat, alertes = self.convertir("Livraison-08-09-2026.xlsx",
            ["Code ITM", "Qté cmdée (nbre colis)"], [["0000087001234", 2]])
        self.assertEqual(resultat, [])
        self.assertTrue(alertes)

    def test_refuse_quantites_non_finies_et_manquantes(self):
        for valeur in [float("nan"), float("inf"), "NaN", None, "", True]:
            with self.subTest(valeur=valeur):
                resultat, alertes = self.convertir("Vente-09-09-2026.xlsx",
                    ["ITM8 Prio", "Date", "Quantité"], [["0000087001234", "08/09/2026", valeur]])
                self.assertEqual(resultat, [])
                self.assertTrue(alertes)


class EcritureImportsTests(unittest.TestCase):
    def test_un_conflit_identifiant_bloque_tout_le_lot_avant_ecriture(self):
        for simuler in (False, True):
            with self.subTest(simuler=simuler), tempfile.TemporaryDirectory() as repertoire:
                dossier = Path(repertoire)
                with patch.object(IMPORT, "DOSSIER_FAITS", dossier):
                    original = fait("v1", "vente", "2026-09-07", 3)
                    IMPORT.ecrire([original])
                    fichier = dossier / "2026.jsonl"
                    avant = fichier.read_bytes()
                    with self.assertRaisesRegex(ValueError, 'v1'):
                        IMPORT.ecrire([fait("v2", "vente", "2026-09-07", 5), dict(original, quantite=4)], simuler)
                    self.assertEqual(fichier.read_bytes(), avant)

    def test_un_conflit_dans_le_lot_ne_devient_pas_un_doublon_silencieux(self):
        with tempfile.TemporaryDirectory() as repertoire:
            dossier = Path(repertoire)
            with patch.object(IMPORT, "DOSSIER_FAITS", dossier):
                with self.assertRaisesRegex(ValueError, 'v1'):
                    IMPORT.ecrire([fait("v1", "vente", "2026-09-07", 3), fait("v1", "vente", "2026-09-07", 4)])
                self.assertEqual([p for p in dossier.iterdir() if p.name != ".operations.lock"], [])

    def test_un_doublon_dans_le_meme_lot_n_est_ajoute_qu_une_fois(self):
        with tempfile.TemporaryDirectory() as repertoire:
            with patch.object(IMPORT, "DOSSIER_FAITS", Path(repertoire)):
                f = fait("v1", "vente", "2026-09-07", 3)
                nouveaux, deja = IMPORT.ecrire([f, dict(f)])
                self.assertEqual((len(nouveaux), deja), (1, 1))
                fichier = Path(repertoire) / "2026.jsonl"
                original = fichier.read_bytes()
                self.assertEqual(IMPORT.ecrire([f]), ([], 1))
                self.assertEqual(fichier.read_bytes(), original)
                self.assertEqual(len(fichier.read_text(encoding="utf-8").splitlines()), 1)


class SimulationImportsTests(unittest.TestCase):
    def test_simuler_ne_modifie_pas_le_dernier_compte_rendu(self):
        with tempfile.TemporaryDirectory() as repertoire:
            racine = Path(repertoire)
            fichier = racine / "Vente-08-09-2026.xlsx"
            fichier.touch()
            compte = racine / "dernier-import.json"
            compte.write_text('{"precedent": true}', encoding="utf-8")
            avant = compte.read_bytes()
            with patch.object(IMPORT, "COMPTE_RENDU", compte), \
                 patch.object(IMPORT, "DOSSIER_FAITS", racine / "faits"), \
                 patch.object(IMPORT.regles, "charger", return_value={"groupes": {}}), \
                 patch.object(IMPORT.catalogue, "articles", return_value={}), \
                 patch.object(IMPORT, "convertir", return_value=[fait("v1", "vente", "2026-09-07", 3)]), \
                 patch.object(sys, "argv", ["integrer-fichiers.py", str(fichier), "--simuler"]):
                self.assertEqual(IMPORT.main(), 0)
            self.assertEqual(compte.read_bytes(), avant)
            self.assertFalse((racine / "faits").exists())


if __name__ == "__main__":
    unittest.main()
