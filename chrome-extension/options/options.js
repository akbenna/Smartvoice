/**
 * SmartVoice - Options Page Controller
 * Manages extension settings stored in chrome.storage.sync.
 */

const FIELDS = [
  'apiUrl', 'apiKey', 'sttProvider', 'llmProvider',
  'practiceId', 'practitionerName',
];

const SELECTOR_FIELDS = {
  selJournaal: 'journaal',
  selSoepS: 'soep_s',
  selSoepO: 'soep_o',
  selSoepE: 'soep_e',
  selSoepP: 'soep_p',
};

function showToast(message, duration = 2500) {
  const toast = document.getElementById('toast');
  toast.textContent = message;
  toast.classList.add('show');
  setTimeout(() => toast.classList.remove('show'), duration);
}

// ── Load settings ──

async function loadSettings() {
  const stored = await chrome.storage.sync.get([...FIELDS, 'bricksSelectors']);

  FIELDS.forEach(key => {
    const el = document.getElementById(key);
    if (el && stored[key]) el.value = stored[key];
  });

  // Load selectors
  if (stored.bricksSelectors) {
    try {
      const selectors = JSON.parse(stored.bricksSelectors);
      Object.entries(SELECTOR_FIELDS).forEach(([inputId, selectorKey]) => {
        const el = document.getElementById(inputId);
        if (el && selectors[selectorKey]) {
          el.value = Array.isArray(selectors[selectorKey])
            ? selectors[selectorKey].join(', ')
            : selectors[selectorKey];
        }
      });
    } catch {
      // Ignore parse errors
    }
  }
}

// ── Save settings ──

async function saveSettings() {
  const data = {};

  FIELDS.forEach(key => {
    const el = document.getElementById(key);
    if (el) data[key] = el.value.trim();
  });

  // Build selectors object
  const selectors = {};
  Object.entries(SELECTOR_FIELDS).forEach(([inputId, selectorKey]) => {
    const el = document.getElementById(inputId);
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
  const apiUrl = document.getElementById('apiUrl').value.trim();
  const apiKey = document.getElementById('apiKey').value.trim();

  if (!apiUrl || !apiKey) {
    showToast('Vul eerst API URL en sleutel in.');
    return;
  }

  try {
    const response = await fetch(`${apiUrl.replace(/\/$/, '')}/api/v1/health`, {
      method: 'GET',
      headers: { 'X-API-Key': apiKey },
    });

    if (response.ok) {
      const data = await response.json();
      showToast(`Verbinding OK! Status: ${data.status || 'healthy'}`);
    } else {
      showToast(`Fout: ${response.status} ${response.statusText}`);
    }
  } catch (err) {
    showToast(`Verbindingsfout: ${err.message}`);
  }
}

// ── Event listeners ──

document.getElementById('btn-save').addEventListener('click', saveSettings);
document.getElementById('btn-test').addEventListener('click', testConnection);

// ── Initialize ──
loadSettings();
