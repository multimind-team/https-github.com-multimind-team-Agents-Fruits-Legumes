"""Colisage dans la fiche : vrai navigateur, réseau entièrement simulé."""
import json
import unittest

import test_interface_mobile as ui


class ColisageMobileTests(unittest.TestCase):
    # Réutilise seulement le harnais isolé, pas les autres tests de l'interface.
    setUpClass = classmethod(ui.InterfaceMobileTests.setUpClass.__func__)
    tearDownClass = classmethod(ui.InterfaceMobileTests.tearDownClass.__func__)
    setUp = ui.InterfaceMobileTests.setUp
    tearDown = ui.InterfaceMobileTests.tearDown
    route = ui.InterfaceMobileTests.route
    open = ui.InterfaceMobileTests.open
    install_photo_fixture = ui.InterfaceMobileTests.install_photo_fixture

    def ouvrir_fiche(self):
        self.open('commander')
        self.page.locator('[data-role="detail"]').first.click()
        self.page.locator('#detail-conditionnement-valeur').wait_for(timeout=2000)

    def test_reponse_retardee_ne_retire_pas_le_colisage_recalcule_dun_autre_article(self):
        autre = '0000000000002'
        seconde = dict(ui.LINE, itm8=autre, libelle='AUTRE ARTICLE TEST')
        self.fixtures['/donnees/proposition.json'] = dict(ui.PROPOSAL, lignes=[ui.LINE, seconde])
        self.ouvrir_fiche()
        ancienne = dict(ui.PROPOSAL, lignes=[dict(ui.LINE, conditionnement=8), seconde])
        recente = dict(ui.PROPOSAL, lignes=[dict(ui.LINE, conditionnement=8), dict(seconde, conditionnement=9)])
        lectures = []
        def relire(route):
            lectures.append(route)
            if len(lectures) > 1:
                route.fulfill(json=recente)
        self.context.route('**/donnees/proposition.json?*', relire)
        self.page.locator('#detail-conditionnement-valeur').fill('8')
        self.page.locator('#detail-conditionnement-valider').click()
        self.page.wait_for_timeout(700)
        self.assertEqual(len(lectures), 1)
        self.page.locator('#fermer-detail').click()
        self.page.locator('[data-itm8="' + autre + '"] [data-role="detail"]').click()
        self.page.locator('#detail-conditionnement-valeur').fill('9')
        self.page.locator('#detail-conditionnement-valider').click()
        self.page.wait_for_function("proposition.lignes[1].conditionnement === 9")
        lectures[0].fulfill(json=ancienne)
        self.page.wait_for_function("suivisColisage.get('0000000000001')?.actif === false")
        self.assertEqual(self.page.evaluate('proposition.lignes[1].conditionnement'), 9)
        self.assertIn('colis de 9 kg', self.page.locator('#detail-sous').inner_text())
        self.assertEqual(self.errors, [])

    def test_erreur_http_ou_reseau_ne_confirme_pas_le_colisage(self):
        for genre in ('refus', 'http', 'reseau', 'enregistre_sans_recalcul'):
            with self.subTest(genre=genre):
                if genre == 'reseau':
                    self.api = lambda route: route.abort('connectionreset')
                else:
                    self.api = lambda route: route.fulfill(status=500, json={
                        'ok': genre == 'http', 'enregistre': genre == 'enregistre_sans_recalcul',
                        'erreur': 'Erreur de test'})
                self.ouvrir_fiche()
                self.page.locator('#detail-conditionnement-valeur').fill('8')
                self.page.locator('#detail-conditionnement-valider').click()
                self.page.wait_for_function("suivisColisage.get('0000000000001')?.actif === false")
                self.assertEqual(self.page.evaluate('proposition.lignes[0].conditionnement'), 6)
                texte = self.page.locator('#detail-conditionnement-etat').inner_text()
                self.assertNotIn('recalculée', texte)
                self.assertIn('Colisage enregistré' if genre == 'enregistre_sans_recalcul' else 'non confirmé', texte)
                self.assertEqual(self.page.locator('#detail-conditionnement-valeur').input_value(), '8')
                self.assertFalse(self.page.locator('#detail-conditionnement-valider').is_disabled())
        self.assertEqual(self.errors, [])

    def test_accuse_sans_recalcul_correspondant_garde_la_proposition_precedente(self):
        self.ouvrir_fiche()
        self.fixtures['/donnees/proposition.json'] = dict(ui.PROPOSAL, genere_le='plus-recent-mais-autre-colisage',
                                                       lignes=[dict(ui.LINE, conditionnement=5)])
        self.page.locator('#detail-conditionnement-valeur').fill('8')
        self.page.locator('#detail-conditionnement-valider').click()
        self.page.wait_for_function("suivisColisage.get('0000000000001')?.actif === false", timeout=17000)
        texte = self.page.locator('#detail-conditionnement-etat').inner_text()
        self.assertIn('Colisage enregistré', texte)
        self.assertIn('pas encore actualisée', texte)
        self.assertEqual(self.page.evaluate('proposition.lignes[0].conditionnement'), 6)
        self.assertEqual(len(self.posts), 1)

    def test_champ_et_bouton_accessibles_avec_photo_sur_telephone_et_tablette(self):
        self.install_photo_fixture()
        for largeur in (320, 360, 768):
            with self.subTest(largeur=largeur):
                self.page.set_viewport_size({'width': largeur, 'height': 800})
                self.ouvrir_fiche()
                champ = self.page.locator('#detail-conditionnement-valeur')
                bouton = self.page.locator('#detail-conditionnement-valider')
                bouton.scroll_into_view_if_needed()
                self.assertGreaterEqual(bouton.bounding_box()['height'], 44)
                self.assertLessEqual(self.page.locator('#detail').evaluate('e=>e.scrollWidth'), largeur)
                rectangles = [x.bounding_box() for x in (champ, bouton)]
                self.assertTrue(all(r['x'] >= 0 and r['x'] + r['width'] <= largeur for r in rectangles))
                a, b = rectangles
                self.assertTrue(a['x'] + a['width'] <= b['x'] or b['x'] + b['width'] <= a['x']
                                or a['y'] + a['height'] <= b['y'] or b['y'] + b['height'] <= a['y'])
        self.assertEqual(self.posts, [])
        self.assertEqual(self.errors, [])

    def test_relecture_interrompue_apres_accuse_reessaie_sans_renvoyer(self):
        self.ouvrir_fiche()
        lectures = []
        def proposition(route):
            lectures.append(route.request.url)
            if len(lectures) == 1:
                return route.abort('connectionreset')
            route.fulfill(json=dict(ui.PROPOSAL, lignes=[dict(ui.LINE, conditionnement=8)]))
        self.context.route('**/donnees/proposition.json?*', proposition)
        self.page.locator('#detail-conditionnement-valeur').fill('8')
        self.page.locator('#detail-conditionnement-valider').click()
        self.page.wait_for_function("suivisColisage.get('0000000000001')?.actif === false", timeout=15000)
        self.assertEqual(self.page.evaluate('proposition.lignes[0].conditionnement'), 8)
        self.assertEqual(len(self.posts), 1)
        self.assertGreaterEqual(len(lectures), 2)
        self.assertIn('recalculée', self.page.locator('#detail-conditionnement-etat').inner_text())

    def test_envoi_en_cours_reouverture_sans_double_envoi_ni_retour_force(self):
        en_attente = []
        self.api = lambda route: en_attente.append(route)
        self.ouvrir_fiche()
        self.page.locator('#detail-conditionnement-valeur').fill('8')
        self.page.locator('#detail-conditionnement-valider').click()
        self.page.wait_for_timeout(100)
        self.page.locator('#fermer-detail').click()
        self.page.locator('[data-role="detail"]').first.click()
        self.assertTrue(self.page.locator('#detail-conditionnement-valider').is_disabled())
        self.page.locator('#fermer-detail').click()
        self.fixtures['/donnees/proposition.json'] = dict(ui.PROPOSAL, lignes=[dict(ui.LINE, conditionnement=8)])
        self.assertEqual(len(en_attente), 1)
        en_attente[0].fulfill(json={'ok': True, 'conditionnement': 8})
        self.page.wait_for_function('proposition.lignes[0].conditionnement === 8')
        self.assertFalse(self.page.locator('#detail').is_visible())
        self.assertEqual(len(self.posts), 1)
        self.page.locator('[data-role="detail"]').first.click()
        self.assertEqual(self.page.locator('#detail-conditionnement-valeur').input_value(), '8')
        self.assertFalse(self.page.locator('#detail-conditionnement-valider').is_disabled())
        self.assertIn('recalculée', self.page.locator('#detail-conditionnement-etat').inner_text())

    def test_avertissement_prix_non_apparie_visible_et_sans_html(self):
        texte = 'Prix non apparié au conditionnement. <img src=x onerror=alert(1)>'
        self.fixtures['/donnees/proposition.json'] = dict(ui.PROPOSAL, lignes=[dict(
            ui.LINE, avertissements_conditionnement=[texte])])
        self.ouvrir_fiche()
        self.assertIn(texte, self.page.locator('#detail-conditionnement').inner_text())
        self.assertEqual(self.page.locator('#detail-conditionnement img').count(), 0)
        self.assertEqual(self.errors, [])

    def test_comptage_local_en_attente_empeche_une_reconversion_silencieuse(self):
        self.ouvrir_fiche()
        pending = [{'itm8': ui.CODE, 'colis': 2, 'conditionnement': 6}]
        self.page.evaluate('(v) => localStorage.setItem(CLE_COMPTAGES, JSON.stringify(v))', pending)
        self.page.locator('#detail-conditionnement-valeur').fill('8')
        self.page.locator('#detail-conditionnement-valider').click()
        self.assertEqual(self.posts, [])
        self.assertIn('comptage', self.page.locator('#detail-conditionnement-etat').inner_text())
        self.assertEqual(self.page.evaluate('JSON.parse(localStorage.getItem(CLE_COMPTAGES))'), pending)

    def test_saisie_validee_avant_envoi_et_virgule_acceptee(self):
        self.ouvrir_fiche()
        champ = self.page.locator('#detail-conditionnement-valeur')
        bouton = self.page.locator('#detail-conditionnement-valider')
        for valeur in ('', '0', '-1', 'NaN', 'Infinity', '1e309', '0x10', '2kg', '1,2,3'):
            with self.subTest(valeur=valeur):
                champ.fill(valeur)
                bouton.click()
                self.assertEqual(self.posts, [])
                self.assertIn('positif', self.page.locator('#detail-conditionnement-etat').inner_text())
        champ.fill('6')
        bouton.click()
        self.assertEqual(self.posts, [])
        self.assertIn('déjà', self.page.locator('#detail-conditionnement-etat').inner_text())
        self.fixtures['/donnees/proposition.json'] = dict(ui.PROPOSAL, lignes=[dict(ui.LINE, conditionnement=2.5)])
        champ.fill('2,5')
        bouton.click()
        self.page.wait_for_function("document.getElementById('detail-conditionnement-etat').textContent.includes('recalculée')")
        self.assertEqual(self.posts, [{'itm8': ui.CODE, 'conditionnement': 2.5, 'ancien_conditionnement': 6}])

    def test_colisage_enregistre_et_recalcul_relu_sans_effacer_les_saisies(self):
        def enregistrer(route):
            self.assertTrue(route.request.url.endswith('/api/conditionnement'))
            self.fixtures['/donnees/proposition.json'] = dict(
                ui.PROPOSAL, genere_le='fixture-after', lignes=[dict(
                    ui.LINE, conditionnement=8, prix_achat=1.5, propose_colis=2,
                    position_colis=1.5)])
            route.fulfill(json={'ok': True, 'conditionnement': 8, 'recalcul': 'en_cours'})
        self.api = enregistrer
        self.ouvrir_fiche()
        memoire = {'date': ui.PROPOSAL['date_commande'], 'par_article': {ui.CODE: 4}}
        self.page.evaluate('(v) => { localStorage.setItem(CLE_AJUSTEMENTS, JSON.stringify(v)); localStorage.setItem("saisie-test", "à conserver"); }', memoire)
        self.assertEqual(self.page.locator('#detail-conditionnement-valeur').input_value(), '6')
        self.page.locator('#detail-conditionnement-valeur').fill('8')
        self.page.locator('#detail-conditionnement-valider').click()
        self.page.wait_for_function("document.getElementById('detail-conditionnement-etat').textContent.includes('recalculée')")
        self.assertEqual(self.posts, [{'itm8': ui.CODE, 'conditionnement': 8, 'ancien_conditionnement': 6}])
        self.assertTrue(self.page.locator('#detail').is_visible())
        self.assertIn('colis de 8 kg', self.page.locator('#detail-sous').inner_text())
        self.assertIn('1,5', self.page.locator('#detail-stock').inner_text())
        self.assertIn('1,5 €', self.page.locator('#detail-prix').inner_text())
        self.assertEqual(self.page.evaluate('proposition.lignes[0].propose_colis'), 2)
        self.assertEqual(self.page.evaluate('quantite(proposition.lignes[0])'), 4)
        self.assertEqual(self.page.evaluate('JSON.parse(localStorage.getItem(CLE_AJUSTEMENTS))'), memoire)
        self.assertEqual(self.page.evaluate('localStorage.getItem("saisie-test")'), 'à conserver')
        self.assertIn('manuelles', self.page.locator('#detail-conditionnement-etat').inner_text())
        self.assertEqual(self.errors, [])


if __name__ == '__main__':
    unittest.main()
