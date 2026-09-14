"""HTTP réel sur port éphémère, données fictives et aucun agent lancé."""
import http.client
import builtins
import importlib.util
import json
import socket
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import Mock, patch

MOTEUR = Path(__file__).resolve().parents[1] / "moteur"
PUBLIC_HOST = "desktop-11kv59v.tail44b4ba.ts.net"
CODE = "0000087003306"
PHOTO = "/app/img/produits/" + "a" * 64


class ServeurIsoleTests(unittest.TestCase):
    def test_rafale_de_connexions_photos_reste_en_attente_sans_refus(self):
        # Tailscale multiplexe les images puis ouvre une connexion locale par
        # requête. Une rafale doit tenir même avant le prochain tour accept().
        classe = self.module.ServeurHTTP
        serveur = classe(("127.0.0.1", 0), self.module.Gestionnaire)
        connexions, refus = [], []
        try:
            for _ in range(24):
                try:
                    connexions.append(socket.create_connection(
                        ("127.0.0.1", serveur.server_port), timeout=0.15))
                except OSError as erreur:
                    refus.append(type(erreur).__name__)
            self.assertEqual(refus, [], "La file TCP perd une partie de la rafale d'images")
        finally:
            for connexion in connexions:
                connexion.close()
            serveur.server_close()

    def setUp(self):
        spec = importlib.util.spec_from_file_location("serveur_isole", MOTEUR / "serveur.py")
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.module.RACINE = self.root
        self.module.DONNEES = self.root / "donnees"
        self.module.DOSSIER_FAITS = self.root / "donnees/faits"
        self.module.JOURNAL = self.root / "donnees/journal.jsonl"
        article = {"itm8": CODE, "libelle": "ARTICLE TEST", "conditionnement": 12, "unite": "Pièce"}
        self.ecrire("donnees/articles.json", json.dumps({"articles": [article]}))
        self.ecrire("donnees/proposition.json", json.dumps({"lignes": [article]}))
        for chemin in ("app/index.html", "app/css/charte.css", "app/img/favicon.ico", "app/js/photos-produits.js",
                       PHOTO.lstrip("/") + "-96.webp", PHOTO.lstrip("/") + "-240.webp",
                       "app/img/produits/test.webp", "donnees/photos.json",
                       "Documents/Promo intermarche/offre test.png", "donnees/faits/2026.jsonl"):
            self.ecrire(chemin, "PUBLIC TEST")
        for chemin in ("AGENT.md", "donnees/pouvoirs.json", "app/interne.py", "app/img/secret.txt"):
            self.ecrire(chemin, "PRIVE TEST")
        self.ecrire("documents-partages/photos-produits/original.jpg", "PRIVE TEST")
        self.ecrire(PHOTO.lstrip("/") + "-512.webp", "PRIVE TEST")
        self.run = patch.object(self.module.subprocess, "run", side_effect=AssertionError("Sous-processus interdit en test HTTP"))
        self.run_mock = self.run.start()
        self.addCleanup(self.run.stop)
        self.launch = patch.object(self.module, "lancer_reponse_message", return_value=0)
        self.launch_mock = self.launch.start()
        self.addCleanup(self.launch.stop)
        self.recalc = patch.object(self.module, "recalculer_en_arriere_plan")
        self.recalc_mock = self.recalc.start()
        self.addCleanup(self.recalc.stop)
        self.server = self.module.ServeurHTTP(("127.0.0.1", 0), self.module.Gestionnaire)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.fermer)

    def fermer(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)

    def ecrire(self, chemin, texte):
        cible = self.root / chemin
        cible.parent.mkdir(parents=True, exist_ok=True)
        cible.write_text(texte, encoding="utf-8")

    def requete(self, methode, chemin, charge=None, headers=None, corps=None):
        entetes = {"Host": PUBLIC_HOST}
        if charge is not None:
            corps = json.dumps(charge).encode("utf-8")
            entetes.update({"Content-Type": "application/json", "Origin": "https://" + PUBLIC_HOST,
                            "Sec-Fetch-Site": "same-origin"})
        entetes.update(headers or {})
        corps = corps or b""
        entetes.setdefault("Content-Length", str(len(corps)))
        paquet = (f"{methode} {chemin} HTTP/1.1\r\n" + "".join(
            f"{k}: {v}\r\n" for k, v in entetes.items() if v is not None) + "\r\n").encode("ascii") + corps
        with socket.create_connection(("127.0.0.1", self.server.server_port), timeout=5) as connexion:
            connexion.sendall(paquet)
            connexion.shutdown(socket.SHUT_WR)
            reponse = http.client.HTTPResponse(connexion, method=methode)
            reponse.begin()
            return reponse.status, reponse.read(), dict(reponse.getheaders())

    def test_html_revalide_le_cache_en_get_head_et_304_sans_toucher_aux_assets(self):
        for page in ('index', 'commander', 'compter', 'promo', 'maintenance'):
            chemin = f'/app/{page}.html'
            self.ecrire(chemin.lstrip('/'), 'PAGE TEST')
            for methode in ('GET', 'HEAD'):
                with self.subTest(page=page, methode=methode):
                    statut, corps, entetes = self.requete(methode, chemin + '?version=test')
                    self.assertEqual(statut, 200)
                    self.assertEqual(entetes.get('Cache-Control'), 'no-cache')
                    if methode == 'HEAD':
                        self.assertEqual(corps, b'')
                    statut, corps, entetes = self.requete(
                        methode, chemin, headers={'If-Modified-Since': entetes['Last-Modified']})
                    self.assertEqual(statut, 304)
                    self.assertEqual(entetes.get('Cache-Control'), 'no-cache')
                    self.assertEqual(corps, b'')
        statut, _, entetes = self.requete('GET', '/app/css/charte.css?v=test')
        self.assertEqual(statut, 200)
        self.assertNotIn('no-cache', entetes.get('Cache-Control', ''))

    def comptage(self, **extra):
        return {"itm8": CODE, "date": date.today().isoformat(), "colis": 2,
                "saisi_le": date.today().isoformat() + "T08:00:00", **extra}

    def test_comptages_refusent_tout_le_lot_avant_ecriture(self):
        chemin = "donnees/faits/" + str(date.today().year) + ".jsonl"
        prefixe = json.dumps({"id": "test-anterieur", "type": "vente", "quantite": 0}) + "\n"
        jour_court = f"{date.today().year}-{date.today().month}-{date.today().day}"
        jour_invalide = jour_court if jour_court != date.today().isoformat() else jour_court + " "
        for invalide in (self.comptage(colis=True), self.comptage(colis="2"),
                         self.comptage(itm8=" " + CODE), self.comptage(saisi_le="invalide"),
                         self.comptage(saisi_le="2099-01-01T08:00:00"),
                         self.comptage(date=jour_invalide),
                         self.comptage(colis=1e309), self.comptage(itm8="inconnu")):
            with self.subTest(invalide=invalide):
                self.ecrire(chemin, prefixe)
                avant = (self.root / chemin).read_bytes()
                retour = json.loads(self.requete("POST", "/api/comptages",
                                                {"comptages": [self.comptage(), invalide]})[1])
                self.assertFalse(retour["ok"])
                self.assertEqual((self.root / chemin).read_bytes(), avant)
        self.recalc_mock.assert_not_called()

    def test_comptages_concurrents_identiques_najoutent_quune_mesure(self):
        chemin = self.root / "donnees/faits" / (str(date.today().year) + ".jsonl")
        self.ecrire(str(chemin.relative_to(self.root)), "")
        rendez_vous = threading.Barrier(8)
        def envoyer(_):
            rendez_vous.wait(5)
            return json.loads(self.requete("POST", "/api/comptages", {"comptages": [self.comptage()]})[1])
        with ThreadPoolExecutor(8) as pool:
            retours = list(pool.map(envoyer, range(8)))
        self.assertTrue(all(r["ok"] for r in retours))
        self.assertEqual(sum(r["enregistres"] for r in retours), 1)
        self.assertEqual(sum(r["corrections"] for r in retours), 0)
        self.assertEqual(len(chemin.read_text(encoding="utf-8").splitlines()), 1)

    def test_recomptage_identique_plus_tard_et_rejeu_ancien(self):
        chemin = "donnees/faits/" + str(date.today().year) + ".jsonl"
        self.ecrire(chemin, "")
        premier = self.comptage()
        second = self.comptage(saisi_le=date.today().isoformat() + "T10:00:00")
        troisieme = self.comptage(colis=3, saisi_le=date.today().isoformat() + "T11:00:00")
        def envoyer(comptage):
            return json.loads(self.requete("POST", "/api/comptages", {"comptages": [comptage]})[1])
        self.assertEqual(envoyer(premier)["enregistres"], 1)
        prefixe = (self.root / chemin).read_bytes()
        for mesure in (second, troisieme):
            retour = envoyer(mesure)
            self.assertEqual(retour["enregistres"], 1)
            self.assertEqual(retour["corrections"], 0)
        apres = (self.root / chemin).read_bytes()
        self.assertTrue(apres.startswith(prefixe))
        self.assertEqual(envoyer(premier)["deja_recus"], 1)
        self.assertEqual(envoyer(troisieme)["deja_recus"], 1)
        self.assertEqual((self.root / chemin).read_bytes(), apres)
        lignes = [json.loads(l) for l in apres.decode("utf-8").splitlines()]
        self.assertEqual(len(lignes), 3)
        self.assertTrue(all(l["type"] == "comptage" and "cible_id" not in l for l in lignes))
        self.assertEqual(len({l["id"] for l in lignes}), 3)
        self.assertEqual(lignes[-1]["horodatage"], troisieme["saisi_le"])

    def test_telephone_deconnecte_ne_supprime_pas_le_recalcul_ni_la_reponse_agent(self):
        self.ecrire("donnees/faits/" + str(date.today().year) + ".jsonl", "")
        for route, charge in (("_recevoir_comptages", {"comptages": [self.comptage()]}),
                              ("_recevoir_messages", {"messages": [{"texte": "Test", "ecrit_le": "2026-09-09T06:30:00.001Z"}]})):
            with self.subTest(route=route):
                gestionnaire = self.module.Gestionnaire.__new__(self.module.Gestionnaire)
                gestionnaire._charge_json = charge
                gestionnaire.command = "POST"
                gestionnaire.wfile = Mock()
                gestionnaire.wfile.write.side_effect = BrokenPipeError("téléphone parti")
                with patch.object(gestionnaire, "send_response"), patch.object(gestionnaire, "send_header"), patch.object(gestionnaire, "end_headers"):
                    try:
                        getattr(gestionnaire, route)()
                    except BrokenPipeError:
                        self.fail("La déconnexion interrompt le traitement après écriture")
        self.recalc_mock.assert_called_once()
        self.launch_mock.assert_called_once()

    def test_echec_lancement_agent_ne_renvoie_pas_un_second_accuse(self):
        message = {"texte": "Message fictif", "ecrit_le": "2026-09-09T06:30:00.001Z"}
        gestionnaire = self.module.Gestionnaire.__new__(self.module.Gestionnaire)
        gestionnaire._charge_json = {"messages": [message]}
        with patch.object(gestionnaire, "_repondre") as repondre:
            self.launch_mock.side_effect = OSError("panne fictive de lancement")
            gestionnaire._recevoir_messages()
            self.assertEqual(repondre.call_count, 1)
            self.assertTrue(repondre.call_args.args[0]["ok"])
        avis = [json.loads(l) for l in (self.root / "donnees/reponses.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertIn("enregistré", avis[0]["texte"])
        self.assertIn("relancer", avis[0]["texte"])

    def test_recalcul_demande_pendant_un_autre_ne_se_perd_pas(self):
        self.recalc.stop()
        self.ecrire("version-test.txt", "1")
        lecture = threading.Event()
        continuer = threading.Event()
        fils = []
        vrai_thread = threading.Thread

        def creer_thread(*args, **kwargs):
            fil = vrai_thread(*args, **kwargs)
            fils.append(fil)
            return fil

        def script(commande, **kwargs):
            self.assertTrue(Path(commande[1]).is_relative_to(self.root))
            if Path(commande[1]).name == "calculer-position.py":
                version = (self.root / "version-test.txt").read_text()
                if version == "1":
                    lecture.set()
                    self.assertTrue(continuer.wait(5))
                self.ecrire("position-test.txt", version)
            return self.module.subprocess.CompletedProcess(commande, 0, "", "")

        self.run_mock.side_effect = script
        with patch.object(self.module.threading, "Thread", side_effect=creer_thread):
            try:
                self.module.recalculer_en_arriere_plan()
                self.assertTrue(lecture.wait(5))
                self.ecrire("version-test.txt", "2")
                self.module.recalculer_en_arriere_plan()
            finally:
                continuer.set()
                for fil in fils:
                    fil.join(10)
        self.assertFalse(any(fil.is_alive() for fil in fils))
        self.assertEqual((self.root / "position-test.txt").read_text(), "2")
        self.assertEqual(sum(Path(c.args[0][1]).name == "calculer-position.py" for c in self.run_mock.call_args_list), 2)

    def test_interruption_projection_ne_tronque_pas_le_json_publie(self):
        chemin = self.root / "donnees/proposition.json"
        avant = chemin.read_bytes()
        ecrire = Path.write_text
        def interrompre(cible, texte, *args, **kwargs):
            if cible.parent == chemin.parent and cible.name.startswith("proposition"):
                ecrire(cible, texte[:10], *args, **kwargs)
                raise OSError("disque fictif interrompu")
            return ecrire(cible, texte, *args, **kwargs)
        self.run_mock.side_effect = lambda commande, **kwargs: self.module.subprocess.CompletedProcess(commande, 0, "", "")
        with patch.object(Path, "write_text", interrompre):
            retour = json.loads(self.requete("POST", "/api/masquer", {"itm8": CODE, "masquer": True})[1])
        self.assertTrue(retour["ok"])  # la décision est acquise, seule sa projection a échoué
        self.assertEqual(chemin.read_bytes(), avant)
        self.assertEqual(list(chemin.parent.glob("proposition-*.tmp")), [])

    def test_deux_decisions_concurrentes_ne_perdent_pas_la_projection(self):
        lecture = Path.read_text
        appels = {}
        rendez_vous = threading.Barrier(2)

        def lire(chemin, *args, **kwargs):
            texte = lecture(chemin, *args, **kwargs)
            if chemin == self.root / "donnees/proposition.json":
                ident = threading.get_ident()
                appels[ident] = appels.get(ident, 0) + 1
                if appels[ident] == 2:
                    time.sleep(0.15)  # retour d'une même ancienne projection aux deux écrivains
            return texte

        def script(commande, **kwargs):
            if Path(commande[1]).name == "appliquer-decision.py":
                self.assertIn("ARTICLE TEST", commande[-1])
                self.assertNotIn("LIBELLE CLIENT", commande[-1])
            return self.module.subprocess.CompletedProcess(commande, 0, "", "")

        def envoyer(cas):
            rendez_vous.wait(5)
            return json.loads(self.requete("POST", cas[0], cas[1])[1])

        self.run_mock.side_effect = script
        cas = [("/api/masquer", {"itm8": CODE, "libelle": "LIBELLE CLIENT", "masquer": True}),
               ("/api/fournisseur", {"itm8": CODE, "libelle": "LIBELLE CLIENT", "fournisseur": "TEST"})]
        with patch.object(Path, "read_text", lire), ThreadPoolExecutor(2) as pool:
            retours = list(pool.map(envoyer, cas))
        self.assertTrue(all(r["ok"] for r in retours))
        ligne = json.loads((self.root / "donnees/proposition.json").read_text(encoding="utf-8"))["lignes"][0]
        self.assertTrue(ligne.get("masque"))
        self.assertEqual(ligne.get("fournisseur"), "TEST")

    def test_decisions_validees_avant_de_lancer_un_ecrivain(self):
        cas = [("/api/masquer", {"itm8": CODE}),
               ("/api/masquer", {"itm8": CODE, "masquer": "false"}),
               ("/api/masquer", {"itm8": "0000000000000", "masquer": True}),
               ("/api/masquer", {"itm8": " " + CODE, "masquer": True}),
               ("/api/fournisseur", {"itm8": "0000000000000", "fournisseur": "TEST"}),
               ("/api/fournisseur", {"itm8": CODE, "fournisseur": "--simuler"}),
               ("/api/fournisseur", {"itm8": CODE, "fournisseur": "TEST\nAUTRE"}),
               ("/api/fournisseur", {"itm8": CODE, "fournisseur": "x" * 81})]
        avant = (self.root / "donnees/proposition.json").read_bytes()
        for route, charge in cas:
            with self.subTest(route=route, charge=charge):
                retour = json.loads(self.requete("POST", route, charge)[1])
                self.assertFalse(retour["ok"])
                self.run_mock.assert_not_called()
        self.assertEqual((self.root / "donnees/proposition.json").read_bytes(), avant)

    def test_messages_dedupliques_dans_le_lot_et_entre_requetes_concurrentes(self):
        message = {"texte": "Message fictif", "ecrit_le": "2026-09-09T06:30:00.001Z"}
        self.ecrire("donnees/messages.jsonl", "")
        rendez_vous = threading.Barrier(8)

        def ouvrir(chemin, mode="r", *args, **kwargs):
            if Path(chemin).name == "messages.jsonl" and mode == "a":
                time.sleep(0.1)  # élargit la fenêtre read/dedup/append réelle
            return builtins.open(chemin, mode, *args, **kwargs)

        def envoyer(_):
            rendez_vous.wait(5)
            return json.loads(self.requete("POST", "/api/messages", {"messages": [message, message]})[1])

        with patch.object(self.module, "open", ouvrir, create=True), ThreadPoolExecutor(8) as pool:
            retours = list(pool.map(envoyer, range(8)))
        self.assertTrue(all(r["ok"] for r in retours))
        self.assertEqual(sum(r["enregistres"] for r in retours), 1)
        lignes = (self.root / "donnees/messages.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lignes), 1)
        self.assertEqual(json.loads(lignes[0])["texte"], message["texte"])

    def test_collision_identifiant_message_refuse_le_lot_sans_perte(self):
        message = {"texte": "Message fictif", "ecrit_le": "2026-09-09T06:30:00.001Z"}
        self.ecrire("donnees/messages.jsonl", json.dumps({"id": "message:" + message["ecrit_le"], **message}) + "\n")
        chemin = self.root / "donnees/messages.jsonl"
        avant = chemin.read_bytes()
        nouveau = {**message, "ecrit_le": "2026-09-09T06:31:00.001Z"}
        conflit = {**message, "texte": "Autre message"}
        retour = json.loads(self.requete("POST", "/api/messages", {"messages": [nouveau, conflit]})[1])
        self.assertFalse(retour["ok"])
        self.assertEqual(chemin.read_bytes(), avant)
        self.launch_mock.assert_not_called()

    def test_messages_valides_en_entier_avant_le_premier_ajout(self):
        valide = {"texte": "Message fictif", "ecrit_le": "2026-09-09T06:30:00.001Z"}
        chemin = self.root / "donnees/messages.jsonl"
        for invalide in (None, {"texte": 12, "ecrit_le": valide["ecrit_le"]},
                         {"texte": " ", "ecrit_le": valide["ecrit_le"]},
                         {"texte": "test"}, {"texte": "test", "ecrit_le": "2026-99-99T25:00:00Z"},
                         {"texte": "test", "ecrit_le": "2026-09-09"},
                         {"texte": "x" * 10001, "ecrit_le": valide["ecrit_le"]},
                         {"texte": "\ud800", "ecrit_le": valide["ecrit_le"]}):
            with self.subTest(invalide=repr(invalide)[:100]):
                self.ecrire("donnees/messages.jsonl", "")
                _, corps, _ = self.requete("POST", "/api/messages", {"messages": [valide, invalide]})
                self.assertFalse(json.loads(corps)["ok"])
                self.assertEqual(chemin.read_bytes(), b"")
        self.launch_mock.assert_not_called()
        self.assertFalse(self.module.JOURNAL.exists())

    def test_corps_json_limite_et_encadrement_http_non_ambigu(self):
        cas = [({"Content-Length": "1048577"}, b"{}", 413),
               ({"Content-Length": "-1"}, b"{}", 400),
               ({"Content-Length": "abc"}, b"{}", 400),
               ({"Content-Length": "20"}, b"{}", 400),
               ({"Content-Length": None}, b"{}", 411),
               ({"Content-Length": "2\r\nContent-Length: 2"}, b"{}", 400),
               ({"Transfer-Encoding": "chunked"}, b"{}", 400),
               ({"Content-Type": "text/plain"}, b"{}", 415),
               ({"Content-Type": "application/x-www-form-urlencoded"}, b"{}", 415),
               ({}, b"[]", 400), ({}, b"null", 400), ({}, b"{", 400),
               ({}, b'{"n":NaN}', 400), ({}, b'{"n":Infinity}', 400),
               ({}, b'{"messages":[],"messages":[]}', 400)]
        for extra, corps, attendu in cas:
            with self.subTest(extra=extra, corps=corps):
                entetes = {"Origin": "https://" + PUBLIC_HOST, "Content-Type": "application/json"}
                entetes.update(extra)
                statut, reponse, _ = self.requete("POST", "/api/messages", headers=entetes, corps=corps)
                self.assertEqual(statut, attendu)
                self.assertFalse(json.loads(reponse)["ok"])
        self.launch_mock.assert_not_called()
        self.assertFalse((self.root / "donnees/messages.jsonl").exists())

    def test_origine_et_hote_sont_controles_avant_toute_route(self):
        for headers in ({"Origin": "https://pirate.invalid"}, {"Origin": "null"},
                        {"Origin": None}, {"Origin": "https://" + PUBLIC_HOST + "\r\nOrigin: https://" + PUBLIC_HOST},
                        {"Host": PUBLIC_HOST + "\r\nHost: " + PUBLIC_HOST},
                        {"Origin": ""}, {"Host": "pirate.invalid"},
                        {"Host": PUBLIC_HOST + ".pirate.invalid"},
                        {"Host": PUBLIC_HOST + ":8080"},
                        {"Sec-Fetch-Site": "cross-site"}, {"Sec-Fetch-Site": "same-site"},
                        {"Host": "pirate.invalid", "X-Forwarded-Host": PUBLIC_HOST}):
            for route in ("/api/messages", "/api/comptages", "/api/masquer", "/api/fournisseur"):
                with self.subTest(headers=headers, route=route):
                    statut, corps, _ = self.requete("POST", route, {}, headers)
                    self.assertEqual(statut, 403)
                    self.assertFalse(json.loads(corps)["ok"])
        for methode in ("GET", "HEAD"):
            self.assertEqual(self.requete(methode, "/app/index.html", headers={"Host": "pirate.invalid"})[0], 403)
        # Fetch JSON actuel + clients navigateur sans Fetch Metadata.
        self.assertEqual(self.requete("POST", "/api/messages", {"messages": []})[0], 200)
        self.assertEqual(self.requete("POST", "/api/messages", {"messages": []}, {"Sec-Fetch-Site": None})[0], 200)
        host = "127.0.0.1:" + str(self.server.server_port)
        self.assertEqual(self.requete("POST", "/api/messages", {"messages": []},
                                     {"Host": host, "Origin": "http://" + host})[0], 200)
        self.run_mock.assert_not_called()
        self.launch_mock.assert_not_called()
        self.assertFalse((self.root / "donnees/messages.jsonl").exists())

    def test_get_et_head_ne_publient_que_les_fichiers_autorises(self):
        interdits = ("/AGENT.md", "/donnees/pouvoirs.json", "/app/", "/app/interne.py",
                     "/documents-partages/photos-produits/original.jpg", PHOTO + "-512.webp", "/app/img/produits/test.webp",
                     "/app/img/secret.txt", "/app/%252e%252e/AGENT.md",
                     "/app/%2e%2e/AGENT.md", "/app/..%5cAGENT.md",
                     "/app/index.html::$DATA", "/app/index.html%20",
                     "/app/%255c..%255cAGENT.md", "/donnees/faits/2026.jsonl.jsonl")
        for methode in ("GET", "HEAD"):
            for chemin in interdits:
                with self.subTest(methode=methode, chemin=chemin):
                    statut, corps, _ = self.requete(methode, chemin)
                    self.assertEqual(statut, 404)
                    self.assertNotIn(b"PRIVE TEST", corps)
            for chemin in ("/app/index.html?v=1", "/app/css/charte.css", "/favicon.ico",
                           PHOTO + "-96.webp", PHOTO + "-240.webp", "/app/js/photos-produits.js", "/donnees/photos.json",
                           "/Documents/Promo%20intermarche/offre%20test.png", "/donnees/faits/2026.jsonl"):
                with self.subTest(methode=methode, chemin=chemin):
                    statut, corps, _ = self.requete(methode, chemin)
                    self.assertEqual(statut, 200)
                    self.assertEqual(corps, b"" if methode == "HEAD" else b"PUBLIC TEST")


if __name__ == "__main__":
    unittest.main()
