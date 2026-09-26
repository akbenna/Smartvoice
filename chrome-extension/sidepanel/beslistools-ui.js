/**
 * VitaScribe - Naslag en patiëntuitleg uit ProVita Care bij de SOEP-regel
 *
 * Onder de Thuisarts-link. De opzoekregels staan in lib/beslistools.js; hier
 * staat alleen wat de arts ziet.
 *
 * - Links verschijnen alleen bij de code die de arts op het scherm heeft
 *   staan, en veranderen mee als hij die aanpast.
 * - Staat er niets bij de code, dan toont dit vak niets. Anders dan bij
 *   Thuisarts is er geen zoekveld: een naslagdeel zoek je in ProVita zelf.
 * - Een naslaglink opent ProVita Care (inloggen nodig), een uitleglink een
 *   filmpje dat de arts de patiënt kan laten zien. Er gaat geen patiëntgegeven
 *   mee in de link.
 */
window.SVBeslistoolsUI = (function () {
  'use strict';

  var $ = function (id) { return document.getElementById(id); };
  var tabel = null;

  var geladen = fetch(chrome.runtime.getURL('lib/beslistools-icpc.json'))
    .then(function (r) { return r.json(); })
    .then(function (j) { tabel = j; })
    .catch(function () { tabel = { links: [] }; });

  function chip(link, voorvoegsel, actie) {
    var a = document.createElement('a');
    a.href = link.url;
    a.target = '_blank';
    a.rel = 'noreferrer';
    a.className = 'ta-chip' + (actie === 'patient.animatie' ? ' bt-patient' : '');
    a.textContent = voorvoegsel + link.titel + ' ↗';
    a.title = (link.uitleg ? link.uitleg + '. ' : '') + 'Gecontroleerd op ' + link.gecontroleerd_op;
    a.addEventListener('click', function () { meldGebruik(actie); });
    return a;
  }

  function rij(label, links, voorvoegsel, actie) {
    var groep = document.createElement('div');
    groep.className = 'bt-groep';
    var kop = document.createElement('span');
    kop.className = 'ta-leeg';
    kop.textContent = label;
    groep.appendChild(kop);
    links.forEach(function (l) { groep.appendChild(chip(l, voorvoegsel, actie)); });
    return groep;
  }

  function toon() {
    var vak = $('bt');
    if (!vak) return;
    geladen.then(function () {
      var el = $('icpc-code');
      var gevonden = SVBeslistools.voorCode(el ? el.innerText : '', tabel);
      vak.textContent = '';
      if (!gevonden.naslag.length && !gevonden.patient.length) {
        vak.classList.add('hidden');
        return;
      }
      if (gevonden.naslag.length) {
        vak.appendChild(rij('Naslag in ProVita Care (geen advies voor deze patiënt):', gevonden.naslag, '', 'naslag.provita'));
      }
      if (gevonden.patient.length) {
        vak.appendChild(rij('Uitleg voor de patiënt:', gevonden.patient, '▶ ', 'patient.animatie'));
      }
      vak.classList.remove('hidden');
    });
  }

  /** Eén gebruiksregel met alleen de hoofdrubriek, zoals bij Thuisarts. */
  async function meldGebruik(actie) {
    try {
      var el = $('icpc-code');
      var hoofd = SVBeslistools.normaliseer(el ? el.innerText : '').split('.')[0];
      var config = await getConfig();
      if (!config.apiUrl || !hoofd) return;
      var headers = { 'Content-Type': 'application/json' };
      if (config.apiKey) headers['X-API-Key'] = config.apiKey;
      if (typeof SVPraktijk !== 'undefined') await SVPraktijk.metKop(headers);
      await fetch(config.apiUrl + '/api/v1/usage', {
        method: 'POST', headers: headers,
        body: JSON.stringify({ action: actie, kind: hoofd }),
      });
    } catch (e) { /* een gebruiksregel mag de zorg nooit ophouden */ }
  }

  var codeEl = $('icpc-code');
  if (codeEl) codeEl.addEventListener('input', toon);

  return { toon: toon };
})();
