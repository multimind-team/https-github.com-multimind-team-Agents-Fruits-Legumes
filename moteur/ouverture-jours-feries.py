"""
Le magasin, un jour férié : ouvert toute la journée, une demi-journée
seulement, ou fermé ? Ça change tout pour la commande, et rien ne le dit
tout seul — c'est le responsable de rayon qui décide, souvent seulement quelques jours avant.

Pourquoi ce fichier existe (2026-09-04) : les jours fériés où le magasin est
ouvert font mesurément moins vendre (-46% en moyenne sur 18 jours mesurés,
le-calcul.md). Le responsable de rayon a expliqué pourquoi : beaucoup de ces jours-là, le
magasin n'ouvre que le matin — c'est une demi-journée de vente, pas un jour
normal qui vend un peu moins. Le calcul doit donc appliquer un vrai correctif
quand c'est une demi-journée, aucun quand c'est la journée complète, et
traiter le jour comme une fermeture quand c'est fermé.

Un jour férié « fixe » (1er janvier, 1er mai, 25 décembre) reste toujours
fermé, ça ne se demande pas — voir moteur/calendrier.py, JOURS_FERIES_FERMETURE.
Ce fichier ne s'occupe que des huit autres (lundi de Pâques, Ascension,
Pentecôte, 14 juillet, Assomption, Toussaint, Armistice, victoire 1945), dont
l'ouverture varie d'une année sur l'autre et doit être confirmée à chaque
fois.

Usage :
  python moteur/ouverture-jours-feries.py                     l'état des jours fériés à venir
  python moteur/ouverture-jours-feries.py --a-confirmer        ceux qu'il faut demander maintenant
  python moteur/ouverture-jours-feries.py --definir 2026-11-11 demi-journee --motif "..." --auteur responsable-rayon
"""
import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

MOTEUR = Path(__file__).resolve().parent
sys.path.insert(0, str(MOTEUR))
import calendrier
import journal_agents

RACINE = MOTEUR.parent
FICHIER = RACINE / "donnees" / "ouverture-jours-feries.json"

STATUTS_VALIDES = {"journee-complete", "demi-journee", "ferme"}

# Le correctif mesuré (le-calcul.md, 18 jours) est une moyenne qui mélange
# sans le savoir des jours ouverts toute la journée et des demi-journées.
# Faute de mieux, on l'applique aux demi-journées : c'est là que la baisse de
# fréquentation est la plus logique. À affiner si on identifie un jour, dans
# l'historique mesuré, qui était vraiment ouvert toute la journée.
FACTEUR_DEMI_JOURNEE = 0.54     # 1 - 0,46
FACTEUR_JOURNEE_COMPLETE = 1.0  # pas de donnée isolée pour trancher autrement
DELAI_A_CONFIRMER_JOURS = 10    # « quelques jours avant », demandé par le responsable de rayon


def charger():
    if not FICHIER.exists():
        return {"_lisez_moi": "", "jours": {}}
    try:
        return json.loads(FICHIER.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"_lisez_moi": "", "jours": {}}


def _ecrire(contenu):
    contenu["_lisez_moi"] = (
        "Statut d'ouverture des jours feries variables (pas les 3 fermetures fixes, "
        "voir calendrier.py). null = pas encore confirme par le responsable de rayon. "
        "journee-complete / demi-journee / ferme. Ne jamais deviner : demander."
    )
    FICHIER.write_text(json.dumps(contenu, ensure_ascii=False, indent=1), encoding="utf-8")


def ensemencer(annees=None):
    """S'assure qu'une entrée existe pour chaque jour férié variable des
    années demandées, sans jamais écraser une réponse déjà donnée."""
    annees = annees or range(date.today().year, date.today().year + 3)
    contenu = charger()
    jours = contenu.setdefault("jours", {})
    for annee in annees:
        for jour, nom in calendrier.jours_feries(annee).items():
            iso = jour.isoformat()
            if iso[5:] in calendrier.FERMETURE:
                continue   # fermeture fixe, pas variable, rien à demander
            if iso not in jours:
                jours[iso] = {"nom": nom, "statut": None, "confirme_par": None,
                              "confirme_le": None, "motif": None}
    _ecrire(contenu)
    return contenu


