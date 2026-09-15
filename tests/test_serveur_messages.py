import importlib.util
from datetime import date
import unittest
from unittest.mock import patch
from pathlib import Path

MOTEUR = Path(__file__).resolve().parents[1] / "moteur"
SPEC = importlib.util.spec_from_file_location("serveur", MOTEUR / "serveur.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ServeurMessagesTests(unittest.TestCase):
    def test_refuse_une_quantite_calculee_non_finie(self):
        code = "0000087003306"
        articles = {code: {"itm8": code, "conditionnement": 1e308}}
        with self.assertRaisesRegex(ValueError, "quantité"):
            MODULE.normaliser_comptage({"itm8": code, "date": date.today().isoformat(), "colis": 2,
                                       "saisi_le": date.today().isoformat() + "T08:00:00"}, articles)

    def test_refuse_un_comptage_invalide_avant_ecriture(self):
        articles = {"0000087003306": {"itm8": "0000087003306", "libelle": "MELON PIECE", "conditionnement": 12, "unite": "Pièce"}}

        with self.assertRaisesRegex(ValueError, "date de comptage"):
            MODULE.normaliser_comptage(
                {"itm8": "0000087003306", "date": "2099-mauvais", "colis": 2}, articles
            )
        with self.assertRaisesRegex(ValueError, "inconnu de la liste"):
            MODULE.normaliser_comptage(
                {"itm8": "inconnu", "date": date.today().isoformat(), "colis": 2}, articles
            )
        with self.assertRaisesRegex(ValueError, "nombre fini"):
            MODULE.normaliser_comptage(
                {"itm8": "0000087003306", "date": date.today().isoformat(), "colis": float("nan")}, articles
            )
    def test_serveur_reste_lie_a_la_boucle_locale(self):
        with patch.object(MODULE, 'ServeurHTTP') as serveur, \
                patch.object(MODULE, 'journaliser'), \
                patch.object(MODULE.sys, 'argv', ['serveur.py', '8751']):
            MODULE.main()
        serveur.assert_called_once_with(('127.0.0.1', 8751), MODULE.Gestionnaire)
        serveur.return_value.serve_forever.assert_called_once_with()

    def test_sert_licone_de_lapplication_a_la_racine(self):
        source = (MOTEUR / "serveur.py").read_text(encoding="utf-8")

        self.assertIn("def do_GET(self):", source)
        self.assertIn('self.path = "/app/img/favicon.ico"', source)

    def test_refuse_un_corps_json_invalide_avec_un_message_explicite(self):
        with self.assertRaisesRegex(ValueError, "message reçu est illisible"):
            MODULE.decoder_requete_json(b"not-json")

    def test_construit_la_commande_de_reponse_sans_utiliser_le_texte_comme_shell(self):
        commande = MODULE.commande_reponse_message("message:abc", "question ; & non exécutée")
        self.assertEqual(commande[:3], [MODULE.sys.executable, str(MOTEUR / "repondre-message-rayon.py"), "--id"])
        self.assertEqual(commande[-2:], ["--texte", "question ; & non exécutée"])


if __name__ == "__main__":
    unittest.main()
