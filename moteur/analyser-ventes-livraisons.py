"""
moteur/analyser-ventes-livraisons.py - Analyseur de tendances : Ventes vs Livraisons avec Protection Anti-Rupture.

Ce module permet à l'agent analyste (agent-tendances) de comparer systématiquement
les quantités livrées (ou commandées) aux ventes réelles constatées en caisse.

Règles métier :
1. RÈGLE ANTI-RUPTURE (Journée exceptionnelle) :
   Si un article subit une mévente sur une seule journée (ex. 10 colis reçus, seulement 2 vendus),
   le système classe l'événement en observation isolée et NE PROPOSE AUCUNE RÉDUCTION DE COMMANDE
   pour le lendemain, afin de garantir zéro rupture si le flux client revient à la normale.
2. DÉTECTION DU DÉCROCHAGE RÉCURRENT :
   Si la mévente persiste sur plusieurs réceptions consécutives (>= 2 livraisons), l'agent identifie
   une sur-commande structurelle.
3. PROPOSITION SÉCURISÉE AVEC MATELAS DE SÉCURITÉ :
   L'agent calcule une suggestion de réduction qui respecte un stock tampon anti-rupture
   (au moins 25 % au-dessus des ventes réelles) et borne la baisse au plafond autorisé
   dans donnees/pouvoirs.json (-30 % max).
4. SOUMISSION PAR SUGGESTION :
   Les ajustements sont proposés via moteur/ajuster-commande.py --proposer et s'affichent
   avec motif et bouton « Suivre » sur l'écran de commande du responsable de rayon.
"""
import argparse
import json
import math
import subprocess
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

MOTEUR = Path(__file__).resolve().parent
sys.path.insert(0, str(MOTEUR))
import agregats
import calendrier
import catalogue
from ecriture_derivee import ecrire_json
from verrou_donnees import operation_donnees, environnement_verrou

RACINE = MOTEUR.parent
DONNEES = RACINE / "donnees"
DOSSIER_FAITS = DONNEES / "faits"
FICHIER_PROPOSITION = DONNEES / "proposition.json"
FICHIER_RAPPORT = DONNEES / "analyse-ventes-livraisons.json"
FICHIER_METEO = DONNEES / "meteo-historique.json"
POUVOIRS_PATH = DONNEES / "pouvoirs.json"
FICHIER_CALENDRIER = DONNEES / "calendrier.json"
FICHIER_OUVERTURES = DONNEES / "ouverture-jours-feries.json"


def qualifier_contexte_jour(d, cal=None, meteo=None, ouvertures=None):
    """Sépare l'absence de cause et l'absence de vérification du contexte."""
    info = {"date": d, "ferme": False, "ferie": None, "vacances": None,
            "pluie_mm": None, "temperature_max": None, "causes": [],
            "contexte_verifie": False, "verifications_manquantes": []}
    manquantes = info["verifications_manquantes"]
    try:
        if not isinstance(cal, dict) or not cal:
            raise ValueError("calendrier absent")
        q = calendrier.ce_jour(d, cal)
        periodes = cal.get("vacances", [])
        if (cal.get("derniere_erreur") or not periodes
                or not min(p["debut"] for p in periodes) <= d <= max(p["fin"] for p in periodes)):
            manquantes.append("calendrier scolaire non couvert")
    except (ValueError, TypeError, KeyError):
        q = {}
        manquantes.append("calendrier indisponible")
    js, ferie, vacances = q.get("jour_semaine"), q.get("ferie"), q.get("vacances")
    # Les jours fériés sont calculables sans téléchargement, quelle que soit l'année.
    ferie = ferie or calendrier.jours_feries(date.fromisoformat(d).year).get(date.fromisoformat(d))
    statut = None
    if isinstance(ouvertures, dict) and isinstance(ouvertures.get("jours"), dict):
        statut = ouvertures["jours"].get(d, {}).get("statut")
    else:
        manquantes.append("ouvertures exceptionnelles non vérifiées")
    ferme = q.get("ferme") or js == "dimanche" or statut == "ferme"
    info.update(ferme=bool(ferme), ferie=ferie, vacances=vacances, jour_semaine=js)
    if ferme:
        info["causes"].append("Magasin fermé (dimanche)" if js == "dimanche" else "Magasin fermé (fermeture exceptionnelle)")
    elif ferie:
        info["causes"].append(f"Jour férié ({ferie})")
    elif statut == "demi-journee":
        info["causes"].append("Ouverture limitée à une demi-journée")
    for delta in (-1, 1):
        voisin = date.fromisoformat(d) + timedelta(days=delta)
        if ((js == "vendredi" and delta == -1) or (js == "lundi" and delta == 1)) and voisin in calendrier.jours_feries(voisin.year):
            info["causes"].append("Pont autour d'un jour férié")
    valeurs = (meteo or {}).get(d)
    if (isinstance(valeurs, (list, tuple)) and len(valeurs) >= 2
            and all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in valeurs[:2])):
        tmax, pluie = valeurs[:2]
        info.update(temperature_max=tmax, pluie_mm=pluie)
        if pluie >= 5:
            info["causes"].append(f"Intempéries / Pluie ({pluie:.0f} mm)")
        if tmax <= 14 and d[5:7] in ("06", "07", "08", "09"):
            info["causes"].append(f"Fraîcheur inhabituelle ({tmax:.0f} °C)")
    else:
        manquantes.append("météo absente ou incomplète")
    if vacances:
        info["causes"].append(f"Vacances scolaires ({vacances})")
    info["contexte_verifie"] = not manquantes
    return info


