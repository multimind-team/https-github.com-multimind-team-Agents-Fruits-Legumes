"""Pipeline réel, pièces et sorties factices ; aucun sous-processus métier lancé."""
import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

MOTEUR = Path(__file__).resolve().parents[1] / "moteur"
sys.path.insert(0, str(MOTEUR))
spec = importlib.util.spec_from_file_location("traiter_courrier_tests", MOTEUR / "traiter-courrier.py")
courrier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(courrier)


class TraitementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.racine = Path(self.temp.name)
        self.appels = []

    def piece(self, nom, contenu=None):
        source = self.racine / "source" / nom
        source.parent.mkdir(exist_ok=True)
        source.write_bytes(contenu or nom.encode("utf-8"))
        return source

    def executer_factice(self, commande, **kwargs):
        # Échouer avant tout appel extérieur si le pipeline échappe à la fixture.
        self.assertTrue(Path(commande[2]).is_relative_to(self.racine))
        self.appels.append(commande)
        if Path(commande[2]).name == "filet-de-securite.py":
            cible = self.racine / "donnees/fraicheur.json"
            cible.parent.mkdir(exist_ok=True)
            precedent = cible.stat().st_mtime_ns if cible.exists() else 0
            cible.write_text(json.dumps({"etat": "a-jour", "calculs_en_echec": []}), encoding="utf-8")
            # Le sous-processus est factice et finit dans le même tick Windows.
            # Matérialiser sa nouvelle génération sans attendre l'horloge réelle.
            nouveau = max(cible.stat().st_mtime_ns, precedent + 1_000_000_000)
            os.utime(cible, ns=(nouveau, nouveau))
        return subprocess.CompletedProcess(commande, 0, json.dumps({"statut": "ok", "a_verifier": []}), "")

    def traiter(self, pieces, execution=None, mail="mail-test", date="2026-09-07", simuler=False):
        argv = ["traiter-courrier.py", "--racine", str(self.racine), "--mail-id", mail,
                "--date", date, "--expediteur", "pdv", *map(str, pieces)]
        if simuler:
            argv.append("--simuler")
        sortie = io.StringIO()
        with patch.object(sys, "argv", argv), contextlib.redirect_stdout(sortie), \
                patch.object(courrier.subprocess, "run", side_effect=execution or self.executer_factice):
            retour = courrier.main()
        return retour, json.loads(sortie.getvalue())

    def test_rejoue_apres_echec_recalcul_sans_reindexer_les_pieces(self):
        pieces = [self.piece("Vente-07.09.2026.xlsx")]

        def echec_recalcul(commande, **kwargs):
            reponse = self.executer_factice(commande, **kwargs)
            if Path(commande[2]).name == "filet-de-securite.py":
                reponse.returncode = 2
            return reponse

        retour, _ = self.traiter(pieces, execution=echec_recalcul)
        self.assertNotEqual(retour, 0)
        index = self.racine / "donnees/courrier/index.jsonl"
        avant = index.read_bytes()
        self.appels.clear()
        retour, resultat = self.traiter(pieces)
        self.assertEqual([Path(c[2]).name for c in self.appels],
                         ["integrer-fichiers.py", "filet-de-securite.py", "note-du-matin.py"])
        self.assertEqual(retour, 0)
        self.assertEqual(resultat["rangement"]["nouveaux"], 0)
        self.assertEqual(resultat["rangement"]["doublons"], 1)
        self.assertEqual(index.read_bytes(), avant)

    def test_donnees_en_retard_produit_la_note_sans_succes_global(self):
        pieces = [self.piece("Vente-07.09.2026.xlsx")]

        def recalcul_en_retard(commande, **kwargs):
            reponse = self.executer_factice(commande, **kwargs)
            if Path(commande[2]).name == "filet-de-securite.py":
                (self.racine / "donnees/fraicheur.json").write_text(json.dumps({
                    "etat": "donnees-en-retard", "calculs_en_echec": []}), encoding="utf-8")
                reponse.returncode = 1
            return reponse

        retour, resultat = self.traiter(pieces, execution=recalcul_en_retard)
        self.assertEqual(Path(self.appels[-1][2]).name, "note-du-matin.py")
        self.assertEqual(retour, 1)
        self.assertEqual(resultat["statut"], "donnees-en-retard")
        self.assertFalse(resultat["succes"])
        self.assertEqual(resultat["resultats"][1]["statut"], "donnees-en-retard")

    def test_timeout_import_garde_un_resultat_echec_et_tente_la_note(self):
        pieces = [self.piece("Vente-07.09.2026.xlsx")]

        def import_interrompu(commande, **kwargs):
            if Path(commande[2]).name == "integrer-fichiers.py":
                self.appels.append(commande)
                raise subprocess.TimeoutExpired(commande, 900, output=b"import interrompu")
            return self.executer_factice(commande, **kwargs)

        try:
            retour, resultat = self.traiter(pieces, execution=import_interrompu)
        except subprocess.TimeoutExpired:
            self.fail("Le timeout doit produire un JSON d'echec, pas abandonner la note")
        self.assertEqual(retour, 2)
        self.assertEqual(resultat["statut"], "echec-technique")
        self.assertFalse(resultat["succes"])
        self.assertEqual([Path(c[2]).name for c in self.appels],
                         ["integrer-fichiers.py", "note-du-matin.py"])
        self.assertEqual(resultat["resultats"][1]["statut"], "non-execute")
        self.assertEqual(resultat["resultats"][0]["code"], 124)
        index = (self.racine / "donnees/courrier/index.jsonl").read_bytes()
        retour, _ = self.traiter(pieces)
        self.assertEqual(retour, 0)
        self.assertEqual((self.racine / "donnees/courrier/index.jsonl").read_bytes(), index)

    def test_factures_et_promotions_restent_a_verifier_meme_sur_un_doublon(self):
        pieces = [self.piece("Facture-TerreAzur.pdf"), self.piece("Prospectus-Intermarche.pdf"),
                  self.piece("photo-inconnue.png")]
        for _ in range(2):
            retour, resultat = self.traiter(pieces)
            self.assertEqual(retour, 3)  # Rangement réussi, pièces à vérifier explicitement.
            self.assertEqual(resultat["statut"], "a-verifier")
            self.assertFalse(resultat["succes"])
            self.assertEqual(self.appels, [])
            self.assertIn("extraire", resultat["facture_directe"])
            self.assertEqual(len(resultat["a_verifier"]), 3)

    def test_import_interrompu_apres_ecriture_ne_redouble_pas_les_faits_au_rejeu(self):
        spec_import = importlib.util.spec_from_file_location("import_fixture_courrier", MOTEUR / "integrer-fichiers.py")
        importeur = importlib.util.module_from_spec(spec_import)
        spec_import.loader.exec_module(importeur)
        # Charger le lecteur courant : une suite longue peut avoir importé une
        # version antérieure de faits avant les modifications d'un autre agent.
        spec_faits = importlib.util.spec_from_file_location("faits_fixture_courrier", MOTEUR / "faits.py")
        carnet = importlib.util.module_from_spec(spec_faits)
        spec_faits.loader.exec_module(carnet)
        pieces = [self.piece("Vente-07.09.2026.xlsx")]
        fait = {"id": "vente:2026-09-07:TEST:0", "type": "vente", "article": "TEST",
                "date_source": "2026-09-07", "date_effet": "2026-09-07", "quantite": 2}
        tentatives = []

        def importer_fixture(commande, **kwargs):
            if Path(commande[2]).name == "integrer-fichiers.py":
                # Seul le writer réel est exercé, sous une racine temporaire.
                with patch.object(importeur, "DOSSIER_FAITS", self.racine / "faits-fixture"), \
                        patch.dict(sys.modules, {"faits": carnet}):
                    nouveaux, deja = importeur.ecrire([fait, fait])
                tentatives.append((len(nouveaux), deja))
                if len(tentatives) == 1:
                    raise subprocess.TimeoutExpired(commande, 900)
            return self.executer_factice(commande, **kwargs)

        retour, _ = self.traiter(pieces, execution=importer_fixture)
        self.assertEqual(retour, 2)
        index = (self.racine / "donnees/courrier/index.jsonl").read_bytes()
        for _ in range(2):
            retour, _ = self.traiter(pieces, execution=importer_fixture)
            self.assertEqual(retour, 0)
        self.assertEqual(tentatives, [(1, 1), (0, 2), (0, 2)])
        faits = [json.loads(ligne) for ligne in (self.racine / "faits-fixture/2026.jsonl").read_text().splitlines()]
        self.assertEqual(faits, [fait])
        self.assertEqual((self.racine / "donnees/courrier/index.jsonl").read_bytes(), index)

    def test_retour_zero_du_filet_ne_masque_pas_un_calcul_en_echec(self):
        pieces = [self.piece("Vente-07.09.2026.xlsx")]

        def calcul_en_echec(commande, **kwargs):
            reponse = self.executer_factice(commande, **kwargs)
            if Path(commande[2]).name == "filet-de-securite.py":
                (self.racine / "donnees/fraicheur.json").write_text(json.dumps({
                    "etat": "a-jour", "calculs_en_echec": [{"calcul": "agregats.py"}]}), encoding="utf-8")
            return reponse

        retour, resultat = self.traiter(pieces, execution=calcul_en_echec)
        self.assertEqual(retour, 2)
        self.assertEqual(resultat["statut"], "echec-technique")
        self.assertFalse(resultat["succes"])
        self.assertEqual(Path(self.appels[-1][2]).name, "note-du-matin.py")

    def test_ancien_constat_de_retard_ne_masque_pas_une_panne_du_filet(self):
        pieces = [self.piece("Vente-07.09.2026.xlsx")]
        (self.racine / "donnees").mkdir()
        (self.racine / "donnees/fraicheur.json").write_text(json.dumps({
            "etat": "donnees-en-retard", "calculs_en_echec": []}), encoding="utf-8")

        def panne_sans_nouveau_constat(commande, **kwargs):
            if Path(commande[2]).name == "filet-de-securite.py":
                self.appels.append(commande)
                return subprocess.CompletedProcess(commande, 1, "panne fixture", "")
            return self.executer_factice(commande, **kwargs)

        retour, resultat = self.traiter(pieces, execution=panne_sans_nouveau_constat)
        self.assertEqual(retour, 2)
        self.assertEqual(resultat["statut"], "echec-technique")
        self.assertFalse(resultat["succes"])
        self.assertEqual(Path(self.appels[-1][2]).name, "note-du-matin.py")

    def test_panne_de_la_note_ne_devient_pas_un_succes_global(self):
        pieces = [self.piece("Vente-07.09.2026.xlsx")]

        def panne_note(commande, **kwargs):
            reponse = self.executer_factice(commande, **kwargs)
            if Path(commande[2]).name == "note-du-matin.py":
                reponse.returncode = 3
            return reponse

        retour, resultat = self.traiter(pieces, execution=panne_note)
        self.assertEqual(retour, 2)
        self.assertFalse(resultat["succes"])
        self.assertEqual(resultat["resultats"][-1]["code"], 3)

    def test_executable_absent_est_un_echec_technique_avec_note_tentee(self):
        pieces = [self.piece("Vente-07.09.2026.xlsx")]
        retour, resultat = self.traiter(pieces, execution=FileNotFoundError("py absent fixture"))
        self.assertEqual(retour, 2)
        self.assertFalse(resultat["succes"])
        self.assertEqual(resultat["resultats"][0]["code"], 127)
        self.assertEqual(Path(resultat["resultats"][-1]["commande"][2]).name, "note-du-matin.py")
        self.assertEqual(resultat["resultats"][-1]["code"], 127)

    def test_mail_transfere_mixte_reprend_les_dossiers_archives_et_nouveaux(self):
        vente = self.piece("Vente-07.09.2026.xlsx")
        self.traiter([vente])
        index = self.racine / "donnees/courrier/index.jsonl"
        avant = index.read_bytes()
        self.appels.clear()
        retour, resultat = self.traiter([
            self.piece("Prospectus-Intermarche.pdf"), vente,
            self.piece("Livraison-08.09.2026.xlsx")], mail="mail-transfert", date="2026-09-08")
        imports = [c for c in self.appels if Path(c[2]).name == "integrer-fichiers.py"]
        self.assertEqual([Path(c[3]) for c in imports],
                         [self.racine / "donnees/courrier/2026-09-07-pdv/Vente-07.09.2026.xlsx",
                          self.racine / "donnees/courrier/2026-09-08-pdv/Livraison-08.09.2026.xlsx"])
        self.assertEqual(retour, 3)
        self.assertEqual(resultat["rangement"]["doublons"], 1)
        self.assertTrue(index.read_bytes().startswith(avant))
        self.assertEqual(len(index.read_bytes().splitlines()), 3)
        self.assertEqual(sum(Path(c[2]).name == "filet-de-securite.py" for c in self.appels), 1)

    def test_piece_absente_signale_echec_rangement_et_tente_une_note(self):
        try:
            retour, resultat = self.traiter([self.racine / "introuvable.xlsx"])
        except OSError:
            self.fail("Un échec de rangement doit laisser un compte rendu et tenter la note")
        self.assertEqual(retour, 2)
        self.assertFalse(resultat["succes"])
        self.assertEqual(resultat["resultats"][0]["etape"], "rangement")
        self.assertEqual([Path(c[2]).name for c in self.appels], ["note-du-matin.py"])

    def test_transfert_renomme_rejoue_le_type_archive_plutot_que_le_nom_du_cache(self):
        vente = self.piece("Vente-07.09.2026.xlsx", b"export identique")
        self.traiter([vente])
        index = (self.racine / "donnees/courrier/index.jsonl").read_bytes()
        self.appels.clear()
        retour, resultat = self.traiter([self.piece("transfert.xlsx", b"export identique")], mail="transfert")
        self.assertEqual([Path(c[2]).name for c in self.appels],
                         ["integrer-fichiers.py", "filet-de-securite.py", "note-du-matin.py"])
        self.assertEqual(resultat["rangement"]["classes"], {"mouvement": 1})
        self.assertEqual(retour, 0)
        self.assertEqual((self.racine / "donnees/courrier/index.jsonl").read_bytes(), index)

    def test_lot_mixte_prospectus_en_premier_cible_le_dossier_des_mouvements(self):
        pieces = [self.piece("Prospectus-Intermarche.pdf"),
                  self.piece("Vente-07.09.2026.xlsx"), self.piece("Livraison-07.09.2026.xlsx")]
        retour, resultat = self.traiter(pieces)
        imports = [c for c in self.appels if Path(c[2]).name == "integrer-fichiers.py"]
        self.assertEqual([Path(c[3]) for c in imports], [
            self.racine / "donnees/courrier/2026-09-07-pdv/Vente-07.09.2026.xlsx",
            self.racine / "donnees/courrier/2026-09-07-pdv/Livraison-07.09.2026.xlsx"])
        self.assertEqual(retour, 3)
        self.assertEqual(resultat["rangement"]["nouveaux"], 3)


if __name__ == "__main__":
    unittest.main()
