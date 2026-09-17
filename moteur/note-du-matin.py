"""
Écrit donnees/note-du-matin.json : ce qui s'est passé, en français, à lire en
trente secondes debout.

Ce script ne fait que les constats qu'un programme sait faire seul, sans
jugement : ce qui manque, ce qui est arrivé, ce qui sort de l'ordinaire.
L'agent donnees reprendra ces constats, ira voir ce qu'ils cachent,
et ajoutera ce qu'un programme ne peut pas voir.

Règle : ne jamais rien affirmer qu'on n'a pas vérifié dans les données, et
signaler ce qu'on ne sait pas plutôt que de le taire.

LECTURE SEULE sur les carnets : ce programme n'en modifie aucun.
"""
import json
from ecriture_derivee import ecrire_json
from verrou_donnees import operation_donnees
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import agregats
import catalogue
import regles
try:
    import saisonnalite_masquage
except ImportError:
    saisonnalite_masquage = None

RACINE = Path(__file__).resolve().parent.parent
DOSSIER_FAITS = RACINE / "donnees" / "faits"

FLUX_ATTENDUS = {"vente": "les ventes", "livraison": "la livraison",
                 "casse": "la casse", "don": "les dons"}
# Une journée sans casse ni don est normale. Ces flux restent affichés lorsqu'ils
# sont intégrés, mais leur absence ne doit jamais devenir une alerte de blocage.
FLUX_A_SURVEILLER = {"vente", "livraison"}
JOURS_AVANT_ALERTE = 2
ECART_NOTABLE = 0.20      # 20 % d'écart avec l'habitude


def lire_faits(depuis=None):
    import faits
    for fait in faits.lire(DOSSIER_FAITS):
        if depuis and (fait.get("date_source") or "") < depuis:
            continue
        yield fait


def veille(iso, n=1):
    a, m, j = (int(x) for x in iso.split("-"))
    return (date(a, m, j) - timedelta(days=n)).isoformat()


