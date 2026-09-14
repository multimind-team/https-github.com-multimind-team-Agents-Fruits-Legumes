"""Contrôles HTTP sur ports éphémères et verrous dans un dossier temporaire."""
import importlib.util
import subprocess
import sys
import tempfile
import threading
import inspect
import shutil
import unittest
from unittest import mock
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]


def charge_module(nom="surveiller-serveur"):
    spec = importlib.util.spec_from_file_location(nom.replace("-", "_"), RACINE / "moteur" / f"{nom}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SanteHttpTests(unittest.TestCase):
    def test_un_200_non_html_n_est_pas_l_application(self):
        module = charge_module()

        class Handler(BaseHTTPRequestHandler):
            code = 200
            content_type = "application/json"

            def do_GET(self):
                self.send_response(self.code)
                self.send_header("Content-Type", self.content_type)
                self.end_headers()
                self.wfile.write(b"{}")

            def log_message(self, *args):
                pass

        serveur = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=serveur.serve_forever, daemon=True)
        thread.start()
        try:
            port = serveur.server_address[1]
            self.assertFalse(module.application_repond(port))
            Handler.content_type = "text/html; charset=utf-8"
            self.assertTrue(module.application_repond(port))
            Handler.code = 503
            self.assertFalse(module.application_repond(port))
        finally:
            serveur.shutdown()
            serveur.server_close()
            thread.join(timeout=5)
        self.assertFalse(module.application_repond(port))


class VerrouTests(unittest.TestCase):
    def test_verrou_exclusif_interprocessus_et_reutilisable_apres_liberation(self):
        module = charge_module("gerer-serveur")
        self.assertTrue(hasattr(module, "VerrouLocal"), "Verrou interprocessus manquant")
        with tempfile.TemporaryDirectory() as dossier:
            verrou = Path(dossier) / "watchdog.lock"
            code = (
                "import importlib.util, sys\n"
                "spec=importlib.util.spec_from_file_location('gestion', sys.argv[1])\n"
                "m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n"
                "try:\n"
                " with m.VerrouLocal(sys.argv[2]): pass\n"
                "except m.VerrouOccupe: sys.exit(3)\n"
            )
            commande = [sys.executable, "-B", "-c", code, str(RACINE / "moteur" / "gerer-serveur.py"), str(verrou)]
            with module.VerrouLocal(verrou):
                bloque = subprocess.run(commande, capture_output=True, timeout=10)
                self.assertEqual(bloque.returncode, 3, bloque.stderr)
            libre = subprocess.run(commande, capture_output=True, timeout=10)
            self.assertEqual(libre.returncode, 0, libre.stderr)
            self.assertTrue(verrou.exists(), "Ne pas supprimer un inode de verrou partagé")


class CycleSurveillanceTests(unittest.TestCase):
    def test_arret_demande_persistant_et_doublon_quittent_sans_demarrer(self):
        module = charge_module()
        self.assertIn("argv", inspect.signature(module.main).parameters,
                      "La surveillance doit avoir un cycle testable")
        with tempfile.TemporaryDirectory() as dossier:
            racine = Path(dossier)
            journal = racine / "surveillance-serveur.log"
            journal.write_text("historique\n", encoding="utf-8")
            with mock.patch.object(module, "RACINE", racine), mock.patch.object(module, "JOURNAL", journal):
                with mock.patch.object(module.gestion, "inventaire_windows", side_effect=AssertionError("aucun inventaire nécessaire")):
                    (racine / ".serveur-arrete").write_text("pause", encoding="utf-8")
                    self.assertEqual(module.main(["--une-fois"]), 0)
                    (racine / ".serveur-arrete").unlink()
                    with module.gestion.VerrouLocal(racine / ".surveillance-serveur.lock"):
                        self.assertEqual(module.main(["--une-fois"]), 0)
            texte = journal.read_text(encoding="utf-8")
            self.assertTrue(texte.startswith("historique\n"))
            self.assertIn("maintenance", texte.lower())
            self.assertIn("déjà active", texte.lower())

    def test_cycle_normal_utilise_le_gestionnaire_cible_et_ne_journalise_pas_les_secrets(self):
        module = charge_module()
        self.assertIn("argv", inspect.signature(module.main).parameters,
                      "La surveillance doit avoir un cycle testable")
        with tempfile.TemporaryDirectory() as dossier:
            racine = Path(dossier)
            journal = racine / "surveillance-serveur.log"
            with mock.patch.object(module, "RACINE", racine), mock.patch.object(module, "JOURNAL", journal):
                with mock.patch.object(module.gestion, "GestionServeur") as fabrique:
                    fabrique.return_value.demarrer.side_effect = RuntimeError("SECRET_A_NE_PAS_LOGUER")
                    self.assertEqual(module.main(["--une-fois"]), 1)
                    fabrique.return_value.demarrer.assert_called_once_with(automatique=True)
            texte = journal.read_text(encoding="utf-8")
            self.assertIn("RuntimeError", texte)
            self.assertNotIn("SECRET_A_NE_PAS_LOGUER", texte)


if __name__ == "__main__":
    unittest.main()
