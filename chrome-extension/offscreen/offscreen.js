/**
 * SmartVoice — Offscreen Document
 * Persistente audio-opname via MediaRecorder.
 * Draait door ook als popup wordt gesloten.
 */

let mediaRecorder = null;
let audioChunks = [];
let stream = null;

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === "OFFSCREEN_START_RECORDING") {
    startRecording().then(() => sendResponse({ ok: true })).catch((err) => sendResponse({ error: err.message }));
    return true;
  }
  if (msg.type === "OFFSCREEN_STOP_RECORDING") {
    stopRecording().then(() => sendResponse({ ok: true })).catch((err) => sendResponse({ error: err.message }));
    return true;
  }
});

async function startRecording() {
  audioChunks = [];

  stream = await navigator.mediaDevices.getUserMedia({
    audio: {
      channelCount: 1,
      sampleRate: 16000,
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
    },
  });

  // Prefer webm/opus for good compression + quality
  const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
    ? "audio/webm;codecs=opus"
    : "audio/webm";

  mediaRecorder = new MediaRecorder(stream, {
    mimeType,
    audioBitsPerSecond: 64000,
  });

  mediaRecorder.ondataavailable = (event) => {
    if (event.data.size > 0) {
      audioChunks.push(event.data);
    }
  };

  mediaRecorder.onstop = async () => {
    const blob = new Blob(audioChunks, { type: mimeType });

    // Convert to base64 data URL for transfer to service worker
    const reader = new FileReader();
    reader.onloadend = () => {
      chrome.runtime.sendMessage({
        type: "RECORDING_DATA",
        blob: reader.result,
      });
    };
    reader.readAsDataURL(blob);

    // Clean up stream
    if (stream) {
      stream.getTracks().forEach((track) => track.stop());
      stream = null;
    }
  };

  mediaRecorder.start(1000); // Chunk every second
  console.log("[SmartVoice] Recording started");
}

async function stopRecording() {
  if (mediaRecorder && mediaRecorder.state !== "inactive") {
    mediaRecorder.stop();
    console.log("[SmartVoice] Recording stopped");
  }
}
