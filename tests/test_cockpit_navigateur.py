"""Parcours réel Edge du cockpit, exclusivement via lancer_tests_isoles.py."""
from datetime import date, timedelta
import importlib.util
import json
import os
from pathlib import Path
import threading
import time
import unittest
import tempfile
from playwright.sync_api import sync_playwright
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.environ.get("PREPARATION_TEST_SANDBOX"), "Copie isolée obligatoire")
class CockpitNavigateurTests(unittest.TestCase):
    def test_parcours_et_ecritures_reelles_en_copie(self):
        spec = importlib.util.spec_from_file_location("serveur_cockpit_qa", ROOT / "moteur/serveur.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        serveur = module.ServeurHTTP(("127.0.0.1", 0), module.Gestionnaire)
        threading.Thread(target=serveur.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{serveur.server_port}"
        sortie = Path(os.environ.get("COCKPIT_QA_OUTPUT", Path(tempfile.gettempdir()) / "cockpit-qa"))
        sortie.mkdir(parents=True, exist_ok=True)
        erreurs = []
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(channel="msedge", headless=True)
                page = browser.new_page(viewport={"width": 1440, "height": 1000}, locale="fr-FR", timezone_id="Europe/Paris")
                page.set_default_timeout(90000)
                page.on("pageerror", lambda err: erreurs.append(err.stack))
                def confirmer():
                    try:
                        page.wait_for_selector('#confirm-dialog[open]', timeout=5000)
                    except Exception:
                        page.screenshot(path=str(sortie / 'cockpit-echec.png'), full_page=True)
                        details=page.evaluate("({forms:[...document.forms].map(f=>({id:f.id,valid:f.checkValidity(),invalid:[...f.elements].filter(x=>x.validity&&!x.validity.valid).map(x=>({name:x.name,message:x.validationMessage}))})),notice:document.querySelector('#notice').textContent,status:document.querySelector('.form-status')?.textContent})")
                        details['dialog']=page.locator('#confirm-dialog').evaluate('(el)=>el.outerHTML')
                        self.fail(str({'erreurs':erreurs,'details':details}))
                    with page.expect_response(lambda response: response.request.method == 'POST' and '/api/' in response.url):
                        page.locator('#confirm-dialog [value="ok"]').click()
                self.assertEqual(page.goto(url + "/app/cockpit.html").status, 200)
                page.wait_for_selector("#kpis .kpi")
                page.screenshot(path=str(sortie / "cockpit-vue-ensemble.png"), full_page=True)
                data = page.request.get(url + "/api/pilotage").json()
                article = next(a for a in data["articles"] if a.get("comptable") and a.get("conditionnement_editable")
                               and a.get("propose_colis") is not None and not a.get("commande_groupe_ambigue")
                               and a["itm8"] == a.get("article_stock") and not a.get("masque"))
                code = article["itm8"]
                page.locator('.nav-item[data-view="products"]').click()
                page.fill("#product-search", code)
                page.locator('#product-list [data-product]').first.click()
                page.wait_for_selector("#product-detail .tabbar")
                page.locator('[data-tab="context"]').click()
                form = page.locator("#context-form")
                form.locator('[name="emplacement"]').select_option("tg")
                form.locator('[name="debut"]').fill(date.today().isoformat())
                form.locator('[name="fin"]').fill((date.today()+timedelta(days=14)).isoformat())
                form.locator('[name="note"]').fill("QA COPIE — <img src=x onerror=alert(1)> observation terrain")
                form.locator('[name="motif"]').fill("QA copie isolée : mise en avant vérifiée pour le parcours navigateur.")
                # Un clic répété sur la vue active ne doit pas perdre un brouillon.
                page.locator('.nav-item[data-view="products"]').click()
                self.assertIn("QA COPIE", form.locator('[name="note"]').input_value())
                form.locator('button[type="submit"]').click()
                confirmer()
                page.wait_for_function("!document.querySelector('#refresh').disabled")
                self.assertIn("enregistré", page.locator("#notice").inner_text())
                self.assertNotIn("error", page.locator("#notice").get_attribute("class"))
                contexte = page.request.get(url + "/api/contexte").json()["articles"][code]
                self.assertEqual(contexte["emplacement"], "tg")
                self.assertIn("<img", contexte["note"])
                page.locator('[data-tab="history"]').click()
                self.assertEqual(page.locator("#detail-panel .human-note img").count(), 0)
                page.screenshot(path=str(sortie / "cockpit-enquete.png"), full_page=True)
                page.locator('[data-tab="promo"]').click()
                form = page.locator("#promo-form")
                form.locator('[name="promo_debut"]').fill((date.today()-timedelta(days=12)).isoformat())
                form.locator('[name="promo_fin"]').fill((date.today()-timedelta(days=4)).isoformat())
                form.locator('[name="precommande_colis"]').fill("12")
                form.locator('[name="prix_promo"]').fill("1.99")
                form.locator('[name="unite_prix_promo"]').select_option("kg")
                form.locator('[name="rupture_promo"]').select_option("oui")
                form.locator('[name="commentaire_promo"]').fill("QA COPIE : rupture constatée le dernier samedi, emplacement îlot.")
                form.locator('[name="bilan_promo"]').fill("Bilan humain vérifié dans la copie isolée uniquement.")
                form.locator('button[type="submit"]').click()
                confirmer()
                page.wait_for_function("!document.querySelector('#refresh').disabled")
                self.assertNotIn("error", page.locator("#notice").get_attribute("class"))
                contexte = page.request.get(url + "/api/contexte").json()["articles"][code]
                self.assertEqual(contexte["precommande_colis"], 12)
                self.assertEqual(contexte["rupture_promo"], "oui")
                page.screenshot(path=str(sortie / "cockpit-promotions.png"), full_page=True)
                page.locator('[data-tab="stock"]').click()
                form = page.locator("#stock-form")
                form.locator('[name="colis"]').fill("2.5")
                form.locator('[name="commentaire"]').fill("QA COPIE : chambre froide comptée, rayon rempli, livraison déjà rangée.")
                form.locator('button[type="submit"]').click()
                confirmer()
                page.wait_for_function("!document.querySelector('#refresh').disabled")
                self.assertNotIn("error", page.locator("#notice").get_attribute("class"))
                faits = [json.loads(l) for l in (ROOT/f"donnees/faits/{date.today().year}.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
                self.assertTrue(any(f.get("article")==code and f.get("colis")==2.5 and "QA COPIE" in f.get("motif","") for f in faits))
                form = page.locator("#pcb-form")
                nouveau = float(form.locator('[name="conditionnement"]').input_value())+1
                form.locator('[name="conditionnement"]').fill(str(nouveau))
                form.locator('[name="motif"]').fill("QA copie isolée : contenu physique du colis vérifié dans le parcours navigateur.")
                form.locator('button[type="submit"]').click()
                confirmer()
                page.wait_for_function("!document.querySelector('#refresh').disabled")
                self.assertNotIn("error", page.locator("#notice").get_attribute("class"))
                proposal = page.request.get(url+"/donnees/proposition.json").json()
                self.assertEqual(next(a for a in proposal["lignes"] if a["itm8"]==code)["conditionnement"], nouveau)
                page.locator('.nav-item[data-view="instructions"]').click()
                self.assertIn("Tête de gondole", page.locator("#instruction-table").inner_text())
                page.screenshot(path=str(sortie / "cockpit-consignes.png"), full_page=True)
                page.locator(f'[data-cancel="{code}"]').click()
                confirmer()
                page.wait_for_function("document.querySelector('#notice').textContent.includes('Consigne annulée')")
                page.wait_for_function("!state.busy && document.querySelector('#loading').hidden")
                page.locator('.nav-item[data-view="products"]').click()
                page.locator('[data-tab="promo"]').click()
                form=page.locator('#promo-form')
                form.locator('[name="commentaire_promo"]').fill('QA COPIE : bilan après annulation ; aucune réactivation autorisée.')
                form.locator('button[type="submit"]').click()
                confirmer()
                page.wait_for_function("!document.querySelector('#refresh').disabled")
                self.assertNotIn('error',page.locator('#notice').get_attribute('class'))
                contexte=page.request.get(url+'/api/contexte').json()['articles'][code]
                self.assertTrue(contexte['annuler'])
                self.assertIn('après annulation',contexte['commentaire_promo'])
                page.locator('.nav-item[data-view="photos"]').click()
                page.wait_for_selector('#photo-file')
                image_path=ROOT/'scratch/photo-cockpit-qa.jpg'
                image_path.parent.mkdir(exist_ok=True)
                image=Image.new('RGB',(640,480),'#dde9c7')
                ImageDraw.Draw(image).text((30,30),'PHOTO DE TEST EN COPIE ISOLEE - aucune photo du magasin',fill='#23422e')
                image.save(image_path)
                page.locator('#photo-file').set_input_files(image_path)
                form=page.locator('#photo-form')
                form.locator('[name="date_photo"]').fill((date.today()-timedelta(days=1)).isoformat()+'T10:30')
                form.locator('[name="zone"]').select_option('tg')
                form.locator('[name="itm8"]').select_option(code)
                form.locator('[name="titre"]').fill('TG test isolé avant changement')
                form.locator('[name="changement"]').fill('QA COPIE : extension de présentation, sans conclusion sur les ventes.')
                page.locator('#photo-copy-auto').click()
                self.assertIn('QA COPIE',form.locator('[name="commentaire"]').input_value())
                with page.expect_response(lambda r:'/api/photos-contexte' in r.url and r.request.method=='POST') as posted:
                    form.locator('button[type="submit"]').click()
                self.assertTrue(posted.value.json()['ok'])
                page.wait_for_function('!state.busy')
                page.wait_for_function("document.querySelector('#photo-gallery img')?.naturalWidth>0")
                page.screenshot(path=str(sortie/'cockpit-journal-photo.png'),full_page=True)
                saved=page.request.get(url+'/api/photos-contexte').json()['photos'][0]
                self.assertEqual(saved['analyse_visuelle'],'non_realisee')
                self.assertEqual(saved['itm8'],code)
                form=page.locator('#photo-form')
                form.locator('[name="commentaire"]').fill('QA COPIE commentaire humain complété après la prise de vue.')
                with page.expect_response(lambda r:'/api/photos-contexte' in r.url and r.request.method=='POST') as edited:
                    form.locator('button[type="submit"]').click()
                self.assertTrue(edited.value.json()['ok'])
                page.wait_for_function('!state.busy')
                after_photo=page.request.get(url+'/api/photos-contexte').json()['photos'][0]
                self.assertEqual(after_photo['revision'],2)
                self.assertEqual(after_photo['sha256'],saved['sha256'])
                page.locator('.photo-image').first.click()
                self.assertTrue(page.locator('#photo-viewer').is_visible())
                page.locator('#photo-close').click()
                page.locator('.nav-item[data-view="dashboard"]').click()
                for width in (1440,1024,390):
                    page.set_viewport_size({"width":width,"height":1000})
                    self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"),width+1)
                    page.screenshot(path=str(sortie / f"cockpit-{width}.png"), full_page=True)
                self.assertEqual(erreurs,[])
                browser.close()
        finally:
            fin=time.monotonic()+90
            while getattr(module,"_recalcul_actif",False) and time.monotonic()<fin:
                time.sleep(.1)
            serveur.shutdown()
            serveur.server_close()


if __name__=="__main__":
    unittest.main()
