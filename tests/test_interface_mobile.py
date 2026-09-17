"""Real browser regression tests. All HTTP is intercepted; no business writes.
Run: py -3.14 -m unittest discover -s tests -p 'test_interface*.py' -v
Requires Playwright and Chromium (or installed Microsoft Edge).
"""
import json
import os
import re
import unittest
from calendar import monthrange
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
CODE = "0000000000001"
PENDING = "rayon-fl.comptages-en-attente"
MESSAGES = "rayon-fl.messages-en-attente"
ARTICLE = dict(itm8=CODE, libelle="POMME TEST", conditionnement=6, unite="kg",
               derniere_position_colis=2, part_ca_cumulee=50)
LINE = dict(ARTICLE, propose_colis=3, position_colis=2, vente_moyenne_jour=10,
            taux_perte=.05, prix_achat=1, prix_vente=2, marge_pct=50,
            fournisseur="SCAFRUIT", connu=True)
PROPOSAL = dict(date_commande="2026-09-10", date_livraison="2026-09-11",
                genere_le="fixture-before", lignes=[LINE], facteurs=dict(
                    jour_semaine_commande=1, jour_semaine_livraison=1,
                    meteo=1, ferie=.5, vacances=1.162),
                totaux=dict(articles_a_commander=1, colis=3, montant_achat=18, marge_pct=50))


class InterfaceMobileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pw = sync_playwright().start()
        try:
            cls.browser = cls.pw.chromium.launch(headless=True)
        except Exception:
            cls.browser = cls.pw.chromium.launch(headless=True, channel="msedge")

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()

    def setUp(self):
        self.context = self.browser.new_context(viewport={"width": 360, "height": 800})
        self.page = self.context.new_page()
        self.errors = []
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))
        self.page.on("dialog", lambda dialog: dialog.dismiss())
        self.posts = []
        self.fixtures = {
            "/donnees/articles.json": {"articles": [ARTICLE, dict(ARTICLE, itm8="0000000000002")]},
            "/donnees/proposition.json": PROPOSAL,
            "/donnees/promotions.json": {"source": {"fichier": "test.pdf", "pages_lues": [1]}, "offres": []},
            "/donnees/note-du-matin.json": {"entrees": []},
            "/donnees/etat.json": {"articles": {}},
        }
        self.api = lambda route: route.fulfill(json={"ok": True})
        self.context.route("**/*", self.route)

    def tearDown(self):
        self.context.close()

    def route(self, route):
        path = urlsplit(route.request.url).path
        if path.startswith("/api/"):
            self.posts.append(route.request.post_data_json)
            return self.api(route)
        if path.startswith("/app/"):
            file = ROOT / path.lstrip("/")
            if file.is_file():
                mime = {".html": "text/html", ".css": "text/css", ".js": "application/javascript"}.get(file.suffix, "application/octet-stream")
                return route.fulfill(body=file.read_bytes(), content_type=mime)
        if path in self.fixtures:
            return route.fulfill(json=self.fixtures[path])
        if path.endswith(".jsonl"):
            return route.fulfill(body="", content_type="text/plain")
        return route.fulfill(status=404, body="fixture absent")

    def open(self, name):
        self.page.goto("http://ui.test/app/" + name + ".html")
        if name == "compter":
            self.page.wait_for_function("articles.length > 0")
        if name == "commander":
            self.page.locator("#liste .article").first.wait_for()
        if name == "maintenance":
            self.page.wait_for_function("document.getElementById('etat-global').textContent !== 'Vérification…'")

    def test_storage_full_keeps_current_count_and_input(self):
        self.open("compter")
        self.page.evaluate("Storage.prototype.setItem = () => { throw new Error('quota'); }; touche=true; saisie='7'; valider()")
        self.assertEqual(self.page.evaluate("index"), 0)
        self.assertEqual(self.page.evaluate("saisie"), "7")
        self.assertRegex(self.page.locator("#resultat").inner_text(), "[Ss]tockage|[Ee]nregistr")
        self.assertEqual(self.page.evaluate(f"localStorage.getItem('{PENDING}')"), None)

    def test_count_keypad_keeps_decimal_comma_and_ignores_second_separator(self):
        self.open('compter')
        key = lambda value: self.page.locator(f'[data-touche="{value}"]').click()
        key('1'); key('virgule')
        self.assertEqual(self.page.locator('#nombre').inner_text(), '1,')
        key('2'); key('virgule'); key('3')
        self.assertEqual(self.page.locator('#nombre').inner_text(), '1,23')
        for expected in ('1,2', '1,', '1', '0'):
            key('effacer')
            self.assertEqual(self.page.locator('#nombre').inner_text(), expected)
        key('1'); key('virgule'); key('2')
        self.assertIn('7,2 kg', self.page.locator('#equivalent').inner_text())
        self.page.locator('#valider').click()
        saved = self.page.evaluate(f"JSON.parse(localStorage.getItem('{PENDING}'))")
        self.assertEqual((saved[0]['colis'], saved[0]['unites'], saved[0]['conditionnement']), (1.2, 7.2, 6))
        self.assertEqual(self.posts, [])
        self.assertFalse(self.errors)

    def test_decimal_negative_count_keeps_original_packaging_and_sends_only_saved(self):
        self.open('compter')
        for value in ('signe', 'virgule', '5'):
            self.page.locator(f'[data-touche="{value}"]').click()
        self.assertEqual(self.page.locator('#nombre').inner_text(), '−0,5')
        self.assertIn('0,5 colis', self.page.locator('#equivalent').inner_text())
        self.fixtures['/donnees/articles.json'] = {'articles': [dict(ARTICLE, conditionnement=10), dict(ARTICLE, itm8='0000000000002')]}
        self.page.evaluate('chargerArticles(false)')
        self.page.locator('#valider').click()
        saved = self.page.evaluate(f"JSON.parse(localStorage.getItem('{PENDING}'))")
        self.assertEqual((saved[0]['itm8'], saved[0]['colis'], saved[0]['unites'], saved[0]['conditionnement']), (CODE, -.5, -3, 6))
        for value in ('2', 'virgule', '5'):
            self.page.locator(f'[data-touche="{value}"]').click()
        self.page.locator('#envoyer').click()
        self.page.wait_for_function('!envoiEnCours')
        self.assertEqual(self.posts, [{'comptages': saved}])
        self.assertEqual(self.page.locator('#nombre').inner_text(), '2,5')
        self.assertEqual(self.page.evaluate(f"JSON.parse(localStorage.getItem('{PENDING}'))"), [])
        self.assertFalse(self.errors)

    def test_count_steps_keep_all_entered_decimal_digits_and_cross_zero(self):
        self.open('compter')
        for value in ('1', '2', 'virgule', '3', '4', '5', '6'):
            self.page.locator(f'[data-touche="{value}"]').click()
        self.assertEqual(self.page.locator('#nombre').inner_text(), '12,3456')
        self.page.locator('#plus').click()
        self.assertEqual(self.page.locator('#nombre').inner_text(), '13,3456')
        self.page.locator('#moins').click()
        self.assertEqual(self.page.locator('#nombre').inner_text(), '12,3456')
        self.page.evaluate("saisie='0.25'; negatif=false; afficher()")
        self.page.locator('#moins').click()
        self.assertEqual(self.page.locator('#nombre').inner_text(), '−0,75')
        self.page.locator('#plus').click()
        self.assertEqual(self.page.locator('#nombre').inner_text(), '0,25')
        # Une valeur reçue sous forme scientifique conserve aussi sa précision.
        self.page.evaluate('touche=false; attendu=1e-7')
        self.page.locator('#plus').click()
        self.assertEqual(self.page.locator('#nombre').inner_text(), '1,0000001')
        self.assertEqual(self.posts, [])
        self.assertFalse(self.errors)

    def test_invalid_or_out_of_range_count_preserves_saved_measurement(self):
        self.open('compter')
        self.page.locator('#valider').click()
        before = self.page.evaluate(f"JSON.parse(localStorage.getItem('{PENDING}'))")
        for text, negative, message in [('9' * 400, False, 'non valide'), ('10000', False, '9 999'), ('10000', True, '9 999')]:
            with self.subTest(text=text[:10], negative=negative):
                self.page.evaluate('([text, negative]) => {allerA(0); touche=true; saisie=text; negatif=negative; valider()}', [text, negative])
                self.assertEqual(self.page.evaluate(f"JSON.parse(localStorage.getItem('{PENDING}'))"), before)
                self.assertEqual(self.page.evaluate('index'), 0)
                self.assertIn(message, self.page.locator('#resultat').inner_text())
        self.page.evaluate('allerA(0)')
        for value in ('9', '9', '9', '8', 'virgule', '7', '5'):
            self.page.locator(f'[data-touche="{value}"]').click()
        self.page.locator('#valider').click()
        saved = self.page.evaluate(f"JSON.parse(localStorage.getItem('{PENDING}'))")
        self.assertEqual((saved[0]['colis'], saved[0]['unites']), (9998.75, 59992.5))
        for value in (9999, -9999):
            with self.subTest(boundary=value):
                self.page.evaluate('(value) => {allerA(0); touche=true; saisie=String(Math.abs(value)); negatif=value<0; valider()}', value)
                saved = self.page.evaluate(f"JSON.parse(localStorage.getItem('{PENDING}'))")
                self.assertEqual(saved[0]['colis'], value)
        self.assertEqual(self.posts, [])
        self.assertFalse(self.errors)

    def test_decimal_keypad_remains_accessible_without_an_extra_row(self):
        self.install_photo_fixture()
        self.fixtures['/donnees/articles.json'] = {'articles': [dict(ARTICLE, libelle='TOMATE CERISE ALLONGEE ROUGE ORIGINE FRANCE')]}
        for width in (320, 360, 768):
            with self.subTest(width=width):
                self.page.set_viewport_size({'width': width, 'height': 800})
                self.open('compter')
                comma = self.page.locator('[data-touche="virgule"]')
                self.assertEqual(comma.inner_text(), ',')
                boxes = self.page.locator('#pave button').evaluate_all('buttons => buttons.map(b => {const r=b.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height};})')
                self.assertTrue(all(b['width'] >= 44 and b['height'] >= 44 for b in boxes))
                self.assertTrue(all(b['x'] >= 0 and b['x'] + b['width'] <= width for b in boxes))
                self.assertEqual(len({round(b['y']) for b in boxes}), 4)
                if width >= 360:
                    send = self.page.locator('#envoyer').bounding_box()
                    self.assertLessEqual(send['y'] + send['height'], 800)
        self.assertEqual(self.posts, [])
        self.assertFalse(self.errors)

    def test_refresh_keeps_visible_article_and_packaging_until_validation(self):
        self.open("compter")
        self.page.locator('[data-touche="3"]').click()
        self.fixtures['/donnees/articles.json'] = {'genere_le': 'new', 'articles': [
            dict(ARTICLE, itm8='0000000000002', libelle='CAROTTE', conditionnement=10),
            dict(ARTICLE, conditionnement=12),
        ]}
        self.page.evaluate("chargerArticles(false)")
        self.assertEqual(self.page.locator('#libelle').inner_text(), 'POMME TEST')
        self.assertIn('6 kg', self.page.locator('#repere').inner_text())
        self.page.locator('#valider').click()
        pending = self.page.evaluate(f"JSON.parse(localStorage.getItem('{PENDING}'))")
        self.assertEqual((pending[0]['itm8'], pending[0]['colis'], pending[0]['unites'], pending[0]['conditionnement']), (CODE, 3, 18, 6))
        self.assertEqual(self.page.locator('#libelle').inner_text(), 'CAROTTE')
        self.assertEqual(self.page.evaluate("JSON.parse(localStorage.getItem(CLE_AVANCEMENT)).itm8"), '0000000000002')

    def test_overlapping_refresh_ignores_late_old_response(self):
        self.open('compter')
        result = self.page.evaluate('''async () => {
          const old = articles[0]; const responses = [];
          window.fetch = () => new Promise(resolve => responses.push(resolve));
          const first = chargerArticles(false); const second = chargerArticles(false);
          responses[1]({ok:true,json:async()=>({articles:[{...old,libelle:'RECENT'}]})});
          await second;
          responses[0]({ok:true,json:async()=>({articles:[{...old,libelle:'ANCIEN'}]})});
          await first;
          return listeEnAttente.articles[0].libelle;
        }''')
        self.assertEqual(result, 'RECENT')

    def test_revisiting_count_after_packaging_change_requires_explicit_input(self):
        self.open('compter')
        self.page.locator('#valider').click()
        before = self.page.evaluate(f"JSON.parse(localStorage.getItem('{PENDING}'))")
        self.page.evaluate("articles[0].conditionnement=10; allerA(0)")
        self.assertEqual(self.page.locator('#nombre').inner_text(), '—')
        self.page.locator('#valider').click()
        self.assertEqual(self.page.evaluate(f"JSON.parse(localStorage.getItem('{PENDING}'))"), before)
        self.assertIn('Colisage différent', self.page.locator('#resultat').inner_text())
        self.page.locator('[data-touche="3"]').click()
        self.page.locator('#valider').click()
        after = self.page.evaluate(f"JSON.parse(localStorage.getItem('{PENDING}'))")
        self.assertEqual((after[0]['conditionnement'], after[0]['unites']), (10, 30))

    def test_http_failure_reports_cached_articles(self):
        self.open('compter')
        self.page.route('**/donnees/articles.json*', lambda route: route.fulfill(status=500, body='Erreur'))
        self.page.evaluate('chargerArticles(false)')
        self.assertIn('cache actif', self.page.locator('#statut-reseau').inner_text())
        self.assertEqual(self.page.locator('#libelle').inner_text(), 'POMME TEST')

    def test_failed_calculation_is_visible_and_old_version_is_not_certified(self):
        self.fixtures['/donnees/recalcul.json'] = {'etat':'echec', 'operation_id':'a'*32}
        self.open('commander')
        self.page.wait_for_function("etatRecalcul?.etat === 'echec'")
        self.assertIn('recalcul a échoué', self.page.locator('#alerte').inner_text())
        self.fixtures['/donnees/recalcul.json'] = {'etat':'termine', 'operation_id':'b'*32}
        self.page.evaluate('chargerEtatRecalcul()')
        self.assertIn('ne correspond pas', self.page.locator('#alerte').inner_text())

    def test_online_retries_pending_message_without_reload(self):
        self.open('index')
        self.api = lambda route: route.abort('failed')
        self.page.locator('#champ-message').fill('Message hors connexion')
        self.page.locator('#bouton-envoyer').click()
        self.page.wait_for_function("!envoiMessagesEnCours")
        self.assertEqual(len(self.page.evaluate(f"JSON.parse(localStorage.getItem('{MESSAGES}'))")), 1)
        self.api = lambda route: route.fulfill(json={'ok': True})
        self.page.evaluate("window.dispatchEvent(new Event('online'))")
        self.page.wait_for_function("JSON.parse(localStorage.getItem(CLE_MESSAGES)).length === 0")
        self.assertIn('Envoyé', self.page.locator('#retour-message').inner_text())

    def test_maintenance_uses_summary_instead_of_downloading_years(self):
        requests = []
        self.page.on('request', lambda request: requests.append(urlsplit(request.url).path))
        self.api = lambda route: route.fulfill(json={'ok': True, 'fichiers':[{'annee':'2030'}], 'total_lignes':150000})
        self.open('maintenance')
        self.assertIn('/api/carnets/resume', requests)
        self.assertFalse(any('/donnees/faits/' in p for p in requests))
        self.assertIn('150000', self.page.locator('#grille-carnets').inner_text())

    def test_storage_full_reports_failed_manual_order_adjustment(self):
        self.open("commander")
        messages = []
        self.page.on("dialog", lambda dialog: messages.append(dialog.message))
        self.page.evaluate("() => { Storage.prototype.setItem = () => { throw new Error('quota'); }; }")
        self.page.locator('[data-role="plus"]').first.click()
        self.assertEqual(self.page.evaluate("quantite(proposition.lignes[0])"), 3)
        self.assertTrue(any('non enregistr' in m for m in messages), messages)
        self.assertEqual(self.errors, [])

    def test_send_preserves_counts_created_during_fetch_and_refuses_parallel_send(self):
        self.open("compter")
        result = self.page.evaluate("""async () => {
            const old = {id:'same', itm8:'1', colis:2, date:aujourdhui()};
            localStorage.setItem(CLE_COMPTAGES, JSON.stringify([old]));
            const finishes=[]; let calls=0;
            window.fetch = () => { calls++; return new Promise(r => {finishes.push(r)}); };
            const first = envoyerComptages();
            envoyerComptages();
            localStorage.setItem(CLE_COMPTAGES, JSON.stringify([{...old,colis:7},{id:'new',itm8:'2',colis:4}]));
            finishes.forEach(finish => finish({ok:true, json:async()=>({ok:true})}));
            await first;
            return {calls, pending:JSON.parse(localStorage.getItem(CLE_COMPTAGES))};
        }""")
        self.assertEqual(result["calls"], 1)
        self.assertEqual([x["colis"] for x in result["pending"]], [7, 4])

    def test_failed_send_does_not_claim_nothing_arrived(self):
        self.open("compter")
        self.page.evaluate("""async () => {
            localStorage.setItem(CLE_COMPTAGES, JSON.stringify([{id:'a'}]));
            window.fetch=async()=>{throw new Error('lost acknowledgement')};
            await envoyerComptages();
        }""")
        text = self.page.locator("#resultat").inner_text()
        self.assertNotIn("Rien n'est parti", text)
        self.assertIn("non confirmé", text)

    def test_daily_memory_failure_does_not_lose_confirmed_count(self):
        self.open("compter")
        self.page.evaluate("""() => {
            const original = Storage.prototype.setItem;
            Storage.prototype.setItem = function(key, value) {
                if(key===CLE_DU_JOUR) throw new Error('quota');
                return original.call(this,key,value);
            };
            touche=true; saisie='7'; valider(); index=0; touche=false; afficher();
        }""")
        self.assertEqual(self.page.locator("#nombre").inner_text(), "7")
        self.page.evaluate("""async () => {
            window.fetch=async()=>({ok:true,json:async()=>({ok:true})});
            await envoyerComptages();
        }""")
        self.assertEqual(len(self.page.evaluate(f"JSON.parse(localStorage.getItem('{PENDING}'))")), 1)
        self.assertRegex(self.page.locator("#resultat").inner_text(), "[Ss]tockage|[Mm]émoire")

    def test_imported_count_text_never_creates_html(self):
        self.open("compter")
        self.page.evaluate("""() => {
            articles[0].libelle='<img src=x onerror=window.__xss=1>';
            articles[0].unite='<svg onload=window.__xss=1>';
            articles[0].position_perdue=true;
            afficher(); afficherListe('');
        }""")
        self.assertEqual(self.page.locator('#liste-articles img, #repere svg').count(), 0)
        self.assertIn('<img', self.page.locator('#liste-articles').inner_text())

    def test_detail_unit_never_creates_html(self):
        self.open("commander")
        self.page.evaluate("proposition.lignes[0].unite='<svg onload=window.__xss=1>'; montrerDetail(proposition.lignes[0])")
        self.assertEqual(self.page.locator('#detail-calcul svg').count(), 0)

    def test_home_totals_never_create_html(self):
        self.fixtures['/donnees/proposition.json'] = dict(PROPOSAL, totaux=dict(PROPOSAL['totaux'], articles_a_commander='<img src=x onerror=window.__xss=1>'))
        self.open('index')
        self.page.wait_for_function("document.getElementById('etat').textContent !== '…'")
        self.assertEqual(self.page.locator('#commande-resume img').count(), 0)

    def test_empty_stock_is_not_sent_as_zero(self):
        self.open('commander')
        self.page.evaluate('montrerDetail(proposition.lignes[0])')
        self.page.locator('#detail-stock-modifier').click()
        self.page.locator('#detail-stock-valeur').fill('')
        self.page.locator('#detail-stock-valider').click()
        self.assertEqual(self.posts, [])
        self.assertIn('quantité', self.page.locator('#detail-stock-etat').inner_text())

    def test_unknown_stock_starts_blank(self):
        self.open('commander')
        self.page.evaluate('proposition.lignes[0].position_colis=null; montrerDetail(proposition.lignes[0])')
        self.page.locator('#detail-stock-modifier').click()
        self.assertEqual(self.page.locator('#detail-stock-valeur').input_value(), '')

    def test_http_error_does_not_claim_stock_was_saved(self):
        self.api = lambda route: route.fulfill(status=500, json={'ok':True})
        self.open('commander')
        self.page.evaluate('montrerDetail(proposition.lignes[0])')
        self.page.locator('#detail-stock-modifier').click()
        self.page.locator('#detail-stock-valeur').fill('7')
        self.page.locator('#detail-stock-valider').click()
        self.page.wait_for_function("document.getElementById('detail-stock-etat').textContent !== 'Enregistrement…'")
        self.assertNotIn('✓ enregistré', self.page.locator('#detail-stock-etat').inner_text())

    def test_detail_does_not_recalculate_incomplete_engine_inputs(self):
        self.open('commander')
        self.page.evaluate('montrerDetail(proposition.lignes[0])')
        self.assertIn('non disponible', self.page.locator('#detail-calcul').inner_text())
        self.assertNotIn('21,05', self.page.locator('#detail-calcul').inner_text())
        self.page.evaluate('proposition.lignes[0].demande=17.432; montrerDetail(proposition.lignes[0])')
        self.assertIn('17,43', self.page.locator('#detail-calcul').inner_text())

    def test_stock_acknowledged_but_stale_proposal_remains_explicit(self):
        self.open('commander')
        self.page.evaluate('montrerDetail(proposition.lignes[0])')
        self.page.locator('#detail-stock-modifier').click()
        self.page.locator('#detail-stock-valeur').fill('7')
        self.page.locator('#detail-stock-valider').click()
        self.page.wait_for_function("document.getElementById('detail-stock-etat').textContent.includes('actualis')", timeout=15000)
        self.assertTrue(self.page.locator('#detail').is_visible())
        self.assertIn('enregistré', self.page.locator('#detail-stock-etat').inner_text())

    def install_photo_fixture(self):
        # A real local image with an isolated mapping; never edit the catalogue.
        photo = next(iter(json.loads((ROOT / 'donnees/photos.json').read_text(encoding='utf-8'))['articles'].values()))
        self.fixtures['/donnees/photos.json'] = {'version': 1, 'articles': {CODE: photo}}

    def test_photos_render_without_changing_quantities(self):
        self.install_photo_fixture()
        for width in (360, 768):
            with self.subTest(width=width):
                self.page.set_viewport_size({'width':width, 'height':1024})
                self.open('compter')
                image = self.page.locator('.photo-produit-comptage')
                self.assertEqual(image.count(), 1)
                self.assertEqual(image.bounding_box()['width'], 64 if width == 360 else 112)
                self.assertEqual(self.page.locator('#nombre').inner_text(), '2')
                self.open('commander')
                image = self.page.locator('#liste .photo-produit-liste')
                self.assertEqual(image.count(), 1)
                # La réponse des photos peut remplacer la liste pendant cette
                # mesure ; lire un élément encore attaché au document courant.
                self.page.wait_for_function("parseFloat(getComputedStyle(document.querySelector('.qte .val')).fontSize) >= 21")
                self.page.evaluate('montrerDetail(proposition.lignes[0])')
                self.assertLessEqual(self.page.locator('.photo-produit-detail').bounding_box()['width'], 200)
        self.assertEqual(self.posts, [])
        self.assertEqual(self.errors, [])

    def test_all_pages_fit_phone_and_tablet_with_long_imported_text(self):
        long = 'LIBELLE-SOURCE-' * 20
        self.fixtures['/donnees/articles.json'] = {'articles':[dict(ARTICLE, libelle=long)]}
        self.fixtures['/donnees/proposition.json'] = dict(PROPOSAL, lignes=[dict(LINE, libelle=long, fournisseur=long)])
        self.fixtures['/donnees/note-du-matin.json'] = {'entrees':[{'texte':long, 'gravite':'grave'}]}
        self.fixtures['/donnees/promotions.json']['source']['fichier'] = long + '.pdf'
        for width in (360, 768):
            for name in ('index', 'compter', 'commander', 'promo', 'maintenance'):
                with self.subTest(width=width, page=name):
                    self.page.set_viewport_size({'width':width, 'height':1024})
                    self.open(name)
                    if name == 'maintenance':
                        self.page.evaluate('afficherJournal(JSON.stringify({message:"X".repeat(300),agent:"A".repeat(100),horodatage:"2026-09-09T10:00:00"}))')
                    self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'), width)
                    if name == 'commander':
                        self.page.evaluate('montrerDetail(proposition.lignes[0])')
                        self.page.locator('#detail-stock-modifier').click()
                        self.assertLessEqual(self.page.locator('#detail').evaluate('e=>e.scrollWidth'), width)
        self.assertEqual(self.errors, [])

    def test_no_remote_font_dependency(self):
        for file in (ROOT / 'app').glob('*.html'):
            self.assertNotIn('fonts.googleapis.com', file.read_text(encoding='utf-8'), file.name)

    def test_send_button_fits_800px_with_photo_and_long_name(self):
        self.install_photo_fixture()
        self.fixtures['/donnees/articles.json'] = {'articles':[dict(ARTICLE, libelle='TOMATE CERISE ALLONGEE ROUGE ORIGINE FRANCE') ]}
        self.open('compter')
        self.page.locator('.photo-produit-comptage').wait_for()
        self.assertEqual(self.page.locator('.photo-produit-comptage').bounding_box()['width'], 64)
        rect = self.page.locator('#envoyer').bounding_box()
        self.assertLessEqual(rect['y'] + rect['height'], 800)
        self.assertGreaterEqual(self.page.locator('#pave button').first.bounding_box()['height'], 44)

    def test_maintenance_reports_display_limit_and_network_failure(self):
        self.open('maintenance')
        self.page.evaluate('afficherJournal(Array.from({length:205},(_,i)=>JSON.stringify({message:"action "+i})).join("\\n"))')
        self.assertNotIn('Jamais tronqué', self.page.locator('body').inner_text())
        self.assertEqual(self.page.locator('#journal .journal-ligne').count(), 200)
        self.assertIn('200 sur 205', self.page.locator('body').inner_text())
        self.page.evaluate("""async () => {
            window.fetch=async()=>{throw new Error('offline')};
            await chargerCarnets();
        }""")
        self.assertNotIn('Serveur actif', self.page.locator('#etat-global').inner_text())
        self.assertIn('indisponible', self.page.locator('#etat-global').inner_text().lower())

    def test_message_queue_preserves_new_messages_during_fetch(self):
        self.open('index')
        result = self.page.evaluate("""async () => {
            await envoyerMessages();
            localStorage.setItem(CLE_MESSAGES, JSON.stringify([{texte:'old',ecrit_le:'1'}]));
            const finishes=[]; let calls=0;
            window.fetch=()=>{calls++; return new Promise(r=>finishes.push(r))};
            const first=envoyerMessages(); const second=envoyerMessages();
            localStorage.setItem(CLE_MESSAGES, JSON.stringify([{texte:'old',ecrit_le:'1'},{texte:'new',ecrit_le:'2'}]));
            finishes.forEach(r=>r({ok:true,json:async()=>({ok:true})}));
            await first; await second;
            return {calls,pending:JSON.parse(localStorage.getItem(CLE_MESSAGES))};
        }""")
        self.assertEqual(result['calls'], 1)
        self.assertEqual([x['texte'] for x in result['pending']], ['new'])


    def analyse_fixture(self):
        return {
            "calcule_le": "2028-01-10T08:00:00", "periode": {
                "date_debut": "2027-01-01", "date_fin": "2028-01-09",
                "total_unites_vendues": 20, "total_jours_ouverts": 2,
                "moyenne_quotidienne_globale": 10, "total_articles_analyses": 1},
            "mois": [{"nom": "Janvier", "moyenne_quotidienne": 10,
                       "part_annuelle_pct": 100, "famille_dominante": "autres",
                       "par_annee": {"2027": {"moyenne_jour": 8}, "2028": {"moyenne_jour": 12}}}],
            "semaines": [], "jours_semaine": [], "meteo": [], "vacances": [],
            "feries_et_veilles": [], "articles": {CODE: {
                "itm8": CODE, "libelle": 'CÉLERI <img src=x onerror="window.injection=true">',
                "famille": "autres", "volume_total_2ans_demi": 20, "jours_observes": 2,
                "ventes_par_mois": {}, "ratios_sensibilite": {"canicule_sup_30": 0}}}}

    def test_analysis_uses_loaded_dates_years_and_safe_product_text(self):
        self.fixtures['/donnees/analyse-ventes-annuelle-saisonniere.json'] = self.analyse_fixture()
        self.context.add_init_script("localStorage.setItem('rayon-fl.theme', 'clair')")
        self.open('analyse-historique')
        self.page.wait_for_function("document.getElementById('stat-total-ventes').textContent === '20'")
        self.assertIn('01/01/2027 au 09/01/2028', self.page.locator('#periode-analyse').inner_text())
        self.assertIn('2028 (u/j)', self.page.locator('#entete-mois').text_content())
        self.assertNotIn('2024', self.page.locator('#entete-mois').text_content())
        self.assertTrue(self.page.locator('body').evaluate("e => e.classList.contains('theme-clair')"))
        self.page.click('#bouton-theme')
        self.assertEqual(self.page.evaluate("localStorage.getItem('rayon-fl.theme')"), 'sombre')
        self.page.click('[data-cible="vue-produits"]')
        self.page.fill('#champ-recherche-produit', 'celeri')
        self.assertEqual(self.page.locator('.fiche-article').count(), 1)
        self.assertEqual(self.page.locator('.fiche-article img').count(), 0)
        self.assertIn('x0', self.page.locator('.fiche-article').inner_text())
        self.assertFalse(self.page.evaluate('Boolean(window.injection)'))
        self.assertFalse(self.errors)

    def test_analysis_unavailable_has_no_hardcoded_statistics(self):
        self.context.add_init_script("Storage.prototype.getItem = () => { throw new Error('blocked') }")
        self.open('analyse-historique')
        self.page.wait_for_function("document.getElementById('periode-analyse').textContent.includes('indisponible')")
        self.assertEqual(self.page.locator('#stat-total-ventes').inner_text(), '—')
        self.page.click('#bouton-theme')
        self.assertFalse(self.errors)

    def test_standalone_backup_announcement_visible_alongside_reply(self):
        message = dict(id='m1', texte='Question du rayon', ecrit_le='2026-09-15T08:00:00')
        replies = [dict(en_reponse_a='m1', texte='Réponse ciblée', ecrit_le='2026-09-15T08:01:00'),
                   dict(texte='Sauvegarde GitHub vérifiée abc123', ecrit_le='2026-09-15T08:02:00')]
        self.context.route('**/donnees/messages.jsonl*', lambda r: r.fulfill(body=json.dumps(message)))
        self.context.route('**/donnees/reponses.jsonl*', lambda r: r.fulfill(body='\n'.join(map(json.dumps, replies))))
        self.open('index')
        self.page.wait_for_function("document.getElementById('fil-messages').textContent.includes('abc123')")
        self.assertIn('Réponse ciblée', self.page.locator('#fil-messages').inner_text())
        self.assertFalse(self.errors)

    def test_ambiguous_group_is_visible_and_manual_choice_preserved(self):
        self.open('commander')
        self.page.evaluate("""() => {
            Object.assign(proposition.lignes[0], {propose_colis:0, article_stock:'principal',
                commande_groupe_ambigue:true, motif_commande_groupe:'Choisir une offre pour ce stock.'});
            afficher(); majAlerte();
        }""")
        self.assertIn('Choix d’offre nécessaire', self.page.locator('#alerte').inner_text())
        self.page.click('#bouton-etat')
        self.assertIn('Choisir une offre', self.page.locator('#liste').inner_text())
        self.page.locator('#liste [data-role="plus"]').click()
        self.page.click('#bouton-etat')
        self.assertIn('1', self.page.locator('#liste .val').inner_text())
        self.assertTrue(self.page.evaluate("proposition.lignes[0].commande_groupe_ambigue"))

    def test_product_graph_uses_group_and_reference_year_instead_of_fixed_dates(self):
        data = self.analyse_fixture()
        profile = data['articles'].pop(CODE)
        profile.update(ventes_par_mois={'1': {'moyenne_jour': 8}, '2': {'moyenne_jour': 10}},
                       saisonnalite={'mois_actuel': 1}, courbes_hebdo={'2027': [1]*53},
                       ventes_quotidiennes={'2028-01-09': 3},
                       historique_mensuel_par_annee={'2027': {'1': {'moyenne_jour': 8}}})
        data['articles']['principal'] = profile
        data['annee_reference'] = 2028
        self.fixtures['/donnees/analyse-ventes-annuelle-saisonniere.json'] = data
        self.fixtures['/donnees/proposition.json'] = dict(PROPOSAL, lignes=[dict(LINE, article_stock='principal')])
        self.open('commander')
        self.page.locator('#liste [data-role="detail"]').first.click()
        self.page.wait_for_selector('#svg-ventes-annuel')
        detail = self.page.locator('#detail-graphique').inner_text()
        self.assertIn('2027 / 2028', detail)
        self.assertIn('Moyenne Fév', detail)
        self.assertNotIn('2026', detail)
        self.assertNotIn('rupture', detail)
        self.assertFalse(self.errors)

    def install_graph_calendar_fixture(self, day, weekly):
        data = self.analyse_fixture()
        data['annee_reference'] = day.year
        data['periode']['date_fin'] = day.isoformat()
        data['articles'][CODE].update(
            ventes_par_mois={str(day.month): {'moyenne_jour': 8}},
            saisonnalite={'mois_actuel': day.month}, courbes_hebdo=weekly,
            ventes_quotidiennes={day.isoformat(): 11})
        self.fixtures['/donnees/analyse-ventes-annuelle-saisonniere.json'] = data
        self.open('commander')
        self.page.locator('#liste [data-role="detail"]').first.click()
        self.page.wait_for_selector('#svg-ventes-annuel')

    @staticmethod
    def graph_date_x(day):
        return 38 + (day.month - 1 + (day.day - .5) / monthrange(day.year, day.month)[1]) * (502 / 12)

    def hover_graph_date(self, day):
        self.page.locator('#svg-ventes-annuel').evaluate('''(svg, x) => {
            const rect = svg.getBoundingClientRect();
            svg.dispatchEvent(new MouseEvent('mousemove', {
                clientX: rect.left + x / 560 * rect.width, clientY: rect.top + 50
            }));
        }''', self.graph_date_x(day))
        return self.page.locator('#graph-infobulle').inner_text()

    def test_graph_weeks_follow_iso_dates_for_august_25_and_empty_area(self):
        weekly = [None] * 53
        weekly[31], weekly[33], weekly[34] = 132, 134, 135
        self.install_graph_calendar_fixture(date(2026, 8, 25), {'2025': weekly})
        # Le point de S35 est placé au jeudi 28 août, pas à 35/52 de l'année.
        path = self.page.locator('path[stroke="var(--graph-n1-stroke)"]').get_attribute('d')
        coordinates = [float(n) for n in re.findall(r'-?\d+(?:\.\d+)?', path)]
        self.assertAlmostEqual(coordinates[-2], self.graph_date_x(date.fromisocalendar(2025, 35, 4)), delta=.06)
        text = self.hover_graph_date(date(2026, 8, 25))
        self.assertIn('2026 : 11', text)
        self.assertIn('2025 (S35) : 135', text)
        self.assertNotIn('2025 (S34)', text)
        # La même chronologie vaut dans une zone sans point quotidien proche.
        text = self.hover_graph_date(date(2025, 8, 5))
        self.assertIn('2025 (S32) : 132', text)
        self.assertFalse(self.errors)
        self.assertEqual(self.posts, [])

    def test_graph_keeps_real_week_53_and_its_iso_year_at_calendar_boundary(self):
        weekly = [None] * 53
        weekly[51], weekly[52] = 152, 153
        self.install_graph_calendar_fixture(date(2021, 12, 31), {'2020': weekly})
        path = self.page.locator('path[stroke="var(--graph-n1-stroke)"]').get_attribute('d')
        coordinates = [float(n) for n in re.findall(r'-?\d+(?:\.\d+)?', path)]
        self.assertAlmostEqual(coordinates[-2], self.graph_date_x(date.fromisocalendar(2020, 53, 4)), delta=.06)
        self.assertIn('2020 (S53) : 153', self.hover_graph_date(date(2021, 12, 31)))
        # Le 1er janvier 2021 appartient encore à 2020 S53 : conserver l'année ISO.
        self.install_graph_calendar_fixture(date(2022, 1, 1), {'2020': weekly, '2021': [None] * 53})
        self.assertIn('2020 (S53) : 153', self.hover_graph_date(date(2022, 1, 1)))
        self.assertFalse(self.errors)
        self.assertEqual(self.posts, [])

    def test_graph_ignores_late_response_after_opening_another_article(self):
        self.open('commander')
        text = self.page.evaluate('''async () => {
            let finish;
            chargerAnalyseHistorique = () => new Promise(resolve => { finish = resolve; });
            document.getElementById('detail-photo').dataset.itm8 = proposition.lignes[0].itm8;
            const pending = afficherGraphiqueArticle(proposition.lignes[0]);
            document.getElementById('detail-photo').dataset.itm8 = 'AUTRE';
            document.getElementById('detail-graphique').textContent = 'Article suivant';
            finish({articles:{}});
            await pending;
            return document.getElementById('detail-graphique').textContent;
        }''')
        self.assertEqual(text, 'Article suivant')
        self.assertFalse(self.errors)
        self.assertEqual(self.posts, [])


if __name__ == "__main__":
    unittest.main()
