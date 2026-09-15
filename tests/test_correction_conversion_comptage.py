"""Maintenance de conversion : toutes les écritures utilisent une racine temporaire."""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
OUTIL = "corriger-conversion-comptage.py"
CONFIRMATION = "Oui : Amandine par caissette de 8 ; filets de 5 kg et 10 kg à l’unité"
MOTIF = "Correction de conversion, pas de nouveau relevé : " + CONFIRMATION


class CorrectionConversionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.racine = Path(self.temp.name)
        self.moteur = self.racine / "moteur"
        self.moteur.mkdir()
        for nom in (OUTIL, "journal_agents.py", "verrou_donnees.py"):
            source = RACINE / "moteur" / nom
            if source.exists():
                shutil.copy2(source, self.moteur / nom)
        self.donnees = self.racine / "donnees"
        self.fichier = self.donnees / "faits" / "2026.jsonl"
        self.fichier.parent.mkdir(parents=True)
        self.original = {
            "id": "comptage:2026-09-07:0000087950042:saisie",
            "type": "comptage", "mesure": "position", "origine_mesure": "ecran-comptage",
            "article": "0000087950042", "article_source": "0000087950042",
            "date_source": "2026-09-07", "date_effet": "2026-09-07",
            "horodatage": "2026-09-07T16:58:54", "enregistre_le": "2026-09-07T17:31:12",
            "quantite": -260, "colis": -4, "conditionnement": 65,
            "unite": "pièce", "libelle": "PDT PRINCESSE AMANDINE 2KG",
            "motif": "Position relevée en chambre froide, rayon déjà rempli.",
            "source": {"origine": "app/compter.html", "saisi_le": "2026-09-07T16:58:54"},
        }
        self.ecrire_faits([self.original])
        (self.donnees / "pouvoirs.json").write_text(json.dumps({
            "plafond_par_jour_tous_agents": 20,
            "agents": {"agent-rayon": {"peut_seul": ["conditionnement"], "plafond_par_jour": 15}},
        }), encoding="utf-8")

    def ecrire_faits(self, lignes):
        self.fichier.write_bytes(("\r\n".join(json.dumps(x, ensure_ascii=False) for x in lignes) + "\r\n").encode("utf-8"))

    def instantane(self):
        return {p.relative_to(self.racine).as_posix(): p.read_bytes()
                for p in self.donnees.rglob("*") if p.is_file()}

    def commande(self, *extras):
        return [sys.executable, str(self.moteur / OUTIL), self.original["id"], "8",
                "--ancien-conditionnement", "65", "--ancienne-quantite", "-260", "--colis", "-4",
                "--auteur", "agent-rayon", "--motif", MOTIF,
                "--confirmation", CONFIRMATION, "--reference-confirmation", "test:confirmation-explicite",
                "--ecrivains-inactifs", *extras]

    def lancer(self, *extras):
        return subprocess.run(self.commande(*extras), cwd=self.racine, capture_output=True,
                              encoding="utf-8", env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"})

    def test_repetition_identique_necrit_plus_rien(self):
        premiere = self.lancer()
        self.assertEqual(premiere.returncode, 0, premiere.stderr)
        avant = self.instantane()
        reprise = self.lancer()
        self.assertEqual(reprise.returncode, 0, reprise.stderr)
        rapport = json.loads(reprise.stdout)
        self.assertEqual(rapport["statut"], "deja-applique")
        self.assertTrue(rapport["verifie"])
        self.assertEqual(rapport["correction"]["id"], json.loads(premiere.stdout)["correction"]["id"])
        self.assertEqual(self.instantane(), avant)

    def test_refuse_parametres_non_confirmes_ou_incoherents(self):
        cas = [
            (("--ancienne-quantite", "-259"), "ancienne quantité"),
            (("--ancien-conditionnement", "64"), "ancien conditionnement"),
            (("--colis", "-3"), "colis"),
            (("--confirmation", ""), "confirmation"),
            (("--reference-confirmation", ""), "référence"),
            (("--motif", "court"), "motif"),
            (("--auteur", "agent-donnees"), "agent-rayon"),
            (("--ancien-conditionnement", "nan"), "fini"),
        ]
        for extras, erreur in cas:
            with self.subTest(extras=extras):
                avant = self.instantane()
                resultat = self.lancer("--simuler", *extras)
                self.assertNotEqual(resultat.returncode, 0)
                self.assertIn(erreur, resultat.stderr.lower())
                self.assertEqual(self.instantane(), avant)

    def test_refuse_fait_original_incoherent_et_conditionnement_invalide(self):
        import copy
        initial = copy.deepcopy(self.original)
        cas = [("quantite", -259), ("quantite", float("nan")),
               ("colis", True), ("conditionnement", 0),
               ("horodatage", "2026-09-08T16:58:54"), ("date_effet", "2026-09-08"),
               ("source", {"origine": "app/compter.html", "saisi_le": "2026-09-07T18:00:00"}),
               ("type", "vente"), ("mesure", "stock")]
        for champ, valeur in cas:
            with self.subTest(champ=champ, valeur=valeur):
                original = {**initial, champ: valeur}
                self.ecrire_faits([original])
                avant = self.instantane()
                resultat = self.lancer("--simuler")
                self.assertNotEqual(resultat.returncode, 0)
                self.assertEqual(self.instantane(), avant)
        self.ecrire_faits([initial])
        for conditionnement in ("0", "-1", "nan", "inf", "1e308"):
            with self.subTest(conditionnement=conditionnement):
                commande = self.commande("--simuler")
                commande[3] = conditionnement
                resultat = subprocess.run(commande, capture_output=True)
                self.assertNotEqual(resultat.returncode, 0)

    def test_refuse_sans_attestation_absence_ecrivains(self):
        commande = self.commande()
        commande.remove("--ecrivains-inactifs")
        resultat = subprocess.run(commande, capture_output=True)
        self.assertNotEqual(resultat.returncode, 0)
        self.assertEqual(len(self.fichier.read_bytes().splitlines()), 1)

    def test_refuse_comptage_posterieur_ou_correction_concurrente(self):
        for type_fait, jour, heure in (("comptage", "2026-09-08", "18:00:00"),
                                      ("comptage", "2026-09-07", "19:00:00"),
                                      ("correction-comptage", "2026-09-07", "16:58:54")):
            with self.subTest(type=type_fait, jour=jour, heure=heure):
                autre = {**self.original, "id": "autre-mesure", "type": type_fait,
                         "date_source": jour, "date_effet": jour, "horodatage": f"{jour}T{heure}"}
                if type_fait == "correction-comptage":
                    autre["cible_id"] = self.original["id"]
                self.ecrire_faits([self.original, autre])
                avant = self.instantane()
                resultat = self.lancer("--simuler")
                self.assertNotEqual(resultat.returncode, 0)
                self.assertRegex(resultat.stderr.lower(), "postérieur|correction.*conflit")
                self.assertEqual(self.instantane(), avant)

    def test_refuse_original_duplique_et_json_tronque_ou_non_fini(self):
        self.ecrire_faits([self.original, self.original])
        self.assertNotEqual(self.lancer("--simuler").returncode, 0)
        for fin in (b'{"id": "tronque"', b'{"id": "infini", "quantite": NaN}\n'):
            self.ecrire_faits([self.original])
            with self.fichier.open("ab") as f:
                f.write(fin)
            avant = self.instantane()
            resultat = self.lancer("--simuler")
            self.assertNotEqual(resultat.returncode, 0)
            self.assertEqual(self.instantane(), avant)

    def test_complete_separateur_sans_recrire_les_octets_existants(self):
        self.fichier.write_bytes(self.fichier.read_bytes().rstrip(b"\r\n"))
        avant = self.fichier.read_bytes()
        resultat = self.lancer()
        self.assertEqual(resultat.returncode, 0, resultat.stderr)
        self.assertTrue(self.fichier.read_bytes().startswith(avant))
        lignes = [json.loads(l) for l in self.fichier.read_bytes().splitlines()]
        self.assertEqual(len(lignes), 2)
        self.assertEqual(lignes[0], self.original)

    def test_refuse_identifiant_malforme_meme_present_dans_les_faits(self):
        self.original["article"] = "87950042"
        self.original["id"] = "comptage:2026-09-07:87950042:saisie"
        self.ecrire_faits([self.original])
        resultat = self.lancer("--simuler")
        self.assertNotEqual(resultat.returncode, 0)
        self.assertIn("identifiant", resultat.stderr.lower())

    def test_refuse_produit_colis_ancien_conditionnement_incoherent(self):
        self.original["quantite"] = -259
        self.ecrire_faits([self.original])
        resultat = self.lancer("--simuler", "--ancienne-quantite", "-259")
        self.assertNotEqual(resultat.returncode, 0)
        self.assertIn("incohérente", resultat.stderr.lower())

    def lancer_injection(self, injection):
        programme = (
            "import importlib.util, sys\n"
            f"spec=importlib.util.spec_from_file_location('conversion', {str(self.moteur / OUTIL)!r})\n"
            "module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)\n"
            f"sys.argv={self.commande()[1:]!r}\n" + injection + "\nmodule.main()\n"
        )
        return subprocess.run([sys.executable, "-c", programme], cwd=self.racine,
                              capture_output=True, encoding="utf-8",
                              env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"})

    def test_detecte_ecriture_entre_lecture_et_append_et_apres_append(self):
        for appel, nombre_corrections in ((2, 0), (3, 1)):
            with self.subTest(appel=appel):
                self.ecrire_faits([self.original])
                injection = (
                    "snapshot=module.instantane\ncompteur=0\n"
                    "def concurrence():\n"
                    " global compteur\n compteur+=1\n"
                    f" if compteur=={appel}:\n"
                    f"  with open({str(self.fichier)!r}, 'ab') as f: f.write(b'{{\"id\":\"concurrent\",\"type\":\"vente\",\"article\":\"autre\"}}\\n')\n"
                    " return snapshot()\n"
                    "module.instantane=concurrence\n"
                )
                resultat = self.lancer_injection(injection)
                self.assertNotEqual(resultat.returncode, 0)
                self.assertIn("conflit", resultat.stderr.lower())
                faits = [json.loads(l) for l in self.fichier.read_bytes().splitlines()]
                self.assertEqual(faits[0], self.original)
                self.assertEqual(sum(f.get("type") == "correction-comptage" for f in faits), nombre_corrections)

    def test_interruption_apres_fait_refuse_duplication_et_signale_audit_incomplet(self):
        resultat = self.lancer_injection(
            "def panne(**kwargs):\n raise OSError('panne de journal simulee')\n"
            "module.carnet_agents.enregistrer=panne\n")
        self.assertNotEqual(resultat.returncode, 0)
        self.assertEqual(len(self.fichier.read_bytes().splitlines()), 2)
        avant = self.instantane()
        reprise = self.lancer()
        self.assertNotEqual(reprise.returncode, 0)
        self.assertIn("reprise manuelle", reprise.stderr.lower())
        self.assertEqual(self.instantane(), avant)

    def test_trois_conversions_negatives_et_rejeu_isole_du_moteur(self):
        cas = [("0000087950042", -4, 65, 8, -260, -32),
               ("0000087955044", -8, 5, 1, -40, -8),
               ("0000087955004", -5, 10, 1, -50, -5)]
        # Ce scénario vérifie un relevé du soir : les ventes du 7 sont déjà
        # comprises. La fixture générale reste à 16h58 pour les autres tests
        # qui vérifient la conservation exacte de l'heure physique d'origine.
        original_soir = {**self.original, "horodatage": "2026-09-07T17:00:00",
                         "source": {**self.original["source"], "saisi_le": "2026-09-07T17:00:00"}}
        originaux = []
        for code, colis, ancien, nouveau, quantite, attendue in cas:
            originaux.append({**original_soir, "id": f"comptage:2026-09-07:{code}:saisie",
                              "article": code, "article_source": code,
                              "quantite": quantite, "colis": colis, "conditionnement": ancien})
        temoin = {**original_soir, "id": "comptage:2026-09-07:0000000000001:saisie",
                  "article": "0000000000001", "quantite": 17}
        mouvements = [{"id": f"vente:{code}:{jour}", "type": "vente", "article": code,
                       "date_source": jour, "date_effet": jour, "quantite": quantite}
                      for code, *_ in cas for jour, quantite in (("2026-09-07", 2), ("2026-09-08", 3))]
        self.ecrire_faits([*originaux, temoin, *mouvements])
        avant = self.fichier.read_bytes()
        for original, (_, colis, ancien, nouveau, quantite, attendue) in zip(originaux, cas):
            self.original = original
            commande = self.commande("--colis", str(colis), "--ancien-conditionnement", str(ancien),
                                     "--ancienne-quantite", str(quantite))
            commande[3] = str(nouveau)
            resultat = subprocess.run(commande, cwd=self.racine, capture_output=True,
                                      env={**os.environ, "PYTHONIOENCODING": "utf-8"})
            self.assertEqual(resultat.returncode, 0, resultat.stderr)
            self.assertEqual(json.loads(resultat.stdout)["correction"]["quantite"], attendue)
        self.assertTrue(self.fichier.read_bytes().startswith(avant))
        self.assertEqual(len(self.fichier.read_bytes().splitlines()), len(avant.splitlines()) + 3)
        for source in (RACINE / "moteur").glob("*.py"):
            shutil.copy2(source, self.moteur / source.name)
        programme = (
            "import importlib.util,json,sys\n"
            f"sys.path.insert(0, {str(self.moteur)!r})\n"
            f"s=importlib.util.spec_from_file_location('calcul', {str(self.moteur / 'calculer-position.py')!r})\n"
            "m=importlib.util.module_from_spec(s); s.loader.exec_module(m)\n"
            "print(json.dumps(m.calculer(jusqua='2026-09-09')))\n")
        resultat = subprocess.run([sys.executable, "-c", programme], cwd=self.racine, capture_output=True,
                                  env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        self.assertEqual(resultat.returncode, 0, resultat.stderr)
        etat = json.loads(resultat.stdout)
        for code, _, _, _, _, attendue in cas:
            self.assertEqual(etat[code]["position"], attendue - 3)
            self.assertEqual(etat[code]["mesuree_le"], "2026-09-07")
            self.assertEqual(etat[code]["moment_mesure"], "soir")
            self.assertEqual(etat[code]["mouvements_depuis"], 1)
        self.assertEqual(etat[temoin["article"]]["position"], 17)

    def test_cli_simule_sans_ecriture_puis_corrige_la_conversion_seule(self):
        avant = self.instantane()
        simulation = self.lancer("--simuler")
        self.assertEqual(simulation.returncode, 0, simulation.stderr)
        self.assertEqual(self.instantane(), avant)
        simule = json.loads(simulation.stdout)
        self.assertEqual(simule["correction"]["quantite"], -32)
        execution = self.lancer()
        self.assertEqual(execution.returncode, 0, execution.stderr)
        rapport = json.loads(execution.stdout)
        self.assertTrue(rapport["verifie"])
        self.assertEqual(rapport["statut"], "applique")
        apres = self.fichier.read_bytes()
        self.assertTrue(apres.startswith(avant["donnees/faits/2026.jsonl"]))
        lignes = [json.loads(x) for x in apres.decode().splitlines()]
        self.assertEqual(len(lignes), 2)
        self.assertEqual(lignes[0], self.original)
        correction = lignes[1]
        self.assertEqual(correction["id"], simule["correction"]["id"])
        self.assertEqual(correction["cible_id"], self.original["id"])
        self.assertEqual(correction["type"], "correction-comptage")
        self.assertEqual(correction["quantite"], -32)
        self.assertEqual(correction["conditionnement"], 8)
        for champ in ("colis", "horodatage", "date_source", "date_effet", "source", "unite", "article_source"):
            self.assertEqual(correction[champ], self.original[champ], champ)
        self.assertEqual(correction["motif"], MOTIF)
        self.assertEqual(correction["auteur"], "agent-rayon")
        self.assertEqual(correction["conversion_comptage"]["confirmation"], CONFIRMATION)
        self.assertEqual(correction["conversion_comptage"]["avant"]["quantite"], -260)
        for nom in ("agent-rayon", "tout"):
            journal = self.donnees / "journaux" / (nom + ".jsonl")
            trace = json.loads(journal.read_text(encoding="utf-8").strip())
            self.assertEqual(trace["action"], rapport["action"])
            self.assertFalse(trace["annulable"])
            self.assertEqual(trace["details"]["correction_id"], correction["id"])


if __name__ == "__main__":
    unittest.main()
