"""Classe et range les pièces jointes relevées par le Leader.

Ce module ne lit pas le contenu métier des fichiers et ne modifie pas les
carnets métier. Son index atteste uniquement le rangement : la même empreinte
ne crée pas deux entrées, mais sa copie archivée reste disponible au rejeu.
"""
import hashlib
import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from verrou_donnees import verrou_donnees


EXTENSIONS_FACTURE = {".pdf", ".jpg", ".jpeg", ".png", ".webp", ".gif"}
PREFIXES_MOUVEMENT = ("vente", "casse", "don", "dons", "livraison")


def nom_piece_jointe(nom):
    """Retire uniquement un éventuel préfixe technique d'archive (ex. doc_<hash>_)."""
    return re.sub(r"^doc_[0-9a-f]{12}_", "", Path(nom).name, flags=re.IGNORECASE)


def actions_a_executer(classes, nouveaux):
    """Rejoue les outils idempotents, même si les pièces sont déjà rangées.

    L'index atteste une réception, pas la réussite d'un import ou d'un calcul.
    L'importeur déduplique les faits par ID ; les calculs reconstruisent leurs
    sorties. ``nouveaux`` est conservé pour compatibilité, pas comme acquittement.
    """
    actions = []
    if classes.get("mouvement"):
        actions.append("integrer")
    if classes.get("cadencier"):
        actions.append("cadencier")
    if classes.get("mouvement") or classes.get("cadencier"):
        actions.extend(("recalculer", "note"))
    if classes.get("facture-directe"):
        actions.append("facture-directe")
    return actions


def est_catalogue_mercalys(fichier):
    chemin = Path(fichier)
    nom = nom_piece_jointe(chemin.name)
    if re.match(r"^cadencier[-_ ]+(?:mercalys|mecalys)", nom, re.I):
        return True
    if chemin.suffix.lower() == ".xlsx" and "cadencier" in nom.lower():
        if chemin.is_file():
            try:
                import openpyxl
                wb = openpyxl.load_workbook(chemin, read_only=True)
                return "Mercalys" in wb.sheetnames
            except Exception:
                pass
        return True
    return False


def est_cadencier_webtelevente(fichier):
    if est_catalogue_mercalys(fichier):
        return False
    nom = nom_piece_jointe(Path(fichier).name)
    return bool(re.match(r"^cadencier[-_ ]+webtelevente", nom, re.I))


def commandes_a_lancer(racine, dossier, actions, *, fichiers=None):
    """Construit les commandes autorisées, sans jamais lancer une facture directe."""
    racine = Path(racine)
    dossiers = [Path(dossier)] if isinstance(dossier, (str, Path)) else sorted(set(map(Path, dossier)))
    outils = racine / "moteur"
    commandes = []
    fichiers = list(map(Path, fichiers or []))
    mercalys = [f for f in fichiers if est_catalogue_mercalys(f)]
    webtelevente = [f for f in fichiers if est_cadencier_webtelevente(f)]
    if "cadencier" in actions and mercalys:
        commandes.append(["py", "-3.14", str(outils / "importer-catalogue-mercalys.py"),
                          *map(str, mercalys), "--agent", "agent-donnees", "--json"])
    for action in actions:
        if action == "integrer":
            cibles = [f for f in fichiers if classer_fichier(f) == "mouvement"] or dossiers
            for cible in cibles:
                commandes.append(["py", "-3.14", str(outils / "integrer-fichiers.py"), str(cible),
                                  "--agent", "agent-donnees", "--json"])
        elif action == "cadencier":
            for cible in webtelevente:
                commandes.append(["py", "-3.14", str(outils / "cadencier-du-jour.py"), str(cible)])
            if webtelevente:
                commandes.append(["py", "-3.14", str(outils / "analyser-marges-mercuriale.py")])
        elif action == "recalculer":
            commandes.append(["py", "-3.14", str(outils / "filet-de-securite.py"), "--forcer"])
        elif action == "note":
            commandes.append(["py", "-3.14", str(outils / "note-du-matin.py")])
    return commandes


def classer_fichier(nom):
    """Retourne le type opérationnel d'une pièce jointe, sans inférer son contenu."""
    chemin = Path(nom)
    base = nom_piece_jointe(chemin.name).lower()
    extension = chemin.suffix.lower()
    if "intermarche" in base and ("prospectus" in base or "promo" in base) and extension == ".pdf":
        return "promo-intermarche"
    if re.match(r"^cadencier[-_ ]+(?:webtelevente|mercalys|mecalys)(?:[-_ ]|$)", base) and extension in {".xls", ".xlsx"}:
        return "cadencier"
    if re.match(r"^(?:vente|casse|don|dons)(?:[-_.\s]|$)|^livraison(?:[-_.\s]|$)", base) and extension in {".xls", ".xlsx"}:
        return "mouvement"
    if any(mot in base for mot in ("pomona", "terreazur", "terre-azur", "facture")):
        return "facture-directe"
    if extension in EXTENSIONS_FACTURE:
        return "inconnu"
    return "inconnu"


def _nom_dossier(valeur):
    propre = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(valeur or "inconnu")).strip(".-")
    return propre or "inconnu"


