"""Photos : rapprochement visuel sans création de code métier."""
import importlib.util
import hashlib
import json
import tempfile
from pathlib import Path
import unittest
from PIL import Image

SCRIPT = Path(__file__).resolve().parents[1] / 'moteur' / 'preparer-photos-produits.py'


def charger_module():
    if not SCRIPT.exists():
        return None
    spec = importlib.util.spec_from_file_location('preparer_photos', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PhotosTests(unittest.TestCase):
    def test_generation_legere_conserve_originaux_et_controle_empreintes(self):
        module = charger_module()
        self.assertTrue(hasattr(module, 'preparer'), 'La génération doit être disponible')
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            dossier = root / 'documents-partages/photos-produits'
            dossier.mkdir(parents=True)
            original = dossier / 'original.jpg'
            Image.new('RGB', (240, 160), 'red').save(original)
            avant = original.read_bytes()
            source = {'filename': 'POMME GALA VRAC.jpg', 'sha256': hashlib.sha256(avant).hexdigest(),
                      'path': original.relative_to(root).as_posix(), 'source_id': 'fixture-photo:1'}
            (dossier / 'sources.jsonl').write_text(json.dumps(source) + '\n', encoding='utf8')
            (root / 'donnees').mkdir()
            (root / 'donnees/cadencier-du-jour.json').write_text(json.dumps({'articles': [
                {'nom': 'POMME GALA', 'article': '0000087004135', 'offres': [{'libelle': 'POMME GALA VRAC'}]}]}), encoding='utf8')
            (root / 'donnees/proposition.json').write_text(json.dumps({'lignes': [
                {'itm8': '0000087004135', 'libelle': 'POMME GALA'}]}), encoding='utf8')
            bilan = module.preparer(root)
            self.assertEqual((bilan['sources'], bilan['images_uniques'], bilan['articles_illustres']), (1, 1, 1))
            self.assertEqual(original.read_bytes(), avant)
            photos = json.loads((root / 'donnees/photos.json').read_text(encoding='utf8'))
            photo = photos['articles']['0000087004135']
            with Image.open(root / photo['src']) as image:
                self.assertEqual(image.format, 'WEBP')
                self.assertLessEqual(max(image.size), 240)
            with Image.open(root / photo['miniature']) as image:
                self.assertLessEqual(max(image.size), 96)
            self.assertNotIn('source_id', json.dumps(photos))
            self.assertEqual(module.preparer(root), bilan)
            original.write_bytes(b'invalide')
            with self.assertRaisesRegex(ValueError, 'empreinte'):
                module.preparer(root)

    def fixture_humaine(self, root):
        dossier = root / 'documents-partages/photos-produits'
        dossier.mkdir(parents=True)
        original = dossier / 'original.jpg'
        Image.new('RGB', (32, 24), 'blue').save(original)
        source = {'filename': 'INCONNU.jpg', 'sha256': hashlib.sha256(original.read_bytes()).hexdigest(),
                  'path': original.relative_to(root).as_posix(), 'source_id': 'fixture:1'}
        (dossier / 'sources.jsonl').write_text(json.dumps(source) + '\n', encoding='utf8')
        (root / 'donnees').mkdir()
        (root / 'donnees/cadencier-du-jour.json').write_text('{"articles": []}', encoding='utf8')
        (root / 'donnees/proposition.json').write_text(json.dumps({'lignes': [
            {'itm8': 'nom:PRODUIT', 'libelle': 'PRODUIT'}]}), encoding='utf8')
        record = {'sha256': source['sha256'], 'itm8': 'nom:PRODUIT', 'libelle': 'PRODUIT',
                  'origine': {k: source[k] for k in ('source_id', 'path', 'filename')},
                  'validation': {'source': 'conversation courante', 'texte': 'photo 1 ok'},
                  'auteur': 'agent-donnees', 'date': '2026-09-10T12:00:00+02:00'}
        journal = dossier / 'associations-validees.jsonl'
        journal.write_text(json.dumps(record) + '\n', encoding='utf8')
        return dossier, source, record, journal

    def test_validation_humaine_independante_des_offres_privee_et_idempotente(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            dossier, source, record, journal = self.fixture_humaine(root)
            avant = journal.read_bytes()
            module = charger_module()
            bilan = module.preparer(root)
            self.assertEqual(bilan['articles_illustres'], 1)
            self.assertEqual(bilan['statuts'], {'validation-humaine': 1})
            sortie = root / 'donnees/photos.json'
            public = sortie.read_bytes()
            self.assertEqual(json.loads(public)['articles']['nom:PRODUIT']['src'],
                             f"app/img/produits/{source['sha256']}-240.webp")
            self.assertNotIn(b'validation', public)
            self.assertNotIn(b'fixture:1', public)
            self.assertEqual(module.preparer(root), bilan)
            self.assertEqual(sortie.read_bytes(), public)
            self.assertEqual(journal.read_bytes(), avant)

    def test_journal_invalide_refuse_avant_toute_publication(self):
        cas = ['sha-inconnu', 'sha-malforme', 'code-inconnu', 'code-malforme', 'libelle',
               'origine', 'validation', 'auteur', 'date', 'doublon', 'conflit-sha',
               'json-tronque', 'ligne-proposition-dupliquee']
        for erreur in cas:
            with self.subTest(erreur=erreur), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                dossier, source, record, journal = self.fixture_humaine(root)
                if erreur == 'sha-inconnu': record['sha256'] = 'a' * 64
                if erreur == 'sha-malforme': record['sha256'] = 'SHA'
                if erreur == 'code-inconnu': record['itm8'] = '0000000000001'
                if erreur == 'code-malforme': record['itm8'] = '123'
                if erreur == 'libelle': record['libelle'] = 'AUTRE'
                if erreur == 'origine': record['origine']['source_id'] = 'inventee'
                if erreur == 'validation': record['validation']['texte'] = ' '
                if erreur == 'auteur': record['auteur'] = ''
                if erreur == 'date': record['date'] = 'hier'
                texte = json.dumps(record) + '\n'
                if erreur == 'doublon': texte *= 2
                if erreur == 'conflit-sha': texte += json.dumps(dict(record, itm8='nom:AUTRE')) + '\n'
                if erreur == 'json-tronque': texte += '{'
                if erreur == 'ligne-proposition-dupliquee':
                    prop = root / 'donnees/proposition.json'
                    donnees = json.loads(prop.read_text(encoding='utf8'))
                    donnees['lignes'] *= 2
                    prop.write_text(json.dumps(donnees), encoding='utf8')
                journal.write_text(texte, encoding='utf8')
                avant = {p.relative_to(root): p.read_bytes() for p in root.rglob('*') if p.is_file()}
                with self.assertRaises(ValueError):
                    charger_module().preparer(root)
                self.assertEqual({p.relative_to(root): p.read_bytes() for p in root.rglob('*') if p.is_file()}, avant)

    def test_exact_anterieur_conserve_sans_validation_humaine_inventee(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            dossier, source, record, journal = self.fixture_humaine(root)
            journal.unlink()
            cad = root / 'donnees/cadencier-du-jour.json'
            cad.write_text(json.dumps({'articles': [{'nom': 'PRODUIT', 'article': None,
                           'offres': [{'libelle': 'INCONNU'}]}]}), encoding='utf8')
            module = charger_module()
            self.assertEqual(module.preparer(root)['articles_illustres'], 1)
            avant = (root / 'donnees/photos.json').read_bytes()
            preuve_avant = (dossier / 'rapport-correspondances.json').read_bytes()
            cad.write_text('{"articles": []}', encoding='utf8')
            self.assertEqual(module.preparer(root)['articles_illustres'], 1)
            self.assertEqual((root / 'donnees/photos.json').read_bytes(), avant)
            rapport = json.loads((dossier / 'rapport-correspondances.json').read_text(encoding='utf8'))
            self.assertEqual(rapport['correspondances'][0]['statut'], 'exact-historique')
            preuve = rapport['correspondances'][0]['preuve_exacte']
            archive = dossier / 'historique' / (preuve['rapport_sha256'] + '.json')
            self.assertTrue(archive.exists(), 'La preuve exacte doit rester archivee en prive')
            self.assertEqual(archive.read_bytes(), preuve_avant)
            self.assertNotIn('validation', rapport['correspondances'][0])
            self.assertFalse(journal.exists())
            self.assertEqual(module.preparer(root)['articles_illustres'], 1)
            self.assertEqual((root / 'donnees/photos.json').read_bytes(), avant)

    def test_collision_photo_refuse_sans_ecriture(self):
        for humaine in (False, True):
            with self.subTest(humaine=humaine), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                dossier, source, record, journal = self.fixture_humaine(root)
                autre = dossier / 'autre.jpg'
                Image.new('RGB', (20, 20), 'red').save(autre)
                source2 = dict(source, sha256=hashlib.sha256(autre.read_bytes()).hexdigest(),
                               path=autre.relative_to(root).as_posix(), filename='EXACT.jpg', source_id='fixture:2')
                with (dossier / 'sources.jsonl').open('a', encoding='utf8') as f:
                    f.write(json.dumps(source2) + '\n')
                if humaine:
                    record2 = dict(record, sha256=source2['sha256'],
                                   origine={k: source2[k] for k in ('source_id', 'path', 'filename')})
                    with journal.open('a', encoding='utf8') as f:
                        f.write(json.dumps(record2) + '\n')
                else:
                    (root / 'donnees/cadencier-du-jour.json').write_text(json.dumps({'articles': [
                        {'nom': 'PRODUIT', 'article': None, 'offres': [{'libelle': 'EXACT'}]}]}), encoding='utf8')
                avant = {p.relative_to(root): p.read_bytes() for p in root.rglob('*') if p.is_file()}
                with self.assertRaisesRegex(ValueError, 'collision|conflit'):
                    charger_module().preparer(root)
                self.assertEqual({p.relative_to(root): p.read_bytes() for p in root.rglob('*') if p.is_file()}, avant)

    def test_validation_prioritaire_sur_nouvelle_offre(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            dossier, source, record, journal = self.fixture_humaine(root)
            (root / 'donnees/cadencier-du-jour.json').write_text(json.dumps({'articles': [
                {'nom': 'AUTRE', 'article': None, 'offres': [{'libelle': 'INCONNU'}]}]}), encoding='utf8')
            prop = root / 'donnees/proposition.json'
            prop.write_text(json.dumps({'lignes': [{'itm8': 'nom:PRODUIT', 'libelle': 'PRODUIT'},
                {'itm8': 'nom:AUTRE', 'libelle': 'AUTRE'}]}), encoding='utf8')
            charger_module().preparer(root)
            public = json.loads((root / 'donnees/photos.json').read_text(encoding='utf8'))
            self.assertEqual(set(public['articles']), {'nom:PRODUIT'})

    def test_refus_changement_photo_publiee_et_preuve_historique_absente(self):
        for erreur in ('reaffectation', 'preuve-absente', 'preuve-fausse', 'code-disparu'):
            with self.subTest(erreur=erreur), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                dossier, source, record, journal = self.fixture_humaine(root)
                journal.unlink()
                cad = root / 'donnees/cadencier-du-jour.json'
                cad.write_text(json.dumps({'articles': [{'nom': 'PRODUIT', 'article': None,
                               'offres': [{'libelle': 'INCONNU'}]}]}), encoding='utf8')
                module = charger_module()
                module.preparer(root)
                cad.write_text('{"articles": []}', encoding='utf8')
                rapport = dossier / 'rapport-correspondances.json'
                if erreur == 'preuve-absente': rapport.unlink()
                if erreur == 'preuve-fausse':
                    contenu = json.loads(rapport.read_text(encoding='utf8'))
                    contenu['correspondances'][0]['source_id'] = 'fausse'
                    rapport.write_text(json.dumps(contenu), encoding='utf8')
                if erreur == 'code-disparu':
                    (root / 'donnees/proposition.json').write_text('{"lignes": []}', encoding='utf8')
                if erreur == 'reaffectation':
                    record.update(itm8='nom:AUTRE', libelle='AUTRE')
                    journal.write_text(json.dumps(record) + '\n', encoding='utf8')
                    (root / 'donnees/proposition.json').write_text(json.dumps({'lignes': [
                        {'itm8': 'nom:PRODUIT', 'libelle': 'PRODUIT'},
                        {'itm8': 'nom:AUTRE', 'libelle': 'AUTRE'}]}), encoding='utf8')
                avant = {p.relative_to(root): p.read_bytes() for p in root.rglob('*') if p.is_file()}
                with self.assertRaises(ValueError): module.preparer(root)
                self.assertEqual({p.relative_to(root): p.read_bytes() for p in root.rglob('*') if p.is_file()}, avant)

    def test_correspondance_exacte_unique_sans_inventer_un_code(self):
        module = charger_module()
        self.assertIsNotNone(module, 'Le préparateur de photos doit exister')
        source = {'filename': 'KIWI SUNGOLD 88-103G BARQUETTE 4 PIECES.jpg'}
        cadencier = {'articles': [{'nom': 'KIWI JAUNE 4 FRUITS', 'article': None,
                                  'offres': [{'libelle': 'KIWI SUNGOLD 88/103G BARQUETTE 4 PIECES'}]}]}
        proposition = {'lignes': [{'itm8': 'nom:KIWI JAUNE 4 FRUITS', 'libelle': 'KIWI JAUNE 4 FRUITS'}]}
        resultat = module.rapprocher(source, cadencier, proposition)
        self.assertEqual(resultat['itm8'], 'nom:KIWI JAUNE 4 FRUITS')
        self.assertEqual(resultat['statut'], 'exact-unique')
        source['filename'] = 'KIWI SUNGOLD 88-103G BARQUETTE 6 PIECES.jpg'
        self.assertEqual(module.rapprocher(source, cadencier, proposition)['statut'], 'sans-correspondance')
        source['filename'] = 'KIWI SUNGOLD 88-103G BARQUETTE 4 PIECES.jpg'
        cadencier['articles'].append(dict(cadencier['articles'][0], nom='AUTRE KIWI'))
        self.assertEqual(module.rapprocher(source, cadencier, proposition)['statut'], 'ambigu')


if __name__ == '__main__':
    unittest.main()
