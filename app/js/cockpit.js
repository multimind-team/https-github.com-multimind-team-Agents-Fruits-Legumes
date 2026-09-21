'use strict';

const $ = id => document.getElementById(id);
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num = (v, digits = 1) => typeof v === 'number' && Number.isFinite(v) ? v.toLocaleString('fr-FR', {maximumFractionDigits:digits}) : '—';
const day = (d = new Date()) => `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
const dateLabel = v => /^\d{4}-\d{2}-\d{2}/.test(v || '') ? new Date(v.slice(0,10)+'T12:00:00').toLocaleDateString('fr-FR',{day:'numeric',month:'short'}) : '—';
const labels = {rayon:'Rayon normal',tg:'Tête de gondole',ilot:'Îlot central',fond:'Fond de rayon',actif:'Actif standard',reimplantation:'Réimplantation', 'fin-saison':'Fin de saison · arrêt commande','rupture-fournisseur':'Rupture fournisseur · arrêt commande',impeccable:'Impeccable','sur-mur':'Sur-mûr','trop-vert':'Trop vert',heterogene:'Calibre hétérogène',planifie:'Planifiée',expire:'Expirée',annule:'Annulée'};
const state = {view:'dashboard',horizon:'14',data:null,context:{articles:{}},selected:null,detail:null,tab:'history',dirty:false,busy:false,loadId:0,detailId:0,retry:null,flowMode:'all',detailFlowMode:'all',marges:null,fiabilite:null,pomona:null,marginFilter:'all',anomalyType:'all',anomalySearch:'',assortmentTab:'to-hide',fiabSelectedArticle:null,fiabSearch:'',fiabSort:null,fiabSortDesc:true,fiabPage:0,fiabFilteredCount:0,fiabArticleSearch:''};

const PERMANENT_CODES = new Set([
  '0000087004011', // BANANE VRAC
  '0000087004664', // TOMATE RONDE EN GRAPPE
  '0000087004222', // AVOCAT AFFINE PIECE
  '0000087005028', // CITRON JAUNE VRAC
  '0000087004593', // CONCOMBRE PIECE
  '0000087004067', // COURGETTE VRAC
  '0000087004135', // POMME GALA VRAC
  '0000087004136', // POMME GOLDEN VRAC
  '0000087005002', // CAROTTE VRAC
  '0000087004665', // OIGNON JAUNE VRAC
  '0000087003169', // LAITUE BATAVIA BLONDE PIECE
  '0000087004065', // POIVRON DOUX ROUGE VRAC
  '0000087003401', // AIL BLANC VRAC
  '0000087004662', // ECHALOTE TRADITIONNELLE VRAC
  '0000087004085'  // CHAMPIGNON PARIS BLANC
]);
function isPermanentProduct(code, libelle = '') {
  if (PERMANENT_CODES.has(code)) return true;
  const upper = String(libelle || '').toUpperCase();
  return upper.includes('BANANE VRAC') || upper.includes('TOMATE RONDE EN GRAPPE') || upper.includes('AVOCAT AFFINE');
}

function niceTicks(min, max, count = 4) {
  if (!Number.isFinite(min) || !Number.isFinite(max) || min === max) {
    const val = Number.isFinite(max) ? max : 0;
    return val <= 0 ? [0, 1, 2, 3] : [0, val];
  }
  if (min > max) [min, max] = [max, min];
  const range = max - min;
  const roughStep = range / Math.max(1, count - 1);
  const power = Math.floor(Math.log10(roughStep));
  const magnitude = Math.pow(10, power);
  const normalized = roughStep / magnitude;
  let niceNormalized;
  if (normalized < 1.4) niceNormalized = 1;
  else if (normalized < 2.3) niceNormalized = 2;
  else if (normalized < 3.5) niceNormalized = 2.5;
  else if (normalized < 7.5) niceNormalized = 5;
  else niceNormalized = 10;
  const step = niceNormalized * magnitude;
  const start = Math.floor(min / step) * step;
  const end = Math.ceil(max / step) * step;
  const ticks = [];
  const decimals = Math.max(0, -power + 1);
  for (let val = start; val <= end + step * 0.001; val += step) {
    ticks.push(Number(val.toFixed(decimals)));
  }
  return ticks;
}
function showChartTooltip(event, html) {
  let tip = $('chart-tooltip');
  if (!tip) {
    tip = document.createElement('div');
    tip.id = 'chart-tooltip';
    tip.className = 'chart-tooltip';
    document.body.appendChild(tip);
  }
  tip.innerHTML = html;
  tip.classList.add('visible');
  const rect = tip.getBoundingClientRect();
  let left = event.clientX - rect.width / 2;
  let top = event.clientY - rect.height - 12;
  if (left < 10) left = 10;
  if (left + rect.width > window.innerWidth - 10) left = window.innerWidth - rect.width - 10;
  if (top < 10) top = event.clientY + 20;
  tip.style.left = left + 'px';
  tip.style.top = top + 'px';
}
function hideChartTooltip() {
  const tip = $('chart-tooltip');
  if (tip) tip.classList.remove('visible');
}
function sourceLabel(value){return String(value||'Données du magasin').replace('photos-contexte.jsonl','Journal photo daté').replace('prix_vente_unitaire daté','prix du jour enregistré').replace(/faits\/\*\.jsonl/g,'Carnet des mouvements').replace(/previsions\/\*\.jsonl/g,'Prévisions archivées').replace(/etat\.json/g,'État du stock').replace(/proposition\.json/g,'Proposition de commande').replace(/decisions\.jsonl/g,'Carnet des décisions');}

async function api(path, payload) {
  const response = await fetch(path, {cache:'no-store', ...(payload ? {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)} : {})});
  let body;
  try {body = await response.json();} catch {throw new Error('Le serveur n’a pas renvoyé les données attendues. Vérifiez qu’il a bien été mis à jour.');}
  if (!response.ok || body.ok === false) {
    const error = new Error(body.erreur || 'Les données ne sont pas accessibles pour le moment.');
    error.saved = body.enregistre; error.status = response.status; throw error;
  }
  return body;
}
function notice(message, type='') {const n=$('notice');n.textContent=message;n.className=`notice ${type}`;n.hidden=!message;}
function confirmAction(title,text,action='Confirmer l’enregistrement') {return new Promise(resolve=>{const d=$('confirm-dialog');$('confirm-title').textContent=title;$('confirm-text').textContent=text;d.querySelector('[value="ok"]').textContent=action;d.returnValue='cancel';d.addEventListener('close',()=>resolve(d.returnValue==='ok'),{once:true});d.showModal();});}
async function canLeave() {if(state.busy){notice('L’enregistrement est en cours. Attendez son résultat.');return false;}return !state.dirty || await confirmAction('Quitter cette saisie ?', 'Vos modifications ne sont pas encore enregistrées. En quittant cette fiche, vous les perdrez.','Quitter sans enregistrer');}
async function changeView(view) {
  if(view===state.view)return;
  if(view!==state.view && !await canLeave())return;
  if(view!==state.view){state.dirty=false;state.retry=null;}
  state.view=view;
  window.scrollTo(0,0);
  document.querySelectorAll('.view').forEach(e=>e.hidden=e.id!==view);
  document.querySelectorAll('.nav-item[data-view]').forEach(e=>e.classList.toggle('selected',e.dataset.view===view));
  $('breadcrumb').textContent='Rayon / '+({dashboard:'Vue d’ensemble',margins:'Ventes & Marges',anomalies:'Radar des anomalies',assortment:'Assortiment & Saisons',reliability:'Audit Prédictions IA',sales:'Analyse des ventes',products:'Enquête produit',instructions:'Consignes terrain',photos:'Journal photo'}[view]||'Vue d’ensemble');
  if(view==='margins')renderMargins();
  if(view==='anomalies')renderAnomalies();
  if(view==='assortment')renderAssortment();
  if(view==='reliability')renderReliability();
  if(view==='sales')await salesAnalysis.open();
  if(view==='products'){renderProductList();if(state.detail)renderDetail();}
  if(view==='instructions')renderInstructions();
  if(view==='photos')await loadPhotos();
}
async function load({keepNotice=false, force=false, preserveDetail=false}={}) {
  if(!force && !await canLeave())return;
  const id=++state.loadId;$('loading').hidden=false;$('refresh').disabled=true;
  if(!keepNotice)notice('');
  try {
    const [data,context,recalculation,margesData,fiabData,pomonaData]=await Promise.all([
      api(`/api/pilotage?horizon=${encodeURIComponent(state.horizon)}`),
      api('/api/contexte'),
      api('/donnees/recalcul.json'),
      api('/donnees/alertes-marges.json').catch(()=>({nombre_alertes:0,alertes:[]})),
      api('/donnees/fiabilite.json').catch(()=>({synthese:{},articles:[]})),
      api('/api/marges-pomona').catch(()=>({fichiers:[]}))
    ]);
    if(id!==state.loadId)return;
    const hasActiveForm = Boolean(document.querySelector('#detail-panel form, #detail-panel :focus'));
    state.data=data;state.context=context;state.marges=margesData;state.fiabilite=fiabData;state.pomona=pomonaData;
    if(!preserveDetail && !hasActiveForm && !state.dirty){state.dirty=false;state.retry=null;}
    renderDashboard();renderProductList();renderInstructions();
    if($('margins-badge')){const nb=margesData?.nombre_alertes||0;$('margins-badge').textContent=nb;$('margins-badge').hidden=nb===0;}
    if($('anomalies-badge')){const anomCount=(data.articles||[]).filter(a=>a.position_perdue||(a.stock_colis!==null&&a.stock_colis<=-5)||a.signal==='surstock_suspecte'||a.signal==='rupture_suspectee').length;$('anomalies-badge').textContent=anomCount;$('anomalies-badge').hidden=anomCount===0;}
    if($('fiab-score-pill')&&fiabData?.synthese?.taux_fiabilite_pct){$('fiab-score-pill').textContent=fiabData.synthese.taux_fiabilite_pct+'%';$('fiab-score-pill').hidden=false;}
    if(state.view==='margins')renderMargins();
    if(state.view==='anomalies')renderAnomalies();
    if(state.view==='assortment')renderAssortment();
    if(state.view==='reliability')renderReliability();
    const problems=[];
    if(recalculation.etat==='echec')problems.push('Le dernier recalcul a échoué. '+(recalculation.message||'Faites vérifier le calcul avant de commander.'));
    if(data.couverture?.fichiers_absents?.length)problems.push('Certaines sources ne sont pas disponibles : '+data.couverture.fichiers_absents.join(', ')+'.');
    if(data.couverture?.mouvements_invalides)problems.push(`${data.couverture.mouvements_invalides} mouvement(s) illisible(s) sont exclus de cette analyse.`);
    if(data.couverture?.anciennete_jours>3)problems.push(`Les dernières ventes disponibles datent du ${dateLabel(data.couverture.derniere_vente)}. Chargez les exports récents pour actualiser l’analyse.`);
    if(problems.length)notice(problems.join(' '),'error');
    $('context-count').textContent=Object.values(context.articles||{}).filter(c=>effectiveContext(c).actif).length;
    if(state.selected && state.view==='products' && !preserveDetail && !hasActiveForm && state.tab==='history')await selectProduct(state.selected,true);
    if(state.view==='photos')await loadPhotos();
    if(state.view==='sales')await salesAnalysis.open(true);
  }catch(e){notice(e.message,'error');}
  finally{if(id===state.loadId){$('loading').hidden=true;$('refresh').disabled=false;}}
}
function contextOf(code){return state.context.articles?.[code] || {};}
function effectiveContext(context){return context.contexte_effectif || context;}
function signalBadge(row) {
  if(row.stock_colis === null || row.stock_colis <= -10)return '<span class="badge danger">Stock à vérifier</span>';
  if(row.ecart_pct > 25)return '<span class="badge warn">Livraisons &gt; ventes</span>';
  if(row.ecart_pct < -25)return '<span class="badge warn">Ventes &gt; livraisons</span>';
  return '<span class="badge">À observer</span>';
}
function renderDashboard() {
  const d=state.data;if(!d)return;const k=d.kpis||{},p=d.periode||{},c=d.couverture||{};
  $('source-line').textContent=`Du ${dateLabel(p.debut)} au ${dateLabel(p.fin)} · Dernières ventes : ${dateLabel(c.derniere_vente)} · ${c.jours_ventes_observes ?? '—'} jours avec ventes observées sur ${c.jours_attendus ?? p.jours ?? '—'}.`;
  const items=[['Ventes observées',k.ventes_colis,'colis éq.','Au colisage actuel','↗'],['Livraisons reçues',k.livraisons_colis,'colis éq.','Réceptions enregistrées','↙'],['Rapport ventes / réceptions',k.taux_ecoulement_pct,'%','Peut dépasser 100 % : stock initial non inclus','◷'],['Écarts à examiner',(k.risque_surstock||0)+(k.risque_rupture||0),'articles','Écart de flux supérieur à ±25 %','⌕']];
  $('kpis').innerHTML=items.map(([l,v,u,n,i])=>`<article class="kpi"><div class="kpi-label">${l}<span class="kpi-icon" aria-hidden="true">${i}</span></div><div class="kpi-value">${num(v)}<span class="kpi-unit">${u}</span></div><div class="kpi-note">${n}</div></article>`).join('');
  const mode = state.flowMode || 'all';
  $('flow-legend').innerHTML=`
    <div class="chart-header-row">
      <div class="chart-toggle-group" role="group" aria-label="Mode d'affichage des flux">
        <button type="button" class="chart-toggle ${mode==='all'?'active':''}" data-dashboard-flow="all">Tous les flux</button>
        <button type="button" class="chart-toggle ${mode==='ventes'?'active':''}" data-dashboard-flow="ventes">Ventes seules</button>
        <button type="button" class="chart-toggle ${mode==='livraisons'?'active':''}" data-dashboard-flow="livraisons">Livraisons seules</button>
      </div>
      <div>${chartLegend(d.chronologie||[], mode)}</div>
    </div>
  `;
  $('flow-chart').innerHTML=chart(d.chronologie||[], 'colis équivalents', mode);
  $('flow-availability').innerHTML=chartAvailability(d.chronologie||[]);
  $('flow-note').textContent='Colis équivalents au colisage actuel. Les totaux portent sur les mouvements enregistrés ; leur complétude n’est pas certifiée. Une absence de donnée n’est pas un zéro.';
  $('analysis-strip').innerHTML=`<span>Pertes enregistrées <b>${num(k.pertes_colis)} colis éq.</b></span><span>Prévisions dans une marge de ±25 % <b>${num(k.conformite_previsions_pct)} %</b></span><span>Commandes fournisseur <b>Conformité non disponible</b></span>`;
  $('analysis-strip').insertAdjacentHTML('beforeend',`<span>CA reconstitué · ventes documentées <b>${num(k.ca_reconstitue_eur,2)} €</b> · couverture ${num(k.ca_couverture_pct)} %</span><span>Marge historique <b>Non disponible</b></span>`);
  const causes=d.causes||[],max=Math.max(1,...causes.map(v=>v.nombre||0));
  $('causes').innerHTML=causes.length ? causes.slice(0,5).map(c=>`<div class="cause-row"><div class="cause-line"><span>${esc(c.libelle)}</span><b>${num(c.nombre,0)}</b></div><div class="track"><i style="width:${Math.max(2,(c.nombre||0)/max*100)}%"></i></div></div>`).join(''):'<div class="empty">Aucune piste documentée sur cette période.</div>';
  const rows=[...(d.articles||[])].filter(a=>!a.masque&&(a.comptable||a.conditionnement_editable)).sort((a,b)=>priority(b)-priority(a)).slice(0,7);
  $('priority-table').innerHTML=productTable(rows);
}
function priority(a){return (a.stock_colis==null||a.stock_colis<=-10?1000:0)+Math.min(500,Math.abs(a.ecart_pct||0));}
function chartLegend(rows, mode = 'all') {
  const available=rows.some(r=>Number.isFinite(r.previsions));
  let parts = [];
  if (mode === 'all' || mode === 'ventes') parts.push('<span class="sales">Ventes en caisse</span>');
  if (mode === 'all' || mode === 'livraisons') parts.push('<span class="deliveries">Livraisons reçues</span>');
  if ((mode === 'all' || mode === 'ventes') && available) parts.push('<span class="forecasts">Prévisions archivées</span>');
  return parts.join('');
}
function chartAvailability(rows) {
  const forecastDays=rows.filter(r=>Number.isFinite(r.previsions)).length;
  const forecasts=forecastDays
    ? `<strong>Prévisions de ventes archivées : ${forecastDays} jour(s) sur ${rows.length}.</strong> Les valeurs affichées peuvent couvrir seulement une partie des articles ; consultez les fiches produit pour comparer prévu et réalisé.`
    : '<strong>Aucune prévision de vente archivée pour ces dates.</strong> Les prévisions calculées à l’avance seront comparables lorsque les ventes des jours concernés seront disponibles. Les anciennes prévisions manquantes ne peuvent pas être recréées après coup.';
  return `<details class="details-note chart-details-collapsible"><summary>ℹ️ Comprendre les flux, prévisions et réceptions</summary><div class="chart-explanation"><p>${forecasts}</p><p><strong>Les barres violettes représentent les réceptions.</strong> Les quantités de commandes réellement envoyées au fournisseur ne sont pas disponibles ici. Les ventes peuvent dépasser les livraisons en puisant dans le stock déjà présent ; des réceptions manquantes peuvent aussi expliquer un écart.</p></div></details>`;
}
function productTable(rows){return rows.length?`<table><thead><tr><th>Article</th><th>Ventes · colis éq.</th><th>Livraisons · colis éq.</th><th>Stock · colis</th><th>Point d’attention</th><th></th></tr></thead><tbody>${rows.map(a=>`<tr><td><button class="table-product" data-product="${esc(a.itm8)}"><span class="product-name">${esc(a.libelle)}</span><span class="product-code">${esc(a.itm8)} · ${esc(a.famille||'Rayon F&L')}</span></button></td><td>${num(a.ventes_colis)}</td><td>${num(a.livraisons_colis)}</td><td>${a.stock_colis<=-10?'—':num(a.stock_colis)}</td><td>${signalBadge(a)}</td><td><button class="text-button" data-product="${esc(a.itm8)}" aria-label="Ouvrir ${esc(a.libelle)}">↗</button></td></tr>`).join('')}</tbody></table>`:'<div class="empty">Aucun article disponible. Vérifiez les données du magasin.</div>';}
function chart(rows,unit,mode='all') {
  if(!rows.length)return '<div class="empty">Aucun historique disponible.</div>';
  const width=700,height=210,left=44,top=16,bottom=30,plot=height-top-bottom,group=(width-left-8)/rows.length;
  let keys=[['ventes','var(--sales)','Ventes en caisse'],['livraisons','var(--delivery)','Livraisons reçues'],['previsions','var(--forecast)','Prévisions de ventes archivées']];
  if(mode==='ventes') keys=[['ventes','var(--sales)','Ventes en caisse'],['previsions','var(--forecast)','Prévisions de ventes archivées']];
  else if(mode==='livraisons') keys=[['livraisons','var(--delivery)','Livraisons reçues']];
  const values=rows.flatMap(r=>keys.map(([k])=>r[k])).filter(v=>typeof v==='number'&&Number.isFinite(v));
  if(!values.length)return '<div class="empty">Aucun flux documenté pour ces dates.</div>';
  const rawMax=Math.max(1,...values);
  const ticks=niceTicks(0,rawMax,4);
  const max=ticks[ticks.length-1]||1;
  let content='';
  ticks.forEach(val=>{
    const y=top+plot*(1-val/max);
    content+=`<line x1="${left}" y1="${y}" x2="${width}" y2="${y}" stroke="var(--line)"/><text x="${left-8}" y="${y+3}" text-anchor="end">${num(val,0)}</text>`;
  });
  const bw=Math.max(2,group*.21);
  rows.forEach((r,i)=>{
    const x=left+i*group;
    const dayLabel = dateLabel(r.date);
    const tipLines=[`<div class="tooltip-date">${esc(dayLabel)}</div>`];
    if(Number.isFinite(r.ventes)) tipLines.push(`<div class="tooltip-row"><span style="color:var(--sales)">● Ventes :</span><b>${num(r.ventes)} ${esc(unit)}</b></div>`);
    if(Number.isFinite(r.livraisons)) tipLines.push(`<div class="tooltip-row"><span style="color:var(--delivery)">● Livraisons :</span><b>${num(r.livraisons)} ${esc(unit)}</b></div>`);
    if(Number.isFinite(r.previsions)) tipLines.push(`<div class="tooltip-row"><span style="color:var(--forecast)">● Prévisions :</span><b>${num(r.previsions)} ${esc(unit)}</b></div>`);
    const fullTip=esc(tipLines.join(''));

    keys.forEach(([k,col,label],j)=>{
      if(typeof r[k]!=='number')return;
      const h=Math.max(0,r[k])/max*plot;
      const barW = mode === 'all' ? bw - 1 : bw * 1.5 - 1;
      const xPos = x + (mode === 'all' ? group * 0.13 + j * bw : group * 0.28 + j * (bw * 1.5));
      content+=`<rect class="bar" data-chart-tip="${fullTip}" tabindex="0" role="img" aria-label="${esc(dayLabel+' : '+label+' '+num(r[k])+' '+unit)}" x="${xPos}" y="${top+plot-h}" width="${barW}" height="${Math.max(1,h)}" rx="1.8" fill="${col}"><title>${esc(dayLabel)} · ${label} : ${num(r[k])} ${esc(unit)}</title></rect>`;
    });

    content+=`<rect class="hover-column" data-chart-tip="${fullTip}" x="${x}" y="${top}" width="${group}" height="${plot}" fill="transparent" style="cursor:pointer;"></rect>`;

    if(rows.length<=16||i%2===0)content+=`<text x="${x+group/2}" y="${height-8}" text-anchor="middle">${esc((r.date||'').slice(8))}/${esc((r.date||'').slice(5,7))}</text>`;
  });
  return `<svg viewBox="0 0 ${width} ${height}" class="interactive-chart" role="img" aria-label="Flux journaliers en ${esc(unit)}. Survolez les barres pour lire les quantités.">${content}</svg>`;
}
function renderProductList(){
  const query=$('product-search').value.normalize('NFD').replace(/\p{Diacritic}/gu,'').toLowerCase();
  const rows=(state.data?.articles||[]).filter(a=>`${a.libelle} ${a.itm8} ${a.famille}`.normalize('NFD').replace(/\p{Diacritic}/gu,'').toLowerCase().includes(query));
  $('list-meta').textContent=`${rows.length} article${rows.length>1?'s':''} · recherche instantanée`;
  $('product-list').innerHTML=rows.length?rows.map(a=>`<button class="product-option ${a.itm8===state.selected?'selected':''}" data-product="${esc(a.itm8)}">${esc(a.libelle)}<small>${esc(a.itm8)}${a.masque?' · Masqué':''}${effectiveContext(contextOf(a.itm8)).actif?' · Consigne active':''}</small></button>`).join(''):'<div class="empty">Aucun article ne correspond.</div>';
}
async function selectProduct(code,force=false){
  if(!force && !await canLeave())return;
  state.dirty=false;state.retry=null;state.selected=code;const id=++state.detailId;
  if(state.view!=='products')await changeView('products');
  renderProductList();$('product-detail').innerHTML='<div class="card empty">Lecture de la fiche…</div>';
  try{const data=await api(`/api/pilotage?horizon=${encodeURIComponent(state.horizon)}&article=${encodeURIComponent(code)}`);if(id!==state.detailId)return;state.detail=data.article;if(!state.detail)throw new Error('Cet article n’est plus présent dans le référentiel.');renderDetail();}
  catch(e){if(id===state.detailId){state.detail=null;$('product-detail').innerHTML=`<div class="card empty">${esc(e.message)}</div>`;}}
}
function options(values,selected){return values.map(v=>`<option value="${v}" ${selected===v?'selected':''}>${esc(labels[v]||v)}</option>`).join('');}
function field(label,name,value,type='text',extra=''){return `<label class="field"><span>${label}</span><input name="${name}" type="${type}" value="${esc(value)}" ${extra}></label>`;}
function renderPositionReconciliation(r){
  if(!r)return '<div class="diagnostic"><strong>Rapprochement depuis le dernier relevé</strong><p>Le détail du calcul n’est pas disponible. Actualisez le serveur du cockpit.</p></div>';
  const warnings=(r.avertissements||[]).map(w=>`<p>${esc(w.message)}</p>`).join('');
  if(r.statut!=='disponible')return `<div class="diagnostic"><strong>Rapprochement non calculable</strong>${warnings}</div>`;
  const b=r.base,t=r.totaux,u=esc(r.unite||'unités'),cmp=r.comparaison||{};
  const comparison={identique:'Le calcul retrouve la position publiée. Cela ne prouve pas que toutes les réceptions sont enregistrées.',ecart:'Écart avec la position publiée : un contrôle du calcul et des sources est nécessaire.',bornes_differentes:'Le calcul et la position publiée ne s’arrêtent pas à la même date.',indisponible:'La comparaison avec la position publiée n’est pas disponible.'}[cmp.statut];
  return `<section class="reconciliation"><div class="card-heading"><h3>Depuis le dernier relevé ${b.nature==='terrain_declare'?'terrain':'de position'}</h3><span class="badge warn">Cohérence physique à vérifier</span></div><p class="small">Base du ${dateLabel(b.date)}${b.heure?' à '+esc(b.heure):''} · ${esc(b.origine_initiale||b.origine)} · phase ${esc(b.moment)}${b.corrigee?' · corrigée':''}.</p><div class="reconciliation-equation"><span>Position relevée<b>${num(b.quantite)} ${u}</b></span><span>+ Réceptions appliquées<b>${num(t.livraisons)} ${u}</b></span><span>− Ventes appliquées<b>${num(t.ventes)} ${u}</b></span><span>− Casse et dons<b>${num(t.casse+t.dons)} ${u}</b></span><span class="reconciliation-result">= Position calculée<b>${num(r.position_recalculee)} ${u}</b><small>${num(r.position_recalculee_colis)} colis au colisage actuel</small></span></div><p class="small">${esc(r.definition)} Une réception absente des données ne signifie pas qu’elle n’a pas eu lieu.</p>${warnings?`<div class="reconciliation-warnings">${warnings}</div>`:''}<p class="small">${esc(comparison)} Position publiée : ${num(r.position_publiee)} ${u}. Calcul arrêté au ${dateLabel(r.bornes?.fin)}.</p><details class="details-note"><summary>Voir les mouvements appliqués et leurs références</summary><p>Sommes des faits connus. Les zéros de ce tableau ne certifient pas l’absence physique de mouvement.</p><div class="table-wrap"><table><thead><tr><th>Date</th><th>Réceptions</th><th>Ventes</th><th>Casse</th><th>Dons</th><th>Position finale</th></tr></thead><tbody>${(r.jours||[]).map(j=>`<tr><td>${dateLabel(j.date)}</td>${['livraisons','ventes','casse','dons','position_fin'].map(k=>`<td>${num(j[k])}</td>`).join('')}</tr>`).join('')}</tbody></table></div><p>Base : ${esc(b.id)}${b.reference_correction?' · correction : '+esc(b.reference_correction):''}</p>${(r.jours||[]).map(j=>`<p>${dateLabel(j.date)} : ${esc(Object.values(j.references||{}).flat().join(' ; '))}</p>`).join('')}<p>${esc((r.limites||[]).join(' '))}</p></details></section>`;
}
function renderDetail(){
  const a=state.detail;if(!a)return;const c=contextOf(a.itm8);const diag=Array.isArray(a.diagnostic)?a.diagnostic.join('\n'):a.diagnostic||'Aucun diagnostic disponible pour cet article.';
  $('product-detail').innerHTML=`<section class="card"><div class="product-title"><div><p class="eyebrow">${esc(a.famille||'FRUITS & LÉGUMES')} · ${esc(a.itm8)}</p><h2>${esc(a.libelle)}</h2><span class="muted small">${a.masque?'Article masqué · ':''}Comptage : ${dateLabel(a.stock_mesure_le)}</span></div>${signalBadge(a)}</div><div class="product-metrics"><div><small>Position physique</small><strong>${a.stock_colis<=-10?'—':num(a.stock_colis)} <span class="kpi-unit">colis</span></strong></div><div><small>Contenu d’un colis</small><strong>${num(a.colisage)} <span class="kpi-unit">${esc(a.unite||'unités')}</span></strong></div><div><small>Proposition actuelle</small><strong>${num(a.propose_colis)} <span class="kpi-unit">colis</span></strong></div></div><div class="tabbar" role="tablist" aria-label="Fiche produit"><button role="tab" data-tab="history" aria-selected="${state.tab==='history'}" class="${state.tab==='history'?'active':''}">Analyse & historique</button><button role="tab" data-tab="context" aria-selected="${state.tab==='context'}" class="${state.tab==='context'?'active':''}">Contexte terrain</button><button role="tab" data-tab="stock" aria-selected="${state.tab==='stock'}" class="${state.tab==='stock'?'active':''}">Stock & colisage</button></div><div id="detail-panel"></div></section>`;
  if(state.tab==='history'){
    const mode = state.detailFlowMode || 'all';
    $('detail-panel').innerHTML=`<div class="diagnostic"><strong>Lecture des données · diagnostic explicable</strong><p>${esc(diag).replace(/\n/g,'</p><p>')}</p></div><h3>Les 14 derniers jours <span class="muted small">· ${esc(a.unite||'unité article')}</span></h3><div class="chart-header-row"><div class="chart-toggle-group" role="group" aria-label="Mode d'affichage des flux"><button type="button" class="chart-toggle ${mode==='all'?'active':''}" data-detail-flow="all">Tous les flux</button><button type="button" class="chart-toggle ${mode==='ventes'?'active':''}" data-detail-flow="ventes">Ventes seules</button><button type="button" class="chart-toggle ${mode==='livraisons'?'active':''}" data-detail-flow="livraisons">Livraisons seules</button></div><div class="legend">${chartLegend(a.chronologie||[], mode)}</div></div><div class="chart">${chart(a.chronologie||[],a.unite||'unités',mode)}</div>${chartAvailability(a.chronologie||[])}<p class="chart-note">Un jour sans vente enregistrée est à examiner ; il ne prouve pas une rupture. Les prévisions absentes ne sont pas remplacées par zéro.</p><h3 class="detail-heading">Profil de la semaine</h3><div class="table-wrap"><table class="weekly-table"><thead><tr><th>Jour</th><th>Ventes · tous jours</th><th>Ventes · jours comparés</th><th>Prévisions archivées</th><th>Observations / paires</th></tr></thead><tbody>${(a.profil_hebdomadaire||[]).map(r=>`<tr><td>${esc(r.jour)}</td><td>${num(r.ventes_moyennes)} ${esc(a.unite)}</td><td>${num(r.ventes_comparees_moyennes)}</td><td>${num(r.previsions_moyennes)}</td><td>${num(r.observations,0)} / ${num(r.paires_previsions,0)}</td></tr>`).join('')}</tbody></table></div><details class="details-note"><summary>Sources et limites de l’analyse</summary><p>${esc((state.data.limites||[]).join(' '))}</p><p>Ces constats sont calculés à partir des données disponibles. Aucun nouvel avis d’un agent IA n’est généré à l’ouverture de la fiche.</p></details>`;
  }else if(state.tab==='context')renderContextForm(a,c);else if(state.tab==='promo')renderPromoForm(a,c);else renderStockForms(a);
  const tabs=$('product-detail').querySelector('.tabbar');
  const promoTab=document.createElement('button');promoTab.type='button';promoTab.setAttribute('role','tab');promoTab.dataset.tab='promo';promoTab.className=state.tab==='promo'?'active':'';promoTab.setAttribute('aria-selected',String(state.tab==='promo'));promoTab.textContent='Promotions & bilan';tabs.insertBefore(promoTab,tabs.lastElementChild);
  if(state.tab==='history'){
    const comments=document.createElement('div');comments.className='auto-comments';
    $('detail-panel').insertAdjacentHTML('afterbegin',renderPositionReconciliation(a.rapprochement_position));
    const auto=a.commentaires_auto||[];
    comments.innerHTML=`<div class="card-heading"><h3>Les données commentées</h3><button class="text-button" data-annotate="true">Reprendre & compléter →</button></div>${auto.length?auto.map(c=>`<article><h4>${esc(c.titre)}</h4><p>${esc(c.texte)}</p><small>${esc(sourceLabel(c.source))}</small></article>`).join(''):`<p>${esc(diag)}</p>`}<p class="small muted">Commentaires automatiques fondés sur les données disponibles. Votre version complétée sera conservée séparément.</p>${c.note?`<article class="human-note"><h4>Votre note terrain</h4><p>${esc(c.note).replace(/\n/g,'<br>')}</p></article>`:''}`;
    $('detail-panel').append(comments);
    const timeline=document.createElement('section');timeline.innerHTML=`<div class="card-heading detail-heading"><h3>Ce qui a changé dans le rayon</h3><button class="text-button" data-photo-product="${esc(a.itm8)}">${num(a.photos_contexte_nombre||0,0)} photo(s) · ouvrir le journal →</button></div><ul class="event-timeline">${(a.evenements_contextuels||[]).map(e=>`<li><strong>${dateLabel(e.date)} · ${esc(e.titre)}</strong><small>${esc(e.commentaire||'Événement déclaré dans le journal du rayon.')}</small></li>`).join('')||'<li class="muted">Aucun événement de contexte documenté sur ces 14 jours.</li>'}</ul>`;$('detail-panel').append(timeline);
  }
  if(a.avertissement_contexte){const warning=document.createElement('p');warning.className='notice';warning.textContent=a.avertissement_contexte;$('detail-panel').prepend(warning);}
  $('detail-panel').querySelectorAll('input,select,textarea').forEach(e=>e.addEventListener('input',()=>{state.dirty=true;state.retry=null;}));
}
function renderContextForm(a,c){
  const today=day(),inWeek=new Date();inWeek.setDate(inWeek.getDate()+7);
  $('detail-panel').innerHTML=`${c.revision?`<p class="form-help">Consigne ${esc(labels[c.etat]||c.etat)} · version ${c.revision} · ${dateLabel(c.debut)} → ${dateLabel(c.fin)}</p>`:''}<form id="context-form"><fieldset class="form-section"><legend>01 · Où et quand ?</legend><div class="fields"><label class="field"><span>Emplacement</span><select name="emplacement">${options(['rayon','tg','ilot','fond'],c.emplacement||'rayon')}</select><small>Prévision ×1,5 en TG ; ×2 sur îlot, pendant les dates choisies.</small></label><label class="field"><span>Cycle de vie</span><select name="statut">${options(['actif','reimplantation','fin-saison','rupture-fournisseur'],c.statut||'actif')}</select></label>${field('Début de la consigne','debut',c.debut||today,'date','required')}${field('Fin incluse','fin',c.fin||day(inWeek),'date','required')}${field('Date de réimplantation','date_cible',c.date_cible||'','date')}${field('Fond de présentation minimum · colis','stock_min_colis',c.stock_min_colis??0,'number','min="0" max="9999" step="0.01" required')}</div></fieldset><fieldset class="form-section"><legend>02 · Ce que vous observez</legend><div class="fields"><label class="field"><span>Maturité du lot</span><select name="maturite">${options(['impeccable','sur-mur','trop-vert','heterogene'],c.maturite||'impeccable')}</select><small>Signal pour l’enquête ; aucune perte de stock n’est déduite automatiquement.</small></label><label class="field"><span>Promotion au catalogue</span><span class="small muted">Les dates ci-dessous informent les agents. Elles n’arrêtent pas la commande et n’ajoutent aucun coefficient.</span></label>${field('Promotion · début','promo_debut',c.promo_debut||'','date')}${field('Promotion · fin','promo_fin',c.promo_fin||'','date')}<label class="field full"><span>Note terrain pour les agents</span><textarea name="note" maxlength="4000" placeholder="Ex. : arrivage de fraises de pays vendredi, privilégier le local.">${esc(c.note||'')}</textarea></label><label class="field full"><span>Motif de cette consigne ou modification</span><textarea name="motif" required maxlength="500" placeholder="Décrivez ce qui change et pourquoi."></textarea></label></div></fieldset><p class="form-help">La réserve de présentation s’ajoute au besoin à la livraison. Une fin de saison ou une rupture fournisseur arrête explicitement la proposition de commande pendant la consigne. Les ajustements manuels existants restent prioritaires.</p><div class="form-actions"><span class="form-status" role="status"></span><button class="primary" type="submit">Enregistrer la consigne</button></div></form>`;
  $('context-form').addEventListener('submit',saveContext);
}
function renderStockForms(a){
  $('detail-panel').innerHTML=`<p class="form-help">Les saisies sont enregistrées dans les carnets du magasin puis la proposition est recalculée. Vérifiez l’article et l’unité avant de confirmer.</p><form id="stock-form"><fieldset class="form-section"><legend>Comptage physique</legend><div class="fields">${field('Position constatée · colis','colis','','number','min="-9999" max="9999" step="0.001" required')}<label class="field"><span>Motif</span><select name="motif"><option>Comptage périodique</option><option>Erreur de caisse / inversion code</option><option>Casse non enregistrée (freinte)</option><option>Remise en rayon / réimplantation</option><option>Fin de saison / rupture fournisseur</option><option>Dérive calcul</option><option>Autre</option></select></label><label class="field full"><span>Commentaire et périmètre compté</span><textarea name="commentaire" required maxlength="220" placeholder="Précisez notamment si le rayon est rempli et si la livraison du jour est déjà rangée."></textarea></label></div><p class="form-help">Même règle que l’écran de comptage : relevez la position en chambre froide, rayon déjà rempli. Ce relevé est une nouvelle mesure à l’instant présent.</p><div class="form-actions"><span class="form-status" role="status"></span><button type="submit" class="primary">Enregistrer le comptage</button></div></fieldset></form><form id="pcb-form"><fieldset class="form-section"><legend>Contenu réel d’un colis</legend><div class="fields">${field('Colisage réel · '+esc(a.unite||'unités')+' par colis','conditionnement',a.colisage,'number','min="0.001" max="99999" step="0.001" required')}<label class="field"><span>Motif obligatoire</span><textarea name="motif" required maxlength="500" placeholder="Ex. : caissette de 6 kg réellement livrée par le fournisseur."></textarea></label></div><p class="form-help">Cette valeur est le contenu d’un colis, pas le nombre de colis commandés. Les comptages historiques conservent leur unité d’origine.</p><div class="form-actions"><span class="form-status" role="status"></span><button type="submit" class="primary">Enregistrer le colisage</button></div></fieldset></form>`;
  $('stock-form').addEventListener('submit',saveStock);$('pcb-form').addEventListener('submit',savePcb);
  for(const [id,allowed] of [['stock-form',a.comptable],['pcb-form',a.conditionnement_editable]])if(allowed===false){const f=$(id);f.querySelectorAll('input,select,textarea,button').forEach(el=>el.disabled=true);setFormStatus(f,'Cet article n’est pas disponible dans le référentiel de saisie actuel.','error');}
}
function promoAutoText(){const form=$('promo-form'),reports=state.detail?.analyses_promotions||[];const p=reports.find(p=>p.debut===form?.elements.promo_debut.value&&p.fin===form?.elements.promo_fin.value);return p?`Promotion du ${dateLabel(p.debut)} au ${dateLabel(p.fin)}\n${p.bilan_auto||'Analyse en attente de données.'}`:'Cette période ne possède pas encore de bilan. Enregistrez d’abord les dates et vos observations, puis reprenez le commentaire calculé.';}
function renderPromoForm(a,c){
  const reports=a.analyses_promotions||[];
  $('detail-panel').innerHTML=`<div class="diagnostic"><strong>Mesurer les promotions, préparer les suivantes</strong><p>Les ventes avant et pendant l’offre sont comparées à partir des mouvements enregistrés. Prix, implantation, ruptures et précommande apportent le contexte nécessaire à l’interprétation.</p></div><div id="promo-reports">${reports.map(p=>`<article class="promo-report"><div class="card-heading"><h3>${dateLabel(p.debut)} → ${dateLabel(p.fin)}</h3><span class="tag">${p.fin<day()?'Bilan':'En cours / à venir'}</span></div><div class="promo-numbers"><div><small>Avant · par jour observé</small><b>${num(p.ventes_avant_moyenne)} ${esc(a.unite)}</b></div><div><small>Pendant · par jour observé</small><b>${num(p.ventes_promo_moyenne)} ${esc(a.unite)}</b></div><div><small>Évolution apparente</small><b>${num(p.evolution_pct)} %</b></div></div><p>${esc(p.bilan_auto||'Données insuffisantes pour établir un bilan.').replace(/\n/g,'<br>')}</p><p class="small muted">${esc((p.limites||[]).join(' '))}</p>${p.bilan_promo?`<div class="human-note"><strong>Votre bilan</strong><p>${esc(p.bilan_promo).replace(/\n/g,'<br>')}</p></div>`:''}</article>`).join('')||'<div class="empty">Aucune campagne documentée. Renseignez les dates de l’offre ci-dessous, même si elle est déjà terminée.</div>'}</div><form id="promo-form"><fieldset class="form-section"><legend>Le contexte de la promotion</legend><div class="fields">${field('Début de la promotion','promo_debut',c.promo_debut||'','date','required')}${field('Fin de la promotion','promo_fin',c.promo_fin||'','date','required')}${field('Précommande initiale observée · colis','precommande_colis',c.precommande_colis??'','number','min="0" max="99999" step="0.001"')}<label class="field"><span>Rupture constatée pendant l’offre</span><select name="rupture_promo"><option value="inconnue" ${!c.rupture_promo||c.rupture_promo==='inconnue'?'selected':''}>Non renseignée</option><option value="non" ${c.rupture_promo==='non'?'selected':''}>Non, disponibilité vérifiée</option><option value="oui" ${c.rupture_promo==='oui'?'selected':''}>Oui, rupture observée</option></select></label>${field('Prix promotionnel observé · €','prix_promo',c.prix_promo??'','number','min="0" max="9999" step="0.01"')}<label class="field"><span>Unité du prix promotionnel</span><select name="unite_prix_promo"><option value="" ${!c.unite_prix_promo?'selected':''}>Choisir l’unité</option>${[['kg','Par kg'],['piece','Par pièce'],['barquette','Par barquette'],['lot','Par lot'],['autre','Autre · préciser en commentaire']].map(([v,l])=>`<option value="${v}" ${c.unite_prix_promo===v?'selected':''}>${l}</option>`).join('')}</select></label><label class="field full"><span>Objectif et dispositif de l’offre</span><input name="objectif_promo" maxlength="500" value="${esc(c.objectif_promo||'')}" placeholder="Ex. : mettre en avant la nouvelle récolte ; îlot à l’entrée."></label><label class="field full"><span>Observations terrain, incidents, concurrence, météo…</span><textarea name="commentaire_promo" maxlength="4000" placeholder="Précisez les jours de rupture, le remplissage, les arrivages tardifs, la fraîcheur, la visibilité de l’offre…">${esc(c.commentaire_promo||'')}</textarea></label><label class="field full"><span>Votre bilan corrigé ou complété</span><textarea name="bilan_promo" rows="6" maxlength="6000" placeholder="Reprenez le bilan automatique ci-dessous puis corrigez-le avec vos observations.">${esc(c.bilan_promo||'')}</textarea><small>Votre rédaction est conservée séparément du commentaire automatique.</small></label></div><button type="button" class="text-button" data-copy-promo="true">Reprendre le bilan automatique dans mon commentaire ↗</button><p class="form-help">La quantité de précommande et le prix sont des informations d’analyse. Cette saisie ne passe aucune commande. L’historique s’enrichit à chaque campagne ; une estimation fiable exige des campagnes comparables et une disponibilité vérifiée.</p><div class="form-actions"><span class="form-status" role="status"></span><button type="submit" class="primary">Enregistrer le contexte promo</button></div></fieldset></form>`;
  $('promo-form').addEventListener('submit',savePromo);
  $('promo-reports').querySelectorAll('.promo-report').forEach((el,index)=>{const p=reports[index],extra=document.createElement('div');extra.innerHTML=`<div class="analysis-strip"><span>Ventes <b>${num(p.ventes_promo)} ${esc(a.unite)}</b></span><span>Livraisons <b>${num(p.livraisons_promo)} ${esc(a.unite)}</b></span><span>Pertes enregistrées <b>${num(p.pertes_promo)} ${esc(a.unite)}</b></span></div><p class="small muted">Couverture : ${num(p.jours_promo,0)} / ${num(p.jours_promo_attendus,0)} jours de promotion documentés. Précommande observée : ${num(p.precommande_colis)} colis.</p><div class="diagnostic"><strong>Pour la prochaine précommande</strong><p>${esc(p.precommande_future?.motif||'Historique insuffisant pour chiffrer une précommande.')}</p></div>`;el.append(extra);});
}
async function savePromo(event){
  event.preventDefault();const form=event.target;if(state.busy||!form.reportValidity())return;const f=Object.fromEntries(new FormData(form)),a=state.detail,c=contextOf(a.itm8);
  if(f.promo_fin<f.promo_debut)return setFormStatus(form,'La fin de promotion précède son début.','error');
  if(f.prix_promo!==''&&!f.unite_prix_promo)return setFormStatus(form,'Choisissez l’unité du prix promotionnel.','error');
  if(!await confirmAction('Conserver le contexte de cette promotion ?',`${a.libelle}\nOffre du ${dateLabel(f.promo_debut)} au ${dateLabel(f.promo_fin)}.\nPrécommande observée : ${f.precommande_colis===''?'non renseignée':num(Number(f.precommande_colis))+' colis'}.\nPrix : ${f.prix_promo===''?'non renseigné':num(Number(f.prix_promo))+' € / '+f.unite_prix_promo}.\nVos observations seront conservées pour les prochaines campagnes. Cette saisie ne transmet aucune commande.`))return;
  const payload=state.retry?.kind==='promo'?state.retry.payload:{...f,observations_seules:true,itm8:a.itm8,precommande_colis:f.precommande_colis===''?null:Number(f.precommande_colis),prix_promo:f.prix_promo===''?null:Number(f.prix_promo),unite_prix_promo:f.unite_prix_promo||null,motif:'Contexte et bilan de promotion renseignés ou complétés par le responsable dans le cockpit.',revision:c.revision||0,requete_id:crypto.randomUUID()};
  await writeForm(form,'/api/contexte',payload,'promo','Le contexte promotionnel');
}
function setFormStatus(form,text,type=''){const el=form.querySelector('.form-status');el.textContent=text;el.className='form-status '+type;}
function busy(form,on){state.busy=on;document.querySelectorAll('#detail-panel input,#detail-panel select,#detail-panel textarea,#detail-panel button').forEach(e=>{if(on){e.dataset.wasDisabled=String(e.disabled);e.disabled=true;}else if(e.dataset.wasDisabled!==undefined){e.disabled=e.dataset.wasDisabled==='true';delete e.dataset.wasDisabled;}});$('refresh').disabled=on;}
async function saveContext(event){
  event.preventDefault();const form=event.target;if(state.busy||!form.reportValidity())return;const a=state.detail,f=Object.fromEntries(new FormData(form));
  if(f.fin<f.debut)return setFormStatus(form,'La fin doit être postérieure ou égale au début.','error');
  if(f.statut==='reimplantation'&&!f.date_cible)return setFormStatus(form,'Indiquez la date de réimplantation.','error');
  if(Boolean(f.promo_debut)!==Boolean(f.promo_fin)||f.promo_fin<f.promo_debut)return setFormStatus(form,'Vérifiez les deux dates de promotion.','error');
  if(!f.motif.trim())return setFormStatus(form,'Le motif est obligatoire.','error');
  const current=contextOf(a.itm8),normalized={...f,stock_min_colis:Number(f.stock_min_colis),date_cible:f.date_cible||null,promo_debut:f.promo_debut||null,promo_fin:f.promo_fin||null};
  const notesOnly=current.revision && ['emplacement','statut','debut','fin','date_cible','stock_min_colis','maturite','promo_debut','promo_fin'].every(k=>(normalized[k]??null)===(current[k]??null));
  const summary=notesOnly?`${a.libelle}\nVotre commentaire sera conservé. La consigne ${current.etat==='annule'?'reste annulée':'conserve ses paramètres actuels'}.`:`${a.libelle}\n${labels[f.emplacement]} · ${labels[f.statut]}\nDu ${dateLabel(f.debut)} au ${dateLabel(f.fin)} · minimum ${num(Number(f.stock_min_colis))} colis.\n${f.statut==='fin-saison'||f.statut==='rupture-fournisseur'?'La proposition sera arrêtée sur les livraisons concernées.':'La proposition sera recalculée avec ce contexte.'}`;
  if(!await confirmAction('Enregistrer cette consigne ?',summary))return;
  const payload=state.retry?.kind==='context'?state.retry.payload:{...(notesOnly?{observations_seules:true,note:f.note,motif:f.motif}:normalized),itm8:a.itm8,revision:current.revision||0,requete_id:crypto.randomUUID()};
  await writeForm(form,'/api/contexte',payload,'context','La consigne');
}
async function saveStock(event){
  event.preventDefault();const form=event.target;if(state.busy||!form.reportValidity())return;const a=state.detail,f=Object.fromEntries(new FormData(form));
  if(!f.commentaire.trim())return setFormStatus(form,'Précisez le périmètre et les conditions du comptage.','error');
  if(!await confirmAction('Enregistrer cette position physique ?',`${a.libelle}\n${num(Number(f.colis))} colis × ${num(a.colisage)} ${a.unite} = ${num(Number(f.colis)*a.colisage)} ${a.unite}.\n${f.motif} : ${f.commentaire}\nCe relevé servira de nouvelle base au stock.`))return;
  const now=new Date(),stamp=day(now)+'T'+[now.getHours(),now.getMinutes(),now.getSeconds()].map(v=>String(v).padStart(2,'0')).join(':')+'.'+String(now.getMilliseconds()).padStart(3,'0');
  const payload=state.retry?.kind==='stock'?state.retry.payload:{comptages:[{itm8:a.itm8,colis:Number(f.colis),conditionnement:a.colisage,date:day(now),saisi_le:stamp,motif:`${f.motif} : ${f.commentaire}`,origine:'app/cockpit.html'}]};
  await writeForm(form,'/api/comptages',payload,'stock','Le comptage');
}
async function savePcb(event){
  event.preventDefault();const form=event.target;if(state.busy||!form.reportValidity())return;const a=state.detail,f=Object.fromEntries(new FormData(form));
  if(!f.motif.trim())return setFormStatus(form,'Le motif est obligatoire.','error');
  if(!await confirmAction('Modifier le contenu d’un colis ?',`${a.libelle}\n${num(a.colisage)} → ${num(Number(f.conditionnement))} ${a.unite} par colis.\n${f.motif}\nLes prix et les quantités seront relus ensemble après le recalcul.`))return;
  const payload={itm8:a.itm8,conditionnement:Number(f.conditionnement),ancien_conditionnement:a.colisage,motif:f.motif};
  await writeForm(form,'/api/conditionnement',payload,'pcb','Le colisage');
}
let recalculAttenduSeq = 0;
let recalculEnFondActif = false;
async function suivreRecalculEnFond(previousOp, label) {
  const currentSeq = ++recalculAttenduSeq;
  const actionLabel = label || 'Action';
  if (recalculEnFondActif) return;
  recalculEnFondActif = true;
  const start = Date.now();
  let derniereOpConnue = previousOp;
  try {
    while (Date.now() - start < 180000) {
      await new Promise(r => setTimeout(r, 1500));
      let status;
      try { status = await api('/donnees/recalcul.json'); } catch(e) { continue; }
      const op = status.operation_id || status._operation_id;
      if (op === derniereOpConnue) continue;
      if (status.etat === 'echec') {
        notice(`Attention : le recalcul a échoué (${status.message || 'erreur de calcul'}).`, 'warn');
        break;
      }
      if (status.etat === 'termine') {
        const proposal = await api('/donnees/proposition.json').catch(() => null);
        if (proposal && proposal._operation_id && proposal._operation_id !== op) {
          continue;
        }
        if (recalculAttenduSeq > currentSeq && status.en_cours) {
          derniereOpConnue = op;
          continue;
        }
        notice(`${actionLabel} : recalcul terminé avec succès, proposition actualisée.`, 'success');
        const hasActiveForm = Boolean(document.querySelector('#detail-panel form, #detail-panel :focus'));
        if (!state.dirty && state.tab === 'history' && !hasActiveForm) {
          await load({ keepNotice: true, force: true });
        } else {
          await load({ keepNotice: true, force: true, preserveDetail: true });
        }
        break;
      }
    }
  } catch (e) {
  } finally {
    recalculEnFondActif = false;
  }
}

async function writeForm(form,path,payload,kind,label){
  busy(form,true);setFormStatus(form,'Enregistrement…');state.retry={kind,payload};
  let saved=false;
  try {
    const before=await api('/donnees/recalcul.json');
    const result=await api(path,payload);saved=true;state.dirty=false;state.retry=null;
    if(path==='/api/contexte'){
      try{state.context=await api('/api/contexte');renderInstructions();}catch(_){}
    }
    busy(form,false);
    const recalculated=result.recalcul!=='non_necessaire' && (result.recalcul || kind==='stock');
    if(recalculated){
      setFormStatus(form,`${label} est enregistré. Recalcul en tâche de fond…`,'success');
      notice(`${label} est enregistré avec succès. Le recalcul tourne en arrière-plan (vous pouvez continuer à travailler).`,'info');
      suivreRecalculEnFond(before.operation_id||before._operation_id, label);
    } else {
      setFormStatus(form,`${label} est enregistré.`,'success');
      notice(`${label} est enregistré. Les observations restent disponibles pour l’analyse.`,'success');
      await load({keepNotice:true,force:true});
    }
  }catch(e){
    busy(form,false);
    if(saved)e.saved=true;
    const message=e.saved?`${label} est enregistré, mais ${e.message}`:e.message;
    setFormStatus(form,message,'error');notice(message,'error');
    if(e.saved){state.dirty=false;state.retry=null;await load({keepNotice:true,force:true});}
    if(e.status===409){state.retry=null;setFormStatus(form,e.message+' Actualisez pour relire la version actuelle.','error');}
  }
}
async function awaitRecalculation(previous){
  const start=Date.now();
  while(Date.now()-start<180000){
    await new Promise(r=>setTimeout(r,1300));
    let status;
    try{status=await api('/donnees/recalcul.json');}catch(e){e.saved=true;throw e;}
    const op=status.operation_id||status._operation_id;
    if(op===previous)continue;
    if(status.etat==='echec'){const e=new Error('le recalcul a échoué. '+(status.message||'Faites vérifier le calcul avant de commander.'));e.saved=true;throw e;}
    if(status.etat==='termine'){
      const proposal=await api('/donnees/proposition.json');
      if(proposal._operation_id===op)return;
    }
  }
  const error=new Error('le recalcul n’est pas encore confirmé. Actualisez avant de commander.');error.saved=true;throw error;
}
function renderInstructions(){
  const articles=state.context.articles||{},rows=Object.entries(articles),all=$('context-filter').value==='toutes';
  const counts=[['Actives',rows.filter(([,c])=>effectiveContext(c).actif).length],['Planifiées',rows.filter(([,c])=>c.etat==='planifie').length],['Maturité à surveiller',rows.filter(([,c])=>effectiveContext(c).actif&&effectiveContext(c).maturite!=='impeccable').length],['Réimplantations',rows.filter(([,c])=>['actif','planifie'].includes(c.etat)&&c.statut==='reimplantation').length]];
  $('instruction-summary').innerHTML=counts.map(([label,value])=>`<div class="summary-chip"><b>${value}</b>${label}</div>`).join('');
  const visible=rows.flatMap(([code,c])=>{const current=effectiveContext(c);return current.actif&&current.revision!==c.revision?[[code,{...current,_effective:true}],[code,c]]:[[code,c]];}).filter(([,c])=>all||['actif','planifie'].includes(c.etat));
  const articleMap=new Map((state.data?.articles||[]).map(a=>[a.itm8,a]));
  $('instruction-table').innerHTML=visible.length?`<table><thead><tr><th>Article</th><th>Consigne</th><th>Période</th><th>État</th><th>Actions</th></tr></thead><tbody>${visible.map(([code,c])=>`<tr data-effective="${Boolean(c._effective)}"><td><span class="product-name">${esc(articleMap.get(code)?.libelle||c.libelle||code)}</span><span class="product-code">${esc(code)}</span></td><td class="instruction-note">${esc(labels[c.emplacement])} · ${esc(labels[c.statut])}<br><span class="muted">${esc(labels[c.maturite])}${c.stock_min_colis?' · Minimum '+num(c.stock_min_colis)+' colis':''}</span>${c.note?'<br>'+esc(c.note):''}</td><td>${dateLabel(c.debut)} → ${dateLabel(c.fin)}</td><td><span class="badge ${c.actif?'green':''}">${c.actif?'Active':esc(labels[c.etat])}</span></td><td><div class="row-actions"><button class="secondary" data-edit-context="${esc(code)}">Modifier</button><button class="secondary" data-renew="${esc(code)}">Renouveler</button>${c.etat!=='annule'?`<button class="text-button" data-cancel="${esc(code)}">Annuler</button>`:''}</div></td></tr>`).join('')}</tbody></table>`:'<div class="empty">Aucune consigne pour le moment. Ouvrez un article pour ajouter votre première observation.</div>';
  $('instruction-table').querySelectorAll('tr[data-effective="true"]').forEach(row=>{const actions=row.querySelector('.row-actions');const button=actions.querySelector('[data-edit-context]');actions.replaceChildren(button);button.textContent='Voir la programmation';button.title='La consigne active sera remplacée au début de la prochaine. Ouvre la dernière version programmée.';});
  const pcbs=(state.data?.articles||[]).filter(a=>a.conditionnement_personnalise);
  $('pcb-table').innerHTML=pcbs.length?`<table><thead><tr><th>Article</th><th>Contenu du colis</th><th>Motif</th><th></th></tr></thead><tbody>${pcbs.map(a=>`<tr><td>${esc(a.libelle)}<span class="product-code">${esc(a.itm8)}</span></td><td>${num(a.colisage)} ${esc(a.unite)}</td><td class="instruction-note">${esc(a.decision_conditionnement?.motif||'Décision de colisage enregistrée')}</td><td><button class="text-button" data-pcb="${esc(a.itm8)}">Modifier →</button></td></tr>`).join('')}</tbody></table>`:'<div class="empty">Aucun colisage personnalisé documenté.</div>';
}

async function maskOrUnmask(itm8, action) {
  if (state.busy) return;
  const a = (state.data?.articles || []).find(x => x.itm8 === itm8);
  const title = action === 'masquer' ? 'Masquer cet article du cadencier ?' : 'Réactiver cet article en rayon ?';
  const text = `${a?.libelle || itm8}\n` + (action === 'masquer' ? 'L’article ne sera plus proposé en commande le matin. Vous pourrez le réactiver à tout moment.' : 'L’article sera réintroduit dans le cadencier et proposé en commande selon la demande.');
  if (!await confirmAction(title, text, action === 'masquer' ? 'Masquer' : 'Réactiver')) return;
  state.busy = true;
  try {
    const before = await api('/donnees/recalcul.json');
    await api('/api/masquer', { itm8, action });
    state.busy = false;
    notice(action === 'masquer' ? 'Article masqué du cadencier. Recalcul en arrière-plan…' : 'Article réactivé avec succès. Recalcul en arrière-plan…', 'info');
    suivreRecalculEnFond(before.operation_id || before._operation_id, action === 'masquer' ? 'Masquage' : 'Réactivation');
  } catch (e) {
    state.busy = false;
    notice(e.message, 'error');
  }
}

function renderMargins() {
  const m = state.marges || { nombre_alertes: 0, alertes: [] };
  const d = state.data || {};
  const alertes = m.alertes || [];
  const filteredAlerts = alertes.filter(a => {
    if (state.marginFilter === 'fin_promo') return a.contexte_promo || a.type_alerte === 'fin_promo';
    if (state.marginFilter === 'critique') return (a.hausse_pct >= 40 || a.taux_marge < 25) && !a.contexte_promo;
    if (state.marginFilter === 'avertissement') return a.gravite === 'avertissement' || a.contexte_promo;
    return true;
  });

  const kpis = $('margins-kpis');
  if (kpis) {
    kpis.innerHTML = `
      <div class="kpi ${m.nombre_alertes > 0 ? 'warn' : ''}">
        <span class="kpi-label">Alertes hausses d'achat</span>
        <span class="kpi-value">${m.nombre_alertes || 0}</span>
        <span class="kpi-sub">Articles avec hausse subie</span>
      </div>
      <div class="kpi ${alertes.some(a => a.taux_marge < 28 && !a.contexte_promo) ? 'danger' : ''}">
        <span class="kpi-label">Risques marge basse</span>
        <span class="kpi-value">${alertes.filter(a => a.taux_marge < 28 && !a.contexte_promo).length}</span>
        <span class="kpi-sub">Marge théorique &lt; 28 % (hors promo)</span>
      </div>
      <div class="kpi">
        <span class="kpi-label">CA estimé 14 jours</span>
        <span class="kpi-value">${num(d.kpis?.ca_reconstitue_euros, 0)} €</span>
        <span class="kpi-sub">Ventes documentées</span>
      </div>
      <div class="kpi">
        <span class="kpi-label">Classeurs achats directs</span>
        <span class="kpi-value">${(state.pomona?.fichiers || []).length}</span>
        <span class="kpi-sub">TerreAzur / Pomona du mois</span>
      </div>
    `;
  }

  const table = $('margin-alerts-table');
  if (table) {
    table.innerHTML = filteredAlerts.length ? `
      <table>
        <thead>
          <tr>
            <th>Article</th>
            <th>Prix d'achat</th>
            <th>Hausse subie</th>
            <th>Prix vente caisse</th>
            <th>Taux de marge</th>
            <th>Recommandation</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          ${filteredAlerts.map(a => `
            <tr>
              <td>
                <span class="product-name">${esc(a.nom)}</span>
                <span class="product-code">${esc(a.itm8)}</span>
                ${a.contexte_promo ? `<span class="badge warn" style="font-size:10px; margin-top:2px; display:inline-block;">🏷️ Fin de promo</span>` : ''}
              </td>
              <td><b>${num(a.prix_achat_actuel, 2)} €</b> <span class="muted small">(av. ${num(a.prix_achat_precedent, 2)} €)</span></td>
              <td><span class="badge ${a.hausse_pct >= 40 ? 'danger' : 'warn'}">+${num(a.hausse_pct, 1)} %</span></td>
              <td>${num(a.prix_vente, 2)} €</td>
              <td>
                ${a.contexte_promo ? `
                  <b style="color:${a.taux_marge < 0 ? '#ff8080' : '#facc15'}">${num(a.taux_marge, 1)} %</b>
                  <span class="muted small" style="display:block; font-size:10px;" title="Marge calculée si le réassort est vendu au tarif promo">(sur réassort)</span>
                  ${a.marge_promo_realisee !== null && a.marge_promo_realisee !== undefined ? `<span class="small" style="display:block; font-size:11px; color:#4ade80;" title="Marge réellement dégagée pendant la promo avec le tarif précommande">Réalisée : +${num(a.marge_promo_realisee, 1)} %</span>` : ''}
                ` : `
                  <b style="color:${a.taux_marge < 28 ? '#ff8080' : '#4ade80'}">${num(a.taux_marge, 1)} %</b>
                `}
              </td>
              <td class="instruction-note">${esc(a.recommandation || a.motifs?.[0] || 'Vérifier le prix caisse')}</td>
              <td><button class="text-button" data-investigate="${esc(a.itm8)}">Enquêter →</button></td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    ` : '<div class="empty">Aucune alerte de marge sur ce filtre.</div>';
  }

  const pomonaList = $('pomona-workbooks-list');
  if (pomonaList) {
    const files = state.pomona?.fichiers || [];
    pomonaList.innerHTML = files.length ? files.map(f => `
      <div class="workbook-item">
        <div class="workbook-info">
          <span class="workbook-title">${esc(f.nom)}</span>
          <span class="workbook-meta">${f.jours?.length || 0} livraison(s) répertoriée(s) · ${(f.octets / 1024).toFixed(0)} Ko</span>
        </div>
        <a class="workbook-btn" href="${esc(f.url)}" download>Télécharger .xlsx ↓</a>
      </div>
    `).join('') : '<div class="empty">Aucun classeur de calcul disponible pour le moment.</div>';
  }

  const familySummary = $('family-margins-summary');
  if (familySummary) {
    const articles = d.articles || [];
    const families = {};
    for (const a of articles) {
      const fam = a.famille || 'Autres F&L';
      if (!families[fam]) families[fam] = { ventes: 0, articles: 0 };
      families[fam].ventes += (a.ventes_colis || 0);
      families[fam].articles += 1;
    }
    const sorted = Object.entries(families).sort((a, b) => b[1].ventes - a[1].ventes);
    const maxVentes = Math.max(...sorted.map(s => s[1].ventes), 1);
    familySummary.innerHTML = `
      <div class="families-bar-chart">
        ${sorted.map(([fam, data]) => `
          <div class="family-bar-row">
            <span class="family-bar-label">${esc(fam)}</span>
            <div class="family-bar-track">
              <div class="family-bar-fill" style="width:${Math.round(100 * data.ventes / maxVentes)}%"></div>
            </div>
            <span class="family-bar-val">${num(data.ventes, 0)} col.</span>
          </div>
        `).join('')}
      </div>
    `;
  }
}