def lire_contexte(chemin):
    """Lecture seule : un cache absent n'est ni créé ni téléchargé par l'analyse."""
    try:
        valeur = json.loads(chemin.read_text(encoding="utf-8"))
        return valeur if isinstance(valeur, dict) else None
    except (OSError, ValueError):
        return None


def decaler_date(iso_str, jours):
    d = date.fromisoformat(iso_str)
    return (d + timedelta(days=jours)).isoformat()


def charger_faits_recents(depuis):
    """Charge les faits de vente et livraison depuis une date donnée."""
    import faits
    livraisons = defaultdict(lambda: defaultdict(float))  # article -> date -> quantite
    livraisons_colis = defaultdict(lambda: defaultdict(float))  # article -> date -> colis
    ventes = defaultdict(lambda: defaultdict(float))  # article -> date -> quantite
    colisages_vus = {}

    for fait in faits.lire(DOSSIER_FAITS):
        d = ((fait.get("date_effet") or fait.get("date_source")) if fait.get("type") == "livraison"
             else (fait.get("date_source") or fait.get("date_effet"))) or ""
        if d < depuis:
            continue
        art = fait.get("article")
        if not art:
            continue

        if fait["type"] == "livraison":
            q = float(fait.get("quantite") or 0.0)
            c = float(fait.get("colis") or 0.0)
            livraisons[art][d] += q
            livraisons_colis[art][d] += c
            if fait.get("par_colis"):
                colisages_vus[art] = float(fait["par_colis"])
        elif fait["type"] == "vente":
            q = float(fait.get("quantite") or 0.0)
            ventes[art][d] += q

    return livraisons, livraisons_colis, ventes, colisages_vus


