"""
moteur/sauvegarder.py - Procédure automatique de sauvegarde GitHub (/sauvegarde)

Ce script réalise l'ensemble de la chaîne de sauvegarde sécurisée :
1. Contrôle anti-fuite de secrets (vérification .env, mot de passe vide dans courrier-config.json, exclusion de donnees/courrier/)
2. Contrôle de cohérence et tests d'intégrité (tests/verifier_projet.py et tests unitaires clés)
3. Synchronisation de la documentation officielle vers l'espace de travail miroir
4. Indexation Git (git add -A) et commit horodaté
5. Publication vers GitHub (git push origin main)
6. Publication de l'annonce dans l'application web (moteur/dire.py)

Usage :
  python moteur/sauvegarder.py
  python moteur/sauvegarder.py --message "feat: mise à jour des photos et du courrier"
  python moteur/sauvegarder.py --sans-push
"""
import argparse
import json
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
DOSSIER_DOCS = RACINE / "Documents" / "Documentation de l'application"
DOSSIER_MIROIR = Path(r"c:\Users\user\Desktop\projets_IA\projets\preparation-commande")
FICHIERS_PRIVES = {
    "donnees/.sentinelle-evenements.json",
    "donnees/.courrier_uids_connus.json",
    "donnees/.operations-bail.lock",
}


def log(titre, message=""):
    """Affichage console lisible et horodaté."""
    prefixe = f"[SAUVEGARDE {datetime.now().strftime('%H:%M:%S')}]"
    if message:
        print(f"{prefixe} {titre} : {message}")
    else:
        print(f"{prefixe} {titre}")