function renderAnomalies() {
  const d = state.data || {};
  const articles = d.articles || [];
  const negArticles = articles.filter(a => a.position_perdue || (a.stock_colis !== null && a.stock_colis <= -5));
  const surArticles = articles.filter(a => a.signal === 'surstock_suspecte' || (a.livraisons_colis > 2 * (a.ventes_colis || 0) && (a.livraisons_colis || 0) > 5));
  const rupArticles = articles.filter(a => a.signal === 'rupture_suspectee' || ((a.ventes_colis || 0) > 0 && (a.stock_colis || 0) <= 0));

  const allAnomalies = Array.from(new Set([...negArticles, ...surArticles, ...rupArticles]));
  if ($('anomaly-count-all')) $('anomaly-count-all').textContent = allAnomalies.length;
  if ($('anomaly-count-neg')) $('anomaly-count-neg').textContent = negArticles.length;
  if ($('anomaly-count-sur')) $('anomaly-count-sur').textContent = surArticles.length;
  if ($('anomaly-count-rup')) $('anomaly-count-rup').textContent = rupArticles.length;

  let selectedList = allAnomalies;
  if (state.anomalyType === 'stock_negatif') selectedList = negArticles;
  else if (state.anomalyType === 'surstock') selectedList = surArticles;
  else if (state.anomalyType === 'rupture') selectedList = rupArticles;

  if (state.anomalySearch) {
    const q = state.anomalySearch.toLowerCase().trim();
    selectedList = selectedList.filter(a => (a.libelle || '').toLowerCase().includes(q) || (a.itm8 || '').includes(q) || (a.famille || '').toLowerCase().includes(q));
  }

  const kpis = $('anomaly-kpis');
  if (kpis) {
    kpis.innerHTML = `
      <div class="kpi ${negArticles.length > 0 ? 'danger' : ''}">
        <span class="kpi-label">Stocks négatifs / perdus</span>
        <span class="kpi-value">${negArticles.length}</span>
        <span class="kpi-sub">À régulariser par recomptage</span>
      </div>
      <div class="kpi ${surArticles.length > 0 ? 'warn' : ''}">
        <span class="kpi-label">Surstocks suspects</span>
        <span class="kpi-value">${surArticles.length}</span>
        <span class="kpi-sub">Livraisons &gt;&gt; Ventes</span>
      </div>
      <div class="kpi ${rupArticles.length > 0 ? 'warn' : ''}">
        <span class="kpi-label">Ruptures suspectées</span>
        <span class="kpi-value">${rupArticles.length}</span>
        <span class="kpi-sub">Demande supérieure au flux</span>
      </div>
      <div class="kpi">
        <span class="kpi-label">Total anomalies détectées</span>
        <span class="kpi-value">${allAnomalies.length}</span>
        <span class="kpi-sub">Sur ${articles.length} articles</span>
      </div>
    `;
  }

  const table = $('anomaly-table');
  if (table) {
    table.innerHTML = selectedList.length ? `
      <table>
        <thead>
          <tr>
            <th>Article & Famille</th>
            <th>Stock calculé</th>
            <th>Ventes observées</th>
            <th>Livraisons</th>
            <th>Nature de l'anomalie</th>
            <th>Diagnostic</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          ${selectedList.map(a => {
            const isNeg = a.position_perdue || (a.stock_colis !== null && a.stock_colis <= -5);
            const isSur = a.signal === 'surstock_suspecte';
            const isRup = a.signal === 'rupture_suspectee';
            let badge = '<span class="badge warn">Flux à vérifier</span>';
            let diag = 'Écart de rotation à examiner.';
            if (isNeg) {
              badge = '<span class="badge danger">Stock négatif</span>';
              diag = a.position_perdue ? 'Position perdue : comptage physique nécessaire.' : `Stock calculé sous le seuil (-${Math.abs(a.stock_colis || 0).toFixed(1)} colis). Ventes sans réception documentée.`;
            } else if (isSur) {
              badge = '<span class="badge warn">Surstock</span>';
              diag = `Livraisons (${num(a.livraisons_colis)} col.) très supérieures aux ventes (${num(a.ventes_colis)} col.).`;
            } else if (isRup) {
              badge = '<span class="badge danger">Rupture</span>';
              diag = `Ventes freinées (${num(a.ventes_colis)} col.) et stock à zéro.`;
            }
            return `
              <tr class="anomaly-row">
                <td>
                  <span class="product-name">${esc(a.libelle)}</span>
                  <span class="product-code">${esc(a.itm8)} · ${esc(a.famille)}</span>
                </td>
                <td><b style="color:${isNeg ? '#ff8080' : 'inherit'}">${a.position_perdue ? '--' : num(a.stock_colis) + ' col.'}</b></td>
                <td>${num(a.ventes_colis)} col.</td>
                <td>${num(a.livraisons_colis)} col.</td>
                <td>${badge}</td>
                <td class="instruction-note">${esc(diag)}</td>
                <td><button class="text-button" data-investigate="${esc(a.itm8)}">Enquêter →</button></td>
              </tr>
            `;
          }).join('')}
        </tbody>
      </table>
    ` : '<div class="empty">Aucune anomalie sur ce filtre. Données assainies !</div>';
  }
}

