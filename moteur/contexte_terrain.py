"""Consignes humaines datées, rejouées depuis le carnet append-only.

Aucun fait de stock n'est produit ici. Les notes, la maturité et le repère
prospectus restent qualitatifs. La route HTTP est une saisie humaine, pas une
délégation de pouvoirs à un agent.

Observations promo facultatives : commentaire_promo (4000 caractères),
objectif_promo (500), bilan_promo (6000), rupture_promo (inconnue/oui/non),
precommande_colis et prix_promo (nombres finis >= 0 ou null),
unite_prix_promo (kg/piece/barquette/lot/autre, obligatoire avec un prix).
Leur omission conserve la valeur existante ; vide/null explicite la retire.
Le mode observations_seules conserve strictement les paramètres et dates du
contexte moteur, ainsi que son annulation, même pour une consigne expirée. Les
dates promotion restent des observations modifiables. Sans contexte, il crée
une base neutre courante. L'annotation est journalisée sans recalcul.
"""
import json
import math
import re
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

from verrou_donnees import append_jsonl, verrou_donnees

EMPLACEMENTS = {"rayon", "tg", "ilot", "fond"}
STATUTS = {"actif", "reimplantation", "fin-saison", "rupture-fournisseur"}
MATURITES = {"impeccable", "sur-mur", "trop-vert", "heterogene"}
PROMO_DEFAUTS = {"commentaire_promo": "", "precommande_colis": None,
                "rupture_promo": "inconnue", "objectif_promo": "", "bilan_promo": "",
                "prix_promo": None, "unite_prix_promo": None}
# Ces observations n'alimentent ni le stock ni le besoin automatique. Une
# précommande saisie ici documente ce que l'humain a observé, sans l'envoyer.
CHAMPS_OBSERVATIONS = set(PROMO_DEFAUTS) | {"note"}
CHAMPS = {"emplacement", "statut", "date_cible", "debut", "fin", "promo_debut",
          "promo_fin", "maturite", "stock_min_colis", "note"} | set(PROMO_DEFAUTS)
CHAMPS_OBSERVATIONS_SEULES = CHAMPS_OBSERVATIONS | {"promo_debut", "promo_fin"}
CHAMPS_MOTEUR = CHAMPS - CHAMPS_OBSERVATIONS_SEULES


class ConflitContexte(ValueError):
    """La fiche a changé ou une clé de requête a été réutilisée autrement."""


def texte(valeur, nom, maximum, obligatoire=False):
    if not isinstance(valeur, str):
        raise ValueError(f"{nom} : texte attendu.")
    valeur = valeur.strip()
    if (obligatoire and not valeur) or len(valeur) > maximum:
        raise ValueError(f"{nom} : {'1 à ' if obligatoire else 'au maximum '}{maximum} caractères.")
    if any(ord(c) < 32 and c not in "\n\r\t" for c in valeur):
        raise ValueError(f"{nom} contient un caractère invalide.")
    try:
        valeur.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError(f"{nom} contient un caractère illisible.") from exc
    return valeur


