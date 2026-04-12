/**
 * SmartVoice — Service Worker (Background)
 * Beheert opname-lifecycle, API-communicatie, en Bricks-push.
 */

// ─── State ───────────────────────────────────────────────────────────────────

let state = {
  isRecording: false,
  isProcessing: false,
  startTime: 0,
  result: null,
  audioBlob: null,
};

// ─── Settings helpers ────────────────────────────────────────────────────────

async function getSettings() {
  const defaults = {
    apiUrl: "http://localhost:8002",
    apiKey: "",
    sttProvider: "groq",
    llmProvider: "mistral",
  };
  const stored = await chrome.storage.sync.get(defaults);
  return { ...defaults, ...stored };
}

// ─── Message handler ─────────────────────────────────────────────────────────

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  handleMessage(msg, sender).then(sendResponse).catch((err) => {
    console.error("Service worker message error:", err);
    sendResponse({ error: err.message });
  });
  return true; // keep channel open for async response
});

async function handleMessage(msg, sender) {
  switch (msg.type) {
    case "GET_STATE":
      return { ...state, audioBlob: undefined };

    case "START_RECORDING":
      return await startRecording();

    case "STOP_RECORDING":
      return await stopRecording();

    case "RECORDING_DATA":
      // Received audio blob from offscreen document
      state.audioBlob = msg.blob;
      return await processAudio();

    case "PUSH_TO_BRICKS":
      return await pushToBricks(msg.data);

    case "RESET":
      state = { isRecording: false, isProcessing: false, startTime: 0, result: null, audioBlob: null };
      return { ok: true };

    default:
      return { error: "Unknown message type" };
  }
}

// ─── Recording via Offscreen Document ────────────────────────────────────────

async function startRecording() {
  // Create offscreen document for audio recording
  const existingContexts = await chrome.runtime.getContexts({
    contextTypes: ["OFFSCREEN_DOCUMENT"],
  });

  if (existingContexts.length === 0) {
    await chrome.offscreen.createDocument({
      url: "offscreen/offscreen.html",
      reasons: ["USER_MEDIA"],
      justification: "Audio opname voor consultatie-transcriptie",
    });
  }

  // Tell offscreen doc to start recording
  await chrome.runtime.sendMessage({ type: "OFFSCREEN_START_RECORDING" });

  state.isRecording = true;
  state.startTime = Date.now();
  state.result = null;
  state.audioBlob = null;

  return { ok: true, startTime: state.startTime };
}

async function stopRecording() {
  state.isRecording = false;
  state.isProcessing = true;

  // Tell offscreen doc to stop — it will send RECORDING_DATA back
  await chrome.runtime.sendMessage({ type: "OFFSCREEN_STOP_RECORDING" });

  return { ok: true };
}

// ─── API Communication ──────────────────────────────────────────────────────

async function processAudio() {
  if (!state.audioBlob) {
    broadcastError("Geen audio-data ontvangen");
    return;
  }

  state.isProcessing = true;
  broadcastUpdate("Audio uploaden naar API...");

  try {
    const settings = await getSettings();
    const formData = new FormData();

    // Convert base64 back to blob if needed
    let blob = state.audioBlob;
    if (typeof blob === "string") {
      const response = await fetch(blob);
      blob = await response.blob();
    }

    formData.append("audio", blob, "consult.webm");
    formData.append("stt_provider", settings.sttProvider);
    formData.append("llm_provider", settings.llmProvider);

    broadcastUpdate("Audio wordt getranscribeerd...");

    const apiUrl = settings.apiUrl.replace(/\/$/, "");
    const resp = await fetch(`${apiUrl}/api/v1/consult/process`, {
      method: "POST",
      headers: {
        "X-API-Key": settings.apiKey,
      },
      body: formData,
    });

    if (!resp.ok) {
      const errBody = await resp.text();
      throw new Error(`API fout (${resp.status}): ${errBody}`);
    }

    const data = await resp.json();

    state.isProcessing = false;
    state.result = data;

    // Notify popup
    chrome.runtime.sendMessage({ type: "RESULT", data });

    // Clean up offscreen document
    try {
      await chrome.offscreen.closeDocument();
    } catch (_) {
      // already closed
    }

    return data;
  } catch (err) {
    state.isProcessing = false;
    broadcastError(err.message);
    throw err;
  }
}

// ─── Bricks Push ─────────────────────────────────────────────────────────────

async function pushToBricks(data) {
  // Find the active Bricks tab
  const tabs = await chrome.tabs.query({
    url: ["https://*.bfrcloud.com/*", "https://*.bfrnet.nl/*", "https://*.bricks-huisarts.nl/*"],
  });

  if (tabs.length === 0) {
    broadcastError("Geen Bricks-tab gevonden. Open Bricks eerst.");
    return { ok: false, error: "Geen Bricks-tab" };
  }

  // Send data to the content script in the Bricks tab
  const result = await chrome.tabs.sendMessage(tabs[0].id, {
    type: "INJECT_SOEP",
    data: data,
  });

  return result;
}

// ─── Broadcast helpers ───────────────────────────────────────────────────────

function broadcastUpdate(step) {
  chrome.runtime.sendMessage({ type: "PROCESSING_UPDATE", step }).catch(() => {});
}

function broadcastError(message) {
  chrome.runtime.sendMessage({ type: "ERROR", message }).catch(() => {});
}
