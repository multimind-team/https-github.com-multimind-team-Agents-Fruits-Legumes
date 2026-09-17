"""Préparation privée : ne modifie les données que dans une copie protégée jetable."""
import copy
from datetime import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

RACINE = Path(__file__).resolve().parents[3]
DOSSIER = Path(__file__).resolve().parent
RAPPORT = Path('C:/Users/user/Desktop/audit-preparation-commande-2026-09-15/articles-a-verifier.json')


def h(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def charger(path):
    return json.loads(path.read_text(encoding='utf-8'))


def dump_nouveau(path, value):
    with path.open('x', encoding='utf-8') as out:
        json.dump(value, out, ensure_ascii=False, indent=2, allow_nan=False)


ENFANT = r'''
import contextlib, copy, importlib.util, io, json, subprocess, sys
from pathlib import Path
import catalogue, conditionnements, faits, journal_agents, regles
racine = Path.cwd()
plan = json.loads((racine/'plan.json').read_text(encoding='utf-8'))
def module(nom):
    spec=importlib.util.spec_from_file_location(nom.replace('-','_'),racine/'moteur'/f'{nom}.py')
    mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod
pos=module('calculer-position'); gen=module('generer-proposition'); imp=module('integrer-fichiers')
avant=list(faits.lire(racine/'donnees/faits'))
prefixes={p.name:p.read_bytes() for p in (racine/'donnees/faits').glob('*.jsonl')}
config=regles.charger(); complet=copy.deepcopy(config)
for reglage in plan['reglages']:
    surcharge=complet['overrides'].setdefault(reglage['code'],{})
    surcharge['conditionnement' if reglage['action']=='conditionnement' else 'masque'] = str(reglage['valeur']) if reglage['action']=='conditionnement' else True
individuelles=[]
for r in plan['reglages']:
    p=subprocess.run([sys.executable,'-B',*r['arguments_python'],'--simuler'],capture_output=True,text=True,encoding='utf-8')
    individuelles.append({'repere':r['repere'],'code_retour':p.returncode,'stdout':p.stdout,'stderr':p.stderr})
assert all(x['code_retour']==0 for x in individuelles)
# L'appel est entièrement dans la copie ; aucune route humaine n'est utilisée.
nouveaux,deja=imp.ecrire(plan['faits_simules'],simuler=True)
assert len(nouveaux)==21 and deja==0
with journal_agents.verrou():
    journal_agents.verifier_pouvoirs('agent-donnees',[],racine/'donnees/pouvoirs.json')
    ajoutes,deja=imp.ecrire(plan['faits_simules'])
    action_import=journal_agents.enregistrer(agent='agent-donnees',message='SIMULATION EN COPIE : 21 positions déclarées dans la conversation',motif='Demande explicite du responsable : positions actuelles du soir, après mouvements ; copie protégée uniquement.',details={'ids':[f['id'] for f in ajoutes]},annulable=False)
rejoues,doublons=imp.ecrire(plan['faits_simules'])
assert rejoues==[] and doublons==21
sequenced=[]
for r in plan['reglages']:
    p=subprocess.run([sys.executable,'-B',*r['arguments_python']],capture_output=True,text=True,encoding='utf-8')
    sequenced.append({'repere':r['repere'],'code_retour':p.returncode,'stdout':p.stdout,'stderr':p.stderr})
    if p.returncode: break
assert len(sequenced)==16 and all(x['code_retour']==0 for x in sequenced[:15]) and sequenced[-1]['code_retour']!=0
assert 'plafond quotidien' in sequenced[-1]['stderr']
apres=list(faits.lire(racine/'donnees/faits'))
assert len(apres)==len(avant)+21
assert all((racine/'donnees/faits'/nom).read_bytes().startswith(contenu) for nom,contenu in prefixes.items())
assert apres[:len(avant)]==avant
positions=pos.calculer_depuis_faits(apres,complet,pos.charger_heures_reception_mail(),details=True)
resultats_positions=[]
for r in plan['positions']:
    article=positions[r['code']]
    assert article['position']==r['quantite'] and article['moment_mesure']=='soir'
    assert article['mouvements_depuis']==0
    resultats_positions.append({'repere':r['repere'],'code':r['code'],'colis':r['colis'],'par_colis':r['par_colis'],'unite':r['unite'],'quantite':r['quantite'],'resultat':article})
# La fixture ultérieure est fictive et reste en mémoire : son heure est comparée
# au repère technique du payload, jamais ajoutée aux carnets de la copie.
f0=plan['faits_simules'][0]
from datetime import datetime,timedelta
suite=copy.deepcopy(f0); suite['id']='fixture:recomptage-ulterieur'; suite['quantite']=2*f0['par_colis']; suite['colis']=2
suite['source']={'saisi_le':(datetime.fromisoformat(f0['enregistre_le'])+timedelta(seconds=1)).isoformat(timespec='seconds'),'fixture':True}
ordre=pos.calculer_depuis_faits(apres+[suite],complet,{},details=True)[f0['article']]
assert ordre['depart']['id']==suite['id'] and ordre['position']==suite['quantite']
temoins={code: {'avant':[f for f in avant if f.get('type')=='comptage' and f.get('article')==code][-1], 'apres':[f for f in apres if f.get('type')=='comptage' and f.get('article')==code][-1]} for code in ['0000087950042','0000087755078','0000087004035','0000087010621']}
assert all(x['avant']==x['apres'] for x in temoins.values())
# Aperçu intégral : paramètres des 18 décisions uniquement en mémoire.
# Ce calcul ne prétend pas que les 18 commandes passent le garde des quotas.
regles.charger=lambda *a,**k: copy.deepcopy(complet)
log=io.StringIO()
with contextlib.redirect_stdout(log):
    pos.main()
    gen.main()
proposition=json.loads((racine/'donnees/proposition.json').read_text(encoding='utf-8'))
lignes={x['itm8']:x for x in proposition['lignes']}
for r in plan['positions']:
    assert lignes[r['code']]['position_colis']==r['colis'], (r['code'],lignes[r['code']]['position_colis'],r['colis'])
for r in plan['reglages']:
    assert lignes[r['code']]['conditionnement']==r['valeur'] if r['action']=='conditionnement' else lignes[r['code']]['masque'] is True
assert lignes['0000087004035']['position_unites']==28
assert lignes['0000087010621']['position_unites']==plan['c09_position_actuelle']
codes=set(r['code'] for r in plan['positions']+plan['reglages'])
retour={'simulations_individuelles':individuelles,'simulation_sequentielle_gardes_reels':sequenced,'simulation_faits':{'nouveaux':len(ajoutes),'doublons_premier_passage':deja,'rejeu_nouveaux':len(rejoues),'rejeu_doublons':doublons,'action_copie':action_import,'prefixes_historiques_conserves':True,'faits_avant':len(avant),'faits_apres':len(apres)},'positions':resultats_positions,'recomptage_ulterieur_fictif_prioritaire':ordre,'temoins_faits_hors_lot':temoins,'hypothese_calcul_18_reglages_en_memoire':True,'proposition_apercu':[l for l in proposition['lignes'] if l['itm8'] in codes],'sortie_calcul':log.getvalue(),'journal_copie_apres':journal_agents.lire()[-20:]}
(racine/'resultat.json').write_text(json.dumps(retour,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'positions':len(resultats_positions),'reglages_simules_individuellement':len(individuelles),'reglages_acceptes_sequentiellement':len(sequenced)-1,'premier_refus':sequenced[-1]['repere'],'faits_hors_lot_conserves':True},ensure_ascii=False))
'''


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    instant=datetime.now().isoformat(timespec='seconds')
    assert instant[:10]=='2026-09-15' and instant[11:] >= '17:00:00', 'La convention de phase du soir doit être revue hors de ce soir.'
    identifiant=datetime.now().strftime('%Y%m%d-%H%M%S')
    photo=charger(RAPPORT)['etat_actuel']
    sys.path.insert(0,str(RACINE/'moteur'))
    import regles, catalogue, conditionnements, journal_agents
    config=regles.charger(); ref=catalogue.articles()
    proposition=charger(RACINE/'donnees/proposition.json')
    lignes={l['itm8']:l for l in proposition['lignes']}
    cadencier=charger(RACINE/'donnees/cadencier-du-jour.json')
    cad={a.get('article') or 'nom:'+a['nom']:a for a in cadencier['articles']}
    fichiers=[RAPPORT,DOSSIER/'demande-source.md',RACINE/'donnees/proposition.json',RACINE/'donnees/etat.json',RACINE/'donnees/decisions.jsonl',RACINE/'donnees/pouvoirs.json',RACINE/'donnees/cadencier-du-jour.json',RACINE/'donnees/catalogue.json',RACINE/'donnees/recalcul.json',*sorted((RACINE/'donnees/faits').glob('*.jsonl')),*sorted((RACINE/'donnees/journaux').glob('*.jsonl'))]
    fichiers=[p for p in fichiers if p.is_file()]
    empreintes={str(p):h(p) for p in fichiers}
    demandes_pcb={'C01':8,'C02':8,'C03':6.5,'C09':6,'C10':8,'C11':8}
    valeurs=[-1,-1,-1,-1,4,-1,0,0,0,0,-1,-1,-1,-1,-1,-1,0,-1,0,-1,-1]
    masques={'P02','P04','P06','P11','P12','P13','P14','P15','P16','P18','P20','P21'}
    positions=[]; reglages=[]
    for r in photo['colisages_a_verifier']:
        if r['repere'] not in demandes_pcb: continue
        n=demandes_pcb[r['repere']]
        motif=f"Demande explicite du responsable, conversation du 15 septembre 2026 ({r['repere']}) : fixer le contenu habituel à {n} {lignes[r['code']]['unite']} par colis ; conserver les quantités historiques."
        if r['repere']=='C09': motif+=' La caisse contient six sacs de 2,5 kg ; le box de 55 sacs est une autre offre.'
        args=['moteur/appliquer-decision.py','conditionnement',r['code'],str(n),'--auteur','agent-rayon','--motif',motif]
        selection=conditionnements.selectionner(cad.get(r['code']),{**config['overrides'].get(r['code'],{}),'conditionnement':str(n)},ref.get(r['code']))
        reglages.append({'repere':r['repere'],'code':r['code'],'produit':r['produit'],'action':'conditionnement','valeur':n,'avant':config['overrides'].get(r['code'],{}).get('conditionnement'),'pcb_affiche_avant':lignes[r['code']]['conditionnement'],'unite_actuelle':lignes[r['code']]['unite'],'motif':motif,'arguments_python':args,'selection_apres':selection})
    for r,n in zip(photo['positions_inconnues'],valeurs,strict=True):
        ligne=lignes[r['code']]
        assert ligne['position_colis'] is None, (r['repere'],'Une nouvelle position impose de revoir la source')
        pcb=ligne['conditionnement']; principal=next((p for p,m in config.get('groupes',{}).items() if r['code'] in m),r['code'])
        positions.append({'repere':r['repere'],'code':r['code'],'article_canonique':principal,'produit':r['produit'],'colis':n,'par_colis':pcb,'unite':ligne['unite'],'quantite':round(n*pcb,3),'date_effet':'2026-09-15','phase_physique':'soir après mouvements du jour','heure_physique':None,'masquer':r['repere'] in masques,'autres_listes':r['autres_listes'],'offres_comparees':cad.get(r['code'],{}).get('offres',[]),'limite_unite':'Libellé générique du moteur conservé ; aucun code caisse ni conversion kg/pièce inventé.' if r['code'].startswith('nom:') else None})
        if r['repere'] in masques:
            motif=f"Demande explicite du responsable, conversation du 15 septembre 2026 ({r['repere']} / {', '.join(r['autres_listes'])}) : article temporairement non vendu ; masquer sans supprimer l'article ni ses faits."
            args=['moteur/appliquer-decision.py','masquer',r['code'],'--auteur','agent-rayon','--motif',motif]
            reglages.append({'repere':r['repere'],'code':r['code'],'produit':r['produit'],'action':'masquer','valeur':True,'avant':config['overrides'].get(r['code'],{}).get('masque'),'motif':motif,'arguments_python':args})
    prefixe='comptage-conversation:reponses-articles-2026-09-15:'
    faits_simules=[{'id':prefixe+r['repere'],'type':'comptage','article':r['code'],'article_source':r['code'],'libelle':r['produit'],'date_source':'2026-09-15','date_effet':'2026-09-15','quantite':r['quantite'],'unite':r['unite'],'colis':r['colis'],'par_colis':r['par_colis'],'origine_mesure':'conversation-responsable','auteur':'agent-donnees','enregistre_le':instant,'source':{'canal':'conversation Codex','document_prive':'documents-partages/controles-stock/reponses-articles-2026-09-15/demande-source.md','sha256_document':h(DOSSIER/'demande-source.md'),'repere':r['repere'],'date_physique':'2026-09-15','phase_physique':'soir, après les mouvements de la journée','heure_physique':None,'repere_technique':'enregistre_le est un instant technique de préparation en simulation, pas une heure physique déclarée ; à remplacer par enregistrement effectif après avis.','message_id':None}} for r in positions]
    dernier={l['action']:l for l in journal_agents.lire() if l.get('action')}
    actions=[l for l in dernier.values() if l['action'].startswith('A-20260915-') and l.get('resultat')=='ok']
    plan={'prepare_le':instant,'statut_execution':'NON INTÉGRÉ','base_proposition_generee_le':proposition['genere_le'],'numero_photo':'etat_actuel : 21 P / 11 C / 18 R','reglages':reglages,'positions':positions,'faits_simules':faits_simules,'c09_position_actuelle':lignes['0000087010621']['position_unites'],'fournisseurs_deja_corrects':[{ 'repere':r,'code':code,'fournisseur':config['overrides'][code]['fournisseur'],'pcb_conserve':lignes[code]['conditionnement']} for r,code in [('C07','0000087004662'),('C08','0000087004082')]],'quotas':{'actions_reelles_avant':actions,'global_avant':len(actions),'rayon_avant':sum(x['agent']=='agent-rayon' for x in actions),'donnees_avant':sum(x['agent']=='agent-donnees' for x in actions),'limite_global':20,'limite_rayon':15,'lot_reglages':18,'lot_comptages_groupes':1,'recalcul_cadencier':1,'recalcul_filet':1,'global_total_necessaire':len(actions)+21,'rayon_total_necessaire':18,'donnees_total_necessaire':sum(x['agent']=='agent-donnees' for x in actions)+2},'empreintes_avant':empreintes,'c09_unite':{'catalogue_actuel':ref['0000087010621'],'proposition_actuelle':lignes['0000087010621']['unite'],'instruction_responsable':'Six sacs de 2,5 kg par caisse ; box de 55 sacs distinct.','decision_unite_supplementaire':False,'contradiction_source':'Export ERP du 15 septembre signalé kg par agent-articles ; le catalogue chargé reste pièce. Aucun import ERP ni conversion des faits dans ce lot.'},'limites':['Aucun réglage ni fait réel écrit ; avis indépendant et mandat final encore attendus.','Les 18 simulations isolées ne cumulent pas les quotas : le refus séquentiel est testé séparément.','Le calcul complet utilise les 18 réglages seulement en mémoire et ne prétend pas que leur exécution est autorisée par les plafonds actuels.','Les identifiants nom: restent provisoires : aucune fusion et aucun code magasin inventé.','Le repère technique est utilisé par le repli du moteur uniquement parce que la phase soir a été confirmée. Il ne démontre aucune heure physique exacte.','P03 : aucune commande ni livraison future ajoutée. P10/P14 : aucune substitution ou fusion ajoutée.','C04/C05/C06 restent à confirmer ; C07/C08 déjà Pomona, PCB5 conservé selon enquête factures.']}
    spec=importlib.util.spec_from_file_location('isolateur',RACINE/'tests/lancer_tests_isoles.py'); iso=importlib.util.module_from_spec(spec); spec.loader.exec_module(iso)
    with tempfile.TemporaryDirectory(prefix='preparation-articles-simulation-') as temporaire:
        base=Path(temporaire); copie=base/'projet'; copie.mkdir()
        for nom in ('moteur','donnees'):
            shutil.copytree(RACINE/nom,copie/nom,ignore=iso.ignorer_prives)
        iso.neutraliser_courrier(copie)
        garde=base/'garde'; garde.mkdir(); (garde/'sitecustomize.py').write_text(iso.GARDE,encoding='utf-8')
        env=os.environ.copy(); env.update(PYTHONDONTWRITEBYTECODE='1',PYTHONUTF8='1',PREPARATION_TEST_SANDBOX=str(base),PREPARATION_TEST_ORIGINAL=str(RACINE),PYTHONPATH=os.pathsep.join([str(garde),str(copie/'moteur')]))
        for nom in tuple(env):
            if any(s in nom.upper() for s in ('PASSWORD','MOT_DE_PASSE','SMTP','IMAP','GMAIL')): env.pop(nom)
        dump_nouveau(copie/'plan.json',plan)
        (copie/'simuler.py').write_text(ENFANT,encoding='utf-8')
        p=subprocess.run([sys.executable,'-B','simuler.py'],cwd=copie,env=env,capture_output=True,text=True,encoding='utf-8')
        plan['execution_simulation']={'code_retour':p.returncode,'stdout':p.stdout,'stderr':p.stderr,'protection_original_et_reseau':True}
        if (copie/'resultat.json').is_file(): plan['simulation']=charger(copie/'resultat.json')
    plan['empreintes_apres']={str(p):h(p) for p in fichiers}
    plan['donnees_originales_inchangees']=plan['empreintes_avant']==plan['empreintes_apres']
    sortie=DOSSIER/f'preparation-agent-donnees-{identifiant}.json'
    dump_nouveau(sortie,plan)
    print(json.dumps({'preuve':str(sortie),'code_retour':p.returncode,'stdout':p.stdout,'stderr':p.stderr,'donnees_originales_inchangees':plan['donnees_originales_inchangees']},ensure_ascii=False))
    return p.returncode


if __name__=='__main__':
    raise SystemExit(main())