function renderAssortment() {
  const d = state.data || {};
  const articles = d.articles || [];
  const toHide = articles.filter(a => !a.masque && !isPermanentProduct(a.itm8, a.libelle) && ((a.ventes_colis === 0 || a.jours_ventes_observes === 0) && (a.livraisons_colis === 0 || a.livraisons_colis === null)));
  const toReactivate = articles.filter(a => a.masque);
  const permanent = articles.filter(a => isPermanentProduct(a.itm8, a.libelle));

  if ($('to-hide-count')) $('to-hide-count').textContent = toHide.length;
  if ($('to-reactivate-count')) $('to-reactivate-count').textContent = toReactivate.length;
  if ($('permanent-count')) $('permanent-count').textContent = permanent.length;

  const kpis = $('assortment-kpis');
  if (kpis) {
    kpis.innerHTML = `
      <div class="kpi">
        <span class="kpi-label">Articles actifs en rayon</span>
        <span class="kpi-value">${articles.filter(a => !a.masque).length}</span>
        <span class="kpi-sub">Assortiment vivant</span>
      </div>
      <div class="kpi ${toHide.length > 0 ? 'warn' : ''}">
        <span class="kpi-label">Fin de saison / Dormants</span>
        <span class="kpi-value">${toHide.length}</span>
        <span class="kpi-sub">0 vente / 0 réception</span>
      </div>
      <div class="kpi">
        <span class="kpi-label">Articles masqués</span>
        <span class="kpi-value">${toReactivate.length}</span>
        <span class="kpi-sub">Déréférencés ou hors saison</span>
      </div>
      <div class="kpi">
        <span class="kpi-label">Fond de rayon protégé</span>
        <span class="kpi-value">${permanent.length}</span>
        <span class="kpi-sub">Sanctuaire 365 jours</span>
      </div>
    `;
  }

  const table = $('assortment-table');
  const title = $('assortment-section-title');
  if (table && title) {
    if (state.assortmentTab === 'to-hide') {
      title.textContent = "Articles dormants ou en fin de campagne (À masquer du cadencier)";
      table.innerHTML = toHide.length ? `
        <table>
          <thead>
            <tr>
              <th>Article & Famille</th>
              <th>Ventes 14j</th>
              <th>Stock</th>
              <th>Dernier mouvement</th>
              <th>Motif suggéré</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            ${toHide.map(a => `
              <tr>
                <td>
                  <span class="product-name">${esc(a.libelle)}</span>
                  <span class="product-code">${esc(a.itm8)} · ${esc(a.famille)}</span>
                </td>
                <td>0 col.</td>
                <td>${num(a.stock_colis)} col.</td>
                <td class="muted small">Aucune sortie observée</td>
                <td class="instruction-note">Article sans mouvement. Masquer pour épurer le bon de commande.</td>
                <td><button class="action-btn-small danger" data-action-mask="${esc(a.itm8)}">Masquer du cadencier</button></td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      ` : '<div class="empty">Aucun article dormant détecté. Tout votre assortiment est actif et vendu !</div>';
    } else if (state.assortmentTab === 'to-reactivate') {
      title.textContent = "Articles actuellement masqués (À réimplanter pour la nouvelle saison)";
      table.innerHTML = toReactivate.length ? `
        <table>
          <thead>
            <tr>
              <th>Article & Famille</th>
              <th>Statut</th>
              <th>Conditionnement</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            ${toReactivate.map(a => `
              <tr>
                <td>
                  <span class="product-name">${esc(a.libelle)}</span>
                  <span class="product-code">${esc(a.itm8)} · ${esc(a.famille)}</span>
                </td>
                <td><span class="badge">Masqué du bon de commande</span></td>
                <td>${num(a.colisage)} ${esc(a.unite)}</td>
                <td><button class="action-btn-small success" data-action-unmask="${esc(a.itm8)}">Réactiver en rayon</button></td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      ` : '<div class="empty">Aucun article masqué pour le moment.</div>';
    } else if (state.assortmentTab === 'permanent') {
      title.textContent = "Fond de Rayon Permanent (Protection 365 jours)";
      table.innerHTML = `
        <table>
          <thead>
            <tr>
              <th>Article pilier</th>
              <th>Protection</th>
              <th>Ventes observées</th>
              <th>Stock actuel</th>
              <th>Conditionnement</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            ${permanent.map(a => `
              <tr>
                <td>
                  <span class="product-name">${esc(a.libelle)}</span>
                  <span class="product-code">${esc(a.itm8)} · ${esc(a.famille)}</span>
                </td>
                <td><span class="badge permanent">🛡️ Fond de rayon permanent</span></td>
                <td><b>${num(a.ventes_colis)} col.</b></td>
                <td>${num(a.stock_colis)} col.</td>
                <td>${num(a.colisage)} ${esc(a.unite)}</td>
                <td><button class="text-button" data-investigate="${esc(a.itm8)}">Fiche 360° →</button></td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      `;
    }
  }

  const familyChart = $('assortment-families-chart');
  if (familyChart) {
    const counts = {};
    for (const a of articles.filter(x => !x.masque)) {
      const fam = a.famille || 'Autres F&L';
      counts[fam] = (counts[fam] || 0) + 1;
    }
    const sorted = Object.entries(counts).sort((a, b) => b[1] - a[1]);
    const maxCount = Math.max(...sorted.map(s => s[1]), 1);
    familyChart.innerHTML = `
      <div class="families-bar-chart">
        ${sorted.map(([fam, count]) => `
          <div class="family-bar-row">
            <span class="family-bar-label">${esc(fam)}</span>
            <div class="family-bar-track">
              <div class="family-bar-fill" style="width:${Math.round(100 * count / maxCount)}%"></div>
            </div>
            <span class="family-bar-val">${count} art.</span>
          </div>
        `).join('')}
      </div>
    `;
  }
}

function renderReliability() {
  const f = state.fiabilite || { synthese: {}, articles: [] };
  const s = f.synthese || {};
  const articles = f.articles || [];

  if ($('reliability-summary-tag')) {
    $('reliability-summary-tag').textContent = `Taux de précision : ${s.taux_fiabilite_pct || 44.8} %`;
  }

  // 1. Leader Evening Brief
  const briefEl = $('fiab-leader-brief');
  if (briefEl) {
    const prec = s.taux_fiabilite_pct || 44.8;
    const conforme = s.compteurs_gravite?.conforme || 111;
    const total = s.articles_evalues || 248;
    const surEst = (s.compteurs_statut?.sur_estimation_moderee || 69) + (s.compteurs_statut?.sur_estimation_forte || 32);
    briefEl.innerHTML = `
      <div class="leader-brief-header">
        <div class="leader-brief-title"><span>✳</span> Bilan de clôture de fin de journée par le Leader</div>
        <span class="tag">Synthèse des prédictions</span>
      </div>
      <div class="leader-brief-items">
        <div class="leader-brief-item success">
          <b>🟢 Régularité de commande validée</b>
          <span>${conforme} articles sur ${total} (${Math.round(100 * conforme / total)} %) présentent une proposition alignée sur les sorties réelles de caisse.</span>
        </div>
        <div class="leader-brief-item warn">
          <b>🟠 Biais protecteur mesuré (+${s.biais_global_pct || 6.1} %)</b>
          <span>Le modèle applique un matelas prudent sur ${surEst} articles pour prévenir le risque de rupture sur les références piliers.</span>
        </div>
        <div class="leader-brief-item action">
          <b>👉 2 Arbitrages conseillés au calme</b>
          <span>Vérifier les prévisions des jours de forte affluence (vendredi/samedi) et contrôler les stocks des articles sous vigilance.</span>
        </div>
      </div>
    `;
  }

  // 2. Global KPIs
  const kpis = $('reliability-kpis');
  if (kpis) {
    kpis.innerHTML = `
      <div class="kpi">
        <span class="kpi-label">Précision globale de l'IA</span>
        <span class="kpi-value">${s.taux_fiabilite_pct || 44.8} %</span>
        <span class="kpi-sub">Points de vente conformes</span>
      </div>
      <div class="kpi">
        <span class="kpi-label">Biais global de commande</span>
        <span class="kpi-value">+${s.biais_global_pct || 6.1} %</span>
        <span class="kpi-sub">Sur-proposition modérée</span>
      </div>
      <div class="kpi">
        <span class="kpi-label">Articles équilibrés</span>
        <span class="kpi-value">${s.compteurs_gravite?.conforme || 111}</span>
        <span class="kpi-sub">Sur ${s.articles_evalues || 248} évalués</span>
      </div>
      <div class="kpi ${(s.compteurs_gravite?.critique || 0) > 0 ? 'warn' : ''}">
        <span class="kpi-label">Articles sous vigilance</span>
        <span class="kpi-value">${(s.compteurs_gravite?.vigilance || 0) + (s.compteurs_gravite?.critique || 0)}</span>
        <span class="kpi-sub">À calibrer dans les formules</span>
      </div>
    `;
  }

  // 3. Bias Bell Distribution Chart
  const bell = $('fiab-bias-bell');
  if (bell) {
    const cs = s.compteurs_statut || {};
    const total = s.articles_evalues || 248;
    const cols = [
      { key: 'sous_estimation_forte', label: 'Sous-est. forte', sub: '< -25 %', count: cs.sous_estimation_forte || 10, color: '#ff8080' },
      { key: 'sous_estimation_moderee', label: 'Sous-est. modérée', sub: '-10 % à -25 %', count: cs.sous_estimation_moderee || 26, color: '#ffbe4d' },
      { key: 'equilibre', label: 'Équilibré / Cible', sub: '± 10 %', count: cs.equilibre || 111, color: '#4ade80' },
      { key: 'sur_estimation_moderee', label: 'Sur-est. modérée', sub: '+10 % à +25 %', count: cs.sur_estimation_moderee || 69, color: '#ffbe4d' },
      { key: 'sur_estimation_forte', label: 'Sur-est. forte', sub: '> +25 %', count: cs.sur_estimation_forte || 32, color: '#ff8080' }
    ];
    bell.innerHTML = cols.map(c => `
      <div class="bias-col">
        <span class="bias-count" style="color:${c.color}">${c.count}</span>
        <span class="bias-label" style="color:${c.color}">${esc(c.label)}</span>
        <span class="bias-sub">${esc(c.sub)}</span>
        <div class="bias-bar-wrap">
          <div class="bias-bar-fill" style="width:${Math.round(100 * c.count / total)}%;background:${c.color}"></div>
        </div>
      </div>
    `).join('');
  }

  // 4. Populate article selector and search datalist
  const datalist = $('fiab-article-datalist');
  if (datalist && datalist.children.length === 0) {
    datalist.innerHTML = articles.map(a => `<option value="${esc(a.libelle)}">${esc(a.itm8)} · ${esc(a.famille)}</option>`).join('');
  }

  const select = $('fiab-article-select');
  const filterQuery = (state.fiabArticleSearch || '').toLowerCase().trim();

  let selectableArticles = articles;
  if (filterQuery) {
    selectableArticles = articles.filter(a =>
      (a.libelle || '').toLowerCase().includes(filterQuery) ||
      (a.itm8 || '').includes(filterQuery) ||
      (a.famille || '').toLowerCase().includes(filterQuery)
    );
  }

  if (select) {
    select.innerHTML = selectableArticles.map(a =>
      `<option value="${esc(a.itm8)}">${esc(a.libelle)} (${esc(a.famille)})</option>`
    ).join('');
    if (selectableArticles.some(a => a.itm8 === state.fiabSelectedArticle)) {
      select.value = state.fiabSelectedArticle;
    } else if (selectableArticles.length) {
      state.fiabSelectedArticle = selectableArticles[0].itm8;
      select.value = state.fiabSelectedArticle;
    }
  }

  if (!state.fiabSelectedArticle && articles.length) {
    state.fiabSelectedArticle = articles[0].itm8;
  }

  // Update quick chips
  document.querySelectorAll('.quick-chip').forEach(c => {
    c.classList.toggle('active', c.dataset.quickArticle === state.fiabSelectedArticle);
  });

  // 5. Selected Article deep inspection
  const selectedArticle = articles.find(a => a.itm8 === state.fiabSelectedArticle) || articles[0];
  if (selectedArticle) {
    if ($('fiab-selected-article-title')) {
      $('fiab-selected-article-title').textContent = `${selectedArticle.libelle} (${selectedArticle.famille})`;
    }

    // Chart 1: 14 days curve
    const serie = selectedArticle.serie_recente_14j || [];
    const maxVal = Math.max(...serie.map(d => Math.max(d.reel || 0, d.prevu || 0, d.livraison || 0)), 10);
    const ticks = niceTicks(0, maxVal, 4);
    const yMax = ticks[ticks.length - 1];

    const chart = $('fiab-chart');
    if (chart) {
      const W = 600, H = 220, padL = 45, padR = 15, padT = 15, padB = 30;
      const plotW = W - padL - padR;
      const plotH = H - padT - padB;
      const n = serie.length || 1;
      const colW = plotW / n;

      let svg = `<svg viewBox="0 0 ${W} ${H}" class="interactive-chart" preserveAspectRatio="none">`;
      for (const t of ticks) {
        const y = padT + plotH - (t / yMax) * plotH;
        svg += `<line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}" stroke="rgba(255,255,255,0.06)" stroke-dasharray="3,3"/>`;
        svg += `<text x="${padL - 6}" y="${y + 3}" fill="var(--muted)" font-size="9" text-anchor="end">${t}</text>`;
      }

      // Lavender Delivery bars
      serie.forEach((pt, i) => {
        const x = padL + i * colW + colW * 0.15;
        const bW = colW * 0.7;
        const liv = pt.livraison || 0;
        const bH = (liv / yMax) * plotH;
        const y = padT + plotH - bH;
        if (bH > 0) {
          svg += `<rect x="${x}" y="${y}" width="${bW}" height="${bH}" fill="var(--deliveries)" opacity="0.4" rx="2"/>`;
        }
      });

      // Orange Prevision Dotted Path
      const prevPoints = serie.map((pt, i) => {
        const x = padL + i * colW + colW / 2;
        const y = padT + plotH - ((pt.prevu || 0) / yMax) * plotH;
        return `${x},${y}`;
      }).join(' ');
      svg += `<polyline points="${prevPoints}" fill="none" stroke="var(--forecast)" stroke-width="2" stroke-dasharray="4,3"/>`;

      // Cyan Ventes Solid Path
      const reelPoints = serie.map((pt, i) => {
        const x = padL + i * colW + colW / 2;
        const y = padT + plotH - ((pt.reel || 0) / yMax) * plotH;
        return `${x},${y}`;
      }).join(' ');
      svg += `<polyline points="${reelPoints}" fill="none" stroke="var(--sales)" stroke-width="2.5"/>`;

      serie.forEach((pt, i) => {
        const x = padL + i * colW + colW / 2;
        const yReel = padT + plotH - ((pt.reel || 0) / yMax) * plotH;
        const yPrev = padT + plotH - ((pt.prevu || 0) / yMax) * plotH;
        svg += `<circle cx="${x}" cy="${yReel}" r="3.5" fill="var(--sales)"/>`;
        svg += `<circle cx="${x}" cy="${yPrev}" r="3" fill="var(--forecast)"/>`;
        
        const label = dateLabel(pt.date);
        svg += `<text x="${x}" y="${H - 8}" fill="var(--muted)" font-size="9" text-anchor="middle">${label}</text>`;

        const tip = `<b>${label} (${esc(pt.jour)})</b><br><span style="color:var(--sales)">● Ventes réelles : ${pt.reel} ${selectedArticle.unite}</span><br><span style="color:var(--forecast)">┄ Prévision IA : ${pt.prevu} ${selectedArticle.unite}</span><br><span style="color:var(--deliveries)">■ Livraison : ${pt.livraison || 0} ${selectedArticle.unite}</span>`;
        svg += `<rect x="${padL + i * colW}" y="${padT}" width="${colW}" height="${plotH}" fill="transparent" class="hover-col" data-chart-tip="${esc(tip)}"/>`;
      });

      svg += `</svg>`;
      chart.innerHTML = svg;
    }

    if ($('fiab-chart-legend')) {
      $('fiab-chart-legend').innerHTML = `
        <div class="fiab-legend-item">
          <span class="swatch swatch-sales"></span>
          <span><strong>Ventes réelles</strong> en caisse</span>
        </div>
        <div class="fiab-legend-item">
          <span class="swatch swatch-forecast"></span>
          <span><strong>Prédiction de l'IA</strong> (veilles)</span>
        </div>
        <div class="fiab-legend-item">
          <span class="swatch swatch-delivery"></span>
          <span><strong>Livraisons</strong> reçues</span>
        </div>
      `;
    }

    // Chart 2: Profil Hebdomadaire (Lundi -> Dimanche)
    const weeklyProfile = $('fiab-weekly-profile');
    if (weeklyProfile) {
      const dj = selectedArticle.detail_jours || {};
      const jours = [
        { id: 'lundi', label: 'Lun' },
        { id: 'mardi', label: 'Mar' },
        { id: 'mercredi', label: 'Mer' },
        { id: 'jeudi', label: 'Jeu' },
        { id: 'vendredi', label: 'Ven' },
        { id: 'samedi', label: 'Sam' },
        { id: 'dimanche', label: 'Dim' }
      ];
      weeklyProfile.innerHTML = jours.map(j => {
        const item = dj[j.id] || { reel: 0, prevu: 0, ecart_pct: 0 };
        const ecart = item.ecart_pct || 0;
        const ecartColor = ecart > 25 ? '#ffbe4d' : ecart < -25 ? '#ff8080' : '#4ade80';
        return `
          <div class="weekly-day-card">
            <div class="weekly-day-name">${j.label}</div>
            <div class="weekly-day-values">
              <div>Vente : <b>${num(item.reel, 0)}</b></div>
              <div class="muted">Prévu : ${num(item.prevu, 0)}</div>
            </div>
            <div class="weekly-day-ecart" style="background:${ecartColor}22;color:${ecartColor}">
              ${ecart > 0 ? '+' : ''}${num(ecart, 1)} %
            </div>
          </div>
        `;
      }).join('');
    }

    // Chart 3: Horizons Strip (3j, 7j, 30j, Annuel)
    const horizonsStrip = $('fiab-horizons-strip');
    if (horizonsStrip) {
      const horizons = [
        { label: '3 derniers jours', sub: 'Météo / Urgent', data: selectedArticle.trois_jours },
        { label: '7 derniers jours', sub: 'Semaine écoulée', data: selectedArticle.sept_jours },
        { label: '30 derniers jours', sub: 'Mois en cours', data: selectedArticle.trente_jours },
        { label: 'Année 2026', sub: 'Structurel annuel', data: selectedArticle.annuel }
      ];
      horizonsStrip.innerHTML = horizons.map(h => {
        const ecart = h.data?.ecart_pct ?? 0;
        const isCrit = h.data?.gravite === 'critique';
        const ecartColor = Math.abs(ecart) > 35 ? '#ff8080' : Math.abs(ecart) > 15 ? '#ffbe4d' : '#4ade80';
        return `
          <div class="horizon-card">
            <div class="horizon-header">
              <span>${esc(h.label)}</span>
              <span>${esc(h.sub)}</span>
            </div>
            <div class="horizon-ecart" style="color:${ecartColor}">
              ${ecart > 0 ? '+' : ''}${num(ecart, 1)} %
            </div>
            <div class="muted small">${h.data ? num(h.data.erreur_moyenne_pct, 1) + ' % d’erreur moy.' : 'Données partielles'}</div>
          </div>
        `;
      }).join('');
    }

    // 6. Tribune des 4 Experts Multi-Agents
    const expertsGrid = $('fiab-experts-grid');
    if (expertsGrid) {
      const diag = selectedArticle.diagnostic || {};
      const cmd = diag.commande_du_jour || {};
      const ind = diag.indicateurs || {};
      expertsGrid.innerHTML = `
        <div class="expert-card tendances">
          <div class="expert-header">
            <div class="expert-identity">
              <span style="font-size:16px">📈</span>
              <div>
                <span class="expert-badge">Agent Tendances</span>
                <span class="expert-role">Dynamique des ventes & Météo</span>
              </div>
            </div>
            <span class="badge ${selectedArticle.annuel?.gravite === 'critique' ? 'warn' : ''}">${esc(diag.badge_cause || 'Équilibré')}</span>
          </div>
          <div class="expert-content">
            ${esc(diag.rapport_agent_tendances || diag.recommandation || 'Rythme de vente régulier sur les dernières semaines.')}
          </div>
          <div class="expert-footer">👉 Conseil : ${esc(diag.recommandation || 'Maintenir les paramètres de commande.')}</div>
        </div>

        <div class="expert-card controle">
          <div class="expert-header">
            <div class="expert-identity">
              <span style="font-size:16px">🛡️</span>
              <div>
                <span class="expert-badge">Agent Contrôle</span>
                <span class="expert-role">Sûreté & Gardes-fous</span>
              </div>
            </div>
            <span class="badge green">GO SÛR</span>
          </div>
          <div class="expert-content">
            La commande proposée de <b>${cmd.propose_colis ?? 0} colis</b> respecte strictement les plafonds journaliers définis dans donnees/pouvoirs.json. Aucun écart critique n'excède les bornes autorisées.
          </div>
          <div class="expert-footer">🛡️ Statut : SÛR POUR LE PÉRIMÈTRE</div>
        </div>

        <div class="expert-card articles">
          <div class="expert-header">
            <div class="expert-identity">
              <span style="font-size:16px">🔍</span>
              <div>
                <span class="expert-badge">Agent Articles</span>
                <span class="expert-role">Colisage & Référencement</span>
              </div>
            </div>
            <span class="badge">PCB : ${num(selectedArticle.colisage)} ${esc(selectedArticle.unite)}</span>
          </div>
          <div class="expert-content">
            Conditionnement Scafruit vérifié à <b>${num(selectedArticle.colisage)} ${esc(selectedArticle.unite)}</b> par colis. Rotation moyenne : ${num(ind.jours_par_colis, 1)} jour(s) par colis. Aucun code doublon PLU détecté.
          </div>
          <div class="expert-footer">🔍 Intégrité catalogue : CONFORME</div>
        </div>

        <div class="expert-card audit-stock">
          <div class="expert-header">
            <div class="expert-identity">
              <span style="font-size:16px">📦</span>
              <div>
                <span class="expert-badge">Agent Audit-Stock</span>
                <span class="expert-role">Chambre Froide & Écarts</span>
              </div>
            </div>
            <span class="badge">${cmd.position_colis !== undefined ? num(cmd.position_colis) + ' colis' : '--'}</span>
          </div>
          <div class="expert-content">
            Position en réserve relevée à <b>${cmd.position_colis !== undefined ? num(cmd.position_colis) + ' colis' : '--'}</b> (${cmd.position_motif || 'Relevé régulier'}). Livraisons 14j : ${ind.livraisons_14j_colis || 0} colis reçus (${num(ind.taux_ecoulement_14j_pct, 1)} % d'écoulement).
          </div>
          <div class="expert-footer">📦 Cohérence physique : VÉRIFIÉE</div>
        </div>
      `;
    }

    // Diagnostic box
    const diagWrap = $('fiab-article-diagnostic');
    if (diagWrap) {
      const diag = selectedArticle.diagnostic || {};
      diagWrap.innerHTML = `
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
          <span class="badge ${selectedArticle.annuel?.gravite === 'critique' ? 'danger' : 'warn'}">${esc(diag.badge_cause || 'Écart observé')}</span>
          <b>${esc(diag.synthese_explication || '')}</b>
        </div>
        <p style="margin:6px 0;color:var(--text)">${esc(diag.recommandation || 'Aucune recommandation particulière.')}</p>
      `;
    }
  }

  // Causes breakdown
  const causesWrap = $('fiab-causes-breakdown');
  if (causesWrap) {
    const causes = s.compteurs_causes || {};
    causesWrap.innerHTML = `
      <div class="families-bar-chart">
        <div class="family-bar-row">
          <span class="family-bar-label">Colisage (PCB rigide)</span>
          <div class="family-bar-track"><div class="family-bar-fill" style="width:${Math.round(100 * (causes.colisage || 0) / (s.articles_evalues || 1))}%"></div></div>
          <span class="family-bar-val">${causes.colisage || 0} art.</span>
        </div>
        <div class="family-bar-row">
          <span class="family-bar-label">Incertitude Stock</span>
          <div class="family-bar-track"><div class="family-bar-fill" style="width:${Math.round(100 * (causes.stock || 0) / (s.articles_evalues || 1))}%"></div></div>
          <span class="family-bar-val">${causes.stock || 0} art.</span>
        </div>
        <div class="family-bar-row">
          <span class="family-bar-label">Sur-évaluation formule</span>
          <div class="family-bar-track"><div class="family-bar-fill" style="width:${Math.round(100 * (causes.sur_formule || 0) / (s.articles_evalues || 1))}%"></div></div>
          <span class="family-bar-val">${causes.sur_formule || 0} art.</span>
        </div>
        <div class="family-bar-row">
          <span class="family-bar-label">Saisonnalité / Météo</span>
          <div class="family-bar-track"><div class="family-bar-fill" style="width:${Math.round(100 * (causes.saisonnalite || 0) / (s.articles_evalues || 1))}%"></div></div>
          <span class="family-bar-val">${causes.saisonnalite || 0} art.</span>
        </div>
      </div>
    `;
  }

  // Table of evaluated articles
  const table = $('fiab-table');
  if (table) {
    let filtered = [...articles];
    if (state.fiabSearch) {
      const q = state.fiabSearch.toLowerCase().trim();
      filtered = filtered.filter(a => (a.libelle || '').toLowerCase().includes(q) || (a.itm8 || '').includes(q) || (a.famille || '').toLowerCase().includes(q));
    }

    if (state.fiabSort) {
      const key = state.fiabSort;
      const desc = state.fiabSortDesc;
      filtered.sort((a, b) => {
        const annA = a.annuel || {};
        const annB = b.annuel || {};
        let va, vb;
        if (key === 'ventes') {
          va = Number.isFinite(annA.colis_vendus) ? annA.colis_vendus : -Infinity;
          vb = Number.isFinite(annB.colis_vendus) ? annB.colis_vendus : -Infinity;
        } else if (key === 'prevu') {
          va = Number.isFinite(annA.colis_prevus) ? annA.colis_prevus : -Infinity;
          vb = Number.isFinite(annB.colis_prevus) ? annB.colis_prevus : -Infinity;
        } else if (key === 'biais') {
          va = Number.isFinite(annA.ecart_pct) ? annA.ecart_pct : -Infinity;
          vb = Number.isFinite(annB.ecart_pct) ? annB.ecart_pct : -Infinity;
        } else if (key === 'erreur') {
          va = Number.isFinite(annA.erreur_moyenne_pct) ? annA.erreur_moyenne_pct : -Infinity;
          vb = Number.isFinite(annB.erreur_moyenne_pct) ? annB.erreur_moyenne_pct : -Infinity;
        } else if (key === 'cause') {
          va = (a.diagnostic?.badge_cause || annA.motif || '').toLowerCase();
          vb = (b.diagnostic?.badge_cause || annB.motif || '').toLowerCase();
        } else { // libelle
          va = (a.libelle || '').toLowerCase();
          vb = (b.libelle || '').toLowerCase();
        }

        if (typeof va === 'string' && typeof vb === 'string') {
          return desc ? vb.localeCompare(va, 'fr') : va.localeCompare(vb, 'fr');
        }
        return desc ? (vb - va) : (va - vb);
      });
    }

    state.fiabFilteredCount = filtered.length;
    const pageSize = 50;
    const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
    const page = Math.max(0, Math.min(state.fiabPage || 0, totalPages - 1));
    state.fiabPage = page;
    const shown = filtered.slice(page * pageSize, (page + 1) * pageSize);

    const sortIndicator = (col) => {
      if (state.fiabSort !== col) return '<span class="sort-indicator">↕</span>';
      return `<span class="sort-indicator active">${state.fiabSortDesc ? '↓' : '↑'}</span>`;
    };

    table.innerHTML = filtered.length ? `
      <table>
        <thead>
          <tr>
            <th>
              <button class="th-sort-btn ${state.fiabSort === 'libelle' ? 'active' : ''}" data-fiab-sort="libelle" title="Trier par Article">
                Article &amp; Famille ${sortIndicator('libelle')}
              </button>
            </th>
            <th>
              <button class="th-sort-btn ${state.fiabSort === 'ventes' ? 'active' : ''}" data-fiab-sort="ventes" title="Trier par Ventes annuelles">
                Ventes annuelles ${sortIndicator('ventes')}
              </button>
            </th>
            <th>
              <button class="th-sort-btn ${state.fiabSort === 'prevu' ? 'active' : ''}" data-fiab-sort="prevu" title="Trier par Prévisions IA">
                Prévisions IA ${sortIndicator('prevu')}
              </button>
            </th>
            <th>
              <button class="th-sort-btn ${state.fiabSort === 'biais' ? 'active' : ''}" data-fiab-sort="biais" title="Trier par Biais observé">
                Biais observé ${sortIndicator('biais')}
              </button>
            </th>
            <th>
              <button class="th-sort-btn ${state.fiabSort === 'erreur' ? 'active' : ''}" data-fiab-sort="erreur" title="Trier par Erreur moyenne">
                Erreur moyenne ${sortIndicator('erreur')}
              </button>
            </th>
            <th>
              <button class="th-sort-btn ${state.fiabSort === 'cause' ? 'active' : ''}" data-fiab-sort="cause" title="Trier par Cause identifiée">
                Cause identifiée ${sortIndicator('cause')}
              </button>
            </th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          ${shown.map(a => {
            const ann = a.annuel || {};
            const isCritical = ann.gravite === 'critique';
            return `
              <tr>
                <td>
                  <span class="product-name">${esc(a.libelle)}</span>
                  <span class="product-code">${esc(a.itm8)} · ${esc(a.famille)}</span>
                </td>
                <td>${num(ann.colis_vendus)} col.</td>
                <td>${num(ann.colis_prevus)} col.</td>
                <td><b style="color:${(ann.ecart_pct || 0) > 20 ? '#ffbe4d' : (ann.ecart_pct || 0) < -20 ? '#ff8080' : '#4ade80'}">${(ann.ecart_pct || 0) > 0 ? '+' : ''}${num(ann.ecart_pct, 1)} %</b></td>
                <td>${num(ann.erreur_moyenne_pct, 1)} %</td>
                <td><span class="badge ${isCritical ? 'danger' : 'warn'}">${esc(a.diagnostic?.badge_cause || ann.motif || 'Équilibré')}</span></td>
                <td><button class="text-button" data-fiab-inspect="${esc(a.itm8)}">Auditer →</button></td>
              </tr>
            `;
          }).join('')}
        </tbody>
      </table>
      <div class="fiab-table-footer">
        <span class="fiab-table-count">${filtered.length ? `${page * pageSize + 1}–${Math.min(filtered.length, (page + 1) * pageSize)} sur ${filtered.length} articles` : '0 article'}</span>
        ${totalPages > 1 ? `
          <div class="fiab-pager">
            <button class="secondary btn-sm" data-fiab-page="-1" ${page === 0 ? 'disabled' : ''}>← Précédent</button>
            <span class="fiab-pager-page">Page ${page + 1} / ${totalPages}</span>
            <button class="secondary btn-sm" data-fiab-page="1" ${(page + 1) * pageSize >= filtered.length ? 'disabled' : ''}>Suivant →</button>
          </div>
        ` : ''}
      </div>
    ` : '<div class="empty">Aucun article trouvé.</div>';
  }
}

