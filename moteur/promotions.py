"""Contrôles déterministes du catalogue de promotions affiché par l'application."""
import json
from datetime import date, timedelta
from pathlib import Path


CHAMPS_OFFRE = {"nom", "visible_a_partir", "debut", "fin", "correspondances"}
CHAMPS_CORRESPONDANCE = {"itm8", "statut"}
STATUTS = {"confirmee", "a_confirmer", "sans_correspondance"}


def mardi_suivant(telecharge_le):
    """Retourne le mardi strictement après la réception du prospectus."""
    if not isinstance(telecharge_le, date):
        raise TypeError("La date de téléchargement doit être une date.")
    jours = (1 - telecharge_le.weekday()) % 7
    return telecharge_le + timedelta(days=jours or 7)


def _date(valeur, champ):
    try:
        return date.fromisoformat(valeur)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Date invalide pour {champ}") from exc


def valider(donnees):
    if not isinstance(donnees, dict) or not isinstance(donnees.get("offres"), list):
        raise ValueError("Le catalogue doit contenir une liste offres.")
    for offre in donnees["offres"]:
        manquants = CHAMPS_OFFRE - set(offre)
        if manquants:
            raise ValueError(f"Offre incomplète : {', '.join(sorted(manquants))}")
        visible = _date(offre["visible_a_partir"], "visible_a_partir")
        debut = _date(offre["debut"], "debut")
        fin = _date(offre["fin"], "fin")
        if not visible <= debut <= fin:
            raise ValueError("Les dates de l'offre sont incohérentes.")
        if not isinstance(offre["correspondances"], list):
            raise ValueError("correspondances doit être une liste.")
        for correspondance in offre["correspondances"]:
            manquants = CHAMPS_CORRESPONDANCE - set(correspondance)
            if manquants or correspondance.get("statut") not in STATUTS:
                raise ValueError("Correspondance promotion incomplète ou invalide.")
            if correspondance["statut"] != "sans_correspondance" and not correspondance.get("itm8"):
                raise ValueError("Une correspondance catalogue doit indiquer son itm8.")
    return donnees


def charger(chemin):
    return valider(json.loads(Path(chemin).read_text(encoding="utf-8")))


def rendre_apercus(prospectus, pages, destination, zoom=1.5):
    """Rend les pages lues en PNG, lisibles sans lecteur PDF sur téléphone."""
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("PyMuPDF est nécessaire pour créer les aperçus du prospectus.") from exc

    prospectus = Path(prospectus)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    document = fitz.open(prospectus)
    apercus = []
    try:
        for numero in pages:
            if not isinstance(numero, int) or numero < 1 or numero > document.page_count:
                raise ValueError(f"Page de prospectus invalide : {numero}")
            image = document.load_page(numero - 1).get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
            sortie = destination / f"page-{numero}.png"
            image.save(sortie)
            apercus.append(sortie)
    finally:
        document.close()
    return apercus


def est_affichable(offre, aujourdhui=None):
    aujourd_hui = aujourdhui or date.today()
    return _date(offre["visible_a_partir"], "visible_a_partir") <= aujourd_hui <= _date(offre["fin"], "fin")
