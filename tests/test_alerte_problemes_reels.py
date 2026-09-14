"""Alertes lisibles : producteurs temporaires et navigateur sans API réelle."""
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import test_fraicheur_et_note as moteur
import test_alerte_date_commande as navigateur


COUVERTURE = {
    "dernier_comptage_le": "2026-09-07", "articles_dernier_comptage": 245,
    "articles_avec_position": 171, "articles_sorties_a_verifier": 171,
    "articles_sans_position": 68, "articles_sans_position_connus": 27,
    "articles_sans_mapping": 41, "sorties_attendues_jusquau": "2026-09-09",
}


def proposition():
    return {
        "date_commande": "2026-09-11", "date_livraison": "2026-09-12",
        "date_stock": "2026-09-10", "date_stock_verifiee": "2026-09-06",
        "date_reference": "2026-09-08", "couverture_stock": dict(COUVERTURE),
        "lignes": [
            {"itm8": "A", "connu": True, "sorties_couvertes_jusquau": "2026-09-08"},
            {"itm8": "B", "connu": True, "position_mesuree_le": "2026-09-02", "sorties_couvertes_jusquau": "2026-09-06"},
        ],
    }


class JourFige(date):
    @classmethod
    def today(cls):
        return cls(2026, 9, 10)


class AlerteMoteurTests(unittest.TestCase):
    def etat(self, p):
        with tempfile.TemporaryDirectory() as tmp:
            racine = Path(tmp)
            fichier = racine / "proposition.json"
            fichier.write_text(json.dumps(p), encoding="utf8")
            avant = fichier.read_bytes()
            with patch.object(moteur.FILET, "RACINE", racine), \
                 patch.object(moteur.FILET, "PROPOSITION", fichier), \
                 patch.object(moteur.FILET, "date", JourFige), \
                 patch.object(moteur.FILET, "jour_de_commande", return_value="2026-09-11"):
                resultat = moteur.FILET.etat_proposition()
            self.assertEqual(fichier.read_bytes(), avant)
            return resultat

    def test_comptage_recent_prime_sur_statistiques_anciennes(self):
        p = proposition()
        p["date_stock_verifiee"] = "2026-09-09"
        p["date_reference"] = "2026-09-04"
        p["couverture_stock"]["articles_sorties_a_verifier"] = 0
        for ligne in p["lignes"]:
            ligne["sorties_couvertes_jusquau"] = "2026-09-09"
        self.assertEqual(self.etat(p)[0], "a-jour")

    def test_vente_recente_ne_cache_pas_un_trou_anterieur(self):
        p = proposition()
        p["date_reference"] = "2026-09-09"
        p["lignes"][0]["sorties_couvertes_jusquau"] = "2026-09-09"
        etat, message, _ = self.etat(p)
        self.assertEqual(etat, "donnees-en-retard")
        self.assertIn("depuis le 07/09", message)
        self.assertNotIn("Ventes du 09/09 non intégrées", message)

    def test_alerte_explique_les_jours_non_couverts_sans_reclamer_un_fichier_deja_recu(self):
        etat, message, contenu = self.etat(proposition())
        self.assertEqual(etat, "donnees-en-retard")
        self.assertIn("Ventes du 09/09 non intégrées", message)
        self.assertIn("08/09", message)
        self.assertNotIn("07/09", message)
        self.assertNotIn("recompte", message)
        self.assertIn("fichier des ventes", message)
        self.assertIn("intégration", message)
        self.assertNotIn("non reçu", message)
        for nombre in ("245", "171", "27", "41"):
            self.assertNotIn(nombre, message)
        self.assertEqual(contenu, proposition())


