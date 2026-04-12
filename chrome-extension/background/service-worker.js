/**
 * SmartVoice - Service Worker (simplified)
 *
 * The heavy lifting (recording, API calls, display) now happens
 * in the Bricks content script widget. The service worker only:
 * 1. Responds to GET_STATE for popup init
 * 2. Handles PUSH_TO_BRICKS from popup
 * 3. Stores/retrieves state from chrome.storage.local
 */

// ── Message handler ──

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  switch (msg.action) {

    case 'GET_STATE':
      // Popup asks for current state — read from storage
      chrome.storage.local.get(['sv_state', 'sv_data', 'sv_error'], (stored) => {
        sendResponse({
          state: stored.sv_state || 'idle',
          data: stored.sv_data || null,
          error: stored.sv_error || null,
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
  }
});