def _empreinte(chemin):
    hachage = hashlib.sha256()
    with open(chemin, "rb") as fichier:
        for bloc in iter(lambda: fichier.read(1024 * 1024), b""):
            hachage.update(bloc)
    return hachage.hexdigest()


def _lire_index(chemin):
    if not chemin.exists():
        return []
    entrees = []
    for numero, ligne in enumerate(chemin.read_text(encoding="utf-8").splitlines(), 1):
        if not ligne.strip():
            continue
        try:
            entree = json.loads(ligne)
            if not isinstance(entree, dict) or any(
                    not isinstance(entree.get(cle), str) or not entree[cle]
                    for cle in ("sha256", "fichier", "type")):
                raise ValueError("empreinte, fichier ou type absent")
            entrees.append(entree)
        except ValueError as erreur:
            raise ValueError(f"Index courrier invalide à la ligne {numero} : {erreur}. "
                             "Restauration à vérifier, aucune réindexation automatique.") from erreur
    return entrees


def ranger_pieces_jointes(racine, identifiant_mail, date_reception, expediteur, chemins, simuler=False):
    if simuler:
        return _ranger_pieces_jointes(racine, identifiant_mail, date_reception, expediteur, chemins, True)
    with verrou_donnees(Path(racine) / "donnees"):
        return _ranger_pieces_jointes(racine, identifiant_mail, date_reception, expediteur, chemins)


def _ranger_pieces_jointes(racine, identifiant_mail, date_reception, expediteur, chemins, simuler=False):
    """Copie les nouvelles pièces jointes sous ``donnees/courrier``.

    L'index append-only porte l'empreinte SHA-256 ; une empreinte déjà connue
    est un doublon, même si le même fichier a été transféré dans un autre mail.
    ``fichiers`` contient les copies utilisables du lot, nouvelles OU connues ;
    ``nouveaux`` compte seulement les nouvelles entrées d'index. Une archive
    absente ou modifiée bloque la relance au lieu de réindexer silencieusement.
    """
    racine = Path(racine)
    dossier_courrier = racine / "donnees" / "courrier"
    index = dossier_courrier / "index.jsonl"
    existantes = _lire_index(index)
    empreintes_connues = {entree.get("sha256"): entree for entree in existantes}
    cible = dossier_courrier / f"{_nom_dossier(date_reception)}-{_nom_dossier(expediteur)}"
    if not simuler:
        cible.mkdir(parents=True, exist_ok=True)

    resultat = {"nouveaux": 0, "doublons": 0, "classes": {}, "fichiers": [], "inconnus": []}
    nouvelles_entrees = []
    for brut in chemins:
        source = Path(brut)
        if not source.is_file():
            raise FileNotFoundError(f"Pièce jointe introuvable : {source}")
        empreinte = _empreinte(source)
        genre = (empreintes_connues[empreinte]["type"] if empreinte in empreintes_connues
                 else classer_fichier(source.name))
        resultat["classes"][genre] = resultat["classes"].get(genre, 0) + 1
        if empreinte in empreintes_connues:
            destination = racine / empreintes_connues[empreinte]["fichier"]
            virtuelle = simuler and empreintes_connues[empreinte] in nouvelles_entrees
            if not virtuelle and (not destination.is_file() or _empreinte(destination) != empreinte):
                raise ValueError(f"Pièce archivée absente ou modifiée : {destination}")
            resultat["doublons"] += 1
            if str(destination) not in resultat["fichiers"]:
                resultat["fichiers"].append(str(destination))
            continue

        destination_dossier = (racine / "Documents" / "Promo intermarche") if genre == "promo-intermarche" else cible
        if not simuler:
            destination_dossier.mkdir(parents=True, exist_ok=True)
        destination = destination_dossier / nom_piece_jointe(source.name)
        suffixe = 2
        while not simuler and destination.exists():
            if _empreinte(destination) == empreinte:
                # Copie achevée avant une interruption de l'index : la reprendre.
                break
            nom = Path(nom_piece_jointe(source.name))
            destination = destination_dossier / f"{nom.stem}-{suffixe}{nom.suffix}"
            suffixe += 1
        if not simuler and not destination.exists():
            shutil.copy2(source, destination)
        resultat["nouveaux"] += 1
        resultat["fichiers"].append(str(destination))
        nouvelles_entrees.append({
            "mail": identifiant_mail,
            "recu_le": datetime.now().isoformat(timespec="seconds"),
            "date_reception": date_reception,
            "expediteur": expediteur,
            "original": source.name,
            "fichier": str(destination.relative_to(racine)).replace("\\", "/"),
            "type": genre,
            "sha256": empreinte,
        })
        empreintes_connues[empreinte] = nouvelles_entrees[-1]
        if genre == "inconnu":
            resultat["inconnus"].append(source.name)

    if nouvelles_entrees and not simuler:
        dossier_courrier.mkdir(parents=True, exist_ok=True)
        separateur_manquant = index.exists() and index.read_bytes()[-1:] not in (b"", b"\n")
        with open(index, "a", encoding="utf-8") as fichier:
            if separateur_manquant:
                fichier.write("\n")
            for entree in nouvelles_entrees:
                fichier.write(json.dumps(entree, ensure_ascii=False) + "\n")
    return resultat
