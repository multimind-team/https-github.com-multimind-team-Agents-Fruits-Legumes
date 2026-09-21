"""Photos synthétiques et serveur éphémère ; aucun fichier métier de production."""
import base64
from datetime import datetime, timedelta
from io import BytesIO
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
import photos_contexte as photos
import test_serveur_securite as serveur_fixture

CODE = serveur_fixture.CODE


def image_test(format_image="PNG", exif=None, taille=(60, 40)):
    flux = BytesIO()
    image = Image.new("RGB", taille, (60, 150, 100))
    image.save(flux, format=format_image, **({"exif": exif} if exif else {}))
    return flux.getvalue()


def charge(contenu=None, **kw):
    return {"requete_id": "photo-requete-test-001", "image_base64": base64.b64encode(contenu or image_test()).decode("ascii"),
            "nom_fichier": "rayon.png", "date_photo": datetime.now().strftime("%Y-%m-%dT%H:%M"),
            "zone": "tg", "itm8": CODE, "titre": "Nouvelle présentation", "changement": "Table avancée",
            "commentaire": "Rayon rempli avant ouverture", **kw}


class PhotosTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.racine = Path(self.temp.name)
        self.articles = {CODE: "ARTICLE TEST"}

    def ecrire(self, requete=None):
        return photos.enregistrer(self.racine, requete or charge(), self.articles)

    def test_upload_prive_derives_valides_et_aucun_fait_stock(self):
        original = image_test(taille=(2400, 1200))
        resultat = self.ecrire(charge(original, nom_fichier="nom-trompeur.exe"))
        photo = resultat["photo"]
        self.assertEqual(photo["format"], "PNG")
        self.assertEqual(photo["mime_original"], "image/png")
        self.assertEqual(photo["analyse_visuelle"], "non_realisee")
        self.assertIn("Changement déclaré", photo["commentaire_auto"])
        self.assertIn("Aucune analyse visuelle", photo["commentaire_auto"])
        self.assertEqual((self.racine / "documents-partages/contexte-visuel/originaux" / (photo["sha256"] + ".png")).read_bytes(), original)
        for cle, taille in (("image_url", (1600, 800)), ("thumbnail_url", (320, 160))):
            with Image.open(self.racine / photo[cle].lstrip("/")) as derive:
                self.assertEqual(derive.format, "JPEG")
                self.assertEqual(derive.size, taille)
                self.assertEqual(dict(derive.getexif()), {})
        self.assertFalse((self.racine / "donnees/faits").exists())
        self.assertFalse((self.racine / "donnees/decisions.jsonl").exists())
        self.assertFalse((self.racine / "donnees/proposition.json").exists())

    def test_orientation_et_exif_prive_uniquement(self):
        exif = Image.Exif()
        exif[274] = 6
        exif[306] = "2026:09:01 08:15:00"
        exif[34853] = {1: "N", 2: (44.0, 0.0, 0.0), 3: "E", 4: (2.0, 0.0, 0.0)}
        image = image_test("JPEG", exif=exif)
        photo = self.ecrire(charge(image))["photo"]
        self.assertEqual((photo["largeur"], photo["hauteur"]), (40, 60))
        self.assertEqual(photo["date_exif"], "2026:09:01 08:15:00")
        self.assertNotEqual(photo["date_photo"], "2026-09-01T08:15")
        with Image.open(self.racine / photo["image_url"].lstrip("/")) as derive:
            self.assertEqual(dict(derive.getexif()), {})
            self.assertNotIn("exif", derive.info)
        with Image.open(self.racine / "documents-partages/contexte-visuel/originaux" / (photo["sha256"] + ".jpg")) as source:
            self.assertIn(34853, source.getexif())

    def test_formats_autorises_sans_extension_fiable(self):
        for format_image in ("JPEG", "PNG", "WEBP"):
            with self.subTest(format_image=format_image):
                photo = self.ecrire(charge(image_test(format_image), requete_id="photo-format-" + format_image))["photo"]
                self.assertEqual(photo["format"], format_image)
        for contenu in (image_test("GIF"), b"<svg><script>alert(1)</script></svg>", b"MZ-executable", image_test()[:30]):
            with self.subTest(contenu=contenu[:10]), self.assertRaises(ValueError):
                self.ecrire(charge(contenu, requete_id="photo-format-refuse"))

    def test_validation_date_zone_article_metadata_et_base64(self):
        invalides = [{"date_photo": ""}, {"date_photo": "2026-02-30T08:00"},
                    {"date_photo": (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")},
                    {"zone": "inconnue"}, {"zone": "produit", "itm8": None}, {"itm8": "inconnu"},
                    {"titre": "x"*161}, {"commentaire": "x"*6001}, {"changement": "x"*2001},
                    {"nom_fichier": "../photo.png"}, {"nom_fichier": "C:\\photo.jpg"},
                    {"image_base64": "data:image/png;base64,AAAA"}, {"image_base64": "??"},
                    {"promo_debut": "2026-09-01"}, {"revision": 0}, {"auteur": "agent-donnees"}]
        for invalid in invalides:
            with self.subTest(invalid=repr(invalid)), self.assertRaises(ValueError):
                self.ecrire(charge(**invalid))
        self.assertFalse((self.racine / "donnees/photos-contexte.jsonl").exists())
        self.assertFalse((self.racine / "documents-partages").exists())

    def test_limites_octets_pixels_et_animation(self):
        with patch.object(photos, "MAX_OCTETS", 30), self.assertRaises(ValueError):
            self.ecrire()
        with patch.object(photos, "MAX_PIXELS", 100), self.assertRaises(ValueError):
            self.ecrire()
        flux = BytesIO()
        frames = [Image.new("RGB", (10, 10), color) for color in ("red", "blue")]
        frames[0].save(flux, format="PNG", save_all=True, append_images=frames[1:], duration=100, loop=0)
        with self.assertRaises(ValueError):
            self.ecrire(charge(flux.getvalue()))

    def test_idempotence_hash_et_edition_append_only(self):
        premiere = self.ecrire()["photo"]
        journal = self.racine / "donnees/photos-contexte.jsonl"
        original = journal.read_bytes()
        self.assertTrue(self.ecrire()["deja_enregistre"])
        self.assertTrue(self.ecrire(charge(requete_id="photo-doublon-001"))["deja_enregistre"])
        self.assertEqual(journal.read_bytes(), original)
        with self.assertRaises(photos.ConflitPhoto):
            self.ecrire(charge(commentaire="Autre requête sous même identifiant"))
        edit = {"id": premiere["id"], "revision": 1, "requete_id": "photo-edition-001", "commentaire": "Ma correction humaine"}
        nouvelle = self.ecrire(edit)["photo"]
        self.assertEqual(nouvelle["revision"], 2)
        self.assertEqual(nouvelle["date_photo"], premiere["date_photo"])
        self.assertEqual(nouvelle["image_url"], premiere["image_url"])
        self.assertEqual(nouvelle["commentaire"], "Ma correction humaine")
        self.assertTrue(journal.read_bytes().startswith(original))
        self.assertTrue(self.ecrire(edit)["deja_enregistre"])
        doublon_apres_annotation = self.ecrire(charge(requete_id="photo-doublon-apres-001"))
        self.assertTrue(doublon_apres_annotation["deja_enregistre"])
        self.assertEqual(doublon_apres_annotation["photo"]["revision"], 2)
        self.assertEqual(doublon_apres_annotation["photo"]["commentaire"], "Ma correction humaine")
        with self.assertRaises(photos.ConflitPhoto):
            self.ecrire({**edit, "requete_id": "photo-stale-001"})
        with self.assertRaises(ValueError):
            self.ecrire({**edit, "revision": 2, "requete_id": "photo-image-edit-001", "image_base64": charge()["image_base64"]})

    def test_lecture_pure_et_filtre_article(self):
        self.assertEqual(photos.charger(self.racine)["photos"], [])
        self.assertEqual(list(self.racine.iterdir()), [])
        self.ecrire()
        self.ecrire(charge(requete_id="photo-rayon-001", zone="rayon", itm8=None))
        self.assertEqual(len(photos.charger(self.racine)["photos"]), 2)
        self.assertEqual(len(photos.charger(self.racine, article=CODE)["photos"]), 1)

    def test_carnet_tronque_et_original_different_ne_sont_pas_ecrases(self):
        self.ecrire()
        journal = self.racine / "donnees/photos-contexte.jsonl"
        initial = journal.read_bytes()
        journal.write_bytes(initial.rstrip(b"\n"))
        with self.assertRaises(ValueError):
            self.ecrire(charge(requete_id="photo-tronque-001"))
        self.assertEqual(journal.read_bytes(), initial.rstrip(b"\n"))
        cible = self.racine / "immuable.jpg"
        cible.write_bytes(b"existant")
        with self.assertRaises(ValueError):
            photos._ajouter_fichier(cible, b"different")
        self.assertEqual(cible.read_bytes(), b"existant")


class PhotosHTTPTests(unittest.TestCase):
    setUp = serveur_fixture.ServeurIsoleTests.setUp
    fermer = serveur_fixture.ServeurIsoleTests.fermer
    ecrire = serveur_fixture.ServeurIsoleTests.ecrire
    requete = serveur_fixture.ServeurIsoleTests.requete

    def test_http_original_prive_apercus_publics_origine_et_absence_recalcul(self):
        statut, corps, _ = self.requete("POST", "/api/photos-contexte", charge())
        self.assertEqual(statut, 200, corps)
        photo = json.loads(corps)["photo"]
        self.assertEqual(self.requete("GET", photo["image_url"])[0], 200)
        self.assertEqual(self.requete("GET", photo["thumbnail_url"])[0], 200)
        prive = "/documents-partages/contexte-visuel/originaux/" + photo["sha256"] + ".png"
        self.assertEqual(self.requete("GET", prive)[0], 404)
        self.assertEqual(self.requete("GET", "/donnees/photos-contexte.jsonl")[0], 404)
        self.assertEqual(self.requete("GET", photo["image_url"].replace("-1600", "-400"))[0], 404)
        self.assertEqual(self.requete("HEAD", "/api/photos-contexte")[1], b"")
        self.assertEqual(len(json.loads(self.requete("GET", "/api/photos-contexte?article=" + CODE)[1])["photos"]), 1)
        self.assertEqual(self.requete("POST", "/api/photos-contexte", charge(), headers={"Origin": "https://evil.test"})[0], 403)
        self.recalc_mock.assert_not_called()

    def test_limite_http_photo_distincte_des_anciennes_routes(self):
        flux = BytesIO()
        Image.frombytes("RGB", (700, 700), os.urandom(700 * 700 * 3)).save(flux, format="PNG")
        requete = charge(flux.getvalue())
        self.assertGreater(len(json.dumps(requete)), self.module.MAX_CORPS_JSON)
        statut, corps, _ = self.requete("POST", "/api/photos-contexte", requete)
        self.assertEqual(statut, 200, corps[:200])
        self.assertEqual(self.requete("POST", "/api/messages", requete)[0], 413)
        self.assertEqual(self.requete("POST", "/api/photos-contexte", {}, headers={"Content-Length": str(self.module.MAX_CORPS_PHOTO+1)})[0], 413)


if __name__ == "__main__":
    unittest.main()
