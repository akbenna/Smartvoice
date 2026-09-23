/**
 * SmartVoice - Dictation side panel
 *
 * Streams microphone audio to the Cloud API (which relays to Deepgram) and
 * shows the transcript while the doctor speaks. Text goes into the Bricks
 * field the doctor last clicked, live or on demand. Optional AI steps:
 * light cleanup, or conversion to a SOEP line.
 */

var CHUNK_MS = 250;
var STOP_TIMEOUT_MS = 6000;

var els = {
  conn: document.getElementById('conn'),
  target: document.getElementById('target'),
  targetName: document.getElementById('target-name'),
  mic: document.getElementById('btn-mic'),
  timer: document.getElementById('timer'),
  live: document.getElementById('live-insert'),
  text: document.getElementById('text'),
  interim: document.getElementById('interim'),
  insert: document.getElementById('btn-insert'),
  copy: document.getElementById('btn-copy'),
  clean: document.getElementById('btn-clean'),
  soepBtn: document.getElementById('btn-soep'),
  clear: document.getElementById('btn-clear'),
  soep: document.getElementById('soep'),
  soepRows: document.getElementById('soep-rows'),
  icpc: document.getElementById('icpc'),
  soepInsert: document.getElementById('btn-soep-insert'),
  soepCopy: document.getElementById('btn-soep-copy'),
  status: document.getElementById('status'),
};

var session = null;       // { ws, stream, recorder, stopTimer }
var state = 'idle';       // idle | connecting | recording | stopping
var timerInterval = null;
var startedAt = 0;
var insertQueue = Promise.resolve();
var lastSoep = null;
var rules = SVTextRules.emptyRules();   // snelteksten + correcties
var learnMode = null;                   // { kind: 'fix'|'snippet', selection }

// ── Helpers ──

function setStatus(message, isError, action) {
  els.status.textContent = message || '';
  els.status.classList.toggle('error', !!isError);
  if (action) {
    var btn = document.createElement('button');
    btn.className = 'btn small';
    btn.style.marginLeft = '6px';
    btn.textContent = action.label;
    btn.addEventListener('click', action.onClick);
    els.status.appendChild(btn);
  }
}

function setState(next) {
  state = next;
  els.mic.classList.toggle('recording', next === 'recording');
  els.mic.classList.toggle('connecting', next === 'connecting' || next === 'stopping');
  els.conn.className = 'conn' + (next === 'recording' ? ' live' : '');
  els.conn.textContent = {
    idle: 'klaar',
    connecting: 'verbinden…',
    recording: '● luistert',
    stopping: 'afronden…',
  }[next];
  var busy = next !== 'idle';
  els.clean.disabled = busy;
  els.soepBtn.disabled = busy;
}

function startTimer() {
  startedAt = Date.now();
  els.timer.textContent = '00:00';
  timerInterval = setInterval(function () {
    var s = Math.floor((Date.now() - startedAt) / 1000);
    els.timer.textContent = String(Math.floor(s / 60)).padStart(2, '0') + ':' + String(s % 60).padStart(2, '0');
  }, 500);
}

function stopTimer() {
  clearInterval(timerInterval);
  timerInterval = null;
}

async function getConfig() {
  var c = await chrome.storage.sync.get(['apiUrl', 'apiKey', 'micDevice', 'llmProvider']);
  return {
    apiUrl: (c.apiUrl || 'http://localhost:8002').replace(/\/$/, ''),
    apiKey: (c.apiKey || '').trim(),
    micDevice: c.micDevice || '',
    llmProvider: c.llmProvider || '',
  };
}

function joinText(existing, addition) {
  if (!existing) return addition.replace(/^\s+/, '');
  if (/\s$/.test(existing) || /^[\s.,;:!?)]/.test(addition)) return existing + addition;
  return existing + ' ' + addition;
}

// ── Target field (clicked in Bricks) ──

function renderTarget(target) {
  if (target && target.label) {
    els.targetName.textContent = target.label;
    els.targetName.classList.remove('muted');
    els.target.classList.add('set');
  } else {
    els.targetName.textContent = 'Klik in Bricks in een veld';
    els.targetName.classList.add('muted');
    els.target.classList.remove('set');
  }
}

chrome.storage.session.get('svTarget').then(function (r) { renderTarget(r.svTarget); });
chrome.storage.onChanged.addListener(function (changes, area) {
  if (area === 'session' && changes.svTarget) renderTarget(changes.svTarget.newValue);
});

