"""Exécute les vrais producteurs dans une copie isolée du moteur."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

RACINE = Path(__file__).resolve().parents[1]


class ChaineMetierTests(unittest.TestCase):
    def test_reconstruction_rejouable_et_sources_intactes(self):
        with tempfile.TemporaryDirectory() as temporaire:
            racine = Path(temporaire)
            moteur = racine / 'moteur'
            moteur.mkdir()
            for nom in ['agregats.py', 'calculer-position.py', 'calculer-commande.py',
                        'generer-proposition.py', 'proposer-commande.py', 'preparer-liste-comptage.py',
                        'note-du-matin.py', 'filet-de-securite.py', 'calendrier.py', 'catalogue.py',
                        'regles.py', 'journal_agents.py', 'ouverture-jours-feries.py', 'faits.py',
                        'ecriture_derivee.py', 'conditionnements.py']:
                shutil.copy2(RACINE / 'moteur' / nom, moteur / nom)
            donnees = racine / 'donnees'
            (donnees / 'faits').mkdir(parents=True)
            codes = ['0000087001234', '0000087001235', '0000087001236']
            catalogue = {c: {'CODE ITM': c, 'LIBELLE': c, 'CONDIT.BASE': 1,
                             'PRIX VENTE': 2, 'PRIX ACHAT': 1} for c in codes}
            (donnees / 'catalogue.json').write_text(json.dumps({'articles': catalogue}), encoding='utf-8')
            (donnees / 'calendrier.json').write_text(json.dumps({'feries': {}, 'vacances': []}), encoding='utf-8')
            cadencier = {'articles': [{'article': c, 'nom': c, 'rang': rang,
                                      'groupe': groupe, 'offres': []}
                                     for rang, (c, groupe) in enumerate(zip(codes, ['bio', 'fruits', 'legumes']), 1)]}
            (donnees / 'cadencier-du-jour.json').write_text(json.dumps(cadencier), encoding='utf-8')
            faits = []
            for c in codes:
                for jour in ['2026-08-30', '2026-08-31', '2026-09-01', '2026-09-02', '2026-09-03', '2026-09-04']:
                    faits.append({'id': f'vente:{c}:{jour}', 'type': 'vente', 'article': c,
                                  'article_source': c, 'date_source': jour, 'date_effet': jour, 'quantite': 3})
                faits.extend([
                    {'id': f'comptage:{c}', 'type': 'comptage', 'article': c, 'date_source': '2026-09-07',
                     'date_effet': '2026-09-07', 'quantite': 20, 'horodatage': '2026-09-07T19:00:00'},
                    {'id': f'livraison:{c}', 'type': 'livraison', 'article': c, 'date_source': '2026-09-08',
                     'date_effet': '2026-09-09', 'quantite': 5, 'colis': 5},
                ])
            faits.append(dict(faits[0], source={'origine': 'copie.xlsx'}))
            journal = donnees / 'faits/2026.jsonl'
            journal.write_text('\n'.join(json.dumps(f) for f in faits) + '\n', encoding='utf-8')
            avant = hashlib.sha256(journal.read_bytes()).hexdigest()
            programme = r'''
import importlib.util, json, sys
from datetime import datetime, date
from pathlib import Path
moteur = Path(sys.argv[1]); sys.path.insert(0, str(moteur))
def charger(nom):
    spec=importlib.util.spec_from_file_location(nom.replace('-', '_'), moteur / nom)
    m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
class HeureFigee(datetime):
    @classmethod
    def now(cls): return cls(2026, 9, 9, 6, 27)
class JourFige(date):
    @classmethod
    def today(cls): return cls(2026, 9, 9)
import agregats
agregats.ecrire()
charger('calculer-position.py').main()
generer=charger('generer-proposition.py'); generer.datetime=HeureFigee
generer.meteo_prevue=lambda: {}; generer.main()
liste=charger('preparer-liste-comptage.py'); liste.date=JourFige; liste.main()
charger('note-du-matin.py').main()
filet=charger('filet-de-securite.py'); filet.datetime=HeureFigee; filet.date=JourFige
etat,message,_=filet.etat_proposition(); filet.marquer_fraicheur(etat,message,[])
'''
            for _ in range(2):
                execution = subprocess.run([sys.executable, '-B', '-c', programme, str(moteur)],
                                           cwd=racine, capture_output=True, text=True,
                                           encoding='utf-8', errors='replace', timeout=60)
                self.assertEqual(execution.returncode, 0, execution.stdout + execution.stderr)
                self.assertEqual(hashlib.sha256(journal.read_bytes()).hexdigest(), avant)
                agr = json.loads((donnees / 'agregats.json').read_text(encoding='utf-8'))
                etat = json.loads((donnees / 'etat.json').read_text(encoding='utf-8'))
                proposition = json.loads((donnees / 'proposition.json').read_text(encoding='utf-8'))
                fraicheur = json.loads((donnees / 'fraicheur.json').read_text(encoding='utf-8'))
                self.assertEqual(agr['audit_faits']['doublons_ignores'], 1)
                self.assertEqual(agr['articles'][codes[0]]['totalVente'], 18)
                self.assertEqual(etat['articles'][codes[0]]['position'], 25)
                self.assertEqual(proposition['date_commande'], '2026-09-09')
                self.assertEqual(proposition['date_stock_verifiee'], '2026-09-07')
                self.assertEqual(proposition['couverture_stock']['articles_sorties_a_verifier'], 3)
                self.assertEqual([l['itm8'] for l in proposition['lignes']], [codes[1], codes[2], codes[0]])
                self.assertEqual(fraicheur['etat'], 'donnees-en-retard')
                for nom in ['articles.json', 'note-du-matin.json']:
                    self.assertIsInstance(json.loads((donnees / nom).read_text(encoding='utf-8')), dict)
                self.assertFalse(list(donnees.glob('*.tmp')))


if __name__ == '__main__':
    unittest.main()
