import importlib.util
import unittest
from pathlib import Path

MOTEUR = Path(__file__).resolve().parents[1] / "moteur"
SPEC = importlib.util.spec_from_file_location("repondre_message_rayon", MOTEUR / "repondre-message-rayon.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PromptMessageRayonTests(unittest.TestCase):
    def test_construit_un_prompt_qui_preserve_le_message_et_l_identifiant(self):
        prompt = MODULE.construire_prompt("message:2026-09-06T17:00:40.679Z", "as-tu traité tous les mails?")
        self.assertIn("message:2026-09-06T17:00:40.679Z", prompt)
        self.assertIn("as-tu traité tous les mails?", prompt)
        self.assertIn("moteur/dire.py", prompt)
        self.assertIn("ne jamais inventer", prompt.lower())


if __name__ == "__main__":
    unittest.main()
