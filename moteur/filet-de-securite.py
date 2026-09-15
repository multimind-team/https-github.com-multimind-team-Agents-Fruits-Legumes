"""
Le filet de sécurité — la commande doit pouvoir être passée, agent ou pas.

Règle donnée par le responsable de rayon le 2026-09-03 :

  « Normalement ça ne devrait pas arriver, mais si l'agent ne répond pas, on
    doit pouvoir passer la commande quand même. »

À 9h25, il n'y a pas de deuxième chance : la commande part à 9h30. Un agent qui
n'a pas tourné, une machine qui a redémarré, une coupure de réseau — rien de
tout ça ne doit laisser le responsable de rayon devant un écran vide.

Ce programme est donc volontairement BÊTE. Il ne comprend rien, ne décide rien,
ne corrige rien : il enchaîne les calculs pour qu'une proposition existe. Toute
l'intelligence (lire les mails, repérer les codes jumeaux, écrire la note) reste
le travail des agents. Lui, il garantit le minimum vital.

C'est justement parce qu'il est bête qu'on peut compter dessus : il n'a aucune
raison de se bloquer sur un cas qu'il n'avait pas prévu.

Trois principes :

  1. Il ne s'arrête JAMAIS en laissant l'écran vide. Si un calcul échoue, il
     garde la proposition précédente et le dit en clair.
  2. Il dit toujours l'ÂGE de ce qu'il montre. Une proposition d'hier n'est pas
     une erreur — la cacher, si.
  3. Il ne touche à rien d'autre. Aucune décision, aucun réglage, aucun article.

Usage :
  python moteur/filet-de-securite.py            vérifie, et recalcule s'il faut
  python moteur/filet-de-securite.py --forcer   recalcule dans tous les cas
  python moteur/filet-de-securite.py --verifier ne fait que dire l'état
"""
import argparse
import json
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

MOTEUR = Path(__file__).resolve().parent
sys.path.insert(0, str(MOTEUR))
import journal_agents
from ecriture_derivee import ecrire_json, publier_etat_calcul
from verrou_donnees import environnement_verrou, operation_donnees

RACINE = MOTEUR.parent
PROPOSITION = RACINE / "donnees" / "proposition.json"
# La fraîcheur vit dans SON PROPRE fichier, et pas dans la proposition.
# Raison : generer-proposition.py réécrit proposition.json en entier à chaque
# calcul. Le 3 septembre 2026, un simple recalcul a donc effacé l'avertissement
# que le filet venait d'écrire, et l'écran s'est remis à dire « fraîcheur non
# vérifiée » alors qu'elle venait de l'être. Deux programmes ne doivent pas
# écrire dans le même fichier.
FRAICHEUR = RACINE / "donnees" / "fraicheur.json"

# Dans l'ordre. Chacun ne dépend que du précédent.
#
# cadencier-du-jour.py AVANT generer-proposition.py : sans lui, la liste des
# articles commandables resterait celle du dernier cadencier lu à la main, même
# si un nouveau vient d'arriver par mail. Le responsable de rayon, 2026-09-04 : « quand le
# cadencier Webtelevente est reçu, on met à jour la liste des produits, ceux
# qui étaient masqués restent masqués » — un article absent aujourd'hui doit
# pouvoir revenir dès que le cadencier le propose de nouveau. Si aucun nouveau
# cadencier n'est arrivé, ce script échoue proprement et generer-proposition.py
# retombe sur ce qu'il connaît déjà (voir son propre code) : l'écran ne reste
# jamais vide pour autant.
ETAPES = [
    ("agregats.py", "ce qu'on sait de chaque article"),
    ("calculer-position.py", "les positions du jour"),
    ("cadencier-du-jour.py", "la liste des articles commandables aujourd'hui"),
    ("generer-proposition.py", "la proposition de commande"),
    ("preparer-liste-comptage.py", "la liste pour le comptage du soir"),
]

JOURS_FERIES_FERMETURE = {"01-01", "05-01", "12-25"}

HEURE_LIMITE_COMMANDE = (9, 30)


