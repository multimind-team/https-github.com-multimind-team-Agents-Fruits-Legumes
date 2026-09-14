"""Tests isolés : ne jamais lancer ni arrêter les processus de production."""
import importlib.util
import os
import subprocess
import sys
import shutil
import socket
import tempfile
import unittest
from unittest import mock
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
SCRIPT = RACINE / "moteur" / "gerer-serveur.py"


def charge_module():
    assert SCRIPT.exists(), "Le gestionnaire sûr des processus doit exister."
    spec = importlib.util.spec_from_file_location("gestion_serveur_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def processus(script, *args, pid=123):
    executable = sys.executable
    return {"pid": pid, "executable": executable,
            "command_line": subprocess.list2cmdline([executable, str(script), *args]),
            "created": 123456}


class IdentiteProcessusTests(unittest.TestCase):
    def test_identifie_uniquement_le_script_absolu_executable_du_projet(self):
        module = charge_module()
        cible = RACINE / "moteur" / "serveur.py"
        self.assertTrue(module.processus_du_projet(processus(cible, "8751"), cible, 8751))
        for autre in [
            processus(RACINE.parent / "autre" / "moteur" / "serveur.py", "8751"),
            processus("moteur/serveur.py", "8751"),
            processus(cible, "8752"),
            processus("-c", "print('rien')", str(cible), "8751"),
            processus("-m", "http.server", "8751", str(cible)),
        ]:
            with self.subTest(commande=autre["command_line"]):
                self.assertFalse(module.processus_du_projet(autre, cible, 8751))
        inconnu = processus(cible, "8751")
        inconnu["command_line"] = None
        self.assertFalse(module.processus_du_projet(inconnu, cible, 8751))


@unittest.skipUnless(os.name == "nt", "Intégration Windows")
class InventaireArretTests(unittest.TestCase):
    def test_inventaire_reel_et_arret_du_seul_enfant_identifie(self):
        module = charge_module()
        self.assertTrue(hasattr(module, "inventaire_windows"), "Inventaire sûr manquant")
        with tempfile.TemporaryDirectory(prefix="commande gestion ") as dossier, socket.socket() as prise:
            prise.bind(("127.0.0.1", 0))
            prise.listen()
            port = prise.getsockname()[1]
            cible = Path(dossier) / "serveur.py"
            cible.write_text("import time; time.sleep(60)\n", encoding="utf-8")
            enfant = subprocess.Popen([sys.executable, "-u", str(cible)])
            try:
                inventaire = module.inventaire_windows(port)
                self.assertIn(os.getpid(), inventaire["listeners"])
                lignes = [p for p in inventaire["processes"] if p["pid"] == enfant.pid]
                self.assertEqual(len(lignes), 1)
                identite = lignes[0]
                self.assertTrue(module.processus_du_projet(identite, cible))
                faux = dict(identite, created=int(identite["created"]) + 10)
                with self.assertRaises(module.GestionErreur):
                    module.arreter_processus(faux, cible)
                self.assertIsNone(enfant.poll(), "Un PID réutilisé ne doit jamais être tué")
                with self.assertRaises(module.GestionErreur):
                    module.arreter_processus(identite, RACINE / "moteur" / "serveur.py")
                self.assertIsNone(enfant.poll(), "Un autre script ne doit jamais être tué")
                module.arreter_processus(identite, cible)
                enfant.wait(timeout=5)
                self.assertIsNotNone(enfant.returncode)
            finally:
                if enfant.poll() is None:
                    enfant.terminate()
                    enfant.wait(timeout=5)


class GestionPrudenteTests(unittest.TestCase):
    def test_cycle_cible_arrete_watchdog_avant_serveur_et_maintenance_persistante(self):
        module = charge_module()
        with tempfile.TemporaryDirectory() as dossier:
            racine = Path(dossier)
            (racine / "moteur").mkdir()
            (racine / "moteur" / "serveur.py").write_text("# fixture", encoding="utf-8")
            (racine / "moteur" / "surveiller-serveur.py").write_text("# fixture", encoding="utf-8")
            etat = {"listeners": [], "processes": []}
            arrets, lancements = [], []

            def lance(script, arguments, cwd, stdout, stderr):
                pid = 200 + len(lancements)
                lancements.append(script)
                etat["processes"].append(processus(script, *arguments, pid=pid))
                etat["listeners"] = [pid]
                return mock.Mock(pid=pid, poll=lambda: None)

            def termine(proces, script, port=None):
                arrets.append(proces["pid"])
                etat["processes"] = [p for p in etat["processes"] if p["pid"] != proces["pid"]]
                etat["listeners"] = [p for p in etat["listeners"] if p != proces["pid"]]

            gestion = module.GestionServeur(
                racine=racine, inventaire=lambda port: etat, termine=termine,
                lance=lance, verifie=lambda port: bool(etat["listeners"]),
            )
            self.assertEqual(gestion.demarrer(), "demarre")
            etat["processes"].extend([
                processus(gestion.surveillance, "--intervalle", "30", pid=301),
                processus(racine / "autre.py", pid=999),
            ])
            self.assertEqual(gestion.demarrer(redemarrer=True), "demarre")
            self.assertEqual(arrets, [301, 200])
            self.assertEqual(len(lancements), 2)
            etat["processes"].append(processus(gestion.surveillance, pid=302))
            self.assertEqual(gestion.arreter(), "arrete")
            self.assertEqual(arrets, [301, 200, 302, 201])
            self.assertEqual([p["pid"] for p in etat["processes"]], [999])
            self.assertTrue((racine / ".serveur-arrete").exists())
            self.assertEqual(gestion.demarrer(automatique=True), "maintenance")
            self.assertEqual(len(lancements), 2)
            self.assertEqual(gestion.demarrer(), "demarre")
            self.assertFalse((racine / ".serveur-arrete").exists())

    def test_conserve_serveur_sain_et_refuse_la_relance_implicite_d_un_serveur_bloque(self):
        module = charge_module()
        with tempfile.TemporaryDirectory() as dossier:
            racine = Path(dossier)
            serveur = processus(racine / "moteur" / "serveur.py", "8751")
            etat = {"listeners": [serveur["pid"]], "processes": [serveur]}
            arrets, lancements = [], []
            sain = [True]
            gestion = module.GestionServeur(
                racine=racine, inventaire=lambda port: etat,
                termine=lambda *args: arrets.append(args),
                lance=lambda *args: lancements.append(args), verifie=lambda port: sain[0],
            )
            self.assertEqual(gestion.demarrer(), "actif")
            sain[0] = False
            with self.assertRaisesRegex(module.GestionErreur, "--redemarrer"):
                gestion.demarrer()
            self.assertEqual(arrets, [])
            self.assertEqual(lancements, [])

    def test_refuse_un_port_etranger_meme_si_http_200_et_redemarrage_demande(self):
        module = charge_module()
        self.assertTrue(hasattr(module, "GestionServeur"), "Gestion prudente manquante")
        with tempfile.TemporaryDirectory() as dossier:
            racine = Path(dossier)
            serveur = processus(racine / "moteur" / "serveur.py", "8751")
            inventaire = {"listeners": [999], "processes": [serveur]}
            arrets, lancements = [], []
            gestion = module.GestionServeur(
                racine=racine, inventaire=lambda port: inventaire,
                termine=lambda *args: arrets.append(args),
                lance=lambda *args: lancements.append(args), verifie=lambda port: True,
            )
            for redemarrer in (False, True):
                with self.subTest(redemarrer=redemarrer), self.assertRaisesRegex(module.GestionErreur, "autre processus"):
                    gestion.demarrer(redemarrer=redemarrer)
            self.assertEqual(arrets, [])
            self.assertEqual(lancements, [])


class LancementJournaliseTests(unittest.TestCase):
    def test_pythonw_lance_python_console_et_conserve_les_journaux(self):
        module = charge_module()
        self.assertTrue(hasattr(module, "lancer_script"), "Lancement journalisé manquant")
        with tempfile.TemporaryDirectory(prefix="commande logs ") as dossier:
            racine = Path(dossier)
            cible = racine / "enfant.py"
            cible.write_text("import sys; print(sys.executable); print('diagnostic', file=sys.stderr)\n", encoding="utf-8")
            sortie, erreurs = racine / "serveur.log", racine / "serveur-erreurs.log"
            sortie.write_bytes(b"historique-sortie\n")
            erreurs.write_bytes(b"historique-erreurs\n")
            pythonw = str(Path(sys.executable).with_name("pythonw.exe"))
            with mock.patch.object(module.sys, "executable", pythonw):
                enfant = module.lancer_script(cible, [], racine, sortie, erreurs)
                self.assertEqual(enfant.wait(timeout=5), 0)
            stdout, stderr = sortie.read_text(), erreurs.read_text()
            self.assertTrue(stdout.startswith("historique-sortie\n"))
            self.assertIn("python.exe", stdout.lower())
            self.assertNotIn("pythonw.exe", stdout.lower())
            self.assertEqual(stderr, "historique-erreurs\ndiagnostic\n")


@unittest.skipUnless(os.name == "nt", "Intégration Windows")
class CycleCliIsoleTests(unittest.TestCase):
    def test_cli_demarrage_idempotent_redemarrage_et_arret_sans_reprise(self):
        module = charge_module()
        self.assertTrue(hasattr(module, "main"), "CLI sûre manquante")
        with tempfile.TemporaryDirectory(prefix="commande cycle ") as dossier:
            racine = Path(dossier)
            moteur = racine / "moteur"
            moteur.mkdir()
            for nom in ("gerer-serveur.py", "surveiller-serveur.py"):
                shutil.copyfile(RACINE / "moteur" / nom, moteur / nom)
            (racine / "app").mkdir()
            (racine / "app" / "index.html").write_text("<!doctype html><title>Fixture isolée</title>", encoding="utf-8")
            (moteur / "serveur.py").write_text(
                "import sys\nfrom http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler\n"
                "print('demarrage-fixture', flush=True)\n"
                "ThreadingHTTPServer(('127.0.0.1', int(sys.argv[1])), SimpleHTTPRequestHandler).serve_forever()\n",
                encoding="utf-8",
            )
            with socket.socket() as prise:
                prise.bind(("127.0.0.1", 0))
                port = prise.getsockname()[1]
            gestion = module.GestionServeur(racine, port)

            def cli(action, *arguments):
                resultat = subprocess.run(
                    [sys.executable, "-B", str(moteur / "gerer-serveur.py"), action,
                     "--port", str(port), "--silencieux", *arguments],
                    capture_output=True, timeout=100,
                )
                self.assertEqual(resultat.returncode, 0, (resultat.stdout, resultat.stderr))
                return resultat

            try:
                cli("demarrer")
                vue, serveurs, veilles, etrangers = gestion.inspecter()
                self.assertFalse(etrangers)
                self.assertEqual(len(serveurs), 1)
                self.assertEqual(len(veilles), 1)
                self.assertEqual(Path(serveurs[0]["executable"]).name.lower(), "python.exe")
                premier_pid = serveurs[0]["pid"]
                cli("demarrer")
                self.assertEqual(gestion.inspecter()[1][0]["pid"], premier_pid)
                cli("etat")
                cli("demarrer", "--redemarrer")
                _, serveurs, veilles, _ = gestion.inspecter()
                self.assertNotEqual(serveurs[0]["pid"], premier_pid)
                self.assertEqual(len(veilles), 1)
                self.assertEqual((racine / "serveur.log").read_text().count("demarrage-fixture"), 2)
                cli("arreter")
                self.assertEqual(gestion.inspecter()[1:3], ([], []))
                self.assertFalse(module.application_repond(port))
                self.assertTrue(gestion.pause.exists())
                veille = subprocess.run(
                    [sys.executable, "-B", str(moteur / "surveiller-serveur.py"),
                     "--port", str(port), "--une-fois"], capture_output=True, timeout=15,
                )
                self.assertEqual(veille.returncode, 0, veille.stderr)
                self.assertFalse(module.application_repond(port))
            finally:
                gestion.arreter()


class LanceursBatTests(unittest.TestCase):
    def test_lanceurs_surs_transmettent_les_erreurs_sans_pause(self):
        for nom in ("demarrer-serveur.bat", "arreter-serveur.bat", "verifier-avant-commande.bat"):
            with self.subTest(lanceur=nom):
                texte = (RACINE / nom).read_text(encoding="utf-8").lower()
                self.assertNotIn("stop-process", texte, "Ne jamais arrêter un simple propriétaire du port")
                self.assertIn("exit /b", texte, "Le code de sortie doit être conservé")
                if nom != "verifier-avant-commande.bat":
                    self.assertIn("gerer-serveur.py", texte)
                # Option invalide : argparse doit refuser AVANT toute action système.
                resultat = subprocess.run(
                    ["cmd.exe", "/d", "/c", nom, "--option-invalide", "--silencieux"],
                    cwd=RACINE, capture_output=True, timeout=15,
                )
                self.assertEqual(resultat.returncode, 2, (resultat.stdout, resultat.stderr))


if __name__ == "__main__":
    unittest.main()