def executer(commande, cwd=RACINE, verifier=True, capture=True):
    """Exécute une commande shell de manière contrôlée."""
    resultat = subprocess.run(
        commande,
        cwd=cwd,
        shell=isinstance(commande, str),
        capture_output=capture,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if verifier and resultat.returncode != 0:
        err = (resultat.stderr or resultat.stdout or "").strip()
        raise RuntimeError(f"Échec de la commande '{commande}' (code {resultat.returncode}) :\n{err}")
    return resultat


def etape_1_controle_securite():
    """Vérifie strictement qu'aucun secret ne peut être exposé sur Git."""
    log("Étape 1/5", "Contrôles de sécurité et anti-fuite de secrets...")

    # 1. Vérifier donnees/courrier-config.json
    config_file = RACINE / "donnees" / "courrier-config.json"
    if config_file.is_file():
        try:
            cfg = json.loads(config_file.read_text(encoding="utf-8-sig"))
            mot_de_passe = cfg.get("mot_de_passe", "")
            if mot_de_passe:
                raise ValueError(
                    "SÉCURITÉ VIOLÉE : un mot de passe en clair est présent dans donnees/courrier-config.json ! "
                    "Le mot de passe DOIT être vidé et placé uniquement dans le fichier local .env."
                )
        except json.JSONDecodeError as exc:
            raise ValueError(f"Erreur de lecture de donnees/courrier-config.json : {exc}")

    # 2. Vérifier que .env est bien ignoré par Git
    res_env = executer("git check-ignore .env", verifier=False)
    if res_env.returncode != 0:
        raise ValueError("SÉCURITÉ VIOLÉE : .env n'est pas exclu par .gitignore !")

    # 3. Vérifier que donnees/courrier/ est bien ignoré
    res_courrier = executer(["git", "check-ignore", "--no-index", "donnees/courrier/controle-confidentialite.eml"], verifier=False)
    if res_courrier.returncode != 0:
        raise ValueError("SÉCURITÉ VIOLÉE : donnees/courrier/ n'est pas exclu par .gitignore !")

    for chemin in sorted(FICHIERS_PRIVES):
        if executer(["git", "check-ignore", "--no-index", chemin], verifier=False).returncode != 0:
            raise ValueError(f"SÉCURITÉ : trace privée non exclue de Git : {chemin}.")

    verifier_index_prive()
    log("Sécurité OK", "Mot de passe absent ; fichiers privés exclus de l'index Git courant.")


def verifier_index_prive():
    """L'exclusion d'un nouveau fichier ne protège pas les fichiers déjà suivis."""
    suivis = executer(["git", "ls-files", "-z"]).stdout.split("\0")
    prives = [nom for nom in suivis if nom.rsplit("/", 1)[-1] == ".env"
              or nom.startswith("donnees/courrier/") or nom in FICHIERS_PRIVES]
    if prives:
        raise ValueError(f"SÉCURITÉ : {len(prives)} fichier(s) privé(s) restent suivis/indexés par Git. "
                         "Retirer leur suivi en conservant les originaux locaux avant sauvegarde.")


def etape_2_tests_integrite():
    """Exécute la vérification de conformité du projet et les tests unitaires essentiels."""
    log("Étape 2/5", "Vérification syntaxique et intégrité des carnets JSONL...")

    # Exécution de verifier_projet.py
    script_audit = RACINE / "tests" / "verifier_projet.py"
    if not script_audit.is_file():
        raise ValueError("Le programme de contrôle syntaxique est absent ; sauvegarde interrompue.")
    res = executer([sys.executable, "-B", str(script_audit)], capture=True)
    try:
        bilan = json.loads(res.stdout)
        erreurs = bilan.get("erreurs", [])
        if erreurs:
            msg_err = "\n".join(f"- {e.get('fichier')}: {e.get('erreur')}" for e in erreurs[:5])
            raise ValueError(f"{len(erreurs)} erreurs détectées dans le projet :\n{msg_err}")
        lignes = bilan.get("lignes_jsonl", 0)
        log("Contrôle syntaxique", f"Aucune erreur de syntaxe ({lignes} lignes JSONL lues).")
    except json.JSONDecodeError as exc:
        raise ValueError("Le contrôle syntaxique n'a pas fourni de bilan JSON valide.") from exc

    # Exécution des tests unitaires clés
    log("Tests unitaires", "Lancement des tests de préparation photos et sécurité mail...")
    tests_a_lancer = [
        "tests/test_preparer_photos.py",
        "tests/test_envoyer_classeur_marge.py",
    ]
    executer([sys.executable, "-B", str(RACINE / "tests" / "lancer_tests_isoles.py"), *tests_a_lancer], verifier=True)

    log("Tests OK", "Tous les tests de conformité ont réussi avec succès.")


def etape_3_synchronisation_documentation():
    """Synchronise la documentation vers l'espace miroir si présent."""
    log("Étape 3/5", "Synchronisation de la documentation et des directives...")
    if not DOSSIER_MIROIR.is_dir():
        log("Miroir", "Aucun dossier miroir secondaire détecté, poursuite normale.")
        return

    miroir_docs = DOSSIER_MIROIR / "Documents" / "Documentation de l'application"
    if miroir_docs.parent.is_dir():
        cmd_sync = f'robocopy "{DOSSIER_DOCS}" "{miroir_docs}" /E /NDL /NFL /NJH /NJS /nc /ns /np'
        # robocopy retourne < 8 pour succès
        res = executer(cmd_sync, verifier=False)
        if res.returncode < 8:
            log("Documentation miroir", f"Synchronisée vers {miroir_docs}")
        else:
            log("Avertissement miroir", f"Code retour robocopy : {res.returncode}")

    # Synchroniser aussi Presentation de l'application si présent
    source_pres = RACINE / "Documents" / "Presentation de l'application"
    miroir_pres = DOSSIER_MIROIR / "Documents" / "Presentation de l'application"
    if source_pres.is_dir() and miroir_pres.parent.is_dir():
        cmd_sync_pres = f'robocopy "{source_pres}" "{miroir_pres}" /E /NDL /NFL /NJH /NJS /nc /ns /np'
        res_pres = executer(cmd_sync_pres, verifier=False)
        if res_pres.returncode < 8:
            log("Présentation miroir", f"Synchronisée vers {miroir_pres}")
        else:
            log("Avertissement miroir présentation", f"Code retour robocopy : {res_pres.returncode}")

    # Synchroniser aussi AGENTS.md si présent
    source_agents = RACINE / "AGENTS.md"
    cible_agents = DOSSIER_MIROIR / "AGENTS.md"
    if source_agents.is_file() and cible_agents.parent.is_dir():
        cible_agents.write_text(source_agents.read_text(encoding="utf-8"), encoding="utf-8")
        log("Directives miroir", "Fichier AGENTS.md synchronisé.")


def etape_4_git_commit_push(message_personnalise=None, sans_push=False):
    """Distingue commit local et publication vérifiée de cette même branche."""
    branche = executer(["git", "branch", "--show-current"]).stdout.strip()
    if branche != "main":
        raise ValueError("La sauvegarde automatique publie main : revenir explicitement sur main avant de sauvegarder.")
    verifier_index_prive()
    executer(["git", "add", "-A"])
    verifier_index_prive()
    statut = executer(["git", "diff", "--cached", "--quiet"], verifier=False)
    if statut.returncode not in (0, 1):
        raise RuntimeError("Impossible de vérifier les changements indexés.")
    nouveau_commit = statut.returncode == 1
    if nouveau_commit:
        instant = datetime.now().strftime("%d/%m/%Y à %H:%M:%S")
        message = (message_personnalise or "sauvegarde: synchronisation du projet") + f"\n\nSauvegarde vérifiée du {instant}"
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".txt", delete=False) as flux:
            flux.write(message)
            fichier_msg = Path(flux.name)
        try:
            executer(["git", "commit", "-F", str(fichier_msg)])
        finally:
            fichier_msg.unlink(missing_ok=True)
    commit_complet = executer(["git", "rev-parse", "HEAD"]).stdout.strip()
    resultat = {"commit": commit_complet[:12], "nouveau_commit": nouveau_commit,
                "branche": branche, "publication_demandee": not sans_push,
                "publication_confirmee": False}
    if sans_push:
        log("Sauvegarde locale", "Publication non demandée (--sans-push).")
        return resultat
    # Même sans nouveau commit, une sauvegarde précédente peut attendre son push.
    executer(["git", "push", "origin", "HEAD:refs/heads/main"])
    distant = executer(["git", "ls-remote", "origin", "refs/heads/main"]).stdout.split()
    if not distant or distant[0] != commit_complet:
        raise RuntimeError("Push exécuté, mais la branche distante ne confirme pas le commit local ; vérifier GitHub.")
    resultat["publication_confirmee"] = True
    log("Publication confirmée", f"Branche {branche}, commit {resultat['commit']}.")
    return resultat


