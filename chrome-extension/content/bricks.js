/**
 * SmartVoice - Bricks HIS Content Script
 *
 * Full recording + SOEP workflow as a floating widget on the Bricks page.
 * No separate tabs, no popups — everything happens here.
 */

/* ── Selectors for Bricks field injection ── */

var DEFAULT_SELECTORS = {
  journaal: [
    'textarea[name*="journaal"]', 'textarea[name*="journal"]',
    'textarea[name*="notitie"]', '[contenteditable="true"][data-field*="journaal"]',
    '.journal-editor textarea', '.consult-notes textarea',
  ],
  soep_s: ['textarea[name*="subjectief"]', 'textarea[data-soep="S"]', '.soep-field-s textarea'],
  soep_o: ['textarea[name*="objectief"]', 'textarea[data-soep="O"]', '.soep-field-o textarea'],
  soep_e: ['textarea[name*="evaluatie"]', 'textarea[data-soep="E"]', '.soep-field-e textarea'],
  soep_p: ['textarea[name*="plan"]', 'textarea[data-soep="P"]', '.soep-field-p textarea'],
  icpc: ['input[name*="icpc"]', 'input[name*="ICPC"]', '.icpc-input input'],
};

var userSelectors = {};
var lastResult = null;

/* ── Recording state ── */

var mediaRecorder = null;
var audioChunks = [];
var audioStream = null;
var timerInterval = null;
var recStartTime = null;

/* ── Selector helpers ── */

async function loadSelectors() {
  try {
    var stored = await chrome.storage.sync.get(['bricksSelectors']);
    if (stored.bricksSelectors) userSelectors = JSON.parse(stored.bricksSelectors);
  } catch (e) { /* defaults */ }
}

function findElement(key) {
  var lists = [
    userSelectors[key] ? (Array.isArray(userSelectors[key]) ? userSelectors[key] : [userSelectors[key]]) : [],
    DEFAULT_SELECTORS[key] || [],
  ];
  for (var i = 0; i < lists.length; i++) {
    for (var j = 0; j < lists[i].length; j++) {
      var el = document.querySelector(lists[i][j]);
      if (el) return el;
    }
  }
  return null;
}

function setFieldValue(el, value) {
  if (!el || !value) return false;
  if (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT') {
    el.value = value;
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
  } else if (el.contentEditable === 'true') {
    el.textContent = value;
    el.dispatchEvent(new Event('input', { bubbles: true }));
  }
  return true;
}

/* ── SOEP injection ── */

function injectSOEP(data) {
  var soep = data.soep || {};
  var injected = false;

  var fields = { soep_s: soep.s, soep_o: soep.o, soep_e: soep.e, soep_p: soep.p };
  for (var key in fields) {
    var el = findElement(key);
    if (el && fields[key]) { setFieldValue(el, fields[key]); injected = true; }
  }

  var icpcEl = findElement('icpc');
  if (icpcEl && soep.icpc_code) setFieldValue(icpcEl, soep.icpc_code);

  if (!injected) {
    var journalEl = findElement('journaal');
    if (journalEl) { setFieldValue(journalEl, formatSOEPText(data)); injected = true; }
  }

  if (!injected && document.activeElement) {
    var active = document.activeElement;
    if (active.tagName === 'TEXTAREA' || active.contentEditable === 'true') {
      setFieldValue(active, formatSOEPText(data));
      injected = true;
    }
  }

  return injected;
}

function formatSOEPText(data) {
  var soep = data.soep || {};
  var parts = [];
  if (data.decisief) parts.push('[Decisief] ' + data.decisief);
  parts.push('');
  if (soep.s) parts.push('S: ' + soep.s);
  if (soep.o) parts.push('O: ' + soep.o);
  if (soep.e) parts.push('E: ' + soep.e);
  if (soep.p) parts.push('P: ' + soep.p);
  if (soep.icpc_code) parts.push('\nICPC: ' + soep.icpc_code + (soep.icpc_titel ? ' - ' + soep.icpc_titel : ''));
  return parts.join('\n');
}

/* ── Toast notification ── */

function showNotification(text) {
  var n = document.createElement('div');
  n.className = 'sv-notification';
  n.textContent = text;
  document.body.appendChild(n);
  setTimeout(function() { n.classList.add('sv-notification-fade'); setTimeout(function() { n.remove(); }, 300); }, 2500);
}

/* ── Timer ── */

function updateTimer() {
  var el = document.getElementById('sv-timer');
  if (!el || !recStartTime) return;
  var s = Math.floor((Date.now() - recStartTime) / 1000);
  el.textContent = String(Math.floor(s / 60)).padStart(2, '0') + ':' + String(s % 60).padStart(2, '0');
}

/* ── Recording ── */