def statut(date_iso):
    """None si pas encore confirmé, sinon 'journee-complete' / 'demi-journee' / 'ferme'."""
    jours = charger().get("jours", {})
    entree = jours.get(date_iso)
    return entree.get("statut") if entree else None


def facteur(date_iso):
    """Le facteur à appliquer à la demande de ce jour. 1.0 si le jour n'est
    pas un férié variable, ou si le responsable de rayon n'a pas encore répondu — mieux vaut
    ignorer que deviner."""
    s = statut(date_iso)
    if s == "demi-journee":
        return FACTEUR_DEMI_JOURNEE
    if s == "journee-complete":
        return FACTEUR_JOURNEE_COMPLETE
    return 1.0


def dates_fermees():
    """Les fériés variables que le responsable de rayon a confirmés fermés cette année-là —
    à traiter exactement comme les 3 fermetures fixes."""
    jours = charger().get("jours", {})
    return {iso for iso, e in jours.items() if e.get("statut") == "ferme"}


def a_confirmer(jours_delai=DELAI_A_CONFIRMER_JOURS, depuis=None):
    """Les fériés variables qui approchent (dans les N prochains jours) et
    dont le statut n'est pas encore connu — ce qu'il faut demander au responsable de rayon."""
    ensemencer()
    contenu = charger()
    debut = date.fromisoformat(depuis) if depuis else date.today()
    limite = debut + timedelta(days=jours_delai)
    trouves = []
    for iso, e in sorted(contenu.get("jours", {}).items()):
        j = date.fromisoformat(iso)
        if debut <= j <= limite and e.get("statut") is None:
            trouves.append({"date": iso, "nom": e.get("nom")})
    return trouves


def definir(date_iso, nouveau_statut, motif, auteur="responsable-rayon"):
    if nouveau_statut not in STATUTS_VALIDES:
        sys.exit(f"Statut inconnu : {nouveau_statut}. Attendu : {', '.join(STATUTS_VALIDES)}.")
    if not motif or len(motif) < 15:
        sys.exit("Motif trop court ou manquant.")
    contenu = ensemencer()
    jours = contenu["jours"]
    if date_iso not in jours:
        sys.exit(f"{date_iso} n'est pas un jour férié variable connu.")
    avant = jours[date_iso].get("statut")
    jours[date_iso].update({
        "statut": nouveau_statut, "confirme_par": auteur,
        "confirme_le": date.today().isoformat(), "motif": motif,
    })
    _ecrire(contenu)
    journal_agents.enregistrer(
        agent=auteur,
        message=f"Ouverture du {date_iso} ({jours[date_iso]['nom']}) : {nouveau_statut}",
        motif=motif, annulable=False,  # pas d'inverse de ce JSON dans annuler.py
        details={"champ": "ouverture-jour-ferie", "date": date_iso,
                 "avant": avant, "apres": nouveau_statut})
    print(f"OK : {date_iso} ({jours[date_iso]['nom']}) -> {nouveau_statut}")
    print("  Penser à relancer generer-proposition.py si une commande est en cours.")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--a-confirmer", action="store_true",
                   help="lister les fériés à demander maintenant")
    p.add_argument("--definir", nargs=2, metavar=("DATE", "STATUT"))
    p.add_argument("--motif", default=None)
    p.add_argument("--auteur", default="responsable-rayon")
    args = p.parse_args()

    if args.definir:
        definir(args.definir[0], args.definir[1], args.motif, args.auteur)
        return

    if args.a_confirmer:
        trouves = a_confirmer()
        if not trouves:
            print("Rien à confirmer dans les prochains jours.")
        for t in trouves:
            print(f"  {t['date']}  {t['nom']} — statut inconnu, à demander au responsable de rayon")
        return

    contenu = ensemencer()
    aujourdhui = date.today().isoformat()
    for iso, e in sorted(contenu["jours"].items()):
        if iso < aujourdhui:
            continue
        print(f"  {iso}  {e['nom']:22} statut : {e['statut'] or 'à confirmer'}")


if __name__ == "__main__":
    main()
