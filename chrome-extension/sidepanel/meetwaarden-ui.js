/**
 * VitaScribe - Meetwaarden in het zijpaneel.
 * Uses from sidepanel.js: els.text, insertOrCopy(), setStatus()
 */
(function () {
  'use strict';
  var box = document.getElementById('mw');
  var rows = document.getElementById('mw-rows');
  var lastText = null;
  var current = [];

  function render() {
    var text = (els.text && els.text.value) || '';
    if (text === lastText) return;
    lastText = text;
    current = SVMeetwaarden.extract(text);
    box.classList.toggle('hidden', current.length === 0);
    rows.textContent = '';
    current.forEach(function (w) {
      var row = document.createElement('div');
      row.className = 'mw-row';
      var label = document.createElement('span');
      label.className = 'mw-label';
      label.textContent = w.label + (w.note ? ' (' + w.note + ')' : '');
      var val = document.createElement('span');
      val.className = 'mw-val';
      val.textContent = w.value + ' ' + w.unit;
      var btn = document.createElement('button');
      btn.className = 'btn small';
      btn.textContent = 'invoegen';
      btn.title = 'Zet ' + w.value + ' in het aangeklikte Bricks-veld';
      btn.addEventListener('click', function () { insertOrCopy(w.value); });
      row.append(label, val, btn);
      rows.appendChild(row);
    });
  }

  document.getElementById('mw-copy').addEventListener('click', async function () {
    await navigator.clipboard.writeText(SVMeetwaarden.asText(current));
    setStatus('Meetwaarden gekopieerd.');
  });

  // The transcript is set from code as well as typed, so check periodically.
  els.text.addEventListener('input', render);
  setInterval(render, 700);
  render();
})();