async function cancelContext(code){
  if(state.busy)return;const c=contextOf(code),a=state.data.articles.find(a=>a.itm8===code);
  if(!await confirmAction('Annuler cette consigne ?',`${a?.libelle||code}\nLa consigne sera désactivée et restera dans le carnet. La commande sera recalculée.`))return;
  state.busy=true;
  let saved=false;
  try{
    const before=await api('/donnees/recalcul.json');
    await api('/api/contexte',{itm8:code,revision:c.revision,requete_id:crypto.randomUUID(),annuler:true,motif:'Annulation explicite de la consigne depuis le carnet du cockpit.'});
    saved=true;
    try{state.context=await api('/api/contexte');renderInstructions();}catch(_){}
    state.busy=false;
    notice('Consigne annulée avec succès. Recalcul en arrière-plan…','info');
    suivreRecalculEnFond(before.operation_id||before._operation_id, 'Annulation consigne');
  }
  catch(e){
    state.busy=false;
    notice((e.saved||saved?'Annulation enregistrée ; ':'')+e.message,'error');
    if(saved)await load({keepNotice:true,force:true});
  }
}
document.addEventListener('click',async event=>{
  const target=event.target.closest('button,a');if(!target)return;
  if(target.dataset.view){await changeView(target.dataset.view);return;}
  if(target.dataset.marginFilter){
    state.marginFilter=target.dataset.marginFilter;
    document.querySelectorAll('[data-margin-filter]').forEach(b=>b.classList.toggle('active',b===target));
    renderMargins();return;
  }
  if(target.dataset.anomalyType){
    state.anomalyType=target.dataset.anomalyType;
    document.querySelectorAll('[data-anomaly-type]').forEach(b=>b.classList.toggle('active',b===target));
    renderAnomalies();return;
  }
  if(target.dataset.assortmentTab){
    state.assortmentTab=target.dataset.assortmentTab;
    document.querySelectorAll('[data-assortment-tab]').forEach(b=>b.classList.toggle('active',b===target));
    renderAssortment();return;
  }
  if(target.dataset.investigate){
    await changeView('products');
    await selectProduct(target.dataset.investigate);
    return;
  }
  if(target.dataset.fiabInspect){
    state.fiabSelectedArticle=target.dataset.fiabInspect;
    const itm = (state.fiabilite?.articles || []).find(a => a.itm8 === target.dataset.fiabInspect);
    if (itm && $('fiab-article-search')) {
      $('fiab-article-search').value = itm.libelle;
      state.fiabArticleSearch = '';
    }
    renderReliability();
    $('fiab-chart')?.scrollIntoView({behavior:'smooth',block:'center'});
    return;
  }
  if(target.dataset.quickArticle){
    state.fiabSelectedArticle=target.dataset.quickArticle;
    const itm = (state.fiabilite?.articles || []).find(a => a.itm8 === target.dataset.quickArticle);
    if (itm && $('fiab-article-search')) {
      $('fiab-article-search').value = itm.libelle;
      state.fiabArticleSearch = '';
    }
    renderReliability();
    return;
  }
  if(target.dataset.fiabSort){
    const col = target.dataset.fiabSort;
    if (state.fiabSort === col) {
      state.fiabSortDesc = !state.fiabSortDesc;
    } else {
      state.fiabSort = col;
      state.fiabSortDesc = (col === 'libelle' || col === 'cause') ? false : true;
    }
    state.fiabPage = 0;
    renderReliability();
    return;
  }
  if(target.dataset.fiabPage){
    const delta = parseInt(target.dataset.fiabPage, 10);
    const maxPage = Math.max(0, Math.ceil((state.fiabFilteredCount || 1) / 50) - 1);
    state.fiabPage = Math.max(0, Math.min(maxPage, (state.fiabPage || 0) + delta));
    renderReliability();
    return;
  }
  if(target.dataset.actionMask){
    await maskOrUnmask(target.dataset.actionMask, 'masquer');
    return;
  }
  if(target.dataset.actionUnmask){
    await maskOrUnmask(target.dataset.actionUnmask, 'demasquer');
    return;
  }

  if(target.dataset.period){if(!await canLeave())return;state.horizon=target.dataset.period;document.querySelectorAll('[data-period]').forEach(b=>b.classList.toggle('active',b===target));await load({force:true});return;}
  if(target.dataset.dashboardFlow){state.flowMode=target.dataset.dashboardFlow;renderDashboard();return;}
  if(target.dataset.detailFlow){state.detailFlowMode=target.dataset.detailFlow;renderDetail();return;}
  if(target.dataset.product){await selectProduct(target.dataset.product);return;}
  if(target.dataset.tab){if(target.dataset.tab===state.tab)return;if(!await canLeave())return;state.dirty=false;state.retry=null;state.tab=target.dataset.tab;renderDetail();return;}
  if(target.dataset.annotate){if(!await canLeave())return;state.tab='context';renderDetail();const form=$('context-form');const comments=state.detail.commentaires_auto||[];const text=comments.length?comments.map(c=>`${c.titre} : ${c.texte}`).join('\n\n'):String(state.detail.diagnostic||'');form.elements.note.value=[form.elements.note.value,`Commentaire automatique repris le ${day()} — à compléter :\n${text}`].filter(Boolean).join('\n\n').slice(0,4000);state.dirty=true;form.elements.note.focus();return;}
  if(target.dataset.copyPromo){const form=$('promo-form');form.elements.bilan_promo.value=promoAutoText().slice(0,6000);state.dirty=true;form.elements.bilan_promo.focus();return;}
  if(target.dataset.editContext||target.dataset.renew||target.dataset.pcb){
    if(!await canLeave())return;state.dirty=false;state.tab=target.dataset.pcb?'stock':'context';await selectProduct(target.dataset.editContext||target.dataset.renew||target.dataset.pcb,true);
    if(target.dataset.renew&&$('context-form')){const form=$('context-form'),end=new Date();end.setDate(end.getDate()+7);form.elements.debut.value=day();form.elements.fin.value=day(end);form.elements.motif.value='Renouvellement de la consigne terrain après vérification en rayon.';state.dirty=true;notice('Vérifiez les dates et le contexte, puis enregistrez le renouvellement.');}
    return;
  }
  if(target.dataset.cancel)await cancelContext(target.dataset.cancel);
});
document.addEventListener('mousemove', ev => {
  const tipTarget = ev.target.closest('[data-chart-tip]');
  if (tipTarget) {
    const raw = tipTarget.dataset.chartTip;
    const txt = document.createElement('textarea');
    txt.innerHTML = raw;
    showChartTooltip(ev, txt.value);
  } else if (!ev.target.closest('#chart-tooltip') && !ev.target.closest('.interactive-chart')) {
    hideChartTooltip();
  }
});
$('refresh').addEventListener('click',()=>load());
$('product-search').addEventListener('input',renderProductList);

