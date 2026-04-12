/**
 * SmartVoice - Options Page Controller
 * Manages extension settings stored in chrome.storage.sync.
 */

var FIELDS = ['apiUrl', 'apiKey', 'sttProvider', 'llmProvider'];

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

  try {
    var response = await fetch(apiUrl.replace(/\/$/, '') + '/health', {
      method: 'GET',
    });

    if (response.ok) {
      var data = await response.json();
      showToast('Verbinding OK! Status: ' + (data.status || 'healthy'));
    } else {
      showToast('Fout: ' + response.status + ' ' + response.statusText);
    }
  } catch (err) {
    showToast('Verbindingsfout: ' + err.message);
  }
}

// ── Event listeners ──

document.getElementById('btn-save').addEventListener('click', saveSettings);
document.getElementById('btn-test').addEventListener('click', testConnection);

// ── Initialize ──
loadSettings();
