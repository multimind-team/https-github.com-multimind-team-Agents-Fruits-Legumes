import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

MOTEUR = Path(__file__).resolve().parents[1] / "moteur"
sys.path.insert(0, str(MOTEUR))

from courrier_pipeline import actions_a_executer, classer_fichier, commandes_a_lancer, ranger_pieces_jointes


class ClasserFichierTests(unittest.TestCase):
    def test_reconnait_les_fichiers_du_matin(self):
        self.assertEqual(classer_fichier("Vente-07.09.2026.xlsx"), "mouvement")
        self.assertEqual(classer_fichier("Casse-07.09.2026.xlsx"), "mouvement")
        self.assertEqual(classer_fichier("Dons-07.09.2026.xlsx"), "mouvement")
        self.assertEqual(classer_fichier("Livraison-07.09.2026.xlsx"), "mouvement")
        self.assertEqual(classer_fichier("Cadencier-Webtelevente-07.09.2026.xls"), "cadencier")

    def test_ne_confond_pas_une_facture_directe_avec_un_export_magasin(self):
        self.assertEqual(classer_fichier("Facture-TerreAzur-123.pdf"), "facture-directe")
        self.assertEqual(classer_fichier("Pomona-07.09.2026.jpg"), "facture-directe")
        self.assertEqual(classer_fichier("Prospectus-Intermarche-08-09-2026.pdf"), "promo-intermarche")
        self.assertEqual(classer_fichier("inconnu.xlsx"), "inconnu")

    def test_reconnait_les_noms_de_documents_avec_prefixe_technique(self):
        self.assertEqual(
            classer_fichier("doc_e41d548001d0_cadencier webtelevente 07.09.2026.xls"),
            "cadencier",
        )
        self.assertEqual(
            classer_fichier("doc_fc097015aa52_vente 07.09.2026.xlsx"),
            "mouvement",
        )