async function startRecording() {
  try {
    audioStream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true }
    });
  } catch (err) {
    showNotification('Microfoon niet beschikbaar: ' + err.message);
    return;
  }

  audioChunks = [];
  var mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
    ? 'audio/webm;codecs=opus' : 'audio/webm';

  mediaRecorder = new MediaRecorder(audioStream, { mimeType: mimeType, audioBitsPerSecond: 128000 });

  mediaRecorder.ondataavailable = function(e) {
    if (e.data && e.data.size > 0) audioChunks.push(e.data);
  };

  mediaRecorder.onstop = function() {
    var mime = mediaRecorder ? mediaRecorder.mimeType : 'audio/webm';
    var blob = new Blob(audioChunks, { type: mime });

    if (audioStream) { audioStream.getTracks().forEach(function(t) { t.stop(); }); audioStream = null; }

    if (blob.size < 1000) {
      setWidgetState('idle');
      showNotification('Opname te kort. Probeer langer op te nemen.');
      return;
    }

    setWidgetState('processing');
    sendAudioToAPI(blob, mime);
  };

  mediaRecorder.start();
  recStartTime = Date.now();
  timerInterval = setInterval(updateTimer, 500);
  setWidgetState('recording');
}

function stopRecording() {
  if (timerInterval) { clearInterval(timerInterval); timerInterval = null; }
  if (mediaRecorder && mediaRecorder.state !== 'inactive') {
    mediaRecorder.stop();
  }
}

/* ── API call ── */

async function sendAudioToAPI(blob, mimeType) {
  try {
    var config = await chrome.storage.sync.get(['apiUrl', 'apiKey', 'sttProvider', 'llmProvider']);
    var apiUrl = (config.apiUrl || 'http://localhost:8002').replace(/\/$/, '');

    var formData = new FormData();
    var ext = mimeType.includes('webm') ? 'webm' : 'wav';
    formData.append('audio', blob, 'consult.' + ext);
    if (config.sttProvider) formData.append('stt_provider', config.sttProvider);
    if (config.llmProvider) formData.append('llm_provider', config.llmProvider);

    var headers = {};
    if (config.apiKey) headers['X-API-Key'] = config.apiKey;

    updateProcessingStep('Audio wordt getranscribeerd...');

    var response = await fetch(apiUrl + '/api/v1/consult/process', {
      method: 'POST',
      headers: headers,
      body: formData,
    });

    if (!response.ok) {
      var errText = await response.text();
      throw new Error('API fout (' + response.status + '): ' + errText.substring(0, 200));
    }

    var result = await response.json();
    lastResult = result;

    // Persist for popup fallback
    chrome.storage.local.set({ sv_state: 'results', sv_data: result });

    setWidgetState('results');
    displayResults(result);

  } catch (err) {
    setWidgetState('error');
    document.getElementById('sv-error-msg').textContent = err.message;
  }
}

/* ── Widget UI ── */

