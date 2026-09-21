'use strict';

// Calculs d'affichage purs : jamais de zéro substitué à une observation absente.
const SalesMath = (() => {
  const finite = Number.isFinite;
  const sum = values => { const known=values.filter(finite); return known.length?known.reduce((a,b)=>a+b,0):null; };
  const iso = d => d.toISOString().slice(0,10);
  const addDays = (d,n) => {const dt=new Date(d+'T12:00:00Z');dt.setUTCDate(dt.getUTCDate()+n);return iso(dt);};
  const dates = (start,end) => {const result=[];for(let d=start;d&&d<=end;d=addDays(d,1))result.push(d);return result;};
  const weekday = d => (new Date(d+'T12:00:00Z').getUTCDay()+6)%7;
  const key = (d,step) => step==='annee'?d.slice(0,4):step==='mois'?d.slice(0,7):step==='semaine'?addDays(d,-weekday(d)):d;
  const change = (a,b) => finite(a)&&finite(b)&&b!==0?(a-b)/Math.abs(b)*100:null;
  function niceTicks(min, max, count = 4) {
    if (!finite(min) || !finite(max) || min === max) {
      const val = finite(max) ? max : 0;
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
  function summarize(rows){
    const observed=new Set(rows.filter(r=>finite(r.ventes)).map(r=>r.date));
    const count=sum(rows.map(r=>r.ca_faits_ventes))||0,priced=sum(rows.map(r=>r.ca_faits_documentes))||0;
    const sales=sum(rows.map(r=>r.ventes_colis));
    return {ventes_colis:sales,ventes:sum(rows.map(r=>r.ventes)),livraisons_colis:sum(rows.map(r=>r.livraisons_colis)),pertes_colis:sum(rows.map(r=>r.pertes_colis)),ca_reconstitue_eur:sum(rows.map(r=>r.ca_reconstitue_eur)),jours:observed.size,ca_faits_ventes:count,ca_faits_documentes:priced,ca_couverture_pct:count?100*priced/count:null,moyenne:observed.size&&finite(sales)?sales/observed.size:null};
  }
  function model(data,f){
    const selected=new Set(f.products||[]),needle=(f.search||'').normalize('NFD').replace(/\p{Diacritic}/gu,'').toLowerCase();
    const articles=data.articles.filter(a=>(!f.family||a.famille===f.family)&&(!selected.size||selected.has(a.itm8))&&(f.hidden!=='visibles'||!a.masque)&&(`${a.libelle} ${a.itm8}`.normalize('NFD').replace(/\p{Diacritic}/gu,'').toLowerCase().includes(needle)));
    const codes=new Set(articles.map(a=>a.itm8)),articleIndex=new Map(articles.map(a=>[a.itm8,a])),days=new Set((f.weekdays||[0,1,2,3,4,5,6]).map(Number));
    const rows=data.jours.filter(r=>codes.has(r.itm8)&&days.has(weekday(r.date))&&(f.promo==='toutes'||(f.promo==='declaree'?r.promo_documentee:!r.promo_documentee)));
    const period=data.periode,comparison=data.comparaison||{};
    const current=rows.filter(r=>r.date>=period.debut&&r.date<=period.fin),previous=rows.filter(r=>comparison.debut&&r.date>=comparison.debut&&r.date<=comparison.fin);
    const byCode=new Map(),oldCode=new Map();
    for(const [source,target] of [[current,byCode],[previous,oldCode]])for(const r of source){if(!target.has(r.itm8))target.set(r.itm8,[]);target.get(r.itm8).push(r);}
    const ranking=articles.map(a=>{const summary=summarize(byCode.get(a.itm8)||[]),old=summarize(oldCode.get(a.itm8)||[]);return {...a,...summary,precedent:old[f.metric],jours_precedents:old.jours,difference:finite(summary[f.metric])&&finite(old[f.metric])?summary[f.metric]-old[f.metric]:null,evolution:change(summary[f.metric],old[f.metric]),valeur:summary[f.metric]};});
    const groupRows=(source,dimension)=>{const groups=new Map();for(const r of source){const a=articleIndex.get(r.itm8),k=dimension==='famille'?a.famille:dimension==='annee'?r.date.slice(0,4):r.itm8;if(!groups.has(k))groups.set(k,[]);groups.get(k).push(r);}return [...groups].map(([name,rs])=>({name,...summarize(rs)}));};
    const families=groupRows(current,'famille'),years=groupRows(current,'annee');
    const currentDates=dates(period.debut,period.fin).filter(d=>days.has(weekday(d))),oldDates=comparison.debut?dates(comparison.debut,comparison.fin).filter(d=>days.has(weekday(d))):[];
    const bucket=(source,ds)=>{const byDate=new Map();for(const r of source){if(!byDate.has(r.date))byDate.set(r.date,[]);byDate.get(r.date).push(r);}const buckets=new Map();for(const d of ds){const k=key(d,f.step);if(!buckets.has(k))buckets.set(k,{label:k,dates:[],rows:[]});const b=buckets.get(k);b.dates.push(d);b.rows.push(...(byDate.get(d)||[]));}return [...buckets.values()].map(b=>({...b,value:sum(b.rows.map(r=>r[f.metric]))}));};
    const temporal=bucket(current,currentDates),oldTemporal=bucket(previous,oldDates);
    let names=f.dimension==='produit'?ranking.filter(a=>finite(a.valeur)).sort((a,b)=>b.valeur-a.valeur).slice(0,f.top).map(a=>({name:a.libelle,id:a.itm8})):f.dimension==='famille'?families.filter(a=>finite(a[f.metric])).sort((a,b)=>b[f.metric]-a[f.metric]).slice(0,f.top).map(a=>({name:a.name,id:a.name})): [{name:'Sélection',id:'all'}];
    const series=names.map(n=>{const subset=f.dimension==='produit'?current.filter(r=>r.itm8===n.id):f.dimension==='famille'?current.filter(r=>articleIndex.get(r.itm8).famille===n.id):current;return {name:n.name,values:bucket(subset,currentDates).map(b=>b.value)};});
    if(f.dimension==='total'&&comparison.debut)series.push({name:'Période comparée',previous:true,values:temporal.map((_,i)=>oldTemporal[i]?.value??null),dates:oldTemporal.map(b=>b.label)});
    const transform=values=>{let cumulative=0;return values.map((v,i)=>{if(!finite(v))return null;if(f.transform==='cumul'){cumulative+=v;return cumulative;}if(f.transform==='moyenne'){const window=values.slice(Math.max(0,i-6),i+1).filter(finite);return sum(window)/window.length;}return v;});};
    series.forEach(s=>s.values=transform(s.values));
    const week=Array.from({length:7},(_,i)=>{const rs=current.filter(r=>weekday(r.date)===i),s=summarize(rs),observed=new Set(rs.filter(r=>finite(r[f.metric])).map(r=>r.date)).size;return {...s,name:['Lundi','Mardi','Mercredi','Jeudi','Vendredi','Samedi','Dimanche'][i],value:observed?sum(rs.map(r=>r[f.metric]))/observed:null,observations:observed};});
    return {articles,current,previous,summary:summarize(current),oldSummary:summarize(previous),ranking,families,years,temporal,series,week,expectedDays:currentDates.length};
  }
  return {sum,addDays,dates,weekday,key,change,summarize,model,niceTicks};
})();
if(typeof module!=='undefined'&&module.exports)module.exports=SalesMath;

if(typeof window!=='undefined')window.salesAnalysis=(()=>{
  const defaults={family:'',products:[],search:'',hidden:'tous',promo:'toutes',metric:'ca_reconstitue_eur',step:'jour',dimension:'total',top:5,transform:'brut',style:'courbes',weekdays:[0,1,2,3,4,5,6],sort:'valeur',descending:true,columns:['ventes_colis','ca_reconstitue_eur','ca_couverture_pct','jours','precedent','jours_precedents','evolution','livraisons_colis','pertes_colis']};
  const metrics={ventes:['Quantités enregistrées · produit unique','unités source à vérifier'],ventes_colis:['Ventes','colis éq.'],ca_reconstitue_eur:['CA reconstitué','€'],livraisons_colis:['Réceptions enregistrées','colis éq.'],pertes_colis:['Casse et dons enregistrés','colis éq.']};
  const columns={ventes_colis:'Ventes · colis éq.',ventes:'Ventes · unité article',ca_reconstitue_eur:'CA reconstitué · €',ca_couverture_pct:'Prix documentés · % faits',jours:'Jours avec ventes',moyenne:'Colis / jour observé',precedent:'Indicateur précédent',jours_precedents:'Jours ventes · comparaison',difference:'Écart absolu indicateur',evolution:'Évolution indicateur · %',livraisons_colis:'Réceptions · colis éq.',pertes_colis:'Pertes · colis éq.'};
  const palette=['#71bbdf','#edba58','#b19ce2','#8ec08c','#f393a3','#65d1c4','#e9945e','#c6c5af'];
  const storage='cockpit-analyse-ventes-v1';let data=null,filters={...defaults},model=null,page=0,request=0,initialized=false;
  const el=id=>document.getElementById(id),e=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const n=(v,d=1)=>Number.isFinite(v)?v.toLocaleString('fr-FR',{maximumFractionDigits:d}):'—';
  const options=(entries,value)=>entries.map(([k,v])=>`<option value="${e(k)}" ${String(k)===String(value)?'selected':''}>${e(v)}</option>`).join('');
  const select=(id,label,entries,value)=>`<label class="compact-field"><span>${label}</span><select id="${id}">${options(entries,value)}</select></label>`;

  function showTip(event, html) {
    let tip = el('chart-tooltip');
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
  function hideTip() {
    const tip = el('chart-tooltip');
    if (tip) tip.classList.remove('visible');
  }

  function save(){try{localStorage.setItem(storage,JSON.stringify({...filters,debut:el('sales-start').value,fin:el('sales-end').value,comparison:el('sales-comparison').value}));}catch{}}
  function status(message,error=false){el('sales-status').textContent=message;el('sales-status').className='sales-status'+(error?' error':'');}

  function renderChips() {
    const box = el('sales-chips-box');
    if (!box) return;
    if (!filters.products.length) {
      box.innerHTML = `<span class="chip-item global"><span class="chip-dot"></span>Tous les articles du rayon (sélection globale)</span>`;
      return;
    }
    const map = new Map((data?.articles || []).map(a => [a.itm8, a.libelle]));
    box.innerHTML = filters.products.map(code => {
      const name = map.get(code) || code;
      return `<span class="chip-item" data-code="${e(code)}">${e(name)} <button type="button" class="chip-del" data-del-product="${e(code)}" title="Retirer ${e(name)}">×</button></span>`;
    }).join('');
  }

  function updateDropdown(query) {
    const dd = el('sales-prod-dropdown');
    if (!dd || !data) return;
    const q = (query || '').trim().normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase();
    if (!q) { dd.hidden = true; dd.innerHTML = ''; return; }
    const matches = data.articles.filter(a =>
      (`${a.libelle} ${a.itm8} ${a.famille}`).normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase().includes(q)
    ).slice(0, 15);
    if (!matches.length) {
      dd.innerHTML = `<div class="sales-dropdown-item"><span class="muted">Aucun article trouvé pour « ${e(query)} »</span></div>`;
    } else {
      dd.innerHTML = matches.map(a => {
        const isSel = filters.products.includes(a.itm8);
        return `<div class="sales-dropdown-item" data-pick-product="${e(a.itm8)}"><span>${isSel ? '✓ ' : ''}${e(a.libelle)}</span><small>${e(a.famille)} · ${e(a.itm8)}</small></div>`;
      }).join('');
    }
    dd.hidden = false;
  }

  function initialize(){
    let saved={};try{saved=JSON.parse(localStorage.getItem(storage)||'{}')||{};}catch{}
    filters={...defaults,...saved};
    for(const [k,allowed] of Object.entries({metric:Object.keys(metrics),step:['jour','semaine','mois','annee'],dimension:['total','produit','famille'],hidden:['tous','visibles'],promo:['toutes','declaree','sans'],style:['courbes','barres'],transform:['brut','cumul','moyenne']}))if(!allowed.includes(filters[k]))filters[k]=defaults[k];
    filters.products=Array.isArray(filters.products)?filters.products.filter(x=>typeof x==='string'):[];filters.columns=Array.isArray(filters.columns)?filters.columns.filter(x=>columns[x]):defaults.columns;
    filters.weekdays=Array.isArray(filters.weekdays)?filters.weekdays.filter(x=>Number.isInteger(x)&&x>=0&&x<=6):defaults.weekdays;
    filters.top=[3,5,10].includes(Number(filters.top))?Number(filters.top):5;

    el('sales-workspace').innerHTML=`
      <form id="sales-filters" class="sales-toolbar-compact">
        <div class="sales-bar-main">
          <div class="sales-presets-pills" role="group" aria-label="Périodes prédéfinies">
            <button type="button" class="pill-btn" data-sales-days="7">7 j</button>
            <button type="button" class="pill-btn" data-sales-days="14">14 j</button>
            <button type="button" class="pill-btn" data-sales-days="30">30 j</button>
            <button type="button" class="pill-btn" data-sales-days="90">90 j</button>
            <button type="button" class="pill-btn" data-sales-days="365">1 an</button>
            <button type="button" class="pill-btn" data-sales-days="all">Tout</button>
          </div>
          <div class="sales-date-range">
            <label class="compact-field"><span>Du</span><input id="sales-start" type="date" required value="${/^\d{4}-\d{2}-\d{2}$/.test(saved.debut||'')?saved.debut:''}"></label>
            <label class="compact-field"><span>Au</span><input id="sales-end" type="date" required value="${/^\d{4}-\d{2}-\d{2}$/.test(saved.fin||'')?saved.fin:''}"></label>
            ${select('sales-comparison','Comparer avec',[['precedente','Période précédente'],['annee_precedente','Mêmes dates n-1'],['aucune','Sans comparaison']],saved.comparison||'precedente')}
            ${select('sales-year','Année',[['','Année...']],'')}
          </div>
          <div class="sales-quick-selectors">
            ${select('sales-metric','Indicateur',Object.entries(metrics).map(([k,v])=>[k,v.join(' · ')]),filters.metric)}
            ${select('sales-dimension','Courbes par',[['total','Total sélection'],['produit','Par produit'],['famille','Par famille']],filters.dimension)}
            ${select('sales-step','Pas',[['jour','Jour'],['semaine','Semaine'],['mois','Mois'],['annee','Année']],filters.step)}
          </div>
          <div class="sales-toolbar-actions">
            <button type="button" class="secondary" id="sales-toggle-adv" title="Afficher ou masquer les filtres avancés">⚙️ Filtres</button>
            <button type="submit" class="primary" id="sales-apply">Actualiser</button>
          </div>
        </div>

        <div class="sales-product-bar">
          <div class="sales-product-chips" id="sales-chips-box"></div>
          <div class="sales-product-search-wrap">
            <input type="search" id="sales-prod-search" placeholder="🔍 Rechercher et ajouter un article à comparer..." autocomplete="off">
            <div id="sales-prod-dropdown" class="sales-dropdown" hidden></div>
          </div>
          <button type="button" class="text-button" id="sales-clear-products">Réinitialiser la sélection</button>
        </div>

        <div id="sales-advanced-drawer" class="sales-advanced-drawer" hidden>
          <div class="sales-filter-grid">
            ${select('sales-family','Famille',[['','Toutes les familles']],filters.family)}
            ${select('sales-promo','Promotion',[['toutes','Tous les jours'],['declaree','Jours en promo documentée'],['sans','Jours sans promo']],filters.promo)}
            ${select('sales-hidden','Articles masqués',[['tous','Tous (inclus masqués)'],['visibles','Articles non masqués']],filters.hidden)}
            ${select('sales-style','Graphique',[['courbes','Courbes'],['barres','Barres']],filters.style)}
            ${select('sales-transform','Lissage / Cumul',[['brut','Valeurs observées'],['cumul','Cumul'],['moyenne','Moyenne mobile (7j)']],filters.transform)}
            ${select('sales-top','Top N',[[3,'Top 3'],[5,'Top 5'],[10,'Top 10']],filters.top)}
          </div>
          <div class="sales-checks">
            <span class="muted small">Jours de vente inclus :</span>
            ${['Lun','Mar','Mer','Jeu','Ven','Sam','Dim'].map((d,i)=>`<label><input type="checkbox" data-sales-weekday="${i}" ${filters.weekdays.includes(i)?'checked':''}>${d}</label>`).join('')}
            <button type="button" class="text-button" id="sales-reset" style="margin-left:auto;">Rétablir réglages par défaut</button>
          </div>
        </div>
        <select id="sales-products" multiple hidden></select>
        <input id="sales-search" type="hidden" value="${e(filters.search)}">
      </form>
      <p id="sales-status" class="sales-status" role="status"></p>
      <div id="sales-results"></div>
    `;

    el('sales-filters').addEventListener('submit',event=>{event.preventDefault();loadData();});
    const fields={family:'sales-family',promo:'sales-promo',hidden:'sales-hidden',metric:'sales-metric',dimension:'sales-dimension',step:'sales-step',style:'sales-style',transform:'sales-transform',top:'sales-top'};
    for(const [k,id] of Object.entries(fields))el(id).addEventListener('change',()=>{filters[k]=k==='top'?Number(el(id).value):el(id).value;page=0;save();render();});
    
    el('sales-toggle-adv').addEventListener('click',()=>{
      const d = el('sales-advanced-drawer');
      d.hidden = !d.hidden;
      el('sales-toggle-adv').classList.toggle('active', !d.hidden);
    });

    el('sales-prod-search').addEventListener('input', e => updateDropdown(e.target.value));
    el('sales-prod-search').addEventListener('focus', e => updateDropdown(e.target.value));

    document.addEventListener('click', event => {
      const pick = event.target.closest('[data-pick-product]');
      if (pick) {
        const code = pick.dataset.pickProduct;
        if (!filters.products.includes(code)) filters.products.push(code);
        else filters.products = filters.products.filter(c => c !== code);
        el('sales-prod-search').value = '';
        el('sales-prod-dropdown').hidden = true;
        renderChips(); page = 0; save(); render();
        return;
      }
      const del = event.target.closest('[data-del-product]');
      if (del) {
        filters.products = filters.products.filter(c => c !== del.dataset.delProduct);
        renderChips(); page = 0; save(); render();
        return;
      }
      if (!event.target.closest('.sales-product-search-wrap')) {
        const dd = el('sales-prod-dropdown');
        if (dd) dd.hidden = true;
      }
    });

    el('sales-clear-products').addEventListener('click',()=>{filters.products=[];renderChips();page=0;save();render();});
    document.querySelectorAll('[data-sales-weekday]').forEach(c=>c.addEventListener('change',()=>{filters.weekdays=[...document.querySelectorAll('[data-sales-weekday]:checked')].map(c=>Number(c.dataset.salesWeekday));page=0;save();render();}));
    el('sales-year').addEventListener('change',()=>{const y=el('sales-year').value;if(y){el('sales-start').value=y+'-01-01';el('sales-end').value=y+'-12-31';filters.step='mois';el('sales-step').value='mois';loadData();}});
    document.querySelectorAll('[data-sales-days]').forEach(b=>b.addEventListener('click',()=>{
      if(!data)return;
      const end=data.couverture.derniere_vente||data.periode.fin;
      el('sales-end').value=end;
      el('sales-start').value=b.dataset.salesDays==='all'?(data.couverture.premiere_vente||data.periode.debut):SalesMath.addDays(end,1-Number(b.dataset.salesDays));
      if(b.dataset.salesDays==='all'){filters.step='annee';el('sales-step').value='annee';}
      document.querySelectorAll('[data-sales-days]').forEach(p => p.classList.toggle('active', p === b));
      loadData();
    }));
    el('sales-reset').addEventListener('click',()=>{try{localStorage.removeItem(storage);}catch{}initialized=false;data=null;initialize();loadData();});
    el('sales-results').addEventListener('change',event=>{if(event.target.dataset.salesColumn){filters.columns=[...el('sales-results').querySelectorAll('[data-sales-column]:checked')].map(c=>c.dataset.salesColumn);save();render();}});
    el('sales-results').addEventListener('click',event=>{
      const b=event.target.closest('button');if(!b)return;
      if(b.dataset.salesSort){filters.descending=filters.sort===b.dataset.salesSort?!filters.descending:true;filters.sort=b.dataset.salesSort;save();render();}
      if(b.dataset.salesPage){page+=Number(b.dataset.salesPage);render();}
      if(b.dataset.salesExport)exportData(b.dataset.salesExport);
    });

    // Écouteur global pour l'infobulle interactive sur graphiques
    document.addEventListener('mousemove', ev => {
      const tipTarget = ev.target.closest('[data-chart-tip]');
      if (tipTarget) {
        const raw = tipTarget.dataset.chartTip;
        let html;
        if (raw.includes('###')) {
          const [d, name, val, col] = raw.split('###');
          html = `<div class="tooltip-date">${d}</div><div class="tooltip-row"><span style="color:${col}">● ${name} :</span><b>${val}</b></div>`;
        } else {
          html = raw;
        }
        showTip(ev, html);
      } else {
        hideTip();
      }
    });

    renderChips();
    initialized=true;
  }

  async function loadData(){
    const start=el('sales-start').value,end=el('sales-end').value;
    if((start&&!end)||(!start&&end)||start>end){status('Vérifiez les deux dates : le début doit précéder la fin.',true);return;}
    const id=++request;status('Lecture des ventes et de leur contexte…');
    el('sales-apply').disabled=true;el('sales-results').hidden=true;
    try{
      const query=new URLSearchParams({comparaison:el('sales-comparison').value});
      if(start&&end){query.set('debut',start);query.set('fin',end);}
      const response=await fetch('/api/analyse-ventes?'+query,{cache:'no-store'});
      const body=await response.json();
      if(id!==request)return;
      if(!response.ok||!body.ok)throw new Error(body.erreur||'Analyse indisponible.');
      data=body;
      el('sales-start').value=body.periode.debut;
      el('sales-end').value=body.periode.fin;
      el('sales-family').innerHTML=options([['','Toutes les familles'],...[...new Set(data.articles.map(a=>a.famille))].sort().map(v=>[v,v])],filters.family);
      filters.family=el('sales-family').value;
      const first=Number(data.couverture.premiere_vente?.slice(0,4)),last=Number(data.couverture.derniere_vente?.slice(0,4));
      const years=[];
      if(first&&last)for(let y=last;y>=first;y--)years.push([y,String(y)]);
      el('sales-year').innerHTML=options([['','Choisir une année'],...years],'');
      renderChips();
      page=0;save();render();
    }catch(error){
      if(id===request){status('Impossible de charger cette période : '+error.message,true);el('sales-results').innerHTML='';}
    }finally{
      if(id===request){el('sales-apply').disabled=false;el('sales-results').hidden=false;}
    }
  }

  function lineChart(labels,series){
    if(!labels.length||!series.some(s=>s.values.some(Number.isFinite)))return '<div class="empty">Aucune valeur documentée pour ces filtres.</div>';
    const width=920,height=280,left=65,right=18,top=24,bottom=42,pw=width-left-right,ph=height-top-bottom;
    const values=series.flatMap(s=>s.values).filter(Number.isFinite);
    const lowVal=Math.min(0,...values),highVal=Math.max(1,...values);
    const ticks = SalesMath.niceTicks(lowVal, highVal, 5);
    const low = ticks[0], high = ticks[ticks.length - 1], scale = (high - low) || 1;
    const y=v=>top+ph-(v-low)/scale*ph,x=i=>left+(i+.5)*pw/labels.length;

    let svg='';
    // Lignes de grille horizontales et graduations arrondies lisibles
    ticks.forEach(v=>{
      const yy=y(v);
      svg+=`<line x1="${left}" x2="${width-right}" y1="${yy}" y2="${yy}" stroke="var(--line)"/><text x="${left-9}" y="${yy+4}" text-anchor="end" fill="var(--muted)" font-size="10">${n(v,v%1===0?0:1)}</text>`;
    });

    const labelStep=Math.max(1,Math.ceil(labels.length/10));
    labels.forEach((label,i)=>{
      if(i%labelStep===0||i===labels.length-1)svg+=`<text x="${x(i)}" y="${height-14}" fill="var(--muted)" text-anchor="middle" font-size="10">${e(label)}</text>`;
    });

    // Courbes / Barres
    series.forEach((s,index)=>{
      const color=palette[index%palette.length],barWidth=Math.max(.5,pw/labels.length*.78/series.length);
      let path='';
      s.values.forEach((v,i)=>{
        if(!Number.isFinite(v)){path+='|';return;}
        const xx=x(i),yy=y(v);
        const tipTitle=`${s.dates?.[i]||labels[i]}###${s.name}###${n(v,2)} ${metrics[filters.metric][1]}###${color}`;
        if(filters.style==='barres') {
          svg+=`<rect class="sales-chart-bar" data-chart-tip="${e(tipTitle)}" x="${xx-pw/labels.length*.39+index*barWidth}" y="${Math.min(yy,y(0))}" width="${barWidth}" height="${Math.max(1,Math.abs(y(0)-yy))}" fill="${color}" opacity="${s.previous?.5:.85}"><title>${e(s.name)} · ${e(s.dates?.[i]||labels[i])} : ${n(v,2)} ${e(metrics[filters.metric][1])}</title></rect>`;
        } else {
          path+=(path===''||path.endsWith('|')?'M':'L')+xx+','+yy+' ';
          svg+=`<circle class="sales-chart-point" data-chart-tip="${e(tipTitle)}" cx="${xx}" cy="${yy}" r="${labels.length>90?2:3.5}" fill="${color}"><title>${e(s.name)} · ${e(s.dates?.[i]||labels[i])} : ${n(v,2)} ${e(metrics[filters.metric][1])}</title></circle>`;
        }
      });
      if(filters.style!=='barres') {
        svg+=`<path d="${path.replace(/\|/g,' ')}" fill="none" stroke="${color}" stroke-width="2.2" ${s.previous?'stroke-dasharray="5 4"':''}/>`;
      }
    });

    // Colonnes transparentes de survol sur tout le graphique
    labels.forEach((label, i) => {
      const xx = left + i * pw / labels.length;
      const colW = pw / labels.length;
      const dayValues = series.map((s, idx) => {
        const val = s.values[i];
        if (!Number.isFinite(val)) return null;
        return `<div class="tooltip-row"><span style="color:${palette[idx % palette.length]}">● ${e(s.name)} :</span><b>${n(val, 2)} ${e(metrics[filters.metric][1])}</b></div>`;
      }).filter(Boolean);
      if (dayValues.length) {
        const fullTip = `<div class="tooltip-date">${e(labels[i])}</div>${dayValues.join('')}`;
        svg += `<rect class="hover-col" data-chart-tip="${e(fullTip)}" x="${xx}" y="${top}" width="${colW}" height="${ph}" fill="transparent" style="cursor:crosshair;"></rect>`;
      }
    });

    return `<svg viewBox="0 0 ${width} ${height}" class="interactive-chart" role="img" aria-label="${e(metrics[filters.metric][0])} par ${e(filters.step)}.">${svg}</svg><div class="sales-chart-legend">${series.map((s,i)=>`<span><i style="background:${palette[i%palette.length]}"></i>${e(s.name)}</span>`).join('')}</div>`;
  }

  function bars(rows,key,click=false){
    const sorted=rows.filter(r=>Number.isFinite(r[key])).sort((a,b)=>b[key]-a[key]);
    if(!sorted.length)return '<div class="empty">Aucune valeur documentée.</div>';
    const max=Math.max(1,...sorted.map(r=>Math.abs(r[key])));
    return `<div class="sales-bars">${sorted.map(r=>{
      const title = r.libelle || r.name;
      const tipData = `${e(title)}###${e(metrics[filters.metric][0])}###${n(r[key],2)} ${e(metrics[filters.metric][1])}###var(--sales)`;
      return `<div class="sales-bar-item" data-chart-tip="${tipData}"><div class="sales-bar-label">${click?`<button data-product="${e(r.itm8)}" title="Ouvrir la fiche ${e(r.libelle)}">${e(r.libelle)}</button>`:`<span>${e(r.name)}</span>`}<b>${n(r[key])} <small class="muted">${e(metrics[filters.metric][1])}</small></b></div><div class="sales-bar-track"><i style="width:${Math.max(0,Math.abs(r[key])/max*100)}%;${r[key]<0?'background:var(--danger-text)':''}"></i></div></div>`;
    }).join('')}</div>`;
  }

  function render(){
    if(!data)return;
    model=SalesMath.model(data,filters);
    const nativeOption=el('sales-metric').querySelector('[value="ventes"]');
    nativeOption.disabled=model.articles.length!==1;
    if(filters.metric==='ventes'&&model.articles.length!==1){
      filters.metric='ca_reconstitue_eur';el('sales-metric').value=filters.metric;
      model=SalesMath.model(data,filters);
    }
    const s=model.summary,old=model.oldSummary,metric=metrics[filters.metric];
    const compare=data.comparaison.debut?`Comparaison : ${data.comparaison.debut} au ${data.comparaison.fin}.`:'Aucune comparaison.';
    status(`${data.periode.debut} au ${data.periode.fin} · ${model.articles.length} produits retenus · ${s.jours}/${model.expectedDays} jours avec ventes observées. ${compare}`);
    
    const kpis=[
      ['Ventes observées',s.ventes_colis,'colis éq.','Colisage actuel'],
      ['CA reconstitué',s.ca_reconstitue_eur,'€',`${n(s.ca_couverture_pct)} % des faits avec prix`],
      ['Évolution · '+metric[0],SalesMath.change(s[filters.metric],old[filters.metric]),'%',data.comparaison.debut?'Totaux connus des deux périodes':'Comparaison désactivée'],
      ['Articles avec ventes',model.ranking.filter(r=>r.jours>0).length,'articles',`${s.jours} jours avec ventes observées`]
    ];

    const sort=filters.sort,sign=filters.descending?-1:1;
    const sorted=[...model.ranking].sort((a,b)=>{
      const av=a[sort],bv=b[sort];
      if(!Number.isFinite(av))return Number.isFinite(bv)?1:a.libelle.localeCompare(b.libelle,'fr');
      if(!Number.isFinite(bv))return -1;
      return sign*(av-bv)||a.libelle.localeCompare(b.libelle,'fr');
    });
    page=Math.max(0,Math.min(page,Math.ceil(sorted.length/50)-1));
    const shown=sorted.slice(page*50,page*50+50);
    const unknown=SalesMath.sum(model.current.map(r=>r.faits_unite_inconnue))||0,incompatible=SalesMath.sum(model.current.map(r=>r.faits_unite_incompatible))||0;
    const missingVolumes=model.current.filter(r=>Number.isFinite(r.ventes)&&!Number.isFinite(r.ventes_colis)).length;
    const actualYears=model.years.sort((a,b)=>a.name.localeCompare(b.name));

    el('sales-results').innerHTML=`
      ${unknown||incompatible||missingVolumes?`<div class="chart-explanation"><strong>Unités à vérifier : ${n(unknown,0)} faits sans unité connue, ${n(incompatible,0)} avec unité différente du référentiel.</strong><p>${missingVolumes} lignes article/jour de vente ne peuvent pas être converties en colis. Le CA daté reste consultable.</p></div>`:''}
      <div class="kpi-grid">
        ${kpis.map(([l,v,u,note])=>`<article class="kpi"><div class="kpi-label">${e(l)}</div><div class="kpi-value">${n(v)}<span class="kpi-unit">${u}</span></div><div class="kpi-note">${e(note)}</div></article>`).join('')}
      </div>
      <div class="sales-grid">
        <section class="card sales-full">
          <div class="card-heading">
            <div><p class="eyebrow">ÉVOLUTION DANS LE TEMPS</p><h2>${e(metric[0])} · ${e(metric[1])}</h2></div>
            <span class="tag">Par ${e(filters.step)}</span>
          </div>
          <div class="sales-chart">${lineChart(model.temporal.map(b=>b.label),model.series)}</div>
        </section>
        <section class="card">
          <div class="card-heading"><h2>Produits · ${e(metric[1])}</h2><span class="tag">Top ${filters.top}</span></div>
          ${bars([...model.ranking].sort((a,b)=>(b.valeur??-Infinity)-(a.valeur??-Infinity)).slice(0,filters.top),'valeur',true)}
        </section>
        <section class="card">
          <div class="card-heading"><h2>Familles · ${e(metric[1])}</h2></div>
          ${bars(model.families,filters.metric)}
        </section>
        <section class="card">
          <div class="card-heading"><h2>Profil des jours de la semaine</h2></div>
          <div class="sales-chart">${lineChart(model.week.map(r=>r.name),[{name:'Moyenne / jour documenté · '+metric[1],values:model.week.map(r=>r.value)}])}</div>
        </section>
        <section class="card">
          <div class="card-heading"><h2>Années · ${e(metric[1])}</h2></div>
          ${bars(actualYears,filters.metric)}
        </section>
      </div>

      <section class="card sales-data-table">
        <div class="card-heading">
          <div><p class="eyebrow">TOUS LES CHIFFRES PAR PRODUIT</p><h2>Détail des ventes et des écarts</h2></div>
          <details class="sales-column-options"><summary>Colonnes affichées</summary><div class="sales-checks">${Object.entries(columns).map(([k,v])=>`<label><input type="checkbox" data-sales-column="${k}" ${filters.columns.includes(k)?'checked':''}>${e(v)}</label>`).join('')}</div></details>
        </div>
        <div class="table-wrap">
          <table>
            <thead><tr><th>Produit / famille</th>${filters.columns.map(k=>`<th><button data-sales-sort="${k}">${e(columns[k])}${sort===k?(filters.descending?' ↓':' ↑'):''}</button></th>`).join('')}</tr></thead>
            <tbody>${shown.map(a=>`<tr><td><button class="table-product" data-product="${e(a.itm8)}"><span class="product-name">${e(a.libelle)}</span><small class="product-code">${e(a.itm8)} · ${e(a.famille)}</small></button></td>${filters.columns.map(k=>`<td>${n(a[k],k==='jours'?0:2)}${k==='ventes'?' '+e(a.unite):''}</td>`).join('')}</tr>`).join('')||'<tr><td>Aucun article ne correspond à ces filtres.</td></tr>'}</tbody>
          </table>
        </div>
        <div class="sales-pager">
          <button class="secondary" data-sales-page="-1" ${page===0?'disabled':''}>Précédent</button>
          <span>${sorted.length?page*50+1:0}–${Math.min(sorted.length,(page+1)*50)} / ${sorted.length}</span>
          <button class="secondary" data-sales-page="1" ${(page+1)*50>=sorted.length?'disabled':''}>Suivant</button>
        </div>
        <div class="sales-toolbar">
          <p class="small muted">Les exports conservent les filtres, les dates et les données manquantes.</p>
          <div>
            <button class="secondary" data-sales-export="resume">Exporter le tableau CSV</button>
            <button class="secondary" data-sales-export="jours">Exporter article / jour CSV</button>
            <button class="secondary" data-sales-export="json">Exporter données et paramètres JSON</button>
          </div>
        </div>
      </section>

      <details class="details-note chart-details-collapsible">
        <summary>ℹ️ Précisions méthodologiques, sources et limites</summary>
        <p class="sales-insight">${s.jours?`${n(s.ventes_colis)} colis équivalents vendus sur ${s.jours} jours avec ventes enregistrées, pour ${model.ranking.filter(a=>a.jours).length} articles. `:'Aucune vente documentée pour ces filtres. '}${Number.isFinite(s.ca_reconstitue_eur)?`CA reconstitué : ${n(s.ca_reconstitue_eur,2)} €, avec un prix disponible pour ${s.ca_faits_documentes} faits sur ${s.ca_faits_ventes}. `:'Les prix historiques disponibles ne permettent pas de reconstituer le CA de cette sélection. '}Une case vide signifie « non documenté ».</p>
        <p>Historique des ventes disponible : ${e(data.couverture.premiere_vente||'inconnu')} au ${e(data.couverture.derniere_vente||'inconnu')}.</p>
        ${(data.limites||[]).map(v=>`<p>${e(v)}</p>`).join('')}
      </details>
    `;
  }

  function exportData(kind){
    if(!model)return;const metadata={periode:data.periode,comparaison:data.comparaison,filtres:filters,couverture:data.couverture,limites:data.limites};let content,type,extension;
    if(kind==='json'){content=JSON.stringify({...metadata,articles:model.articles,observations:[...new Map([...model.current,...model.previous].map(r=>[r.itm8+'|'+r.date,r])).values()]},null,2);type='application/json';extension='json';}
    else{let headers,rows;const context=[data.periode.debut,data.periode.fin,data.comparaison.debut||'',data.comparaison.fin||'',filters.metric,JSON.stringify(filters)];const prefix=['periode_debut','periode_fin','comparaison_debut','comparaison_fin','indicateur','filtres_json'];
      if(kind==='resume'){headers=[...prefix,'itm8','libelle','famille','unite','colisage',...Object.keys(columns)];rows=model.ranking.map(a=>[...context,a.itm8,a.libelle,a.famille,a.unite,a.colisage,...Object.keys(columns).map(k=>a[k])]);}
      else{const keys=['date','itm8','ventes','livraisons','pertes','ventes_colis','livraisons_colis','pertes_colis','ca_reconstitue_eur','ca_faits_ventes','ca_faits_documentes','promo_documentee'];headers=[...prefix,'periode','libelle','unite',...keys];const lookup=new Map(model.articles.map(a=>[a.itm8,a]));rows=[...model.current.map(r=>[r,'selection']),...model.previous.map(r=>[r,'comparaison'])].map(([r,p])=>[...context,p,lookup.get(r.itm8).libelle,lookup.get(r.itm8).unite,...keys.map(k=>r[k])]);}
      const cell=v=>{let s=v==null?'':typeof v==='number'?String(v).replace('.',','):String(v);if(typeof v==='string'&&/^[\s]*[=+@-]/.test(s))s="'"+s;return '"'+s.replace(/"/g,'""')+'"';};content='\ufeff'+[headers,...rows].map(r=>r.map(cell).join(';')).join('\r\n');type='text/csv;charset=utf-8';extension='csv';}
    const blob=new Blob([content],{type}),url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=`ventes-${kind}-${data.periode.debut}-${data.periode.fin}.${extension}`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  return {open:async(force=false)=>{if(!initialized)initialize();if(!data||force)await loadData();}};
})();