class RangerPiecesJointesTests(unittest.TestCase):
    def test_index_interrompu_ou_invalide_refuse_sans_ajouter_de_lignes(self):
        for contenu in (b'{"sha256":', b'[]\n', b'{}\n'):
            with self.subTest(contenu=contenu), tempfile.TemporaryDirectory() as tmp:
                racine = Path(tmp)
                source = racine / "Vente-07.09.2026.xlsx"
                source.write_bytes(b"fixture")
                index = racine / "donnees/courrier/index.jsonl"
                index.parent.mkdir(parents=True)
                index.write_bytes(contenu)
                with self.assertRaisesRegex(ValueError, "Index courrier invalide"):
                    ranger_pieces_jointes(racine, "mail", "2026-09-07", "pdv", [source])
                self.assertEqual(index.read_bytes(), contenu)

    def test_index_termine_sans_saut_de_ligne_reste_append_only_a_la_reprise(self):
        with tempfile.TemporaryDirectory() as tmp:
            racine = Path(tmp)
            vente = racine / "Vente-07.09.2026.xlsx"
            vente.write_bytes(b"vente fixture")
            ranger_pieces_jointes(racine, "mail", "2026-09-07", "pdv", [vente])
            index = racine / "donnees/courrier/index.jsonl"
            avant = index.read_bytes().rstrip(b"\r\n")
            index.write_bytes(avant)  # Interruption fixture entre le JSON et le séparateur.
            ranger_pieces_jointes(racine, "mail", "2026-09-07", "pdv", [vente])
            self.assertEqual(index.read_bytes(), avant)
            livraison = racine / "Livraison-07.09.2026.xlsx"
            livraison.write_bytes(b"livraison fixture")
            ranger_pieces_jointes(racine, "suite", "2026-09-07", "pdv", [livraison])
            self.assertTrue(index.read_bytes().startswith(avant))
            self.assertEqual(len(index.read_bytes().splitlines()), 2)
            for ligne in index.read_text(encoding="utf-8").splitlines():
                self.assertIsInstance(json.loads(ligne), dict)

    def test_simulation_deux_pieces_identiques_ne_lit_pas_une_copie_non_creee(self):
        with tempfile.TemporaryDirectory() as tmp:
            racine = Path(tmp)
            source = racine / "Vente-07.09.2026.xlsx"
            source.write_bytes(b"fixture")
            try:
                resultat = ranger_pieces_jointes(racine, "mail", "2026-09-07", "pdv",
                                                 [source, source], simuler=True)
            except ValueError as erreur:
                self.fail(f"La simulation ne doit pas chercher une copie physique : {erreur}")
            self.assertEqual(resultat["nouveaux"], 1)
            self.assertEqual(resultat["doublons"], 1)
            self.assertEqual(len(resultat["fichiers"]), 1)
            self.assertFalse((racine / "donnees").exists())

    def test_reprise_apres_copie_interrompue_avant_indexation(self):
        with tempfile.TemporaryDirectory() as tmp:
            racine = Path(tmp)
            source = racine / "Vente-07.09.2026.xlsx"
            source.write_bytes(b"export fixture")

            def copier_puis_interrompre(depart, arrivee):
                Path(arrivee).write_bytes(Path(depart).read_bytes())
                raise OSError("interruption apres copie")

            with patch("courrier_pipeline.shutil.copy2", side_effect=copier_puis_interrompre):
                with self.assertRaises(OSError):
                    ranger_pieces_jointes(racine, "mail", "2026-09-07", "pdv", [source])
            reprise = ranger_pieces_jointes(racine, "mail", "2026-09-07", "pdv", [source])
            destination = racine / "donnees/courrier/2026-09-07-pdv" / source.name
            self.assertEqual(reprise["fichiers"], [str(destination)])
            index = racine / "donnees/courrier/index.jsonl"
            self.assertEqual(len(index.read_text(encoding="utf-8").splitlines()), 1)
            avant = index.read_bytes()
            ranger_pieces_jointes(racine, "mail", "2026-09-07", "pdv", [source])
            self.assertEqual(index.read_bytes(), avant)

    def test_range_les_pieces_et_ignore_le_meme_fichier_du_meme_mail(self):
        with tempfile.TemporaryDirectory() as tmp:
            racine = Path(tmp)
            source = racine / "source"
            source.mkdir()
            vente = source / "Vente-07.09.2026.xlsx"
            vente.write_bytes(b"export magasin")
            facture = source / "Facture-TerreAzur-123.pdf"
            facture.write_bytes(b"facture directe")

            premier = ranger_pieces_jointes(
                racine, "<mail-123@example.test>", "2026-09-07", "pdv11768", [vente, facture]
            )
            self.assertEqual(premier["nouveaux"], 2)
            self.assertEqual(premier["doublons"], 0)
            self.assertEqual(premier["classes"], {"mouvement": 1, "facture-directe": 1})
            self.assertTrue(all(Path(p).exists() for p in premier["fichiers"]))

            second = ranger_pieces_jointes(
                racine, "<mail-123@example.test>", "2026-09-07", "pdv11768", [vente, facture]
            )
            self.assertEqual(second["nouveaux"], 0)
            self.assertEqual(second["doublons"], 2)

            index = racine / "donnees" / "courrier" / "index.jsonl"
            lignes = index.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lignes), 2)
            self.assertIn(hashlib.sha256(vente.read_bytes()).hexdigest(), lignes[0])

    def test_range_un_prospectus_intermarche_dans_le_dossier_promo(self):
        with tempfile.TemporaryDirectory() as tmp:
            racine = Path(tmp)
            source = racine / "source"
            source.mkdir()
            prospectus = source / "Prospectus-Intermarche-08-09-2026.pdf"
            prospectus.write_bytes(b"prospectus")

            resultat = ranger_pieces_jointes(
                racine, "<promo@example.test>", "2026-09-06", "intermarche", [prospectus]
            )

            destination = racine / "Documents" / "Promo intermarche" / prospectus.name
            self.assertEqual(resultat["classes"], {"promo-intermarche": 1})
            self.assertEqual(resultat["fichiers"], [str(destination)])
            self.assertTrue(destination.exists())

    def test_collision_prospectus_reste_en_promotions_avec_nom_utilisable(self):
        with tempfile.TemporaryDirectory() as tmp:
            racine = Path(tmp)
            source = racine / "doc_e41d548001d0_Prospectus-Intermarche.pdf"
            source.write_bytes(b"premiere edition")
            premier = ranger_pieces_jointes(racine, "mail-1", "2026-09-07", "pdv", [source])
            source.write_bytes(b"seconde edition")
            second = ranger_pieces_jointes(racine, "mail-2", "2026-09-07", "pdv", [source])
            cible = Path(second["fichiers"][0])
            self.assertEqual(cible.parent, racine / "Documents/Promo intermarche")
            self.assertEqual(cible.name, "Prospectus-Intermarche-2.pdf")
            self.assertEqual(Path(premier["fichiers"][0]).read_bytes(), b"premiere edition")
            self.assertEqual(cible.read_bytes(), b"seconde edition")

    def test_retire_le_prefixe_technique_au_rangement(self):
        with tempfile.TemporaryDirectory() as tmp:
            racine = Path(tmp)
            source = racine / "doc_e41d548001d0_cadencier webtelevente 07.09.2026.xls"
            source.write_bytes(b"cadencier")

            resultat = ranger_pieces_jointes(
                racine, "<mail-123@example.test>", "2026-09-07", "pdv11768", [source]
            )

            destination = racine / "donnees/courrier/2026-09-07-pdv11768/cadencier webtelevente 07.09.2026.xls"
            self.assertEqual(resultat["classes"], {"cadencier": 1})
            self.assertEqual(resultat["fichiers"], [str(destination)])
            self.assertTrue(destination.exists())


