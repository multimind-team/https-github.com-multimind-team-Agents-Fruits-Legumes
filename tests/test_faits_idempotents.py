"""Rejeu de faits append-only sur fixtures, sans suppression des sources."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

MOTEUR = Path(__file__).resolve().parents[1] / "moteur"
sys.path.insert(0, str(MOTEUR))


def charger(nom):
    spec = importlib.util.spec_from_file_location('test_rejeu_' + nom.replace('-', '_'), MOTEUR / nom)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def mouvement(**champs):
    return {"id": "v1", "article": "123", "article_source": "123", "type": "vente",
            "date_source": "2026-09-08", "date_effet": "2026-09-08", "quantite": 3,
            "source": {"origine": "Vente.xlsx", "ligne": 2}, **champs}


class FaitsIdempotentsTests(unittest.TestCase):
    def test_fait_json_tronque_refuse_et_carnet_conserve(self):
        import faits
        with tempfile.TemporaryDirectory() as temporaire:
            dossier = Path(temporaire)
            fichier = dossier / "2026.jsonl"
            avant = (json.dumps(mouvement()) + '\n{"id":"incomplet"').encode("utf-8")
            fichier.write_bytes(avant)
            with self.assertRaises(json.JSONDecodeError):
                list(faits.lire(dossier))
            self.assertEqual(fichier.read_bytes(), avant)

    def test_bilan_liste_les_copies_ignorees_sans_fusionner_les_faits_sans_id(self):
        import faits
        with tempfile.TemporaryDirectory() as temporaire:
            dossier = Path(temporaire)
            sans_id = mouvement()
            del sans_id['id']
            lignes = [mouvement(), mouvement(source={'origine': 'copie.xlsx'}), sans_id, sans_id]
            fichier = dossier / '2026.jsonl'
            fichier.write_text('\n'.join(json.dumps(x) for x in lignes), encoding='utf-8')
            avant = fichier.read_bytes()
            bilan = {}
            self.assertEqual(len(list(faits.lire(dossier, bilan))), 3)
            self.assertEqual(bilan['lignes_lues'], 4)
            self.assertEqual(bilan['doublons_ignores'], 1)
            self.assertEqual(bilan['sans_id'], 2)
            self.assertEqual(bilan['doublons'][0]['id'], 'v1')
            self.assertEqual(bilan['doublons'][0]['ignore']['ligne'], 2)
            self.assertEqual(fichier.read_bytes(), avant)

    def test_agregats_publie_un_bilan_des_doublons(self):
        agr = charger('agregats.py')
        calc = charger('calculer-commande.py')
        with tempfile.TemporaryDirectory() as temporaire:
            dossier = Path(temporaire)
            (dossier / 'faits').mkdir()
            (dossier / 'faits/2026.jsonl').write_text('\n'.join(json.dumps(mouvement()) for _ in range(2)), encoding='utf-8')
            with patch.object(agr, 'DOSSIER_FAITS', dossier / 'faits'), \
                 patch.object(calc, 'DOSSIER_FAITS', dossier / 'faits'), \
                 patch.object(agr, 'DONNEES', dossier), \
                 patch.object(agr, '_module', return_value=calc), \
                 patch.object(agr.regles, 'charger', return_value={}), \
                 patch.object(agr.catalogue, 'noms', return_value={}), \
                 patch.object(agr.catalogue, 'prix', return_value=1), \
                 patch.object(agr.catalogue, 'conditionnement_cadencier', return_value=1), \
                 patch.object(agr.catalogue, 'fiche', return_value={}), \
                 patch.object(agr.catalogue, 'ordre_webtelevente', return_value=[]):
                resultat = agr.construire()
            self.assertEqual(resultat['articles']['123']['totalCA'], 3)
            self.assertEqual(resultat.get('audit_faits', {}).get('doublons_ignores'), 1)

    def test_calibrage_et_tendances_ne_doublent_pas_les_ventes(self):
        calibrage = charger('calibrer-jour-semaine.py')
        tendances = charger('tendances.py')
        with tempfile.TemporaryDirectory() as temporaire:
            dossier = Path(temporaire)
            (dossier / 'faits').mkdir()
            (dossier / 'faits/2026.jsonl').write_text('\n'.join(json.dumps(mouvement()) for _ in range(2)), encoding='utf-8')
            with patch.object(calibrage, 'DOSSIER_FAITS', dossier / 'faits'), patch.object(tendances, 'DONNEES', dossier):
                self.assertEqual(calibrage.charger()[0]['123']['2026-09-08'], 3)
                self.assertEqual(tendances.ventes_par_jour('2026-09-01')['123']['2026-09-08'], 3)

    def test_lecteurs_partagent_rejeu_idempotent_et_refus_des_conflits(self):
        for nom in ['calculer-position.py', 'calculer-commande.py', 'agregats.py',
                    'evaluer-prevision.py', 'note-du-matin.py']:
            module = charger(nom)
            with self.subTest(lecteur=nom), tempfile.TemporaryDirectory() as temporaire:
                dossier = Path(temporaire)
                fichier = dossier / '2026.jsonl'
                original = mouvement()
                copie = mouvement(source={"origine": "autre.xlsx", "ligne": 2})
                texte = '\n'.join(json.dumps(f) for f in [original, copie]) + '\n'
                fichier.write_text(texte, encoding='utf-8')
                avant = fichier.read_bytes()
                with patch.object(module, 'DOSSIER_FAITS', dossier):
                    self.assertEqual(list(module.lire_faits()), [original])
                    self.assertEqual(fichier.read_bytes(), avant)
                    for champ, valeur in [('quantite', 4), ('date_effet', '2026-09-09'),
                                          ('date_source', '2026-09-07'), ('type', 'don'),
                                          ('article', '456'), ('cible_id', 'c2')]:
                        conflit = dict(copie, **{champ: valeur})
                        fichier.write_text('\n'.join(json.dumps(f) for f in [original, conflit]), encoding='utf-8')
                        with self.subTest(champ=champ), self.assertRaisesRegex(ValueError, 'v1'):
                            list(module.lire_faits())

    def test_quantites_de_stock_et_ventes_non_doublees(self):
        position = charger('calculer-position.py')
        calcul = charger('calculer-commande.py')
        with tempfile.TemporaryDirectory() as temporaire:
            dossier = Path(temporaire)
            f = mouvement()
            comptage = mouvement(id='c1', type='comptage', date_source='2026-09-07',
                                 date_effet='2026-09-07', quantite=20)
            (dossier / '2026.jsonl').write_text('\n'.join(json.dumps(x) for x in [comptage, f, f]), encoding='utf-8')
            with patch.object(position, 'DOSSIER_FAITS', dossier), patch.object(calcul, 'DOSSIER_FAITS', dossier):
                self.assertEqual(position.calculer()['123']['position'], 17)
                self.assertEqual(calcul.construire_moyennes()['123']['totalVente'], 3)


if __name__ == '__main__':
    unittest.main()
