"""Sécurité transport : mocks uniquement, aucune connexion réseau."""
import importlib.util
import io
from pathlib import Path
import ssl
import sys
import unittest
from contextlib import redirect_stderr
from unittest.mock import MagicMock, patch

SCRIPT = Path(__file__).resolve().parents[1] / "moteur/envoyer-classeur-marge.py"
spec = importlib.util.spec_from_file_location("envoi_securite", SCRIPT)
envoi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(envoi)


class TLSVerificationTests(unittest.TestCase):
    def test_cli_exige_classeur_explicite_ne_choisit_jamais_septembre(self):
        with patch.object(sys, "argv", ["envoi", "--destinataire", "test@example.invalid", "--simuler"]), \
             patch.object(envoi, "lit_env_mail", side_effect=AssertionError("Configuration ne doit pas être lue")), \
             redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as erreur:
                envoi.main()
        self.assertEqual(erreur.exception.code, 2)

    def test_ssl_et_starttls_verifient_certificat_et_nom_avant_login(self):
        for port in (465, 587):
            with self.subTest(port=port):
                client = MagicMock()
                client.__enter__.return_value = client
                client.send_message.return_value = {}
                config = {"EMAIL_SMTP_HOST": "smtp.invalid", "EMAIL_SMTP_PORT": str(port),
                          "EMAIL_ADDRESS": "test@example.invalid", "EMAIL_PASSWORD": "fixture"}
                with patch.object(envoi.smtplib, "SMTP_SSL", return_value=client) as ssl_client, \
                     patch.object(envoi.smtplib, "SMTP", return_value=client):
                    envoi.envoie_message(config, object())
                kwargs = ssl_client.call_args.kwargs if port == 465 else client.starttls.call_args.kwargs
                self.assertIn("context", kwargs)
                self.assertEqual(kwargs["context"].verify_mode, ssl.CERT_REQUIRED)
                self.assertTrue(kwargs["context"].check_hostname)

    def test_certificat_refuse_interdit_login_et_envoi(self):
        for port in (465, 587):
            with self.subTest(port=port):
                client = MagicMock()
                client.__enter__.return_value = client
                erreur = ssl.SSLCertVerificationError("fixture non fiable")
                if port != 465:
                    client.starttls.side_effect = erreur
                config = {"EMAIL_SMTP_HOST": "smtp.invalid", "EMAIL_SMTP_PORT": str(port),
                          "EMAIL_ADDRESS": "test@example.invalid", "EMAIL_PASSWORD": "fixture"}
                with patch.object(envoi.smtplib, "SMTP_SSL", side_effect=erreur), \
                     patch.object(envoi.smtplib, "SMTP", return_value=client):
                    with self.assertRaises(ssl.SSLCertVerificationError):
                        envoi.envoie_message(config, object())
                client.login.assert_not_called()
                client.send_message.assert_not_called()


if __name__ == "__main__":
    unittest.main()
