/**
 * node --test tests/js/thuisarts.test.js
 *
 * De eerste JavaScript-proef van de extensie. Die had nog geen testopzet; dit
 * is het kleinste begin dat ergens over gaat, en het gaat over de plek waar
 * een fout de patiënt raakt: welke pagina er bij een code hoort.
 *
 * De proef staat hier en niet in chrome-extension/, omdat pack_extension.sh die
 * map in zijn geheel tot CRX maakt: testcode hoort niet mee te reizen naar de
 * browser van elke werkplek.
 */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const EXT = path.join(__dirname, '..', '..', 'chrome-extension');
const T = require(path.join(EXT, 'lib', 'thuisarts.js'));

const TABEL = {
  paginas: [
    { icpc: 'R78', titel: 'Acute bronchitis', url: 'https://www.thuisarts.nl/acute-bronchitis',
      gecontroleerd_op: '2026-10-01', door: 'AB' },
    { icpc: 'R78', titel: 'Hoesten', url: 'https://www.thuisarts.nl/hoesten',
      gecontroleerd_op: '2026-10-01', door: 'AB' },
    { icpc: 'N95', titel: 'Spanningshoofdpijn', url: null, gecontroleerd_op: null, door: null },
    { icpc: 'K86', titel: 'Hoge bloeddruk', url: 'https://www.thuisarts.nl/hoge-bloeddruk',
      gecontroleerd_op: null, door: null },
    { icpc: 'U71', titel: 'Blaasontsteking', url: 'http://www.thuisarts.nl/blaasontsteking',
      gecontroleerd_op: '2026-10-01', door: 'AB' },
  ],
};

test('een bekende code geeft alle pagina\'s die erbij horen', () => {
  const p = T.pagesForIcpc('R78', TABEL);
  assert.equal(p.length, 2);
  assert.deepEqual(p.map((x) => x.titel), ['Acute bronchitis', 'Hoesten']);
});

test('een subrubriek valt terug op de hoofdrubriek', () => {
  assert.equal(T.pagesForIcpc('R78.01', TABEL).length, 2);
  assert.equal(T.normaliseer(' r78.02 '), 'R78');
});

test('een onbekende of lege code geeft niets, zonder te struikelen', () => {
  for (const code of ['Z99', '', null, undefined, 'onzin', 42, {}]) {
    assert.deepEqual(T.pagesForIcpc(code, TABEL), []);
  }
});

/* Een regel zonder adres of zonder controledatum telt niet mee. Dat is het hele
   punt van de tabel: een link die opent maar over een andere aandoening gaat,
   leest de patiënt met hetzelfde vertrouwen als een goede. */
test('een ongevulde of ongecontroleerde regel doet niet mee', () => {
  assert.deepEqual(T.pagesForIcpc('N95', TABEL), []);
  assert.deepEqual(T.pagesForIcpc('K86', TABEL), []);
});

test('alleen https op thuisarts.nl telt', () => {
  assert.deepEqual(T.pagesForIcpc('U71', TABEL), []);
});

test('een ontbrekende of rare tabel geeft niets terug', () => {
  assert.deepEqual(T.pagesForIcpc('R78', null), []);
  assert.deepEqual(T.pagesForIcpc('R78', {}), []);
  assert.deepEqual(T.pagesForIcpc('R78', { paginas: [null, {}] }), []);
});

/* Corrigeert de arts de code, dan hoort de titel van de oude code niet te
   blijven staan. De titel mag uit een ongecontroleerde regel komen: het is het
   label van de code, geen link. */
test('de titel bij een code komt uit de tabel, ook zonder adres', () => {
  assert.equal(T.titelVoor('N95', TABEL), 'Spanningshoofdpijn');
  assert.equal(T.titelVoor('R78.01', TABEL), 'Acute bronchitis');
  assert.equal(T.titelVoor('Z99', TABEL), '');
  assert.equal(T.titelVoor('', TABEL), '');
});

test('de zoekterm wordt veilig in het zoekadres gezet', () => {
  assert.equal(T.zoekUrl('acute bronchitis'), 'https://www.thuisarts.nl/zoeken?query=acute%20bronchitis');
  assert.ok(T.zoekUrl('<script>').indexOf('<') === -1);
});

/* Thuisarts is Nederlandstalig. Staat er een vertaling, dan moet de regel in
   die taal zeggen dat de website Nederlands is; anders wekt de uitleg de
   indruk dat er ook informatie in het Turks te vinden is. */
test('de verwijzing zegt in de taal van de patiënt dat de site Nederlands is', () => {
  assert.equal(T.verwijzing('https://www.thuisarts.nl/x', 'nl'), 'Meer lezen: https://www.thuisarts.nl/x');
  for (const taal of ['tr', 'ar', 'en', 'pl', 'uk', 'fr', 'de', 'es']) {
    const regel = T.verwijzing('https://www.thuisarts.nl/x', taal);
    assert.ok(regel.endsWith('https://www.thuisarts.nl/x'), taal);
    assert.notEqual(regel, T.verwijzing('https://www.thuisarts.nl/x', 'nl'), taal + ' krijgt geen Nederlandse regel');
  }
  // Een taal die de tabel niet kent valt terug op het Nederlands in plaats van
  // op "undefined" in de tekst van de patiënt.
  assert.equal(T.verwijzing('https://www.thuisarts.nl/x', 'zz'), T.verwijzing('https://www.thuisarts.nl/x', 'nl'));
});

/* Elke taal die het zijpaneel aanbiedt moet ook een regel hebben. Komt er een
   taal bij, dan valt die anders stil terug op het Nederlands. */
test('elke taal uit het zijpaneel heeft een eigen regel', () => {
  const html = fs.readFileSync(path.join(EXT, 'sidepanel', 'sidepanel.html'), 'utf8');
  const blok = html.slice(html.indexOf('id="pi-taal"'), html.indexOf('</select>', html.indexOf('id="pi-taal"')));
  const talen = [...blok.matchAll(/value="([a-z]{2})"/g)].map((m) => m[1]);
  assert.ok(talen.length >= 8, 'talen gevonden in het zijpaneel');
  for (const taal of talen) assert.ok(T.TALEN[taal], 'geen regel voor ' + taal);
});

/* De meegeleverde tabel moet leesbaar zijn en de vorm hebben die de module
   verwacht, ook nu er nog geen adressen in staan. */
test('de meegeleverde tabel heeft de juiste vorm', () => {
  const tabel = JSON.parse(fs.readFileSync(path.join(EXT, 'lib', 'thuisarts-icpc.json'), 'utf8'));
  assert.ok(Array.isArray(tabel.paginas) && tabel.paginas.length > 0);
  for (const rij of tabel.paginas) {
    assert.match(rij.icpc, /^[A-Z]\d{2}$/);
    assert.equal(typeof rij.titel, 'string');
    assert.ok('url' in rij && 'gecontroleerd_op' in rij && 'door' in rij);
  }
});

/* De QR-code wordt in de browser gemaakt; een QR-dienst op internet zou zien
   welke aandoening er op papier gaat. Deze proef bewijst dat de meegeleverde
   bibliotheek dat zonder netwerk kan. */
test('de meegeleverde QR-bibliotheek maakt lokaal een code', () => {
  const qrcode = require(path.join(EXT, 'lib', 'qrcode', 'qrcode.js'));
  const qr = qrcode(0, 'M');
  qr.addData('https://www.thuisarts.nl/acute-bronchitis');
  qr.make();
  assert.ok(qr.getModuleCount() > 20);
  assert.ok(qr.createSvgTag({ scalable: true }).indexOf('<svg') === 0);
});