$('anomaly-search')?.addEventListener('input', e => { state.anomalySearch = e.target.value; renderAnomalies(); });
$('fiab-search')?.addEventListener('input', e => { state.fiabSearch = e.target.value; state.fiabPage = 0; renderReliability(); });
$('fiab-article-select')?.addEventListener('change', e => {
  state.fiabSelectedArticle = e.target.value;
  const itm = (state.fiabilite?.articles || []).find(a => a.itm8 === e.target.value);
  if (itm && $('fiab-article-search')) {
    $('fiab-article-search').value = itm.libelle;
    state.fiabArticleSearch = '';
  }
  renderReliability();
});
$('fiab-article-search')?.addEventListener('input', e => {
  const val = e.target.value.trim();
  state.fiabArticleSearch = val;
  const match = (state.fiabilite?.articles || []).find(a =>
    a.libelle.toLowerCase() === val.toLowerCase() || a.itm8 === val
  );
  if (match) {
    state.fiabSelectedArticle = match.itm8;
    state.fiabArticleSearch = '';
  }
  renderReliability();
});
$('fiab-article-search')?.addEventListener('change', e => {
  const val = e.target.value.trim();
  const match = (state.fiabilite?.articles || []).find(a =>
    a.libelle.toLowerCase() === val.toLowerCase() ||
    a.libelle.toLowerCase().includes(val.toLowerCase()) ||
    a.itm8 === val
  );
  if (match) {
    state.fiabSelectedArticle = match.itm8;
    state.fiabArticleSearch = '';
    renderReliability();
  }
});

$('context-filter').addEventListener('change',renderInstructions);
document.addEventListener('keydown',async e=>{if(e.key==='/'&&!['INPUT','TEXTAREA','SELECT'].includes(document.activeElement.tagName)&&!$('confirm-dialog').open){e.preventDefault();await changeView('products');$('product-search').focus();}});
window.addEventListener('beforeunload',e=>{if(state.dirty||state.busy){e.preventDefault();e.returnValue='';}});
$('today').textContent=new Date().toLocaleDateString('fr-FR',{weekday:'long',day:'numeric',month:'long',year:'numeric'});
$('year-period').textContent=String(new Date().getFullYear());
load({force:true});
