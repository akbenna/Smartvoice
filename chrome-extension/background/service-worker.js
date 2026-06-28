/**
 * SmartVoice - Service Worker
 *
 * Handles:
 * 1. PROCESS_AUDIO — receives base64 audio from popup/recorder, calls Cloud API,
 *    stores results in chrome.storage.local. Runs persistently even when popup closes.
 * 2. GET_STATE — popup asks for current state
 * 3. PUSH_TO_BRICKS — push results to Bricks content script
 * 4. RECORDER_AUDIO — legacy handler for recorder page
 */

// ── API call (runs in service worker — survives popup close) ──

async function callCloudAPI(base64Audio, mimeType) {
  const config = await chrome.storage.sync.get(['apiUrl', 'apiKey', 'sttProvider', 'llmProvider']);
  const apiUrl = (config.apiUrl || 'http://localhost:8002').replace(/\/$/, '');
  const endpoint = apiUrl + '/api/v1/consult/process';

  // Convert base64 to Blob
  const byteChars = atob(base64Audio);
  const byteArray = new Uint8Array(byteChars.length);
  for (let i = 0; i < byteChars.length; i++) {
    byteArray[i] = byteChars.charCodeAt(i);
  }
  const blob = new Blob([byteArray], { type: mimeType });

  const ext = mimeType.includes('webm') ? 'webm' : 'wav';
  const formData = new FormData();
  formData.append('audio', blob, 'consult.' + ext);
  if (config.sttProvider) formData.append('stt_provider', config.sttProvider);
  if (config.llmProvider) formData.append('llm_provider', config.llmProvider);

  const headers = {};
  const apiKey = (config.apiKey || '').trim();
  if (apiKey) headers['X-API-Key'] = apiKey;

  // Update state: processing
  await chrome.storage.local.set({
    sv_state: 'processing',
    sv_step: 'Audio wordt verzonden naar ' + apiUrl + '...',
    sv_error: null,
  });

  const response = await fetch(endpoint, {
    method: 'POST',
    headers: headers,
    body: formData,
  });

  if (!response.ok) {
    const errText = await response.text();
    if (response.status === 403) {
      throw new Error('API-sleutel klopt niet. Controleer of de sleutel in de ' +
        'extensie-instellingen exact overeenkomt met die op de server (Railway: API_KEYS).');
    }
    if (response.status === 401) {
      throw new Error('API-sleutel ontbreekt. Vul de sleutel in bij de extensie-instellingen.');
    }
    throw new Error('API fout (' + response.status + '): ' + errText.substring(0, 200));
  }

  return await response.json();
}

// ── Message handler ──

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  switch (msg.action) {

    case 'PROCESS_AUDIO':
      // Popup/recorder sends base64 audio — we call the API from here
      // so the request survives popup close.
      (async () => {
        try {
          await chrome.storage.local.set({ sv_state: 'processing', sv_step: 'Audio wordt verwerkt...', sv_error: null });

          const result = await callCloudAPI(msg.audio, msg.mimeType);

          await chrome.storage.local.set({ sv_state: 'results', sv_data: result, sv_error: null });
          sendResponse({ success: true, data: result });
        } catch (err) {
          const config = await chrome.storage.sync.get(['apiUrl']);
          const apiUrl = config.apiUrl || 'http://localhost:8002';
          let errorMsg = err.message || 'Onbekende fout';

          // Verduidelijk "Failed to fetch" met API URL
          if (errorMsg === 'Failed to fetch') {
            errorMsg = 'Kan de API niet bereiken op: ' + apiUrl +
              '\n\nControleer:\n• Is de API URL correct in Instellingen?\n• Is de server actief?\n• Heb je internetverbinding?';
          }

          await chrome.storage.local.set({ sv_state: 'error', sv_error: errorMsg });
          sendResponse({ success: false, error: errorMsg });
        }
      })();
      return true; // async response

    case 'GET_STATE':
      // Popup asks for current state — read from storage
      chrome.storage.local.get(['sv_state', 'sv_data', 'sv_error', 'sv_step'], (stored) => {
        sendResponse({
          state: stored.sv_state || 'idle',
          data: stored.sv_data || null,
          error: stored.sv_error || null,
          step: stored.sv_step || null,
        });
      });
      return true; // async response

    case 'PUSH_TO_BRICKS':
      // Find Bricks tab and send INJECT_SOEP
      (async () => {
        try {
          const stored = await chrome.storage.local.get(['sv_data']);
          if (!stored.sv_data) {
            sendResponse({ error: 'Geen resultaten om te pushen.' });
            return;
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
            sendResponse({ error: 'Geen Bricks-tab gevonden.' });
            return;
          }

          const response = await chrome.tabs.sendMessage(tabs[0].id, {
            action: 'INJECT_SOEP',
            data: stored.sv_data,
          });
          sendResponse(response || { success: true });
        } catch (err) {
          sendResponse({ error: err.message });
        }
      })();
      return true; // async response

    case 'RECORDER_AUDIO':
      // Legacy: recorder page sends base64 audio
      (async () => {
        try {
          await chrome.storage.local.set({ sv_state: 'processing', sv_error: null });

          const result = await callCloudAPI(msg.audio, msg.mimeType);

          await chrome.storage.local.set({ sv_state: 'results', sv_data: result, sv_error: null });

          // Notify recorder page
          chrome.runtime.sendMessage({ action: 'PROCESSING_COMPLETE', data: result });
        } catch (err) {
          const config = await chrome.storage.sync.get(['apiUrl']);
          const apiUrl = config.apiUrl || 'http://localhost:8002';
          let errorMsg = err.message || 'Onbekende fout';
          if (errorMsg === 'Failed to fetch') {
            errorMsg = 'Kan de API niet bereiken op: ' + apiUrl + '. Controleer de instellingen.';
          }

          await chrome.storage.local.set({ sv_state: 'error', sv_error: errorMsg });
          chrome.runtime.sendMessage({ action: 'PROCESSING_ERROR', error: errorMsg });
        }
      })();
      sendResponse({ received: true });
      return false;
  }
});
