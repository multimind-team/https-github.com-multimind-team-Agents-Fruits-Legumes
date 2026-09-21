"""Audit UI : copies temporaires, toutes les requêtes interceptées, aucun POST réel.

Ce script constate des défauts ; il n'applique aucune correction.
"""
import ast
import importlib.util
import json
import math
from pathlib import Path
import re
import shutil
import sys
import tempfile
from datetime import date, datetime, timedelta

sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[2]


def emit(value):
    print(json.dumps(value, ensure_ascii=False), flush=True)


with tempfile.TemporaryDirectory(prefix="audit-controle-ui-") as temporary:
    copy = Path(temporary)
    (copy / "app").mkdir()
    for page in (ROOT / "app").glob("*.html"):
        shutil.copy2(page, copy / "app" / page.name)
    for folder in ("js", "css"):
        shutil.copytree(ROOT / "app" / folder, copy / "app" / folder)
    shutil.copy2(ROOT / "tests/test_interface_mobile.py", copy / "test_interface_mobile.py")
    shutil.copy2(ROOT / "moteur/serveur.py", copy / "serveur.py")
    parsed = ast.parse((copy / "serveur.py").read_text(encoding="utf-8"))
    selected = ast.Module(body=[n for n in parsed.body if isinstance(n, ast.FunctionDef)
                               and n.name in ("normaliser_comptage", "nombre_conditionnement")], type_ignores=[])
    namespace = {"math": math, "re": re, "datetime": datetime}
    exec(compile(selected, str(copy / "serveur.py"), "exec"), namespace)
    spec = importlib.util.spec_from_file_location("audit_ui", copy / "test_interface_mobile.py")
    ui = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ui)
    ui.ROOT = copy
    cls = ui.InterfaceMobileTests
    cls.setUpClass()
    try:
        h = cls()
        h.setUp()
        try:
            h.open("compter")
            h.page.locator("#valider").click()
            h.page.locator("#envoyer").click()
            h.page.wait_for_function("JSON.parse(localStorage.getItem(CLE_COMPTAGES)).length===0")

            def accept_count(route):
                h.fixtures["/donnees/proposition.json"] = dict(
                    ui.PROPOSAL, genere_le="fixture-after", lignes=[dict(ui.LINE, position_colis=7)])
                h.fixtures["/donnees/articles.json"] = {"articles": [
                    dict(ui.ARTICLE, derniere_position_colis=7), dict(ui.ARTICLE, itm8="0000000000002")]}
                route.fulfill(json={"ok": True, "enregistres": 1})

            h.api = accept_count
            h.open("commander")
            h.page.evaluate("montrerDetail(proposition.lignes[0])")
            h.page.locator("#detail-stock-modifier").click()
            h.page.locator("#detail-stock-valeur").fill("7")
            h.page.locator("#detail-stock-valider").click()
            h.page.wait_for_function("proposition.genere_le==='fixture-after'")
            accepted = h.posts[-1]["comptages"][0]
            h.open("compter")
            h.page.evaluate("allerA(0)")
            h.page.wait_for_timeout(1100)
            shown = h.page.locator("#nombre").inner_text()
            origin = h.page.locator("#origine").inner_text()
            h.page.locator("#valider").click()
            emit({"scenario": "correction_commande_non_synchronisee", "correction_acceptee": accepted,
                  "retour_comptage_affiche": shown, "origine": origin,
                  "nouvelle_file": h.page.evaluate("JSON.parse(localStorage.getItem(CLE_COMPTAGES))"),
                  "erreurs_JS": h.errors})
        finally:
            h.tearDown()

        h = cls()
        h.setUp()
        try:
            refusals = []

            def actual_validator(route):
                try:
                    for row in route.request.post_data_json["comptages"]:
                        namespace["normaliser_comptage"](row, {
                            ui.CODE: ui.ARTICLE, "0000000000002": dict(ui.ARTICLE, itm8="0000000000002")})
                    route.fulfill(json={"ok": True})
                except ValueError as error:
                    refusals.append(str(error))
                    route.fulfill(json={"ok": False, "erreur": str(error)})

            h.api = actual_validator
            h.open("compter")
            past = (date.today() - timedelta(days=1)).isoformat()
            yesterday = dict(ui.ARTICLE, date=past, colis=2, unites=12, saisi_le=past + "T17:30:00")
            h.page.evaluate("(x)=>localStorage.setItem(CLE_COMPTAGES,JSON.stringify([x]))", yesterday)
            h.page.locator("#valider").click()
            for _ in range(2):
                h.page.locator("#envoyer").click()
                h.page.wait_for_function("!envoiEnCours")
            emit({"scenario": "file_hier_bloque_comptages_du_jour", "refus_serveur": refusals,
                  "message_utilisateur": h.page.locator("#resultat").inner_text(),
                  "file_apres_deux_tentatives": h.page.evaluate("JSON.parse(localStorage.getItem(CLE_COMPTAGES))"),
                  "requetes": len(h.posts), "erreurs_JS": h.errors})
        finally:
            h.tearDown()

        h = cls()
        h.setUp()
        try:
            second = dict(ui.LINE, itm8="0000000000002", libelle="ARTICLE B")
            h.fixtures["/donnees/proposition.json"] = dict(ui.PROPOSAL, lignes=[ui.LINE, second])
            h.open("commander")
            h.page.evaluate("montrerDetail(proposition.lignes[0])")
            h.page.locator("#detail-stock-modifier").click()
            h.page.locator("#detail-stock-valeur").fill("7")
            responses = []
            fresh_a = dict(ui.PROPOSAL, genere_le="A-only", lignes=[dict(ui.LINE, position_colis=7), second])
            fresh_ab = dict(ui.PROPOSAL, genere_le="A-and-B", lignes=[
                dict(ui.LINE, position_colis=7), dict(second, position_colis=9)])

            def hold_first(route):
                responses.append(route)
                if len(responses) > 1:
                    route.fulfill(json=fresh_ab)

            h.context.route("**/donnees/proposition.json?*", hold_first)
            h.page.locator("#detail-stock-valider").click()
            h.page.wait_for_timeout(700)
            h.page.locator("#fermer-detail").click()
            h.page.locator('[data-itm8="0000000000002"] [data-role="detail"]').click()
            h.page.locator("#detail-stock-modifier").click()
            h.page.locator("#detail-stock-valeur").fill("9")
            h.page.locator("#detail-stock-valider").click()
            h.page.wait_for_function("proposition.genere_le==='A-and-B'")
            before = h.page.evaluate("proposition.lignes[1].position_colis")
            responses[0].fulfill(json=fresh_a)
            h.page.wait_for_function("proposition.genere_le==='A-only'")
            emit({"scenario": "relectures_stock_hors_ordre", "B_apres_correction": before,
                  "B_apres_reponse_A_retardee": h.page.evaluate("proposition.lignes[1].position_colis"),
                  "requetes": len(h.posts), "erreurs_JS": h.errors})
        finally:
            h.tearDown()

        h = cls()
        h.setUp()
        try:
            h.open("commander")
            h.page.evaluate("agentAjustements[proposition.lignes[0].itm8]={applique:true,avant:3,apres:2,motif:'test'}; afficher()")
            before = h.page.evaluate("quantite(proposition.lignes[0])")
            h.page.locator('[data-role="plus"]').click()
            emit({"scenario": "ajustement_applique_retour_proposition", "avant": before,
                  "attendu_apres_plus": 3, "apres": h.page.evaluate("quantite(proposition.lignes[0])"),
                  "memoire": h.page.evaluate("localStorage.getItem(CLE_AJUSTEMENTS)"), "erreurs_JS": h.errors})
        finally:
            h.tearDown()
    finally:
        cls.tearDownClass()
