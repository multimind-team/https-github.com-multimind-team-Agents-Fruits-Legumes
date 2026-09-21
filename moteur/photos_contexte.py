"""Photographies terrain locales, datées par l'humain, sans analyse visuelle.

Originaux privés immuables, dérivés JPEG sans métadonnées, carnet de versions
en ajout seul. Aucune quantité, aucun prix ni ordre de commande n'est déduit.
"""
import base64
import binascii
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import re
from datetime import datetime
import uuid
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError

from contexte_terrain import jour_iso, texte
from verrou_donnees import append_jsonl, verrou_donnees

MAX_OCTETS = 8 * 1024 * 1024
MAX_PIXELS = 40_000_000
ZONES = {"rayon": "rayon", "tg": "tête de gondole", "ilot": "îlot", "produit": "produit", "reserve": "réserve"}
FORMATS = {"JPEG": ("jpg", "image/jpeg"), "PNG": ("png", "image/png"), "WEBP": ("webp", "image/webp")}
METADONNEES = {"date_photo", "zone", "itm8", "titre", "changement", "commentaire", "promo_debut", "promo_fin"}
LIMITES = ["Les dates de prise de vue et les changements sont déclarés par l'utilisateur.",
           "Le commentaire automatique décrit les informations saisies ; aucune analyse visuelle n'a été réalisée.",
           "Une photo ne prouve ni une quantité de stock, ni un prix, ni l'effet d'un changement sur les ventes.",
           "Les images restent sur ce PC. Les originaux privés conservent leurs métadonnées ; les aperçus publics n'en contiennent pas."]


class ConflitPhoto(ValueError):
    pass


def _lire(racine):
    chemin = Path(racine) / "donnees" / "photos-contexte.jsonl"
    if not chemin.exists():
        return []
    contenu = chemin.read_bytes()
    if contenu and not contenu.endswith(b"\n"):
        raise ValueError("Carnet photos incomplet : dernière ligne non terminée. Aucun ajout effectué.")
    resultat = []
    for ligne in contenu.splitlines():
        if not ligne.strip():
            continue
        entree = json.loads(ligne)
        if (not isinstance(entree, dict) or entree.get("schema") != 1 or entree.get("type") != "photo-contexte"
                or not re.fullmatch(r"photo:[a-f0-9]{32}", str(entree.get("id") or ""))
                or type(entree.get("revision")) is not int or entree["revision"] < 1):
            raise ValueError("Carnet photos invalide. Fais vérifier les données.")
        resultat.append(entree)
    return resultat


def _vue(photo):
    return {k: v for k, v in photo.items() if k not in {"requete_signature", "schema", "type"}}


def charger(racine, article=None):
    """Lecture pure ; aucune image n'est ouverte, aucune métadonnée extraite."""
    dernieres = {p["id"]: p for p in _lire(racine)}
    photos = [_vue(p) for p in dernieres.values() if article is None or p.get("itm8") == article]
    photos.sort(key=lambda p: (p["date_photo"], p["enregistre_le"], p["id"]), reverse=True)
    return {"ok": True, "photos": photos, "limites": LIMITES}


