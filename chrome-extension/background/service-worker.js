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
    // Document might already exist
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
    'practiceId', 'practitionerName',
  ]);
}

async function callAPI(endpoint, body, isFormData = false) {
  const config = await getConfig();
  if (!config.apiUrl || !config.apiKey) {
    throw new Error('API niet geconfigureerd. Open instellingen.');
  }

  const url = `${config.apiUrl.replace(/\/$/, '')}${endpoint}`;
  const headers = {
    'X-API-Key': config.apiKey,
  };

  if (!isFormData) {
    headers['Content-Type'] = 'application/json';
  }

  const response = await fetch(url, {
    method: 'POST',
    headers,
    body: isFormData ? body : JSON.stringify(body),
  });

  if (!response.ok) {
    const errBody = await response.text();
    throw new Error(`API fout (${response.status}): ${errBody}`);
  }

  return response.json();
}

// ── Processing pipeline ──

async function processAudio(audioBase64, mimeType) {
  state.status = 'processing';
  state.percent = 10;
  state.step = 'Audio wordt verzonden...';
  broadcastUpdate();

  try {
    // Build form data with audio
    const config = await getConfig();

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
    if (config.practiceId) formData.append('practice_id', config.practiceId);
    if (config.practitionerName) formData.append('practitioner_name', config.practitionerName);

    state.percent = 30;
    state.step = 'Audio wordt getranscribeerd...';
    broadcastUpdate();

    // Single endpoint: upload audio, get full result
    const result = await callAPI('/api/v1/consult/process', formData, true);

    state.percent = 100;
    state.step = 'Verwerking voltooid!';
    state.status = 'results';
    state.data = result;
    broadcastComplete(result);
  } catch (err) {
    state.status = 'error';
    broadcastError(err.message);
  }
}

// ── Broadcast messages to popup ──

function broadcastUpdate() {
  chrome.runtime.sendMessage({
    action: 'PROCESSING_UPDATE',
    percent: state.percent,
    step: state.step,
  }).catch(() => {}); // popup might be closed
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

  // Find Bricks tab
  const tabs = await chrome.tabs.query({
    url: [
      'https://*.bfrw.nl/*',
      'https://*.bfrw.cloud/*',
      'https://*.brickshuisarts.nl/*',
      'https://*.bfrw-online.nl/*',
    ],
  });

  if (tabs.length === 0) {
    // Fallback: copy to clipboard via popup
    return { error: 'Geen Bricks-tab gevonden. Data is gekopieerd naar klembord.' };
  }

  // Send data to content script in Bricks tab
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
      (async () => {
        try {
          await ensureOffscreen();
          const result = await chrome.runtime.sendMessage({
            action: 'OFFSCREEN_START_RECORDING',
          });
          if (result?.error) {
            sendResponse({ error: result.error });
            return;
          }
          state.status = 'recording';
          state.startTime = Date.now();
          state.data = null;
          sendResponse({ success: true });
        } catch (err) {
          sendResponse({ error: `Kon microfoon niet starten: ${err.message}` });
        }
      })();
      return true; // async

    case 'STOP_RECORDING':
      (async () => {
        try {
          const result = await chrome.runtime.sendMessage({
            action: 'OFFSCREEN_STOP_RECORDING',
          });
          await closeOffscreen();

          if (result?.error) {
            sendResponse({ error: result.error });
            return;
          }

          sendResponse({ success: true });
          // Start processing in background
          processAudio(result.audio, result.mimeType);
        } catch (err) {
          sendResponse({ error: `Fout bij stoppen opname: ${err.message}` });
        }
      })();
      return true;

    case 'PUSH_TO_BRICKS':
      pushToBricks().then(sendResponse);
      return true;
  }
});
