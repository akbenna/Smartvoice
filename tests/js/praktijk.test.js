/**
 * node --test tests/js/praktijk.test.js
 *
 * Het praktijknummer uit de Bricks-URL. Twee dingen moeten hier hard kloppen:
 * het nummer van de praktijk wordt gevonden, en een dossier- of consultnummer
 * dieper in het pad gaat nooit mee (dat hoort bij een patiënt).
 */
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');

const P = require(path.join(__dirname, '..', '..', 'chrome-extension', 'lib', 'praktijk.js'));

test('praktijknummer uit het eerste deel van het pad', () => {
  assert.deepEqual(P.nummersUit('https://groep06.brickshuisarts.nl/2876/login'), ['2876']);
  assert.deepEqual(P.nummersUit('https://groep06.brickshuisarts.nl/2876/s/consult/123456/journaal'), ['2876']);
});

test('lokale installatie zet het nummer in de hostnaam', () => {
  assert.deepEqual(P.nummersUit('https://2876.brickslokaal.nl/s/consult/99999'), ['2876']);
});

test('dossier- en consultnummers gaan nooit mee', () => {
  assert.deepEqual(P.nummersUit('https://groep06.brickshuisarts.nl/s/consult/123456'), []);
  assert.deepEqual(P.nummersUit('https://groep06.brickshuisarts.nl/login?patient=123456'), []);
});

test('alleen Bricks-adressen', () => {
  assert.deepEqual(P.nummersUit('https://example.com/2876/'), []);
  assert.deepEqual(P.nummersUit('https://evil-bricks.nl.example.com/2876/'), []);
  assert.deepEqual(P.nummersUit('geen url'), []);
});

test('zonder opgeslagen nummer geen kop', async () => {
  const kop = await P.metKop({ 'X-API-Key': 'k' });
  assert.equal(kop['X-Bricks-Praktijk'], undefined);
});