def jour_iso(valeur, nom):
    if not isinstance(valeur, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", valeur):
        raise ValueError(f"{nom} : date AAAA-MM-JJ attendue.")
    try:
        date.fromisoformat(valeur)
    except ValueError as exc:
        raise ValueError(f"{nom} : date invalide.") from exc
    return valeur


def nombre_observe(valeur, nom):
    if valeur is None:
        return None
    try:
        if type(valeur) not in (float, int) or valeur < 0 or not math.isfinite(valeur):
            raise ValueError
        return float(valeur)
    except (ValueError, OverflowError) as exc:
        raise ValueError(f"{nom} doit être un nombre fini positif ou nul, ou rester vide.") from exc


def normaliser(recu, articles, aujourd_hui=None):
    if not isinstance(recu, dict):
        raise ValueError("La consigne reçue est incomplète.")
    inconnus = set(recu) - CHAMPS - {"itm8", "revision", "requete_id", "motif", "annuler", "observations_seules"}
    if inconnus:
        raise ValueError("Champs de consigne non reconnus : " + ", ".join(sorted(inconnus)))
    if "observations_seules" in recu and type(recu["observations_seules"]) is not bool:
        raise ValueError("Observations seules : booléen attendu.")
    code = recu.get("itm8")
    if not isinstance(code, str) or code not in articles:
        raise ValueError("Article inconnu. Recharge la fiche produit.")
    revision = recu.get("revision")
    if type(revision) is not int or revision < 0:
        raise ValueError("Révision de la fiche invalide. Recharge la page.")
    requete = recu.get("requete_id")
    if not isinstance(requete, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,100}", requete):
        raise ValueError("Identifiant de requête invalide.")
    annuler = recu.get("annuler", False)
    if type(annuler) is not bool:
        raise ValueError("Annulation : booléen attendu.")
    resultat = {"itm8": code, "revision": revision, "requete_id": requete,
                "annuler": annuler, "motif": texte(recu.get("motif"), "Motif", 500, True)}
    if annuler:
        return resultat
    valeurs = {"emplacement": recu.get("emplacement", "rayon"),
               "statut": recu.get("statut", "actif"),
               "maturite": recu.get("maturite", "impeccable")}
    for nom, permis in (("emplacement", EMPLACEMENTS), ("statut", STATUTS), ("maturite", MATURITES)):
        if not isinstance(valeurs[nom], str) or valeurs[nom] not in permis:
            raise ValueError(f"{nom} : valeur non reconnue.")
    valeurs["debut"] = jour_iso(recu.get("debut"), "Début")
    valeurs["fin"] = jour_iso(recu.get("fin"), "Fin")
    if valeurs["fin"] < valeurs["debut"]:
        raise ValueError("La fin doit suivre le début de la consigne.")
    aujourd_hui = aujourd_hui or date.today().isoformat()
    if valeurs["fin"] < aujourd_hui:
        raise ValueError("La consigne est déjà expirée. Choisis une nouvelle date de fin.")
    valeurs["date_cible"] = None
    if recu.get("date_cible") not in (None, ""):
        valeurs["date_cible"] = jour_iso(recu["date_cible"], "Date cible")
        if not valeurs["debut"] <= valeurs["date_cible"] <= valeurs["fin"]:
            raise ValueError("La date cible doit être comprise dans la période de la consigne.")
    if valeurs["statut"] == "reimplantation" and not valeurs["date_cible"]:
        raise ValueError("La réimplantation nécessite une date cible.")
    valeurs["promo_debut"] = valeurs["promo_fin"] = None
    if recu.get("promo_debut") or recu.get("promo_fin"):
        valeurs["promo_debut"] = jour_iso(recu.get("promo_debut"), "Début prospectus")
        valeurs["promo_fin"] = jour_iso(recu.get("promo_fin"), "Fin prospectus")
        if valeurs["promo_fin"] < valeurs["promo_debut"]:
            raise ValueError("La fin du prospectus doit suivre son début.")
    minimum = recu.get("stock_min_colis", 0)
    if type(minimum) not in (float, int) or not 0 <= minimum <= 9999 or not math.isfinite(minimum):
        raise ValueError("Le minimum de présentation doit être un nombre entre 0 et 9999 colis.")
    valeurs["stock_min_colis"] = float(minimum)
    valeurs["note"] = texte(recu.get("note", ""), "Note", 4000)
    for champ, nom, maximum in (("commentaire_promo", "Commentaire promotion", 4000),
                                 ("objectif_promo", "Objectif promotion", 500),
                                 ("bilan_promo", "Bilan promotion", 6000)):
        valeurs[champ] = texte(recu.get(champ, ""), nom, maximum)
    rupture = recu.get("rupture_promo", "inconnue")
    if not isinstance(rupture, str) or rupture not in {"inconnue", "oui", "non"}:
        raise ValueError("Rupture promotion : inconnue, oui ou non attendu.")
    valeurs["rupture_promo"] = rupture
    valeurs["precommande_colis"] = nombre_observe(recu.get("precommande_colis"), "La précommande observée")
    valeurs["prix_promo"] = nombre_observe(recu.get("prix_promo"), "Le prix promotion observé")
    unite_prix = recu.get("unite_prix_promo")
    if unite_prix is not None and (not isinstance(unite_prix, str)
                                  or unite_prix not in {"kg", "piece", "barquette", "lot", "autre"}):
        raise ValueError("L'unité du prix promotion doit être kg, piece, barquette, lot ou autre.")
    if valeurs["prix_promo"] is not None and unite_prix is None:
        raise ValueError("Précise l'unité correspondant au prix promotion observé.")
    valeurs["unite_prix_promo"] = unite_prix
    return {**resultat, **valeurs, "observations_fournies": sorted(CHAMPS_OBSERVATIONS.intersection(recu))}


def _lire(donnees):
    fichier = Path(donnees) / "decisions.jsonl"
    if not fichier.exists():
        return []
    contenu = fichier.read_bytes()
    if contenu and not contenu.endswith(b"\n"):
        raise ValueError("Carnet de décisions incomplet : dernière ligne non terminée.")
    resultat = []
    for ligne in contenu.splitlines():
        if not ligne.strip():
            continue
        def refuser_non_fini(valeur):
            raise ValueError("Carnet de décisions : nombre non fini.")
        entree = json.loads(ligne, parse_constant=refuser_non_fini)
        if not isinstance(entree, dict):
            raise ValueError("Carnet de décisions invalide.")
        if entree.get("type") == "contexte-terrain":
            resultat.append(entree)
    return resultat


def effectif(contexte, jour):
    """Une programmation future laisse vivre l'ancienne consigne jusqu'au début.

    Une consigne expirée ne réactive jamais une ancienne version. Une annulation
    prend effet dès sa saisie, même si la dernière période était encore future.
    """
    if not contexte:
        return {}
    calendrier = contexte.get("calendrier")
    if calendrier is None:
        return contexte
    return next((c for c in reversed(calendrier)
                 if (c.get("enregistre_le", "")[:10] if c.get("annuler") else c.get("debut", "9999")) <= jour), {})


def actif(contexte, jour):
    contexte = effectif(contexte, jour)
    return bool(contexte and not contexte.get("annuler")
                and contexte.get("debut", "9999") <= jour <= contexte.get("fin", ""))


def coefficient(contexte, jour):
    """La majoration porte uniquement sur le jour couvert par la consigne."""
    contexte = effectif(contexte, jour)
    return {"tg": 1.5, "ilot": 2.0}.get(contexte.get("emplacement"), 1.0) if actif(contexte, jour) else 1.0


def _vue(decision, jour):
    resultat = {**PROMO_DEFAUTS, **decision["valeur"], "itm8": decision["article"],
                **{k: decision[k] for k in ("id", "revision", "auteur", "enregistre_le", "motif")}}
    resultat["annotation_seule"] = decision.get("annotation_seule", False)
    resultat["actif"] = actif(resultat, jour)
    resultat["etat"] = ("annule" if resultat.get("annuler") else "actif" if resultat["actif"]
                        else "planifie" if resultat.get("debut", "") > jour else "expire")
    return resultat


def charger(donnees, jour=None):
    """Lecture sans projection écrite ; historique limité aux 500 consignes récentes."""
    jour = jour_iso(jour or date.today().isoformat(), "Jour")
    decisions = _lire(donnees)
    articles, calendriers = {}, {}
    for decision in decisions:
        vue = _vue(decision, jour)
        code = decision["article"]
        calendriers.setdefault(code, []).append(vue)
        articles[code] = {**vue, "calendrier": calendriers[code]}
    for contexte in articles.values():
        contexte["contexte_effectif"] = effectif(contexte, jour) or None
    return {"ok": True, "jour": jour, "articles": articles,
            "historique": [_vue(d, jour) for d in reversed(decisions[-500:])]}


def _enregistrer_observations(donnees, recu, articles):
    """Un commentaire ne peut réactiver une consigne, même annulée ou expirée.

    La requête reste idempotente après une modification ultérieure : un rejeu
    est normalisé à partir de sa propre version déjà enregistrée.
    """
    with verrou_donnees(donnees):
        decisions = _lire(donnees)
        deja = next((d for d in decisions if d.get("requete_id") == recu.get("requete_id")), None)
        precedent = next((d for d in reversed(decisions) if d["article"] == recu.get("itm8")), None)
        source = deja or precedent
        aujourd_hui = date.today()
        neutre = {"emplacement": "rayon", "statut": "actif", "date_cible": None,
                  "debut": aujourd_hui.isoformat(), "fin": (aujourd_hui + timedelta(days=7)).isoformat(),
                  "maturite": "impeccable", "stock_min_colis": 0, "note": "",
                  "promo_debut": None, "promo_fin": None, **PROMO_DEFAUTS}
        base = {**neutre, **(source["valeur"] if source else {})}
        fusion = {**base, **recu, "annuler": False}
        requete = normaliser(fusion, articles, aujourd_hui="0001-01-01")
        # Le formulaire d'annotation n'envoie aucun paramètre moteur : même
        # une valeur apparemment identique doit passer par la consigne terrain.
        for champ in CHAMPS_MOTEUR:
            if champ in recu:
                raise ValueError("Une annotation ne doit pas transmettre " + champ + ". Utilise la consigne terrain.")
        if "annuler" in recu:
            raise ValueError("Une annotation ne doit pas transmettre l'état d'annulation.")
        requete["observations_seules"] = True
        requete["observations_fournies"] = sorted(CHAMPS_OBSERVATIONS_SEULES.intersection(recu))
        requete["parametres_fournis"] = sorted((CHAMPS_MOTEUR | {"annuler"}).intersection(recu))
        if deja:
            if deja.get("requete") != requete:
                raise ConflitContexte("Cette requête a déjà été utilisée pour une autre consigne.")
            return {"ok": True, "enregistre": True, "deja_enregistre": True, "annotation_seule": True,
                    "contexte": _vue(deja, aujourd_hui.isoformat())}
        revision = precedent["revision"] if precedent else 0
        if requete["revision"] != revision:
            raise ConflitContexte("Cette consigne a changé depuis l'ouverture de la fiche. Recharge la page.")
        valeur = {k: requete[k] for k in CHAMPS}
        valeur["annuler"] = bool(base.get("annuler"))
        decision = {"id": "contexte:" + uuid.uuid4().hex, "type": "contexte-terrain",
                    "article": requete["itm8"], "valeur": valeur, "revision": revision + 1,
                    "motif": requete["motif"], "auteur": "responsable-rayon",
                    "origine": "interface-rayon", "enregistre_le": datetime.now().isoformat(timespec="seconds"),
                    "requete_id": requete["requete_id"], "requete": requete, "annotation_seule": True}
        append_jsonl(Path(donnees) / "decisions.jsonl", [decision])
        return {"ok": True, "enregistre": True, "deja_enregistre": False, "annotation_seule": True,
                "contexte": _vue(decision, aujourd_hui.isoformat())}


def enregistrer(donnees, recu, articles):
    """Valide puis ajoute une seule décision sous le verrou commun."""
    if isinstance(recu, dict) and recu.get("observations_seules") is True:
        return _enregistrer_observations(donnees, recu, articles)
    # Un accusé perdu peut être rejoué même après l'expiration de la consigne.
    requete = normaliser(recu, articles, aujourd_hui="0001-01-01")
    with verrou_donnees(donnees):
        decisions = _lire(donnees)
        deja = next((d for d in decisions if d.get("requete_id") == requete["requete_id"]), None)
        if deja:
            ancienne_requete = deja.get("requete")
            if isinstance(ancienne_requete, dict) and not ancienne_requete.get("annuler"):
                fournies = sorted(CHAMPS_OBSERVATIONS.intersection(ancienne_requete))
                ancienne_requete = {**PROMO_DEFAUTS, "observations_fournies": fournies, **ancienne_requete}
            if ancienne_requete != requete:
                raise ConflitContexte("Cette requête a déjà été utilisée pour une autre consigne.")
            return {"ok": True, "enregistre": True, "deja_enregistre": True,
                    "annotation_seule": deja.get("annotation_seule", False),
                    "contexte": _vue(deja, date.today().isoformat())}
        precedent = next((d for d in reversed(decisions) if d["article"] == requete["itm8"]), None)
        revision = precedent["revision"] if precedent else 0
        if requete["revision"] != revision:
            raise ConflitContexte("Cette consigne a changé depuis l'ouverture de la fiche. Recharge la page.")
        if requete["annuler"] and precedent is None:
            raise ValueError("Aucune consigne à annuler pour cet article.")
        valeur = dict(precedent["valeur"]) if requete["annuler"] else {k: requete[k] for k in CHAMPS}
        # Une ancienne interface ou un renouvellement qui omet les nouvelles
        # observations ne doit jamais les effacer. Une chaîne vide / null
        # explicitement transmis constitue en revanche un retrait volontaire.
        if precedent and not requete["annuler"]:
            for champ in CHAMPS_OBSERVATIONS:
                if champ not in recu and champ in precedent["valeur"]:
                    valeur[champ] = precedent["valeur"][champ]
        if valeur.get("prix_promo") is not None and valeur.get("unite_prix_promo") is None:
            raise ValueError("Le prix promotion conservé nécessite son unité. Retire aussi le prix pour supprimer l'unité.")
        valeur["annuler"] = requete["annuler"]
        parametres = (CHAMPS - CHAMPS_OBSERVATIONS) | {"annuler"}
        annotation_seule = bool(precedent and not requete["annuler"] and all(
            valeur.get(champ) == precedent["valeur"].get(champ) for champ in parametres))
        if not requete["annuler"] and requete["fin"] < date.today().isoformat() and not annotation_seule:
            raise ValueError("Cette consigne est expirée : seuls ses commentaires et observations promotion peuvent être complétés. "
                             "Ses dates et paramètres de commande doivent rester inchangés.")
        decision = {"id": "contexte:" + uuid.uuid4().hex, "type": "contexte-terrain",
                    "article": requete["itm8"], "valeur": valeur, "revision": revision + 1,
                    "motif": requete["motif"], "auteur": "responsable-rayon",
                    "origine": "interface-rayon", "enregistre_le": datetime.now().isoformat(timespec="seconds"),
                    "requete_id": requete["requete_id"], "requete": requete,
                    "annotation_seule": annotation_seule}
        append_jsonl(Path(donnees) / "decisions.jsonl", [decision])
        return {"ok": True, "enregistre": True, "deja_enregistre": False,
                "annotation_seule": annotation_seule,
                "contexte": _vue(decision, date.today().isoformat())}
