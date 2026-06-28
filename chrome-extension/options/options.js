/**
 * SmartVoice - Options Page Controller
 * Manages extension settings stored in chrome.storage.sync.
 */

var FIELDS = ['apiUrl', 'apiKey', 'sttProvider', 'llmProvider', 'micDevice'];

var SELECTOR_FIELDS = {
  selJournaal: 'journaal',
  selSoepS: 'soep_s',
  selSoepO: 'soep_o',
  selSoepE: 'soep_e',
  selSoepP: 'soep_p',
};

function showToast(message, duration) {
  var toast = document.getElementById('toast');
  toast.textContent = message;
  toast.classList.add('show');
  setTimeout(function() { toast.classList.remove('show'); }, duration || 2500);
}

// ── Load settings ──

async function loadSettings() {
  var stored = await chrome.storage.sync.get(FIELDS.concat(['bricksSelectors']));

  FIELDS.forEach(function(key) {
    var el = document.getElementById(key);
    if (el && stored[key]) el.value = stored[key];
  });

  if (stored.bricksSelectors) {
    try {
      var selectors = JSON.parse(stored.bricksSelectors);
      Object.keys(SELECTOR_FIELDS).forEach(function(inputId) {
        var selectorKey = SELECTOR_FIELDS[inputId];
        var el = document.getElementById(inputId);
        if (el && selectors[selectorKey]) {
          el.value = Array.isArray(selectors[selectorKey])
            ? selectors[selectorKey].join(', ')
            : selectors[selectorKey];
        }
      });
    } catch (e) {
      // Ignore parse errors
    }
  }
}

// ── Save settings ──

async function saveSettings() {
  var data = {};

  FIELDS.forEach(function(key) {
    var el = document.getElementById(key);
    if (el) data[key] = el.value.trim();
  });

  var selectors = {};
  Object.keys(SELECTOR_FIELDS).forEach(function(inputId) {
    var selectorKey = SELECTOR_FIELDS[inputId];
    var el = document.getElementById(inputId);
    if (el && el.value.trim()) {
      selectors[selectorKey] = el.value.trim();
    }
  });

  if (Object.keys(selectors).length > 0) {
    data.bricksSelectors = JSON.stringify(selectors);
  }

  await chrome.storage.sync.set(data);
  showToast('Instellingen opgeslagen!');
}

// ── Test API connection ──

async function testConnection() {
  var apiUrl = document.getElementById('apiUrl').value.trim();

  if (!apiUrl) {
    showToast('Vul eerst de API URL in.');
    return;
  }

  var base = apiUrl.replace(/\/$/, '');

  try {
    var response = await fetch(base + '/health', { method: 'GET' });
    if (!response.ok) {
      showToast('Server bereikbaar maar fout: ' + response.status + ' ' + response.statusText);
      return;
    }

    // Server bereikbaar — test nu of de API-sleutel geaccepteerd wordt.
    var apiKey = document.getElementById('apiKey').value.trim();
    var headers = {};
    if (apiKey) headers['X-API-Key'] = apiKey;

    var auth = await fetch(base + '/api/v1/providers', { method: 'GET', headers: headers });
    if (auth.ok) {
      showToast('Verbinding én API-sleutel OK!');
    } else if (auth.status === 403) {
      showToast('Server OK, maar API-sleutel klopt niet (403). Vergelijk met API_KEYS op de server.');
    } else if (auth.status === 401) {
      showToast('Server OK, maar API-sleutel ontbreekt (401). Vul de sleutel in.');
    } else {
      showToast('Server OK, maar sleuteltest gaf: ' + auth.status + ' ' + auth.statusText);
    }
  } catch (err) {
    showToast('Verbindingsfout: ' + err.message);
  }
}

// ── Microphone enumeration ──

async function loadMicDevices() {
  var select = document.getElementById('micDevice');
  if (!select) return;

  try {
    // Vraag kort toestemming zodat labels zichtbaar worden
    var deviceList = await navigator.mediaDevices.enumerateDevices();
    var audioInputs = deviceList.filter(function(d) { return d.kind === 'audioinput'; });

    if (audioInputs.length > 0 && !audioInputs[0].label) {
      var tempStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      tempStream.getTracks().forEach(function(t) { t.stop(); });
      deviceList = await navigator.mediaDevices.enumerateDevices();
      audioInputs = deviceList.filter(function(d) { return d.kind === 'audioinput'; });
    }

    // Bewaar huidige selectie
    var current = select.value;

    // Reset opties (bewaar standaard optie)
    select.innerHTML = '<option value="">Standaard microfoon (systeem)</option>';

    audioInputs.forEach(function(device, i) {
      var opt = document.createElement('option');
      opt.value = device.deviceId;
      opt.textContent = device.label || ('Microfoon ' + (i + 1));
      select.appendChild(opt);
    });

    // Herstel selectie
    if (current) select.value = current;
  } catch (e) {
    var statusEl = document.getElementById('mic-test-status');
    if (statusEl) statusEl.textContent = 'Kan apparaten niet laden: ' + e.message;
  }
}

async function testMicrophone() {
  var statusEl = document.getElementById('mic-test-status');
  var deviceId = document.getElementById('micDevice').value;

  statusEl.textContent = 'Testen...';
  statusEl.style.color = 'var(--text-secondary)';

  try {
    var constraints = {
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true }
    };
    if (deviceId) constraints.audio.deviceId = { exact: deviceId };

    var stream = await navigator.mediaDevices.getUserMedia(constraints);

    // Controleer of er daadwerkelijk audio binnenkomt
    var ctx = new AudioContext();
    var source = ctx.createMediaStreamSource(stream);
    var analyser = ctx.createAnalyser();
    analyser.fftSize = 256;
    source.connect(analyser);

    var data = new Uint8Array(analyser.frequencyBinCount);

    // Wacht kort en meet of er signaal is
    await new Promise(function(resolve) { setTimeout(resolve, 500); });
    analyser.getByteTimeDomainData(data);

    var hasSignal = data.some(function(v) { return v !== 128; });

    stream.getTracks().forEach(function(t) { t.stop(); });
    ctx.close();

    statusEl.style.color = 'var(--primary)';
    statusEl.textContent = hasSignal
      ? 'Microfoon werkt! Audiosignaal gedetecteerd.'
      : 'Microfoon verbonden (stil — spreek in de microfoon om te testen).';
  } catch (e) {
    statusEl.style.color = '#dc2626';
    if (e.name === 'NotFoundError') {
      statusEl.textContent = 'Microfoon niet gevonden. Controleer de aansluiting.';
    } else if (e.name === 'NotAllowedError') {
      statusEl.textContent = 'Microfoontoegang geweigerd. Sta dit toe in browserinstellingen.';
    } else {
      statusEl.textContent = 'Fout: ' + e.message;
    }
  }
}

// ── Event listeners ──

document.getElementById('btn-save').addEventListener('click', saveSettings);
document.getElementById('btn-test').addEventListener('click', testConnection);
document.getElementById('btn-refresh-mic').addEventListener('click', loadMicDevices);
document.getElementById('btn-test-mic').addEventListener('click', testMicrophone);

// ── Initialize ──
loadSettings();
loadMicDevices();
