"""
moteur/saisonnalite_masquage.py - Analyse des transitions saisonnières pour la commande F&L.

Détecte :
1. Les articles masqués à DÉMASQUER (remettre en vente) car leur saison démarre
   (ex: potirons, potimarrons, courges, butternuts, poires d'automne, noix, agrumes).
2. Les articles actifs à MASQUER (arrêter les commandes) car leurs ventes s'effondrent
   (ex: melons, pastèques, pêches, nectarines en fin de récolte estivale).

Indique explicitement le calendrier d'action (« à partir de quand ») :
- Dès maintenant (semaine en cours / mi-mois)
- D'ici la fin du mois
- Au début du mois suivant

Écrit : donnees/recommandations-saisonnieres.json
Alimente : donnees/note-du-matin.json
"""
import json
import sys
from datetime import date, datetime
from pathlib import Path

RACINE_PAR_DEFAUT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

import agregats
import catalogue
import regles
from ecriture_derivee import ecrire_json

NOMS_MOIS = ["", "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
             "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"]


def semaine_debut_mois(annee, mois):
    return date(annee, mois, 1).isocalendar()[1]


def analyser_recommandations(racine=None):
    racine = Path(racine) if racine else RACINE_PAR_DEFAUT
    dossier_donnees = racine / "donnees"

    fic_saisons = dossier_donnees / "analyse-ventes-annuelle-saisonniere.json"
    if not fic_saisons.exists():
        return None

    try:
        saisons = json.loads(fic_saisons.read_text(encoding="utf-8"))
    except Exception:
        return None

    config = regles.charger()
    masques = {k for k, v in config.get("overrides", {}).items() if v.get("masque")}
    satellites = {m for ms in config.get("groupes", {}).values() for m in ms}

    mercalys = {}
    for a in list(catalogue.articles().values()):
        if a.get("CODE ITM"):
            mercalys[str(a["CODE ITM"])] = (a.get("LIBELLE") or "").strip()

    fic_prop = dossier_donnees / "proposition.json"
    prop = json.loads(fic_prop.read_text(encoding="utf-8")) if fic_prop.exists() else {}
    lignes_prop = {l.get("itm8"): l for l in prop.get("lignes", [])}

    # Déterminer la date de référence active de la chaîne
    try:
        ag = agregats.charger()
        date_ref = ag.get("date_reference")
    except Exception:
        date_ref = None

    if not date_ref:
        date_ref = prop.get("date_reference") or saisons.get("periode", {}).get("date_fin") or "2026-09-15"

    annee_ref = int(date_ref[:4])
    mois_ref = int(date_ref[5:7])
    jour_ref = int(date_ref[8:10])
    dt_ref = date(annee_ref, mois_ref, jour_ref)
    semaine_ref = dt_ref.isocalendar()[1]

    nom_mois_actuel = NOMS_MOIS[mois_ref]
    mois_suivant_idx = (mois_ref % 12) + 1
    nom_mois_suivant = NOMS_MOIS[mois_suivant_idx]
    mois_apres_idx = ((mois_ref + 1) % 12) + 1
    nom_mois_apres = NOMS_MOIS[mois_apres_idx]

    mois_horizon = [nom_mois_actuel, nom_mois_suivant, nom_mois_apres]

    # --- 1. Articles à DÉMASQUER (Saison en approche / demande en forte hausse) ---
    demasquer = []
    for code, art in saisons.get("articles", {}).items():
        if code not in masques or code in satellites:
            continue

        nom = (art.get("libelle") or mercalys.get(code)
               or (code[4:] if code.startswith("nom:") else code)).strip()
        if not nom or nom.isdigit():
            continue

        pleine = art.get("mois_pleine_saison") or ""
        s_info = art.get("saisonnalite", {})
        evo = s_info.get("evolution_pct")
        tendance = s_info.get("tendance")
        hebdo = art.get("courbes_hebdo", {}).get("moyenne", [])
        vol_tot = art.get("volume_total_2ans_demi", 0)

        # On exige un volume historique significatif pour éviter les articles anecdotiques
        if vol_tot < 15:
            continue

        # Condition de démasquage : pleine saison imminente ou hausse marquée sur le mois suivant
        if pleine in mois_horizon and (tendance in ["pleine_saison", "forte_hausse", "hausse"] or (evo is not None and evo >= 15.0)):
            val_sem_act = hebdo[semaine_ref - 1] if len(hebdo) >= semaine_ref else 0
            val_sem_suiv = hebdo[semaine_ref] if len(hebdo) > semaine_ref else 0

            if pleine == nom_mois_actuel or val_sem_act >= 2.0:
                quand = f"Dès maintenant (mi-{nom_mois_actuel.lower()})"
                priorite = 1
            elif val_sem_suiv >= 1.5 or pleine == nom_mois_suivant:
                quand = f"D'ici fin {nom_mois_actuel.lower()} (semaine {semaine_ref + 1})"
                priorite = 2
            else:
                s_pleine = semaine_debut_mois(annee_ref, NOMS_MOIS.index(pleine))
                quand = f"Début {pleine.lower()} (semaine {s_pleine})"
                priorite = 3

            motif = f"Pleine saison en {pleine}" if pleine else "Demande en hausse"
            if evo and evo > 0:
                motif += f" (+{evo:.0f}% attendus en {nom_mois_suivant.lower()})"

            demasquer.append({
                "itm8": code,
                "libelle": nom,
                "quand": quand,
                "priorite": priorite,
                "pleine_saison": pleine,
                "evolution_pct": evo,
                "tendance": tendance,
                "motif": motif,
                "volume_total": round(vol_tot, 1)
            })

    # --- 2. Articles à MASQUER (Fin de saison / chute brutale des ventes) ---
    masquer = []
    for code, art in saisons.get("articles", {}).items():
        if code in masques or code in satellites or code not in lignes_prop:
            continue

        nom = (art.get("libelle") or mercalys.get(code)
               or (code[4:] if code.startswith("nom:") else code)).strip()
        if not nom or nom.isdigit():
            continue

        pleine = art.get("mois_pleine_saison") or ""
        s_info = art.get("saisonnalite", {})
        evo = s_info.get("evolution_pct")
        tendance = s_info.get("tendance")
        hebdo = art.get("courbes_hebdo", {}).get("moyenne", [])
        vol_tot = art.get("volume_total_2ans_demi", 0)

        if vol_tot < 20:
            continue

        # Pleine saison passée (ex: produits d'été pour l'automne)
        est_produit_ete = pleine in ["Mai", "Juin", "Juillet", "Août"]
        decrochage = (tendance == "fin_saison") or (evo is not None and evo <= -35.0)

        if est_produit_ete and decrochage:
            val_sem_act = hebdo[semaine_ref - 1] if len(hebdo) >= semaine_ref else 0
            val_sem_suiv = hebdo[semaine_ref] if len(hebdo) > semaine_ref else 0
            val_sem_suiv2 = hebdo[semaine_ref + 1] if len(hebdo) > semaine_ref + 1 else 0

            if val_sem_act <= 1.0 or (evo is not None and evo <= -85.0):
                quand = f"Dès maintenant (semaine {semaine_ref})"
                priorite = 1
            elif val_sem_suiv <= 2.0 or val_sem_suiv2 == 0:
                quand = f"D'ici fin {nom_mois_actuel.lower()} (semaine {semaine_ref + 1})"
                priorite = 2
            else:
                s_suiv = semaine_debut_mois(annee_ref, mois_suivant_idx)
                quand = f"Début {nom_mois_suivant.lower()} (semaine {s_suiv})"
                priorite = 3

            motif = f"Fin de récolte : ventes en chute libre ({evo:.0f}% en {nom_mois_suivant.lower()})" if evo else "Décrochage saisonnier estival"

            masquer.append({
                "itm8": code,
                "libelle": nom,
                "quand": quand,
                "priorite": priorite,
                "pleine_saison": pleine,
                "evolution_pct": evo,
                "tendance": tendance,
                "motif": motif,
                "volume_total": round(vol_tot, 1)
            })

    # Tri par priorité chronologique puis volume décroissant
    demasquer.sort(key=lambda x: (x["priorite"], -x["volume_total"]))
    masquer.sort(key=lambda x: (x["priorite"], -x["volume_total"]))

    return {
        "calcule_le": datetime.now().isoformat(timespec="seconds"),
        "date_reference": date_ref,
        "mois_reference": mois_ref,
        "nom_mois_reference": nom_mois_actuel,
        "semaine_iso": semaine_ref,
        "a_demasquer": demasquer,
        "a_masquer": masquer
    }


