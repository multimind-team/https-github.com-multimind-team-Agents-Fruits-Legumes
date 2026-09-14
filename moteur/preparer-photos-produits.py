"""Prépare les photos produit ; jamais de rapprochement approximatif de code.

Usage : py -3.14 moteur/preparer-photos-produits.py [--racine <dossier>]
Les originaux et leur index restent privés et inchangés. Les vignettes et
photos.json sont des dérivés régénérables. Aucun prix/stock n'est modifié.
"""
import argparse
import hashlib
import io
import json
import os
import re
import tempfile
import unicodedata
from collections import Counter
from datetime import datetime
from pathlib import Path
from PIL import Image, ImageOps


def cle_libelle(texte):
    """Compare les noms sans altérer les sources ni les codes article.

    La barre de calibre '/' devient '-' dans les noms de fichiers Windows.
    Seules casse, normalisation Unicode et espaces sont neutralisés en plus.
    """
    return ' '.join(unicodedata.normalize('NFC', texte).upper().replace('/', '-').split())


def rapprocher(source, cadencier, proposition):
    libelle = cle_libelle(Path(source['filename']).stem)
    candidats = [a for a in cadencier['articles']
                 if any(cle_libelle(o['libelle']) == libelle for o in a.get('offres', []))]
    if len(candidats) != 1:
        return {'statut': 'ambigu' if candidats else 'sans-correspondance'}
    article = candidats[0]
    lignes = [l for l in proposition['lignes'] if l['libelle'] == article['nom']]
    if len(lignes) != 1:
        return {'statut': 'absent-ou-ambigu-proposition', 'nom': article['nom']}
    ligne = lignes[0]
    if ligne['itm8'] not in (article.get('article'), 'nom:' + article['nom']):
        return {'statut': 'code-incoherent', 'nom': article['nom']}
    return {'statut': 'exact-unique', 'itm8': ligne['itm8'], 'nom': article['nom']}


def ecrire_atomiquement(chemin, contenu):
    chemin.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=chemin.parent, delete=False) as fichier:
        temporaire = Path(fichier.name)
        fichier.write(contenu)
    try:
        temporaire.replace(chemin)
    finally:
        temporaire.unlink(missing_ok=True)


