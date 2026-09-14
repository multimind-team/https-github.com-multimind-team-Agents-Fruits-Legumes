"""Limites des ajustements : moteur copié et carnets exclusivement temporaires."""
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path
from unittest.mock import patch

from verifier_factures_isolees import garde

# Refuser une éventuelle écriture réelle avant le premier import du moteur.
sys.dont_write_bytecode = True
sys.addaudithook(garde)
RACINE = Path(__file__).resolve().parents[1]
MOTIF = "Fixture isolée : les ventes observées justifient cette suggestion de test."


class DateFixe(date):
    @classmethod
    def today(cls):
        return cls(2026, 9, 9)


def charger(nom, fichier):
    spec = importlib.util.spec_from_file_location(nom, fichier)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AjustementsLimitesTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.racine = Path(temp.name)
        moteur = self.racine / "moteur"
        moteur.mkdir()
        donnees = self.racine / "donnees"
        donnees.mkdir()
        for nom in ("ajuster-commande.py", "journal_agents.py"):
            (moteur / nom).write_bytes((RACINE / "moteur" / nom).read_bytes())
        (donnees / "pouvoirs.json").write_bytes((RACINE / "donnees/pouvoirs.json").read_bytes())
        journal = charger("journal_limites_fixture", moteur / "journal_agents.py")
        # Ni import partagé ni constante de chemin ne peuvent pointer vers les carnets réels.
        with patch.dict(sys.modules, {"journal_agents": journal}), patch.object(sys, "path", sys.path.copy()):
            self.cli = charger("ajuster_limites_fixture", moteur / "ajuster-commande.py")
        self.enterContext(patch.object(self.cli, "date", DateFixe))
        self.proposition()

    def proposition(self, avant=10, jour="2026-09-10"):
        self.cli.PROPOSITION.write_text(json.dumps({
            "date_commande": jour,
            "lignes": [{"itm8": "TEST", "libelle": "Article fixture", "propose_colis": avant}],
        }), encoding="utf-8")

    def appeler(self, colis="11", agent="agent-tendances"):
        arguments = [str(self.cli.__file__), "--agent", agent, "--proposer", "--motif", MOTIF,
                     "--", "TEST", str(colis)]
        with patch.object(sys, "argv", arguments), redirect_stdout(io.StringIO()):
            return self.cli.main()

    def etat(self):
        return {str(p.relative_to(self.racine)): p.read_bytes()
                for p in (self.racine / "donnees").rglob("*") if p.is_file()}

    def test_verifier_refuse_quantites_non_finies_meme_sans_limite_de_role(self):
        for agent in ("agent-tendances", "responsable-rayon"):
            for valeur in (float("nan"), float("inf"), float("-inf")):
                for avant, apres in ((10, valeur), (valeur, 11)):
                    with self.subTest(agent=agent, avant=avant, apres=apres):
                        with self.assertRaisesRegex(SystemExit, "fini"):
                            self.cli.verifier(agent, "TEST", avant, apres, False)

    def test_cli_refuse_quantites_non_finies_avant_toute_ecriture(self):
        for valeur in (float("nan"), float("inf"), float("-inf")):
            for avant, apres in ((10, valeur), (valeur, 11)):
                with self.subTest(avant=avant, apres=apres):
                    self.proposition(avant=avant)
                    etat = self.etat()
                    with self.assertRaises(SystemExit):
                        self.appeler(apres)
                    self.assertEqual(self.etat(), etat)

    def carnet(self, nombre, jour, prefixe="FIXTURE"):
        with self.cli.FICHIER.open("a", encoding="utf-8") as fichier:
            for indice in range(nombre):
                fichier.write(json.dumps({
                    "date_commande": jour, "article": f"{prefixe}-{indice}",
                    "libelle": "Article fixture", "avant": 10, "apres": 11,
                    "applique": False, "agent": "agent-tendances", "motif": MOTIF,
                }) + "\n")

    def test_onzieme_suggestion_refusee_pour_la_commande_de_demain(self):
        self.carnet(10, "2026-09-10")
        self.assertEqual(len(self.cli.lire("2026-09-10")), 10)
        self.assertEqual(len(self.cli.lire()), 0)
        etat = self.etat()
        with self.assertRaisesRegex(SystemExit, "maximum.*10"):
            self.appeler()
        self.assertEqual(self.etat(), etat)

    def test_dixieme_suggestion_acceptee_sans_compter_la_commande_du_jour(self):
        self.carnet(10, "2026-09-09", prefixe="AUJOURDHUI")
        self.carnet(9, "2026-09-10", prefixe="DEMAIN")
        prefixe = self.cli.FICHIER.read_bytes()
        self.assertEqual(self.appeler(), 0)
        self.assertTrue(self.cli.FICHIER.read_bytes().startswith(prefixe))
        ajustements = self.cli.lire("2026-09-10")
        self.assertEqual(len(ajustements), 10)
        self.assertEqual(len(self.cli.lire("2026-09-09")), 10)
        self.assertEqual(ajustements["TEST"]["date_commande"], "2026-09-10")
        self.assertEqual(ajustements["TEST"]["apres"], 11)
        self.assertFalse(ajustements["TEST"]["applique"])
        self.assertEqual(self.cli.journal_agents.lire()[-1]["details"]["date_commande"], "2026-09-10")

    def test_date_cible_invalide_refusee_sans_normalisation_ni_ecriture(self):
        for jour in (None, "", 20260910, "20260910", "2026-W37-4", "2026-9-10",
                     "2026-02-30", "2026-09-10 ", "2026-09-10T00:00:00"):
            with self.subTest(jour=jour):
                self.proposition(jour=jour)
                etat = self.etat()
                with self.assertRaisesRegex(SystemExit, "[Dd]ate.*AAAA-MM-JJ"):
                    self.appeler()
                self.assertEqual(self.etat(), etat)


if __name__ == "__main__":
    unittest.main()