def analyser(fenetre_jours=7, seuil_ecoulement=0.50):
    """
    Analyse les livraisons vs ventes sur la période.
    Renvoie un dictionnaire complet de diagnostic.
    """
    # 0. Charger le calendrier et la météo historique pour qualifier le contexte externe
    cal = lire_contexte(FICHIER_CALENDRIER)
    meteo = lire_contexte(FICHIER_METEO) or {}
    ouvertures = lire_contexte(FICHIER_OUVERTURES)

    # 1. Charger la proposition actuelle pour connaître les dates de référence
    prop = {}
    if FICHIER_PROPOSITION.exists():
        try:
            prop = json.loads(FICHIER_PROPOSITION.read_text(encoding="utf-8"))
        except Exception:
            pass

    date_commande = prop.get("date_commande", date.today().isoformat())
    date_ref = min(prop.get("date_reference") or decaler_date(date_commande, -1), decaler_date(date.today().isoformat(), -1))
    date_debut = decaler_date(date_ref, -(fenetre_jours - 1))

    lignes_prop = {l["itm8"]: l for l in prop.get("lignes", [])}
    catalogue_articles = catalogue.articles()

    livraisons, livraisons_colis, ventes, colisages_vus = charger_faits_recents(date_debut)

    # Une journée absente du fichier des ventes n'est pas une vente nulle.
    jours_ventes = {d for par_jour in ventes.values() for d in par_jour if d <= date_ref}
    agr = lire_contexte(FICHIER_PROPOSITION.parent / "agregats.json") or {}
    jours_ventes.update(d for d in agr.get("jours_ventes_integres", []) if d <= date_ref)
    articles_evalues = sorted(a for a in livraisons if any(d <= date_ref for d in livraisons[a]))
    anomalies_isolees = []
    anomalies_recurrentes = []
    analyses_articles = []

    for itm8 in articles_evalues:
        dates_livraisons = sorted(d for d in livraisons[itm8] if d <= date_ref)
        if not dates_livraisons:
            continue

        fiche_cat = catalogue_articles.get(itm8, {})
        libelle = fiche_cat.get("LIBELLE") or lignes_prop.get(itm8, {}).get("libelle") or itm8
        colisage = colisages_vus.get(itm8) or fiche_cat.get("COLISAGE") or lignes_prop.get(itm8, {}).get("conditionnement") or 1.0
        try:
            colisage = float(colisage)
            if colisage <= 0:
                colisage = 1.0
        except (ValueError, TypeError):
            colisage = 1.0

        # Historique des réceptions et ventes associées
        historique_receptions = []
        consecutive_faibles = 0
        total_livre = 0.0
        total_vendu = 0.0

        for rang, d in enumerate(dates_livraisons):
            fin_periode = min(date_ref, decaler_date(dates_livraisons[rang + 1], -1)) if rang + 1 < len(dates_livraisons) else date_ref
            jours_periode = [decaler_date(d, n) for n in range((date.fromisoformat(fin_periode) - date.fromisoformat(d)).days + 1)]
            contextes = [qualifier_contexte_jour(j, cal, meteo, ouvertures) for j in jours_periode]
            ventes_completes = all(j in jours_ventes or c["ferme"] for j, c in zip(jours_periode, contextes))
            q_livree = livraisons[itm8][d]
            c_livres = livraisons_colis[itm8].get(d) or q_livree / colisage
            q_vendue = sum(ventes[itm8].get(j, 0.0) for j in jours_periode)
            c_vendus = q_vendue / colisage

            total_livre += q_livree
            total_vendu += q_vendue

            taux = (q_vendue / q_livree) if q_livree > 0 else 1.0
            reliquat_colis = max(0.0, c_livres - c_vendus)


            point = {
                "date": d,
                "fin_periode": fin_periode,
                "ventes_completes": ventes_completes,
                "contexte_verifie": ventes_completes and all(c["contexte_verifie"] for c in contextes),
                "verifications_manquantes": sorted({m for c in contextes for m in c["verifications_manquantes"]} | ({"journées de vente manquantes"} if not ventes_completes else set())),
                "quantite_livree": round(q_livree, 2),
                "colis_livres": round(c_livres, 1),
                "quantite_vendue": round(q_vendue, 2),
                "colis_vendus": round(c_vendus, 1),
                "taux_ecoulement": round(taux, 2),
                "reliquat_colis": round(reliquat_colis, 1),
                "sous_ecoulement": (taux < seuil_ecoulement and c_livres >= 1.0),
                "causes_externes": [f"{c['date']} : {cause}" for c in contextes for cause in c["causes"]],
            }
            historique_receptions.append(point)

        # Vérifier si les dernières réceptions sont en sous-écoulement consécutif
        for pt in reversed(historique_receptions):
            if pt["sous_ecoulement"]:
                consecutive_faibles += 1
            else:
                break

        jours_avec_ventes = len([d for d, q in ventes[itm8].items() if date_debut <= d <= date_ref and q > 0])
        somme_ventes = sum(q for d, q in ventes[itm8].items() if date_debut <= d <= date_ref)
        vitesse_vente_jour_unites = (somme_ventes / max(1, jours_avec_ventes)) if jours_avec_ventes else 0.0
        vitesse_vente_jour_colis = vitesse_vente_jour_unites / colisage

        ligne_p = lignes_prop.get(itm8, {})
        propose_colis = float(ligne_p.get("propose_colis") or 0.0)

        resume = {
            "itm8": itm8,
            "libelle": libelle,
            "colisage": colisage,
            "propose_colis": propose_colis,
            "total_livre_unites": round(total_livre, 2),
            "total_vendu_unites": round(total_vendu, 2),
            "vitesse_vente_jour_colis": round(vitesse_vente_jour_colis, 2),
            "receptions_observees": len(historique_receptions),
            "consecutive_faibles": consecutive_faibles,
            "derniere_reception": historique_receptions[-1] if historique_receptions else None,
        }

        # CAS 1 : JOURNÉE ATYPIQUE ISOLÉE (1 seule livraison sous-écoulée)
        if consecutive_faibles == 1:
            derniere = historique_receptions[-1]
            causes = derniere.get("causes_externes", [])
            cause_txt = f", expliquée par cause(s) externe(s) : {', '.join(causes)}" if causes else ""
            diag = {
                **resume,
                "statut": "isole",
                "causes_externes": causes,
                "ajustement_propose": None,
                "motif_analyse": (
                    f"Mévente ponctuelle le {derniere['date']} ({derniere['colis_livres']} colis reçus, "
                    f"seulement {derniere['colis_vendus']} vendus{cause_txt}). "
                    f"Classé en journée atypique : AUCUNE réduction de commande n'est proposée pour "
                    f"protéger le rayon contre toute rupture en cas de retour à la normale."
                ),
            }
            anomalies_isolees.append(diag)
            analyses_articles.append(diag)

        # CAS 2 : SUR-COMMANDE RÉCURRENTE (>= 2 réceptions consécutives en sous-écoulement)
        elif consecutive_faibles >= 2 and propose_colis > 0:
            receptions_faibles = [pt for pt in historique_receptions[-consecutive_faibles:] if pt["sous_ecoulement"]]
            causes_trouvees = []
            for pt in receptions_faibles:
                for c in pt.get("causes_externes", []):
                    causes_trouvees.append(f"{pt['date']} ({c})")

            # SOUS-CAS 2A : Sous-écoulement expliqué par des facteurs externes (magasin fermé, météo, férié, vacances)
            if causes_trouvees:
                causes_str = " ; ".join(causes_trouvees)
                motif = (
                    f"Sous-écoulement sur {consecutive_faibles} livraisons consécutives, mais expliqué par "
                    f"cause(s) externe(s) : {causes_str}. "
                    f"La mévente n'étant pas structurelle, commande actuelle de {propose_colis:.0f} colis maintenue "
                    f"pour garantir zéro rupture lors du retour aux conditions normales."
                )
                diag = {
                    **resume,
                    "statut": "recurrent_cause_externe",
                    "causes_externes": causes_trouvees,
                    "ajustement_propose": None,
                    "motif_analyse": motif,
                }
                anomalies_recurrentes.append(diag)
                analyses_articles.append(diag)
            elif any(not pt["contexte_verifie"] for pt in receptions_faibles):
                manquantes = sorted({m for pt in receptions_faibles for m in pt["verifications_manquantes"]})
                diag = {**resume, "statut": "recurrent_contexte_incomplet", "causes_externes": [],
                        "ajustement_propose": None, "verifications_manquantes": manquantes,
                        "motif_analyse": "Commande maintenue : contexte non vérifié (" + ", ".join(manquantes) + "). Aucune baisse proposée."}
                anomalies_recurrentes.append(diag)
                analyses_articles.append(diag)
            else:
                # SOUS-CAS 2B : Sur-commande structurelle réelle -> Réduction prudente avec matelas anti-rupture
                buffer_securite = max(1.0, math.ceil(vitesse_vente_jour_colis * 1.25))

                max_pourcent = 30.0
                if POUVOIRS_PATH.exists():
                    try:
                        p = json.loads(POUVOIRS_PATH.read_text(encoding="utf-8"))
                        max_pourcent = float(p.get("agents", {}).get("agent-tendances", {}).get("ajustement_max_pourcent", 30))
                    except Exception:
                        pass

                plancher_pouvoirs = max(1.0, math.ceil(propose_colis * (1.0 - (max_pourcent / 100.0))))

                colis_ajustes = max(buffer_securite, plancher_pouvoirs)

                if colis_ajustes < propose_colis:
                    baisse_colis = propose_colis - colis_ajustes
                    baisse_pct = round((baisse_colis / propose_colis) * 100, 1)

                    motif = (
                        f"Sur-stockage récurrent ({consecutive_faibles} livraisons consécutives où les ventes "
                        f"restent sous {int(seuil_ecoulement*100)} % des réceptions). "
                        f"Ajustement proposé de {propose_colis:.0f} à {colis_ajustes:.0f} colis "
                        f"(-{baisse_pct:.0f} %, marge anti-rupture de {buffer_securite:.0f} colis incluse)."
                    )

                    diag = {
                        **resume,
                        "statut": "recurrent",
                        "causes_externes": [],
                        "ajustement_propose": {
                            "avant": propose_colis,
                            "apres": colis_ajustes,
                            "baisse_colis": baisse_colis,
                            "baisse_pourcent": baisse_pct,
                            "buffer_anti_rupture": buffer_securite,
                        },
                        "motif_analyse": motif,
                    }
                    anomalies_recurrentes.append(diag)
                    analyses_articles.append(diag)
                else:
                    if buffer_securite >= propose_colis:
                        motif = (
                            f"Sur-stockage récurrent ({consecutive_faibles} livraisons consécutives où les ventes "
                            f"restent sous {int(seuil_ecoulement*100)} % des réceptions). "
                            f"Commande actuelle de {propose_colis:.0f} colis maintenue : la vitesse de vente "
                            f"nécessite un tampon de sécurité de {buffer_securite:.0f} colis pour garantir zéro rupture."
                        )
                        statut = "recurrent_protege_anti_rupture"
                    else:
                        motif = (
                            f"Sur-stockage récurrent ({consecutive_faibles} livraisons consécutives où les ventes "
                            f"restent sous {int(seuil_ecoulement*100)} % des réceptions). "
                            f"Commande actuelle : {propose_colis:.0f} colis. Une baisse d'au moins 1 colis dépasserait "
                            f"le plafond d'ajustement autorisé de {max_pourcent:.0f} % pour l'analyste. "
                            f"Arbitrage manuel recommandé pour le responsable de rayon."
                        )
                        statut = "recurrent_plafonne"

                    diag = {
                        **resume,
                        "statut": statut,
                        "causes_externes": [],
                        "ajustement_propose": None,
                        "motif_analyse": motif,
                    }
                    anomalies_recurrentes.append(diag)
                    analyses_articles.append(diag)

    # Tri par gravité (plus forte baisse ou plus fort reliquat)
    anomalies_recurrentes.sort(key=lambda x: -x["consecutive_faibles"])
    anomalies_isolees.sort(key=lambda x: -(x["derniere_reception"]["colis_livres"] if x.get("derniere_reception") else 0))

    rapport = {
        "_lisez_moi": "Analyse Ventes vs Livraisons avec garde-fou anti-rupture pour l'agent-tendances.",
        "genere_le": date.today().isoformat(),
        "periode": {"debut": date_debut, "fin": date_ref, "jours": fenetre_jours},
        "synthese": {
            "articles_evalues": len(articles_evalues),
            "journees_isolees_sans_action": len(anomalies_isolees),
            "surcommandes_recurrentes_detectees": len(anomalies_recurrentes),
            "recurrentes_causes_externes_sans_baisse": len([a for a in anomalies_recurrentes if a.get("statut") == "recurrent_cause_externe"]),
            "recurrentes_propositions_baisse": len([a for a in anomalies_recurrentes if a.get("ajustement_propose")]),
        },
        "anomalies_recurrentes": anomalies_recurrentes,
        "anomalies_isolees": anomalies_isolees,
    }

    return rapport