async function sendToTarget(text) {
  var r = await chrome.storage.session.get('svTarget');
  var target = r.svTarget;
  if (!target) throw new Error('Nog geen doelveld: klik eerst in Bricks in het veld waar de tekst moet komen.');
  var res;
  try {
    res = await chrome.tabs.sendMessage(target.tabId, { action: 'SV_INSERT_TEXT', text: text }, { frameId: target.frameId });
  } catch (e) {
    throw new Error('Het Bricks-tabblad reageert niet. Ververs de pagina en klik opnieuw in het veld.');
  }
  if (!res || !res.ok) throw new Error((res && res.error) || 'Invoegen mislukt.');
}

function queueLiveInsert(text) {
  insertQueue = insertQueue.then(function () {
    return sendToTarget(text);
  }).catch(function (err) {
    // Text is never lost: it is also in the panel.
    setStatus(err.message + '\nDe tekst staat wel in het paneel.', true);
  });
}

async function insertOrCopy(text) {
  if (!text.trim()) return;
  try {
    await sendToTarget(text);
    setStatus('Ingevoegd.');
  } catch (err) {
    await navigator.clipboard.writeText(text).catch(function () {});
    setStatus(err.message + '\nTekst is gekopieerd; plak met Ctrl+V.', true);
  }
}

// ── Dictation session ──

function wsUrl(apiUrl) {
  return apiUrl.replace(/^http/, 'ws') + '/api/v1/dictation/stream';
}

async function openMicrophone(micDevice) {
  var audio = { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true };
  if (micDevice) audio.deviceId = { exact: micDevice };
  try {
    return await navigator.mediaDevices.getUserMedia({ audio: audio });
  } catch (err) {
    if (err.name === 'NotAllowedError') {
      // A side panel cannot show the permission prompt itself; ask once in a tab.
      chrome.tabs.create({ url: chrome.runtime.getURL('sidepanel/mic-permission.html') });
      throw new Error('Geef in het geopende tabblad eenmalig toestemming voor de microfoon en probeer opnieuw.');
    }
    if (err.name === 'OverconstrainedError' || err.name === 'NotFoundError') {
      throw new Error('Gekozen microfoon niet gevonden. Kies een andere in Instellingen.');
    }
    throw err;
  }
}

function handleServerEvent(event) {
  if (event.type === 'ready') {
    startRecorder();
  } else if (event.type === 'transcript') {
    if (event.is_final) {
      var finalText = SVTextRules.applyRules(event.text, rules);
      els.interim.textContent = '';
      els.text.value = joinText(els.text.value, finalText);
      els.text.scrollTop = els.text.scrollHeight;
      if (els.live.checked) queueLiveInsert(finalText);
    } else {
      els.interim.textContent = event.text;
    }
  } else if (event.type === 'error') {
    setStatus(event.message, true);
  } else if (event.type === 'closed') {
    teardown();
  }
}

function startRecorder() {
  var mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus' : 'audio/webm';
  var recorder = new MediaRecorder(session.stream, { mimeType: mimeType, audioBitsPerSecond: 32000 });
  recorder.ondataavailable = function (e) {
    if (e.data && e.data.size > 0 && session && session.ws.readyState === WebSocket.OPEN) {
      session.ws.send(e.data);
    }
  };
  recorder.onstop = function () {
    // Last chunk has been sent by now; ask the server to flush and close.
    if (session && session.ws.readyState === WebSocket.OPEN) {
      session.ws.send(JSON.stringify({ type: 'stop' }));
    }
  };
  session.recorder = recorder;
  recorder.start(CHUNK_MS);
  setState('recording');
  startTimer();
  setStatus('');
}

async function startDictation() {
  if (state !== 'idle') return;
  setState('connecting');
  setStatus('');
  var config = await getConfig();

  var stream;
  try {
    stream = await openMicrophone(config.micDevice);
  } catch (err) {
    setState('idle');
    setStatus(err.message, true);
    return;
  }

  var ws = new WebSocket(wsUrl(config.apiUrl));
  session = { ws: ws, stream: stream, recorder: null, stopTimer: null };

  ws.onopen = function () {
    ws.send(JSON.stringify({ type: 'auth', api_key: config.apiKey, keyterms: SVTextRules.keyterms(rules) }));
  };
  ws.onmessage = function (msg) {
    try { handleServerEvent(JSON.parse(msg.data)); } catch (e) { /* ignore malformed */ }
  };
  ws.onerror = function () {
    setStatus('Kan de server niet bereiken op ' + config.apiUrl + '. Controleer Instellingen.', true);
  };
  ws.onclose = function () { teardown(); };
}

function stopDictation() {
  if (!session || state !== 'recording') return;
  setState('stopping');
  stopTimer();
  if (session.recorder && session.recorder.state !== 'inactive') session.recorder.stop();
  session.stream.getTracks().forEach(function (t) { t.stop(); });
  // Do not wait forever for the last words.
  session.stopTimer = setTimeout(teardown, STOP_TIMEOUT_MS);
}

