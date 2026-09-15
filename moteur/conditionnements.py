"""Sélection du colis commandable et de son offre, sans écriture métier."""


import json
import math
import re
from pathlib import Path


def _positif_fini(valeur):
    """Un booléen, NaN, un infini ou une quantité non positive n'est pas un PCB."""
    if isinstance(valeur, bool):
        return None
    try:
        nombre = float(valeur)
    except (TypeError, ValueError, OverflowError):
        return None
    return nombre if math.isfinite(nombre) and nombre > 0 else None


def _meme_conditionnement(gauche, droite):
    """Tolère uniquement l'erreur de représentation float32 de l'export XLS.

    Une mantisse binary32 a 24 bits significatifs : son epsilon relatif est
    2**-23. Aucun arrondi métier ou seuil absolu n'est appliqué aux petits PCB.
    Les valeurs conservées dans l'offre et dans la décision restent intactes.
    """
    gauche, droite = _positif_fini(gauche), _positif_fini(droite)
    return (gauche is not None and droite is not None
            and math.isclose(gauche, droite, rel_tol=2**-23, abs_tol=0.0))


def selectionner(article_cadencier, surcharge=None, reference=None):
    """Priorité : décision valide, PCB du jour, Mercalys, repli inconnu à 1.

    `offre` est le dictionnaire original, jamais un prix recalculé. Sans offre
    appariée à une décision, conserver la première et signaler la contradiction.
    Le repli à 1 est seulement une compatibilité technique, pas un PCB attesté.
    """
    article_cadencier = article_cadencier or {}
    surcharge = surcharge or {}
    reference = reference or {}
    offres = article_cadencier.get("offres") or []
    premiere = offres[0] if offres else {}
    avertissements = []
    valides = []
    for i, offre in enumerate(offres, 1):
        pcb = _positif_fini(offre.get("par_colis"))
        if pcb is None:
            avertissements.append(f"PCB absent ou invalide dans l'offre {i} du cadencier.")
        else:
            valides.append((pcb, offre))
    pcbs = {pcb for pcb, _ in valides}

    conditionnement = _positif_fini(surcharge.get("conditionnement"))
    if "conditionnement" in surcharge and conditionnement is None:
        avertissements.append("Conditionnement de décision invalide : valeur ignorée.")
    if conditionnement is not None:
        source = "decision"
        offre = next((o for pcb, o in valides if _meme_conditionnement(pcb, conditionnement)), premiere)
        if not any(_meme_conditionnement(pcb, conditionnement) for pcb in pcbs):
            liste_pcb = ", ".join(f"{p:g}" for p in sorted(pcbs)) if pcbs else "aucun"
            avertissements.append(
                f"Contradiction de colisage : réglage magasin fixé à {conditionnement:g}, "
                f"alors que le cadencier fournisseur annonce {liste_pcb}. "
                "Le calcul utilise bien votre valeur.")
    elif valides:
        conditionnement, offre = valides[0]
        source = "cadencier"
        nom = (article_cadencier.get("nom") or "").upper()
        caissette = None
        if re.search(r"\bPDT\b|POMMES? DE TERRE", nom) and pcbs == {65, 8}:
            caissette = 8
        elif re.search(r"\bPDT\b|POMMES? DE TERRE", nom) and pcbs == {55, 6}:
            caissette = 6
        elif "ORANGE" in nom and "FILET" in nom and pcbs == {90, 9}:
            caissette = 9
        if caissette is not None:
            conditionnement, offre = next((pcb, o) for pcb, o in valides if pcb == caissette)
            source = "cadencier_caissette"
        elif len(pcbs) > 1:
            avertissements.append("Plusieurs PCB sans règle de caissette attestée : première offre valide conservée.")
    else:
        offre = premiere
        conditionnement = _positif_fini(reference.get("CONDIT.BASE"))
        if conditionnement is not None:
            source = "mercalys"
            avertissements.append("PCB du jour absent ou invalide : repli sur Mercalys, colisage du jour non vérifié.")
        else:
            conditionnement = 1.0
            source = "inconnu"
            avertissements.append("Conditionnement inconnu : repli technique à 1 pour compatibilité, à vérifier.")
    return {"conditionnement": conditionnement,
            "source_conditionnement": source, "offre": offre,
            "avertissements": avertissements}


def charger(racine, config, mercalys):
    """Lit le cadencier à chaque appel ; mapping par code, sans écrire ni importer.

    Inclut Mercalys et les articles rattachés du cadencier. Pour les lignes sans
    code, appeler directement selectionner(article, surcharge_par_nom).
    Les erreurs de lecture/JSON ne sont pas transformées en absence de fichier.
    """
    fichier = Path(racine) / "donnees" / "cadencier-du-jour.json"
    cadencier = json.loads(fichier.read_text(encoding="utf-8")) if fichier.exists() else {}
    articles = {}
    repetes = set()
    for article in cadencier.get("articles", []):
        code = article.get("article")
        if not code:
            continue
        if code in articles:
            repetes.add(code)
        else:
            articles[code] = article
    overrides = config.get("overrides", {})
    resultat = {code: selectionner(articles.get(code), overrides.get(code), mercalys.get(code))
                for code in dict.fromkeys([*mercalys, *articles])}
    for code in repetes:
        resultat[code]["avertissements"].append(
            f"Code {code} lié à plusieurs articles du cadencier : première ligne conservée, rapprochement à vérifier.")
    return resultat
