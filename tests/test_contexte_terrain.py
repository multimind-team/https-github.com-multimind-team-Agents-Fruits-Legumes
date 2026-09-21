"""Consignes : journal, HTTP et calcul sur fixtures uniquement."""
import importlib.util
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import contexte_terrain as ct
import test_serveur_securite as serveur_fixture

CODE = serveur_fixture.CODE


def charge(**surcharge):
    jour = date.today()
    return {"itm8": CODE, "revision": 0, "requete_id": "requete-test-001",
            "emplacement": "tg", "statut": "actif", "maturite": "impeccable",
            "debut": jour.isoformat(), "fin": (jour + timedelta(days=7)).isoformat(),
            "stock_min_colis": 2, "note": "Nouvelle implantation", "motif": "TG semaine", **surcharge}


class ContexteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.donnees = Path(self.temp.name) / "donnees"
        self.donnees.mkdir()

    def ecrire(self, **kw):
        return ct.enregistrer(self.donnees, charge(**kw), {CODE})

    def test_journal_ajout_seul_idempotence_revision_et_annulation(self):
        premiere = self.ecrire()
        carnet = self.donnees / "decisions.jsonl"
        original = carnet.read_bytes()
        self.assertTrue(self.ecrire()["deja_enregistre"])
        self.assertEqual(carnet.read_bytes(), original)
        with self.assertRaises(ct.ConflitContexte):
            self.ecrire(note="reutilisation differente")
        with self.assertRaises(ct.ConflitContexte):
            self.ecrire(requete_id="autre-requete-001")
        annulation = self.ecrire(requete_id="annule-requete-01", revision=1, annuler=True)
        self.assertEqual(annulation["contexte"]["revision"], 2)
        self.assertTrue(carnet.read_bytes().startswith(original))
        vue = ct.charger(self.donnees)["articles"][CODE]
        self.assertEqual(vue["etat"], "annule")
        self.assertEqual(vue["stock_min_colis"], 2)
        self.assertEqual(ct.coefficient(vue, date.today().isoformat()), 1)
        self.assertEqual(premiere["contexte"]["auteur"], "responsable-rayon")

    def test_validation_stricte_avant_ecriture(self):
        invalides = [{"stock_min_colis": x} for x in (True, float("nan"), float("inf"), -1, "2", 10**400)]
        invalides += [{"revision": True}, {"debut": "2026-02-30"}, {"emplacement": []},
                      {"motif": " "}, {"auteur": "agent-donnees"}, {"itm8": "inconnu"},
                      {"statut": "reimplantation"}, {"promo_debut": "2026-09-20"},
                      {"note": "\ud800"}, {"annuler": 1}]
        for invalide in invalides:
            with self.subTest(invalide=repr(invalide)), self.assertRaises(ValueError):
                self.ecrire(**invalide)
        self.assertFalse((self.donnees / "decisions.jsonl").exists())

    def test_concurrence_ne_perd_pas_une_revision(self):
        def tenter(numero):
            try:
                return self.ecrire(requete_id=f"concurrence-{numero:04}")["ok"]
            except ct.ConflitContexte:
                return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(tenter, range(2))), [False, True])
        self.assertEqual(len(ct.charger(self.donnees)["historique"]), 1)

    def test_carnet_incomplet_est_refuse_sans_reparation(self):
        carnet = self.donnees / "decisions.jsonl"
        carnet.write_bytes(b'{"type":"conditionnement"}')
        with self.assertRaises(ValueError):
            self.ecrire()
        self.assertEqual(carnet.read_bytes(), b'{"type":"conditionnement"}')

    def test_programmation_future_et_expiration_sans_resurrection(self):
        today = date.today()
        self.ecrire()
        debut = (today + timedelta(days=2)).isoformat()
        fin = (today + timedelta(days=3)).isoformat()
        self.ecrire(revision=1, requete_id="future-requete-01", emplacement="ilot", debut=debut, fin=fin)
        contexte = ct.charger(self.donnees)["articles"][CODE]
        self.assertEqual(ct.coefficient(contexte, today.isoformat()), 1.5)
        self.assertEqual(ct.coefficient(contexte, debut), 2)
        self.assertEqual(ct.coefficient(contexte, (today + timedelta(days=4)).isoformat()), 1)

    def test_charger_ne_cree_aucun_fichier(self):
        self.assertEqual(ct.charger(self.donnees)["articles"], {})
        self.assertEqual(list(self.donnees.iterdir()), [])

    def test_promo_champs_optionnels_renouvellement_et_annulation_preservent_observations(self):
        champs = {"commentaire_promo": "Tête de gondole très visible", "precommande_colis": 18.5,
                  "rupture_promo": "oui", "objectif_promo": "Vendre avant dimanche", "bilan_promo": "Rupture samedi à 16 h",
                  "prix_promo": 1.99, "unite_prix_promo": "kg"}
        self.ecrire(**champs)
        renouvellement = self.ecrire(revision=1, requete_id="renouveler-promo-01", fin=(date.today() + timedelta(days=14)).isoformat())
        annulation = self.ecrire(revision=2, requete_id="annulation-promo-01", annuler=True)
        for resultat in (renouvellement, annulation):
            for champ, attendu in champs.items():
                self.assertEqual(resultat["contexte"][champ], attendu)
        self.assertEqual(len(ct.charger(self.donnees)["historique"]), 3)

    def test_validation_observations_promo_et_prix_unite(self):
        invalides = [{champ: valeur} for champ in ("precommande_colis", "prix_promo")
                    for valeur in (True, float("nan"), float("inf"), -1, "2", 10**400)]
        invalides += [{"commentaire_promo": "x" * 4001}, {"objectif_promo": "x" * 501},
                      {"bilan_promo": "x" * 6001}, {"note": "x" * 4001},
                      {"rupture_promo": True}, {"rupture_promo": "peut-etre"},
                      {"prix_promo": 1.99}, {"prix_promo": 1, "unite_prix_promo": "colis"}]
        for invalide in invalides:
            with self.subTest(invalide=repr(invalide)), self.assertRaises(ValueError):
                self.ecrire(**invalide)
        self.assertFalse((self.donnees / "decisions.jsonl").exists())

    def test_bilan_expire_ajoute_une_annotation_sans_reactiver_la_consigne(self):
        aujourd_hui = date.today()
        debut = (aujourd_hui - timedelta(days=7)).isoformat()
        fin = (aujourd_hui - timedelta(days=1)).isoformat()
        class DateCreation(date):
            @classmethod
            def today(cls):
                return aujourd_hui - timedelta(days=7)
        with patch.object(ct, "date", DateCreation):
            self.ecrire(debut=debut, fin=fin, promo_debut=debut, promo_fin=fin)
        avant = ct.charger(self.donnees)["articles"][CODE]
        requete = charge(revision=1, requete_id="bilan-expire-001", debut=debut, fin=fin,
                         promo_debut=debut, promo_fin=fin, bilan_promo="Écoulement terminé", precommande_colis=10,
                         commentaire_promo="Temps pluvieux", note="Conserver ce retour pour la prochaine promo")
        resultat = ct.enregistrer(self.donnees, requete, {CODE})
        self.assertTrue(resultat["annotation_seule"])
        self.assertEqual(resultat["contexte"]["etat"], "expire")
        apres = ct.charger(self.donnees)["articles"][CODE]
        for jour in (debut, fin, aujourd_hui.isoformat(), (aujourd_hui + timedelta(days=1)).isoformat()):
            self.assertEqual(ct.coefficient(avant, jour), ct.coefficient(apres, jour))
        self.assertTrue(ct.enregistrer(self.donnees, requete, {CODE})["deja_enregistre"])
        for changement in ({"emplacement": "ilot"}, {"stock_min_colis": 3}, {"statut": "fin-saison"},
                           {"maturite": "sur-mur"}, {"promo_debut": (aujourd_hui - timedelta(days=8)).isoformat()}):
            with self.subTest(changement=changement), self.assertRaises(ValueError):
                ct.enregistrer(self.donnees, {**requete, "revision": 2, "requete_id": "bilan-interdit-01", **changement}, {CODE})

    def test_nouvelle_consigne_antidatee_refusee_mais_observation_promo_passee_possible(self):
        passe = (date.today() - timedelta(days=1)).isoformat()
        with self.assertRaises(ValueError):
            self.ecrire(debut=passe, fin=passe, bilan_promo="Ancien bilan")
        resultat = self.ecrire(emplacement="rayon", stock_min_colis=0, promo_debut=passe, promo_fin=passe,
                               commentaire_promo="Souvenir documenté", precommande_colis=0)
        self.assertEqual(ct.coefficient(resultat["contexte"], date.today().isoformat()), 1)
        self.assertEqual(resultat["contexte"]["precommande_colis"], 0)

    def test_idempotence_distingue_omission_et_retrait_explicite(self):
        self.ecrire(precommande_colis=10)
        self.ecrire(revision=1, requete_id="omettre-promo-001")
        with self.assertRaises(ct.ConflitContexte):
            self.ecrire(revision=1, requete_id="omettre-promo-001", precommande_colis=None)

    def test_prix_conserve_ne_perd_pas_son_unite_par_omission_partielle(self):
        self.ecrire(prix_promo=1.99, unite_prix_promo="kg")
        with self.assertRaises(ValueError):
            self.ecrire(revision=1, requete_id="unite-promo-001", unite_prix_promo=None)
        self.assertEqual(ct.charger(self.donnees)["articles"][CODE]["unite_prix_promo"], "kg")

    def test_observations_sur_tg_ou_arret_annules_ne_reactivent_rien(self):
        for statut in ("actif", "fin-saison", "rupture-fournisseur"):
            dossier = self.donnees / statut / "donnees"
            ct.enregistrer(dossier, charge(statut=statut, commentaire_promo="À conserver", precommande_colis=12), {CODE})
            ct.enregistrer(dossier, {"itm8": CODE, "revision": 1, "requete_id": "annule-commentaire-001",
                                    "annuler": True, "motif": "Arrêt de cette consigne"}, {CODE})
            avant = ct.charger(dossier)["articles"][CODE]
            demande = {"itm8": CODE, "revision": 2, "requete_id": "observe-annule-001", "motif": "Retour rayon",
                       "observations_seules": True, "note": "Commentaire automatique corrigé", "bilan_promo": "Belle visibilité"}
            resultat = ct.enregistrer(dossier, demande, {CODE})
            apres = ct.charger(dossier)["articles"][CODE]
            with self.subTest(statut=statut):
                self.assertTrue(resultat["annotation_seule"])
                self.assertTrue(apres["annuler"])
                self.assertEqual(apres["etat"], "annule")
                self.assertFalse(ct.actif(apres, date.today().isoformat()))
                self.assertEqual(ct.coefficient(apres, date.today().isoformat()), 1)
                self.assertEqual(apres["commentaire_promo"], "À conserver")
                self.assertEqual(apres["precommande_colis"], 12)
                for champ in ct.CHAMPS_MOTEUR:
                    self.assertEqual(apres[champ], avant[champ])
                self.assertTrue(ct.enregistrer(dossier, demande, {CODE})["deja_enregistre"])

    def test_observations_sans_contexte_creent_seulement_un_contexte_neutre(self):
        passe = (date.today() - timedelta(days=5)).isoformat()
        demande = {"itm8": CODE, "revision": 0, "requete_id": "observe-neutre-001", "motif": "Ancienne campagne",
                   "observations_seules": True, "promo_debut": passe, "promo_fin": passe, "bilan_promo": "Bilan passé"}
        resultat = ct.enregistrer(self.donnees, demande, {CODE})
        self.assertTrue(resultat["annotation_seule"])
        contexte = resultat["contexte"]
        self.assertEqual(contexte["emplacement"], "rayon")
        self.assertEqual(contexte["statut"], "actif")
        self.assertEqual(contexte["stock_min_colis"], 0)
        self.assertEqual(contexte["debut"], date.today().isoformat())
        self.assertEqual(contexte["promo_debut"], passe)
        self.assertEqual(ct.coefficient(contexte, date.today().isoformat()), 1)

    def test_observations_interdisent_tout_changement_moteur_et_supportent_rejeu_apres_modification(self):
        self.ecrire(note="Première note")
        demande = {"itm8": CODE, "revision": 1, "requete_id": "observe-interdits-001", "motif": "Complément",
                   "observations_seules": True, "note": "Deuxième note"}
        for change in ({"emplacement": "ilot"}, {"emplacement": "tg"}, {"stock_min_colis": 5}, {"stock_min_colis": 2}, {"statut": "fin-saison"},
                       {"maturite": "sur-mur"}, {"debut": (date.today() + timedelta(days=1)).isoformat()},
                       {"annuler": True}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                ct.enregistrer(self.donnees, {**demande, **change}, {CODE})
        ct.enregistrer(self.donnees, demande, {CODE})
        self.ecrire(revision=2, requete_id="autre-modif-001", emplacement="ilot")
        self.assertTrue(ct.enregistrer(self.donnees, demande, {CODE})["deja_enregistre"])
        self.assertEqual(ct.charger(self.donnees)["articles"][CODE]["emplacement"], "ilot")

    def test_observations_expirees_acceptent_dates_promo_corrigees_sans_changer_periode_moteur(self):
        aujourd_hui = date.today()
        debut = (aujourd_hui - timedelta(days=10)).isoformat()
        fin = (aujourd_hui - timedelta(days=1)).isoformat()
        class DateCreation(date):
            @classmethod
            def today(cls):
                return aujourd_hui - timedelta(days=10)
        with patch.object(ct, "date", DateCreation):
            self.ecrire(debut=debut, fin=fin)
        resultat = ct.enregistrer(self.donnees, {"itm8": CODE, "revision": 1, "requete_id": "dates-promo-expire-001",
            "motif": "Dates exactes de la campagne", "observations_seules": True,
            "promo_debut": debut, "promo_fin": fin, "commentaire_promo": "Offre passée"}, {CODE})
        self.assertTrue(resultat["annotation_seule"])
        self.assertEqual(resultat["contexte"]["etat"], "expire")
        self.assertEqual(resultat["contexte"]["fin"], fin)


class CalculContexteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("proposition_contexte", Path(__file__).resolve().parents[1] / "moteur/proposer-commande.py")
        cls.prop = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.prop)

    def calcul(self, contexte=None, position=0, date_ref="2026-09-07", surcharge=None, moyenne=10):
        return self.prop.proposer(date_ref, {CODE: {"tauxPerte": 0, "saison": [moyenne] * 366}},
            {CODE: {"position": position, "mesuree_le": "2026-08-01"}},
            {"overrides": {CODE: surcharge or {}}}, {CODE: {"CONDIT.BASE": 10}}, {CODE: "2026-09-07"},
            [1] * 7, {}, contextes={CODE: contexte} if contexte else {})["lignes"][CODE]

    def contexte(self, **kw):
        return {"debut": "2026-09-01", "fin": "2026-09-30", "emplacement": "tg", "statut": "actif", "stock_min_colis": 0, **kw}

    def test_dates_tg_et_ilot_sont_appliques_aux_bons_jours(self):
        self.assertEqual(self.calcul()["demande"], 20)
        self.assertEqual(self.calcul(self.contexte())["demande"], 30)
        self.assertEqual(self.calcul(self.contexte(emplacement="ilot", debut="2026-09-09"))["demande"], 30)
        self.assertEqual(self.calcul(self.contexte(fin="2026-09-07"))["demande"], 20)
        self.assertEqual(self.calcul(self.contexte(emplacement="ilot", debut="2026-09-20", fin="2026-09-20"), date_ref="2026-09-18")["demande"], 40)

    def test_previsions_archivees_sont_ventes_journalieres_pas_besoin_net(self):
        calcule = self.calcul(self.contexte(emplacement="ilot", debut="2026-09-20", fin="2026-09-20", stock_min_colis=3),
                              position=25, date_ref="2026-09-18")
        self.assertEqual(calcule["previsions_journalieres"], {"2026-09-19": 10, "2026-09-20": 20, "2026-09-21": 10})
        self.assertEqual(sum(calcule["previsions_journalieres"].values()), 40)

    def test_maturite_note_promo_ne_changent_pas_stock_ou_demande(self):
        normal = self.calcul(self.contexte(emplacement="rayon"), position=30)
        for maturite in ct.MATURITES:
            autre = self.calcul(self.contexte(emplacement="rayon", maturite=maturite, note="ne pas commander", promo_debut="2026-09-01", promo_fin="2026-09-30"), position=30)
            for champ in ("demande", "position_unites", "propose_colis", "promotion"):
                self.assertEqual(autre[champ], normal[champ])

    def test_plancher_reimplantation_arret_et_protections(self):
        contexte = self.contexte(emplacement="rayon", stock_min_colis=2)
        self.assertEqual(self.calcul(contexte, position=10)["propose_colis"], 3)
        self.assertEqual(self.calcul({**contexte, "statut": "reimplantation", "date_cible": "2026-09-09"}, moyenne=0)["propose_colis"], 2)
        self.assertEqual(self.calcul({**contexte, "statut": "reimplantation", "date_cible": "2026-09-10"}, moyenne=0)["propose_colis"], 0)
        self.assertEqual(self.calcul(contexte, position=-100)["propose_colis"], 0)
        self.assertEqual(self.calcul(contexte, surcharge={"promotion": True})["propose_colis"], 0)
        for statut in ("fin-saison", "rupture-fournisseur"):
            self.assertEqual(self.calcul({**contexte, "statut": statut})["propose_colis"], 0)