function teardown() {
  if (!session) return;
  var s = session;
  session = null;
  clearTimeout(s.stopTimer);
  stopTimer();
  if (s.recorder && s.recorder.state !== 'inactive') {
    s.recorder.onstop = null;
    s.recorder.stop();
  }
  s.stream.getTracks().forEach(function (t) { t.stop(); });
  if (s.ws.readyState === WebSocket.OPEN || s.ws.readyState === WebSocket.CONNECTING) s.ws.close();
  // Leftover interim text is kept so nothing that was said disappears.
  var leftover = SVTextRules.applyRules(els.interim.textContent, rules);
  if (leftover) {
    els.text.value = joinText(els.text.value, leftover);
    els.interim.textContent = '';
    if (els.live.checked) queueLiveInsert(leftover);
  }
  setState('idle');
}

function toggleDictation() {
  if (state === 'idle') startDictation();
  else if (state === 'recording') stopDictation();
}

// ── AI processing ──

async function processText(mode) {
  var text = els.text.value.trim();
  if (!text) { setStatus('Nog geen tekst om te verwerken.', true); return; }
  var config = await getConfig();
  var button = mode === 'clean' ? els.clean : els.soepBtn;
  var label = button.textContent;
  button.disabled = true;
  button.textContent = 'Bezig…';
  setStatus('');

  try {
    var headers = { 'Content-Type': 'application/json' };
    if (config.apiKey) headers['X-API-Key'] = config.apiKey;
    var body = { text: text, mode: mode };
    if (config.llmProvider) body.llm_provider = config.llmProvider;
    var resp = await fetch(config.apiUrl + '/api/v1/dictation/process', {
      method: 'POST', headers: headers, body: JSON.stringify(body),
    });
    if (!resp.ok) {
      var detail = await resp.json().then(function (j) { return j.detail; }).catch(function () { return ''; });
      throw new Error('Server gaf fout ' + resp.status + (detail ? ': ' + detail : ''));
    }
    var data = await resp.json();
    if (mode === 'clean') {
      var original = els.text.value;
      els.text.value = data.text;
      setStatus('Opgeschoond.', false, {
        label: 'Herstel origineel',
        onClick: function () { els.text.value = original; setStatus('Origineel hersteld.'); },
      });
    } else {
      renderSoep(data.soep);
      setStatus('SOEP klaar. Klik in Bricks in een veld en gebruik "invoegen".');
    }
  } catch (err) {
    setStatus(err.message === 'Failed to fetch' ? 'Kan de server niet bereiken.' : err.message, true);
  } finally {
    button.textContent = label;
    button.disabled = state !== 'idle';
  }
}

var SOEP_KEYS = [['s', 'S'], ['o', 'O'], ['e', 'E'], ['p', 'P']];

function renderSoep(soep) {
  lastSoep = soep;
  els.soepRows.textContent = '';
  SOEP_KEYS.forEach(function (pair) {
    var row = document.createElement('div');
    row.className = 'soep-row';

    var letter = document.createElement('span');
    letter.className = 'soep-letter';
    letter.textContent = pair[1];

    var text = document.createElement('div');
    text.className = 'soep-text';
    text.contentEditable = 'true';
    text.dataset.key = pair[0];
    text.textContent = soep[pair[0]] || '';

    var btn = document.createElement('button');
    btn.className = 'btn small';
    btn.textContent = 'invoegen';
    btn.addEventListener('click', function () { insertOrCopy(text.innerText.trim()); });

    row.appendChild(letter);
    row.appendChild(text);
    row.appendChild(btn);
    els.soepRows.appendChild(row);
  });
  els.icpc.textContent = soep.icpc_code ? soep.icpc_code + (soep.icpc_titel ? ' · ' + soep.icpc_titel : '') : '';
  els.soep.classList.remove('hidden');
}

function soepAsText() {
  var lines = [];
  els.soepRows.querySelectorAll('.soep-text').forEach(function (node) {
    var value = node.innerText.trim();
    var key = node.dataset.key;
    if (key === 'e' && lastSoep && lastSoep.icpc_code && value.indexOf(lastSoep.icpc_code) === -1) {
      value = (value ? value + ' ' : '') + '(' + lastSoep.icpc_code + ')';
    }
    if (value) lines.push(key.toUpperCase() + ': ' + value);
  });
  return lines.join('\n');
}

// ── Learning: corrections and snippets from selected text ──

function selectedText() {
  return els.text.value.slice(els.text.selectionStart, els.text.selectionEnd).trim();
}

