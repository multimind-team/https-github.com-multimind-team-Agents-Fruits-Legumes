"""
Le serveur local de preparation-commande.

Il sert les pages et les carnets, et sait recevoir ce que l'écran de comptage
lui envoie. Rien de plus : tout ce qui demande du jugement est le travail des
agents, pas le sien.

Lancer : python moteur/serveur.py [port]   (par défaut 8751)
"""
import json
import math
import re
import subprocess
import sys
import threading
import uuid
from datetime import date, datetime
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from io import BytesIO
from contextlib import nullcontext
from pathlib import Path
from urllib.parse import quote, unquote, urlparse
sys.path.insert(0, str(Path(__file__).resolve().parent))
from verrou_donnees import append_jsonl, environnement_verrou, verrou_donnees
from ecriture_derivee import publier_etat_calcul

RACINE = Path(__file__).resolve().parent.parent
DONNEES = RACINE / "donnees"
DOSSIER_FAITS = DONNEES / "faits"
JOURNAL = DONNEES / "journal.jsonl"
HOTE_TAILSCALE = "desktop-11kv59v.tail44b4ba.ts.net"
MAX_CORPS_JSON = 1024 * 1024
DONNEES_PUBLIQUES = {
    "articles.json", "ajustements.jsonl", "decisions.jsonl", "etat.json", "fraicheur.json",
    "journal.jsonl", "messages.jsonl", "note-du-matin.json", "promotions.json",
    "proposition.json", "reponses.jsonl", "photos.json",
    "analyse-ventes-annuelle-saisonniere.json", "profils-produits-sensibilites.json",
    "alertes-marges.json", "recalcul.json",
}
APP_PUBLIQUE = {
    "/app/index.html", "/app/commander.html", "/app/compter.html",
    "/app/promo.html", "/app/maintenance.html",
    "/app/analyse-historique.html",
    "/app/manifest.json", "/app/css/charte.css", "/app/img/favicon.ico",
    "/app/js/photos-produits.js",
    "/app/img/icone-192.png", "/app/img/icone-512.png",
}


_RESUMES_CARNETS = {}


def resume_carnets():
    """Statistiques de taille, en cache selon l'empreinte filesystem du carnet."""
    fichiers = []
    with verrou_donnees(DONNEES):
        for chemin in sorted(DOSSIER_FAITS.glob("[0-9][0-9][0-9][0-9].jsonl")):
            if not chemin.is_file() or chemin.resolve() != chemin.absolute():
                continue
            stat = chemin.stat()
            signature = (stat.st_mtime_ns, stat.st_size)
            cle = str(chemin.resolve())
            precedent = _RESUMES_CARNETS.get(cle)
            if not precedent or precedent[0] != signature:
                with chemin.open("rb") as flux:
                    lignes = sum(1 for ligne in flux if ligne.strip())
                _RESUMES_CARNETS[cle] = (signature, lignes)
            fichiers.append({"annee": chemin.stem, "fichier": chemin.name,
                             "lignes": _RESUMES_CARNETS[cle][1], "octets": stat.st_size})
    return {"ok": True, "fichiers": fichiers,
            "total_lignes": sum(f["lignes"] for f in fichiers),
            "total_octets": sum(f["octets"] for f in fichiers)}


def marges_pomona_disponibles():
    """Liste les classeurs remplis, pas une preuve de validation ou d'envoi."""
    from openpyxl import load_workbook

    dossier = RACINE / "documents-partages" / "calcul-marge-pomona"
    fichiers, indisponibles = [], 0
    for cible in dossier.glob("*.xlsx"):
        nom = re.fullmatch(
            r"(0[1-9]|1[0-2])([0-9]{2}) Calcul marge Pomona"
            r"(?: - livraison [0-9]{2}-[0-9]{2}-[0-9]{4})?\.xlsx", cible.name)
        if not nom or cible.resolve() != cible.absolute() or not cible.is_file():
            continue
        try:
            jours = []
            with cible.open("rb") as source:
                classeur = load_workbook(source, read_only=True, data_only=False)
                try:
                    for feuille in classeur:
                        if not re.fullmatch(r"[0-9]{2}", feuille.title):
                            continue
                        try:
                            jour = date(2000 + int(nom[2]), int(nom[1]), int(feuille.title))
                        except ValueError:
                            continue
                        if any(isinstance(ligne[0], str) and ligne[0].strip()
                               and not ligne[0].startswith("=")
                               and isinstance(ligne[5], (int, float))
                               and not isinstance(ligne[5], bool) and ligne[5] > 0
                               for ligne in feuille.iter_rows(min_row=4, max_col=6, values_only=True)):
                            jours.append(jour.isoformat())
                finally:
                    classeur.close()
            if jours:
                fichiers.append({
                    "nom": cible.name, "jours": sorted(jours),
                    "url": "/documents-partages/calcul-marge-pomona/" + quote(cible.name),
                    "octets": cible.stat().st_size,
                })
        except Exception:
            # Une copie en cours ou un fichier illisible ne devient jamais un
            # lien déclaré prêt ; le nombre d'échecs est visible dans l'écran.
            indisponibles += 1
    fichiers.sort(key=lambda f: (f["jours"][-1], f["nom"]), reverse=True)
    return {"fichiers": fichiers, "indisponibles": indisponibles}


def commande_reponse_message(identifiant, texte):
    """Construit la commande agent sans jamais interpréter le texte en shell."""
    return [
        sys.executable, str(RACINE / "moteur" / "repondre-message-rayon.py"),
        "--id", str(identifiant), "--texte", str(texte),
    ]