def formater_liste_note(items, max_par_periode=3):
    """Regroupe les articles par période pour une lecture directe en 30 secondes."""
    par_quand = {}
    for it in items:
        par_quand.setdefault((it["priorite"], it["quand"]), []).append(it)

    groupes_textes = []
    for (prio, quand), liste in sorted(par_quand.items(), key=lambda kv: kv[0][0]):
        liste.sort(key=lambda x: -x["volume_total"])
        extraits = []
        for x in liste[:max_par_periode]:
            detail = f"{x['libelle']}"
            evo = x.get("evolution_pct")
            if evo is not None and abs(evo) > 0:
                detail += f" ({evo:+.0f}%)"
            extraits.append(detail)
        reste = f" et {len(liste) - max_par_periode} autre(s)" if len(liste) > max_par_periode else ""
        groupes_textes.append(f"**{quand}** : {', '.join(extraits)}{reste}")

    return " — ".join(groupes_textes)


def synthese_note_du_matin(recommandations):
    """Produit les entrées prêtes pour la Note du Matin."""
    if not recommandations:
        return []

    entrees = []
    heure = datetime.now().strftime("%Hh%M")

    a_demasquer = recommandations.get("a_demasquer", [])
    if a_demasquer:
        resume = formater_liste_note(a_demasquer, max_par_periode=3)
        texte = (
            f"**Transition saisonnière — Produits à remettre en vente (démasquer)** : {resume}. "
            f"À réactiver sur la console de commande (onglet Masqués) pour capter la demande d'automne."
        )
        entrees.append({"heure": heure, "texte": texte, "gravite": "attention"})

    a_masquer = recommandations.get("a_masquer", [])
    if a_masquer:
        resume = formater_liste_note(a_masquer, max_par_periode=3)
        texte = (
            f"**Fin de saison estivale — Produits à arrêter (masquer)** : {resume}. "
            f"À masquer sur la console de commande pour éviter les invendus et la casse."
        )
        entrees.append({"heure": heure, "texte": texte, "gravite": "attention"})

    return entrees


def sauvegarder_recommandations(recommandations, racine=None):
    if not recommandations:
        return
    racine = Path(racine) if racine else RACINE_PAR_DEFAUT
    chemin = racine / "donnees" / "recommandations-saisonnieres.json"
    ecrire_json(chemin, recommandations)


def main():
    rec = analyser_recommandations()
    if rec:
        sauvegarder_recommandations(rec)
        print(f"Recommandations saisonnières enregistrées ({len(rec['a_demasquer'])} à démasquer, {len(rec['a_masquer'])} à masquer).")
        for e in synthese_note_du_matin(rec):
            print(f"\n[{e['gravite']}] {e['texte']}")


if __name__ == "__main__":
    main()
