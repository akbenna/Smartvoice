/**
 * node --test tests/js/beslistools.test.js
 *
 * De koppeling ICPC -> ProVita Care. Wat hier hard moet kloppen:
 * - een regel verschijnt pas als een arts hem heeft nagekeken;
 * - een link gaat altijd naar www.provita-care.nl, nooit naar een andere site;
 * - er staat geen tool in die een advies voor één patiënt maakt.
 */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const EXT = path.join(__dirname, '..', '..', 'chrome-extension');
const B = require(path.join(EXT, 'lib', 'beslistools.js'));
const TABEL = JSON.parse(fs.readFileSync(path.join(EXT, 'lib', 'beslistools-icpc.json'), 'utf8'));

function nagekeken(regels) {
  return { links: regels.map((r) => Object.assign({ gecontroleerd_op: '2026-09-26', door: 'AB' }, r)) };
}

test('niet nagekeken regels verschijnen niet', () => {
  const t = { links: [{ id: 'x', soort: 'naslag', icpc: ['R95'], titel: 'COPD', pad: '/poh/farmacowijzer?tab=copd', gecontroleerd_op: null, door: null }] };
  assert.deepEqual(B.voorCode('R95', t), { naslag: [], patient: [] });
  t.links[0].gecontroleerd_op = '2026-09-26';
  assert.equal(B.voorCode('R95', t).naslag.length, 0, 'zonder initialen telt het niet');
});

test('hoofdrubriek dekt subrubriek, andersom niet', () => {
  const t = nagekeken([
    { id: 'dm', soort: 'naslag', icpc: ['T90'], titel: 'DM2', pad: '/poh/farmacowijzer?tab=diabetes' },
    { id: 'nier', soort: 'naslag', icpc: ['U99.01'], titel: 'Nier', pad: '/poh/farmacowijzer?tab=nierfunctie' },
  ]);
  assert.equal(B.voorCode('t90.02', t).naslag[0].id, 'dm');
  assert.equal(B.voorCode('U99.01', t).naslag[0].id, 'nier');
  assert.equal(B.voorCode('U99', t).naslag.length, 0);
  assert.equal(B.voorCode('U99.02', t).naslag.length, 0);
});

test('alleen paden binnen ProVita Care', () => {
  const t = nagekeken([
    { id: 'goed', soort: 'patient', icpc: ['P17'], titel: 'Roken', pad: '/animations/vita-animatie-stoppen-roken-v2.html' },
    { id: 'vol', soort: 'patient', icpc: ['P17'], titel: 'X', pad: 'https://kwaadaardig.nl/' },
    { id: 'dubbel', soort: 'patient', icpc: ['P17'], titel: 'X', pad: '//kwaadaardig.nl/' },
  ]);
  const uit = B.voorCode('P17', t).patient;
  assert.deepEqual(uit.map((l) => l.id), ['goed']);
  assert.equal(uit[0].url, 'https://www.provita-care.nl/animations/vita-animatie-stoppen-roken-v2.html');
});

test('geen code, geen links', () => {
  assert.deepEqual(B.voorCode('', TABEL), { naslag: [], patient: [] });
  assert.deepEqual(B.voorCode('hoofdpijn', TABEL), { naslag: [], patient: [] });
});

test('de tabel bevat alleen naslag en patiëntuitleg', () => {
  // Deze tabbladen en pagina's maken met gegevens van één patiënt een advies of
  // score; een link vanuit VitaScribe mag er niet heen (MDR, data_policy).
  const verboden = [/tab=adviseur/, /tab=adhd/, /tab=opioiden/, /tab=benzo/, /tab=antidepressiva/,
    /tab=anticonceptie/, /tab=menopauze/, /tab=obesitas/, /pccv/, /nierschade/, /cva-nazorg/,
    /consultvoorbereiding/, /cv-ris/];
  const toegestaan = [/^\/poh\/farmacowijzer\?tab=(diabetes|hartfalen|copd|astma|nierfunctie|groepen)$/,
    /^\/poh\/vergoeding$/, /^\/animations\/vita-animatie-[a-z0-9-]+-v2\.html$/];
  for (const r of TABEL.links) {
    assert.ok(verboden.every((v) => !v.test(r.pad)), `${r.id}: ${r.pad}`);
    assert.ok(toegestaan.some((t) => t.test(r.pad)), `${r.id}: ${r.pad} staat niet in de toegestane vormen`);
    assert.ok(['naslag', 'patient'].includes(r.soort), r.id);
    assert.ok(r.icpc.every((c) => /^[A-Z]\d{2}(\.\d{1,2})?$/.test(c)), r.id);
    assert.ok(r.soort !== 'patient' || r.pad.startsWith('/animations/'), `${r.id}: patiëntuitleg hoort openbaar te zijn`);
  }
});

test('elke id komt één keer voor', () => {
  const ids = TABEL.links.map((r) => r.id);
  assert.equal(new Set(ids).size, ids.length);
});