def preparer(racine):
    racine = Path(racine).resolve()
    dossier = racine / 'documents-partages/photos-produits'
    sources = [json.loads(l) for l in (dossier / 'sources.jsonl').read_text(encoding='utf8').splitlines() if l.strip()]
    cadencier = json.loads((racine / 'donnees/cadencier-du-jour.json').read_text(encoding='utf8'))
    proposition = json.loads((racine / 'donnees/proposition.json').read_text(encoding='utf8'))
    journal = dossier / 'associations-validees.jsonl'
    validations = (
        [json.loads(l) for l in journal.read_text(encoding='utf8').splitlines() if l.strip()]
        if journal.exists() else [])
    associations = {}
    codes_valides = set()
    for numero, a in enumerate(validations, 1):
        try:
            sha, code, libelle = a['sha256'], a['itm8'], a['libelle']
            if not re.fullmatch(r'[a-f0-9]{64}', sha):
                raise ValueError('empreinte invalide')
            if not (re.fullmatch(r'[0-9]{13}', code) or code == 'nom:' + libelle):
                raise ValueError('code invalide')
            if sha in associations or code in codes_valides:
                raise ValueError('doublon ou conflit de validation')
            origines = [s for s in sources if s['sha256'] == sha]
            if len(origines) != 1 or any(a['origine'][k] != origines[0][k]
                                         for k in ('source_id', 'path', 'filename')):
                raise ValueError('reference origine inconnue ou ambigue')
            lignes = [l for l in proposition['lignes'] if l['itm8'] == code]
            if len(lignes) != 1 or lignes[0]['libelle'] != libelle:
                raise ValueError('code/libelle absent ou ambigu dans la proposition')
            textes = [libelle, a['auteur'], a['validation']['source'], a['validation']['texte']]
            if not all(isinstance(t, str) and t.strip() for t in textes):
                raise ValueError('preuve de validation incomplete')
            if datetime.fromisoformat(a['date']).tzinfo is None:
                raise ValueError('date sans fuseau')
        except (KeyError, TypeError, ValueError) as erreur:
            raise ValueError(f'Association humaine ligne {numero} invalide : {erreur}') from erreur
        associations[sha] = a
        codes_valides.add(code)
    uniques = {}
    correspondances = []
    # Contrôle complet du lot avant publication ; noms de pièce jointe jamais
    # utilisés comme chemins de sortie. Pas de lecture hors du dossier privé.
    for source in sources:
        empreinte = source['sha256']
        chemin = (racine / source['path']).resolve()
        if not chemin.is_file():
            for candidat in (dossier / 'originaux' / 'Fruits' / 'Fruits exotiques' / chemin.name,
                             dossier / 'originaux' / 'Fruits' / 'Legumes exotiques' / chemin.name,
                             dossier / 'originaux' / 'legumes' / chemin.name,
                             dossier / 'originaux' / 'Fruits' / chemin.name,
                             dossier / 'originaux' / chemin.name):
                if candidat.is_file():
                    chemin = candidat
                    break
            else:
                candidats = [c for c in (dossier / 'originaux').rglob(chemin.name) if c.is_file()]
                if candidats:
                    chemin = candidats[0]
        if not re.fullmatch(r'[a-f0-9]{64}', empreinte) or not chemin.is_relative_to(dossier):
            raise ValueError('Source photo ou empreinte invalide')
        contenu = chemin.read_bytes()
        if hashlib.sha256(contenu).hexdigest() != empreinte:
            raise ValueError('L’empreinte de la photo ne correspond pas à l’original')
        with Image.open(io.BytesIO(contenu)) as image:
            image.verify()
        uniques[empreinte] = contenu
        association = associations.get(empreinte)
        resultat = ({'statut': 'validation-humaine', 'itm8': association['itm8'],
                     'nom': association['libelle']} if association else rapprocher(source, cadencier, proposition))
        correspondances.append({**source, **resultat})

    # Une offre du jour disparue ne retire pas une correspondance exacte déjà
    # publiée et prouvée par le rapport privé. Ce n'est pas une validation humaine.
    public_precedent = racine / 'donnees/photos.json'
    rapport_precedent = dossier / 'rapport-correspondances.json'
    anciens = (json.loads(public_precedent.read_text(encoding='utf8'))['articles']
               if public_precedent.exists() else {})
    rapport_octets = rapport_precedent.read_bytes() if rapport_precedent.exists() else b''
    precedentes = json.loads(rapport_octets)['correspondances'] if rapport_octets else []
    acceptes = ('exact-unique', 'validation-humaine', 'exact-historique')
    archives = {}
    for code, photo in anciens.items():
        candidats = [c for c in correspondances
                     if photo['src'] == f"app/img/produits/{c['sha256']}-240.webp"
                     and photo['miniature'] == f"app/img/produits/{c['sha256']}-96.webp"]
        lignes = [l for l in proposition['lignes'] if l['itm8'] == code]
        if len(candidats) != 1 or len(lignes) != 1 or lignes[0]['libelle'] != photo['libelle']:
            raise ValueError(f'Photo deja attribuee non preservable : {code}')
        c = candidats[0]
        if c['statut'] in acceptes:
            if c['itm8'] != code or c['nom'] != photo['libelle']:
                raise ValueError(f'Conflit avec photo deja attribuee : {code}')
            continue
        preuves = [p for p in precedentes if p.get('itm8') == code
                   and p.get('nom') == photo['libelle']
                   and p.get('statut') in ('exact-unique', 'exact-historique')
                   and all(p.get(k) == c.get(k) for k in ('sha256', 'path', 'filename', 'source_id'))]
        if len(preuves) != 1:
            raise ValueError(f'Preuve exacte historique absente ou ambigue : {code}')
        c.update(statut='exact-historique', itm8=code, nom=photo['libelle'],
                 preuve_exacte=preuves[0].get('preuve_exacte') or {
                     'rapport_sha256': hashlib.sha256(rapport_octets).hexdigest(),
                     'statut': 'exact-unique'})
        sha_rapport = c['preuve_exacte']['rapport_sha256']
        if not re.fullmatch(r'[a-f0-9]{64}', sha_rapport):
            raise ValueError('Empreinte de preuve historique invalide')
        archive = dossier / 'historique' / (sha_rapport + '.json')
        contenu_archive = archive.read_bytes() if archive.exists() else rapport_octets
        if hashlib.sha256(contenu_archive).hexdigest() != sha_rapport:
            raise ValueError(f'Archive historique absente ou alteree : {code}')
        preuves_archive = [p for p in json.loads(contenu_archive)['correspondances']
                           if p.get('statut') == 'exact-unique' and p.get('itm8') == code
                           and p.get('nom') == photo['libelle']
                           and all(p.get(k) == c.get(k) for k in ('sha256', 'path', 'filename', 'source_id'))]
        if len(preuves_archive) != 1:
            raise ValueError(f'Archive sans preuve exacte unique : {code}')
        if not archive.exists():
            archives[archive] = contenu_archive

    comptes = Counter(c['itm8'] for c in correspondances if c['statut'] in acceptes)
    for code, nombre in comptes.items():
        if nombre > 1 and (code in codes_valides or code in anciens):
            raise ValueError(f'collision de photos pour un article protege : {code}')
    # Création exclusive, jamais de réécriture d'une preuve historique privée.
    for archive, contenu in archives.items():
        archive.parent.mkdir(parents=True, exist_ok=True)
        with archive.open('xb') as fichier:
            fichier.write(contenu)
            fichier.flush()
            os.fsync(fichier.fileno())
    variantes = {}
    taille_derivee = 0
    for empreinte, contenu in uniques.items():
        variantes[empreinte] = {}
        with Image.open(io.BytesIO(contenu)) as original:
            image = ImageOps.exif_transpose(original).convert('RGB')
            for bord in (96, 240):
                vignette = image.copy()
                vignette.thumbnail((bord, bord), Image.Resampling.LANCZOS)
                buffer = io.BytesIO()
                vignette.save(buffer, format='WEBP', quality=78, method=6)
                chemin = f'app/img/produits/{empreinte}-{bord}.webp'
                ecrire_atomiquement(racine / chemin, buffer.getvalue())
                taille_derivee += len(buffer.getvalue())
                variantes[empreinte][bord] = {'chemin': chemin, 'largeur': vignette.width, 'hauteur': vignette.height}

    articles = {}
    for c in correspondances:
        if c['statut'] not in acceptes:
            continue
        if comptes[c['itm8']] != 1:
            c['statut'] = 'plusieurs-photos-pour-article'
            continue
        variantes_photo = variantes[c['sha256']]
        grande = variantes_photo[240]
        articles[c['itm8']] = {
            'libelle': c['nom'], 'src': grande['chemin'],
            'miniature': variantes_photo[96]['chemin'],
            'largeur': grande['largeur'], 'hauteur': grande['hauteur'],
        }
    bilan = {'sources': len(sources), 'images_uniques': len(uniques),
             'articles_illustres': len(articles),
             'statuts': dict(Counter(c['statut'] for c in correspondances)),
             'octets_originaux': sum(map(len, uniques.values())),
             'octets_variantes': taille_derivee}
    sortie = {'version': 1, 'note': 'Photos indicatives reçues par mail ; le libellé et le conditionnement font foi.',
              'articles': articles}
    ecrire_atomiquement(racine / 'donnees/photos.json', json.dumps(sortie, ensure_ascii=False, indent=1).encode('utf8'))
    ecrire_atomiquement(dossier / 'rapport-correspondances.json', json.dumps(
        {'bilan': bilan, 'correspondances': correspondances}, ensure_ascii=False, indent=1).encode('utf8'))
    return bilan


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--racine', type=Path, default=Path(__file__).resolve().parents[1])
    arguments = parser.parse_args()
    print(json.dumps(preparer(arguments.racine), ensure_ascii=False, indent=2))