class ActionsCourrierTests(unittest.TestCase):
    def test_planifie_l_integration_et_le_recalcul_pour_un_export_magasin(self):
        self.assertEqual(
            actions_a_executer({"mouvement": 3, "cadencier": 1, "facture-directe": 1}, nouveaux=5),
            ["integrer", "cadencier", "recalculer", "note", "facture-directe"],
        )

    def test_rangement_deja_fait_ne_prouve_pas_le_succes_de_l_import(self):
        self.assertEqual(actions_a_executer({"mouvement": 1}, nouveaux=0),
                         ["integrer", "recalculer", "note"])

    def test_construit_uniquement_les_commandes_connues(self):
        racine = Path("C:/rayon")
        dossier = racine / "donnees/courrier/2026-09-07-pdv"
        self.assertEqual(
            commandes_a_lancer(racine, dossier, ["integrer", "cadencier", "recalculer", "note"],
                              fichiers=[dossier / "cadencier webtelevente 07.09.2026.xls"]),
            [
                ["py", "-3.14", str(racine / "moteur/integrer-fichiers.py"), str(dossier), "--agent", "agent-donnees", "--json"],
                ["py", "-3.14", str(racine / "moteur/cadencier-du-jour.py"), str(dossier / "cadencier webtelevente 07.09.2026.xls")],
                ["py", "-3.14", str(racine / "moteur/analyser-marges-mercuriale.py")],
                ["py", "-3.14", str(racine / "moteur/filet-de-securite.py"), "--forcer"],
                ["py", "-3.14", str(racine / "moteur/note-du-matin.py")],
            ],
        )


class TraiterCourrierCliTests(unittest.TestCase):
    def test_simulation_planifie_sans_ranger_ni_ecrire_dans_le_projet(self):
        with tempfile.TemporaryDirectory() as tmp:
            racine = Path(tmp)
            source = racine / "Vente-07.09.2026.xlsx"
            source.write_bytes(b"export magasin")
            resultat = subprocess.run(
                [sys.executable, str(MOTEUR / "traiter-courrier.py"), "--racine", str(racine), "--simuler",
                 "--mail-id", "<test@example>", "--date", "2026-09-07", "--expediteur", "pdv",
                 str(source)],
                capture_output=True, text=True, encoding="utf-8", check=True,
            )
            sortie = json.loads(resultat.stdout)
            self.assertEqual(sortie["actions"], ["integrer", "recalculer", "note"])
            self.assertEqual(sortie["resultats"][0]["sortie"], "SIMULATION")
            self.assertFalse((racine / "donnees/courrier/index.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