def jour_de_commande(aujourdhui=None, maintenant=None):
    """Le prochain jour où une commande se passe : ni dimanche, ni jour de
    fermeture. Après 9 h 30, la commande du jour est close : on vise le
    prochain jour ouvré."""
    maintenant = maintenant or datetime.now()
    jour = aujourdhui or maintenant.date()
    if (jour == maintenant.date() and
            (maintenant.hour, maintenant.minute) >= HEURE_LIMITE_COMMANDE):
        jour += timedelta(days=1)
    fichier_feries = RACINE / "donnees" / "ouverture-jours-feries.json"
    jours_feries = json.loads(fichier_feries.read_text(encoding="utf-8")).get("jours", {}) if fichier_feries.exists() else {}
    fermetures = {iso for iso, entree in jours_feries.items() if entree.get("statut") == "ferme"}
    for _ in range(10):
        if (jour.weekday() != 6 and jour.strftime("%m-%d") not in JOURS_FERIES_FERMETURE
                and jour.isoformat() not in fermetures):
            return jour.isoformat()
        jour += timedelta(days=1)
    return (aujourdhui or date.today()).isoformat()


def etat_proposition():
    """L'âge de ce qui est affiché. Renvoie (etat, message, contenu)."""
    if not PROPOSITION.exists():
        return "absente", "Aucune proposition n'existe. L'écran de commande serait vide.", None
    try:
        contenu = json.loads(PROPOSITION.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as erreur:
        return "illisible", f"La proposition existe mais ne peut pas être lue : {erreur}", None

    attendu = jour_de_commande()
    trouve = contenu.get("date_commande")
    lignes = len(contenu.get("lignes") or [])

    if not lignes:
        return "vide", "La proposition ne contient aucun article.", contenu
    # Le maximum des mouvements ne prouve pas les sorties des autres
    # articles. Les sorties couvertes sont vérifiées article par article par
    # le générateur ; un ancien fichier sans cette preuve reste conservateur.
    reference = contenu.get("date_stock_verifiee")
    if not reference:
        reperes = [contenu.get("date_stock"), contenu.get("date_reference")]
        reference = min((r for r in reperes if r), default="")
    hier = (date.today() - timedelta(days=1)).isoformat()
    if not reference or reference < hier:
        # Une couverture consécutive indique le premier jour à vérifier pour
        # CET article. Ni la date du dernier import ni une livraison ne comble
        # le trou ; on ne prétend pas non plus que le fichier n'a pas été reçu.
        debuts = sorted({
            (date.fromisoformat(l["sorties_couvertes_jusquau"]) + timedelta(days=1)).isoformat()
            for l in contenu.get("lignes", []) if not l.get("masque")
            and l.get("sorties_couvertes_jusquau")
            and l["sorties_couvertes_jusquau"] < hier
        })
        ventes = contenu.get("date_reference")
        if debuts and ventes and ventes < hier:
            # La statistique seule ne suffit pas : il faut une position dont
            # les sorties ne sont pas couvertes. Les trous plus anciens sont
            # conservés par article dans la proposition, pas dans le bandeau.
            debut = max(debuts[0], (date.fromisoformat(ventes) + timedelta(days=1)).isoformat())
            periode = date.fromisoformat(debut).strftime("%d/%m")
            if debut != hier:
                periode += " au " + date.fromisoformat(hier).strftime("%d/%m")
            message = (f"Ventes du {periode} non intégrées. "
                       f"Les dernières ventes intégrées sont celles du {date.fromisoformat(ventes).strftime('%d/%m')}. "
                       f"Vérifie l'intégration du fichier des ventes du {periode}.")
        elif debuts:
            message = ("Fichier des ventes à vérifier. Certaines positions ne couvrent pas toutes les ventes "
                       f"depuis le {date.fromisoformat(debuts[0]).strftime('%d/%m')}. "
                       "Vérifie les journées couvertes par le fichier des ventes et son intégration.")
        else:
            message = (f"Les sorties du stock ne sont vérifiées que jusqu'au {reference or 'jour inconnu'}. "
                       "Vérifie les dates du fichier des ventes et son intégration.")
        return "donnees-en-retard", message, contenu
    if trouve == attendu:
        return "a-jour", f"Proposition du {trouve}, {lignes} articles.", contenu
    return "perimee", (f"La proposition affichée est celle du {trouve}, "
                       f"alors qu'on commande pour le {attendu}."), contenu


def lancer(script):
    """Lance un calcul. Renvoie (réussi, ce qui s'est dit)."""
    resultat = subprocess.run([sys.executable, str(MOTEUR / script)],
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=900,
                              env=environnement_verrou(PROPOSITION.parent))
    sortie = (resultat.stdout or "") + (resultat.stderr or "")
    return resultat.returncode == 0, sortie.strip()


def marquer_fraicheur(etat, message, echecs):
    """Écrit ce qu'il faut penser de la proposition. L'écran de commande le lit
    pour prévenir le responsable de rayon — une proposition vieille reste utilisable, mais il
    doit le savoir."""
    try:
        genere_le = json.loads(PROPOSITION.read_text(encoding="utf-8")).get("genere_le")
    except (json.JSONDecodeError, OSError):
        genere_le = None
    ecrire_json(FRAICHEUR, {
        "_lisez_moi": ("Ce qu'il faut penser de la proposition affichée. Ecrit par "
                       "filet-de-securite.py, lu par l'ecran de commande. Fichier "
                       "separe expres : proposition.json est reecrit a chaque calcul."),
        "etat": etat,
        "message": message,
        "verifie_le": datetime.now().isoformat(timespec="seconds"),
        "jour_de_commande_attendu": jour_de_commande(),
        # Sert à savoir si la vérification porte encore sur la proposition
        # affichée, ou si un recalcul est passé depuis.
        "proposition_generee_le": genere_le,
        "calculs_en_echec": echecs,
    })


@operation_donnees(lambda: PROPOSITION.parent)
def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--forcer", action="store_true", help="recalculer dans tous les cas")
    p.add_argument("--verifier", action="store_true", help="ne rien recalculer, juste dire l'état")
    args = p.parse_args()

    etat, message, _ = etat_proposition()
    print(f"État : {etat}")
    print(f"       {message}")

    if args.verifier:
        return 0 if etat == "a-jour" else 1

    if etat == "a-jour" and not args.forcer:
        marquer_fraicheur(etat, message, [])
        print("\nRien à faire : la commande peut être passée.")
        return 0

    print("\nRecalcul :")
    publier_etat_calcul(PROPOSITION.parent, "en-cours", "filet-de-securite")
    echecs = []
    for script, quoi in ETAPES:
        print(f"  {quoi:42}", end=" ", flush=True)
        try:
            reussi, sortie = lancer(script)
        except subprocess.TimeoutExpired:
            reussi, sortie = False, "le calcul a dépassé 15 minutes"
        if reussi:
            print("fait")
        else:
            print("ÉCHEC")
            echecs.append({"calcul": script, "quoi": quoi,
                           "erreur": sortie[-600:] if sortie else "sans message"})
            journal_agents.echec("filet-de-securite",
                                 f"Le calcul « {quoi} » a échoué",
                                 details={"script": script, "sortie": sortie[-2000:]})
            if script in {"agregats.py", "calculer-position.py", "generer-proposition.py"}:
                # Ne pas fabriquer une proposition datée du jour à partir
                # d'un mélange d'anciens et de nouveaux fichiers dérivés.
                break

    etat, message, _ = etat_proposition()
    if echecs:
        etat = "calcul-incomplet"
        message = ("Recalcul incomplet : " + ", ".join(e["calcul"] for e in echecs)
                   + ". Les fichiers déjà publiés restent disponibles ; le lot complet n'est pas confirmé. " + message)
    marquer_fraicheur(etat, message, echecs)
    publier_etat_calcul(PROPOSITION.parent, "echec" if echecs else "termine",
                       "filet-de-securite", message if echecs else "")

    print()
    if etat == "a-jour" and not echecs:
        print("La proposition est à jour. La commande peut être passée.")
    elif etat == "calcul-incomplet":
        print(message)
        print("Vérifier les articles avant de commander ; le recalcul n'est pas déclaré réussi.")
    elif etat == "donnees-en-retard":
        print("Les calculs ont bien tourné, mais il manque des données.")
        print(f"  {message}")
        print("  La commande peut être passée : la proposition affichée reste la")
        print("  meilleure possible avec ce qu'on sait. Elle ignore simplement les")
        print("  ventes et les livraisons des jours manquants.")
    elif etat in ("perimee", "vide"):
        # Le pire cas, et celui qui compte : on ne bloque pas, on prévient.
        print("ATTENTION — la proposition n'a pas pu être mise à jour.")
        print(f"  {message}")
        print("  L'écran de commande l'affiche quand même, avec un avertissement :")
        print("  une proposition vieille vaut mieux que pas de proposition à 9h25.")
        print("  À vérifier article par article avant de commander.")
    else:
        print("ATTENTION — il n'y a aucune proposition affichable.")
        print("  Il faut passer la commande comme avant preparation-commande, à la main,")
        print("  en s'appuyant sur la tablette Webtelevente.")

    journal_agents.enregistrer(
        agent="filet-de-securite",
        message=f"Vérification avant commande : {etat}",
        motif=("La commande doit pouvoir être passée même si aucun agent n'a tourné. "
               "Ce contrôle ne comprend rien et ne décide rien : il garantit qu'une "
               "proposition existe, et dit son âge."),
        details={"etat": etat, "message": message, "echecs": echecs},
        annulable=False,
    )
    return 0 if etat == "a-jour" else 1


if __name__ == "__main__":
    sys.exit(main())
