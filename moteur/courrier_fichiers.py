"""Conservation des originaux MIME sans sortie de dossier ni écrasement."""
import hashlib
import re
from pathlib import Path


def assainir_nom(nom):
    nom = str(nom).replace("\\", "/").rsplit("/", 1)[-1]
    nom = re.sub(r'[\x00-\x1f\x7f/*?:"<>|]', "_", nom).strip(" .")
    nom = nom or "piece-jointe"
    if re.fullmatch(r"(?i:con|prn|aux|nul|com[1-9]|lpt[1-9])", nom.split(".")[0]):
        nom = "_" + nom
    return nom[:200]


def identite_message(*elements):
    return hashlib.sha256("\0".join(map(str, elements)).encode("utf-8")).hexdigest()


def conserver_piece(dossier, nom, contenu):
    """Une empreinte de contenu sépare les homonymes ; création exclusive.

    Le nom original reste dans le manifeste appelant. La pièce conservée garde
    un nom exploitable par les importeurs. Un original existant reste intact.
    """
    dossier = Path(dossier).resolve()
    empreinte = hashlib.sha256(contenu).hexdigest()
    cible = dossier / empreinte / assainir_nom(nom)
    if not cible.resolve().is_relative_to(dossier):
        raise ValueError("La pièce jointe sort du dossier autorisé")
    cible.parent.mkdir(parents=True, exist_ok=True)
    if not cible.resolve().is_relative_to(dossier):
        raise ValueError("La pièce jointe sort du dossier autorisé")
    try:
        with cible.open("xb") as sortie:
            sortie.write(contenu)
    except FileExistsError:
        if cible.read_bytes() != contenu:
            raise ValueError("Original existant altéré : aucun écrasement autorisé")
    return cible, empreinte
