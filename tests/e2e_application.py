"""QA navigateur : copie isolée par défaut, aucune écriture métier en production.

py -3.14 tests/e2e_application.py
py -3.14 tests/e2e_application.py --lecture-seule --url https://... --sortie <dossier>
Installer les dépendances QA avec requirements-dev.txt ; utilise Edge installé.
"""
import argparse
from datetime import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import time
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
PAGES = {'index': "#commande-resume", 'commander': "#liste .article",
         'compter': "#libelle", 'promo': "#offres .offre", 'maintenance': "#grille-carnets .carte"}
CLE = 'rayon-fl.comptages-en-attente'


def empreintes():
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in ROOT.rglob('*.jsonl')}


def lire_json(chemin):
    return json.loads(chemin.read_text(encoding='utf8'))


def attendre_recalcul(module):
    fin = time.monotonic() + 80
    while getattr(module, '_recalcul_actif', False) and time.monotonic() < fin:
        time.sleep(.1)
    assert not getattr(module, '_recalcul_actif', False), 'Recalcul non terminé en 80 secondes'


def parcours(browser, url, sortie, resultats):
    for largeur, hauteur in [(320, 640), (360, 800), (768, 1024), (1024, 768)]:
        context = browser.new_context(viewport={'width': largeur, 'height': hauteur},
                                      device_scale_factor=2, is_mobile=largeur < 768,
                                      has_touch=True, locale='fr-FR', timezone_id='Europe/Paris')
        page = context.new_page()
        for nom, selecteur in PAGES.items():
            erreurs, echecs = [], []
            def erreur(exc):
                erreurs.append(str(exc))
            def console(message):
                if message.type == 'error':
                    echecs.append(message.text)
            def statut(reponse):
                if reponse.status >= 400:
                    echecs.append(f'HTTP {reponse.status} : {reponse.url}')
            page.on('pageerror', erreur)
            page.on('console', console)
            page.on('response', statut)
            reponse = page.goto(url + '/app/' + nom + '.html', wait_until='networkidle', timeout=90000)
            assert reponse.status == 200, (nom, reponse.status)
            page.wait_for_selector(selecteur, timeout=20000)
            if nom == 'compter':
                page.wait_for_function("document.querySelector('#libelle').textContent !== 'Chargement…'")
            if nom == 'maintenance':
                page.wait_for_function("!document.querySelector('#etat-global').textContent.includes('Vérification')")
            dimensions = page.evaluate('({ecran:innerWidth, document:document.documentElement.scrollWidth})')
            capture = sortie / f'{nom}-{largeur}.png'
            page.screenshot(path=str(capture), full_page=False)
            resultats.append({'test': 'page', 'page': nom, 'largeur': largeur,
                              'http': reponse.status, 'dimensions': dimensions,
                              'erreurs_js': erreurs.copy(), 'erreurs_console': echecs.copy(), 'capture': str(capture)})
            page.remove_listener('pageerror', erreur)
            page.remove_listener('console', console)
            page.remove_listener('response', statut)
            assert not erreurs, (nom, erreurs)
            assert dimensions['document'] <= largeur + 1, (nom, dimensions, largeur)
            # Toutes les ressources normalement attendues doivent répondre.
            assert not echecs, (nom, echecs)
        context.close()


