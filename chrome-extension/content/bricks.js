/**
 * SmartVoice - Bricks HIS Content Script
 *
 * Detects the Bricks Huisarts web interface and provides:
 * 1. Floating SmartVoice widget for quick access
 * 2. SOEP injection into Bricks journal fields
 * 3. Decisief regel insertion into the active text field
 *
 * Since Bricks DOM structure varies by version, this uses configurable
 * selectors with sensible defaults. Users can override selectors via
 * the extension options page.
 */

// ── Default Bricks field selectors ──
// These target common patterns in Bricks Huisarts.
// Users can override these in extension options.
const DEFAULT_SELECTORS = {
  // Journal/consult note field (textarea or contenteditable)
  journaal: [
    'textarea[name*="journaal"]',
    'textarea[name*="journal"]',
    'textarea[name*="notitie"]',
    '[contenteditable="true"][data-field*="journaal"]',
    '.journal-editor textarea',
    '.consult-notes textarea',
  ],
  // Individual SOEP fields (if Bricks uses separate fields)
  soep_s: [
    'textarea[name*="subjectief"]',
    'textarea[data-soep="S"]',
    '#soep-s',
    '.soep-field-s textarea',
  ],
  soep_o: [
    'textarea[name*="objectief"]',
    'textarea[data-soep="O"]',
    '#soep-o',
    '.soep-field-o textarea',
  ],
  soep_e: [
    'textarea[name*="evaluatie"]',
    'textarea[data-soep="E"]',
    '#soep-e',
    '.soep-field-e textarea',
  ],
  soep_p: [
    'textarea[name*="plan"]',
    'textarea[data-soep="P"]',
    '#soep-p',
    '.soep-field-p textarea',
  ],
  // ICPC code input
  icpc: [
    'input[name*="icpc"]',
    'input[name*="ICPC"]',
    '.icpc-input input',
    '#icpc-code',
  ],
};

let userSelectors = {};
let floatingWidget = null;
let lastResult = null;

// ── Load user-configured selectors ──

async function loadSelectors() {
  try {
    const stored = await chrome.storage.sync.get(['bricksSelectors']);
    if (stored.bricksSelectors) {
      userSelectors = JSON.parse(stored.bricksSelectors);
    }
  } catch {
    // Use defaults
  }
}

// ── Find element using selector list ──

function findElement(selectorKey) {
  // Try user-defined selectors first
  if (userSelectors[selectorKey]) {
    const selectors = Array.isArray(userSelectors[selectorKey])
      ? userSelectors[selectorKey]
      : [userSelectors[selectorKey]];
    for (const sel of selectors) {
      const el = document.querySelector(sel);
      if (el) return el;
    }
  }

  // Fallback to defaults
  const defaults = DEFAULT_SELECTORS[selectorKey] || [];
  for (const sel of defaults) {
    const el = document.querySelector(sel);
    if (el) return el;
  }
  return null;
}

// ── Set value in field (handles both textarea and contenteditable) ──

function setFieldValue(element, value) {
  if (!element || !value) return false;

  if (element.tagName === 'TEXTAREA' || element.tagName === 'INPUT') {
    element.value = value;
    element.dispatchEvent(new Event('input', { bubbles: true }));
    element.dispatchEvent(new Event('change', { bubbles: true }));
  } else if (element.contentEditable === 'true') {
    element.textContent = value;
    element.dispatchEvent(new Event('input', { bubbles: true }));
  }
  return true;
}

// ── Inject SOEP into Bricks ──

function injectSOEP(data) {
  const soep = data.soep || {};
  let injected = false;

  // Try individual SOEP fields first
  const sField = findElement('soep_s');
  const oField = findElement('soep_o');
  const eField = findElement('soep_e');
  const pField = findElement('soep_p');

  if (sField || oField || eField || pField) {
    if (sField && soep.s) { setFieldValue(sField, soep.s); injected = true; }
    if (oField && soep.o) { setFieldValue(oField, soep.o); injected = true; }
    if (eField && soep.e) { setFieldValue(eField, soep.e); injected = true; }
    if (pField && soep.p) { setFieldValue(pField, soep.p); injected = true; }
  }

  // Try ICPC field
  const icpcField = findElement('icpc');
  if (icpcField && soep.icpc_code) {
    setFieldValue(icpcField, soep.icpc_code);
  }

  // Fallback: try journal field with combined text
  if (!injected) {
    const journalField = findElement('journaal');
    if (journalField) {
      const text = formatSOEPText(data);
      setFieldValue(journalField, text);
      injected = true;
    }
  }

  // Last resort: try the currently focused element
  if (!injected) {
    const active = document.activeElement;
    if (active && (active.tagName === 'TEXTAREA' || active.contentEditable === 'true')) {
      const text = formatSOEPText(data);
      setFieldValue(active, text);
      injected = true;
    }
  }

  return injected;
}

