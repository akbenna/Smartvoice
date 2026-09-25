/**
 * SmartVoice - Patiëntinstructie (B1 + vertaling) uit de SOEP-regel.
 * Uses from sidepanel.js: getConfig(), setStatus(), lastSoep, els.soepRows
 */
(function () {
  'use strict';
  var $ = function (id) { return document.getElementById(id); };

  function currentEP() {
    // The doctor may have edited the SOEP rows; read what is on screen.
    var get = function (k) {
      var el = document.querySelector('.soep-text[data-key="' + k + '"]');
      return el ? el.innerText.trim() : ((typeof lastSoep !== 'undefined' && lastSoep && lastSoep[k]) || '');
    };
    return { e: get('e'), p: get('p') };
  }

  $('btn-patient').addEventListener('click', function () { $('pi').classList.toggle('hidden'); });

  $('pi-go').addEventListener('click', async function () {
    var ep = currentEP();
    if (ep.p.length < 3) { setStatus('Er staat nog geen plan (P) om uit te leggen.', true); return; }
    var btn = this; btn.disabled = true; btn.textContent = 'Bezig…';
    try {
      var config = await getConfig();
      var headers = { 'Content-Type': 'application/json' };
      if (config.apiKey) headers['X-API-Key'] = config.apiKey;
      var resp = await fetch(config.apiUrl + '/api/v1/patient-instructions', {
        method: 'POST', headers: headers, body: JSON.stringify({ e: ep.e, p: ep.p, taal: $('pi-taal').value }),
      });
      if (!resp.ok) {
        var d = await resp.json().then(function (j) { return j.detail; }).catch(function () { return ''; });
        throw new Error('Server gaf fout ' + resp.status + (d ? ': ' + d : ''));
      }
      var data = await resp.json();
      $('pi-nl').value = data.nl;
      $('pi-nl').classList.remove('hidden');
      $('pi-tr').value = data.vertaling || '';
      $('pi-tr').classList.toggle('hidden', !data.vertaling);
      document.querySelector('.pi-actions').classList.remove('hidden');
      setStatus('Patiëntinstructie klaar. Lees hem na voordat je hem meegeeft.');
    } catch (e) {
      setStatus(e.message === 'Failed to fetch' ? 'Kan de server niet bereiken.' : e.message, true);
    } finally { btn.disabled = false; btn.textContent = 'Maak'; }
  });

  function fullText() {
    var t = $('pi-nl').value.trim();
    if ($('pi-tr').value.trim()) t += '\n\n────────\n\n' + $('pi-tr').value.trim();
    return t;
  }
  $('pi-copy').addEventListener('click', async function () {
    await navigator.clipboard.writeText(fullText());
    setStatus('Gekopieerd.');
  });
  $('pi-print').addEventListener('click', function () {
    var esc = function (s) { return s.replace(/[&<>]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]; }); };
    var html = '<!doctype html><html lang="nl"><head><meta charset="utf-8"><title>Uitleg voor u</title>' +
      '<style>body{font:15px/1.6 system-ui,sans-serif;max-width:640px;margin:32px auto;padding:0 16px;white-space:pre-wrap}' +
      '.tr{margin-top:28px;padding-top:16px;border-top:1px solid #ccc}</style></head><body>' +
      '<div>' + esc($('pi-nl').value) + '</div>' +
      ($('pi-tr').value.trim() ? '<div class="tr" dir="auto">' + esc($('pi-tr').value) + '</div>' : '') +
      '</body></html>';
    var url = URL.createObjectURL(new Blob([html], { type: 'text/html' }));
    var w = window.open(url);
    if (w) w.addEventListener('load', function () { w.print(); });
  });
})();