def ecritures_isolees(browser, url, racine, module, sortie, resultats):
    context = browser.new_context(viewport={'width': 390, 'height': 844}, has_touch=True,
                                  is_mobile=True, device_scale_factor=2, locale='fr-FR', timezone_id='Europe/Paris')
    page = context.new_page()
    erreurs = []
    page.on('pageerror', lambda e: erreurs.append(str(e)))
    page.on('dialog', lambda dialog: dialog.accept())
    page.goto(url + '/app/compter.html', wait_until='networkidle')
    page.wait_for_function("typeof articles !== 'undefined' && articles.length > 0")
    photos = lire_json(racine / 'donnees/photos.json')['articles']
    liste = lire_json(racine / 'donnees/articles.json')['articles']
    article = next(a for a in liste if a['itm8'] in photos)
    page.click('#ouvrir-liste')
    page.fill('#recherche', article['itm8'])
    page.locator('#liste-articles .ligne-article').first.click()
    page.wait_for_selector('.photo-produit-comptage')
    page.wait_for_function("document.querySelector('.photo-produit-comptage').naturalWidth > 0")
    page.screenshot(path=str(sortie / 'comptage-photo-390.png'))
    # Une mesure connue et une correction répétée passent par l'UI puis l'API réelle.
    page.click('[data-touche="3"]')
    page.click('#valider')
    attente = page.evaluate('(cle) => JSON.parse(localStorage.getItem(cle))', CLE)
    assert len(attente) == 1 and attente[0]['itm8'] == article['itm8'] and attente[0]['colis'] == 3
    context.set_offline(True)
    page.click('#envoyer')
    page.wait_for_function("!document.querySelector('#envoyer').disabled")
    assert page.evaluate('(cle) => JSON.parse(localStorage.getItem(cle)).length', CLE) == 1
    resultats.append({'test': 'comptage-hors-ligne', 'conserve': True, 'message': page.inner_text('#resultat')})
    context.set_offline(False)
    with page.expect_response(lambda r: '/api/comptages' in r.url and r.request.method == 'POST') as envoi:
        page.click('#envoyer')
    retour = envoi.value.json()
    assert retour['ok'], retour
    page.wait_for_function('(cle) => JSON.parse(localStorage.getItem(cle)).length === 0', arg=CLE)
    # Le serveur lance le travail après avoir répondu : attendre d'abord son déclenchement.
    time.sleep(.15)
    attendre_recalcul(module)
    for quantite in [4, 5]:
        page.click('#ouvrir-liste')
        page.fill('#recherche', article['itm8'])
        page.locator('#liste-articles .ligne-article').first.click()
        page.click(f'[data-touche="{quantite}"]')
        page.click('#valider')
        with page.expect_response(lambda r: '/api/comptages' in r.url and r.request.method == 'POST') as envoi:
            page.click('#envoyer')
        assert envoi.value.json()['ok']
        page.wait_for_function('(cle) => JSON.parse(localStorage.getItem(cle)).length === 0', arg=CLE)
        time.sleep(.15)
        attendre_recalcul(module)
    etat = lire_json(racine / 'donnees/etat.json')['articles'][article['itm8']]
    assert abs(etat['position'] - 5 * article['conditionnement']) < .001, etat
    resultats.append({'test': 'comptage-et-deux-corrections-recalcules', 'article': article['itm8'], 'position': etat['position']})
    # Commande : recherche accent-insensible, ajustement local et détail/photo.
    page.goto(url + '/app/commander.html', wait_until='networkidle')
    page.wait_for_function("typeof proposition !== 'undefined' && proposition !== null")
    ligne = next(l for l in lire_json(racine / 'donnees/proposition.json')['lignes']
                 if l['itm8'] in photos and not l['masque'] and l['propose_colis'] > 0)
    page.fill('#recherche', ligne['libelle'])
    bloc = page.locator('#liste .article').filter(has=page.locator(f'[data-role="detail"]', has_text=ligne['libelle'])).first
    assert bloc.count()
    quantite_avant = bloc.locator('.val').inner_text()
    bloc.locator('[data-role="plus"]').click()
    assert bloc.locator('.val').inner_text() != quantite_avant
    bloc.locator('[data-role="detail"]').first.click()
    page.wait_for_selector('#detail.visible .photo-produit-detail')
    page.screenshot(path=str(sortie / 'commande-detail-390.png'))
    page.click('#fermer-detail')
    # Masquage : vrai écrivain des décisions, dans la copie seulement.
    with page.expect_response(lambda r: '/api/masquer' in r.url) as envoi:
        bloc.locator('[data-role="masquer"]').click()
    assert envoi.value.json()['ok']
    page.wait_for_timeout(200)
    attendre_recalcul(module)
    assert next(l for l in lire_json(racine / 'donnees/proposition.json')['lignes'] if l['itm8'] == ligne['itm8'])['masque']
    resultats.append({'test': 'commande-ajustement-detail-masquage', 'article': ligne['itm8'], 'ok': True})
    # Réception du message seulement : l'agent externe est neutralisé explicitement.
    page.goto(url + '/app/index.html', wait_until='networkidle')
    texte = 'TEST QA ISOLÉ — réception vérifiée, aucun agent ni e-mail lancé.'
    page.fill('#champ-message', texte)
    with page.expect_response(lambda r: '/api/messages' in r.url) as envoi:
        page.click('#bouton-envoyer')
    assert envoi.value.json()['ok']
    records = [json.loads(l) for l in (racine / 'donnees/messages.jsonl').read_text(encoding='utf8').splitlines() if l.strip()]
    assert any(r['texte'] == texte for r in records)
    resultats.append({'test': 'message-reception', 'ok': True, 'reponse_agent_exclue': True})
    assert not erreurs, erreurs
    context.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lecture-seule', action='store_true')
    parser.add_argument('--url', default='http://127.0.0.1:8751')
    parser.add_argument('--sortie', type=Path, default=Path(tempfile.gettempdir()) / 'preparation-audit/navigateur')
    args = parser.parse_args()
    sortie = args.sortie.resolve()
    sortie.mkdir(parents=True, exist_ok=True)
    avant = empreintes()
    resultats, serveur, temp, module = [], None, None, None
    rapport = {'commence_le': datetime.now().isoformat(), 'lecture_seule': args.lecture_seule, 'tests': resultats}
    try:
        url = args.url.rstrip('/')
        if not args.lecture_seule:
            temp = tempfile.TemporaryDirectory(prefix='preparation-qa-')
            racine = Path(temp.name)
            for dossier in ['app', 'moteur', 'donnees', 'Documents']:
                if (ROOT / dossier).exists():
                    shutil.copytree(ROOT / dossier, racine / dossier, ignore=shutil.ignore_patterns('__pycache__'))
            spec = importlib.util.spec_from_file_location('serveur_qa', racine / 'moteur/serveur.py')
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            module.lancer_reponse_message = lambda *a: 0
            serveur = module.ServeurHTTP(('127.0.0.1', 0), module.Gestionnaire)
            threading.Thread(target=serveur.serve_forever, daemon=True).start()
            url = f'http://127.0.0.1:{serveur.server_port}'
            rapport['copie_isolee'] = str(racine)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel='msedge', headless=True)
            try:
                parcours(browser, url, sortie, resultats)
                if not args.lecture_seule:
                    ecritures_isolees(browser, url, racine, module, sortie, resultats)
            finally:
                browser.close()
        rapport['ok'] = True
    except Exception as exc:
        rapport['ok'] = False
        rapport['erreur'] = str(exc)
        raise
    finally:
        if module:
            attendre_recalcul(module)
        if serveur:
            serveur.shutdown()
            serveur.server_close()
        if temp:
            temp.cleanup()
        rapport['journaux_production_inchanges'] = avant == empreintes()
        rapport['termine_le'] = datetime.now().isoformat()
        (sortie / 'resultats.json').write_text(json.dumps(rapport, ensure_ascii=False, indent=2), encoding='utf8')
        print(json.dumps(rapport, ensure_ascii=False, indent=2))
        assert rapport['journaux_production_inchanges'], 'Carnets production modifiés durant QA : examiner avant de conclure'


if __name__ == '__main__':
    main()
