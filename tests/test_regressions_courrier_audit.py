"""Régressions audit courrier : réseau fictif et écritures temporaires uniquement."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from email.message import EmailMessage
from unittest.mock import patch

MOTEUR = Path(__file__).resolve().parents[1] / 'moteur'
sys.path.insert(0, str(MOTEUR))


def module(nom):
    spec = importlib.util.spec_from_file_location('audit_' + nom.replace('-', '_'), MOTEUR / (nom + '.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


IMPORT = module('integrer-fichiers')
RELEVE = module('relever-courrier')
LECTURE = module('lire-mail-uid')
SENT = module('surveille-mail-message-comptage')
PIPE = module('traiter-courrier')


class FakeIMAP:
    def __init__(self, messages):
        self.messages = messages
    def login(self, *args): pass
    def select(self, *args, **kwargs): return 'OK', [b'2']
    def response(self, *args): return 'UIDVALIDITY', [b'987']
    def close(self): pass
    def logout(self): pass
    def uid(self, action, *args):
        if action.lower() == 'search':
            return 'OK', [b' '.join(self.messages)]
        if action.lower() == 'fetch':
            contenu = self.messages[args[0]]
            return 'OK', [(b'1 (RFC822.SIZE ' + str(len(contenu)).encode() + b')', contenu), b')']
        raise AssertionError('Aucune écriture IMAP autorisée dans ce test')


def mail(identifiant, contenu, nom='vente 15.09.2026.xlsx'):
    msg = EmailMessage()
    msg['Message-ID'] = identifiant
    msg['From'] = 'magasin@example.invalid'
    msg['Subject'] = 'Exports'
    msg.set_content('Fichiers magasin')
    msg.add_attachment(contenu, maintype='application', subtype='octet-stream', filename=nom)
    return msg.as_bytes()


class CourrierRegressions(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_homonymes_et_rejeu_conservent_les_deux_originaux(self):
        cfg = {'imap_host': 'imap.invalid', 'utilisateur': 'fixture', 'mot_de_passe': 'fixture'}
        fake = FakeIMAP({b'1': mail('<un>', b'premier'), b'2': mail('<deux>', b'second')})
        with patch.object(RELEVE, 'RACINE', self.root), patch.object(RELEVE.imaplib, 'IMAP4_SSL', return_value=fake):
            a = RELEVE.relever(cfg, classer=False)
            b = RELEVE.relever(cfg, classer=False)
        chemins = [Path(m['pieces_jointes'][0]) for m in a['messages_traites']]
        self.assertNotEqual(*chemins)
        self.assertEqual([c.read_bytes() for c in chemins], [b'premier', b'second'])
        self.assertEqual([m['pieces_jointes'] for m in a['messages_traites']],
                         [m['pieces_jointes'] for m in b['messages_traites']])
        self.assertGreater(a['messages_traites'][0]['taille_octets'], 0)

    def test_telechargement_uid_confine_les_noms_mime_hostiles(self):
        fake = FakeIMAP({b'1': mail('<un>', b'piece', '../../exterieur.xlsx')})
        with patch.object(LECTURE, 'RACINE', self.root), \
             patch.object(LECTURE, 'charger_config_courrier', return_value={'imap_host': 'invalid', 'utilisateur': '', 'mot_de_passe': ''}), \
             patch.object(LECTURE.imaplib, 'IMAP4_SSL', return_value=fake), \
             patch.object(sys, 'argv', ['lire-mail-uid.py', '1', '--telecharger']), contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(LECTURE.main(), 0)
        cible = Path(json.loads(out.getvalue())['pieces_jointes'][0]['chemin'])
        self.assertTrue(cible.is_relative_to(self.root / 'donnees/courrier/uid-1'))
        self.assertEqual(cible.read_bytes(), b'piece')
        self.assertFalse((self.root / 'exterieur.xlsx').exists())

    def test_configuration_injectee_ne_lit_pas_env_de_production(self):
        import config_courrier as cfg
        config = self.root / 'donnees/courrier-config.json'
        config.parent.mkdir()
        config.write_text('{}')
        with patch.dict(os.environ, {}, clear=True), patch.object(cfg, 'ENV_PATH', self.root / 'interdit.env'):
            self.assertEqual(cfg.charger_config_courrier(config)['mot_de_passe'], '')
        self.assertFalse(hasattr(cfg, 'FALLBACK_ENV_PATH'))

    def test_cli_envoi_marge_passe_par_configuration_et_transport_simules(self):
        envoi = module('envoyer-classeur-marge')
        import config_courrier
        classeur = self.root / 'marge.xlsx'
        classeur.write_bytes(b'classeur-fixture')
        cfg = {'utilisateur': 'fixture@example.invalid', 'mot_de_passe': 'fixture'}
        with patch.object(config_courrier, 'charger_config_courrier', return_value=cfg), \
             patch.object(envoi, 'envoie_message') as transport, \
             patch.object(sys, 'argv', ['envoi', '--classeur', str(classeur), '--destinataire', 'test@example.invalid']), \
             contextlib.redirect_stdout(io.StringIO()) as out:
            envoi.main()
        transport.assert_called_once()
        self.assertEqual(list(transport.call_args.args[1].iter_attachments())[0].get_payload(decode=True), b'classeur-fixture')
        self.assertTrue(json.loads(out.getvalue())['smtp_accepte'])

    def ventes(self, lignes):
        colonnes = ['ITM8 Prio', 'Libellé', 'Date', 'Quantité']
        with patch.object(IMPORT, 'lire_tableau', return_value=(colonnes, lignes, [])):
            return IMPORT.convertir(Path('vente 15.09.2026.xlsx'), {}, {'00000001', '00000002'}, lambda *a: None, {})

    def test_retri_reconnait_aussi_anciens_identifiants_et_refuse_chevauchement(self):
        lignes = [['00000001', 'Pomme', '14/09/2026', 2], ['00000002', 'Poire', '14/09/2026', 3]]
        initial = self.ventes(lignes)
        retri = self.ventes(lignes[::-1])
        self.assertEqual({f['id'] for f in initial}, {f['id'] for f in retri})
        anciens = [dict(f, id=f"vente:2026-09-14:{f['article_source']}:{i}") for i, f in enumerate(initial)]
        dossier = self.root / 'donnees/faits'
        dossier.mkdir(parents=True)
        carnet = dossier / '2026.jsonl'
        carnet.write_text(''.join(json.dumps(f) + '\n' for f in anciens), encoding='utf-8')
        avant = carnet.read_bytes()
        with patch.object(IMPORT, 'DOSSIER_FAITS', dossier):
            self.assertEqual(IMPORT.ecrire(retri), ([], 2))
            changes = self.ventes([['00000001', 'Pomme', '14/09/2026', 7]])
            with self.assertRaisesRegex(ValueError, 'Chevauchement'):
                IMPORT.ecrire(changes)
        self.assertEqual(carnet.read_bytes(), avant)

    def test_vrac_base_un_refuse_au_lieu_de_multiplie_par_catalogue(self):
        alertes = []
        donnees = (['Code ITM', 'Qté cmdée (nbre colis)', 'Cond. de base', 'Unité de mesure', 'Libellé article'],
                   [['00000001', 2, 1, 'KG', 'POMME VRAC']], [])
        with patch.object(IMPORT, 'lire_tableau', return_value=donnees):
            faits = IMPORT.convertir(Path('livraison 15.09.2026.xlsx'), {}, {'00000001'},
                                     lambda *a: alertes.append(a), {'00000001': 10})
        self.assertEqual(faits, [])
        self.assertEqual(alertes[0][0], 'conversion-non-prouvee')

    def test_reexport_avec_moins_de_lignes_pour_article_exige_correction(self):
        lignes = [['00000001', 'Pomme', '14/09/2026', 2], ['00000001', 'Pomme', '14/09/2026', 3]]
        dossier = self.root / 'donnees/faits'
        with patch.object(IMPORT, 'DOSSIER_FAITS', dossier):
            self.assertEqual(len(IMPORT.ecrire(self.ventes(lignes))[0]), 2)
            avant = (dossier / '2026.jsonl').read_bytes()
            self.assertEqual(IMPORT.ecrire(self.ventes(lignes[::-1])), ([], 2))
            with self.assertRaisesRegex(ValueError, 'nombre de lignes'):
                IMPORT.ecrire(self.ventes(lignes[:1]))
        self.assertEqual((dossier / '2026.jsonl').read_bytes(), avant)

    def test_import_partiel_code_zero_n_est_pas_un_succes_global(self):
        from subprocess import CompletedProcess
        commande = ['py', '-3.14', str(self.root / 'moteur/integrer-fichiers.py'), '--json']
        bilan = {'statut': 'a-verifier', 'a_verifier': [{'genre': 'conversion-non-prouvee'}]}
        with patch.object(PIPE.subprocess, 'run', return_value=CompletedProcess(commande, 0, json.dumps(bilan), '')):
            self.assertEqual(PIPE.lancer(commande, False)['statut'], 'a-verifier')

    def test_livraison_unite_manquante_ou_kg_contre_piece_est_refusee(self):
        for unite in ('', 'kg'):
            with self.subTest(unite=unite):
                alertes = []
                donnees = (['Code ITM', 'Qté cmdée (nbre colis)', 'Cond. de base', 'Unité de mesure'],
                           [['00000001', 2, 6, unite]], [])
                with patch.object(IMPORT, 'lire_tableau', return_value=donnees), \
                     patch.object(IMPORT.catalogue, 'unite', return_value='1 Pièce'):
                    resultat = IMPORT.convertir(Path('livraison 15.09.2026.xlsx'), {}, {'00000001'},
                                               lambda *a: alertes.append(a), {})
                self.assertEqual(resultat, [])
                self.assertEqual(alertes[0][0], 'unite-non-prouvee')

    def test_sentinelle_reprend_backlog_correction_et_arrivee_pendant_traitement(self):
        donnees = self.root / 'donnees'
        faits = donnees / 'faits'
        faits.mkdir(parents=True)
        messages = donnees / 'messages.jsonl'
        messages.write_text(json.dumps({'id': 'm1', 'texte': 'demande'}) + '\n', encoding='utf-8')
        (faits / '2026.jsonl').write_text(json.dumps({'id': 'c1', 'type': 'correction-comptage', 'article': 'A'}) + '\n')
        with patch.multiple(SENT, DONNEES=donnees, DOSSIER_FAITS=faits, MESSAGES_PATH=messages,
                            CONFIG_PATH=donnees / 'absent.json'), contextlib.redirect_stdout(io.StringIO()):
            SENT.surveiller(une_fois=True)
            self.assertEqual(set(SENT.charger_file()['en_attente']), {'MESSAGE:m1', 'COMPTAGE:c1'})
            with messages.open('a') as out:
                out.write(json.dumps({'id': 'm2', 'texte': 'autre'}) + '\n')
            SENT.surveiller(une_fois=True)
            self.assertEqual(len(SENT.charger_file()['en_attente']), 3)
            SENT.acquitter('MESSAGE', 'm1', 'reponse:fixture-verifiee')
            SENT.surveiller(une_fois=True)
            self.assertEqual(set(SENT.charger_file()['en_attente']), {'MESSAGE:m2', 'COMPTAGE:c1'})
        self.assertFalse((donnees / 'reponses.jsonl').exists())

    def test_mail_detecte_pas_acquitte_implicitement(self):
        cfg = {'imap_host': 'invalid', 'utilisateur': 'fixture', 'mot_de_passe': 'fixture'}
        with patch.object(SENT.imaplib, 'IMAP4_SSL', return_value=FakeIMAP({b'1': mail('<un>', b'piece')})):
            a, connus = SENT.verifier_boite_mail(cfg, set())
            b, _ = SENT.verifier_boite_mail(cfg, connus)
        self.assertEqual(a, b)
        self.assertEqual(connus, set())


if __name__ == '__main__':
    unittest.main()
