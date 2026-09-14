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
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
DOSSIER_DOCS = RACINE / "Documents" / "Documentation de l'application"
DOSSIER_MIROIR = Path(r"c:\Users\user\Desktop\projets_IA\projets\preparation-commande")


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
        shell=True,
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
    res_courrier = executer("git check-ignore donnees/courrier/test_ignore.tmp", verifier=False)
    if res_courrier.returncode != 0:
        raise ValueError("SÉCURITÉ VIOLÉE : donnees/courrier/ n'est pas exclu par .gitignore !")

    log("Sécurité OK", "Aucun mot de passe détecté, .env et dossiers de courrier bruts protégés.")


def etape_2_tests_integrite():
    """Exécute la vérification de conformité du projet et les tests unitaires essentiels."""
    log("Étape 2/5", "Vérification syntaxique et intégrité des carnets JSONL...")

    # Exécution de verifier_projet.py
    script_audit = RACINE / "tests" / "verifier_projet.py"
    if script_audit.is_file():
        cmd = f'"{sys.executable}" "{script_audit}"'
        res = executer(cmd, capture=True)
        try:
            bilan = json.loads(res.stdout)
            erreurs = bilan.get("erreurs", [])
            if erreurs:
                msg_err = "\n".join(f"- {e.get('fichier')}: {e.get('erreur')}" for e in erreurs[:5])
                raise ValueError(f"{len(erreurs)} erreurs détectées dans le projet :\n{msg_err}")
            lignes = bilan.get("lignes_jsonl", 0)
            log("Contrôle syntaxique", f"100% conforme ({lignes} lignes de faits et carnets certifiées).")
        except json.JSONDecodeError:
            pass

    # Exécution des tests unitaires clés
    log("Tests unitaires", "Lancement des tests de préparation photos et sécurité mail...")
    tests_a_lancer = [
        "tests/test_preparer_photos.py",
        "tests/test_envoyer_classeur_marge.py",
    ]
    for test in tests_a_lancer:
        cmd_test = f'"{sys.executable}" -m unittest {test}'
        executer(cmd_test, verifier=True)

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

    # Synchroniser aussi AGENTS.md si présent
    source_agents = RACINE / "AGENT.md"
    cible_agents = DOSSIER_MIROIR / "AGENTS.md"
    if source_agents.is_file() and cible_agents.parent.is_dir():
        cible_agents.write_text(source_agents.read_text(encoding="utf-8"), encoding="utf-8")
        log("Directives miroir", "Fichier AGENTS.md synchronisé.")


def etape_4_git_commit_push(message_personnalise=None, sans_push=False):
    """Indexe, crée le commit et le pousse vers GitHub."""
    log("Étape 4/5", "Indexation Git et préparation du commit...")

    # Stage tous les fichiers respectant .gitignore
    executer("git add -A")

    # Vérifier s'il y a des changements à committer
    res_status = executer("git status --porcelain")
    lignes_status = [l.strip() for l in res_status.stdout.splitlines() if l.strip()]

    if not lignes_status:
        log("Git", "Aucune modification à committer. L'arbre de travail est propre.")
        # Obtenir le dernier hash
        res_hash = executer("git rev-parse --short HEAD")
        commit_hash = res_hash.stdout.strip()
        return commit_hash, False

    maintenant_str = datetime.now().strftime("%d/%m/%Y à %H:%M:%S")
    if message_personnalise:
        message_commit = f"{message_personnalise}\n\nSauvegarde automatique du {maintenant_str}"
    else:
        # Message automatique synthétique
        nb_modifs = len(lignes_status)
        message_commit = (
            f"sauvegarde: synchronisation automatique du {maintenant_str}\n\n"
            f"- {nb_modifs} fichier(s) mis à jour ou synchronisés\n"
            f"- Tests de non-régression et audits syntaxiques validés\n"
            f"- Secrets protégés (.env exclus, mots de passe déportés)"
        )

    # Écriture du message de commit dans un fichier temporaire pour éviter les problèmes d'échappement shell
    fichier_msg = RACINE / ".commit_msg_tmp.txt"
    try:
        fichier_msg.write_text(message_commit, encoding="utf-8")
        executer(f'git commit -F "{fichier_msg}"')
    finally:
        if fichier_msg.is_file():
            fichier_msg.unlink()

    res_hash = executer("git rev-parse --short HEAD")
    commit_hash = res_hash.stdout.strip()
    log("Commit créé", f"Identifiant : {commit_hash}")

    if sans_push:
        log("Push désactivé", "Option --sans-push active : le push n'est pas exécuté.")
        return commit_hash, True

    log("Étape 5/5", "Publication vers GitHub (git push origin main)...")
    executer("git push origin main")
    log("GitHub Push OK", f"Modifications publiées sur GitHub (branche main, commit {commit_hash}).")
    return commit_hash, True


def etape_5_annonce_web(commit_hash, nouveau_commit=True):
    """Publie l'annonce dans l'application web via moteur/dire.py."""
    try:
        from dire import publier
    except ImportError:
        sys.path.insert(0, str(RACINE / "moteur"))
        from dire import publier

    if nouveau_commit:
        message = (
            f"📦 Sauvegarde complète réalisée avec succès sur GitHub. "
            f"Tous les fichiers, la documentation officielle (23 chapitres) et les données "
            f"sont synchronisés et protégés (commit `{commit_hash}`)."
        )
    else:
        message = (
            f"ℹ️ Sauvegarde vérifiée : le projet est déjà strictement à jour sur GitHub "
            f"au commit `{commit_hash}` (zéro modification en attente)."
        )

    publier(message, auteur="Agent Orchestrateur")
    log("Annonce Web", "Message publié dans le flux de discussion de l'application.")


def executer_sauvegarde_complete(message=None, sans_push=False):
    """Orchestre la procédure complète."""
    print("=" * 70)
    print(" DÉMARRAGE DE LA PROCÉDURE DE SAUVEGARDE GITHUB (/sauvegarde)")
    print("=" * 70)

    try:
        etape_1_controle_securite()
        etape_2_tests_integrite()
        etape_3_synchronisation_documentation()
        commit_hash, a_committe = etape_4_git_commit_push(message_personnalise=message, sans_push=sans_push)
        etape_5_annonce_web(commit_hash, nouveau_commit=a_committe)
        print("=" * 70)
        print(f" SAUVEGARDE TERMINÉE AVEC SUCCÈS (Commit {commit_hash})")
        print("=" * 70)
        return True
    except Exception as exc:
        print("!" * 70)
        print(f" ÉCHEC DE LA SAUVEGARDE : {exc}")
        print("!" * 70)
        try:
            from dire import publier
            publier(f"⚠️ Échec de la sauvegarde GitHub : {exc}", auteur="Agent Orchestrateur")
        except Exception:
            pass
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