def _normaliser(recu, articles, precedent=None):
    if not isinstance(recu, dict):
        raise ValueError("La fiche photo reçue est incomplète.")
    inconnus = set(recu) - METADONNEES - {"requete_id", "id", "revision", "image_base64", "nom_fichier"}
    if inconnus:
        raise ValueError("Champs photo non reconnus : " + ", ".join(sorted(inconnus)))
    req = recu.get("requete_id")
    if not isinstance(req, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,100}", req):
        raise ValueError("Identifiant de requête photo invalide.")
    edition = "id" in recu
    if edition:
        if not isinstance(recu["id"], str) or not re.fullmatch(r"photo:[a-f0-9]{32}", recu["id"]):
            raise ValueError("Identifiant de photo invalide.")
        if type(recu.get("revision")) is not int or recu["revision"] < 1:
            raise ValueError("Révision photo invalide. Recharge la galerie.")
        if "image_base64" in recu or "nom_fichier" in recu:
            raise ValueError("L'édition conserve l'image originale. Ajoute une nouvelle photo pour changer d'image.")
        if not precedent:
            raise ValueError("Photo inconnue. Recharge la galerie.")
    elif "revision" in recu:
        raise ValueError("Une nouvelle photo ne doit pas indiquer de révision.")
    valeurs = {k: precedent[k] for k in METADONNEES if k in precedent} if precedent else {}
    valeurs.update({k: recu[k] for k in METADONNEES if k in recu})
    valeur_date = valeurs.get("date_photo")
    if not isinstance(valeur_date, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", valeur_date):
        raise ValueError("Précise la date et l'heure de la photo, au format AAAA-MM-JJTHH:MM.")
    try:
        moment = datetime.fromisoformat(valeur_date)
    except ValueError as exc:
        raise ValueError("La date de prise de vue est invalide.") from exc
    if moment > datetime.now().replace(second=0, microsecond=0):
        raise ValueError("La date de prise de vue ne peut pas être dans le futur.")
    zone = valeurs.get("zone")
    if not isinstance(zone, str) or zone not in ZONES:
        raise ValueError("Choisis une zone : rayon, tg, ilot, produit ou reserve.")
    itm8 = valeurs.get("itm8")
    if itm8 in (None, ""):
        itm8 = None
    if itm8 is not None and (not isinstance(itm8, str) or itm8 not in articles):
        raise ValueError("Article inconnu. Sélectionne un article du magasin.")
    if zone == "produit" and itm8 is None:
        raise ValueError("Une photo de produit doit être liée à un article.")
    resultat = {"date_photo": valeur_date, "zone": zone, "itm8": itm8,
                "libelle": articles.get(itm8, "") if itm8 else None,
                "titre": texte(valeurs.get("titre", ""), "Titre", 160),
                "changement": texte(valeurs.get("changement", ""), "Changement constaté", 2000),
                "commentaire": texte(valeurs.get("commentaire", ""), "Commentaire", 6000),
                "promo_debut": None, "promo_fin": None}
    if valeurs.get("promo_debut") or valeurs.get("promo_fin"):
        resultat["promo_debut"] = jour_iso(valeurs.get("promo_debut"), "Début promotion")
        resultat["promo_fin"] = jour_iso(valeurs.get("promo_fin"), "Fin promotion")
        if resultat["promo_fin"] < resultat["promo_debut"]:
            raise ValueError("La fin de promotion doit suivre son début.")
    return resultat


def _commentaire_auto(meta):
    texte_auto = f"Prise de vue déclarée : {meta['date_photo'].replace('T', ' à ')} — zone {ZONES[meta['zone']]}"
    if meta["itm8"]:
        texte_auto += f", article {meta['libelle'] or meta['itm8']} ({meta['itm8']})"
    texte_auto += "."
    if meta["changement"]:
        texte_auto += " Changement déclaré : " + meta["changement"]
    if meta["promo_debut"]:
        texte_auto += f" Promotion déclarée du {meta['promo_debut']} au {meta['promo_fin']}."
    return texte_auto + " Aucune analyse visuelle automatique n'a été réalisée."


def _decoder_image(recu):
    nom = texte(recu.get("nom_fichier"), "Nom du fichier", 200, True)
    if any(c in nom for c in "/\\\x00"):
        raise ValueError("Le nom du fichier ne doit pas contenir de chemin.")
    encodee = recu.get("image_base64")
    if not isinstance(encodee, str) or not encodee or len(encodee) > 4 * ((MAX_OCTETS + 2) // 3):
        raise ValueError("La photo doit peser au maximum 8 Mo avant encodage.")
    try:
        original = base64.b64decode(encodee, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("L'image reçue n'est pas un encodage base64 valide.") from exc
    if not original or len(original) > MAX_OCTETS:
        raise ValueError("La photo doit peser au maximum 8 Mo.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(original)) as controle:
                format_image = controle.format
                if format_image not in FORMATS:
                    raise ValueError("Formats acceptés : JPEG, PNG ou WebP uniquement.")
                largeur, hauteur = controle.size
                if largeur <= 0 or hauteur <= 0 or largeur * hauteur > MAX_PIXELS:
                    raise ValueError("La photo dépasse la limite de 40 millions de pixels.")
                if getattr(controle, "n_frames", 1) != 1:
                    raise ValueError("Les images animées ne sont pas acceptées. Choisis une photo fixe.")
                controle.verify()
            with Image.open(BytesIO(original)) as source:
                source.load()
                exif = source.getexif()
                exif_photo = exif.get_ifd(34665) if 34665 in exif else {}
                date_exif = next((str(tags.get(tag))[:64] for tags in (exif_photo, exif)
                                  for tag in (36867, 36868, 306) if tags.get(tag)), None)
                corrigee = ImageOps.exif_transpose(source)
                rgba = corrigee.convert("RGBA")
                propre = Image.new("RGB", rgba.size, "white")
                propre.paste(rgba, mask=rgba.getchannel("A"))
                largeur, hauteur = propre.size
                derives = {}
                for taille in (1600, 320):
                    reduite = propre.copy()
                    reduite.thumbnail((taille, taille), Image.Resampling.LANCZOS)
                    sortie = BytesIO()
                    reduite.save(sortie, format="JPEG", quality=88, optimize=True)
                    derives[taille] = sortie.getvalue()
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError("La photo est illisible, incomplète ou trop grande. Utilise un JPEG, PNG ou WebP valide de 40 millions de pixels maximum.") from exc
    empreinte = hashlib.sha256(original).hexdigest()
    return original, derives, {"sha256": empreinte, "format": format_image, "mime_original": FORMATS[format_image][1],
        "largeur": largeur, "hauteur": hauteur, "octets": len(original), "nom_fichier": nom, "date_exif": date_exif,
        "image_url": f"/app/img/contexte/{empreinte}-1600.jpg", "thumbnail_url": f"/app/img/contexte/{empreinte}-320.jpg"}


def _chemin(racine, relatif):
    cible = Path(racine).resolve() / relatif
    if cible.resolve() != cible.absolute():
        raise ValueError("Le stockage photo ne doit pas utiliser de lien vers un autre dossier.")
    return cible


def _ajouter_fichier(cible, contenu):
    """Ne remplace jamais un original ou aperçu existant ; vérifie son contenu."""
    cible.parent.mkdir(parents=True, exist_ok=True)
    if cible.exists():
        if cible.read_bytes() != contenu:
            raise ValueError("Un fichier photo de même empreinte possède un contenu différent. Aucun remplacement effectué.")
        return
    temporaire = cible.with_name(cible.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temporaire.open("xb") as fichier:
            fichier.write(contenu)
            fichier.flush()
            os.fsync(fichier.fileno())
        try:
            # Publication complète sans remplacement possible, y compris si
            # un autre processus a créé la cible entre-temps (NTFS/POSIX).
            os.link(temporaire, cible)
        except FileExistsError:
            if cible.read_bytes() != contenu:
                raise ValueError("Un fichier photo de même empreinte possède un contenu différent. Aucun remplacement effectué.")
    finally:
        temporaire.unlink(missing_ok=True)


def enregistrer(racine, recu, articles):
    """Valide une photo ou une annotation puis ajoute sa version au carnet."""
    if not isinstance(recu, dict):
        raise ValueError("La fiche photo reçue est incomplète.")
    edition = "id" in recu
    image_data = None if edition else _decoder_image(recu)
    # Le contenu lourd est remplacé par son empreinte dans la signature privée.
    requete = {k: v for k, v in recu.items() if k != "image_base64"}
    if image_data:
        requete["image_sha256"] = image_data[2]["sha256"]
    try:
        signature = hashlib.sha256(json.dumps(requete, sort_keys=True, ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()
    except (ValueError, TypeError, UnicodeEncodeError) as exc:
        raise ValueError("La fiche photo contient une valeur invalide.") from exc
    with verrou_donnees(Path(racine) / "donnees"):
        lignes = _lire(racine)
        deja = next((p for p in lignes if p.get("requete_id") == recu.get("requete_id")), None)
        if deja:
            if deja.get("requete_signature") != signature:
                raise ConflitPhoto("Cette requête a déjà enregistré une autre photo ou annotation.")
            return {"ok": True, "enregistre": True, "deja_enregistre": True, "photo": _vue(deja)}
        precedent = next((p for p in reversed(lignes) if p["id"] == recu.get("id")), None) if edition else None
        meta = _normaliser(recu, articles, precedent)
        if edition:
            if recu["revision"] != precedent["revision"]:
                raise ConflitPhoto("Cette photo a été annotée depuis l'ouverture de la fiche. Recharge la galerie.")
            photo = {**precedent, **meta, "revision": precedent["revision"] + 1, "operation": "annotation"}
        else:
            original, derives, image_meta = image_data
            # Deux envois de la même observation ne créent pas deux photos.
            doublon = next((p for p in lignes if p["operation"] == "ajout" and p["sha256"] == image_meta["sha256"]
                           and all(p.get(k) == v for k, v in meta.items())), None)
            if doublon:
                derniere = next(p for p in reversed(lignes) if p["id"] == doublon["id"])
                return {"ok": True, "enregistre": True, "deja_enregistre": True, "photo": _vue(derniere)}
            extension = FORMATS[image_meta["format"]][0]
            _ajouter_fichier(_chemin(racine, f"documents-partages/contexte-visuel/originaux/{image_meta['sha256']}.{extension}"), original)
            for taille, contenu in derives.items():
                _ajouter_fichier(_chemin(racine, f"app/img/contexte/{image_meta['sha256']}-{taille}.jpg"), contenu)
            photo = {**image_meta, **meta, "id": "photo:" + uuid.uuid4().hex, "revision": 1, "operation": "ajout"}
        photo.update(schema=1, type="photo-contexte", requete_id=recu["requete_id"], requete_signature=signature,
                     auteur="responsable-rayon", enregistre_le=datetime.now().isoformat(timespec="seconds"),
                     analyse_visuelle="non_realisee", commentaire_auto=_commentaire_auto(meta))
        append_jsonl(Path(racine) / "donnees" / "photos-contexte.jsonl", [photo])
        return {"ok": True, "enregistre": True, "deja_enregistre": False, "photo": _vue(photo)}