class AlerteEcranTests(unittest.TestCase):
    setUpClass = navigateur.AlerteDateCommandeTests.__dict__["setUpClass"]
    tearDownClass = navigateur.AlerteDateCommandeTests.__dict__["tearDownClass"]
    setUp = navigateur.AlerteDateCommandeTests.setUp
    tearDown = navigateur.AlerteDateCommandeTests.tearDown
    route = navigateur.AlerteDateCommandeTests.route
    ouvrir = navigateur.AlerteDateCommandeTests.ouvrir
    rapport = navigateur.AlerteDateCommandeTests.rapport

    def test_rapport_sans_preuves_detaillees_ne_recopie_jamais_le_pave(self):
        rapport = self.rapport(jour="2026-09-11")
        rapport["message"] = "Comptage reçu : 245 articles ; 171 à vérifier ; 27 sans position ; 41 sans correspondance."
        alerte = self.ouvrir("2026-09-10T15:10:00+02:00", jour="2026-09-11", rapport=rapport)
        self.assertTrue(alerte.is_visible())
        texte = alerte.inner_text()
        self.assertIn("Fichier des ventes à vérifier", texte)
        self.assertIn("intégration", texte)
        for nombre in ("245", "171", "27", "41"):
            self.assertNotIn(nombre, texte)
        self.assertNotIn("non intégrées", texte, "Pas de date certaine sans preuve")

    def test_stock_recompte_a_jour_pas_de_bandeau_pour_statistiques_ou_bilan(self):
        self.ouvrir("2026-09-10T15:10:00+02:00", jour="2026-09-11", rapport=self.rapport(jour="2026-09-11"))
        p = proposition()
        p["date_reference"] = "2026-09-04"
        p["date_stock_verifiee"] = "2026-09-09"
        p["couverture_stock"]["articles_sorties_a_verifier"] = 0
        p["couverture_stock"]["sorties_attendues_jusquau"] = "2026-09-09"
        for ligne in p["lignes"]:
            ligne["sorties_couvertes_jusquau"] = "2026-09-09"
        self.page.evaluate("p => { Object.assign(proposition, p); majAlerte(); }", p)
        self.assertFalse(self.page.locator("#alerte").is_visible())
        self.assertEqual(self.page.locator("#alerte").inner_text(), "")
        self.assertEqual(self.page.evaluate("proposition.date_reference"), "2026-09-04")

    def test_jour_non_couvert_reste_visible_sans_rapport_ou_avec_rapport_perime(self):
        for rapport in (None, self.rapport(jour="2026-09-10"), self.rapport(jour="2026-09-11", etat="a-jour")):
            with self.subTest(rapport=rapport):
                self.ouvrir("2026-09-10T15:10:00+02:00", jour="2026-09-11", rapport=rapport)
                self.page.evaluate("p => { Object.assign(proposition, p); majAlerte(); }", proposition())
                alerte = self.page.locator("#alerte")
                self.assertTrue(alerte.is_visible())
                self.assertIn("09/09", alerte.inner_text())
                self.assertNotIn("10/09/2026", alerte.inner_text())

    def test_echec_technique_reste_visible_meme_pour_la_bonne_date(self):
        for etat in ("calcul-incomplet", "illisible", "vide", "absente"):
            with self.subTest(etat=etat):
                rapport = self.rapport(jour="2026-09-11", etat=etat)
                rapport["message"] = "Le calcul a échoué. La dernière proposition disponible est conservée."
                alerte = self.ouvrir("2026-09-10T15:10:00+02:00", jour="2026-09-11", rapport=rapport)
                self.assertTrue(alerte.is_visible())
                self.assertIn("échoué", alerte.inner_text())
                self.assertNotIn("Tu peux commander quand même", alerte.inner_text())

    def test_panne_sur_meme_generation_ne_disparait_pas_a_la_coupure(self):
        rapport = self.rapport(jour="2026-09-10", etat="calcul-incomplet")
        rapport["message"] = "Le calcul a échoué."
        alerte = self.ouvrir("2026-09-10T15:10:00+02:00", jour="2026-09-11", rapport=rapport)
        self.assertTrue(alerte.is_visible())
        self.assertIn("échoué", alerte.inner_text())

    def test_detail_identifie_les_articles_au_comptage_plus_ancien(self):
        self.ouvrir("2026-09-10T15:10:00+02:00", jour="2026-09-11")
        self.page.evaluate("p => { Object.assign(proposition, p); majAlerte(); }", proposition())
        self.page.locator("#details-donnees summary").click()
        ligne = self.page.locator("#details-donnees li").filter(has_text="B :")
        self.assertIn("comptage du 02/09", ligne.inner_text())
        self.assertIn("à vérifier depuis le 07/09", ligne.inner_text())

    def test_ancien_rapport_technique_devient_alerte_datee_et_details_sous_les_articles(self):
        rapport = self.rapport(jour="2026-09-11")
        rapport["message"] = (
            "Comptage du 2026-09-07 reçu : 245 articles, quantités prises en compte. "
            "171 article(s) à vérifier ; 27 articles identifiés sans position ; 41 sans correspondance."
        )
        self.ouvrir("2026-09-10T15:10:00+02:00", jour="2026-09-11", rapport=rapport)
        self.page.evaluate("p => { Object.assign(proposition, p, {lignes: p.lignes.map(l => ({...proposition.lignes[0], ...l}))}); majAlerte(); }", proposition())
        texte = self.page.locator("#alerte").inner_text()
        self.assertIn("Ventes du 09/09 non intégrées", texte)
        self.assertIn("08/09", texte)
        self.assertNotIn("07/09", texte)
        self.assertNotIn("recompte", texte)
        self.assertIn("fichier des ventes", texte)
        self.assertIn("intégration", texte)
        for nombre in ("245", "171", "27", "41"):
            self.assertNotIn(nombre, texte)
        self.assertNotIn("non reçu", texte)
        self.assertNotIn("10/09/2026", texte, "La journée en cours n'est pas exigible")
        details = self.page.locator("#details-donnees")
        self.assertFalse(details.evaluate("e => e.open"))
        self.assertTrue(self.page.evaluate("Boolean(document.getElementById('liste').compareDocumentPosition(document.getElementById('details-donnees')) & Node.DOCUMENT_POSITION_FOLLOWING)"))
        details.locator("summary").click()
        self.assertIn("245", details.inner_text())
        self.assertIn("27", details.inner_text())
        self.assertIn("41", details.inner_text())
        self.assertIn("07/09", details.inner_text())
        self.assertIn("08/09", details.inner_text())
        self.assertIn("compter", details.inner_text().lower())
        self.assertIn("correspondance", details.inner_text())


if __name__ == "__main__":
    unittest.main()
