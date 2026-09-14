"""Le classeur Pomona doit être accessible sur téléphone sans POST ni SMTP."""
import json
import unittest
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
NOM = "0926 Calcul marge Pomona - livraison 09-09-2026.xlsx"
URL = "/documents-partages/calcul-marge-pomona/0926%20Calcul%20marge%20Pomona%20-%20livraison%2009-09-2026.xlsx"


@unittest.skip("Section Marge Pomona retirée de l'index sur demande explicite du responsable (devenue inutile)")
class MargesMobileTests(unittest.TestCase):
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
        self.context = self.browser.new_context(viewport={"width": 320, "height": 640})
        self.addCleanup(self.context.close)
        self.page = self.context.new_page()
        self.errors = []
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))
        self.posts = []
        self.statut = 200
        self.retour = {"fichiers": [{"nom": NOM, "url": URL, "jours": ["2026-09-07", "2026-09-08", "2026-09-09"]}], "indisponibles": 0}
        self.context.route("**/*", self.route)
        self.context.add_init_script("localStorage.setItem('rayon-fl.comptages-en-attente', JSON.stringify([{itm8:'sentinelle'}]))")

    def route(self, route):
        path = urlsplit(route.request.url).path
        if route.request.method not in ("GET", "HEAD"):
            self.posts.append(path)
            return route.fulfill(status=403)
        if path == "/api/marges-pomona":
            return route.fulfill(status=self.statut, json=self.retour)
        if path.startswith("/app/"):
            cible = ROOT / path.lstrip("/")
            if cible.is_file():
                mime = {".html": "text/html", ".css": "text/css", ".js": "text/javascript"}.get(cible.suffix, "application/octet-stream")
                return route.fulfill(body=cible.read_bytes(), content_type=mime)
        return route.fulfill(status=404, body="fixture absente")

    def ouvrir(self):
        self.page.goto("http://marge.test/app/index.html")
        self.page.wait_for_function("typeof chargerMargesPomona === 'function'")
        self.page.evaluate("chargerMargesPomona()")

    def test_lien_classeur_et_dates_sans_promesse_envoi_sur_mobile(self):
        self.page.goto("http://marge.test/app/index.html")
        self.assertEqual(self.page.locator("#bloc-marge-pomona").count(), 1)
        self.page.evaluate("chargerMargesPomona()")
        bloc = self.page.locator("#bloc-marge-pomona")
        self.assertEqual(bloc.locator("a[download]").get_attribute("href"), URL)
        self.assertIn("09/09/2026", bloc.inner_text())
        self.assertIn("sans attendre le mail", bloc.inner_text())
        self.assertNotIn("envoyé", bloc.inner_text())
        self.assertLessEqual(self.page.evaluate("document.documentElement.scrollWidth"), 320)
        self.assertIn("sentinelle", self.page.evaluate("localStorage.getItem('rayon-fl.comptages-en-attente')"))
        self.assertEqual(self.posts, [])
        self.assertEqual(self.errors, [])

    def test_absence_et_panne_ne_promettent_pas_de_fichier(self):
        self.retour = {"fichiers": [], "indisponibles": 0}
        self.ouvrir()
        self.assertIn("Aucun classeur rempli", self.page.locator("#marges-pomona").inner_text())
        self.statut = 503
        self.page.locator("#actualiser-marges").click()
        self.page.wait_for_function("document.getElementById('marges-pomona').textContent.includes('Impossible')")
        self.assertEqual(self.page.locator("#marges-pomona a").count(), 0)
        self.assertTrue(self.page.locator("#actualiser-marges").is_enabled())
        self.assertEqual(self.posts, [])

    def test_nom_echappe_et_lien_exterieur_refuse(self):
        self.retour["fichiers"][0]["nom"] = "<img src=x onerror=window.injecte=1>.xlsx"
        self.ouvrir()
        self.assertEqual(self.page.locator("#marges-pomona img").count(), 0)
        self.assertIsNone(self.page.evaluate("window.injecte"))
        self.retour["fichiers"][0]["url"] = "https://etranger.test/fichier.xlsx"
        self.page.evaluate("chargerMargesPomona()")
        self.assertEqual(self.page.locator("#marges-pomona a").count(), 0)
        self.assertIn("Impossible", self.page.locator("#marges-pomona").inner_text())


if __name__ == "__main__":
    unittest.main()
