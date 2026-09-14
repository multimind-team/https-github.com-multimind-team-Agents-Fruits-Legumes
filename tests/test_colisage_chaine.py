"""Parcours navigateur → HTTP → décision → vrais producteurs, en copie isolée."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from datetime import date, timedelta
from unittest.mock import patch

from playwright.sync_api import sync_playwright

RACINE = Path(__file__).resolve().parents[1]
CODE = '0000087001234'


class ColisageChaineTests(unittest.TestCase):
    def test_modifier_depuis_la_fiche_recalcule_et_persiste_sans_changer_le_comptage(self):
        with tempfile.TemporaryDirectory(prefix='colisage-chaine-') as temporaire:
            racine = Path(temporaire).resolve()
            self.assertFalse(racine.is_relative_to(RACINE))
            moteur = racine / 'moteur'
            moteur.mkdir()
            for chemin in (RACINE / 'moteur').glob('*.py'):
                shutil.copy2(chemin, moteur / chemin.name)
            for relatif in ('app/commander.html', 'app/css/charte.css', 'app/js/photos-produits.js'):
                cible = racine / relatif
                cible.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(RACINE / relatif, cible)
            donnees = racine / 'donnees'
            (donnees / 'faits').mkdir(parents=True)
            jour = date.today()
            def ecrire(nom, valeur):
                (donnees / nom).write_text(json.dumps(valeur), encoding='utf-8')
            ecrire('catalogue.json', {'articles': {CODE: {
                'CODE ITM': CODE, 'LIBELLE': 'POMME TEST COLISAGE', 'CONDIT.BASE': 6,
                'PRIX VENTE': 2, 'PRIX ACHAT': 1, 'UNITE MESURE': '1 kg'}}})
            ecrire('calendrier.json', {'feries': {}, 'vacances': []})
            ecrire('pouvoirs.json', {'agents': {'responsable-rayon': {
                'peut_seul': ['conditionnement'], 'plafond_par_jour': 999}}})
            ecrire('cadencier-du-jour.json', {'articles': [{
                'article': CODE, 'nom': 'POMME TEST COLISAGE', 'rang': 1, 'groupe': 'fruits',
                'offres': [{'par_colis': 6, 'prix_achat': 1}, {'par_colis': 8, 'prix_achat': 1.5}]}]})
            faits = []
            for n in range(1, 8):
                j = (jour - timedelta(days=n)).isoformat()
                faits.append({'id': 'vente:' + j, 'type': 'vente', 'article': CODE,
                              'article_source': CODE, 'date_source': j, 'date_effet': j, 'quantite': 3})
            faits.append({'id': 'comptage:fixture', 'type': 'comptage', 'article': CODE,
                          'date_source': jour.isoformat(), 'date_effet': jour.isoformat(),
                          'horodatage': jour.isoformat() + 'T00:00:00',
                          'colis': -2, 'conditionnement': 6, 'quantite': -12})
            carnet = donnees / 'faits' / (str(jour.year) + '.jsonl')
            carnet.write_text(''.join(json.dumps(f) + '\n' for f in faits), encoding='utf-8')
            avant = carnet.read_bytes()
            run_reel = subprocess.run
            def executer(commande, **kwargs):
                script = Path(commande[1]).resolve()
                self.assertEqual(script.parent, moteur)
                self.assertIn(script.name, ('agregats.py', 'calculer-position.py',
                    'generer-proposition.py', 'preparer-liste-comptage.py', 'appliquer-decision.py'))
                if script.name == 'generer-proposition.py':
                    # Seule dépendance externe remplacée : aucune météo réseau en test.
                    wrapper = ('import importlib.util,sys; sys.path.insert(0,sys.argv[1]); '
                        's=importlib.util.spec_from_file_location("generateur_test",sys.argv[2]); '
                        'm=importlib.util.module_from_spec(s); s.loader.exec_module(m); '
                        'm.meteo_prevue=lambda:{}; m.main()')
                    commande = [sys.executable, '-B', '-c', wrapper, str(moteur), str(script)]
                else:
                    commande = [commande[0], '-B', *commande[1:]]
                env = dict(kwargs.get('env', os.environ))
                env['PYTHONIOENCODING'] = 'utf-8'
                options = {**kwargs, 'cwd': str(racine), 'env': env}
                if 'errors' not in options:
                    options['errors'] = 'replace'
                return run_reel(commande, **options)
            for nom in ('agregats.py', 'calculer-position.py', 'generer-proposition.py', 'preparer-liste-comptage.py'):
                resultat = executer([sys.executable, str(moteur / nom)], capture_output=True,
                                    text=True, encoding='utf-8', timeout=30)
                self.assertEqual(resultat.returncode, 0, resultat.stdout + resultat.stderr)
            spec = importlib.util.spec_from_file_location('serveur_chaine_colisage', moteur / 'serveur.py')
            serveur = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(serveur)
            with patch.object(serveur.subprocess, 'run', side_effect=executer):
                http = serveur.ServeurHTTP(('127.0.0.1', 0), serveur.Gestionnaire)
                fil = threading.Thread(target=http.serve_forever, daemon=True)
                fil.start()
                base = 'http://127.0.0.1:' + str(http.server_port)
                try:
                    with sync_playwright() as pw:
                        try:
                            navigateur = pw.chromium.launch(headless=True)
                        except Exception:
                            navigateur = pw.chromium.launch(headless=True, channel='msedge')
                        contexte = navigateur.new_context(viewport={'width': 360, 'height': 800})
                        contexte.route('**/*', lambda route: route.continue_() if route.request.url.startswith(base + '/') else route.abort())
                        page = contexte.new_page()
                        erreurs = []
                        page.on('pageerror', lambda e: erreurs.append(str(e)))
                        try:
                            page.goto(base + '/app/commander.html')
                            page.locator('[data-role="detail"]').first.click()
                            self.assertEqual(page.locator('#detail-conditionnement-valeur').input_value(), '6')
                            page.evaluate('localStorage.setItem("saisie-a-conserver", "intacte")')
                            page.locator('#detail-conditionnement-valeur').fill('8')
                            page.locator('#detail-conditionnement-valider').click()
                            page.wait_for_function("document.getElementById('detail-conditionnement-etat').textContent.includes('recalculée')", timeout=20000)
                            self.assertIn('colis de 8 kg', page.locator('#detail-sous').inner_text())
                            self.assertIn('1,5 €', page.locator('#detail-prix').inner_text())
                            self.assertEqual(page.evaluate('proposition.lignes[0].position_unites'), -12)
                            self.assertEqual(page.evaluate('proposition.lignes[0].position_colis'), -1.5)
                            self.assertEqual(page.evaluate('localStorage.getItem("saisie-a-conserver")'), 'intacte')
                            if os.environ.get('COLISAGE_PREUVES'):
                                preuve = Path(os.environ['COLISAGE_PREUVES'])
                                preuve.mkdir(parents=True, exist_ok=True)
                                page.screenshot(path=str(preuve / 'colisage-mobile-fixture.png'))
                            page.reload()
                            page.locator('[data-role="detail"]').first.click()
                            self.assertEqual(page.locator('#detail-conditionnement-valeur').input_value(), '8')
                            self.assertEqual(erreurs, [])
                        finally:
                            contexte.close()
                            navigateur.close()
                finally:
                    http.shutdown()
                    http.server_close()
                    fil.join(5)
                    limite = time.monotonic() + 30
                    while serveur._recalcul_actif and time.monotonic() < limite:
                        time.sleep(.05)
                    self.assertFalse(serveur._recalcul_actif, 'Le recalcul isolé ne se termine pas')
            decisions = [json.loads(l) for l in (donnees / 'decisions.jsonl').read_text(encoding='utf-8').splitlines()]
            self.assertEqual(len(decisions), 1)
            self.assertEqual(decisions[0]['type'], 'conditionnement')
            self.assertEqual(float(decisions[0]['valeur']), 8)
            self.assertEqual(carnet.read_bytes(), avant)
            articles = json.loads((donnees / 'articles.json').read_text(encoding='utf-8'))['articles']
            self.assertEqual(next(a for a in articles if a['itm8'] == CODE)['conditionnement'], 8)
            self.assertEqual(json.loads((donnees / 'etat.json').read_text(encoding='utf-8'))['articles'][CODE]['position'], -12)


if __name__ == '__main__':
    unittest.main()
