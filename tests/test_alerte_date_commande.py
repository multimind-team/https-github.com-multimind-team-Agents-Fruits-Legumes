"""Dates de commande : navigateur isolé, horloge Paris, aucun envoi réel.

Run: py -3.14 -m unittest discover -s tests -p 'test_alerte_date_commande.py' -v
"""
import unittest

import test_interface_mobile as ui


GENERATION = "2026-09-10T09:29:22"
MOUVEMENTS = (
    "Les ventes du 09/09 manquent à la couverture des sorties. "
    "Vérifie les mouvements après comptage ; les statistiques restent au 08/09."
)


class AlerteDateCommandeTests(unittest.TestCase):
    setUpClass = classmethod(ui.InterfaceMobileTests.setUpClass.__func__)
    tearDownClass = classmethod(ui.InterfaceMobileTests.tearDownClass.__func__)
    route = ui.InterfaceMobileTests.route

    def setUp(self):
        self.context = self.browser.new_context(
            viewport={"width": 360, "height": 800}, timezone_id="Europe/Paris"
        )
        self.page = self.context.new_page()
        self.errors = []
        self.posts = []
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))
        self.fixtures = {
            "/donnees/proposition.json": dict(ui.PROPOSAL, genere_le=GENERATION),
            "/donnees/promotions.json": {"offres": []},
            "/donnees/photos.json": {"version": 1, "articles": {}},
        }
        # Toute tentative d'API est refusée, même sur l'origine fictive.
        self.api = lambda route: route.fulfill(status=405, json={"ok": False})
        self.context.route("**/*", self.route)

    def tearDown(self):
        try:
            self.assertEqual(self.errors, [])
            self.assertEqual(self.posts, [], "L'alerte ne doit appeler aucune API")
        finally:
            self.context.close()

    def ouvrir(self, maintenant, *, jour="2026-09-10", rapport=None):
        self.fixtures["/donnees/proposition.json"] = dict(
            ui.PROPOSAL, date_commande=jour, genere_le=GENERATION
        )
        if rapport is None:
            self.fixtures.pop("/donnees/fraicheur.json", None)
        else:
            self.fixtures["/donnees/fraicheur.json"] = rapport
        self.page.clock.set_fixed_time(maintenant)
        self.page.goto("http://ui.test/app/commander.html")
        # L'en-tête est écrit après toutes les lectures asynchrones de démarrage.
        self.page.wait_for_function(
            "document.getElementById('dates').textContent.startsWith('Commande du')"
        )
        self.page.locator("#liste .article").first.wait_for()
        return self.page.locator("#alerte")

    def rapport(self, *, jour="2026-09-10", etat="donnees-en-retard", **autres):
        return dict(
            etat=etat, message=MOUVEMENTS,
            jour_de_commande_attendu=jour,
            proposition_generee_le=GENERATION, **autres
        )

    def test_apres_9h30_ancien_rapport_distingue_proposition_et_prochaine_commande(self):
        alerte = self.ouvrir("2026-09-10T13:46:00+02:00", rapport=self.rapport())
        self.assertTrue(alerte.is_visible())
        texte = alerte.inner_text()
        self.assertEqual(self.page.evaluate("jourAttenduActuel()"), "2026-09-11")
        self.assertIn("commande du 10/09", texte)
        self.assertIn("Prochaine commande attendue : 11/09", texte)
        self.assertIn("Proposition pour une autre date", texte)
        self.assertIn("Après 9h30", texte)
        self.assertNotIn("on commande aujourd'hui", texte)
        self.assertNotIn("Tu peux commander quand même", texte)
        self.assertIn("verifier-avant-commande.bat sur le PC", texte)
        self.assertIn("recharge", texte)
        self.assertIn("Commande du 10/09", self.page.locator("#dates").inner_text())
        self.assertEqual(self.page.evaluate("proposition.genere_le"), GENERATION)
        self.assertEqual(self.page.locator("#alerte button").count(), 0)

    def test_avant_la_coupure_date_conforme_sans_pretendre_verifier_les_donnees(self):
        for rapport in (None, self.rapport(etat="a-jour")):
            with self.subTest(rapport=rapport):
                alerte = self.ouvrir("2026-09-10T09:29:59+02:00", rapport=rapport)
                self.assertEqual(self.page.evaluate("jourAttenduActuel()"), "2026-09-10")
                self.assertFalse(alerte.is_visible())
                self.assertNotIn("données à jour", self.page.locator("body").inner_text().lower())
                self.assertEqual(self.page.evaluate("proposition.date_commande"), "2026-09-10")

    def test_9h30_exactement_rapport_absent_alerte_sans_faux_succes(self):
        alerte = self.ouvrir("2026-09-10T09:30:00+02:00")
        self.assertTrue(alerte.is_visible())
        texte = alerte.inner_text()
        self.assertIn("commande du 10/09", texte)
        self.assertIn("Prochaine commande attendue : 11/09", texte)
        self.assertIn("avant 9h30", texte)
        self.assertNotIn("recalculée", texte)
        self.assertNotIn("à jour", texte)
        self.assertEqual(self.page.evaluate("fraicheur"), None)

    def test_jour_suivant_ne_confond_pas_generation_et_date_de_commande(self):
        alerte = self.ouvrir("2026-09-11T08:00:00+02:00")
        self.assertTrue(alerte.is_visible())
        self.assertIn("commande du 10/09", alerte.inner_text())
        self.assertIn("Prochaine commande attendue : 11/09", alerte.inner_text())
        self.assertNotIn("on commande aujourd'hui", alerte.inner_text())
        self.assertEqual(self.page.evaluate("proposition.genere_le"), GENERATION)

    def test_dimanche_et_fermetures_gardent_le_prochain_jour_ouvrable(self):
        cas = (
            ("2026-09-12T09:30:00+02:00", "2026-09-12", "2026-09-14", "14/09"),
            ("2026-09-13T08:00:00+02:00", "2026-09-12", "2026-09-14", "14/09"),
            ("2026-05-01T08:00:00+02:00", "2026-04-30", "2026-05-02", "02/05"),
            ("2026-12-24T09:30:00+01:00", "2026-12-24", "2026-12-26", "26/12"),
            ("2027-01-01T08:00:00+01:00", "2026-12-31", "2027-01-02", "02/01"),
        )
        for maintenant, jour, attendu, date_fr in cas:
            with self.subTest(maintenant=maintenant):
                alerte = self.ouvrir(maintenant, jour=jour)
                self.assertTrue(alerte.is_visible())
                self.assertEqual(self.page.evaluate("jourAttenduActuel()"), attendu)
                self.assertIn("Prochaine commande attendue : " + date_fr, alerte.inner_text())
                self.assertIn("hors dimanche et jours de fermeture", alerte.inner_text())
                self.assertNotIn("on commande aujourd'hui", alerte.inner_text())
                self.assertEqual(self.page.evaluate("proposition.date_commande"), jour)

    def test_fermeture_exceptionnelle_fournie_par_le_filet_reste_prioritaire(self):
        alerte = self.ouvrir(
            "2026-09-10T13:46:00+02:00",
            rapport=self.rapport(jour="2026-09-12", etat="a-jour"),
        )
        self.assertEqual(self.page.evaluate("jourAttenduActuel()"), "2026-09-12")
        self.assertTrue(alerte.is_visible())
        self.assertIn("Prochaine commande attendue : 12/09", alerte.inner_text())

    def test_proposition_de_la_prochaine_commande_ne_devient_pas_celle_du_jour(self):
        alerte = self.ouvrir("2026-09-10T13:46:00+02:00", jour="2026-09-11")
        self.assertFalse(alerte.is_visible())
        self.assertEqual(self.page.evaluate("proposition.date_commande"), "2026-09-11")
        self.assertIn("Commande du 11/09", self.page.locator("#dates").inner_text())

    def test_vraies_ventes_manquantes_gardent_leur_alerte_avant_et_apres_9h30(self):
        for maintenant, attendu in (
            ("2026-09-10T09:29:59+02:00", "2026-09-10"),
            ("2026-09-10T09:30:00+02:00", "2026-09-11"),
        ):
            with self.subTest(maintenant=maintenant):
                alerte = self.ouvrir(maintenant, rapport=self.rapport(jour=attendu))
                self.assertTrue(alerte.is_visible())
                texte = alerte.inner_text()
                self.assertIn("Fichier des ventes à vérifier", texte)
                self.assertIn("Vérifie les dates du fichier des ventes et son intégration.", texte)
                self.assertNotIn("Proposition pour une autre date", texte)
                self.assertNotIn("données à jour", texte.lower())

    def test_rapport_dune_autre_generation_ne_se_fait_pas_passer_pour_actuel(self):
        rapport = self.rapport(jour="2026-09-11")
        rapport["proposition_generee_le"] = "2026-09-10T08:00:00"
        alerte = self.ouvrir("2026-09-10T13:46:00+02:00", rapport=rapport)
        self.assertIn("Prochaine commande attendue : 11/09", alerte.inner_text())
        self.assertNotIn(MOUVEMENTS, alerte.inner_text())

    def test_message_de_fraicheur_reste_echappe(self):
        rapport = self.rapport(etat="calcul-incomplet")
        rapport["message"] += ' <img src=x onerror="window.__xss=1">'
        alerte = self.ouvrir("2026-09-10T09:29:59+02:00", rapport=rapport)
        self.assertIn(rapport["message"], alerte.inner_text())
        self.assertEqual(alerte.locator("img").count(), 0)
        self.assertIsNone(self.page.evaluate("window.__xss"))

    def test_bascule_preserve_ajustements_comptages_et_saisies_de_la_fiche(self):
        alerte = self.ouvrir("2026-09-10T09:29:59+02:00", rapport=self.rapport())
        self.page.locator('[data-role="plus"]').first.click()
        self.page.evaluate("""() => {
            localStorage.setItem(CLE_COMPTAGES, JSON.stringify([
                {id: 'test-en-attente', itm8: '0000000000001', colis: 2, conditionnement: 6}
            ]));
            localStorage.setItem('saisie-test', 'à conserver');
            majAlerte();
        }""")
        self.page.locator("#recherche").fill("POMME")
        self.page.locator('[data-role="detail"]').first.click()
        self.page.locator("#detail-conditionnement-valeur").fill("8,5")
        self.page.locator("#detail-stock-modifier").click()
        self.page.locator("#detail-stock-valeur").fill("7")
        memoire = self.page.evaluate("JSON.stringify({...localStorage})")
        proposition_avant = self.page.evaluate("JSON.stringify(proposition)")
        self.assertIn("Fichier des ventes à vérifier", alerte.inner_text())
        self.assertIn("1 comptage pas encore envoyé", alerte.inner_text())
        self.page.clock.set_fixed_time("2026-09-10T09:30:00+02:00")
        self.page.evaluate("majAlerte()")
        self.assertIn("Prochaine commande attendue : 11/09", alerte.inner_text())
        self.assertIn("1 comptage pas encore envoyé", alerte.inner_text())
        self.assertEqual(self.page.evaluate("JSON.stringify({...localStorage})"), memoire)
        self.assertEqual(self.page.evaluate("JSON.stringify(proposition)"), proposition_avant)
        self.assertEqual(self.page.evaluate("quantite(proposition.lignes[0])"), 4)
        self.assertEqual(self.page.locator("#recherche").input_value(), "POMME")
        self.assertEqual(self.page.locator("#detail-conditionnement-valeur").input_value(), "8,5")
        self.assertEqual(self.page.locator("#detail-stock-valeur").input_value(), "7")
        self.assertTrue(self.page.locator("#detail").is_visible())

    def test_alerte_et_articles_restent_lisibles_sur_mobile(self):
        for largeur in (320, 360, 768):
            with self.subTest(largeur=largeur):
                self.page.set_viewport_size({"width": largeur, "height": 800})
                alerte = self.ouvrir("2026-09-10T13:46:00+02:00")
                self.assertTrue(alerte.is_visible())
                self.assertLessEqual(self.page.evaluate("document.documentElement.scrollWidth"), largeur)
                bouton = self.page.locator('[data-role="plus"]').first
                bouton.click()
                self.assertEqual(self.page.evaluate("quantite(proposition.lignes[0])"), 4)
                # On remet seulement la fixture locale pour l'itération suivante.
                self.page.locator('[data-role="moins"]').first.click()


if __name__ == "__main__":
    unittest.main()