class ContexteHTTPTests(unittest.TestCase):
    # Réutilise uniquement la fixture HTTP ; les tests historiques gardent leur
    # propre classe et ne doivent pas être exécutés plusieurs fois par la suite.
    setUp = serveur_fixture.ServeurIsoleTests.setUp
    fermer = serveur_fixture.ServeurIsoleTests.fermer
    ecrire = serveur_fixture.ServeurIsoleTests.ecrire
    requete = serveur_fixture.ServeurIsoleTests.requete

    def test_contexte_http_revision_rejeu_et_provenance(self):
        statut, corps, _ = self.requete("POST", "/api/contexte", charge())
        self.assertEqual(statut, 200, corps)
        self.assertTrue(json.loads(corps)["enregistre"])
        statut, corps, _ = self.requete("GET", "/api/contexte")
        self.assertEqual(json.loads(corps)["articles"][CODE]["revision"], 1)
        self.assertEqual(self.requete("HEAD", "/api/contexte")[1], b"")
        self.assertEqual(self.requete("POST", "/api/contexte", charge(requete_id="nouveau-requete-01"))[0], 409)
        self.assertTrue(json.loads(self.requete("POST", "/api/contexte", charge())[1])["deja_enregistre"])
        self.assertEqual(self.requete("POST", "/api/contexte", charge(), headers={"Origin": "https://evil.test"})[0], 403)

    def test_comptage_conserve_motif_et_commentaire_distincts(self):
        from datetime import datetime
        fait = self.module.normaliser_comptage({"itm8": CODE, "date": date.today().isoformat(),
            "colis": 1, "saisi_le": datetime.now().isoformat(), "motif": "Erreur de caisse", "commentaire": "Inversion pomme poire"},
            {CODE: {"conditionnement": 10, "libelle": "TEST"}})
        self.assertEqual(fait["motif"], "Erreur de caisse")
        self.assertEqual(fait["commentaire"], "Inversion pomme poire")

    def test_annotation_promo_http_ne_declenche_pas_de_recalcul(self):
        self.assertEqual(self.requete("POST", "/api/contexte", charge())[0], 200)
        self.recalc_mock.reset_mock()
        statut, corps, _ = self.requete("POST", "/api/contexte", charge(
            revision=1, requete_id="annotation-http-001", commentaire_promo="Très bonne visibilité", precommande_colis=12))
        self.assertEqual(statut, 200, corps)
        self.assertEqual(json.loads(corps)["recalcul"], "non_necessaire")
        self.recalc_mock.assert_not_called()

    def test_mode_observations_http_conserve_annulation_et_ne_recalcule_pas(self):
        self.requete("POST", "/api/contexte", charge())
        self.requete("POST", "/api/contexte", {"itm8": CODE, "revision": 1, "requete_id": "http-annule-mode-001",
            "annuler": True, "motif": "Fin de mise en avant"})
        self.recalc_mock.reset_mock()
        statut, corps, _ = self.requete("POST", "/api/contexte", {"itm8": CODE, "revision": 2,
            "requete_id": "http-observe-mode-001", "motif": "Bilan", "observations_seules": True,
            "commentaire_promo": "Bonne opération", "note": "Observation complétée"})
        self.assertEqual(statut, 200, corps)
        resultat = json.loads(corps)
        self.assertTrue(resultat["contexte"]["annuler"])
        self.assertEqual(resultat["recalcul"], "non_necessaire")
        self.recalc_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
