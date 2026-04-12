/**
 * SmartVoice - Bricks HIS Content Script
 *
 * Detects the Bricks Huisarts web interface and provides:
 * 1. Floating SmartVoice widget for quick access
 * 2. SOEP injection into Bricks journal fields
 * 3. Decisief regel insertion
 */

var DEFAULT_SELECTORS = {
  journaal: [
    'textarea[name*="journaal"]',
    'textarea[name*="journal"]',
    'textarea[name*="notitie"]',
    '[contenteditable="true"][data-field*="journaal"]',
    '.journal-editor textarea',
    '.consult-notes textarea',
  ],
  soep_s: ['textarea[name*="subjectief"]', 'textarea[data-soep="S"]', '.soep-field-s textarea'],
  soep_o: ['textarea[name*="objectief"]', 'textarea[data-soep="O"]', '.soep-field-o textarea'],
  soep_e: ['textarea[name*="evaluatie"]', 'textarea[data-soep="E"]', '.soep-field-e textarea'],
  soep_p: ['textarea[name*="plan"]', 'textarea[data-soep="P"]', '.soep-field-p textarea'],
  icpc: ['input[name*="icpc"]', 'input[name*="ICPC"]', '.icpc-input input'],
};

var userSelectors = {};
var floatingWidget = null;
var lastResult = null;

async function loadSelectors() {
  try {
    var stored = await chrome.storage.sync.get(['bricksSelectors']);
    if (stored.bricksSelectors) {
      userSelectors = JSON.parse(stored.bricksSelectors);
    }
  } catch (e) { /* Use defaults */ }
}

function findElement(selectorKey) {
  if (userSelectors[selectorKey]) {
    var selectors = Array.isArray(userSelectors[selectorKey])
      ? userSelectors[selectorKey] : [userSelectors[selectorKey]];
    for (var i = 0; i < selectors.length; i++) {
      var el = document.querySelector(selectors[i]);
      if (el) return el;
    }
  }
  var defaults = DEFAULT_SELECTORS[selectorKey] || [];
  for (var j = 0; j < defaults.length; j++) {
    var el2 = document.querySelector(defaults[j]);
    if (el2) return el2;
  }
  return null;
}

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

function injectSOEP(data) {
  var soep = data.soep || {};
  var injected = false;

  var sField = findElement('soep_s');
  var oField = findElement('soep_o');
  var eField = findElement('soep_e');
  var pField = findElement('soep_p');

  if (sField || oField || eField || pField) {
    if (sField && soep.s) { setFieldValue(sField, soep.s); injected = true; }
    if (oField && soep.o) { setFieldValue(oField, soep.o); injected = true; }
    if (eField && soep.e) { setFieldValue(eField, soep.e); injected = true; }
    if (pField && soep.p) { setFieldValue(pField, soep.p); injected = true; }
  }

  var icpcField = findElement('icpc');
  if (icpcField && soep.icpc_code) {
    setFieldValue(icpcField, soep.icpc_code);
  }

  if (!injected) {
    var journalField = findElement('journaal');
    if (journalField) {
      setFieldValue(journalField, formatSOEPText(data));
      injected = true;
    }
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

function showNotification(text) {
  var notif = document.createElement('div');
  notif.className = 'sv-notification';
  notif.textContent = text;
  document.body.appendChild(notif);
  setTimeout(function() {
    notif.classList.add('sv-notification-fade');
    setTimeout(function() { notif.remove(); }, 300);
  }, 2500);
}

function createWidget() {
  if (floatingWidget) return;

  floatingWidget = document.createElement('div');
  floatingWidget.id = 'smartvoice-widget';
  floatingWidget.innerHTML = '<div class="sv-widget-btn" id="sv-toggle" title="SmartVoice">' +
    '<svg width="20" height="20" viewBox="0 0 24 24" fill="white">' +
    '<path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3z"/>' +
    '<path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z"/>' +
    '</svg></div>' +
    '<div class="sv-widget-panel hidden" id="sv-panel">' +
    '<div class="sv-panel-header"><span>SmartVoice</span><button id="sv-close" class="sv-close">&times;</button></div>' +
    '<div class="sv-panel-body">' +
    '<div id="sv-no-result" class="sv-message">Nog geen resultaat. Gebruik de extensie popup om een consult op te nemen.</div>' +
    '<div id="sv-result" class="hidden">' +
    '<div class="sv-decisief"><strong>Decisief:</strong><p id="sv-decisief-text"></p></div>' +
    '<div class="sv-actions">' +
    '<button id="sv-inject" class="sv-btn sv-btn-primary">Invoegen in Bricks</button>' +
    '<button id="sv-copy" class="sv-btn sv-btn-secondary">Kopieer</button>' +
    '</div></div></div></div>';

  document.body.appendChild(floatingWidget);

  document.getElementById('sv-toggle').addEventListener('click', function() {
    document.getElementById('sv-panel').classList.toggle('hidden');
  });
  document.getElementById('sv-close').addEventListener('click', function() {
    document.getElementById('sv-panel').classList.add('hidden');
  });
  document.getElementById('sv-inject').addEventListener('click', function() {
    if (lastResult) {
      var success = injectSOEP(lastResult);
      showNotification(success ? 'SOEP succesvol ingevoegd!' : 'Kon geen velden vinden.');
    }
  });
  document.getElementById('sv-copy').addEventListener('click', function() {
    if (lastResult) {
      navigator.clipboard.writeText(formatSOEPText(lastResult));
      showNotification('Gekopieerd naar klembord!');
    }
  });
}

function updateWidget(data) {
  lastResult = data;
  document.getElementById('sv-no-result').classList.add('hidden');
  document.getElementById('sv-result').classList.remove('hidden');
  document.getElementById('sv-decisief-text').textContent = data.decisief || '';
  document.getElementById('sv-panel').classList.remove('hidden');
}

chrome.runtime.onMessage.addListener(function(msg, _sender, sendResponse) {
  if (msg.action === 'INJECT_SOEP') {
    var success = injectSOEP(msg.data);
    updateWidget(msg.data);
    sendResponse({ success: success });
    showNotification(success ? 'SOEP ingevoegd in Bricks!' : 'Velden niet gevonden. Gebruik de widget.');
    return false;
  }
});

async function init() {
  await loadSelectors();
  createWidget();
}

init();
