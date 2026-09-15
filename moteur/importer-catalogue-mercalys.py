"""Import contrôlé du référentiel Mercalys ; aucun mouvement de stock.

Fournir seulement les fichiers revus, puis --simuler avant contrôle indépendant.
Le mode réel fusionne les fiches sans supprimer les articles absents du fichier.
"""
import argparse
from contextlib import nullcontext
from datetime import date, datetime
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import sys

MOTEUR = Path(__file__).resolve().parent
sys.path.insert(0, str(MOTEUR))
import catalogue
from ecriture_derivee import ecrire_json
from verrou_donnees import verrou_donnees


def lecteur_tableau(chemin):
    spec = importlib.util.spec_from_file_location("lecteur_import_catalogue", MOTEUR / "integrer-fichiers.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.lire_tableau(chemin)


def code_source(valeur):
    if isinstance(valeur, bool):
        raise ValueError("code article booléen")
    if isinstance(valeur, (int, float)):
        if not math.isfinite(valeur) or valeur < 0 or int(valeur) != valeur:
            raise ValueError("code article numérique invalide")
        valeur = str(int(valeur))
    code = str(valeur or "").strip()
    if not re.fullmatch(r"\d{1,13}", code):
        raise ValueError("code article absent ou invalide")
    return code.zfill(13)


def lire_referentiel(chemin):
    colonnes, lignes, entete = lecteur_tableau(chemin)
    requis = {"CODE ITM", "LIBELLE", "CONDIT.BASE", "UNITE MESURE", "PRIX ACHAT BRUT", "PRIX VENTE"}
    if not colonnes or not requis <= set(colonnes):
        raise ValueError("colonnes obligatoires du référentiel Mercalys absentes")
    dates = re.findall(r"Date d.application\s*:\s*(\d{2})/(\d{2})/(\d{4})", str(entete), re.I)
    if not dates:
        raise ValueError("date d'application absente de l'en-tête Mercalys")
    dates = {date(int(a), int(m), int(j)).isoformat() for j, m, a in dates}
    if len(dates) != 1:
        raise ValueError("dates d'application contradictoires")
    jour = dates.pop()
    articles, erreurs = {}, []
    compteur = 0
    compte_annonce = None
    for rang, valeurs in enumerate(lignes, len(entete) + 2):
        if not any(v is not None and str(v).strip() for v in valeurs):
            continue
        premier = str(valeurs[0] or "").strip()
        pied = re.fullmatch(r"Nombre de lignes\s*:\s*:?\s*(\d+)", premier, re.I)
        if pied and not any(v is not None and str(v).strip() for v in valeurs[1:]):
            compte_annonce = int(pied[1])
            continue
        compteur += 1
        try:
            fiche = {cle: valeur for cle, valeur in zip(colonnes, valeurs) if cle}
            code = code_source(fiche.get("CODE ITM"))
            fiche["CODE ITM"] = code
            if not str(fiche.get("LIBELLE") or "").strip() or not str(fiche.get("UNITE MESURE") or "").strip():
                raise ValueError("libellé ou unité absents")
            for cle in ("CONDIT.BASE", "PRIX ACHAT BRUT", "PRIX VENTE"):
                v = fiche.get(cle)
                if isinstance(v, bool) or v in (None, ""):
                    raise ValueError(f"{cle} absent ou invalide")
                n = float(str(v).replace(",", "."))
                if not math.isfinite(n) or n < 0:
                    raise ValueError(f"{cle} négatif ou non fini")
                fiche[cle] = n
            if code in articles and articles[code] != fiche:
                raise ValueError(f"deux fiches contradictoires pour {code}")
            articles[code] = fiche
        except (ValueError, TypeError) as exc:
            erreurs.append({"ligne": rang, "motif": str(exc)})
    if not articles:
        erreurs.append({"motif": "aucune fiche article exploitable"})
    if compte_annonce is not None and compte_annonce != compteur:
        erreurs.append({"motif": f"nombre de lignes annoncé {compte_annonce}, lu {compteur}"})
    return jour, articles, erreurs


def importer(fichiers, *, simuler=True, sortie=None, agent="agent-donnees"):
    sortie = Path(sortie) if sortie is not None else catalogue.FICHIER
    bilan = {"ok": False, "statut": "refuse", "simule": simuler, "agent": agent,
             "a_verifier": [], "erreurs": [], "ajoutes": 0, "modifies": 0,
             "identiques": 0, "fichiers": [], "ecrit": False}
    if agent != "agent-donnees":
        bilan["erreurs"].append("Import réservé à agent-donnees après contrôle indépendant.")
        return bilan
    # La simulation est strictement en lecture seule, même pour le verrou.
    with (nullcontext() if simuler else verrou_donnees(sortie.parent)):
        ancien = json.loads(sortie.read_text(encoding="utf-8")) if sortie.exists() else {"articles": {}}
        fusion = {**ancien, "articles": {k: dict(v) for k, v in ancien.get("articles", {}).items()}}
        lots = []
        for fichier in fichiers:
            chemin = Path(fichier)
            preuve = {"fichier": chemin.name}
            try:
                empreinte = hashlib.sha256(chemin.read_bytes()).hexdigest()
                jour, articles, erreurs = lire_referentiel(chemin)
                if hashlib.sha256(chemin.read_bytes()).hexdigest() != empreinte:
                    raise ValueError("fichier modifié pendant la lecture")
                preuve.update(date=jour, sha256=empreinte, articles=len(articles), erreurs=erreurs)
                if erreurs:
                    bilan["a_verifier"].extend({"fichier": chemin.name, **e} for e in erreurs)
                lots.append((jour, chemin.name, articles))
            except (ValueError, OSError, TypeError) as exc:
                bilan["erreurs"].append(f"{chemin.name} : {exc}")
            bilan["fichiers"].append(preuve)
        if not lots:
            bilan["erreurs"].append("Aucun référentiel exploitable.")
        vus = {}
        for jour, nom, articles in sorted(lots):
            if jour < (ancien.get("derniere_maj") or ""):
                bilan["a_verifier"].append({"fichier": nom, "motif": "référentiel antérieur au catalogue actuel"})
            for code, fiche in articles.items():
                cle = (jour, code)
                if cle in vus and vus[cle] != fiche:
                    bilan["a_verifier"].append({"fichier": nom, "motif": f"référentiels contradictoires le même jour pour {code}"})
                vus[cle] = fiche
                fusion["articles"][code] = {**fusion["articles"].get(code, {}), **fiche}
        if bilan["erreurs"] or bilan["a_verifier"]:
            return bilan
        for code, fiche in fusion["articles"].items():
            if code not in ancien.get("articles", {}):
                bilan["ajoutes"] += 1
            elif fiche != ancien["articles"][code]:
                bilan["modifies"] += 1
            else:
                bilan["identiques"] += 1
        fusion.update(derniere_maj=max(j for j, _, _ in lots),
                      importe_le=datetime.now().isoformat(timespec="seconds"),
                      sources_dernier_import=bilan["fichiers"])
        bilan.update(ok=True, statut="simule" if simuler else "integre")
        if not simuler:
            ecrire_json(sortie, fusion)
            catalogue.charger.cache_clear()
            bilan["ecrit"] = True
        return bilan


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("fichiers", nargs="+")
    p.add_argument("--simuler", action="store_true")
    p.add_argument("--json", action="store_true", help="Résultat structuré (également fourni par défaut)")
    p.add_argument("--agent", default="agent-donnees")
    args = p.parse_args()
    try:
        bilan = importer(args.fichiers, simuler=args.simuler, agent=args.agent)
    except (OSError, ValueError, TypeError) as exc:
        bilan = {"ok": False, "statut": "refuse", "erreurs": [str(exc)], "ecrit": False}
    print(json.dumps(bilan, ensure_ascii=False))
    return 0 if bilan["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
