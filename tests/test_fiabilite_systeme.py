"""Régressions audit : aucun serveur ou carnet réel n'est utilisé."""
import importlib.util
import contextlib
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from http.server import SimpleHTTPRequestHandler
from io import BytesIO, StringIO

MOTEUR = Path(__file__).resolve().parents[1] / "moteur"
sys.path.insert(0, str(MOTEUR))
from verrou_donnees import append_jsonl, environnement_verrou, verrou_donnees
from ecriture_derivee import ecrire_json, publier_etat_calcul
import ecriture_derivee
from lancer_tests_isoles import ignorer_prives, neutraliser_courrier


def charger(nom):
    spec = importlib.util.spec_from_file_location(nom, MOTEUR / (nom + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class IsolationCopiesTests(unittest.TestCase):
    def test_garde_refuse_lecture_secret_et_ecriture_projet(self):
        from verifier_factures_isolees import garde, RACINE as racine_protegee
        with tempfile.TemporaryDirectory() as tmp:
            secret_fictif = str(Path(tmp) / '.env')
            garde('open', (secret_fictif, 'w', os.O_WRONLY | os.O_CREAT))
            for mode, flags in [('r', os.O_RDONLY), ('r+', os.O_RDWR), ('w+', os.O_RDWR | os.O_TRUNC)]:
                with self.assertRaisesRegex(AssertionError, 'Lecture de secrets'):
                    garde('open', (secret_fictif, mode, flags))
            with self.assertRaisesRegex(AssertionError, 'Écriture dans le projet réel'):
                garde('open', (str(racine_protegee / '.env'), 'w', os.O_WRONLY | os.O_CREAT))

    def test_copie_exclut_les_secrets_et_traces_privees(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, copie = Path(tmp) / "source", Path(tmp) / "copie"
            prives = [".env", ".env.local", "donnees/courrier-config.json",
                      "donnees/courrier/lot/piece.eml", "donnees/.sentinelle-evenements.json",
                      "donnees/.courrier_uids_connus.json", "donnees/.operations.lock",
                      "donnees/.operations-bail.lock", "moteur/serveur.log"]
            utiles = [".env.example", "moteur/serveur.py", "donnees/faits/2026.jsonl"]
            for nom in prives + utiles:
                fichier = source / nom
                fichier.parent.mkdir(parents=True, exist_ok=True)
                fichier.write_text("FIXTURE", encoding="utf-8")
            shutil.copytree(source, copie, ignore=ignorer_prives)
            for nom in prives:
                self.assertFalse((copie / nom).exists(), nom)
            for nom in utiles:
                self.assertEqual((copie / nom).read_text(encoding="utf-8"), "FIXTURE")
            neutraliser_courrier(copie)
            self.assertEqual(json.loads((copie / "donnees/courrier-config.json").read_text()),
                             {"mot_de_passe": "", "actif": False})


class VerrousTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "Partage des fichiers Windows")
    def test_publication_reessaie_apres_lecture_windows_breve(self):
        with tempfile.TemporaryDirectory() as tmp:
            cible = Path(tmp) / "recalcul.json"
            cible.write_bytes(b'{"etat":"en-cours"}')
            remplacer = os.replace
            appels = []
            def parfois_occupe(source, destination):
                appels.append(1)
                if len(appels) == 1:
                    raise PermissionError("Lecture concurrente brève")
                return remplacer(source, destination)
            with patch.object(ecriture_derivee.os, "replace", side_effect=parfois_occupe):
                ecrire_json(cible, {"etat": "termine"})
            self.assertEqual(json.loads(cible.read_text())["etat"], "termine")
            self.assertEqual(len(appels), 2)

    def test_statut_et_sorties_dun_lot_partagent_la_meme_identite(self):
        with tempfile.TemporaryDirectory() as tmp, verrou_donnees(tmp):
            dossier = Path(tmp)
            publier_etat_calcul(dossier, "en-cours", "fixture")
            ecrire_json(dossier / "etat.json", {"articles": {}})
            ecrire_json(dossier / "proposition.json", {"lignes": []})
            publier_etat_calcul(dossier, "echec", "fixture", "Arrêt avant la liste de comptage")
            statut = json.loads((dossier / "recalcul.json").read_text())
            self.assertEqual(statut["etat"], "echec")
            for nom in ("etat.json", "proposition.json"):
                self.assertEqual(json.loads((dossier / nom).read_text())["_operation_id"], statut["operation_id"])

    def test_ajout_refuse_une_ligne_sans_separateur_sans_modifier(self):
        with tempfile.TemporaryDirectory() as tmp:
            chemin = Path(tmp) / "messages.jsonl"
            original = b'{"id":"ancien"}'
            chemin.write_bytes(original)
            with self.assertRaisesRegex(ValueError, "dernière ligne"):
                append_jsonl(chemin, [{"id": "nouveau"}])
            self.assertEqual(chemin.read_bytes(), original)

    def test_enfant_synchrone_herite_du_verrou_et_concurrent_refuse(self):
        code = "from verrou_donnees import verrou_donnees; import sys\nwith verrou_donnees(sys.argv[1], timeout=.1): print('pris')"
        with tempfile.TemporaryDirectory() as tmp, verrou_donnees(tmp):
            environnement = os.environ.copy()
            environnement["PYTHONPATH"] = str(MOTEUR) + os.pathsep + environnement.get("PYTHONPATH", "")
            concurrent = subprocess.run([sys.executable, "-B", "-c", code, tmp], env=environnement, capture_output=True, text=True)
            self.assertNotEqual(concurrent.returncode, 0)
            environnement.update(environnement_verrou(tmp))
            environnement["PYTHONPATH"] = str(MOTEUR) + os.pathsep + environnement.get("PYTHONPATH", "")
            enfant = subprocess.run([sys.executable, "-B", "-c", code, tmp], env=environnement, capture_output=True, text=True, timeout=10)
            self.assertEqual(enfant.returncode, 0, enfant.stderr)
            self.assertIn("pris", enfant.stdout)

    def test_lecture_et_ecriture_concurrentes_ne_perdent_pas_de_modification(self):
        code = """from verrou_donnees import verrou_donnees
from pathlib import Path
import sys, time
p=Path(sys.argv[1]); compteur=p/'compteur.txt'
for _ in range(15):
    with verrou_donnees(p):
        n=int(compteur.read_text()); time.sleep(.002); compteur.write_text(str(n+1))
"""
        with tempfile.TemporaryDirectory() as tmp:
            compteur = Path(tmp) / "compteur.txt"
            compteur.write_text("0")
            env = os.environ.copy()
            env["PYTHONPATH"] = str(MOTEUR) + os.pathsep + env.get("PYTHONPATH", "")
            enfants = [subprocess.Popen([sys.executable, "-B", "-c", code, tmp], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(3)]
            for enfant in enfants:
                _, erreurs = enfant.communicate(timeout=15)
                self.assertEqual(enfant.returncode, 0, erreurs)
            self.assertEqual(compteur.read_text(), "45")


class SauvegardeTests(unittest.TestCase):
    def setUp(self):
        self.module = charger("sauvegarder")
        self.appels = []

    def faux_git(self, commande, **options):
        self.appels.append(commande)
        sorties = {("git", "branch", "--show-current"): "main\n",
                   ("git", "rev-parse", "HEAD"): "abcdef123456789\n",
                   ("git", "ls-remote", "origin", "refs/heads/main"): "abcdef123456789\trefs/heads/main\n"}
        return subprocess.CompletedProcess(commande, 0, sorties.get(tuple(commande), ""), "")

    def test_echec_public_ne_reproduit_pas_un_detail_prive(self):
        secret = "https://identite:SECRET-FIXTURE@exemple.invalid/projet.git"
        with patch.object(self.module, "etape_1_controle_securite", side_effect=RuntimeError(secret)), \
             patch("dire.publier") as publier, contextlib.redirect_stdout(StringIO()) as console:
            self.assertFalse(self.module.executer_sauvegarde_complete())
        self.assertIn(secret, console.getvalue())
        message = publier.call_args.args[0]
        self.assertNotIn(secret, message)
        self.assertIn("Sauvegarde interrompue", message)
        self.assertNotIn("confirmée", message)

    def test_tests_sauvegarde_passent_ensemble_par_la_copie_isolee(self):
        def execute(commande, **options):
            self.appels.append(commande)
            return subprocess.CompletedProcess(commande, 0, '{"erreurs":[],"lignes_jsonl":0}', "")
        with patch.object(self.module, "executer", side_effect=execute):
            self.module.etape_2_tests_integrite()
        self.assertEqual(len(self.appels), 2)
        self.assertEqual(self.appels[0][:2], [sys.executable, "-B"])
        self.assertEqual(Path(self.appels[1][2]).name, "lancer_tests_isoles.py")
        self.assertEqual(self.appels[1][3:], ["tests/test_preparer_photos.py", "tests/test_envoyer_classeur_marge.py"])

    def test_arbre_propre_pousse_aussi_le_commit_en_attente(self):
        with patch.object(self.module, "executer", side_effect=self.faux_git):
            resultat = self.module.etape_4_git_commit_push()
        self.assertFalse(resultat["nouveau_commit"])
        self.assertTrue(resultat["publication_confirmee"])
        self.assertIn(["git", "push", "origin", "HEAD:refs/heads/main"], self.appels)

    def test_sans_push_reste_explicitement_local(self):
        with patch.object(self.module, "executer", side_effect=self.faux_git):
            resultat = self.module.etape_4_git_commit_push(sans_push=True)
        self.assertFalse(resultat["publication_confirmee"])
        self.assertFalse(resultat["publication_demandee"])
        self.assertFalse(any("push" in appel for appel in self.appels))

    def test_fichier_courrier_deja_suivi_bloque(self):
        with patch.object(self.module, "executer", return_value=subprocess.CompletedProcess([], 0, "donnees/courrier/photo.jpg\0", "")):
            with self.assertRaisesRegex(ValueError, "restent suivis"):
                self.module.verifier_index_prive()

    def test_registres_prives_et_bail_deja_suivis_bloquent(self):
        for chemin in sorted(self.module.FICHIERS_PRIVES):
            with self.subTest(chemin=chemin), patch.object(self.module, "executer", return_value=subprocess.CompletedProcess([], 0, chemin + "\0", "")):
                with self.assertRaisesRegex(ValueError, "restent suivis"):
                    self.module.verifier_index_prive()

    def test_exclusions_privees_reelles_et_fausse_preuve_tmp_refusee(self):
        with tempfile.TemporaryDirectory() as tmp:
            racine = Path(tmp)
            subprocess.run(["git", "init", "--quiet", str(racine)], check=True, capture_output=True)
            ignore = racine / ".gitignore"
            ignore.write_bytes((MOTEUR.parent / ".gitignore").read_bytes())
            def executer(commande, **options):
                return subprocess.run(commande, cwd=racine, capture_output=True, text=True, shell=isinstance(commande, str))
            with patch.object(self.module, "RACINE", racine), patch.object(self.module, "executer", side_effect=executer):
                self.module.etape_1_controle_securite()
                ignore.write_text(ignore.read_text().replace("donnees/courrier/", ""))
                # *.tmp demeure ignoré : l'ancien contrôle aurait faussement passé.
                self.assertEqual(executer(["git", "check-ignore", "donnees/courrier/test_ignore.tmp"]).returncode, 0)
                with self.assertRaisesRegex(ValueError, "courrier/"):
                    self.module.etape_1_controle_securite()

    def test_autre_branche_refuse_avant_indexation(self):
        with patch.object(self.module, "executer", return_value=subprocess.CompletedProcess([], 0, "codex/essai\n", "")) as execution:
            with self.assertRaisesRegex(ValueError, "revenir explicitement"):
                self.module.etape_4_git_commit_push()
        self.assertEqual(execution.call_count, 1)

    def test_push_non_confirme_ne_declenche_pas_succes(self):
        def git(commande, **options):
            retour = self.faux_git(commande, **options)
            if "ls-remote" in commande:
                retour.stdout = "autre\trefs/heads/main"
            return retour
        with patch.object(self.module, "executer", side_effect=git), self.assertRaisesRegex(RuntimeError, "ne confirme pas"):
            self.module.etape_4_git_commit_push()


class ResumeCarnetsTests(unittest.TestCase):
    def test_statut_initial_absent_est_servi_sans_creer_de_donnee(self):
        serveur = charger("serveur")
        with tempfile.TemporaryDirectory() as tmp:
            donnees = Path(tmp)
            requete = serveur.Gestionnaire.__new__(serveur.Gestionnaire)
            requete.path = "/donnees/recalcul.json"
            requete.command = "GET"
            requete._verifier_provenance = lambda: True
            codes = []
            requete.send_response = codes.append
            requete.send_header = lambda *args: None
            requete.end_headers = lambda: None
            requete.wfile = BytesIO()
            with patch.object(serveur, "DONNEES", donnees):
                self.assertIsNone(requete.send_head())
            self.assertEqual(codes, [200])
            self.assertEqual(json.loads(requete.wfile.getvalue()), {"etat": "absent"})
            self.assertEqual(list(donnees.iterdir()), [])

    def test_derive_http_ferme_le_disque_avant_envoi_client(self):
        serveur = charger("serveur")
        with tempfile.TemporaryDirectory() as tmp:
            racine = Path(tmp)
            donnees = racine / "donnees"
            donnees.mkdir()
            cible = donnees / "etat.json"
            cible.write_bytes(b'{"version":1}')
            requete = serveur.Gestionnaire.__new__(serveur.Gestionnaire)
            requete.path = "/donnees/etat.json"
            requete.command = "GET"
            requete._verifier_provenance = lambda: True
            with patch.object(serveur, "DONNEES", donnees), patch.object(serveur, "RACINE", racine), \
                 patch.object(SimpleHTTPRequestHandler, "send_head", side_effect=lambda: cible.open("rb")):
                flux_http = requete.send_head()
            nouveau = donnees / "remplacement.json"
            nouveau.write_bytes(b'{"version":2}')
            os.replace(nouveau, cible)
            self.assertEqual(flux_http.read(), b'{"version":1}')
            flux_http.close()
            self.assertEqual(cible.read_bytes(), b'{"version":2}')

    def test_api_message_ne_confirme_pas_un_ajout_sur_carnet_incomplet(self):
        serveur = charger("serveur")
        with tempfile.TemporaryDirectory() as tmp:
            donnees = Path(tmp)
            chemin = donnees / "messages.jsonl"
            original = b'{"id":"message:2026-09-15T07:00:00","texte":"ancien"}'
            chemin.write_bytes(original)
            reponses = []
            requete = SimpleNamespace(_charge_json={"messages": [{"texte": "nouveau", "ecrit_le": "2026-09-15T08:00:00"}]},
                                      _repondre=lambda charge, *args: reponses.append(charge))
            with patch.object(serveur, "DONNEES", donnees), patch.object(serveur, "lancer_reponse_message") as lancer:
                serveur.Gestionnaire._recevoir_messages(requete)
            self.assertFalse(reponses[0]["ok"])
            self.assertEqual(chemin.read_bytes(), original)
            lancer.assert_not_called()

    def test_decouvre_annees_et_invalide_cache_apres_ajout(self):
        serveur = charger("serveur")
        with tempfile.TemporaryDirectory() as tmp:
            donnees = Path(tmp) / "donnees"
            faits = donnees / "faits"
            faits.mkdir(parents=True)
            (faits / "2027.jsonl").write_text('{}\n', encoding="utf-8")
            (faits / "prive.jsonl").write_text('{}\n', encoding="utf-8")
            with patch.object(serveur, "DONNEES", donnees), patch.object(serveur, "DOSSIER_FAITS", faits):
                resultat = serveur.resume_carnets()
                self.assertEqual([f["annee"] for f in resultat["fichiers"]], ["2027"])
                self.assertEqual(resultat["total_lignes"], 1)
                append_jsonl(faits / "2027.jsonl", [{"id": "nouveau"}])
                self.assertEqual(serveur.resume_carnets()["total_lignes"], 2)


if __name__ == "__main__":
    unittest.main()
