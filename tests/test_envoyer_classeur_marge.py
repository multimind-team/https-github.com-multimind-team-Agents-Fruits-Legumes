import hashlib
import importlib.util
import unittest
from email import policy
from email.parser import BytesParser
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
SCRIPT = RACINE / "moteur" / "envoyer-classeur-marge.py"
CLASSEUR = RACINE / "documents-partages" / "calcul-marge-pomona" / "0926 Calcul marge Pomona.xlsx"


def charge_module():
    spec = importlib.util.spec_from_file_location("envoyer_classeur_marge", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class EnvoiClasseurMargeTests(unittest.TestCase):
    def test_construit_un_email_avec_le_classeur_binaire_exact(self):
        module = charge_module()

        message = module.construit_message(
            expediteur="test@example.invalid",
            destinataire="dest@example.invalid",
            classeur=CLASSEUR,
            sujet="Calcul de marge Pomona",
            corps="Classeur de marge Pomona en pièce jointe.",
        )
        recu = BytesParser(policy=policy.default).parsebytes(message.as_bytes())
        pieces = list(recu.iter_attachments())

        self.assertEqual(recu["Subject"], "Calcul de marge Pomona")
        self.assertEqual(len(pieces), 1)
        self.assertEqual(pieces[0].get_filename(), CLASSEUR.name)
        self.assertEqual(
            hashlib.sha256(pieces[0].get_payload(decode=True)).hexdigest(),
            hashlib.sha256(CLASSEUR.read_bytes()).hexdigest(),
        )


if __name__ == "__main__":
    unittest.main()
