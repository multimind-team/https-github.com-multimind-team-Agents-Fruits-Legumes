"""Revue du seul payload conversation corrigé, dans une copie protégée."""
from datetime import datetime
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

DOSSIER=Path(__file__).resolve().parent
RACINE=DOSSIER.parents[2]
spec=importlib.util.spec_from_file_location('preparation',DOSSIER/'preparer-simulation-agent-donnees-2115.py')
prep=importlib.util.module_from_spec(spec); spec.loader.exec_module(prep)
SOURCE=DOSSIER/'preparation-agent-donnees-20260915-210721.json'
plan=prep.charger(SOURCE)
plan['preuve_precedente']=str(SOURCE)
plan['prepare_le']=datetime.now().isoformat(timespec='seconds')
assert plan['prepare_le'][:10]=='2026-09-15' and plan['prepare_le'][11:] >= '17:00:00'
for fait in plan['faits_simules']:
    fait.update(mesure='position',conditionnement=fait['par_colis'],enregistre_le=plan['prepare_le'],motif='Position actuelle du soir déclarée par le responsable dans la conversation, après les mouvements du 15 septembre 2026 ; heure physique précise non fournie.')
plan['sous_lots']={
    'positions': {'compte':21,'depend_des_reglages_pcb':False,'autorisation_metier':'Demande et phase du soir confirmées ; attendre avis indépendant et mandat de l’orchestrateur.','actions':{'integration_agent_donnees':1,'recalcul_cadencier_agent_donnees':1,'recalcul_filet':1},'global_apres_si_positions_seules':plan['quotas']['global_avant']+3,'rayon_apres':0,'donnees_apres':5},
    'reglages': {'compte':18,'pcb':6,'masques':12,'autorisation_metier':'Demande explicite ; plafonds actuels insuffisants, exception non acquise dans cette préparation.','auteur_futur':'agent-rayon','global_apres_tout_si_recalcul_unique':25,'rayon_apres':18,'recalcul_si_realises_apres_positions_deja_recalculees':'Deux actions supplémentaires (cadencier + filet) : total global27, données6, rayon18 ; aucun second import des positions.'}
}
empreintes={str(p):prep.h(p) for p in map(Path,plan['empreintes_avant'])}
assert empreintes==plan['empreintes_avant'], 'Une source ou donnée a changé : revoir le lot avant simulation.'

