"""Droits et marche arrière : uniquement des carnets temporaires, jamais le rayon réel."""
import contextlib
import importlib.util
import io
import multiprocessing
import threading
from concurrent.futures import ThreadPoolExecutor
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

MOTEUR = Path(__file__).resolve().parents[1] / "moteur"
sys.path.insert(0, str(MOTEUR))
import journal_agents as journal
import regles


def charger(nom):
    spec = importlib.util.spec_from_file_location("droits_" + nom.replace("-", "_"), MOTEUR / (nom + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


AJUSTER = charger("ajuster-commande")
ANNULER = charger("annuler")
APPLIQUER = charger("appliquer-decision")
FERIES = charger("ouverture-jours-feries")
MOTIF = "Test isolé : la vérification justifie ce changement temporaire."


class FixturesTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.racine = Path(temp.name)
        self.decisions = self.racine / "decisions.jsonl"
        self.ajustements = self.racine / "ajustements.jsonl"
        self.proposition = self.racine / "proposition.json"
        self.pouvoirs = self.racine / "pouvoirs.json"
        self.pouvoirs.write_bytes((MOTEUR.parent / "donnees/pouvoirs.json").read_bytes())
        self.proposition.write_text(json.dumps({"date_commande": date.today().isoformat(),
            "lignes": [{"itm8": "TEST", "libelle": "Article fixture", "propose_colis": 10}]}), encoding="utf-8")
        for module, nom, valeur in [
            (AJUSTER, "FICHIER", self.ajustements), (AJUSTER, "PROPOSITION", self.proposition),
            (AJUSTER, "POUVOIRS", self.pouvoirs), (APPLIQUER, "POUVOIRS", self.pouvoirs),
            (APPLIQUER, "DECISIONS", self.decisions), (ANNULER, "DECISIONS", self.decisions),
            (journal, "JOURNAUX", self.racine / "journaux"), (regles, "CARNET", self.decisions),
            (FERIES, "FICHIER", self.racine / "feries.json"),
        ]:
            self.enterContext(patch.object(module, nom, valeur))
        self.enterContext(patch.object(ANNULER, "libelles", return_value={"TEST": "Article fixture"}))
        self.enterContext(patch.object(APPLIQUER, "libelles", return_value={"TEST": "Article fixture"}))

    def appeler(self, module, *arguments):
        sortie = io.StringIO()
        with patch.object(sys, "argv", [module.__file__, *arguments]), contextlib.redirect_stdout(sortie):
            resultat = module.main()
        return resultat, sortie.getvalue()

    def etat_fichiers(self):
        # Le fichier vide du verrou OS persiste pour garder une identité commune.
        # Tous les carnets, compteurs et décisions doivent rester intacts.
        return {str(p.relative_to(self.racine)): p.read_bytes() for p in self.racine.rglob("*")
                if p.is_file() and p.name != ".operations.lock"}

    def ajustement(self, applique=False, agent="agent-tendances"):
        self.ajustements.write_text(json.dumps({"date_commande": date.today().isoformat(),
            "article": "TEST", "libelle": "Article fixture", "avant": 10, "apres": 12,
            "applique": applique, "agent": agent, "motif": MOTIF}) + "\n", encoding="utf-8")


class RetraitsTests(FixturesTests):
    def test_lecture_seule_ne_retire_ni_proposition_ni_commande(self):
        for agent in ("agent-controle", "agent-articles", "agent-orchestrateur", "inconnu"):
            for applique in (False, True):
                with self.subTest(agent=agent, applique=applique):
                    self.ajustement(applique)
                    avant = self.etat_fichiers()
                    with self.assertRaises(SystemExit):
                        self.appeler(AJUSTER, "--retirer", "TEST", "--agent", agent, "--motif", MOTIF)
                    self.assertEqual(self.etat_fichiers(), avant)

    def test_analyste_ne_retire_pas_une_commande_appliquee(self):
        self.ajustement(applique=True, agent="responsable-rayon")
        avant = self.etat_fichiers()
        with self.assertRaises(SystemExit):
            self.appeler(AJUSTER, "--retirer", "TEST", "--agent", "agent-tendances", "--motif", MOTIF)
        self.assertEqual(self.etat_fichiers(), avant)

    def test_analyste_retire_sa_suggestion_par_ajout_uniquement(self):
        self.ajustement()
        avant = self.ajustements.read_bytes()
        self.appeler(AJUSTER, "--retirer", "TEST", "--agent", "agent-tendances", "--motif", MOTIF)
        self.assertTrue(self.ajustements.read_bytes().startswith(avant))
        self.assertEqual(AJUSTER.lire(), {})


class AnnulationsTests(FixturesTests):
    def action(self, avant="8", apres="12", champ="conditionnement"):
        numero = journal.enregistrer("agent-rayon", "Réglage fixture", motif=MOTIF,
            changements=[{"itm8": "TEST", "champ": champ, "avant": avant, "apres": apres}])
        self.decisions.write_text(json.dumps({"id": "fixture", "action": numero,
            "article": "TEST", "type": champ, "valeur": apres,
            "valide_a_partir_de": date.today().isoformat()}) + "\n", encoding="utf-8")
        return numero

    def test_annulation_refuse_les_roles_sans_droit(self):
        numero = self.action()
        with patch.object(ANNULER, "POUVOIRS", self.pouvoirs, create=True):
            for agent in ("agent-controle", "agent-articles", "agent-orchestrateur", "agent-tendances", "inconnu"):
                with self.subTest(agent=agent):
                    avant = self.etat_fichiers()
                    with self.assertRaises(SystemExit):
                        self.appeler(ANNULER, numero, "--par", agent)
                    self.assertEqual(self.etat_fichiers(), avant)

    def test_annulation_ne_signe_pas_responsable_par_defaut(self):
        numero = self.action()
        avant = self.etat_fichiers()
        with self.assertRaises(SystemExit):
            self.appeler(ANNULER, numero)
        self.assertEqual(self.etat_fichiers(), avant)

    def test_conflit_refuse_ancienne_action_sans_ecriture(self):
        for valeur in ("20", None, "12"):
            with self.subTest(valeur=valeur):
                numero = self.action()
                with self.decisions.open("a", encoding="utf-8") as fichier:
                    fichier.write(json.dumps({"id": "nouvelle", "type": "conditionnement",
                        "article": "TEST", "valeur": valeur}) + "\n")
                avant = self.etat_fichiers()
                with patch.object(ANNULER, "POUVOIRS", self.pouvoirs, create=True):
                    with self.assertRaisesRegex(SystemExit, "[Cc]onflit"):
                        self.appeler(ANNULER, numero, "--par", "responsable-rayon")
                self.assertEqual(self.etat_fichiers(), avant)

    def test_action_vide_ou_inverse_inconnu_est_refusee_sans_write(self):
        for changements in ([], [{"itm8": "TEST", "champ": "seuil", "avant": 1, "apres": 2}]):
            with self.subTest(changements=changements):
                # Émule un journal historique qui annonçait abusivement annulable.
                numero = journal.enregistrer("agent-rayon", "Action historique", annulable=True,
                                              changements=changements)
                avant = self.etat_fichiers()
                with patch.object(ANNULER, "POUVOIRS", self.pouvoirs, create=True):
                    with self.assertRaisesRegex(SystemExit, "[Ii]nverse|annulable"):
                        self.appeler(ANNULER, numero, "--par", "responsable-rayon")
                self.assertEqual(self.etat_fichiers(), avant)

    def test_echec_verification_ne_dit_jamais_defait(self):
        numero = self.action()
        cfg = regles.charger()
        sortie = io.StringIO()
        with patch.object(ANNULER, "POUVOIRS", self.pouvoirs, create=True), \
             patch.object(regles, "charger", return_value=cfg), \
             patch.object(sys, "argv", ["annuler.py", numero, "--par", "agent-rayon"]), \
             contextlib.redirect_stdout(sortie):
            with self.assertRaises(SystemExit):
                ANNULER.main()
        self.assertNotIn("C'est défait", sortie.getvalue())
        self.assertNotIn(numero, journal.actions_annulees())

    def test_dernier_ne_selectionne_pas_un_ancien_etat_reussi(self):
        numero = self.action()
        journal.echec("agent-rayon", "Échec final fixture", action=numero)
        avant = self.etat_fichiers()
        with patch.object(ANNULER, "POUVOIRS", self.pouvoirs), self.assertRaises(SystemExit):
            self.appeler(ANNULER, "--dernier", "--par", "agent-rayon")
        self.assertEqual(self.etat_fichiers(), avant)

    def test_annulation_autorisee_conserve_carnet_et_signe_executant(self):
        numero = self.action()
        avant = self.decisions.read_bytes()
        with patch.object(ANNULER, "POUVOIRS", self.pouvoirs, create=True):
            _, texte = self.appeler(ANNULER, numero, "--par", "agent-rayon")
        self.assertIn("C'est défait", texte)
        self.assertTrue(self.decisions.read_bytes().startswith(avant))
        self.assertEqual(regles.charger()["overrides"]["TEST"]["conditionnement"], "8")
        self.assertEqual(journal.lire()[-1]["agent"], "agent-rayon")


class SimulationTests(FixturesTests):
    def test_application_refuse_un_carnet_non_termine_sans_le_modifier(self):
        avant = b'{"type":"fournisseur","article":"TEST","valeur":"Fixture"}'
        self.decisions.write_bytes(avant)
        with self.assertRaisesRegex(ValueError, "dernière ligne non terminée"):
            self.appeler(APPLIQUER, "conditionnement", "TEST", "8", "--motif", MOTIF)
        self.assertEqual(self.decisions.read_bytes(), avant)

    def test_annulation_refuse_un_carnet_non_termine_sans_le_modifier(self):
        self.appeler(APPLIQUER, "conditionnement", "TEST", "8", "--motif", MOTIF)
        numero = journal.lire()[-1]["action"]
        avant = self.decisions.read_bytes().rstrip(b"\r\n")
        self.decisions.write_bytes(avant)
        with patch.object(ANNULER, "POUVOIRS", self.pouvoirs), \
             self.assertRaisesRegex(ValueError, "dernière ligne non terminée"):
            self.appeler(ANNULER, numero, "--par", "agent-rayon")
        self.assertEqual(self.decisions.read_bytes(), avant)

    def test_simulation_application_ne_cree_pas_de_repertoire(self):
        avant = list(self.racine.rglob("*"))
        self.appeler(APPLIQUER, "conditionnement", "TEST", "12", "--motif", MOTIF, "--simuler")
        self.assertEqual(list(self.racine.rglob("*")), avant)

    def test_annuler_sans_cible_affiche_aide_sans_write(self):
        avant = self.etat_fichiers()
        resultat, texte = self.appeler(ANNULER, "--par", "agent-rayon")
        self.assertEqual(resultat, 1)
        self.assertIn("--dernier", texte)
        self.assertEqual(self.etat_fichiers(), avant)

    def test_ids_decisions_distincts_meme_seconde(self):
        from datetime import datetime
        class Figee(datetime):
            @classmethod
            def now(cls):
                return cls(2026, 9, 9, 12, 0, 0)
        with patch.object(APPLIQUER, "datetime", Figee), patch.object(ANNULER, "datetime", Figee), \
             patch.object(ANNULER, "POUVOIRS", self.pouvoirs):
            self.appeler(APPLIQUER, "conditionnement", "TEST", "8", "--motif", MOTIF)
            self.appeler(APPLIQUER, "conditionnement", "TEST", "12", "--motif", MOTIF)
            numero = journal.lire()[-1]["action"]
            self.appeler(ANNULER, numero, "--par", "agent-rayon")
        lignes = [json.loads(l) for l in self.decisions.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len({l["id"] for l in lignes}), 3)


class FeriesTests(FixturesTests):
    def test_consultation_ne_cree_pas_de_fichier(self):
        avant = self.etat_fichiers()
        self.assertIn("2040-11-11", [j["date"] for j in FERIES.a_confirmer(depuis="2040-11-05")])
        self.appeler(FERIES)
        self.assertEqual(self.etat_fichiers(), avant)

    def test_consultation_conserve_exactement_les_confirmations(self):
        contenu = {"jours": {"2040-11-11": {"nom": "Armistice", "statut": "ferme"}}}
        FERIES.FICHIER.write_text(json.dumps(contenu), encoding="utf-8")
        avant = FERIES.FICHIER.read_bytes()
        self.assertEqual(FERIES.a_confirmer(depuis="2040-11-05"), [])
        self.assertEqual(FERIES.FICHIER.read_bytes(), avant)

    def test_fichier_invalide_est_refuse_et_jamais_remplace(self):
        for contenu in (b'{"jours":', b'[]', b'{"jours":[]}',
                        b'{"jours":{"2026-11-11":{"statut":"inconnu"}}}'):
            with self.subTest(contenu=contenu):
                FERIES.FICHIER.write_bytes(contenu)
                with self.assertRaises(ValueError):
                    FERIES.a_confirmer()
                with self.assertRaises(ValueError):
                    FERIES.definir(f"{date.today().year}-11-11", "ferme", MOTIF)
                self.assertEqual(FERIES.FICHIER.read_bytes(), contenu)

    def test_definition_invalide_ne_cree_pas_de_fichier_metier(self):
        with self.assertRaises(SystemExit):
            FERIES.definir(f"{date.today().year}-12-25", "ferme", MOTIF)
        self.assertFalse(FERIES.FICHIER.exists())

    def test_definition_ferie_ne_promet_pas_une_annulation_non_implantee(self):
        jour = f"{date.today().year}-11-11"
        with contextlib.redirect_stdout(io.StringIO()):
            FERIES.definir(jour, "ferme", MOTIF, "responsable-rayon")
        self.assertEqual(FERIES.statut(jour), "ferme")
        self.assertFalse(journal.lire()[-1]["annulable"])
        self.assertNotIn("_operation_id", json.loads(FERIES.FICHIER.read_text(encoding="utf-8")))

    def test_journal_ne_declare_pas_annulable_un_inverse_non_supporte(self):
        for changements in ([], [{"itm8": "TEST", "champ": "seuil", "avant": 1, "apres": 2}]):
            with self.subTest(changements=changements):
                journal.enregistrer("agent-rayon", "Fixture", annulable=True, changements=changements)
                self.assertFalse(journal.lire()[-1]["annulable"])


class DatesReglesTests(FixturesTests):
    def test_carnet_absent_et_lignes_vides_restent_acceptes(self):
        self.assertEqual(regles.charger(), {"groupes": {}, "overrides": {}})
        self.decisions.write_text('\n  \n{"type":"conditionnement","article":"TEST","valeur":"8"}', encoding="utf-8")
        self.assertEqual(regles.charger()["overrides"]["TEST"]["conditionnement"], "8")

    def test_decision_tronquee_nest_pas_ignoree(self):
        avant = b'{"type":"fournisseur","article":"TEST","valeur":"Fixture"}\n{"type":"conditionnement","valeur":"8"'
        self.decisions.write_bytes(avant)
        with self.assertRaisesRegex(ValueError, "decisions.jsonl.*ligne 2"):
            regles.charger()
        self.assertEqual(self.decisions.read_bytes(), avant)

    def test_journal_annulations_tronque_bloque_le_calcul(self):
        self.carnet([{"type": "conditionnement", "article": "TEST", "valeur": "8"}])
        fichier = journal.JOURNAUX / "tout.jsonl"
        fichier.parent.mkdir()
        avant = b'{"message":"ancien format"}\n{"annule_action":'
        fichier.write_bytes(avant)
        with self.assertRaisesRegex(ValueError, "tout.jsonl.*ligne 2"):
            regles.charger()
        self.assertEqual(fichier.read_bytes(), avant)

    def test_journal_annulations_inaccessible_nest_pas_un_journal_vide(self):
        self.carnet([{"type": "conditionnement", "article": "TEST", "valeur": "8"}])
        with patch.object(journal, "actions_annulees", side_effect=PermissionError("Fixture inaccessible")), \
             self.assertRaises(PermissionError):
            regles.charger()

    def test_objet_json_obligatoire_mais_anciens_champs_acceptes(self):
        for invalide in ("[]", "null", "12"):
            with self.subTest(invalide=invalide):
                self.decisions.write_text(invalide, encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "objet JSON attendu"):
                    regles.charger()
        self.carnet([{"ancienne_information": "conservée"},
                     {"type": "conditionnement", "article": "TEST", "valeur": "8"}])
        self.assertEqual(regles.charger()["overrides"]["TEST"]["conditionnement"], "8")

    def test_reservation_numeros_refuse_un_carnet_endommage(self):
        fichier = journal.JOURNAUX / ".numeros.jsonl"
        fichier.parent.mkdir()
        fichier.write_bytes(b'{"action":')
        with self.assertRaisesRegex(ValueError, ".numeros.jsonl.*ligne 1"):
            journal.numero_action()
        self.assertEqual(fichier.read_bytes(), b'{"action":')

    def carnet(self, lignes):
        self.decisions.write_text("".join(json.dumps(l) + "\n" for l in lignes), encoding="utf-8")

    def test_decision_future_inactive_aujourdhui(self):
        self.carnet([
            {"id": "a", "type": "conditionnement", "article": "TEST", "valeur": "8"},
            {"id": "b", "type": "conditionnement", "article": "TEST", "valeur": "12", "valide_a_partir_de": "2999-01-01"},
        ])
        avant = self.etat_fichiers()
        self.assertEqual(regles.charger()["overrides"]["TEST"]["conditionnement"], "8")
        self.assertEqual(self.etat_fichiers(), avant)

    def test_date_calcul_inclut_le_jour_effectif_sans_changer_le_carnet(self):
        self.carnet([
            {"id": "a", "type": "fournisseur", "article": "TEST", "valeur": "A", "valide_a_partir_de": "2026-09-01"},
            {"id": "b", "type": "fournisseur", "article": "TEST", "valeur": "B", "valide_a_partir_de": "2026-09-10"},
        ])
        avant = self.etat_fichiers()
        self.assertEqual(regles.charger(date_calcul="2026-09-09")["overrides"]["TEST"]["fournisseur"], "A")
        self.assertEqual(regles.charger(date_calcul=date(2026, 9, 10))["overrides"]["TEST"]["fournisseur"], "B")
        self.assertEqual([d["id"] for d in regles.expliquer("TEST", date_calcul="2026-09-09")], ["a"])
        self.assertEqual(self.etat_fichiers(), avant)

    def test_annulation_future_ne_suppprime_pas_decision_active(self):
        self.carnet([
            {"id": "a", "type": "fournisseur", "article": "TEST", "valeur": "A"},
            {"id": "b", "type": "annulation", "annule": "a", "valide_a_partir_de": "2999-01-01"},
        ])
        self.assertEqual(regles.charger()["overrides"]["TEST"]["fournisseur"], "A")


def reserver_processus(racine, barriere, resultats):
    journal.JOURNAUX = Path(racine) / "journaux"
    numero = journal.numero_action()
    barriere.wait(timeout=15)  # tous ont réservé AVANT la première publication
    journal.enregistrer("agent-fixture", "Numéro réservé en processus", action=numero)
    resultats.put(numero)


def appliquer_processus(racine, barriere, resultats, agent):
    import time
    racine = Path(racine)
    journal.JOURNAUX = racine / "journaux"
    APPLIQUER.POUVOIRS = racine / "pouvoirs.json"
    APPLIQUER.DECISIONS = regles.CARNET = racine / "decisions.jsonl"
    APPLIQUER.libelles = lambda: {"TEST": "Article fixture"}
    original = APPLIQUER.ecrire_decision
    def lent(ligne):
        time.sleep(0.2)  # élargit la fenêtre entre contrôle et publication
        original(ligne)
    APPLIQUER.ecrire_decision = lent
    sys.argv = ["appliquer-decision.py", "conditionnement", "TEST", "12", "--motif", MOTIF, "--auteur", agent]
    barriere.wait(timeout=15)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            APPLIQUER.main()
        resultats.put("ok")
    except SystemExit as erreur:
        resultats.put(str(erreur))


def annuler_processus(racine, barriere, resultats, numero):
    import time
    racine = Path(racine)
    journal.JOURNAUX = racine / "journaux"
    ANNULER.POUVOIRS = racine / "pouvoirs.json"
    ANNULER.DECISIONS = regles.CARNET = racine / "decisions.jsonl"
    ANNULER.libelles = lambda: {"TEST": "Article fixture"}
    original = regles.charger
    def lent(*args, **kwargs):
        cfg = original(*args, **kwargs)
        time.sleep(0.2)
        return cfg
    regles.charger = lent
    sys.argv = ["annuler.py", numero, "--par", "agent-rayon"]
    barriere.wait(timeout=15)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            ANNULER.main()
        resultats.put("ok")
    except SystemExit as erreur:
        resultats.put(str(erreur))


class ConcurrenceTests(FixturesTests):
    def test_une_seule_annulation_concurrente(self):
        numero = journal.enregistrer("agent-rayon", "Fixture", changements=[
            {"itm8": "TEST", "champ": "conditionnement", "avant": "8", "apres": "12"}])
        self.decisions.write_text(json.dumps({"id": "fixture", "action": numero,
            "type": "conditionnement", "article": "TEST", "valeur": "12"}) + "\n", encoding="utf-8")
        contexte = multiprocessing.get_context("spawn")
        barriere, resultats = contexte.Barrier(4), contexte.Queue()
        processus = [contexte.Process(target=annuler_processus,
            args=(str(self.racine), barriere, resultats, numero)) for _ in range(4)]
        try:
            for fils in processus:
                fils.start()
            retours = [resultats.get(timeout=25) for _ in processus]
            for fils in processus:
                fils.join(timeout=15)
                self.assertEqual(fils.exitcode, 0)
            self.assertEqual(retours.count("ok"), 1, retours)
            self.assertEqual(len(self.decisions.read_text(encoding="utf-8").splitlines()), 2)
        finally:
            for fils in processus:
                if fils.is_alive():
                    fils.terminate()
                    fils.join()
            resultats.close()

    def test_plafonds_processus_sur_controle_et_ecriture(self):
        for global_max, max_agent, agents in [
            (20, 1, ["agent-rayon"] * 4),
            (1, 20, ["agent-rayon", "agent-donnees", "agent-courrier", "agent-rayon"]),
        ]:
            with self.subTest(global_max=global_max), tempfile.TemporaryDirectory() as temp:
                racine = Path(temp)
                pouvoirs = json.loads(self.pouvoirs.read_text(encoding="utf-8"))
                pouvoirs["plafond_par_jour_tous_agents"] = global_max
                for agent in set(agents):
                    pouvoirs["agents"][agent]["plafond_par_jour"] = max_agent
                (racine / "pouvoirs.json").write_text(json.dumps(pouvoirs), encoding="utf-8")
                contexte = multiprocessing.get_context("spawn")
                barriere, resultats = contexte.Barrier(4), contexte.Queue()
                processus = [contexte.Process(target=appliquer_processus,
                    args=(str(racine), barriere, resultats, agent)) for agent in agents]
                try:
                    for fils in processus:
                        fils.start()
                    retours = [resultats.get(timeout=25) for _ in processus]
                    for fils in processus:
                        fils.join(timeout=15)
                        self.assertEqual(fils.exitcode, 0)
                    self.assertEqual(retours.count("ok"), 1, retours)
                    lignes = (racine / "decisions.jsonl").read_text(encoding="utf-8").splitlines()
                    self.assertEqual(len(lignes), 1)
                finally:
                    for fils in processus:
                        if fils.is_alive():
                            fils.terminate()
                            fils.join()
                    resultats.close()

    def test_plafond_ne_compte_pas_plusieurs_etats_de_la_meme_action(self):
        numero = journal.enregistrer("agent-rayon", "Fixture")
        journal.enregistrer("agent-rayon", "Même action", action=numero)
        pouvoirs = json.loads(self.pouvoirs.read_text(encoding="utf-8"))
        pouvoirs["agents"]["agent-rayon"]["plafond_par_jour"] = 2
        self.pouvoirs.write_text(json.dumps(pouvoirs), encoding="utf-8")
        APPLIQUER.verifier_pouvoirs("agent-rayon", "conditionnement")

    def test_plafond_utilise_le_dernier_etat_de_l_action(self):
        numero = journal.enregistrer("agent-rayon", "Fixture")
        journal.echec("agent-rayon", "Échec ultérieur fixture", action=numero)
        pouvoirs = json.loads(self.pouvoirs.read_text(encoding="utf-8"))
        pouvoirs["agents"]["agent-rayon"]["plafond_par_jour"] = 1
        self.pouvoirs.write_text(json.dumps(pouvoirs), encoding="utf-8")
        APPLIQUER.verifier_pouvoirs("agent-rayon", "conditionnement")

    def test_reservations_distinctes_meme_sans_publication(self):
        numeros = [journal.numero_action() for _ in range(5)]
        self.assertEqual(len(set(numeros)), 5)

    def test_reservations_threads_distinctes_avant_publication(self):
        barriere = threading.Barrier(6)
        def reserver(_):
            numero = journal.numero_action()
            barriere.wait(timeout=15)
            journal.enregistrer("agent-fixture", "Action fixture", action=numero)
            return numero
        with ThreadPoolExecutor(max_workers=6) as pool:
            numeros = list(pool.map(reserver, range(6)))
        self.assertEqual(len(set(numeros)), 6)
        self.assertEqual(len(journal.lire()), 6)

    def test_reservations_processus_distinctes_avant_publication(self):
        contexte = multiprocessing.get_context("spawn")
        barriere = contexte.Barrier(4)
        resultats = contexte.Queue()
        processus = [contexte.Process(target=reserver_processus,
            args=(str(self.racine), barriere, resultats)) for _ in range(4)]
        try:
            for processus_fils in processus:
                processus_fils.start()
            numeros = [resultats.get(timeout=25) for _ in processus]
            for processus_fils in processus:
                processus_fils.join(timeout=20)
                self.assertEqual(processus_fils.exitcode, 0)
            self.assertEqual(len(set(numeros)), 4)
            self.assertEqual(len(journal.lire()), 4)
        finally:
            for processus_fils in processus:
                if processus_fils.is_alive():
                    processus_fils.terminate()
                    processus_fils.join()
            resultats.close()


if __name__ == "__main__":
    unittest.main()
