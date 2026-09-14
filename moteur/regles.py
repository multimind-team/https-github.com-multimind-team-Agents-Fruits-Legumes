"""
Les réglages des articles — reconstitués depuis le carnet des décisions.

Un réglage n'est jamais stocké quelque part « en dur » : il est le résultat de
toutes les décisions prises sur l'article, rejouées dans l'ordre. La ligne la
plus récente gagne, une décision annulée est sautée, et rien n'est jamais
effacé.

C'est ce qui permet de répondre, pour n'importe quel réglage du rayon : qui
l'a voulu, quand, et pourquoi. Un fichier de configuration ne sait pas
répondre à ça — un carnet, si.

  donnees/decisions.jsonl   le carnet, une ligne par décision.

Les décisions du 2 septembre 2026 sont les décisions FONDATRICES : l'état du
rayon relevé à la mise en place de l'application (fournisseur de chaque
article, colisage, unité de vente, articles hors cadencier, regroupements de
codes jumeaux). Tout ce qui a été décidé depuis s'empile par-dessus.

Le résultat a la forme {"groupes", "overrides"}, la seule que les calculs du
moteur connaissent.

Usage :
    import regles
    config = regles.charger()
    config["overrides"]["0000087010624"]["conditionnement"]   ->  "8"

    regles.expliquer("0000087010624", "conditionnement")
    -> la décision qui a produit cette valeur, avec son motif et son auteur.
"""
import json
import sys
from pathlib import Path
from datetime import date

RACINE = Path(__file__).resolve().parent.parent
DONNEES = RACINE / "donnees"
CARNET = DONNEES / "decisions.jsonl"

# Type de décision -> champ de réglage. Le masquage et le démasquage touchent
# le même champ dans deux sens opposés.
CHAMPS = {
    "fournisseur": "fournisseur",
    "conditionnement": "conditionnement",
    "unite": "unite",
    "masquage": "masque",
    "demasquage": "masque",
    "promotion": "promotion",
}


def _lignes(fichier):
    if not fichier.exists():
        return []
    lues = []
    with open(fichier, encoding="utf-8") as f:
        for ligne in f:
            ligne = ligne.strip()
            if not ligne:
                continue
            try:
                lues.append(json.loads(ligne))
            except json.JSONDecodeError:
                continue
    return lues


def _date_calcul(valeur=None):
    if valeur is None:
        return date.today()
    if type(valeur) is date:
        return valeur
    if not isinstance(valeur, str) or len(valeur) != 10:
        raise ValueError(f"Date de décision invalide : {valeur!r} (AAAA-MM-JJ attendu)")
    resultat = date.fromisoformat(valeur)
    if resultat.isoformat() != valeur:
        raise ValueError(f"Date de décision invalide : {valeur!r}")
    return resultat


def _effective(decision, jour):
    debut = decision.get("valide_a_partir_de")
    return debut is None or _date_calcul(debut) <= jour


def _annulations(jour):
    """Deux façons d'annuler, on tient compte des deux : une ligne « annulation »
    dans le carnet, ou une action annulée dans le journal des agents."""
    annules = {d["annule"] for d in _lignes(CARNET)
               if d.get("type") == "annulation" and d.get("annule") and _effective(d, jour)}
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import journal_agents
        actions = journal_agents.actions_annulees(date_calcul=jour)
    except Exception:
        actions = set()
    return annules, actions


def decisions(avec_annulees=False, date_calcul=None):
    """Toutes les décisions, de la plus ancienne à la plus récente."""
    toutes = _lignes(CARNET)
    if avec_annulees:
        return toutes
    jour = _date_calcul(date_calcul)
    annules, actions = _annulations(jour)
    return [d for d in toutes
            if _effective(d, jour) and d.get("type") != "annulation"
            and d.get("id") not in annules
            and not (d.get("action") and d["action"] in actions)]


def charger(date_calcul=None):
    """Réglages effectifs à date_calcul (date ou AAAA-MM-JJ), aujourd’hui par défaut."""
    config = {"groupes": {}, "overrides": {}}
    for d in decisions(date_calcul=date_calcul):
        type_decision = d.get("type")
        if type_decision == "fusion":
            principal = d.get("principal") or d.get("article")
            membres = d.get("membres") or []
            if membres:
                config["groupes"][principal] = sorted(set(membres))
            else:
                config["groupes"].pop(principal, None)
            continue
        champ = CHAMPS.get(type_decision)
        if not champ:
            continue
        article = d.get("article")
        if not article:
            continue
        surcharge = config["overrides"].setdefault(article, {})
        if type_decision == "demasquage" or d.get("valeur") in (False, None):
            surcharge.pop(champ, None)
        else:
            surcharge[champ] = d["valeur"]
    # Un article dont tous les réglages ont été retirés ne doit pas laisser
    # une case vide derrière lui.
    config["overrides"] = {a: s for a, s in config["overrides"].items() if s}
    return config


def expliquer(article, champ=None, date_calcul=None):
    """Qui a voulu ce réglage, quand, et pourquoi. C'est la question que le responsable de rayon
    pose vraiment : « pourquoi cet article est masqué ? »"""
    trouvees = []
    for d in decisions(date_calcul=date_calcul):
        vise = (d.get("principal") or d.get("article")) == article \
            or article in (d.get("membres") or [])
        if not vise:
            continue
        if champ and CHAMPS.get(d.get("type")) != champ and d.get("type") != "fusion":
            continue
        trouvees.append(d)
    return trouvees


def _resume():
    config = charger()
    print(f"groupes    : {len(config['groupes'])}")
    print(f"articles réglés : {len(config['overrides'])}")
    compte = {}
    for surcharge in config["overrides"].values():
        for champ in surcharge:
            compte[champ] = compte.get(champ, 0) + 1
    for champ, n in sorted(compte.items(), key=lambda x: -x[1]):
        print(f"  {champ:16} {n}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        for d in expliquer(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None):
            print(f"\n{d.get('type')} = {d.get('valeur', d.get('membres'))}")
            print(f"  décidé par {d.get('auteur')} le {d.get('enregistre_le', '?')[:10]}")
            print(f"  motif : {d.get('motif', '')[:300]}")
    else:
        _resume()
