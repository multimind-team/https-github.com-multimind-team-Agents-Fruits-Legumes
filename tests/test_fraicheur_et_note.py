import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

MOTEUR = Path(__file__).resolve().parents[1] / "moteur"
sys.path.insert(0, str(MOTEUR))


def charger(nom, fichier):
    spec = importlib.util.spec_from_file_location(nom, MOTEUR / fichier)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


FILET = charger("filet_de_securite", "filet-de-securite.py")
NOTE = charger("note_du_matin", "note-du-matin.py")
GENERER = charger("generer_proposition", "generer-proposition.py")


class FraicheurEtNoteTests(unittest.TestCase):
    def test_echec_amont_ne_publie_pas_une_nouvelle_proposition_ni_un_succes(self):
        with patch.object(sys, 'argv', ['filet-de-securite.py', '--forcer']), \
             patch.object(FILET, 'etat_proposition', return_value=('a-jour', 'ancienne proposition présentable', {})), \
             patch.object(FILET, 'lancer', return_value=(False, 'conflit de faits')) as lancer, \
             patch.object(FILET, 'marquer_fraicheur') as marquer, \
             patch.object(FILET.journal_agents, 'echec'), \
             patch.object(FILET.journal_agents, 'enregistrer'):
            self.assertEqual(FILET.main(), 1)
            self.assertEqual([c.args[0] for c in lancer.call_args_list], ['agregats.py'])
            self.assertNotEqual(marquer.call_args.args[0], 'a-jour')
            self.assertIn('ancienne', marquer.call_args.args[1])

    def _etat_proposition(self, contenu, jour_attendu):
        """Évalue une proposition isolée sans toucher aux données métier."""
        with tempfile.TemporaryDirectory() as dossier:
            proposition = Path(dossier) / "proposition.json"
            proposition.write_text(json.dumps(contenu), encoding="utf-8")

            class DateFigee(FILET.date):
                @classmethod
                def today(cls):
                    return cls(2026, 9, 9)

            with patch.object(FILET, "PROPOSITION", proposition), \
                 patch.object(FILET, "date", DateFigee), \
                 patch.object(FILET, "jour_de_commande", return_value=jour_attendu):
                return FILET.etat_proposition()

    def test_ne_surveille_pas_casse_ni_don_comme_flux_obligatoires(self):
        self.assertEqual(NOTE.FLUX_A_SURVEILLER, {"vente", "livraison"})

    def test_la_date_de_calcul_suit_le_stock_compte_et_les_livraisons(self):
        etat = {"calcule_jusquau": "2026-09-09", "date_base_commande": "2026-09-08"}

        self.assertEqual(GENERER.date_de_calcul(etat, "2026-09-04", maintenant=FILET.datetime(2026, 9, 9, 6, 27)), "2026-09-08")

    def test_le_filet_saute_aussi_les_fermetures_variables_confirmees(self):
        with tempfile.TemporaryDirectory() as dossier:
            racine = Path(dossier)
            (racine / "donnees").mkdir()
            (racine / "donnees/ouverture-jours-feries.json").write_text(json.dumps({
                "jours": {"2026-11-11": {"statut": "ferme"}},
            }), encoding="utf-8")
            with patch.object(FILET, "RACINE", racine):
                self.assertEqual(FILET.jour_de_commande(maintenant=FILET.datetime(2026, 11, 11, 6, 27)), "2026-11-12")

    def test_le_message_legacy_alerte_sur_la_date_sans_bilan_chiffre(self):
        etat, message, _ = self._etat_proposition({
            "date_commande": "2026-09-09", "date_stock": "2026-09-09",
            "date_stock_verifiee": "2026-09-07", "date_reference": "2026-09-04", "lignes": [{}, {}],
            "couverture_stock": {"articles_avec_position": 2, "articles_sorties_a_verifier": 1,
                                 "articles_sans_position": 12, "articles_sans_mapping": 3},
        }, "2026-09-09")
        self.assertEqual(etat, "donnees-en-retard")
        self.assertIn("2026-09-07", message)
        self.assertIn("fichier des ventes", message)
        self.assertIn("intégration", message)
        self.assertNotIn("1 article", message)
        self.assertNotIn("12", message)

    def test_apres_la_cloture_la_prochaine_commande_est_le_lendemain(self):
        self.assertEqual(
            FILET.jour_de_commande(FILET.date(2026, 9, 8), maintenant=FILET.datetime(2026, 9, 8, 16, 0)),
            "2026-09-09",
        )

    def test_stock_actuel_ne_declenche_pas_donnees_en_retard_si_ventes_anciennes(self):
        etat, _, _ = self._etat_proposition({
            "date_commande": "2026-09-10",
            "date_stock": "2026-09-09",
            "date_stock_verifiee": "2026-09-09",
            "date_reference": "2026-09-04",
            "lignes": [{}],
        }, "2026-09-09")

        self.assertEqual(etat, "perimee")

    def test_une_livraison_recente_seule_ne_certifie_pas_la_fraicheur_du_stock(self):
        etat, _, _ = self._etat_proposition({
            "date_commande": "2026-09-09", "date_stock": "2026-09-09",
            "date_reference": "2026-09-04", "lignes": [{}],
        }, "2026-09-09")
        self.assertEqual(etat, "donnees-en-retard")

    def test_la_couverture_article_par_article_prime_sur_la_date_du_dernier_fait(self):
        etat, _, _ = self._etat_proposition({
            "date_commande": "2026-09-09", "date_stock": "2026-09-09",
            "date_stock_verifiee": "2026-09-07", "date_reference": "2026-09-04", "lignes": [{}],
        }, "2026-09-09")
        self.assertEqual(etat, "donnees-en-retard")

    def test_stock_en_retard_alerte_meme_si_proposition_est_du_jour(self):
        etat, message, _ = self._etat_proposition({
            "date_commande": "2026-09-09",
            "date_stock": "2026-09-04",
            "date_reference": "2026-09-09",
            "lignes": [{}],
        }, "2026-09-09")

        self.assertEqual(etat, "donnees-en-retard")
        self.assertIn("stock", message.lower())
        self.assertIn("2026-09-04", message)


if __name__ == "__main__":
    unittest.main()