function openLearnForm(kind) {
  var selection = selectedText();
  if (!selection) {
    setStatus('Selecteer eerst tekst in het tekstvak.', true);
    return;
  }
  learnMode = { kind: kind, selection: selection };
  document.getElementById('learn-label').textContent = kind === 'fix'
    ? 'Verkeerd verstaan: \u201c' + selection + '\u201d\nMoet zijn:'
    : 'Tekst: \u201c' + selection + '\u201d\nAls ik zeg (meerdere mag, met komma):';
  var input = document.getElementById('learn-input');
  input.value = '';
  input.placeholder = kind === 'fix' ? 'juiste schrijfwijze' : 'bijv. normaal longen';
  document.getElementById('learn-form').classList.remove('hidden');
  input.focus();
}

function closeLearnForm() {
  learnMode = null;
  document.getElementById('learn-form').classList.add('hidden');
}

async function saveLearnForm() {
  if (!learnMode) return;
  var value = document.getElementById('learn-input').value.trim();
  if (!value) return;
  var latest = await SVTextRules.load();
  if (learnMode.kind === 'fix') {
    var correction = { wrong: learnMode.selection, right: value };
    latest.corrections = latest.corrections.filter(function (c) {
      return c.wrong.toLowerCase() !== correction.wrong.toLowerCase();
    });
    latest.corrections.push(correction);
    els.text.value = SVTextRules.applyCorrections(els.text.value, [correction]);
    setStatus('Onthouden: \u201c' + correction.wrong + '\u201d wordt voortaan \u201c' + correction.right + '\u201d.');
  } else {
    latest.snippets.push({ triggers: value, text: learnMode.selection });
    setStatus('Sneltekst opgeslagen. Zeg \u201c' + SVTextRules.splitTriggers(value)[0] + '\u201d om hem in te voegen.');
  }
  await SVTextRules.save(latest);
  closeLearnForm();
}

SVTextRules.load().then(function (r) { rules = r; });
chrome.storage.onChanged.addListener(function (changes, area) {
  if (area === 'local' && changes[SVTextRules.STORAGE_KEY]) {
    rules = SVTextRules.normalize(changes[SVTextRules.STORAGE_KEY].newValue);
  }
});

// ── Wiring ──

els.mic.addEventListener('click', toggleDictation);
els.insert.addEventListener('click', function () {
  var start = els.text.selectionStart, end = els.text.selectionEnd;
  var text = start !== end ? els.text.value.slice(start, end) : els.text.value;
  insertOrCopy(text.trim());
});
els.copy.addEventListener('click', function () {
  navigator.clipboard.writeText(els.text.value).then(function () { setStatus('Gekopieerd.'); });
});
els.clean.addEventListener('click', function () { processText('clean'); });
els.soepBtn.addEventListener('click', function () { processText('soep'); });
els.clear.addEventListener('click', function () {
  els.text.value = '';
  els.interim.textContent = '';
  els.soep.classList.add('hidden');
  lastSoep = null;
  setStatus('');
});
els.soepInsert.addEventListener('click', function () { insertOrCopy(soepAsText()); });
els.soepCopy.addEventListener('click', function () {
  navigator.clipboard.writeText(soepAsText()).then(function () { setStatus('SOEP gekopieerd.'); });
});
document.getElementById('btn-fix').addEventListener('click', function () { openLearnForm('fix'); });
document.getElementById('btn-snippet').addEventListener('click', function () { openLearnForm('snippet'); });
document.getElementById('learn-save').addEventListener('click', saveLearnForm);
document.getElementById('learn-cancel').addEventListener('click', closeLearnForm);
document.getElementById('learn-input').addEventListener('keydown', function (e) {
  if (e.key === 'Enter') saveLearnForm();
  if (e.key === 'Escape') closeLearnForm();
});
document.getElementById('open-rules').addEventListener('click', function (e) {
  e.preventDefault();
  chrome.tabs.create({ url: chrome.runtime.getURL('rules/rules.html') });
});
document.getElementById('open-settings').addEventListener('click', function (e) {
  e.preventDefault();
  chrome.runtime.openOptionsPage();
});

chrome.storage.local.get('svLiveInsert').then(function (r) { els.live.checked = !!r.svLiveInsert; });
els.live.addEventListener('change', function () {
  chrome.storage.local.set({ svLiveInsert: els.live.checked });
});

// Keyboard shortcut (Alt+Shift+D) arrives via the service worker. The port
// drops when Chrome stops the idle worker, so reconnect to stay reachable.
function connectPort() {
  var port;
  try { port = chrome.runtime.connect({ name: 'sv-sidepanel' }); } catch (e) { return; }
  port.onMessage.addListener(function (msg) {
    if (msg.action === 'SV_TOGGLE_DICTATION') toggleDictation();
  });
  port.onDisconnect.addListener(function () { setTimeout(connectPort, 250); });
}
connectPort();

// Opened by the shortcut while closed: start right away.
chrome.storage.session.get('svAutoStart').then(function (r) {
  if (r.svAutoStart) {
    chrome.storage.session.remove('svAutoStart');
    startDictation();
  }
});

setState('idle');
