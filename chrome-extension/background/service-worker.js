/**
 * SmartVoice - Service Worker
 *
 * Coordinates between popup, offscreen document, content scripts, and cloud API.
 * Manages recording state, API calls, and Bricks integration.
 */

// ── State ──

const state = {
  status: 'idle', // idle | recording | processing | results | error
  startTime: null,
  data: null,
  percent: 0,
  step: '',
};

// ── Offscreen document management ──

let offscreenCreated = false;

async function ensureOffscreen() {
  if (offscreenCreated) return;
  try {
    await chrome.offscreen.createDocument({
      url: 'offscreen/offscreen.html',
      reasons: ['USER_MEDIA'],
      justification: 'Microphone recording for medical consultation capture',
    });
    offscreenCreated = true;
  } catch (e) {
    if (!e.message.includes('already exists')) throw e;
    offscreenCreated = true;
  }
}

async function closeOffscreen() {
  try {
    await chrome.offscreen.closeDocument();
    offscreenCreated = false;
  } catch {
    // Already closed
  }
}

// ── API communication ──

async function getConfig() {
  return chrome.storage.sync.get([
    'apiUrl', 'apiKey', 'sttProvider', 'llmProvider',
  ]);
}

// ── Processing pipeline ──

async function processAudio(audioBase64, mimeType) {
  state.status = 'processing';
  state.percent = 10;
  state.step = 'Audio wordt verzonden...';
  broadcastUpdate();

  try {
    const config = await getConfig();
    const apiUrl = (config.apiUrl || 'http://localhost:8002').replace(/\/$/, '');

    // Convert base64 to blob
    const byteChars = atob(audioBase64);
    const byteArray = new Uint8Array(byteChars.length);
    for (let i = 0; i < byteChars.length; i++) {
      byteArray[i] = byteChars.charCodeAt(i);
    }
    const ext = mimeType.includes('webm') ? 'webm' : mimeType.includes('mp4') ? 'mp4' : 'wav';
    const blob = new Blob([byteArray], { type: mimeType });

    const formData = new FormData();
    formData.append('audio', blob, `consult.${ext}`);
    if (config.sttProvider) formData.append('stt_provider', config.sttProvider);
    if (config.llmProvider) formData.append('llm_provider', config.llmProvider);

    state.percent = 30;
    state.step = 'Audio wordt getranscribeerd...';
    broadcastUpdate();

    const headers = {};
    if (config.apiKey) {
      headers['X-API-Key'] = config.apiKey;
    }

    const response = await fetch(`${apiUrl}/api/v1/consult/process`, {
      method: 'POST',
      headers,
      body: formData,
    });

    if (!response.ok) {
      const errBody = await response.text();
      throw new Error(`API fout (${response.status}): ${errBody}`);
    }

    const result = await response.json();

    state.percent = 100;
    state.step = 'Verwerking voltooid!';
    state.status = 'results';
    state.data = result;

    // Persist results so popup can retrieve them even after service worker sleeps
    chrome.storage.local.set({
      sv_state: 'results',
      sv_data: result,
    });

    broadcastComplete(result);
  } catch (err) {
    state.status = 'error';
    chrome.storage.local.set({
      sv_state: 'error',
      sv_error: err.message,
    });
    broadcastError(err.message);
  }
}

// ── Broadcast messages to popup ──

function broadcastUpdate() {
  chrome.runtime.sendMessage({
    action: 'PROCESSING_UPDATE',
    percent: state.percent,
    step: state.step,
  }).catch(() => {});
}

function broadcastComplete(data) {
  chrome.runtime.sendMessage({
    action: 'PROCESSING_COMPLETE',
    data,
  }).catch(() => {});
}

function broadcastError(error) {
  chrome.runtime.sendMessage({
    action: 'PROCESSING_ERROR',
    error,
  }).catch(() => {});
}

// ── Push to Bricks ──

async function pushToBricks() {
  if (!state.data) {
    return { error: 'Geen resultaten om te pushen.' };
  }

  const tabs = await chrome.tabs.query({
    url: [
      'https://*.bfrcloud.com/*',
      'https://*.bfrnet.nl/*',
      'https://*.bricks-huisarts.nl/*',
      'https://*.bfrw.nl/*',
      'https://*.bfrw.cloud/*',
      'https://*.brickshuisarts.nl/*',
      'https://*.bfrw-online.nl/*',
    ],
  });

  if (tabs.length === 0) {
    return { error: 'Geen Bricks-tab gevonden. Open Bricks in een tab.' };
  }

  try {
    const response = await chrome.tabs.sendMessage(tabs[0].id, {
      action: 'INJECT_SOEP',
      data: state.data,
    });
    return response || { success: true };
  } catch (err) {
    return { error: `Kon niet injecteren in Bricks: ${err.message}` };
  }
}

// ── Message handler ──

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  switch (msg.action) {
    case 'GET_STATE':
      sendResponse({
        state: state.status,
        startTime: state.startTime,
        data: state.data,
        percent: state.percent,
        step: state.step,
      });
      return false;

    case 'START_RECORDING':
      // Open recorder tab (works in Edge + Chrome, no offscreen needed)
      (async () => {
        try {
          const tab = await chrome.tabs.create({
            url: chrome.runtime.getURL('recorder/recorder.html'),
            active: true,
          });
          state.status = 'recording';
          state.startTime = Date.now();
          state.data = null;
          chrome.storage.local.remove(['sv_state', 'sv_data', 'sv_error']);
          sendResponse({ success: true });
        } catch (err) {
          sendResponse({ error: `Kon recorder niet openen: ${err.message}` });
        }
      })();
      return true;

    case 'RECORDER_STARTED':
      state.status = 'recording';
      state.startTime = Date.now();
      sendResponse({ success: true });
      return false;

    case 'RECORDER_AUDIO':
      // Audio received from recorder tab
      sendResponse({ success: true });
      processAudio(msg.audio, msg.mimeType);
      return false;

    case 'STOP_RECORDING':
      sendResponse({ success: true });
      return false;

    case 'PUSH_TO_BRICKS':
      pushToBricks().then(sendResponse);
      return true;
  }
});