function createWidget() {
  var widget = document.createElement('div');
  widget.id = 'smartvoice-widget';

  widget.innerHTML =
    // Toggle button
    '<div class="sv-fab" id="sv-fab">' +
      '<svg width="22" height="22" viewBox="0 0 24 24" fill="white">' +
        '<path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3z"/>' +
        '<path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z"/>' +
      '</svg>' +
    '</div>' +

    // Panel
    '<div class="sv-panel hidden" id="sv-panel">' +
      // Header
      '<div class="sv-header">' +
        '<span class="sv-logo">SV</span>' +
        '<span class="sv-title">SmartVoice</span>' +
        '<button id="sv-close" class="sv-close-btn">&times;</button>' +
      '</div>' +

      // State: Idle
      '<div class="sv-body" id="sv-state-idle">' +
        '<p class="sv-hint">Klik om het consult op te nemen</p>' +
        '<button id="sv-btn-record" class="sv-btn sv-btn-record">' +
          '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3z"/><path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z"/></svg>' +
          ' Start opname' +
        '</button>' +
      '</div>' +

      // State: Recording
      '<div class="sv-body hidden" id="sv-state-recording">' +
        '<div class="sv-rec-indicator">' +
          '<span class="sv-pulse"></span>' +
          '<span class="sv-rec-label">Opname actief</span>' +
        '</div>' +
        '<div id="sv-timer" class="sv-timer">00:00</div>' +
        '<button id="sv-btn-stop" class="sv-btn sv-btn-stop">' +
          '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="6" width="12" height="12" rx="1"/></svg>' +
          ' Stop &amp; verwerk' +
        '</button>' +
      '</div>' +

      // State: Processing
      '<div class="sv-body hidden" id="sv-state-processing">' +
        '<div class="sv-spinner"></div>' +
        '<p id="sv-processing-step" class="sv-processing-text">Audio wordt verwerkt...</p>' +
      '</div>' +

      // State: Results
      '<div class="sv-body hidden" id="sv-state-results">' +
        '<div class="sv-result-section">' +
          '<div class="sv-label">DECISIEF</div>' +
          '<p id="sv-decisief" class="sv-decisief-text"></p>' +
        '</div>' +
        '<div class="sv-soep-grid">' +
          '<div class="sv-soep-item"><span class="sv-soep-letter">S</span><p id="sv-soep-s"></p></div>' +
          '<div class="sv-soep-item"><span class="sv-soep-letter">O</span><p id="sv-soep-o"></p></div>' +
          '<div class="sv-soep-item"><span class="sv-soep-letter">E</span><p id="sv-soep-e"></p></div>' +
          '<div class="sv-soep-item"><span class="sv-soep-letter">P</span><p id="sv-soep-p"></p></div>' +
        '</div>' +
        '<div id="sv-icpc" class="sv-icpc hidden">' +
          '<span id="sv-icpc-code"></span> <span id="sv-icpc-title"></span>' +
        '</div>' +
        '<div class="sv-actions">' +
          '<button id="sv-btn-inject" class="sv-btn sv-btn-primary">Invoegen in Bricks</button>' +
          '<button id="sv-btn-copy" class="sv-btn sv-btn-secondary">Kopieer</button>' +
        '</div>' +
        '<button id="sv-btn-new" class="sv-btn sv-btn-link">Nieuw consult</button>' +
      '</div>' +

      // State: Error
      '<div class="sv-body hidden" id="sv-state-error">' +
        '<p id="sv-error-msg" class="sv-error-text"></p>' +
        '<button id="sv-btn-retry" class="sv-btn sv-btn-secondary">Opnieuw</button>' +
      '</div>' +

    '</div>';

  document.body.appendChild(widget);

  // ── Event listeners ──

  document.getElementById('sv-fab').addEventListener('click', function() {
    document.getElementById('sv-panel').classList.toggle('hidden');
  });

  document.getElementById('sv-close').addEventListener('click', function() {
    document.getElementById('sv-panel').classList.add('hidden');
  });

  document.getElementById('sv-btn-record').addEventListener('click', function() {
    startRecording();
  });

  document.getElementById('sv-btn-stop').addEventListener('click', function() {
    stopRecording();
  });

  document.getElementById('sv-btn-inject').addEventListener('click', function() {
    if (lastResult) {
      var ok = injectSOEP(lastResult);
      showNotification(ok ? 'SOEP ingevoegd in Bricks!' : 'Kon geen velden vinden. Tekst gekopieerd.');
      if (!ok) navigator.clipboard.writeText(formatSOEPText(lastResult));
    }
  });

  document.getElementById('sv-btn-copy').addEventListener('click', function() {
    if (lastResult) {
      navigator.clipboard.writeText(formatSOEPText(lastResult));
      showNotification('Gekopieerd!');
    }
  });

  document.getElementById('sv-btn-new').addEventListener('click', function() {
    lastResult = null;
    chrome.storage.local.remove(['sv_state', 'sv_data', 'sv_error']);
    setWidgetState('idle');
  });

  document.getElementById('sv-btn-retry').addEventListener('click', function() {
    setWidgetState('idle');
  });
}

function setWidgetState(state) {
  var states = ['idle', 'recording', 'processing', 'results', 'error'];
  states.forEach(function(s) {
    var el = document.getElementById('sv-state-' + s);
    if (el) el.classList.toggle('hidden', s !== state);
  });

  // Pulse the FAB red during recording
  var fab = document.getElementById('sv-fab');
  if (fab) fab.classList.toggle('sv-fab-recording', state === 'recording');
}

function updateProcessingStep(text) {
  var el = document.getElementById('sv-processing-step');
  if (el) el.textContent = text;
}

function displayResults(data) {
  var soep = data.soep || {};
  document.getElementById('sv-decisief').textContent = data.decisief || '-';
  document.getElementById('sv-soep-s').textContent = soep.s || '-';
  document.getElementById('sv-soep-o').textContent = soep.o || '-';
  document.getElementById('sv-soep-e').textContent = soep.e || '-';
  document.getElementById('sv-soep-p').textContent = soep.p || '-';

  var icpcEl = document.getElementById('sv-icpc');
  if (soep.icpc_code) {
    icpcEl.classList.remove('hidden');
    document.getElementById('sv-icpc-code').textContent = soep.icpc_code;
    document.getElementById('sv-icpc-title').textContent = soep.icpc_titel || '';
  } else {
    icpcEl.classList.add('hidden');
  }
}

/* ── Message handler (for popup-initiated pushes) ── */

chrome.runtime.onMessage.addListener(function(msg, _sender, sendResponse) {
  if (msg.action === 'INJECT_SOEP') {
    lastResult = msg.data;
    var ok = injectSOEP(msg.data);
    displayResults(msg.data);
    setWidgetState('results');
    document.getElementById('sv-panel').classList.remove('hidden');
    sendResponse({ success: ok });
    showNotification(ok ? 'SOEP ingevoegd in Bricks!' : 'Velden niet gevonden. Gebruik kopieer.');
    return false;
  }
});

/* ── Check for pending results on load ── */

async function checkPendingResults() {
  try {
    var stored = await chrome.storage.local.get(['sv_state', 'sv_data']);
    if (stored.sv_state === 'results' && stored.sv_data) {
      lastResult = stored.sv_data;
      displayResults(stored.sv_data);
      setWidgetState('results');
    }
  } catch (e) { /* ignore */ }
}

/* ── Init ── */

async function init() {
  await loadSelectors();
  createWidget();
  await checkPendingResults();
}

init();
