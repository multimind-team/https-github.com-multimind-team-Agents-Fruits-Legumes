'use strict';
// Données synthétiques uniquement ; aucun accès au serveur ni aux carnets.
const assert=require('node:assert/strict');
const math=require('../app/js/cockpit-ventes.js');
const data={periode:{debut:'2026-01-01',fin:'2026-01-04'},comparaison:{debut:'2025-12-28',fin:'2025-12-31'},articles:[{itm8:'a',libelle:'Banane',famille:'Fruits',unite:'kg'},{itm8:'b',libelle:'Tomate',famille:'Légumes',unite:'kg'}],jours:[
  {date:'2026-01-01',itm8:'a',ventes:0,ventes_colis:0,ca_reconstitue_eur:0,ca_faits_ventes:1,ca_faits_documentes:1,promo_documentee:true},
  {date:'2026-01-03',itm8:'a',ventes:20,ventes_colis:2,ca_reconstitue_eur:40,ca_faits_ventes:1,ca_faits_documentes:1,promo_documentee:false},
  {date:'2026-01-03',itm8:'b',ventes:30,ventes_colis:3,ca_reconstitue_eur:null,ca_faits_ventes:1,ca_faits_documentes:0,promo_documentee:true},
  {date:'2025-12-28',itm8:'a',ventes:10,ventes_colis:1,ca_reconstitue_eur:20,ca_faits_ventes:1,ca_faits_documentes:1,promo_documentee:true},
]};
const filter={family:'',products:[],search:'',hidden:'tous',promo:'toutes',weekdays:[0,1,2,3,4,5,6],metric:'ventes_colis',step:'jour',dimension:'total',top:5,transform:'brut'};
assert.equal(math.sum([null,undefined]),null);
assert.equal(math.sum([null,0]),0);
assert.equal(math.change(10,0),null);
assert.equal(math.key('2026-01-01','semaine'),'2025-12-29');
assert.equal(math.key('2026-01-01','annee'),'2026');
let m=math.model(data,filter);
assert.equal(m.summary.ventes_colis,5);
assert.equal(m.summary.jours,2);
assert.equal(m.summary.ca_couverture_pct,200/3);
assert.deepEqual(m.series[0].values,[0,null,5,null]);
assert.equal(m.ranking.find(a=>a.itm8==='b').precedent,null);
assert.equal(m.ranking.find(a=>a.itm8==='a').evolution,100);
assert.equal(m.ranking.find(a=>a.itm8==='a').jours_precedents,1);
m=math.model(data,{...filter,promo:'declaree'});
assert.equal(m.summary.ventes_colis,3); // Promo filtrée par jour, pas par produit.
assert.equal(m.previous.length,1);
m=math.model(data,{...filter,products:['a'],transform:'cumul'});
assert.deepEqual(m.series[0].values,[0,null,2,null]);
m=math.model(data,{...filter,family:'Fruits',step:'annee'});
assert.equal(m.articles.length,1);
assert.equal(m.temporal[0].value,2);
m=math.model(data,{...filter,weekdays:[]});
assert.equal(m.summary.ventes_colis,null);
assert.equal(m.expectedDays,0);
m=math.model(data,{...filter,dimension:'produit',top:1});
assert.equal(m.series.length,1);
assert.equal(m.summary.ventes_colis,5); // Top N ne tronque pas les totaux.
const overlapping={...data,comparaison:{debut:'2026-01-01',fin:'2026-01-03'}};
m=math.model(overlapping,filter);
assert.equal(m.previous.length,3);
assert.equal(m.current.length,3); // Pas de double comptage dans chaque période.
console.log('Analyse ventes : filtres, trous, zéros, comparaisons, unités séparées par article et agrégations vérifiés.');