def soumettre_suggestions(rapport, max_ajustements=10):
    """
    Soumet les ajustements récurrents via moteur/ajuster-commande.py --proposer.
    L'agent ne modifie jamais d'office : il propose sur l'écran du chef de rayon.
    """
    recurrentes = rapport.get("anomalies_recurrentes", [])
    if not recurrentes:
        return []

    ajustes = []
    for item in recurrentes[:max_ajustements]:
        art = item["itm8"]
        prop_ajust = item["ajustement_propose"]
        if not prop_ajust:
            continue
        colis_cible = prop_ajust["apres"]
        motif = item["motif_analyse"]

        cmd = [
            sys.executable,
            str(MOTEUR / "ajuster-commande.py"),
            art,
            str(colis_cible),
            "--motif", motif,
            "--proposer",
            "--agent", "agent-tendances",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, env=environnement_verrou(DONNEES))
        ajustes.append({
            "article": art,
            "libelle": item["libelle"],
            "colis_propose": colis_cible,
            "code_retour": res.returncode,
            "sortie": res.stdout.strip(),
            "erreur": res.stderr.strip() if res.returncode != 0 else "",
        })

    return ajustes


@operation_donnees(lambda: DONNEES)
def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--jours", type=int, default=7, help="Fenêtre d'observation en jours (défaut: 7)")
    parser.add_argument("--seuil-ecoulement", type=float, default=0.50, help="Seuil de sous-écoulement ratio ventes/livraisons (défaut: 0.50)")
    parser.add_argument("--proposer", action="store_true", help="Transmet automatiquement les suggestions d'ajustement à ajuster-commande.py")
    parser.add_argument("--silencieux", action="store_true", help="N'affiche que le résumé essentiel")
    args = parser.parse_args()

    rapport = analyser(fenetre_jours=args.jours, seuil_ecoulement=args.seuil_ecoulement)

    # Écriture du rapport dans donnees/analyse-ventes-livraisons.json
    ecrire_json(FICHIER_RAPPORT, rapport)

    if not args.silencieux:
        synth = rapport["synthese"]
        print(f"=== ANALYSE VENTES VS LIVRAISONS ({rapport['periode']['debut']} -> {rapport['periode']['fin']}) ===")
        print(f"  Articles avec livraisons évalués : {synth['articles_evalues']}")
        print(f"  Journées atypiques isolées (anti-rupture : 0 baisse) : {synth['journees_isolees_sans_action']}")
        print(f"  Sur-commandes récurrentes détectées : {synth['surcommandes_recurrentes_detectees']}")
        if synth.get("recurrentes_causes_externes_sans_baisse"):
            print(f"    -> dont expliquées par causes externes (fermé, météo, férié) : {synth['recurrentes_causes_externes_sans_baisse']} (0 baisse)")
        if synth.get("recurrentes_propositions_baisse"):
            print(f"    -> dont réelles propositions d'ajustement : {synth['recurrentes_propositions_baisse']}")

        if rapport["anomalies_recurrentes"]:
            print("\n[!] DÉCROCHAGES RÉCURRENTS (Suggestions de réduction avec matelas anti-rupture) :")
            for item in rapport["anomalies_recurrentes"]:
                p = item.get("ajustement_propose")
                print(f"  - {item['libelle']} ({item['itm8']}) : {item['consecutive_faibles']} réceptions consécutives en mévente.")
                if p:
                    print(f"    Proposition : {p['avant']} -> {p['apres']} colis (-{p['baisse_pourcent']} %). Matelas anti-rupture : {p['buffer_anti_rupture']} colis.")
                elif item.get("statut") == "recurrent_cause_externe":
                    print(f"    Proposition : 0 baisse (mévente expliquée par facteurs externes : magasin fermé, météo, férié ou vacances).")
                elif item.get("statut") == "recurrent_contexte_incomplet":
                    print("    Proposition : 0 baisse (contexte non vérifié).")
                elif item.get("statut") == "recurrent_protege_anti_rupture":
                    print(f"    Proposition : 0 baisse (maintien à {item['propose_colis']} colis pour protéger contre la rupture).")
                else:
                    print(f"    Proposition : Baisse d'au moins 1 colis dépasserait le plafond autorisé (-30 %). Arbitrage manuel.")
                print(f"    Raison : {item['motif_analyse']}")

        if rapport["anomalies_isolees"]:
            print("\n[i] JOURNÉES ATYPIQUES ISOLÉES (Préservées sans réduction pour éviter toute rupture) :")
            for item in rapport["anomalies_isolees"][:5]:
                d = item["derniere_reception"]
                print(f"  - {item['libelle']} le {d['date']} : {d['colis_livres']} colis livrés, {d['colis_vendus']} vendus. Aucun ajustement (journée exceptionnelle).")

    if args.proposer and rapport["anomalies_recurrentes"]:
        print("\nSoumission des suggestions d'ajustement à l'écran de commande...")
        actions = soumettre_suggestions(rapport)
        for a in actions:
            statut = "OK" if a["code_retour"] == 0 else f"ERREUR ({a['erreur']})"
            print(f"  -> {a['libelle']} : {a['colis_propose']} colis suggérés [{statut}]")


if __name__ == "__main__":
    main()
