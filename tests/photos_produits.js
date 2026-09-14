const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const fichier = path.join(__dirname, '../app/js/photos-produits.js');
assert.ok(fs.existsSync(fichier), 'Le helper de photos doit exister');
const empreinte = 'a'.repeat(64);
const photo = {libelle: 'Pomme <fraîche> "', src: `app/img/produits/${empreinte}-240.webp`,
  miniature: `app/img/produits/${empreinte}-96.webp`, largeur: 240, hauteur: 160};
const contexte = {window: {}, document: {addEventListener() {}},
  fetch: async () => ({ok: true, json: async () => ({version: 1, articles: {
    '0000087004135': photo, 'nom:INJECTION': {...photo, src: 'https://example.org/track.webp'},
  }})})};
vm.runInNewContext(fs.readFileSync(fichier, 'utf8'), contexte);
(async () => {
  const api = contexte.window.PhotosProduits;
  await api.charger();
  const html = api.image('0000087004135', 'liste');
  assert.ok(html.includes('loading="lazy"'));
  assert.ok(html.includes('photo-produit-liste'));
  assert.ok(html.includes('-96.webp'));
  assert.ok(html.includes('srcset='));
  assert.ok(!html.includes('<fraîche>'));
  assert.ok(html.includes('&lt;fraîche&gt;'));
  assert.equal(api.image('inconnu', 'liste'), '');
  assert.equal(api.image('nom:INJECTION', 'detail'), '');
  assert.ok(!api.image('0000087004135', '" onload="evil').includes('evil'));
  assert.ok(api.image('0000087004135', 'comptage').includes('loading="eager"'));
  console.log('Photos JS : HTML sûr, variantes, absence et injection vérifiés');
})().catch(e => { console.error(e); process.exitCode = 1; });
