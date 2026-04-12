/**
 * SmartVoice - Offscreen Audio Recorder
 *
 * Runs in an offscreen document to persist audio recording even when the
 * popup is closed. Uses MediaRecorder API with noise suppression.
 */

let mediaRecorder = null;
let audioChunks = [];
let audioStream = null;

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  switch (msg.action) {
    case 'OFFSCREEN_START_RECORDING':
      startRecording().then(sendResponse).catch(err =>
        sendResponse({ error: err.message })
      );
      return true;

    case 'OFFSCREEN_STOP_RECORDING':
      stopRecording().then(sendResponse).catch(err =>
        sendResponse({ error: err.message })
      );
      return true;

    case 'OFFSCREEN_GET_STATUS':
      sendResponse({ recording: mediaRecorder?.state === 'recording' });
      return false;
  }
});

async function startRecording() {
  audioStream = await navigator.mediaDevices.getUserMedia({
    audio: {
      channelCount: 1,
      sampleRate: 16000,
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
    },
  });

  audioChunks = [];

  const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
    ? 'audio/webm;codecs=opus'
    : MediaRecorder.isTypeSupported('audio/webm')
      ? 'audio/webm'
      : 'audio/mp4';

  mediaRecorder = new MediaRecorder(audioStream, {
    mimeType,
    audioBitsPerSecond: 128000,
  });

  mediaRecorder.ondataavailable = (event) => {
    if (event.data.size > 0) {
      audioChunks.push(event.data);
    }
  };

  mediaRecorder.start(5000);
  return { success: true, mimeType };
}

async function stopRecording() {
  if (!mediaRecorder || mediaRecorder.state === 'inactive') {
    return { error: 'Geen actieve opname.' };
  }

  return new Promise((resolve) => {
    mediaRecorder.onstop = async () => {
      const mimeType = mediaRecorder.mimeType;
      const blob = new Blob(audioChunks, { type: mimeType });

      const reader = new FileReader();
      reader.onloadend = () => {
        const base64 = reader.result.split(',')[1];
        resolve({
          success: true,
          audio: base64,
          mimeType,
          size: blob.size,
          duration: audioChunks.length * 5,
        });
      };
      reader.readAsDataURL(blob);

      if (audioStream) {
        audioStream.getTracks().forEach(t => t.stop());
        audioStream = null;
      }
      mediaRecorder = null;
      audioChunks = [];
    };

    mediaRecorder.stop();
  });
}