@operation_donnees(lambda: RACINE / "donnees")
def main():
    aggregats = agregats.charger()
    config = regles.charger()
    etat = json.loads((RACINE / "donnees" / "etat.json").read_text(encoding="utf-8"))
    date_reference = aggregats["date_reference"]
    mercalys = {str(a["CODE ITM"]): (a.get("LIBELLE") or "").strip()
                for a in list(catalogue.articles().values()) if a.get("CODE ITM")}
    masques = {k for k, v in config.get("overrides", {}).items() if v.get("masque")}
    relies = set(config.get("groupes", {})) | {m for ms in config.get("groupes", {}).values() for m in ms}

    entrees = []

    def dire(texte, gravite="info"):
        entrees.append({"heure": datetime.now().strftime("%Hh%M"), "texte": texte, "gravite": gravite})

    # --- 1. Ce qui manque : c'est le plus important -----------------------
    dernier_jour = {}
    for fait in lire_faits(depuis=veille(date_reference, 20)):
        t = fait["type"]
        if t in FLUX_ATTENDUS:
            jour = fait.get("date_source") or ""
            if jour > dernier_jour.get(t, ""):
                dernier_jour[t] = jour

    for flux in FLUX_A_SURVEILLER:
        nom = FLUX_ATTENDUS[flux]
        dernier = dernier_jour.get(flux)
        if not dernier:
            dire(f"Aucune donnée pour {nom} sur les 20 derniers jours.", "grave")
            continue
        retard = (date(*(int(x) for x in date_reference.split("-")))
                  - date(*(int(x) for x in dernier.split("-")))).days
        if retard >= JOURS_AVANT_ALERTE:
            dire(f"**{nom.capitalize()} n'arrive plus depuis {retard} jours** "
                 f"(dernière fois le {dernier[8:10]}/{dernier[5:7]}).", "grave")

    # --- 2. Ce qui est arrivé cette nuit ------------------------------------
    du_jour = defaultdict(lambda: [0, 0.0])
    for fait in lire_faits(depuis=date_reference):
        if fait.get("date_source") == date_reference:
            du_jour[fait["type"]][0] += 1
            du_jour[fait["type"]][1] += fait.get("quantite") or 0
    if du_jour:
        morceaux = []
        for t in ("vente", "livraison", "casse", "don"):
            if t in du_jour:
                morceaux.append(f"{FLUX_ATTENDUS[t]} ({du_jour[t][0]} lignes)")
        dire(f"Données du {date_reference[8:10]}/{date_reference[5:7]} intégrées : "
             + ", ".join(morceaux) + ".")

    # --- 3. Livraison arrivée sur un article masqué -------------------------
    livre_masque = defaultdict(float)
    for fait in lire_faits(depuis=veille(date_reference, 3)):
        if fait["type"] == "livraison" and fait["article"] in masques and fait["article"] not in relies:
            nom = fait.get("libelle") or mercalys.get(fait["article"], fait["article"])
            livre_masque[nom] += fait.get("colis") or 0
    if livre_masque:
        classes = sorted(livre_masque.items(), key=lambda kv: -kv[1])
        detail = ", ".join(f"{n} ({c:g} colis)" for n, c in classes[:3])
        reste = f" et {len(classes) - 3} autre(s)" if len(classes) > 3 else ""
        dire(f"**{len(classes)} article(s) masqués ont reçu une livraison** : {detail}{reste}.", "attention")

    # --- 4. Positions devenues incrédibles ----------------------------------
    conditionnements = {}
    for article in list(catalogue.articles().values()):
        code = str(article.get("CODE ITM") or "")
        if code:
            try:
                conditionnements[code] = float(article.get("CONDIT.BASE") or 1) or 1
            except (TypeError, ValueError):
                conditionnements[code] = 1.0
    for code, surcharge in config.get("overrides", {}).items():
        if surcharge.get("conditionnement"):
            try:
                conditionnements[code] = float(surcharge["conditionnement"]) or 1
            except (TypeError, ValueError):
                pass

    # Cas normaux, jamais signales : les oranges de la machine a jus partent a
    # la presse sans passer en caisse, leur position descend forcement.
    CAS_NORMAUX = {"0000087004386"}

    perdues = []
    for code, donnees in etat["articles"].items():
        if code in masques or code in CAS_NORMAUX or donnees.get("position") is None:
            continue
        colis = donnees["position"] / (conditionnements.get(code, 1) or 1)
        if colis <= -10:
            perdues.append((colis, mercalys.get(code, code)))
    if perdues:
        perdues.sort()
        noms = ", ".join(n for _, n in perdues[:4])
        dire(f"{len(perdues)} article(s) ont une position trop basse pour être crédible "
             f"({noms}{'…' if len(perdues) > 4 else ''}). Un comptage les remettrait d'aplomb.",
             "attention")

    # --- 5. Articles jamais comptés -----------------------------------------
    satellites = {m for ms in config.get("groupes", {}).values() for m in ms}
    actifs = {k for k in aggregats["articles"] if k not in masques and k not in satellites}
    jamais = [mercalys.get(k, k) for k in actifs
              if etat["articles"].get(k, {}).get("position") is None]
    if jamais:
        dire(f"{len(jamais)} article(s) actifs n'ont aucune position mesurée : "
             + ", ".join(sorted(jamais))
             + ". Leur commande part d'une estimation.", "attention")

    # --- 6. Sur-commandes récurrentes (ventes vs livraisons) -----------------
    fic_analyse_vl = RACINE / "donnees" / "analyse-ventes-livraisons.json"
    if fic_analyse_vl.exists():
        try:
            rap = json.loads(fic_analyse_vl.read_text(encoding="utf-8"))
            recurrentes = rap.get("anomalies_recurrentes", [])
            avec_ajustement = [item for item in recurrentes if item.get("ajustement_propose")]
            if avec_ajustement:
                detail = ", ".join(f"{item['libelle']} ({item['ajustement_propose']['avant']:.0f} -> {item['ajustement_propose']['apres']:.0f} colis)" for item in avec_ajustement[:3])
                reste = f" et {len(avec_ajustement) - 3} autre(s)" if len(avec_ajustement) > 3 else ""
                dire(f"**Sur-stockage récurrent détecté** sur {len(avec_ajustement)} article(s) : {detail}{reste}. "
                     f"Des réductions prudentes sont suggérées sur l'écran de commande.", "attention")
        except Exception:
            pass

    # --- 7. Alertes Prix d'achat & Marges (Mercuriale) -----------------------
    fic_marges = RACINE / "donnees" / "alertes-marges.json"
    if fic_marges.exists():
        try:
            rap_marges = json.loads(fic_marges.read_text(encoding="utf-8"))
            alertes_m = rap_marges.get("alertes", [])
            critiques = [a for a in alertes_m if a.get("gravite") == "critique"]
            hausses = [a for a in alertes_m if any("Hausse" in m for m in a.get("motifs", []))]
            faibles = [a for a in alertes_m if any("Marge brute faible" in m for m in a.get("motifs", [])) and a not in critiques]
            if critiques:
                noms_c = ", ".join(f"{a['nom']} (Achat {a['prix_achat_actuel']:.2f} € > Vente {a['prix_vente']:.2f} €)" for a in critiques[:2])
                dire(f"**Risque de vente à perte** sur {len(critiques)} article(s) : {noms_c}. Rehausser le prix de vente en caisse.", "grave")
            if hausses:
                noms_h = ", ".join(f"{a['nom']} (+{a.get('hausse_pct', 0):.0f}%)" for a in hausses[:3])
                dire(f"**Hausse brutale du prix d'achat** sur {len(hausses)} article(s) ce matin : {noms_h}. Vérifier le prix de vente en caisse.", "attention")
            elif faibles and not critiques:
                noms_f = ", ".join(f"{a['nom']} ({a['taux_marge']:.0f}% marge)" for a in faibles[:3])
                dire(f"Marge brute faible constatée sur {len(faibles)} article(s) : {noms_f}.", "attention")
        except Exception:
            pass

    # --- 8. Recommandations saisonnières (Masquage & Démasquage) -----------
    if saisonnalite_masquage:
        try:
            recommandations = saisonnalite_masquage.analyser_recommandations(RACINE)
            if recommandations:
                saisonnalite_masquage.sauvegarder_recommandations(recommandations, RACINE)
                for point in saisonnalite_masquage.synthese_note_du_matin(recommandations):
                    dire(point["texte"], point["gravite"])
        except Exception:
            pass

    if not any(e["gravite"] != "info" for e in entrees):
        dire("Rien d'anormal ce matin.")

    # Le plus grave en premier, le simple compte rendu en dernier.
    rang = {"grave": 0, "attention": 1, "info": 2}
    entrees.sort(key=lambda e: rang[e["gravite"]])

    note = {
        "date": date_reference,
        "ecrite_le": datetime.now().isoformat(timespec="seconds"),
        "ecrite_par": "constats automatiques (le Leader n'a pas encore relu)",
        "entrees": entrees,
    }
    ecrire_json(RACINE / "donnees" / "note-du-matin.json", note)

    print(f"Note du matin du {date_reference} — {len(entrees)} point(s) :\n")
    for e in entrees:
        marque = {"grave": "[!]", "attention": "[.]", "info": "   "}[e["gravite"]]
        print(f"  {marque} {e['texte']}")


if __name__ == "__main__":
    main()
