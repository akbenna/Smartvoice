/**
 * SmartVoice - Manage snelteksten and correcties.
 * Every edit is saved immediately to chrome.storage.local.
 */

var rules = SVTextRules.emptyRules();
var saveTimer = null;

function toast(message) {
  var el = document.getElementById('toast');
  el.textContent = message;
  el.classList.add('show');
  setTimeout(function () { el.classList.remove('show'); }, 1800);
}

function scheduleSave() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(function () {
    SVTextRules.save(rules).then(function () { toast('Opgeslagen'); });
  }, 400);
}

function field(labelText, value, multiline, onInput) {
  var row = document.createElement('div');
  row.className = 'item-row';
  var label = document.createElement('label');
  label.textContent = labelText;
  var input = document.createElement(multiline ? 'textarea' : 'input');
  if (!multiline) input.type = 'text';
  input.value = value || '';
  input.addEventListener('input', function () { onInput(input.value); });
  row.appendChild(label);
  row.appendChild(input);
  return row;
}

function deleteButton(onClick) {
  var btn = document.createElement('button');
  btn.className = 'btn delete';
  btn.textContent = 'Verwijderen';
  btn.addEventListener('click', onClick);
  return btn;
}

function render() {
  var snippetList = document.getElementById('snippets');
  snippetList.textContent = '';
  rules.snippets.forEach(function (snippet, index) {
    var item = document.createElement('div');
    item.className = 'item';
    item.appendChild(field('Commando', snippet.triggers, false, function (v) { snippet.triggers = v; scheduleSave(); }));
    item.appendChild(field('Tekst', snippet.text, true, function (v) { snippet.text = v; scheduleSave(); }));
    item.appendChild(deleteButton(function () { rules.snippets.splice(index, 1); render(); scheduleSave(); }));
    snippetList.appendChild(item);
  });
  document.getElementById('snippets-empty').hidden = rules.snippets.length > 0;

  var correctionList = document.getElementById('corrections');
  correctionList.textContent = '';
  rules.corrections.forEach(function (correction, index) {
    var item = document.createElement('div');
    item.className = 'item';
    var row = document.createElement('div');
    row.className = 'item-row';
    var wrong = field('Verstaan', correction.wrong, false, function (v) { correction.wrong = v; scheduleSave(); });
    var right = field('Wordt', correction.right, false, function (v) { correction.right = v; scheduleSave(); });
    row.appendChild(wrong);
    row.appendChild(right);
    row.appendChild(deleteButton(function () { rules.corrections.splice(index, 1); render(); scheduleSave(); }));
    item.appendChild(row);
    correctionList.appendChild(item);
  });
  document.getElementById('corrections-empty').hidden = rules.corrections.length > 0;
}

function focusLast(listId) {
  var inputs = document.querySelectorAll('#' + listId + ' .item:last-child input');
  if (inputs.length) inputs[0].focus();
}

document.getElementById('add-snippet').addEventListener('click', function () {
  // Kept on screen right away; stored once it has text.
  rules.snippets.push({ triggers: '', text: '' });
  render();
  focusLast('snippets');
});

document.getElementById('add-correction').addEventListener('click', function () {
  rules.corrections.push({ wrong: '', right: '' });
  render();
  focusLast('corrections');
});

document.getElementById('export').addEventListener('click', function () {
  var blob = new Blob([JSON.stringify(SVTextRules.normalize(rules), null, 2)], { type: 'application/json' });
  var a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'smartvoice-snelteksten.json';
  a.click();
  URL.revokeObjectURL(a.href);
});

document.getElementById('import').addEventListener('change', function (e) {
  var file = e.target.files[0];
  if (!file) return;
  file.text().then(function (content) {
    var parsed = JSON.parse(content);
    rules = SVTextRules.normalize(parsed);
    return SVTextRules.save(rules);
  }).then(function () {
    render();
    toast('Geïmporteerd: ' + rules.snippets.length + ' snelteksten, ' + rules.corrections.length + ' correcties');
  }).catch(function () {
    toast('Dit bestand kon niet worden gelezen.');
  });
  e.target.value = '';
});

SVTextRules.load().then(function (r) { rules = r; render(); });
