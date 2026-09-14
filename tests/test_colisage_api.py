"""API colisage : HTTP réel, CLI réel en copie, jamais de données production."""
import http.client
import importlib.util
import json
import shutil
import socket
import subprocess
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from unittest.mock import patch

MOTEUR = Path(__file__).resolve().parents[1] / "moteur"
CODE = "0000087003306"
VRAI_RUN = subprocess.run


class ColisageAPITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="colisage-api-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.assertFalse(self.root.is_relative_to(MOTEUR.parent))
        moteur = self.root / "moteur"
        moteur.mkdir()
        for nom in ("serveur.py", "appliquer-decision.py", "journal_agents.py", "regles.py", "catalogue.py"):
            shutil.copy2(MOTEUR / nom, moteur / nom)
        spec = importlib.util.spec_from_file_location("serveur_colisage_isole", moteur / "serveur.py")
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.assertEqual(self.module.RACINE, self.root)
        self.article = {"itm8": CODE, "libelle": "ARTICLE TEST FIABLE", "conditionnement": 12,
                        "prix_achat": 2.5, "colis": 3, "total_achat": 90}
        self.ecrire("donnees/proposition.json", {"lignes": [self.article], "total_achat": 90})
        self.ecrire("donnees/catalogue.json", {"articles": {CODE: {"LIBELLE": "ARTICLE TEST FIABLE"}}})
        self.ecrire("donnees/articles.json", {"articles": [self.article]})
        self.ecrire("donnees/pouvoirs.json", {"agents": {"responsable-rayon": {
            "peut_seul": ["conditionnement"], "plafond_par_jour": 999}}})
        self.ajouter_decision(12, id="decision-initiale")
        self.ecrire("donnees/faits/2026.jsonl", json.dumps({
            "id": "comptage-fictif", "type": "comptage", "article": CODE,
            "colis": 2, "conditionnement": 12, "quantite": 24}) + "\n")
        self.intacts = {p: p.read_bytes() for p in (
            self.root / "donnees/proposition.json", self.root / "donnees/articles.json",
            self.root / "donnees/faits/2026.jsonl")}
        self.addCleanup(self.verifier_intacts)
        self.recalc = patch.object(self.module, "recalculer_en_arriere_plan")
        self.recalc_mock = self.recalc.start()
        self.addCleanup(self.recalc.stop)
        self.run = patch.object(self.module.subprocess, "run", side_effect=self.executer_cli_isole)
        self.run_mock = self.run.start()
        self.addCleanup(self.run.stop)
        self.server = self.module.ServeurHTTP(("127.0.0.1", 0), self.module.Gestionnaire)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.fermer)

    def fermer(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)
        self.assertFalse(self.thread.is_alive())

    def verifier_intacts(self):
        for chemin, avant in self.intacts.items():
            self.assertEqual(chemin.read_bytes(), avant, str(chemin))

    def ecrire(self, relatif, valeur):
        cible = self.root / relatif
        cible.parent.mkdir(parents=True, exist_ok=True)
        cible.write_text(valeur if isinstance(valeur, str) else json.dumps(valeur), encoding="utf-8")

    def decisions(self):
        return [json.loads(l) for l in (self.root / "donnees/decisions.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]

    def ajouter_decision(self, valeur, **extra):
        decision = {"id": "decision-fixture", "type": "conditionnement", "article": CODE,
                    "valeur": str(valeur), "valide_a_partir_de": date.today().isoformat(),
                    "auteur": "responsable-rayon", **extra}
        chemin = self.root / "donnees/decisions.jsonl"
        chemin.parent.mkdir(parents=True, exist_ok=True)
        with chemin.open("a", encoding="utf-8") as fichier:
            fichier.write(json.dumps(decision) + "\n")
        return decision

    def verifier_commande_isolee(self, commande, kwargs):
        script = Path(commande[1]).resolve()
        self.assertEqual(script, self.root / "moteur/appliquer-decision.py")
        self.assertEqual(commande[2:4], ["conditionnement", CODE])
        self.assertEqual(commande[5:8], ["--auteur", "responsable-rayon", "--motif"])
        self.assertIn("ARTICLE TEST FIABLE", commande[8])
        self.assertNotIn("LIBELLE CLIENT", commande[8])
        self.assertFalse(kwargs.get("shell", False))

    def executer_cli_isole(self, commande, **kwargs):
        self.verifier_commande_isolee(commande, kwargs)
        return VRAI_RUN(commande, **{**kwargs, "cwd": str(self.root)})

    def requete(self, charge=None, headers=None, corps=None, route="/api/conditionnement"):
        host = "127.0.0.1:" + str(self.server.server_port)
        entetes = {"Host": host, "Origin": "http://" + host,
                   "Content-Type": "application/json", "Sec-Fetch-Site": "same-origin"}
        entetes.update(headers or {})
        if corps is None:
            corps = json.dumps(charge if charge is not None else {
                "itm8": CODE, "conditionnement": 6.5, "ancien_conditionnement": 12,
                "libelle": "LIBELLE CLIENT"}).encode("utf-8")
        entetes.setdefault("Content-Length", str(len(corps)))
        paquet = (f"POST {route} HTTP/1.1\r\n" + "".join(
            f"{k}: {v}\r\n" for k, v in entetes.items() if v is not None) + "\r\n").encode("ascii") + corps
        with socket.create_connection(("127.0.0.1", self.server.server_port), timeout=10) as connexion:
            connexion.sendall(paquet)
            connexion.shutdown(socket.SHUT_WR)
            reponse = http.client.HTTPResponse(connexion)
            try:
                reponse.begin()
            except http.client.RemoteDisconnected:
                self.fail("La route coupe la connexion au lieu d'un accusé JSON d'erreur")
            contenu = reponse.read()
            return reponse.status, contenu

    def test_valeurs_doit_etre_nombres_reels_finis_strictement_positifs(self):
        avant = (self.root / "donnees/decisions.jsonl").read_bytes()
        for champ in ("conditionnement", "ancien_conditionnement"):
            for valeur in (True, False, "6.5", "6,5", None, [], {}, 0, -2, 1e309, float("nan"), 10**400):
                with self.subTest(champ=champ, valeur=repr(valeur)[:50]):
                    charge = {"itm8": CODE, "conditionnement": 6.5, "ancien_conditionnement": 12, champ: valeur}
                    statut, corps = self.requete(charge)
                    self.assertEqual(statut, 400, corps)
                    self.assertFalse(json.loads(corps)["ok"])
                    self.assertTrue(json.loads(corps)["erreur"])
                    self.assertEqual((self.root / "donnees/decisions.jsonl").read_bytes(), avant)
        self.run_mock.assert_not_called()
        self.recalc_mock.assert_not_called()

    def test_article_source_refuse_code_inconnu_doublon_ou_libelle_non_fiable(self):
        for code in ("0000000000000", " " + CODE, CODE + " ", CODE[1:], None, True, "--simuler"):
            with self.subTest(code=code):
                statut, corps = self.requete({"itm8": code, "conditionnement": 6.5, "ancien_conditionnement": 12})
                self.assertEqual(statut, 400, corps)
                self.assertFalse(json.loads(corps)["ok"])
        for lignes in ([self.article, {**self.article, "conditionnement": 8}],
                       [{**self.article, "libelle": None}], [{**self.article, "libelle": " "}],
                       [{**self.article, "libelle": 123}], [{**self.article, "libelle": "a\nb"}],
                       [{**self.article, "conditionnement": None}]):
            with self.subTest(lignes=lignes):
                self.ecrire("donnees/proposition.json", {"lignes": lignes})
                chemin = self.root / "donnees/proposition.json"
                self.intacts[chemin] = chemin.read_bytes()
                statut, corps = self.requete()
                self.assertEqual(statut, 400, corps)
                self.assertFalse(json.loads(corps)["ok"])
        self.run_mock.assert_not_called()
        self.assertEqual(len(self.decisions()), 1)

    def test_rejeu_avant_recalcul_ne_duplique_pas_la_decision(self):
        statut, corps = self.requete()
        self.assertEqual(statut, 200, corps)
        premiere = json.loads(corps)
        avant = (self.root / "donnees/decisions.jsonl").read_bytes()
        self.recalc_mock.reset_mock()
        statut, corps = self.requete()
        self.assertEqual(statut, 200, corps)
        retour = json.loads(corps)
        self.assertTrue(retour["ok"])
        self.assertTrue(retour.get("deja_effectif"), retour)
        self.assertEqual(retour["decision_id"], premiere["decision_id"])
        self.assertEqual(retour["conditionnement"], 6.5)
        self.assertEqual(retour["recalcul"], "en_cours")
        self.assertEqual((self.root / "donnees/decisions.jsonl").read_bytes(), avant)
        self.run_mock.assert_called_once()
        self.recalc_mock.assert_called_once()

    def test_precondition_perimee_refuse_meme_si_projection_encore_ancienne(self):
        self.ajouter_decision(8, id="plus-recente")
        avant = (self.root / "donnees/decisions.jsonl").read_bytes()
        for ancien in (12, 3):
            with self.subTest(ancien=ancien):
                statut, corps = self.requete({"itm8": CODE, "conditionnement": 6.5, "ancien_conditionnement": ancien})
                self.assertEqual(statut, 409, corps)
                retour = json.loads(corps)
                self.assertFalse(retour["ok"])
                self.assertEqual(retour["conditionnement"], 8)
                self.assertIn("recharge", retour["erreur"].lower())
        self.assertEqual((self.root / "donnees/decisions.jsonl").read_bytes(), avant)
        self.run_mock.assert_not_called()
        self.recalc_mock.assert_not_called()

    def test_refus_cli_reel_ne_se_fait_pas_passer_pour_un_succes(self):
        self.ecrire("donnees/pouvoirs.json", {"agents": {"responsable-rayon": {
            "peut_seul": [], "plafond_par_jour": 999}}})
        avant = (self.root / "donnees/decisions.jsonl").read_bytes()
        statut, corps = self.requete()
        self.assertEqual(statut, 502, corps)
        retour = json.loads(corps)
        self.assertFalse(retour["ok"])
        self.assertTrue(retour["erreur"])
        self.assertFalse(retour.get("enregistre", False))
        self.assertEqual((self.root / "donnees/decisions.jsonl").read_bytes(), avant)
        self.recalc_mock.assert_not_called()

    def test_code_retour_zero_sans_decision_exacte_nest_pas_un_succes(self):
        def sans_ecriture(commande, **kwargs):
            self.verifier_commande_isolee(commande, kwargs)
            return subprocess.CompletedProcess(commande, 0, "SUCCES NON FIABLE", "")
        self.run_mock.side_effect = sans_ecriture
        statut, corps = self.requete()
        self.assertEqual(statut, 500, corps)
        retour = json.loads(corps)
        self.assertFalse(retour["ok"])
        self.assertIn("décision", retour["erreur"].lower())
        self.assertEqual(len(self.decisions()), 1)
        self.recalc_mock.assert_not_called()

    def test_echec_cli_apres_ecriture_signale_enregistre_et_rejeu_sans_append(self):
        def ecriture_puis_panne(commande, **kwargs):
            resultat = self.executer_cli_isole(commande, **kwargs)
            self.assertEqual(resultat.returncode, 0, resultat.stderr)
            return subprocess.CompletedProcess(commande, 1, "", "Panne audit simulée après la décision")
        self.run_mock.side_effect = ecriture_puis_panne
        statut, corps = self.requete()
        self.assertEqual(statut, 502, corps)
        retour = json.loads(corps)
        self.assertFalse(retour["ok"])
        self.assertTrue(retour.get("enregistre"), retour)
        self.assertEqual(len(self.decisions()), 2)
        avant = (self.root / "donnees/decisions.jsonl").read_bytes()
        statut, corps = self.requete()
        self.assertEqual(statut, 200, corps)
        self.assertTrue(json.loads(corps)["deja_effectif"])
        self.assertEqual((self.root / "donnees/decisions.jsonl").read_bytes(), avant)
        self.run_mock.assert_called_once()

    def test_panne_demarrage_recalcul_annonce_la_decision_deja_enregistree(self):
        self.recalc_mock.side_effect = OSError("Impossible de démarrer le fil")
        statut, corps = self.requete()
        self.assertEqual(statut, 500, corps)
        retour = json.loads(corps)
        self.assertFalse(retour["ok"])
        self.assertTrue(retour.get("enregistre"), retour)
        self.assertIn("recalcul", retour["erreur"].lower())
        self.assertEqual(len(self.decisions()), 2)
        self.recalc_mock.side_effect = None
        statut, corps = self.requete()
        self.assertEqual(statut, 200, corps)
        self.assertTrue(json.loads(corps)["deja_effectif"])
        self.run_mock.assert_called_once()

    def test_exception_cli_ou_timeout_retourne_json_sans_faux_succes(self):
        for erreur, attendu in ((OSError("programme indisponible"), 502),
                                (subprocess.TimeoutExpired("CLI isolé", 30), 504)):
            with self.subTest(erreur=type(erreur).__name__):
                def panne(commande, **kwargs):
                    self.verifier_commande_isolee(commande, kwargs)
                    raise erreur
                self.run_mock.side_effect = panne
                statut, corps = self.requete()
                self.assertEqual(statut, attendu, corps)
                retour = json.loads(corps)
                self.assertFalse(retour["ok"])
                self.assertTrue(retour["erreur"])
                self.assertFalse(retour.get("enregistre"))
        self.assertEqual(len(self.decisions()), 1)
        self.recalc_mock.assert_not_called()

    def test_effectif_ignore_decisions_futures_et_les_deux_annulations(self):
        self.ajouter_decision(8, id="annule-par-id")
        self.ajouter_decision(None, id="annulation-1", type="annulation", annule="annule-par-id")
        self.ajouter_decision(9, id="annule-par-action", action="A-FICTIVE")
        self.ecrire("donnees/journaux/tout.jsonl", json.dumps({
            "annule_action": "A-FICTIVE", "resultat": "ok", "horodatage": "2000-01-01T00:00:00"}) + "\n")
        self.ajouter_decision(20, id="future", valide_a_partir_de="2999-01-01")
        statut, corps = self.requete()
        self.assertEqual(statut, 200, corps)
        self.assertEqual(json.loads(corps)["conditionnement"], 6.5)
        self.assertEqual(float(self.decisions()[-1]["valeur"]), 6.5)
        self.run_mock.assert_called_once()

    def test_carnet_illisible_refuse_avant_cli(self):
        initiale = (self.root / "donnees/decisions.jsonl").read_text(encoding="utf-8")
        invalides = [initiale + '{"type":', initiale + "[]\n", initiale.rstrip()]

        invalides.append(initiale + json.dumps({"id": "date-invalide", "type": "conditionnement",
            "article": CODE, "valeur": "8", "valide_a_partir_de": "2026-99-99"}) + "\n")
        for contenu in invalides:
            with self.subTest(contenu=contenu[-120:]):
                self.ecrire("donnees/decisions.jsonl", contenu)
                avant = (self.root / "donnees/decisions.jsonl").read_bytes()
                statut, corps = self.requete()
                self.assertEqual(statut, 500, corps)
                self.assertFalse(json.loads(corps)["ok"])
                self.assertEqual((self.root / "donnees/decisions.jsonl").read_bytes(), avant)
        self.run_mock.assert_not_called()
        self.recalc_mock.assert_not_called()

    def test_retrait_ou_decision_invalide_utilise_le_repli_publie(self):
        initiale = (self.root / "donnees/decisions.jsonl").read_text(encoding="utf-8")
        for valeur in ("NaN", "Infinity", True, -3, "illisible", None, False):
            with self.subTest(valeur=valeur):
                self.ecrire("donnees/decisions.jsonl", initiale + json.dumps({
                    "id": "retiree-ou-invalide", "type": "conditionnement", "article": CODE,
                    "valeur": valeur}) + "\n")
                statut, corps = self.requete()
                self.assertEqual(statut, 200, corps)
                self.assertEqual(float(self.decisions()[-1]["valeur"]), 6.5)

    def test_comptage_hors_ligne_refuse_pcb_different_sans_reconversion(self):
        for valeur in (8, True, "12", None, 0, -2, 1e309, 10**400):
            with self.subTest(conditionnement=repr(valeur)[:40]):
                comptage = {"itm8": CODE, "conditionnement": valeur, "colis": 2,
                            "date": date.today().isoformat(),
                            "saisi_le": date.today().isoformat() + "T08:00:00"}
                statut, corps = self.requete({"comptages": [comptage]}, route="/api/comptages")
                retour = json.loads(corps)
                self.assertFalse(retour["ok"], retour)
                self.assertTrue(retour["erreur"])
                if valeur == 8:
                    self.assertIn(CODE, retour["erreur"])
                    self.assertIn("8", retour["erreur"])
                    self.assertIn("12", retour["erreur"])
        self.recalc_mock.assert_not_called()
        self.run_mock.assert_not_called()

    def test_deux_envois_concurrents_identiques_ne_font_quun_append(self):
        rendez_vous = threading.Barrier(2)
        def envoyer(_):
            rendez_vous.wait(5)
            return self.requete()
        with ThreadPoolExecutor(2) as pool:
            retours = list(pool.map(envoyer, range(2)))
        self.assertEqual([s for s, _ in retours], [200, 200], retours)
        self.assertEqual(sum(bool(json.loads(c)["deja_effectif"]) for _, c in retours), 1)
        self.assertEqual(len(self.decisions()), 2)
        self.run_mock.assert_called_once()

    def test_deux_valeurs_concurrentes_necrasent_pas_la_premiere(self):
        rendez_vous = threading.Barrier(2)
        def envoyer(valeur):
            rendez_vous.wait(5)
            return self.requete({"itm8": CODE, "conditionnement": valeur, "ancien_conditionnement": 12})
        with ThreadPoolExecutor(2) as pool:
            retours = list(pool.map(envoyer, (6.5, 8)))
        self.assertEqual(sorted(s for s, _ in retours), [200, 409], retours)
        gagnant = next(json.loads(c)["conditionnement"] for s, c in retours if s == 200)
        self.assertEqual(float(self.decisions()[-1]["valeur"]), gagnant)
        self.assertEqual(len(self.decisions()), 2)
        self.run_mock.assert_called_once()

    def test_relecture_apres_cli_refuse_decision_dun_autre_article(self):
        def autre_article(commande, **kwargs):
            self.verifier_commande_isolee(commande, kwargs)
            self.ajouter_decision(6.5, article="0000000000000", motif=commande[-1], id="autre-article")
            return subprocess.CompletedProcess(commande, 0, "", "")
        self.run_mock.side_effect = autre_article
        statut, corps = self.requete()
        self.assertEqual(statut, 500, corps)
        self.assertFalse(json.loads(corps)["ok"])
        self.recalc_mock.assert_not_called()

    def test_origin_csrf_et_encadrement_json_restent_proteges(self):
        for entetes in ({"Origin": "https://pirate.invalid"}, {"Origin": None},
                        {"Sec-Fetch-Site": "cross-site"}, {"Host": "pirate.invalid"},
                        {"Origin": "null"}):
            with self.subTest(entetes=entetes):
                statut, corps = self.requete(headers=entetes)
                self.assertEqual(statut, 403, corps)
                self.assertFalse(json.loads(corps)["ok"])
        for corps, entetes, attendu in ((b"{", {}, 400), (b"[]", {}, 400), (b"null", {}, 400),
                (b'{"itm8":"a","itm8":"b"}', {}, 400), (b'{"conditionnement":NaN}', {}, 400),
                (b'{"conditionnement":1e309}', {}, 400),
                (b"{}", {"Content-Type": "text/plain"}, 415),
                (b"{}", {"Content-Length": "1048577"}, 413),
                (b"{}", {"Transfer-Encoding": "chunked"}, 400)):
            with self.subTest(corps=corps, entetes=entetes):
                statut, reponse = self.requete(corps=corps, headers=entetes)
                self.assertEqual(statut, attendu, reponse)
                self.assertFalse(json.loads(reponse)["ok"])
        self.assertEqual(len(self.decisions()), 1)
        self.run_mock.assert_not_called()
        self.recalc_mock.assert_not_called()

    def test_comptage_pcb_identique_ou_absent_reste_compatible(self):
        base = {"itm8": CODE, "colis": 2, "date": date.today().isoformat(),
                "saisi_le": date.today().isoformat() + "T08:00:00"}
        for extra in ({}, {"conditionnement": 12}, {"conditionnement": 12.0}):
            with self.subTest(extra=extra):
                fait = self.module.normaliser_comptage({**base, **extra}, {CODE: self.article})
                self.assertEqual(fait["quantite"], 24)
                self.assertEqual(fait["colis"], 2)
                self.assertEqual(fait["conditionnement"], 12)

    def test_succes_decision_cli_reelle_durable_sans_projection_partielle(self):
        avant = (self.root / "donnees/decisions.jsonl").read_bytes()
        statut, corps = self.requete()
        self.assertEqual(statut, 200, corps)
        retour = json.loads(corps)
        self.assertTrue(retour["ok"])
        self.assertEqual(retour["conditionnement"], 6.5)
        self.assertEqual(retour["recalcul"], "en_cours")
        decisions = self.decisions()
        self.assertEqual(len(decisions), 2)
        self.assertEqual(decisions[-1]["article"], CODE)
        self.assertEqual(float(decisions[-1]["valeur"]), 6.5)
        self.assertEqual(decisions[-1]["auteur"], "responsable-rayon")
        self.assertIn("ARTICLE TEST FIABLE", decisions[-1]["motif"])
        self.assertTrue((self.root / "donnees/decisions.jsonl").read_bytes().startswith(avant))
        self.assertEqual(retour["decision_id"], decisions[-1]["id"])
        self.recalc_mock.assert_called_once()
        self.run_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
