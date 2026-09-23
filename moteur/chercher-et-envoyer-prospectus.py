"""
moteur/chercher-et-envoyer-prospectus.py
Recherche automatique, téléchargement, compilation PDF et envoi par e-mail
du dernier prospectus promotionnel Intermarché vers multimind.team@gmail.com.

Ce script est entièrement autonome et conçu pour être exécuté directement par Windows
(via Tâche planifiée Windows ou double-clic sur lancer-recherche-prospectus.bat),
sans aucune intervention requise de l'IA.

Dès réception de l'e-mail avec la pièce jointe PDF, la Tri-Sentinelle
(surveille-mail-message-comptage.py) détecte automatiquement l'événement MAIL
et déclenche le traitement par la brigade d'agents.
"""

import argparse
import io
import json
import os
import re
import smtplib
import ssl
import sys
from datetime import datetime, date
from email.message import EmailMessage
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
DONNEES = RACINE / "donnees"
DOSSIER_PROMO = RACINE / "Documents" / "Promo intermarche"
REGISTRE_ENVOIS = DONNEES / ".prospectus-derniers-envois.json"

sys.path.insert(0, str(RACINE / "moteur"))
from config_courrier import charger_config_courrier


def log(message):
    horodatage = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{horodatage}] {message}", flush=True)


def charger_registre():
    if REGISTRE_ENVOIS.exists():
        try:
            return json.loads(REGISTRE_ENVOIS.read_text(encoding="utf-8"))
        except Exception:
            return {"envois": []}
    return {"envois": []}


def enregistrer_envoi(identifiant, nom_fichier, sujet, destinataire):
    registre = charger_registre()
    registre["envois"].append({
        "identifiant": identifiant,
        "nom_fichier": nom_fichier,
        "sujet": sujet,
        "destinataire": destinataire,
        "envoye_le": datetime.now().isoformat(timespec="seconds")
    })
    REGISTRE_ENVOIS.parent.mkdir(parents=True, exist_ok=True)
    REGISTRE_ENVOIS.write_text(json.dumps(registre, ensure_ascii=False, indent=2), encoding="utf-8")


def deja_envoye(identifiant):
    registre = charger_registre()
    for e in registre.get("envois", []):
        if e.get("identifiant") == identifiant:
            return True
    return False


