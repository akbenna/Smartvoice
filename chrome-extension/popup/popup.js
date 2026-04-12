/**
 * SmartVoice Chrome Extension - Popup Controller
 *
 * Manages UI state transitions and communication with service worker.
 * States: idle → recording → processing → results → idle
 */

const STATES = ['idle', 'recording', 'processing', 'results', 'error'];

let currentState = null;
let timerInterval = null;
let recordingStartTime = null;
let waveformAnimationId = null;

// ── State management ──

function setState(name) {
  STATES.forEach(s => {
    const el = document.getElementById(`state-${s}`);
    if (el) {
      el.classList.add('hidden');
    }
  });
  const active = document.getElementById(`state-${name}`);
  if (active) {
    active.classList.remove('hidden');
  }
  currentState = name;
}

function showStatus(text, isError) {
  const bar = document.getElementById('status-bar');
  const dot = document.getElementById('status-dot');
  const textEl = document.getElementById('status-text');
  bar.classList.remove('hidden');
  dot.classList.toggle('error', !!isError);
  textEl.textContent = text;
}

function hideStatus() {
  document.getElementById('status-bar').classList.add('hidden');
}

// ── Timer ──

function startTimer() {
  recordingStartTime = Date.now();
  timerInterval = setInterval(updateTimer, 1000);
  updateTimer();
}

function stopTimer() {
  if (timerInterval) clearInterval(timerInterval);
  timerInterval = null;
}

function updateTimer() {
  const elapsed = Math.floor((Date.now() - recordingStartTime) / 1000);
  const mins = String(Math.floor(elapsed / 60)).padStart(2, '0');
  const secs = String(elapsed % 60).padStart(2, '0');
  document.getElementById('timer').textContent = `${mins}:${secs}`;
}

// ── Waveform visualization ──

function startWaveform() {
  const canvas = document.getElementById('waveform');
  const ctx = canvas.getContext('2d');
  const bars = 40;
  const barWidth = canvas.width / bars - 2;

  function draw() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = '#059669';
    for (let i = 0; i < bars; i++) {
      const height = Math.random() * canvas.height * 0.8 + canvas.height * 0.1;
      const x = i * (barWidth + 2);
      const y = (canvas.height - height) / 2;
      ctx.fillRect(x, y, barWidth, height);
    }
    waveformAnimationId = requestAnimationFrame(draw);
  }
  draw();
}

function stopWaveform() {
  if (waveformAnimationId) cancelAnimationFrame(waveformAnimationId);
  waveformAnimationId = null;
}

// ── Clipboard helper ──

async function copyToClipboard(text, btnEl) {
  try {
    await navigator.clipboard.writeText(text);
    btnEl.classList.add('copied');
    setTimeout(() => btnEl.classList.remove('copied'), 1500);
  } catch (e) {
    const ta = document.createElement('textarea');
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    btnEl.classList.add('copied');
    setTimeout(() => btnEl.classList.remove('copied'), 1500);
  }
}

// ── Format SOEP for clipboard ──

function formatSOEPText(soep) {
  let text = '';
  if (soep.s) text += `S: ${soep.s}\n`;
  if (soep.o) text += `O: ${soep.o}\n`;
  if (soep.e) text += `E: ${soep.e}\n`;
  if (soep.p) text += `P: ${soep.p}\n`;
  if (soep.icpc_code) text += `\nICPC: ${soep.icpc_code} - ${soep.icpc_titel || ''}`;
  return text.trim();
}

// ── Service worker communication ──

function sendMessage(action, data) {
  return chrome.runtime.sendMessage({ action: action, ...(data || {}) });
}

// ── Event handlers ──

document.getElementById('btn-settings').addEventListener('click', function() {
  chrome.runtime.openOptionsPage();
});

document.getElementById('btn-start').addEventListener('click', async function() {
  setState('recording');
  showStatus('Opname actief...', false);
  startTimer();
  startWaveform();
  var response = await sendMessage('START_RECORDING');
  if (response && response.error) {
    stopTimer();
    stopWaveform();
    setState('error');
    document.getElementById('error-message').textContent = response.error;
  }
});