def etape_5_annonce_web(resultat):
    """Publie uniquement le niveau de sauvegarde réellement vérifié."""
    sys.path.insert(0, str(RACINE / "moteur"))
    from dire import publier
    if resultat["publication_confirmee"]:
        message = (f"📦 Sauvegarde publiée et vérifiée sur GitHub : branche {resultat['branche']}, "
                   f"commit `{resultat['commit']}`. Le courrier privé et les secrets restent locaux.")
    else:
        message = (f"📦 Sauvegarde locale vérifiée : commit `{resultat['commit']}`. "
                   "Publication GitHub non demandée ; aucune synchronisation distante confirmée.")
    publier(message, auteur="Leader")
    log("Annonce Web", "Message publié dans l'application.")


def executer_sauvegarde_complete(message=None, sans_push=False):
    """Orchestre la procédure complète."""
    print("=" * 70)
    print(" DÉMARRAGE DE LA PROCÉDURE DE SAUVEGARDE GITHUB (/sauvegarde)")
    print("=" * 70)

    try:
        etape_1_controle_securite()
        etape_2_tests_integrite()
        etape_3_synchronisation_documentation()
        resultat = etape_4_git_commit_push(message_personnalise=message, sans_push=sans_push)
        etape_5_annonce_web(resultat)
        print("=" * 70)
        print(f" SAUVEGARDE TERMINÉE AVEC SUCCÈS (Commit {resultat['commit']})")
        print("=" * 70)
        return True
    except Exception as exc:
        print("!" * 70)
        print(f" ÉCHEC DE LA SAUVEGARDE : {exc}")
        print("!" * 70)
        try:
            from dire import publier
            publier(f"⚠️ Sauvegarde interrompue ({type(exc).__name__}). "
                    "Consulter le compte rendu technique local avant de conclure sur sa publication.",
                    auteur="Leader")
        except Exception as publication:
            print(f"L'annonce d'échec n'a pas pu être publiée : {type(publication).__name__}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(description="Procédure automatique de sauvegarde GitHub (/sauvegarde).")
    parser.add_argument("--message", "-m", type=str, default=None, help="Message de commit personnalisé.")
    parser.add_argument("--sans-push", action="store_true", help="Effectuer les vérifications et le commit sans pousser vers GitHub.")
    args = parser.parse_args()

    succes = executer_sauvegarde_complete(message=args.message, sans_push=args.sans_push)
    sys.exit(0 if succes else 1)


if __name__ == "__main__":
    main()