ENFANT=r'''
import contextlib,copy,importlib.util,io,json,sys
from datetime import datetime,timedelta
from pathlib import Path
import faits,journal_agents,regles
r=Path.cwd(); plan=json.loads((r/'plan.json').read_text(encoding='utf-8'))
def mod(n):
 s=importlib.util.spec_from_file_location(n.replace('-','_'),r/'moteur'/f'{n}.py'); m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
imp=mod('integrer-fichiers');pos=mod('calculer-position');gen=mod('generer-proposition')
avant=list(faits.lire(r/'donnees/faits')); config=regles.charger()
prefixes={p.name:p.read_bytes() for p in (r/'donnees/faits').glob('*.jsonl')}
decisions=(r/'donnees/decisions.jsonl').read_bytes()
payload=plan['faits_simules']
for f in payload:
 assert f['mesure']=='position' and f['conditionnement']==f['par_colis'] and f['quantite']==round(f['colis']*f['conditionnement'],3)
 assert 'saisi_le' not in f['source'] and 'horodatage' not in f and f['source']['heure_physique'] is None
 assert pos.moment_du_comptage(f)=='soir' and pos.heure_physique(f)==f['enregistre_le'][11:19]
nouveaux,deja=imp.ecrire(payload,simuler=True);assert len(nouveaux)==21 and deja==0
with journal_agents.verrou():
 journal_agents.verifier_pouvoirs('agent-donnees',[],r/'donnees/pouvoirs.json')
 ajoutes,deja=imp.ecrire(payload)
 action=journal_agents.enregistrer(agent='agent-donnees',message='SIMULATION EN COPIE : 21 positions déclarées dans la conversation',motif='Positions actuelles du soir confirmées après mouvements ; aucun réglage article appliqué dans cette copie.',details={'ids':[f['id'] for f in ajoutes]},annulable=False)
rejoues,doublons=imp.ecrire(payload); assert rejoues==[] and doublons==21
apres=list(faits.lire(r/'donnees/faits'))
assert apres[:len(avant)]==avant and len(apres)==len(avant)+21
assert all((r/'donnees/faits'/n).read_bytes().startswith(b) for n,b in prefixes.items())
assert (r/'donnees/decisions.jsonl').read_bytes()==decisions
resultat=pos.calculer_depuis_faits(apres,config,pos.charger_heures_reception_mail(),details=True)
for x in plan['positions']:
 assert resultat[x['code']]['position']==x['quantite'] and resultat[x['code']]['moment_mesure']=='soir' and resultat[x['code']]['mouvements_depuis']==0
f0=payload[0]; futur=copy.deepcopy(f0);futur['id']='fixture:recomptage-ulterieur';futur['quantite']=12;futur['colis']=2;futur['source']={'saisi_le':(datetime.fromisoformat(f0['enregistre_le'])+timedelta(seconds=1)).isoformat(),'fixture':True}
priorite=pos.calculer_depuis_faits(apres+[futur],config,{},details=True)[f0['article']]
assert priorite['depart']['id']==futur['id'] and priorite['position']==12
log=io.StringIO()
with contextlib.redirect_stdout(log):pos.main();gen.main()
publication=json.loads((r/'donnees/proposition.json').read_text(encoding='utf-8'));lignes={l['itm8']:l for l in publication['lignes']}
for x in plan['positions']:assert lignes[x['code']]['position_colis']==x['colis']
assert lignes['0000087004035']['conditionnement']==7 and lignes['0000087004035']['position_unites']==28
assert lignes['0000087010621']['conditionnement']==8 and lignes['0000087010621']['position_unites']==-3
assert lignes['0000087950042']['position_colis']==0
# ICEBERG a bien une mesure, mais son code n'est pas une offre de la proposition
# actuelle : contrôler son état canonique, sans inventer une ligne commandable.
etat_avant=pos.calculer_depuis_faits(avant,config,pos.charger_heures_reception_mail(),details=True)
temoins_etat={c:{'avant':etat_avant[c],'apres':resultat[c]} for c in ['0000087950042','0000087755078','0000087004035','0000087010621']}
assert all(x['avant']==x['apres'] for x in temoins_etat.values())
assert resultat['0000087755078']['position']==54
preuves={'statut':'SIMULATION EN COPIE UNIQUEMENT','nouveaux':len(ajoutes),'rejeu_nouveaux':len(rejoues),'rejeu_doublons':doublons,'faits_avant':len(avant),'faits_apres':len(apres),'faits_anciens_et_prefixes_identiques':True,'decisions_inchangees':True,'conditionnement_et_mesure_verifies_21':True,'positions_21_sans_aucun_reglage':[{'repere':x['repere'],'etat':resultat[x['code']],'ligne_proposition':lignes[x['code']]} for x in plan['positions']],'recomptage_ulterieur_fictif':priorite,'temoins_etat_hors_lot':temoins_etat,'temoins_proposition_hors_lot':[lignes[c] for c in ['0000087950042','0000087004035','0000087010621']],'journal_import_copie':action,'sortie_calcul':log.getvalue()}
(r/'resultat.json').write_text(json.dumps(preuves,ensure_ascii=False,indent=2),encoding='utf-8')
print('21 positions indépendantes vérifiées ; mesure/conditionnement conservés ; rejeu 0 nouveau / 21 doublons ; anciens faits inchangés.')
'''
spec=importlib.util.spec_from_file_location('isoles',RACINE/'tests/lancer_tests_isoles.py');iso=importlib.util.module_from_spec(spec);spec.loader.exec_module(iso)
with tempfile.TemporaryDirectory(prefix='preparation-payload-positions-') as t:
    base=Path(t);copie=base/'projet';copie.mkdir()
    for n in ('moteur','donnees'):shutil.copytree(RACINE/n,copie/n,ignore=iso.ignorer_prives)
    iso.neutraliser_courrier(copie)
    garde=base/'garde';garde.mkdir();(garde/'sitecustomize.py').write_text(iso.GARDE,encoding='utf-8')
    env=os.environ.copy();env.update(PYTHONDONTWRITEBYTECODE='1',PYTHONUTF8='1',PREPARATION_TEST_SANDBOX=str(base),PREPARATION_TEST_ORIGINAL=str(RACINE),PYTHONPATH=os.pathsep.join([str(garde),str(copie/'moteur')]))
    for n in tuple(env):
        if any(s in n.upper() for s in ('PASSWORD','MOT_DE_PASSE','SMTP','IMAP','GMAIL')):env.pop(n)
    prep.dump_nouveau(copie/'plan.json',plan);(copie/'simuler.py').write_text(ENFANT,encoding='utf-8')
    execution=subprocess.run([sys.executable,'-B','simuler.py'],cwd=copie,env=env,capture_output=True,text=True,encoding='utf-8')
    plan['execution_simulation_payload_corrige']={'code_retour':execution.returncode,'stdout':execution.stdout,'stderr':execution.stderr,'protection_original_et_reseau':True}
    if (copie/'resultat.json').exists():plan['simulation_payload_corrige']=prep.charger(copie/'resultat.json')
plan['empreintes_apres_payload_corrige']={str(p):prep.h(p) for p in map(Path,empreintes)}
plan['donnees_originales_inchangees']=empreintes==plan['empreintes_apres_payload_corrige']
sortie=DOSSIER/f'preparation-agent-donnees-v2-{datetime.now():%Y%m%d-%H%M%S}.json'
prep.dump_nouveau(sortie,plan)
sys.stdout.reconfigure(encoding='utf-8');print(json.dumps({'preuve':str(sortie),'code_retour':execution.returncode,'stdout':execution.stdout,'stderr':execution.stderr,'donnees_originales_inchangees':plan['donnees_originales_inchangees']},ensure_ascii=False))
raise SystemExit(execution.returncode)
