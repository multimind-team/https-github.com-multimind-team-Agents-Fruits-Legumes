"""Mobile photo regression with a REAL warm HTTP cache, never production writes.
Run: py -3.14 -m unittest discover -s tests -p test_cache_photos_mobile.py -v
No Playwright routes: routing disables the HTTP cache and hides this regression.
"""
import json
import re
import tempfile
import threading
import unittest
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright
from test_interface_mobile import ROOT, CODE, ARTICLE, LINE, PROPOSAL, PENDING


class CachePhotosMobileTests(unittest.TestCase):
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
        self.requests = Counter()
        self.posts = []
        self.force_stale_css = True
        self.warm_legacy_js = False
        # Model the deployed charte before the photo rules existed. The browser
        # must reuse these exact bytes from its cache after the warm-up visit.
        self.old_css = (ROOT / "app/css/charte.css").read_text(encoding="utf-8").split(
            "/* Repères photo uniquement")[0] + '\n:root { --cache-photo-fixture: ancien; }\n'
        src = next((ROOT / "app/img/produits").glob("*-240.webp"))
        photo = dict(src=src.relative_to(ROOT).as_posix(),
                     miniature=src.relative_to(ROOT).as_posix().replace("-240.webp", "-96.webp"),
                     largeur=240, hauteur=240, libelle='PHOTO TEST <svg onload="window.__xss=1">')
        self.fixtures = {
            "/donnees/proposition.json": PROPOSAL,
            "/donnees/articles.json": {"articles": [ARTICLE]},
            "/donnees/photos.json": {"version": 1, "articles": {CODE: photo}},
            "/donnees/promotions.json": {"offres": []},
            "/donnees/etat.json": {"articles": {}},
            "/donnees/note-du-matin.json": {"entrees": []},
        }
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                owner.posts.append(self.path)
                self.send_error(405, "No business writes in this fixture")

            def do_GET(self):
                owner.requests[self.path] += 1
                parsed = urlsplit(self.path)
                path = parsed.path
                cache = False
                mime = "text/html; charset=utf-8"
                status = 200
                if path == "/warm.html":
                    script = '<script src="/app/js/photos-produits.js"></script>' if owner.warm_legacy_js else ''
                    body = '<!doctype html><link rel="stylesheet" href="/app/css/charte.css">' + script
                elif path == "/app/css/charte.css" and not parsed.query:
                    body, mime, cache = owner.old_css, "text/css", True
                elif path == "/app/js/photos-produits.js" and not parsed.query and owner.warm_legacy_js:
                    body, mime, cache = "window.__legacyPhotoAsset = true;", "application/javascript", True
                elif path in owner.fixtures:
                    body, mime = json.dumps(owner.fixtures[path]), "application/json"
                elif path.endswith(".jsonl"):
                    body, mime = "", "text/plain"
                elif path.startswith("/app/"):
                    file = (ROOT / path.lstrip("/")).resolve()
                    if file.is_relative_to(ROOT / "app") and file.is_file():
                        body = file.read_bytes()
                        mime = {".css": "text/css", ".js": "application/javascript", ".html": "text/html; charset=utf-8", ".webp": "image/webp"}.get(file.suffix, "application/octet-stream")
                        if file.suffix == ".html" and owner.force_stale_css:
                            body = re.sub(rb'css/charte\.css(?:\?[^\"]*)?', b'css/charte.css', body)
                    else:
                        status, body = 404, "fixture absent"
                else:
                    status, body = 404, "fixture absent"
                if isinstance(body, str):
                    body = body.encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(body)))
                if cache:
                    # No Cache-Control, like the affected production server:
                    # old Last-Modified grants heuristic freshness in Chromium.
                    self.send_header("Last-Modified", "Wed, 01 Jan 2020 00:00:00 GMT")
                else:
                    self.send_header("Cache-Control", "no-store")
                self.end_headers()
                try:
                    self.wfile.write(body)
                except ConnectionError:
                    pass  # Navigation/closing the fixture cancels optional fetches.

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.origin = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.assertEqual(self.posts, [], "No POST, even on isolated fixtures")

    def test_versioned_assets_refresh_after_warm_cache_without_losing_counts(self):
        self.force_stale_css = False
        self.warm_legacy_js = True
        context = self.browser.new_context(viewport={"width": 360, "height": 800},
                                           is_mobile=True, device_scale_factor=3, has_touch=True)
        try:
            page = context.new_page()
            page.goto(self.origin + "/warm.html")
            self.assertTrue(page.evaluate("window.__legacyPhotoAsset"))
            pending = '[{"id":"preserve-across-deployment","colis":7}]'
            page.evaluate("([key,value]) => localStorage.setItem(key,value)", [PENDING, pending])
            for name in ("commander", "compter", "index", "promo", "maintenance"):
                with self.subTest(page=name):
                    page.goto(self.origin + f"/app/{name}.html")
                    stylesheet = page.locator('link[rel="stylesheet"]').get_attribute("href")
                    self.assertTrue(urlsplit(stylesheet).query, f"{name}: CSS still unversioned")
                    self.assertEqual(page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--cache-photo-fixture').trim()"), "")
                    self.assertEqual(page.evaluate("window.__legacyPhotoAsset"), None)
                    if name in ("commander", "compter"):
                        self.assertTrue(urlsplit(page.locator('script[src]').get_attribute("src")).query)
                        image = page.locator('.photo-produit').first
                        image.wait_for()
                        self.assertEqual(image.bounding_box()['width'], 48 if name == "commander" else 64)
                    self.assertEqual(page.evaluate('(key) => localStorage.getItem(key)', PENDING), pending)
            self.assertEqual(self.requests["/app/css/charte.css"], 1)
            self.assertEqual(self.requests["/app/js/photos-produits.js"], 1)
        finally:
            context.close()

    def test_cached_pre_photo_css_never_covers_quantity_buttons(self):
        for width in (320, 360, 390):
            with self.subTest(width=width):
                before = self.requests["/app/css/charte.css"]
                context = self.browser.new_context(viewport={"width": width, "height": 800},
                                                   is_mobile=True, device_scale_factor=3, has_touch=True)
                try:
                    page = context.new_page()
                    errors = []
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.goto(self.origin + "/warm.html")
                    pending = '[{"id":"unsent-fixture","colis":7}]'
                    page.evaluate("([key,value]) => localStorage.setItem(key,value)", [PENDING, pending])
                    page.goto(self.origin + "/app/commander.html")
                    page.wait_for_function("document.getElementById('dates').textContent.includes('Commande du')", timeout=10000)
                    image = page.locator("#liste .photo-produit-liste")
                    image.wait_for()
                    page.wait_for_function("document.querySelector('#liste img').naturalWidth > 0")
                    image.scroll_into_view_if_needed()
                    # Both the CSS marker and request count prove actual reuse,
                    # not simply a fresh context fulfilled with stale CSS bytes.
                    self.assertEqual(page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--cache-photo-fixture').trim()"), "ancien")
                    self.assertEqual(self.requests["/app/css/charte.css"] - before, 1)
                    photo = image.bounding_box()
                    buttons = {}
                    for role in ("moins", "plus", "masquer"):
                        button = page.locator(f'#liste [data-role="{role}"]')
                        box = button.bounding_box()
                        buttons[role] = box
                        self.assertGreaterEqual(box["x"], 0)
                        self.assertLessEqual(box["x"] + box["width"], width)
                        self.assertTrue(button.evaluate("e => { const r=e.getBoundingClientRect(); return [0.2,0.5,0.8].every(x => [0.2,0.5,0.8].every(y => e.contains(document.elementFromPoint(r.x+r.width*x,r.y+r.height*y)))); }"), role)
                        # Trial click exercises Playwright's actual actionability
                        # without sending a mask/stock API request.
                        button.click(trial=True, timeout=2000)
                    evidence = Path(tempfile.gettempdir()) / "photos-mobile-regression"
                    evidence.mkdir(exist_ok=True)
                    page.screenshot(path=str(evidence / f"cache-{width}-{round(photo['width'])}px.png"), full_page=True)
                    print(json.dumps({"viewport": width, "photo": photo, "buttons": buttons, "css_requests": self.requests["/app/css/charte.css"] - before}))
                    for role, box in buttons.items():
                        overlap = (min(photo["x"] + photo["width"], box["x"] + box["width"]) > max(photo["x"], box["x"]) and min(photo["y"] + photo["height"], box["y"] + box["height"]) > max(photo["y"], box["y"]))
                        self.assertFalse(overlap, f"Photo covers {role}: photo={photo}, button={box}")
                    self.assertEqual(photo["width"], 48)
                    self.assertEqual(photo["height"], 48)
                    self.assertEqual(page.locator('.qte .val').inner_text().splitlines()[0], '3')
                    page.locator('[data-role="moins"]').tap()
                    self.assertEqual(page.locator('.qte .val').inner_text().splitlines()[0], '2')
                    page.locator('[data-role="plus"]').tap()
                    self.assertEqual(page.locator('.qte .val').inner_text().splitlines()[0], '3')
                    self.assertEqual(page.evaluate('(key) => localStorage.getItem(key)', PENDING), pending)
                    self.assertEqual(page.locator('#liste svg').count(), 0)
                    self.assertEqual(page.evaluate('window.__xss'), None)
                    self.assertEqual(errors, [])
                finally:
                    context.close()


if __name__ == "__main__":
    unittest.main()
