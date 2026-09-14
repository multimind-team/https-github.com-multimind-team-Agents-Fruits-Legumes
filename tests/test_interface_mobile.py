"""Real browser regression tests. All HTTP is intercepted; no business writes.
Run: py -3.14 -m unittest discover -s tests -p 'test_interface*.py' -v
Requires Playwright and Chromium (or installed Microsoft Edge).
"""
import json
import os
import unittest
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
                self.assertGreaterEqual(self.page.locator('.qte .val').evaluate('e=>parseFloat(getComputedStyle(e).fontSize)'), 21)
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


if __name__ == "__main__":
    unittest.main()