function formatSOEPText(data) {
  const soep = data.soep || {};
  let parts = [];
  if (data.decisief) parts.push(`[Decisief] ${data.decisief}`);
  parts.push('');
  if (soep.s) parts.push(`S: ${soep.s}`);
  if (soep.o) parts.push(`O: ${soep.o}`);
  if (soep.e) parts.push(`E: ${soep.e}`);
  if (soep.p) parts.push(`P: ${soep.p}`);
  if (soep.icpc_code) parts.push(`\nICPC: ${soep.icpc_code}${soep.icpc_titel ? ' - ' + soep.icpc_titel : ''}`);
  return parts.join('\n');
}

// ── Floating widget ──

function createWidget() {
  if (floatingWidget) return;

  floatingWidget = document.createElement('div');
  floatingWidget.id = 'smartvoice-widget';
  floatingWidget.innerHTML = `
    <div class="sv-widget-btn" id="sv-toggle" title="SmartVoice">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="white">
        <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3z"/>
        <path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z"/>
      </svg>
    </div>
    <div class="sv-widget-panel hidden" id="sv-panel">
      <div class="sv-panel-header">
        <span>SmartVoice</span>
        <button id="sv-close" class="sv-close">&times;</button>
      </div>
      <div class="sv-panel-body">
        <div id="sv-no-result" class="sv-message">
          Nog geen resultaat. Gebruik de extensie popup om een consult op te nemen.
        </div>
        <div id="sv-result" class="hidden">
          <div class="sv-decisief">
            <strong>Decisief:</strong>
            <p id="sv-decisief-text"></p>
          </div>
          <div class="sv-actions">
            <button id="sv-inject" class="sv-btn sv-btn-primary">Invoegen in Bricks</button>
            <button id="sv-copy" class="sv-btn sv-btn-secondary">Kopieer</button>
          </div>
        </div>
      </div>
    </div>
  `;
  document.body.appendChild(floatingWidget);

  // Event listeners
  document.getElementById('sv-toggle').addEventListener('click', () => {
    document.getElementById('sv-panel').classList.toggle('hidden');
  });
  document.getElementById('sv-close').addEventListener('click', () => {
    document.getElementById('sv-panel').classList.add('hidden');
  });
  document.getElementById('sv-inject').addEventListener('click', () => {
    if (lastResult) {
      const success = injectSOEP(lastResult);
      showNotification(success
        ? 'SOEP succesvol ingevoegd!'
        : 'Kon geen velden vinden. Probeer handmatig plakken.');
    }
  });
  document.getElementById('sv-copy').addEventListener('click', () => {
    if (lastResult) {
      navigator.clipboard.writeText(formatSOEPText(lastResult));
      showNotification('Gekopieerd naar klembord!');
    }
  });
}

function showNotification(text) {
  const notif = document.createElement('div');
  notif.className = 'sv-notification';
  notif.textContent = text;
  document.body.appendChild(notif);
  setTimeout(() => {
    notif.classList.add('sv-notification-fade');
    setTimeout(() => notif.remove(), 300);
  }, 2500);
}

function updateWidget(data) {
  lastResult = data;
  document.getElementById('sv-no-result').classList.add('hidden');
  document.getElementById('sv-result').classList.remove('hidden');
  document.getElementById('sv-decisief-text').textContent = data.decisief || '';
  // Auto-show panel
  document.getElementById('sv-panel').classList.remove('hidden');
}

// ── Message listener ──

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.action === 'INJECT_SOEP') {
    const success = injectSOEP(msg.data);
    updateWidget(msg.data);
    sendResponse({ success });
    if (!success) {
      showNotification('Velden niet gevonden. Gebruik de widget om handmatig in te voegen.');
    } else {
      showNotification('SOEP ingevoegd in Bricks!');
    }
    return false;
  }
});

// ── Initialize ──

async function init() {
  await loadSelectors();
  createWidget();
}

init();