def decoder_requete_json(corps):
    """Lit un corps JSON et retourne une erreur utilisable par le responsable."""
    def refuser_constante(valeur):
        raise ValueError("Nombre non fini")

    def objet_unique(paires):
        objet = {}
        for cle, valeur in paires:
            if cle in objet:
                raise ValueError("Clé répétée")
            objet[cle] = valeur
        return objet

    try:
        objet = json.loads(corps.decode("utf-8"), parse_constant=refuser_constante,
                           object_pairs_hook=objet_unique)
        if not isinstance(objet, dict):
            raise ValueError("Objet attendu")
        return objet
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise ValueError("Le message reçu est illisible. Vérifie la connexion puis réessaie.") from exc


def normaliser_messages(messages):
    """Valide le lot entier avant même d'ouvrir le carnet en ajout."""
    if not isinstance(messages, list) or len(messages) > 100:
        raise ValueError("Envoie une liste de 100 messages au maximum.")
    resultat = []
    for message in messages:
        if not isinstance(message, dict):
            raise ValueError("Un message reçu est incomplet.")
        texte = message.get("texte")
        if not isinstance(texte, str) or not texte.strip() or len(texte) > 10000:
            raise ValueError("Chaque message doit contenir entre 1 et 10000 caractères.")
        try:
            texte.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ValueError("Un message contient un caractère illisible.") from exc
        horodatage = message.get("ecrit_le")
        if not isinstance(horodatage, str) or not re.fullmatch(
                r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?(?:Z|[+-][0-9]{2}:[0-9]{2})?", horodatage):
            raise ValueError("La date d'un message est invalide.")
        try:
            datetime.fromisoformat(horodatage)
        except ValueError as exc:
            raise ValueError("La date d'un message est invalide.") from exc
        resultat.append({"texte": texte.strip(), "ecrit_le": horodatage})
    return resultat


def charger_articles_comptables():
    """Retourne le référentiel produit publié par la liste de comptage et la proposition."""
    articles = {}
    chemin_articles = DONNEES / "articles.json"
    if chemin_articles.exists():
        try:
            contenu = json.loads(chemin_articles.read_text(encoding="utf-8"))
            articles.update({str(a.get("itm8")): a for a in contenu.get("articles", []) if a.get("itm8")})
        except Exception:
            pass
    chemin_prop = DONNEES / "proposition.json"
    if chemin_prop.exists():
        try:
            prop = json.loads(chemin_prop.read_text(encoding="utf-8"))
            for l in prop.get("lignes", []):
                code = str(l.get("itm8") or "")
                if code and code not in articles:
                    articles[code] = {
                        "itm8": code,
                        "libelle": str(l.get("libelle") or ""),
                        "conditionnement": float(l.get("conditionnement") or 1.0),
                        "unite": str(l.get("unite") or "colis"),
                    }
        except Exception:
            pass
    return articles


def publier_proposition(proposition):
    """Une projection temporaire ratée ne doit jamais tronquer la version lisible."""
    chemin = DONNEES / "proposition.json"
    temporaire = chemin.with_name("proposition-" + uuid.uuid4().hex + ".tmp")
    try:
        temporaire.write_text(json.dumps(proposition, ensure_ascii=False, allow_nan=False, indent=1), encoding="utf-8")
        temporaire.replace(chemin)
    finally:
        temporaire.unlink(missing_ok=True)


def article_de_decision(recu, avec_conditionnement=False):
    itm8 = recu.get("itm8")
    if (not isinstance(itm8, str) or itm8 != itm8.strip()
            or not re.fullmatch(r"(?:[0-9]{13}|nom:[^\x00-\x1f\x7f]{1,200})", itm8)):
        raise ValueError("Le code de l'article reçu est invalide.")
    proposition = json.loads((DONNEES / "proposition.json").read_text(encoding="utf-8"))
    articles = [a for a in proposition.get("lignes", []) if a.get("itm8") == itm8]
    article = articles[0] if articles else None
    if article is None:
        raise ValueError("Cet article est inconnu de la proposition. Recharge la page.")
    if avec_conditionnement:
        if len(articles) != 1:
            raise ValueError("Cet article apparaît plusieurs fois : colisage ambigu. Fais vérifier la proposition.")
        libelle = article.get("libelle")
        if (not isinstance(libelle, str) or not libelle.strip()
                or any(ord(c) < 32 or ord(c) == 127 for c in libelle)):
            raise ValueError("Le libellé de l'article n'est pas fiable. Fais vérifier la proposition.")
        libelle.encode("utf-8")
        return itm8, libelle, nombre_conditionnement(article.get("conditionnement"))
    return itm8, str(article.get("libelle") or itm8)


def nombre_conditionnement(valeur):
    """Nombre JSON strict : le CLI historique accepte aussi des chaînes."""
    try:
        if type(valeur) not in (int, float):
            raise ValueError
        nombre = float(valeur)
        if not math.isfinite(nombre) or nombre <= 0:
            raise ValueError
        return nombre
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Le colisage doit être un nombre fini strictement positif.") from exc


def decision_conditionnement_effective(itm8):
    """Même temporalité/annulations que regles, sans ses chemins globaux."""
    def lire(chemin):
        if not chemin.exists():
            return []
        contenu = chemin.read_bytes()
        if contenu and not contenu.endswith(b"\n"):
            raise ValueError("Carnet incomplet : dernière ligne non terminée.")
        return [decoder_requete_json(l) for l in contenu.splitlines() if l.strip()]

    jour = datetime.now().date().isoformat()
    decisions = lire(DONNEES / "decisions.jsonl")
    for decision in decisions:
        debut = decision.get("valide_a_partir_de")
        if debut is not None:
            if (not isinstance(debut, str)
                    or datetime.strptime(debut, "%Y-%m-%d").date().isoformat() != debut):
                raise ValueError("Date de décision invalide.")
    decisions = [d for d in decisions if (d.get("valide_a_partir_de") or "") <= jour]
    annulees = {d["annule"] for d in decisions if d.get("type") == "annulation" and d.get("annule")}
    actions_annulees = {l["annule_action"] for l in lire(DONNEES / "journaux" / "tout.jsonl")
                       if l.get("annule_action") and l.get("resultat") == "ok"
                       and l.get("horodatage", "")[:10] <= jour}
    decision = next((d for d in reversed(decisions)
                 if d.get("type") == "conditionnement" and d.get("article") == itm8
                 and d.get("id") not in annulees and d.get("action") not in actions_annulees), None)
    if decision is not None:
        valeur = decision.get("valeur")
        if valeur is None or valeur is False:
            return None  # retrait de surcharge, comme regles.charger
        if isinstance(valeur, bool):
            return None
        try:
            nombre_conditionnement(float(valeur))  # le CLI historique écrit des chaînes
        except (TypeError, ValueError, OverflowError):
            return None  # conditionnements.selectionner ignore cette surcharge invalide
    return decision


def normaliser_comptage(recu, articles):
    """Refuse les données client incohérentes et reconstruit le fait fiable.

    Le téléphone ne décide ni du libellé, ni du conditionnement, ni de
    l'identifiant durable : ces valeurs viennent du référentiel local.
    """
    if not isinstance(recu, dict):
        raise ValueError("Le comptage reçu est incomplet.")
    if "cible_id" in recu or ("type" in recu and recu["type"] != "comptage"):
        raise ValueError("Cette route reçoit une nouvelle mesure physique, pas une correction historique. "
                         "Conserve la demande de correction pour vérification explicite.")
    jour = recu.get("date")
    if not isinstance(jour, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", jour):
        raise ValueError("La date de comptage est invalide.")
    try:
        date_comptee = datetime.strptime(str(jour), "%Y-%m-%d").date()
    except (TypeError, ValueError) as exc:
        raise ValueError("La date de comptage est invalide.") from exc
    if date_comptee != datetime.now().date():
        raise ValueError("La date de comptage doit être celle du jour.")

    itm8 = recu.get("itm8")
    if not isinstance(itm8, str) or not re.fullmatch(r"(?:[0-9]{13}|nom:[^\x00-\x1f\x7f]{1,200})", itm8):
        raise ValueError("Cet article est inconnu de la liste de comptage.")
    article = articles.get(itm8)
    if not article:
        raise ValueError("Cet article est inconnu de la liste de comptage.")
    try:
        if type(recu.get("colis")) not in (int, float):
            raise ValueError
        colis = float(recu.get("colis"))
    except (TypeError, ValueError) as exc:
        raise ValueError("Le nombre de colis est invalide.") from exc
    if not math.isfinite(colis):
        raise ValueError("Le nombre de colis doit être un nombre fini.")
    if abs(colis) > 9999:
        raise ValueError("Le nombre de colis dépasse la limite saisissable.")
    conditionnement = float(article.get("conditionnement"))
    if not math.isfinite(conditionnement) or conditionnement <= 0:
        raise ValueError("Le conditionnement de cet article est invalide.")
    if "conditionnement" in recu:
        saisi = nombre_conditionnement(recu["conditionnement"])
        if saisi != conditionnement:
            raise ValueError(f"{article.get('libelle') or itm8} ({itm8}) : colisage du comptage {saisi:g}, "
                             f"colisage actuel {conditionnement:g}. Rien n'a été reconverti : conserve le relevé "
                             "et vérifie le colisage avant de le renvoyer.")
    quantite = round(colis * conditionnement, 3)
    if not math.isfinite(quantite):
        raise ValueError("La quantité calculée est invalide. Fais vérifier le conditionnement.")

    horodatage = recu.get("saisi_le")
    try:
        if not isinstance(horodatage, str) or not re.fullmatch(
                r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?(?:Z|[+-][0-9]{2}:[0-9]{2})?", horodatage):
            raise ValueError
        saisi_le = datetime.fromisoformat(horodatage)
        if saisi_le.date() != date_comptee:
            raise ValueError
    except ValueError as exc:
        raise ValueError("L'heure de saisie du comptage est invalide ou ne correspond pas au jour compté.") from exc
    return {
        # L'ancien ID client article/jour reste accepté, mais l'identité
        # durable distingue les instants physiques sans dépendre de la valeur.
        "id": f"comptage:{jour}:{itm8}:mesure:{saisi_le.isoformat()}",
        "type": "comptage",
        "mesure": "position",
        "origine_mesure": "ecran-comptage",
        "date_source": jour,
        "date_effet": jour,
        "article": itm8,
        "article_source": itm8,
        "quantite": quantite,
        "colis": colis,
        "conditionnement": conditionnement,
        "unite": str(article.get("unite") or "inconnue"),
        "libelle": str(article.get("libelle") or ""),
        "horodatage": saisi_le.isoformat(),
        "motif": "Position relevée en chambre froide, rayon déjà rempli.",
        "source": {"origine": "app/compter.html", "saisi_le": horodatage or None},
        "enregistre_le": datetime.now().isoformat(timespec="seconds"),
    }


def lancer_reponse_message(identifiant, texte):
    """Déclenche le traitement du message sans bloquer la réponse HTTP de l'application."""
    processus = subprocess.Popen(
        commande_reponse_message(identifiant, texte),
        cwd=RACINE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )

    def vider_sortie():
        if processus.stdout:
            for _ in processus.stdout:
                pass
        processus.wait()

    threading.Thread(target=vider_sortie, daemon=True).start()
    return processus.pid


sys.path.insert(0, str(Path(__file__).resolve().parent))
def journaliser(agent, message, motif, details=None):
    """Le journal n'est jamais tronqué, et tout changement porte son motif."""
    evenement = {
        "horodatage": datetime.now().isoformat(timespec="seconds"),
        "agent": agent,
        "message": message,
        "motif": motif,
    }
    if details is not None:
        evenement["details"] = details
    try:
        JOURNAL.parent.mkdir(parents=True, exist_ok=True)
        append_jsonl(JOURNAL, [evenement])
    except Exception as exc:
        print(f"Journal serveur indisponible : {type(exc).__name__}", file=sys.stderr)


def lire_comptages(chemin):
    """Relevés et corrections bruts : une correction ne devient pas une mesure."""
    if not chemin.exists():
        return
    contenu = chemin.read_bytes()
    if contenu and not contenu.endswith(b"\n"):
        raise ValueError("Carnet incomplet : dernière ligne non terminée. Aucun comptage ajouté.")
    for ligne in contenu.splitlines():
        if not ligne.strip():
            continue
        fait = decoder_requete_json(ligne)
        if fait.get("type") in {"comptage", "correction-comptage"}:
            yield fait


_recalcul_en_cours = threading.Lock()
_recalcul_etat = threading.Lock()
_recalcul_demande = False
_recalcul_actif = False
_ecriture_faits = threading.Lock()
_ecriture_messages = threading.Lock()


def recalculer_en_arriere_plan():
    """Recalcule la position de chaque article et la liste de comptage, APRÈS
    avoir répondu au téléphone.

    Pourquoi en arrière-plan : le recalcul prend environ 2 secondes. Devant la
    porte de la chambre froide, avec un réseau capricieux, faire attendre le
    téléphone 2 secondes de plus, c'est prendre le risque que la connexion
    lâche alors que tout est déjà enregistré.

    Pourquoi c'est indispensable : sans lui, les positions comptées le soir
    n'apparaîtraient nulle part, et l'écran de comptage réafficherait le
    lendemain des valeurs attendues périmées.

    Depuis le 2026-09-04, régénère aussi proposition.json : le responsable de rayon peut
    corriger une position directement depuis l'écran de commande (pas
    seulement le soir en chambre froide), et veut voir l'effet tout de suite
    sur la quantité proposée, sans attendre le lendemain.
    """
    global _recalcul_demande, _recalcul_actif
    with _recalcul_etat:
        _recalcul_demande = True
        if _recalcul_actif:
            return
        _recalcul_actif = True

    def une_passe():
        with _recalcul_en_cours, verrou_donnees(DONNEES):
            try:
                publier_etat_calcul(DONNEES, "en-cours", "serveur")
                for script in ("calculer-position.py", "generer-proposition.py", "preparer-liste-comptage.py"):
                    resultat = subprocess.run(
                        [sys.executable, str(RACINE / "moteur" / script)],
                        capture_output=True, text=True, timeout=120,
                        env=environnement_verrou(DONNEES))
                    if resultat.returncode != 0:
                        publier_etat_calcul(DONNEES, "echec", "serveur",
                                           f"Le calcul {script} a échoué ; relancer le recalcul complet.")
                        journaliser("serveur", f"Echec du recalcul ({script})",
                                    "Les faits sont enregistrés ; les sorties peuvent être partiellement actualisées. "
                                    "Le recalcul complet doit être relancé.",
                                    {"erreur": (resultat.stderr or "")[-400:]})
                        return
                publier_etat_calcul(DONNEES, "termine", "serveur")
                journaliser("serveur", "Positions recalculées après réception des comptages",
                            "Les positions, la proposition et la liste de comptage sont recalculées ensemble.")
            except Exception as exc:
                try:
                    publier_etat_calcul(DONNEES, "echec", "serveur",
                                       "Le recalcul a été interrompu ; relancer le calcul complet.")
                except Exception as statut:
                    print(f"Statut de recalcul indisponible : {type(statut).__name__}", file=sys.stderr)
                journaliser("serveur", "Echec du recalcul automatique",
                            "Les faits sont enregistrés, mais le recalcul complet n'est pas confirmé.",
                            {"erreur": str(exc)})

    def travail():
        global _recalcul_demande, _recalcul_actif
        while True:
            with _recalcul_etat:
                if not _recalcul_demande:
                    _recalcul_actif = False
                    return
                _recalcul_demande = False
            # Un nouvel envoi pendant cette passe impose une passe supplémentaire.
            try:
                une_passe()
            except Exception as exc:
                with _recalcul_etat:
                    _recalcul_actif = False
                print(f"Recalcul non démarré : {type(exc).__name__}. Relance nécessaire.", file=sys.stderr)
                return

    try:
        threading.Thread(target=travail, daemon=True).start()
    except Exception:
        with _recalcul_etat:
            _recalcul_actif = False
        raise


class Gestionnaire(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(RACINE), **kwargs)

    def log_message(self, format, *args):
        pass   # pas de bruit dans la console

    def do_GET(self):
        return super().do_GET()

    def end_headers(self):
        # Les URL CSS/JS sont versionnées dans le HTML : celui-ci doit être
        # revalidé, y compris après un 304. Ne touche pas au stockage des saisies.
        if (self.command in ("GET", "HEAD")
                and getattr(self, "_fichier_public", "").endswith(".html")):
            self.send_header("Cache-Control", "no-cache")
        if getattr(self, "_marge_publique", False):
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Disposition", "attachment; filename*=UTF-8''" +
                             quote(Path(self._fichier_public).name))
        return super().end_headers()

    def send_head(self):
        self._marge_publique = False
        self._fichier_public = ""
        if not self._verifier_provenance():
            return None
        # Point commun GET/HEAD : une vérification dans do_GET seul est contournable.
        try:
            url = urlparse(self.path)
            chemin = unquote(url.path, errors="strict")
            parties = chemin.split("/")[1:]
            if (url.scheme or url.netloc or not chemin.startswith("/")
                    or any(c in chemin for c in "\\:%\x00")
                    or any(ord(c) < 32 for c in chemin)
                    or any(p in ("", ".", "..") or p.endswith((" ", ".")) for p in parties)):
                raise ValueError
            statut_absent = chemin == "/donnees/recalcul.json" and not (DONNEES / "recalcul.json").is_file()
            if chemin in {"/api/marges-pomona", "/api/carnets/resume"} or statut_absent:
                if statut_absent:
                    charge = {"etat": "absent"}
                else:
                    charge = marges_pomona_disponibles() if chemin == "/api/marges-pomona" else resume_carnets()
                contenu = json.dumps(charge, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(contenu)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(contenu)
                return None
            if chemin == "/favicon.ico":
                self.path = "/app/img/favicon.ico"
                chemin = self.path
            marge_publique = False
            if chemin.startswith("/documents-partages/calcul-marge-pomona/"):
                autorises = {unquote(f["url"]) for f in marges_pomona_disponibles()["fichiers"]}
                marge_publique = chemin in autorises
            publie = (
                marge_publique
                or chemin in APP_PUBLIQUE
                or (chemin.startswith("/donnees/") and chemin[9:] in DONNEES_PUBLIQUES)
                or re.fullmatch(r"/donnees/faits/[0-9]{4}\.jsonl", chemin)
                or re.fullmatch(r"/app/img/produits/[a-f0-9]{64}-(?:96|240)\.webp", chemin)
                or (chemin.startswith("/Documents/Promo intermarche/")
                    and chemin.lower().endswith((".pdf", ".png"))))
            cible = RACINE.joinpath(*chemin.split("/")[1:])
            # Les liens/jonctions ne doivent pas ouvrir une autre zone du projet.
            if not publie or cible.resolve() != cible.absolute() or not cible.is_file():
                raise ValueError
            self._fichier_public = str(cible)
            self._marge_publique = marge_publique
        except (ValueError, OSError):
            self.send_error(404, "Ressource non publiée.")
            return None
        # Ouvrir chaque dérivé après la fin du lot en cours. Le statut reste
        # consultable pendant le calcul pour que l'interface puisse le signaler.
        cible = Path(self._fichier_public)
        if cible.parent == DONNEES and cible.suffix == ".json":
            with (nullcontext() if cible.name == "recalcul.json" else verrou_donnees(DONNEES)):
                flux = super().send_head()
                if flux is None:
                    return None
                # Sous Windows, un handle disque encore ouvert empêcherait le
                # remplacement atomique suivant pendant un téléchargement lent.
                with flux:
                    return BytesIO(flux.read())
        return super().send_head()

    def translate_path(self, path):
        # Ne pas laisser SimpleHTTPRequestHandler décoder une seconde fois l'URL.
        return self._fichier_public

    def do_POST(self):
        if not self._verifier_provenance(ecriture=True):
            return
        chemin = self.path.split("?")[0]
        if chemin not in {"/api/comptages", "/api/messages", "/api/masquer", "/api/fournisseur", "/api/conditionnement"}:
            self.send_error(404)
            return
        self._charge_json = self._lire_json()
        if self._charge_json is None:
            return
        if chemin == "/api/comptages":
            with verrou_donnees(DONNEES):
                self._recevoir_comptages()
            return
        if chemin == "/api/messages":
            self._recevoir_messages()
            return
        if chemin == "/api/masquer":
            with _recalcul_en_cours, verrou_donnees(DONNEES):
                self._masquer_demasquer()
            return
        if chemin == "/api/fournisseur":
            with _recalcul_en_cours, verrou_donnees(DONNEES):
                self._changer_fournisseur()
            return
        if chemin == "/api/conditionnement":
            with _recalcul_en_cours, verrou_donnees(DONNEES):
                try:
                    self._changer_conditionnement()
                except (OSError, ValueError, TypeError, KeyError, OverflowError, AttributeError):
                    self._repondre({"ok": False, "erreur": "Impossible de vérifier le colisage dans les données. Fais vérifier le carnet et la proposition avant de réessayer."}, 500)
            return
        self.send_error(404)

    def _lire_json(self):
        def refuser(message, code=400):
            self.close_connection = True
            self._repondre({"ok": False, "erreur": message}, code)

        longueurs = self.headers.get_all("Content-Length", [])
        if self.headers.get_all("Transfer-Encoding") or len(longueurs) > 1:
            return refuser("Envoi ambigu. Réessaie depuis l'application.")
        if not longueurs:
            return refuser("La taille de l'envoi est manquante.", 411)
        if not re.fullmatch(r"[0-9]+", longueurs[0]):
            return refuser("La taille de l'envoi est invalide.")
        if len(longueurs[0]) > 7 or int(longueurs[0]) > MAX_CORPS_JSON:
            return refuser("Envoi trop volumineux. Envoie moins de relevés à la fois.", 413)
        longueur = int(longueurs[0])
        types = self.headers.get_all("Content-Type", [])
        if len(types) != 1 or types[0].split(";", 1)[0].strip().lower() != "application/json":
            return refuser("Format d'envoi refusé. Utilise l'application.", 415)
        try:
            self.connection.settimeout(10)
            corps = self.rfile.read(longueur)
            if len(corps) != longueur:
                return refuser("Envoi incomplet. Vérifie la connexion puis réessaie.")
            return decoder_requete_json(corps)
        except TimeoutError:
            return refuser("Envoi interrompu. Vérifie la connexion puis réessaie.", 408)
        except ValueError as exc:
            return refuser(str(exc))

    def _verifier_provenance(self, ecriture=False):
        # Ne jamais prendre X-Forwarded-Host/Origin pour une autorisation.
        hotes = self.headers.get_all("Host", [])
        hote = hotes[0].lower() if len(hotes) == 1 else ""
        locaux = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
        distants = {HOTE_TAILSCALE, HOTE_TAILSCALE + ":443"}
        autorise = hote in locaux | distants
        if ecriture:
            origines = self.headers.get_all("Origin", [])
            attendues = {"http://" + hote} if hote in locaux else {
                "https://" + HOTE_TAILSCALE, "https://" + HOTE_TAILSCALE + ":443"}
            fetch = self.headers.get_all("Sec-Fetch-Site", [])
            autorise = (autorise and len(origines) == 1 and origines[0] in attendues
                        and (not fetch or fetch == ["same-origin"]))
        if not autorise:
            self.close_connection = True
            self._repondre({"ok": False, "erreur": "Accès refusé. Ouvre l'application depuis son adresse habituelle."}, 403)
        return autorise

    def _repondre(self, charge, code=200):
        corps = json.dumps(charge, ensure_ascii=False).encode("utf-8")
        try:
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(corps)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(corps)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            # Les faits sont déjà sauvegardés : le traitement doit continuer même
            # si le téléphone disparaît avant son accusé de réception.
            self.close_connection = True

    def _recevoir_messages(self):
        """Recoit ce que le responsable de rayon ecrit depuis le rayon.

        Ces messages sont la seule facon de faire entrer dans le systeme ce
        qu'il sait et qu'aucun fichier ne dit : une mise en tete de gondole,
        une fete locale, une palette gardee en reserve, un doute sur un article.
        Ils sont ranges tels quels, sans interpretation : c'est l'assistant qui
        les lira et decidera quoi en faire.
        """
        try:
            recu = self._charge_json
            messages = normaliser_messages(recu.get("messages", []))
            if not messages:
                return self._repondre({"ok": False, "erreur": "aucun message recu"})

            chemin = DONNEES / "messages.jsonl"
            nouveaux_messages = []
            with _ecriture_messages, verrou_donnees(DONNEES):
                connus = {}
                if chemin.exists():
                    with open(chemin, encoding="utf-8") as f:
                        for ligne in f:
                            if ligne.strip():
                                message = json.loads(ligne)
                                connus[message["id"]] = message["texte"]
                a_ecrire = []
                for m in messages:
                    texte = m["texte"]
                    identifiant = "message:" + m["ecrit_le"]
                    if identifiant in connus:
                        if connus[identifiant] != texte:
                            raise ValueError("Deux messages différents portent la même date. Rien n'a été ajouté ; conserve les textes et signale ce conflit.")
                        continue
                    a_ecrire.append({
                        "id": identifiant,
                        "texte": texte,
                        "ecrit_le": m["ecrit_le"],
                        "recu_le": datetime.now().isoformat(timespec="seconds"),
                        "lu_par_agent": False,
                    })
                    connus[identifiant] = texte
                    nouveaux_messages.append((identifiant, texte))
                if a_ecrire:
                    append_jsonl(chemin, a_ecrire)
            ecrits = len(nouveaux_messages)

            if ecrits:
                journaliser("rayon", f"{ecrits} message(s) recu(s) du responsable de rayon",
                            "Ce que le responsable de rayon sait et qu'aucun fichier ne dit. A lire par l'assistant.",
                            {"messages": [(m.get("texte") or "")[:80] for m in messages][:5]})
            self._repondre({"ok": True, "enregistres": ecrits})
        except Exception as e:
            self._repondre({"ok": False, "erreur": str(e)})
            return
        for identifiant, texte in nouveaux_messages:
            try:
                lancer_reponse_message(identifiant, texte)
            except Exception:
                # L'accusé HTTP est déjà parti : ne pas envoyer une deuxième réponse.
                avis = {
                    "id": "erreur-reponse:" + uuid.uuid4().hex,
                    "auteur": "serveur", "message_id": identifiant,
                    "ecrit_le": datetime.now().isoformat(timespec="seconds"),
                    "texte": "Ton message est enregistré, mais la réponse automatique n'a pas pu démarrer. Il faut relancer l'assistant.",
                }
                journaliser("serveur", "Echec du lancement de la réponse automatique", avis["texte"], {"message_id": identifiant})
                try:
                    with _ecriture_messages, verrou_donnees(DONNEES):
                        append_jsonl(DONNEES / "reponses.jsonl", [avis])
                except (OSError, ValueError):
                    journaliser("serveur", "Impossible de publier l'avis de panne dans le chat", avis["texte"])

    def _recevoir_comptages(self):
        """Reçoit les positions relevées en chambre froide et les inscrit dans
        le carnet des faits.

        Un nouvel instant physique ajoute un comptage distinct, jamais une
        correction historique. Un renvoi identique ou plus ancien n'ajoute rien.
        Les corrections déjà présentes gardent leur sémantique inchangée.
        """
        try:
            recu = self._charge_json
            comptages = recu.get("comptages") or []
            if not comptages:
                return self._repondre({"ok": False, "erreur": "aucun comptage reçu"})

            par_annee = {}
            articles = charger_articles_comptables()
            for c in comptages:
                fait = normaliser_comptage(c, articles)
                par_annee.setdefault(fait["date_effet"][:4], []).append(fait)

            ecrits = deja_recus = 0
            ids_ecrits = []
            DOSSIER_FAITS.mkdir(parents=True, exist_ok=True)
            # Le serveur est multithreadé : lecture, déduplication et ajout
            # doivent former une seule opération atomique en mémoire.
            with _ecriture_faits, verrou_donnees(DONNEES):
                for annee, lignes in par_annee.items():
                    chemin = DOSSIER_FAITS / f"{annee}.jsonl"
                    recus = list(lire_comptages(chemin))
                    a_ecrire = []
                    for nouveau in lignes:
                        nouvel_horaire = datetime.fromisoformat(nouveau["source"]["saisi_le"]).astimezone()
                        meme_article = [f for f in recus if f.get("article") == nouveau["article"]
                                        and (f.get("date_effet") or f.get("date_source")) == nouveau["date_effet"]]
                        # Un ancien relevé UI a parfois été écrit comme correction.
                        # Reconnaître son renvoi sans le matérialiser rétroactivement
                        # en nouvelle mesure. Son heure d'audit ne sert PAS de base.
                        renvois = [f for f in meme_article
                                   if f.get("origine_mesure") == "ecran-comptage-correction"
                                   and (f.get("source") or {}).get("saisi_le")
                                   and datetime.fromisoformat(f["source"]["saisi_le"]).astimezone() == nouvel_horaire]
                        if renvois:
                            if not any(f.get("quantite") == nouveau["quantite"] for f in renvois):
                                raise ValueError("Deux valeurs différentes au même instant de comptage : "
                                                 "conserve le relevé et fais vérifier la correction de saisie.")
                            deja_recus += 1
                            continue
                        precedents = [
                            (datetime.fromisoformat((f.get("source") or {}).get("saisi_le")
                                                    or f.get("horodatage")).astimezone(), f)
                            for f in meme_article
                            if f.get("type") == "comptage"
                        ]
                        # Un conflit reste un conflit même si une mesure plus
                        # récente existe : ne pas acquitter puis perdre ce relevé.
                        if any(horaire == nouvel_horaire and f.get("quantite") != nouveau["quantite"]
                               for horaire, f in precedents):
                            raise ValueError("Deux valeurs différentes au même instant de comptage : "
                                             "conserve le relevé et fais vérifier la correction de saisie.")
                        ancien_horaire, precedent = max(precedents, key=lambda p: p[0], default=(None, None))
                        if precedent is None:
                            a_ecrire.append(nouveau)
                            recus.append(nouveau)
                            ecrits += 1
                            continue
                        # Une mesure identique plus tard établit aussi une nouvelle
                        # base à son heure ; un ancien envoi hors-ligne ne doit pas
                        # annuler une mesure plus récente.
                        if (ancien_horaire is not None and (
                                nouvel_horaire < ancien_horaire or (
                                nouvel_horaire == ancien_horaire and precedent.get("quantite") == nouveau["quantite"]))):
                            deja_recus += 1
                            continue
                        a_ecrire.append(nouveau)
                        recus.append(nouveau)
                        ecrits += 1
                    if a_ecrire:
                        append_jsonl(chemin, a_ecrire)
                        ids_ecrits.extend(fait["id"] for fait in a_ecrire)

            if ecrits:
                journaliser(
                    "ecran-comptage",
                    f"{ecrits} position(s) reçue(s) depuis la chambre froide",
                    "Le responsable de rayon a envoyé de nouvelles mesures physiques. "
                    "Chaque mesure établit une base à son propre instant ; les mouvements "
                    "postérieurs s'appliquent par-dessus. Aucun fait historique n'est corrigé.",
                    {"positions": ecrits, "corrections": 0, "deja_recus": deja_recus,
                     "ids_comptages": ids_ecrits,
                     "articles": [c.get("libelle") for c in comptages][:20]},
                )
            # On repond D'ABORD au telephone, on recalcule ENSUITE.
            self._repondre({"ok": True, "enregistres": ecrits, "corrections": 0,
                            "deja_recus": deja_recus})
            recalculer_en_arriere_plan()

        except Exception as e:
            self._repondre({"ok": False, "erreur": str(e)})

    def _masquer_demasquer(self):
        """Le bouton rond de l'écran de commande : masquer ou démasquer un
        article d'un geste, depuis le rayon.

        Passe par appliquer-decision.py comme toute décision (motif, pouvoirs,
        marche arrière) — jamais d'écriture directe dans les carnets ici.

        La décision elle-même est rapide (~0,3 s), mais regénérer toute la
        proposition (418 articles, la formule complète) prend ~3 s — bien trop
        long pour un bouton qu'on presse au rayon. On corrige donc tout de
        suite le seul champ qui compte pour l'écran ("masque" sur cette ligne)
        directement dans proposition.json, et la régénération complète (ordre,
        totaux exacts) se fait juste après, en arrière-plan — trouvé lent le
        2026-09-04, le responsable de rayon l'a signalé.
        """
        try:
            recu = self._charge_json
            if type(recu.get("masquer")) is not bool:
                raise ValueError("Indique explicitement si l'article doit être masqué ou démasqué.")
            itm8, libelle = article_de_decision(recu)
            action = "masquer" if recu.get("masquer") else "demasquer"
            if not itm8:
                return self._repondre({"ok": False, "erreur": "aucun article recu"})

            motif = (f"le responsable de rayon, depuis l'ecran de commande : {action} \"{libelle}\" "
                     f"d'un geste au rayon — "
                     + ("il ne veut plus le voir propose a la commande pour l'instant."
                        if action == "masquer" else
                        "il veut a nouveau le voir propose a la commande."))

            resultat = subprocess.run(
                [sys.executable, str(RACINE / "moteur" / "appliquer-decision.py"),
                 action, itm8, "--auteur", "responsable-rayon", "--motif", motif],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30, env=environnement_verrou(DONNEES))

            if resultat.returncode != 0:
                return self._repondre({"ok": False,
                                       "erreur": (resultat.stdout or resultat.stderr or "").strip()})

            chemin_prop = DONNEES / "proposition.json"
            try:
                prop = json.loads(chemin_prop.read_text(encoding="utf-8"))
                for l in prop.get("lignes", []):
                    if l.get("itm8") == itm8:
                        l["masque"] = (action == "masquer")
                        break
                publier_proposition(prop)
            except Exception:
                pass   # tant pis pour la reponse immediate, la regen ci-dessous rattrape tout

            self._repondre({"ok": True, "action": action})

            recalculer_en_arriere_plan()
        except Exception as e:
            self._repondre({"ok": False, "erreur": str(e)})

    def _changer_conditionnement(self):
        """Action directe confirmée par l'humain, pas une délégation d'agent.

        Le CLI garde pouvoirs, motif et audit. Le PCB seul n'est jamais publié :
        offre, prix et totaux doivent être régénérés ensemble.
        """
        recu = self._charge_json
        try:
            valeur = nombre_conditionnement(recu.get("conditionnement"))
            ancien = nombre_conditionnement(recu.get("ancien_conditionnement"))
            itm8, libelle, publie = article_de_decision(recu, avec_conditionnement=True)
        except ValueError as exc:
            return self._repondre({"ok": False, "erreur": str(exc)}, 400)
        decision = decision_conditionnement_effective(itm8)
        effectif = float(decision["valeur"]) if decision is not None else publie
        if decision is not None and effectif == valeur:
            return self._accuser_conditionnement(decision, valeur, deja_effectif=True)
        if effectif != ancien:
            return self._repondre({"ok": False, "conditionnement": effectif,
                                   "erreur": "Le colisage a changé depuis l'ouverture de la fiche. Recharge la page avant de confirmer."}, 409)
        motif = (f"Le responsable de rayon confirme depuis la fiche de commande le colisage "
                 f"de \"{libelle}\" : {ancien} vers {valeur}. "
                 "Recalculer la commande sans modifier les comptages historiques.")
        erreur_cli, statut_cli = None, 502
        try:
            resultat = subprocess.run(
                [sys.executable, str(RACINE / "moteur" / "appliquer-decision.py"),
                 "conditionnement", itm8, str(valeur), "--auteur", "responsable-rayon", "--motif", motif],
                cwd=RACINE, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30, env=environnement_verrou(DONNEES))
            if resultat.returncode != 0:
                erreur_cli = (resultat.stderr or resultat.stdout or "refus du programme").strip()[-400:]
        except subprocess.TimeoutExpired:
            erreur_cli, statut_cli = "Le programme a dépassé le délai de réponse.", 504
        except OSError:
            erreur_cli = "Le programme de décision n'a pas pu s'exécuter."
        decision = decision_conditionnement_effective(itm8)
        enregistre = (decision is not None and bool(decision.get("id"))
                      and decision.get("motif") == motif and decision.get("auteur") == "responsable-rayon"
                      and float(decision.get("valeur", 0)) == valeur)
        if erreur_cli:
            return self._repondre({"ok": False, "enregistre": enregistre,
                                   "erreur": "Le colisage n'a pas pu être confirmé : " + erreur_cli}, statut_cli)
        if not enregistre:
            return self._repondre({"ok": False, "erreur": "La décision exacte n'a pas été retrouvée dans le carnet. Fais vérifier avant de réessayer."}, 500)
        return self._accuser_conditionnement(decision, valeur)

    def _accuser_conditionnement(self, decision, valeur, deja_effectif=False):
        try:
            recalculer_en_arriere_plan()
        except Exception:
            return self._repondre({"ok": False, "enregistre": True, "conditionnement": valeur,
                                   "decision_id": decision["id"],
                                   "erreur": "Le colisage est enregistré, mais le recalcul n'a pas pu démarrer. Réessaie pour le relancer."}, 500)
        return self._repondre({"ok": True, "conditionnement": valeur, "recalcul": "en_cours",
                               "decision_id": decision["id"], "deja_effectif": deja_effectif})

    def _changer_fournisseur(self):
        """Changer le fournisseur habituel d'un article depuis l'écran de
        commande — utile le jour où le responsable de rayon bascule un produit de Scafruit
        vers Pomona (ou l'inverse). Même schéma que _masquer_demasquer :
        décision via appliquer-decision.py, correction immédiate de
        proposition.json pour un retour rapide, régénération complète en
        arrière-plan."""
        try:
            recu = self._charge_json
            itm8, libelle = article_de_decision(recu)
            fournisseur = recu.get("fournisseur")
            if (not isinstance(fournisseur, str) or not fournisseur
                    or fournisseur != fournisseur.strip() or len(fournisseur) > 80
                    or fournisseur.startswith("-")
                    or any(ord(c) < 32 or ord(c) == 127 for c in fournisseur)):
                raise ValueError("Le nom du fournisseur doit contenir entre 1 et 80 caractères, sans caractères de contrôle.")
            fournisseur.encode("utf-8")
            if not itm8 or not fournisseur:
                return self._repondre({"ok": False, "erreur": "article ou fournisseur manquant"})

            motif = (f"le responsable de rayon, depuis l'ecran de commande : change le fournisseur habituel "
                     f"de \"{libelle}\" pour \"{fournisseur}\" — un meme produit peut venir de "
                     f"plusieurs fournisseurs selon le jour, c'est juste la reference par defaut.")

            resultat = subprocess.run(
                [sys.executable, str(RACINE / "moteur" / "appliquer-decision.py"),
                 "fournisseur", itm8, fournisseur, "--auteur", "responsable-rayon", "--motif", motif],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30, env=environnement_verrou(DONNEES))

            if resultat.returncode != 0:
                return self._repondre({"ok": False,
                                       "erreur": (resultat.stdout or resultat.stderr or "").strip()})

            chemin_prop = DONNEES / "proposition.json"
            try:
                prop = json.loads(chemin_prop.read_text(encoding="utf-8"))
                for l in prop.get("lignes", []):
                    if l.get("itm8") == itm8:
                        l["fournisseur"] = fournisseur
                        break
                publier_proposition(prop)
            except Exception:
                pass

            self._repondre({"ok": True, "fournisseur": fournisseur})

            recalculer_en_arriere_plan()
        except Exception as e:
            self._repondre({"ok": False, "erreur": str(e)})


class ServeurHTTP(ThreadingHTTPServer):
    # Les vignettes arrivent en rafale via Tailscale. La limite Python de cinq
    # connexions en attente provoque des refus TCP puis des 502 du proxy.
    request_queue_size = 128


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8751
    # L'accès mobile passe par Tailscale Serve, qui relaie localement vers ce
    # processus. Ne jamais exposer les routes d'écriture sur le LAN.
    serveur = ServeurHTTP(("127.0.0.1", port), Gestionnaire)
    journaliser("serveur", f"Serveur preparation-commande démarré (port {port})",
                "Démarrage normal.", None)
    print(f"preparation-commande sur http://127.0.0.1:{port}/app/index.html")
    serveur.serve_forever()


if __name__ == "__main__":
    main()
