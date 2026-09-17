"""F01 : HTTP réel → carnet append-only → moteur inchangé, uniquement en copie."""
import hashlib
import http.client
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from unittest.mock import patch


RACINE = Path(__file__).resolve().parents[1]
CODE = "0000087001234"
JOUR = "2026-09-10"


def empreintes_production():
    chemins = {p for p in (RACINE / "donnees").glob("*.json") if not p.name.startswith(".")}
    for dossier in ("donnees", "donnees/faits", "donnees/journaux"):
        chemins.update(p for p in (RACINE / dossier).glob("*.jsonl") if not p.name.startswith("."))
    return {p.relative_to(RACINE).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(chemins)}


class ReComptageAPIChaineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.production_avant = empreintes_production()

    @classmethod
    def tearDownClass(cls):
        if empreintes_production() != cls.production_avant:
            raise AssertionError("Les données de production ont changé pendant les tests F01")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="recomptage-api-chaine-")
        self.addCleanup(self.temp.cleanup)
        self.racine = Path(self.temp.name).resolve()
        self.assertFalse(self.racine.is_relative_to(RACINE))
        self.moteur = self.racine / "moteur"
        self.moteur.mkdir()
        for chemin in (RACINE / "moteur").glob("*.py"):
            shutil.copy2(chemin, self.moteur / chemin.name)
        donnees = self.racine / "donnees"
        (donnees / "faits").mkdir(parents=True)
        self.carnet = donnees / "faits/2026.jsonl"
        self.carnet.touch()
        article = {"itm8": CODE, "libelle": "ARTICLE FICTIF F01",
                   "conditionnement": 1, "unite": "Pièce"}
        for nom, contenu in {
            "articles.json": {"articles": [article]},
            "catalogue.json": {"articles": {CODE: {
                "CODE ITM": CODE, "LIBELLE": article["libelle"], "CONDIT.BASE": 1}}},
            "agregats.json": {"date_reference": "2026-09-09", "articles": {}},
        }.items():
            (donnees / nom).write_text(json.dumps(contenu), encoding="utf-8")
        chemin_python = sys.path[:]
        self.addCleanup(lambda: sys.path.__setitem__(slice(None), chemin_python))
        spec = importlib.util.spec_from_file_location("serveur_recomptage_chaine", self.moteur / "serveur.py")
        self.serveur = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.serveur)

        class HeureFigee(datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2026, 9, 10, 23, 0, 0, tzinfo=tz)

        horloge = patch.object(self.serveur, "datetime", HeureFigee)
        horloge.start()
        self.addCleanup(horloge.stop)
        # Seul l'ordonnanceur asynchrone est remplacé : le vrai moteur est
        # exécuté explicitement après chaque acquittement dans la même copie.
        recalcul = patch.object(self.serveur, "recalculer_en_arriere_plan")
        self.recalcul = recalcul.start()
        self.addCleanup(recalcul.stop)
        self.http = self.serveur.ServeurHTTP(("127.0.0.1", 0), self.serveur.Gestionnaire)
        self.fil = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.fil.start()
        self.addCleanup(self.fermer)

    def fermer(self):
        self.http.shutdown()
        self.http.server_close()
        self.fil.join(5)

    def releve(self, colis, heure, **extra):
        # Charge exacte des deux UI, y compris l'ancien ID article/jour.
        return {"id": f"comptage:{JOUR}:{CODE}:saisie", "itm8": CODE,
                "date": JOUR, "colis": colis, "conditionnement": 1,
                "saisi_le": JOUR + "T" + heure, **extra}

    def envoyer(self, *releves):
        connexion = http.client.HTTPConnection("127.0.0.1", self.http.server_port, timeout=5)
        self.addCleanup(connexion.close)
        origine = f"http://127.0.0.1:{self.http.server_port}"
        connexion.request("POST", "/api/comptages", json.dumps({"comptages": releves}),
                          {"Content-Type": "application/json", "Origin": origine,
                           "Sec-Fetch-Site": "same-origin"})
        reponse = connexion.getresponse()
        contenu = json.loads(reponse.read())
        self.assertEqual(reponse.status, 200, contenu)
        return contenu

    def ajouter_faits(self, *faits):
        with self.carnet.open("a", encoding="utf-8") as flux:
            for fait in faits:
                flux.write(json.dumps(fait) + "\n")

    def vente_du_jour(self):
        self.ajouter_faits({"id": "vente:F01:J", "type": "vente", "article": CODE,
                           "date_source": JOUR, "date_effet": JOUR, "quantite": 3})

    def position(self):
        avant = self.carnet.read_bytes()
        execution = subprocess.run([sys.executable, "-B", str(self.moteur / "calculer-position.py")],
                                   cwd=self.racine, capture_output=True, text=True,
                                   encoding="utf-8", errors="replace", timeout=30)
        self.assertEqual(execution.returncode, 0, execution.stdout + execution.stderr)
        self.assertEqual(self.carnet.read_bytes(), avant)
        etat = json.loads((self.racine / "donnees/etat.json").read_text(encoding="utf-8"))
        self.assertEqual(etat["date_reference"], "2026-09-09", "Une mesure ne rajeunit pas les ventes")
        return etat["articles"][CODE]

    def test_08h30_vers_19h20_sorties_j3_nouvelle_base_du_soir(self):
        self.assertTrue(self.envoyer(self.releve(30, "08:30:00"))["ok"])
        self.vente_du_jour()
        self.assertEqual(self.position()["position"], 27)
        prefixe = self.carnet.read_bytes()
        retour = self.envoyer(self.releve(20, "19:20:00"))
        self.assertTrue(retour["ok"], retour)
        position = self.position()
        self.assertEqual(position["position"], 20, "Le nouveau relevé inclut les sorties J=3")
        self.assertEqual(position["moment_mesure"], "soir")
        self.assertEqual(position["mouvements_depuis"], 0)
        self.assertEqual(position["mesuree_le"], JOUR)
        apres = self.carnet.read_bytes()
        self.assertTrue(apres.startswith(prefixe))
        lignes = [json.loads(l) for l in apres.splitlines()]
        mesures = [f for f in lignes if f["type"] == "comptage"]
        self.assertEqual(len(mesures), 2)
        self.assertNotEqual(mesures[0]["id"], mesures[1]["id"])
        self.assertEqual(mesures[-1]["horodatage"], JOUR + "T19:20:00")
        self.assertNotIn("cible_id", mesures[-1])
        self.assertEqual(retour, {"ok": True, "enregistres": 1, "corrections": 0, "deja_recus": 0})
        self.assertEqual(self.position(), position, "Reconstruction réitérable")

    def test_meme_instant_contradictoire_refuse_sans_correction_implicite(self):
        self.assertTrue(self.envoyer(self.releve(20, "19:20:00"))["ok"])
        avant = self.carnet.read_bytes()
        retour = self.envoyer(self.releve(18, "19:20:00"), self.releve(22, "20:00:00"))
        self.assertFalse(retour["ok"], "Deux valeurs au même instant exigent une correction explicite")
        self.assertIn("instant", retour["erreur"])
        self.assertEqual(self.carnet.read_bytes(), avant)
        self.assertEqual(self.position()["position"], 20)

    def test_correction_historique_tardive_garde_08h30_et_nouvelle_mesure_gagne(self):
        original = {"id": f"comptage:{JOUR}:{CODE}:saisie", "type": "comptage",
                    "article": CODE, "date_source": JOUR, "date_effet": JOUR,
                    "quantite": 30, "horodatage": JOUR + "T08:30:00"}
        correction = {**original, "id": "correction-comptage:historique-fictive",
                      "type": "correction-comptage", "cible_id": original["id"],
                      "quantite": 25, "horodatage": JOUR + "T21:00:00"}
        self.ajouter_faits(original, correction)
        self.vente_du_jour()
        position = self.position()
        self.assertEqual(position["position"], 22)
        self.assertEqual(position["moment_mesure"], "matin")
        self.assertEqual(position["mesuree_le"], JOUR)
        prefixe = self.carnet.read_bytes()
        retour = self.envoyer(self.releve(20, "19:20:00"))
        self.assertTrue(retour["ok"], retour)
        self.assertEqual(self.position()["position"], 20,
                         "L'heure d'audit de la correction ne date pas la mesure physique")
        self.assertTrue(self.carnet.read_bytes().startswith(prefixe))
        self.ajouter_faits({**correction, "id": "correction-comptage:historique-fictive-2",
                           "quantite": 24, "horodatage": JOUR + "T22:00:00"})
        self.assertEqual(self.position()["position"], 20)
        self.assertEqual(self.position()["moment_mesure"], "soir")

    def test_conflit_meme_instant_ancien_refuse_aussi_le_lot_sans_ecriture(self):
        self.assertTrue(self.envoyer(self.releve(30, "08:30:00"),
                                    self.releve(20, "19:20:00"))["ok"])
        avant = self.carnet.read_bytes()
        conflit = self.releve(31, "08:30:00")
        nouveau = self.releve(22, "20:00:00")
        for lot in ((conflit,), (conflit, nouveau), (nouveau, conflit)):
            with self.subTest(lot=lot):
                retour = self.envoyer(*lot)
                self.assertFalse(retour["ok"], "Un ancien instant enregistré doit aussi être contrôlé")
                self.assertIn("instant", retour["erreur"])
                self.assertEqual(self.carnet.read_bytes(), avant)
                self.assertEqual(self.position()["position"], 20)

    def test_rejeu_ancienne_correction_ui_ne_reinterprete_pas_lhistorique(self):
        original = {"id": f"comptage:{JOUR}:{CODE}:saisie", "type": "comptage",
                    "article": CODE, "date_source": JOUR, "date_effet": JOUR,
                    "quantite": 30, "colis": 30, "conditionnement": 1,
                    "horodatage": JOUR + "T08:30:00",
                    "source": {"origine": "app/compter.html", "saisi_le": JOUR + "T08:30:00"}}
        correction = {**original, "id": "correction-comptage:ancienne-ui-fictive",
                      "type": "correction-comptage", "cible_id": original["id"],
                      "origine_mesure": "ecran-comptage-correction", "quantite": 20, "colis": 20,
                      "horodatage": JOUR + "T19:20:00",
                      "source": {"origine": "app/compter.html", "saisi_le": JOUR + "T19:20:00"}}
        self.ajouter_faits(original, correction)
        self.vente_du_jour()
        self.assertEqual(self.position()["position"], 17, "L'ancien fait n'est pas réparé implicitement")
        avant = self.carnet.read_bytes()
        retour = self.envoyer(self.releve(20, "19:20:00"))
        self.assertTrue(retour["ok"], retour)
        self.assertEqual(retour["deja_recus"], 1, "Le renvoi d'un ancien envoi n'est pas une nouvelle mesure")
        self.assertEqual(self.carnet.read_bytes(), avant)
        self.assertEqual(self.position()["position"], 17)
        self.assertTrue(self.envoyer(self.releve(20, "20:00:00"))["ok"])
        self.assertEqual(self.position()["position"], 20, "Seul un vrai nouveau relevé actualise la base")

    def test_carnet_interrompu_refuse_lajout_sans_recoudre_la_source(self):
        for fin in (b'{"id":"incomplet"', b'{"id":"sans-separateur","type":"vente"}'):
            with self.subTest(fin=fin):
                self.carnet.write_bytes(fin)  # Fixture uniquement, hors racine projet.
                retour = self.envoyer(self.releve(20, "19:20:00"))
                self.assertFalse(retour["ok"], retour)
                self.assertEqual(self.carnet.read_bytes(), fin)
        self.recalcul.assert_not_called()

    def test_api_de_releves_ne_transforme_pas_une_correction_explicite_en_mesure(self):
        self.assertTrue(self.envoyer(self.releve(30, "08:30:00"))["ok"])
        avant = self.carnet.read_bytes()
        for extra in ({"type": "correction-comptage"}, {"cible_id": "comptage:historique"}):
            with self.subTest(extra=extra):
                retour = self.envoyer(self.releve(20, "19:20:00", **extra))
                self.assertFalse(retour["ok"], "Cette route ne corrige pas un fait historique")
                self.assertIn("historique", retour["erreur"])
                self.assertEqual(self.carnet.read_bytes(), avant)

    def test_rejeu_ne_duplique_pas_laudit_et_audit_reference_le_fait_durable(self):
        releve = self.releve(20, "19:20:00")
        self.assertTrue(self.envoyer(releve)["ok"])
        journal = self.racine / "donnees/journal.jsonl"
        avant = journal.read_bytes()
        self.assertEqual(self.envoyer(releve)["deja_recus"], 1)
        self.assertEqual(journal.read_bytes(), avant)
        fait = json.loads(self.carnet.read_text(encoding="utf-8"))
        audit = json.loads(avant)
        self.assertEqual(audit["details"]["ids_comptages"], [fait["id"]])

    def test_meme_valeur_plus_tard_rafraichit_la_base_sans_rajeunir_les_ventes(self):
        self.assertTrue(self.envoyer(self.releve(30, "08:30:00"))["ok"])
        self.vente_du_jour()
        self.assertEqual(self.position()["position"], 27)
        self.assertTrue(self.envoyer(self.releve(30, "19:20:00"))["ok"])
        position = self.position()
        self.assertEqual(position["position"], 30)
        self.assertEqual(position["moment_mesure"], "soir")
        self.assertEqual(position["mouvements_depuis"], 0)

    def test_rejeu_et_ancien_offline_ne_remplacent_pas_la_mesure_recente(self):
        matin = self.releve(30, "08:30:00")
        soir = self.releve(20, "19:20:00")
        self.assertTrue(self.envoyer(matin, soir)["ok"])
        self.vente_du_jour()
        avant = self.carnet.read_bytes()
        for ancien in (matin, soir, self.releve(99, "12:00:00")):
            with self.subTest(ancien=ancien):
                retour = self.envoyer(ancien)
                self.assertEqual(retour, {"ok": True, "enregistres": 0, "corrections": 0, "deja_recus": 1})
                self.assertEqual(self.carnet.read_bytes(), avant)
                self.assertEqual(self.position()["position"], 20)
                self.assertEqual(self.position()["moment_mesure"], "soir")

    def test_lot_inverse_et_precision_sous_seconde_restent_idempotents(self):
        recent = self.releve(20, "19:20:00.900000")
        ancien = self.releve(50, "19:20:00.100000")
        retour = self.envoyer(recent, ancien, recent)
        self.assertEqual(retour, {"ok": True, "enregistres": 1, "corrections": 0, "deja_recus": 2})
        fait = json.loads(self.carnet.read_text(encoding="utf-8"))
        self.assertEqual(fait["horodatage"], JOUR + "T19:20:00.900000")
        articles = self.serveur.charger_articles_comptables()
        self.assertEqual(fait["id"], self.serveur.normaliser_comptage(recent, articles)["id"])
        self.assertNotEqual(fait["id"], self.serveur.normaliser_comptage(ancien, articles)["id"])
        self.assertEqual(self.position()["position"], 20)

    def test_mesures_concurrentes_selectionnent_linstant_recent_pas_lordre_http(self):
        rendez_vous = threading.Barrier(8)

        def envoyer(n):
            rendez_vous.wait(5)
            return self.envoyer(self.releve(20, "19:20:00") if n % 2
                                else self.releve(30, "08:30:00"))

        with ThreadPoolExecutor(8) as pool:
            retours = list(pool.map(envoyer, range(8)))
        self.assertTrue(all(r["ok"] for r in retours), retours)
        lignes = [json.loads(l) for l in self.carnet.read_bytes().splitlines()]
        self.assertIn(len(lignes), (1, 2))
        self.assertEqual(len({l["id"] for l in lignes}), len(lignes))
        self.assertEqual(sum(r["enregistres"] for r in retours), len(lignes))
        self.vente_du_jour()
        self.assertEqual(self.position()["position"], 20)
        self.assertEqual(self.position()["moment_mesure"], "soir")

    def test_correction_dun_jour_ancien_ne_change_pas_la_date_de_mesure(self):
        original = {"id": "comptage:veille-fictive", "type": "comptage", "article": CODE,
                    "date_source": "2026-09-09", "date_effet": "2026-09-09", "quantite": 30,
                    "horodatage": "2026-09-09T08:30:00"}
        correction = {**original, "id": "correction-comptage:veille-fictive",
                      "type": "correction-comptage", "cible_id": original["id"],
                      "date_effet": JOUR, "quantite": 25, "horodatage": JOUR + "T21:00:00"}
        self.ajouter_faits(original, correction)
        self.vente_du_jour()
        position = self.position()
        self.assertEqual(position["position"], 22)
        self.assertEqual(position["mesuree_le"], "2026-09-09")
        self.assertEqual(position["moment_mesure"], "matin")
        self.assertTrue(self.envoyer(self.releve(20, "19:20:00"))["ok"])
        position = self.position()
        self.assertEqual(position["position"], 20)
        self.assertEqual(position["mesuree_le"], JOUR)

    def test_reprise_apres_echec_avant_ou_apres_append_najoute_quun_fait(self):
        for phase in ("avant", "apres"):
            with self.subTest(phase=phase):
                self.carnet.write_bytes(b"")  # Réinitialisation de la fixture privée.

                ajout_reel = self.serveur.append_jsonl

                def ajouter_interrompu(chemin, objets):
                    cible = Path(chemin) == self.carnet
                    if cible and phase == "avant":
                        raise OSError("Interruption fictive avant append")
                    ajout_reel(chemin, objets)
                    if cible:
                        raise OSError("Interruption fictive après append durable")

                with patch.object(self.serveur, "append_jsonl", ajouter_interrompu):
                    retour = self.envoyer(self.releve(20, "19:20:00"))
                self.assertFalse(retour["ok"], retour)
                if phase == "avant":
                    self.assertEqual(self.carnet.read_bytes(), b"")
                else:
                    self.assertEqual(len(self.carnet.read_text(encoding="utf-8").splitlines()), 1)
                retour = self.envoyer(self.releve(20, "19:20:00"))
                self.assertTrue(retour["ok"], retour)
                self.assertEqual(retour["enregistres"], int(phase == "avant"))
                self.assertEqual(retour["deja_recus"], int(phase == "apres"))
                self.assertEqual(len(self.carnet.read_text(encoding="utf-8").splitlines()), 1)
                self.assertEqual(self.position()["position"], 20)


if __name__ == "__main__":
    unittest.main()