document.getElementById('btn-stop').addEventListener('click', async function() {
  stopTimer();
  stopWaveform();
  setState('processing');
  showStatus('Verwerken...', false);
  updateProgress(10, 'Audio wordt verzonden...');
  await sendMessage('STOP_RECORDING');
});

document.getElementById('btn-copy-decisief').addEventListener('click', function() {
  var text = document.getElementById('decisief-text').textContent;
  copyToClipboard(text, this);
});

document.getElementById('btn-copy-soep').addEventListener('click', function() {
  var soep = {
    s: document.getElementById('soep-s').textContent,
    o: document.getElementById('soep-o').textContent,
    e: document.getElementById('soep-e').textContent,
    p: document.getElementById('soep-p').textContent,
    icpc_code: document.getElementById('icpc-code') ? document.getElementById('icpc-code').textContent : '',
    icpc_titel: document.getElementById('icpc-title') ? document.getElementById('icpc-title').textContent : '',
  };
  copyToClipboard(formatSOEPText(soep), this);
});

document.getElementById('btn-push-bricks').addEventListener('click', async function() {
  var result = await sendMessage('PUSH_TO_BRICKS');
  if (result && result.success) {
    showStatus('Succesvol naar Bricks gepusht!', false);
  } else {
    showStatus((result && result.error) || 'Bricks-pagina niet gevonden.', true);
  }
});

document.getElementById('btn-new-consult').addEventListener('click', function() {
  hideStatus();
  setState('idle');
});

document.getElementById('btn-retry').addEventListener('click', function() {
  hideStatus();
  setState('idle');
});

// ── Progress updates ──

function updateProgress(percent, step) {
  document.getElementById('progress-fill').style.width = percent + '%';
  if (step) document.getElementById('processing-step').textContent = step;
}

// ── Display results ──

function displayResults(data) {
  document.getElementById('decisief-text').textContent = data.decisief || 'Geen decisief regel gegenereerd.';

  var soep = data.soep || {};
  document.getElementById('soep-s').textContent = soep.s || '-';
  document.getElementById('soep-o').textContent = soep.o || '-';
  document.getElementById('soep-e').textContent = soep.e || '-';
  document.getElementById('soep-p').textContent = soep.p || '-';

  if (soep.icpc_code) {
    document.getElementById('icpc-badge').classList.remove('hidden');
    document.getElementById('icpc-code').textContent = soep.icpc_code;
    document.getElementById('icpc-title').textContent = soep.icpc_titel || '';
  } else {
    document.getElementById('icpc-badge').classList.add('hidden');
  }

  setState('results');
  showStatus('Verwerking voltooid', false);
}

// ── Listen for messages from service worker ──

chrome.runtime.onMessage.addListener(function(msg) {
  if (msg.action === 'PROCESSING_UPDATE') {
    updateProgress(msg.percent, msg.step);
  } else if (msg.action === 'PROCESSING_COMPLETE') {
    displayResults(msg.data);
  } else if (msg.action === 'PROCESSING_ERROR') {
    setState('error');
    document.getElementById('error-message').textContent =
      msg.error || 'Er is een fout opgetreden bij het verwerken.';
    showStatus('Fout bij verwerking', true);
  }
});

// ── Initialize ──

async function init() {
  var response = await sendMessage('GET_STATE');
  if (response && response.state === 'recording') {
    setState('recording');
    showStatus('Opname actief...', false);
    recordingStartTime = response.startTime || Date.now();
    startTimer();
    startWaveform();
  } else if (response && response.state === 'processing') {
    setState('processing');
    showStatus('Verwerken...', false);
    updateProgress(response.percent || 50, response.step || 'Bezig met verwerken...');
  } else if (response && response.state === 'results' && response.data) {
    displayResults(response.data);
  } else {
    setState('idle');
  }
}

init();