def decouvrir_catalogues_intermarche():
    """Découvre les catalogues Intermarché disponibles en ligne."""
    from curl_cffi import requests
    from bs4 import BeautifulSoup

    url_source = "https://anti-crise.fr/catalogue/"
    log(f"Recherche des catalogues sur {url_source}...")

    try:
        r = requests.get(url_source, impersonate="chrome124", timeout=15)
        if r.status_code != 200:
            log(f"Erreur HTTP {r.status_code} sur {url_source}")
            return []
    except Exception as exc:
        log(f"Impossible de contacter la source de catalogues : {exc}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    catalogues = []
    vus = set()

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "intermarche" in href.lower() and "catalogue" in href.lower() and href not in vus:
            # On privilégie la version Super (format de Carmaux), ou Contact / Hyper
            est_super = "version-super" in href.lower()
            est_contact = "version-contact" in href.lower()
            
            texte = a.get_text(strip=True) or href.rstrip("/").split("/")[-1]
            vus.add(href)
            catalogues.append({
                "url": href,
                "titre": texte,
                "priorite": 1 if est_super else (2 if est_contact else 3)
            })

    # Trier par priorité (Super en premier)
    catalogues.sort(key=lambda c: c["priorite"])
    return catalogues


def extraire_details_catalogue(url_catalogue):
    """Extrait le titre et les URLs des pages depuis la page flipbook."""
    from curl_cffi import requests

    log(f"Extraction des pages depuis {url_catalogue}...")
    try:
        r = requests.get(url_catalogue, impersonate="chrome124", timeout=20)
        if r.status_code != 200:
            log(f"Erreur HTTP {r.status_code} sur la page catalogue")
            return None
    except Exception as exc:
        log(f"Erreur de téléchargement de la page : {exc}")
        return None

    html = r.text
    # Recherche du bloc real3dflipbook contenant les pages
    m = re.search(r'var real3dflipbook_[a-zA-Z0-9_]+\s*=\s*"(.*?)";', html)
    if not m:
        log("Aucun lecteur flipbook trouvé sur cette page.")
        return None

    raw_str = m.group(1).replace(r'\"', '"').replace(r'\/', '/')
    try:
        data = json.loads(raw_str)
    except Exception as exc:
        log(f"Erreur de décodage du JSON flipbook : {exc}")
        return None

    nom = data.get("name", "Catalogue Intermarche")
    pages_raw = data.get("pages", [])
    if not pages_raw:
        log("Le catalogue ne contient aucune page.")
        return None

    pages = []
    for p in pages_raw:
        src = p.get("src", "").replace(r"\/", "/")
        if src:
            pages.append({
                "titre": p.get("title", ""),
                "src": src
            })

    # Détection des dates dans le nom ou l'URL
    # Ex: "du 22 septembre au 04 octobre 2026"
    date_slug = "prospectus"
    m_dates = re.search(r'du[ -](\d{1,2})[ -]([a-zA-Zéû]+)[ -]au[ -](\d{1,2})[ -]([a-zA-Zéû]+)[ -](\d{4})', nom, re.IGNORECASE)
    if not m_dates:
        m_dates = re.search(r'du[ -](\d{1,2})[ -]au[ -](\d{1,2})[ -]([a-zA-Zéû]+)[ -](\d{4})', nom, re.IGNORECASE)

    mois_map = {
        "janvier": "01", "fevrier": "02", "février": "02", "mars": "03", "avril": "04",
        "mai": "05", "juin": "06", "juillet": "07", "aout": "08", "août": "08",
        "septembre": "09", "octobre": "10", "novembre": "11", "decembre": "12", "décembre": "12"
    }

    if m_dates:
        groupes = m_dates.groups()
        if len(groupes) == 5:
            j1, m1_str, j2, m2_str, annee = groupes
            m1 = mois_map.get(m1_str.lower(), "09")
            m2 = mois_map.get(m2_str.lower(), "10")
            date_slug = f"{j1.zfill(2)}-{m1}-{annee}_{j2.zfill(2)}-{m2}-{annee}"
        elif len(groupes) == 4:
            j1, j2, m_str, annee = groupes
            m = mois_map.get(m_str.lower(), "09")
            date_slug = f"{j1.zfill(2)}-{m}-{annee}_{j2.zfill(2)}-{m}-{annee}"

    identifiant = f"{date_slug}_{nom}"
    return {
        "nom": nom,
        "identifiant": identifiant,
        "date_slug": date_slug,
        "pages": pages,
        "url_source": url_catalogue
    }


def telecharger_et_compiler_pdf(catalogue_info, max_pages=None):
    """Télécharge les images et compile le catalogue en fichier PDF."""
    from curl_cffi import requests
    from PIL import Image

    nom_fichier = f"{catalogue_info['date_slug']}_Prospectus_Super_Intermarche.pdf"
    chemin_pdf = DOSSIER_PROMO / nom_fichier
    DOSSIER_PROMO.mkdir(parents=True, exist_ok=True)

    if chemin_pdf.exists() and chemin_pdf.stat().st_size > 1_000_000 and not max_pages:
        log(f"Le fichier PDF existe déjà localement ({chemin_pdf.stat().st_size / (1024*1024):.2f} Mo) : réutilisation directe.")
        return chemin_pdf

    pages = catalogue_info["pages"]
    if max_pages and max_pages > 0:
        pages = pages[:max_pages]

    log(f"Téléchargement de {len(pages)} pages pour {nom_fichier}...")
    images = []

    for i, p in enumerate(pages, 1):
        src = p["src"]
        try:
            r = requests.get(src, impersonate="chrome124", timeout=20)
            if r.status_code == 200:
                im = Image.open(io.BytesIO(r.content)).convert("RGB")
                images.append(im)
                if i % 10 == 0 or i == len(pages):
                    log(f"  -> Page {i}/{len(pages)} téléchargée ({im.size[0]}x{im.size[1]}px)")
            else:
                log(f"  [!] Échec téléchargement page {i} (HTTP {r.status_code})")
        except Exception as exc:
            log(f"  [!] Erreur sur page {i} : {exc}")

    if not images:
        log("Aucune page n'a pu être téléchargée.")
        return None

    log(f"Compilation de {len(images)} pages en PDF : {chemin_pdf}...")
    try:
        images[0].save(
            chemin_pdf,
            save_all=True,
            append_images=images[1:],
            resolution=100.0,
            quality=85
        )
        taille_mo = chemin_pdf.stat().st_size / (1024 * 1024)
        log(f"PDF créé avec succès : {taille_mo:.2f} Mo")
        return chemin_pdf
    except Exception as exc:
        log(f"Erreur lors de la sauvegarde du PDF : {exc}")
        return None


def envoyer_par_mail(chemin_pdf, catalogue_info, destinataire="multimind.team@gmail.com"):
    """Envoie le fichier PDF du prospectus par e-mail SMTP sécurisé."""
    cfg = charger_config_courrier()
    expediteur = cfg.get("utilisateur")
    mot_de_passe = cfg.get("mot_de_passe")
    hote_smtp = cfg.get("smtp_host", "smtp.gmail.com")
    port_smtp = int(cfg.get("smtp_port", 587))

    if not expediteur or not mot_de_passe:
        log("Configuration e-mail incomplète (utilisateur ou mot de passe manquant).")
        return False

    taille_mo = chemin_pdf.stat().st_size / (1024 * 1024)
    sujet = f"[Prospectus Intermarché] Nouveau prospectus disponible — Demande d'intégration : {catalogue_info['nom']}"
    corps = f"""Bonjour la brigade numérique,

Un nouveau prospectus Intermarché est disponible et vient d'être récupéré automatiquement par la tâche planifiée Windows pour le magasin de Carmaux :

- Intitulé : {catalogue_info['nom']}
- Période : {catalogue_info['date_slug']}
- Fichier joint : {chemin_pdf.name} ({taille_mo:.2f} Mo)
- Source en ligne : {catalogue_info['url_source']}

DEMANDE D'INTÉGRATION POUR LES AGENTS :
1. Agent-courrier : certifier la pièce jointe PDF et vérifier son rangement dans Documents/Promo intermarche/.
2. Agent-rayon : identifier les pages Fruits & Légumes du prospectus, générer les aperçus haute définition (PNG) avec moteur/preparer-apercus-promotion.py, rapprocher les offres avec les codes articles ITM8 du catalogue magasin et mettre à jour donnees/promotions.json.
3. Agent-contrôle : vérifier la cohérence des dates d'application (début le mardi, visibilité dès le samedi), contrôler les rapprochements et attester la validité avant acquittement dans la Tri-Sentinelle.

Ce message est émis automatiquement par la tâche planifiée Windows du rayon Fruits & Légumes.

Bien cordialement,
Le Système de Préparation de Commande
"""

    message = EmailMessage()
    message["From"] = expediteur
    message["To"] = destinataire
    message["Subject"] = sujet
    message.set_content(corps)

    # Pièce jointe PDF
    donnees_pdf = chemin_pdf.read_bytes()
    message.add_attachment(
        donnees_pdf,
        maintype="application",
        subtype="pdf",
        filename=chemin_pdf.name
    )

    log(f"Envoi du mail à {destinataire} via {hote_smtp}:{port_smtp}...")
    contexte = ssl.create_default_context()

    try:
        with smtplib.SMTP(hote_smtp, port_smtp, timeout=30) as serveur:
            serveur.ehlo()
            serveur.starttls(context=contexte)
            serveur.ehlo()
            serveur.login(expediteur, mot_de_passe)
            serveur.send_message(message)
        log("E-mail envoyé avec succès !")
        return True
    except Exception as exc:
        log(f"Erreur lors de l'envoi SMTP : {exc}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Recherche et envoi automatique du prospectus Intermarché.")
    parser.add_argument("--destinataire", default="multimind.team@gmail.com", help="Adresse e-mail cible")
    parser.add_argument("--forcer", action="store_true", help="Force l'envoi même si déjà enregistré")
    parser.add_argument("--simuler", action="store_true", help="Télécharge et compile sans envoyer de courriel")
    parser.add_argument("--max-pages", type=int, default=None, help="Limite le nombre de pages à compiler")
    parser.add_argument("--silencieux", action="store_true", help="Mode silencieux pour tâche planifiée")
    parser.add_argument("--cron", action="store_true", help="Mode planifié (sans attente console)")
    args = parser.parse_args()

    log("=== Début de la recherche autonome de prospectus Intermarché ===")

    catalogues = decouvrir_catalogues_intermarche()
    if not catalogues:
        log("Aucun catalogue Intermarché trouvé.")
        return 0

    log(f"{len(catalogues)} catalogue(s) détecté(s).")
    
    # Sélectionner le catalogue prioritaire (Super)
    catalogue_choisi = None
    for cat in catalogues:
        info = extraire_details_catalogue(cat["url"])
        if info:
            catalogue_choisi = info
            break

    if not catalogue_choisi:
        log("Impossible d'extraire les détails d'un catalogue.")
        return 1

    log(f"Catalogue retenu : {catalogue_choisi['nom']}")
    identifiant = catalogue_choisi["identifiant"]

    if not args.forcer and deja_envoye(identifiant):
        log(f"Ce prospectus a déjà été envoyé précédemment ({identifiant}). Aucun renvoi nécessaire.")
        return 0

    # Compilation PDF
    chemin_pdf = telecharger_et_compiler_pdf(catalogue_choisi, max_pages=args.max_pages)
    if not chemin_pdf or not chemin_pdf.exists():
        log("Échec de la création du fichier PDF.")
        return 1

    if args.simuler:
        log(f"[SIMULATION] Fichier PDF disponible : {chemin_pdf}. Aucun e-mail n'a été envoyé.")
        return 0

    # Envoi par courriel
    succes = envoyer_par_mail(chemin_pdf, catalogue_choisi, destinataire=args.destinataire)
    if succes:
        enregistrer_envoi(identifiant, chemin_pdf.name, f"[Prospectus Intermarché] {catalogue_choisi['nom']}", args.destinataire)
        log("Opération terminée avec succès. La sentinelle va détecter le courriel.")
        return 0
    else:
        log("Échec de l'envoi du courriel.")
        return 2


if __name__ == "__main__":
    sys.exit(main())
