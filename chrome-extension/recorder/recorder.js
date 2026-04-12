/**
 * SmartVoice - Recorder Page Controller
 * Handles microphone recording, waveform visualization, and sending audio to the service worker.
 */

var mediaRecorder = null;
var audioChunks = [];
var audioStream = null;
var timerInterval = null;
var startTime = null;
var waveformId = null;

var btnStart = document.getElementById('btn-start');
var btnStop = document.getElementById('btn-stop');

function showState(name) {
  ['idle', 'recording', 'processing', 'done'].forEach(function(s) {
    document.getElementById(s + '-state').classList.toggle('hidden', s !== name);
  });
}

function showError(msg) {
  var el = document.getElementById('error-msg');
  el.textContent = msg;
  el.classList.remove('hidden');
}

function updateTimer() {
  var elapsed = Math.floor((Date.now() - startTime) / 1000);
  var mins = String(Math.floor(elapsed / 60)).padStart(2, '0');
  var secs = String(elapsed % 60).padStart(2, '0');
  document.getElementById('timer').textContent = mins + ':' + secs;
}

function startWaveform() {
  var canvas = document.getElementById('waveform');
  var ctx = canvas.getContext('2d');
  var bars = 40;
  var barWidth = canvas.width / bars - 2;
  function draw() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = '#059669';
    for (var i = 0; i < bars; i++) {
      var height = Math.random() * canvas.height * 0.8 + canvas.height * 0.1;
      var x = i * (barWidth + 2);
      var y = (canvas.height - height) / 2;
      ctx.fillRect(x, y, barWidth, height);
    }
    waveformId = requestAnimationFrame(draw);
  }
  draw();
}

btnStart.addEventListener('click', async function() {
  try {
    audioStream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, sampleRate: 16000, echoCancellation: true, noiseSuppression: true, autoGainControl: true }
    });

    audioChunks = [];
    var mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
      ? 'audio/webm;codecs=opus' : 'audio/webm';

    mediaRecorder = new MediaRecorder(audioStream, { mimeType: mimeType, audioBitsPerSecond: 128000 });

    mediaRecorder.ondataavailable = function(e) {
      if (e.data && e.data.size > 0) {
        audioChunks.push(e.data);
        document.getElementById('status').textContent = 'Chunks: ' + audioChunks.length + ' (' + Math.round(e.data.size/1024) + ' KB)';
      }
    };

    // Set onstop handler BEFORE starting (avoids race condition)
    mediaRecorder.onstop = function() {
      var mimeType = mediaRecorder ? mediaRecorder.mimeType : 'audio/webm';
      var blob = new Blob(audioChunks, { type: mimeType });

      document.getElementById('processing-step').textContent =
        'Audio: ' + Math.round(blob.size / 1024) + ' KB, ' + audioChunks.length + ' chunks. Verzenden...';

      if (blob.size < 1000) {
        showState('idle');
        showError('Opname te kort of leeg (' + blob.size + ' bytes). Probeer langer op te nemen.');
        return;
      }

      // Convert to base64
      var reader = new FileReader();
      reader.onloadend = function() {
        var base64 = reader.result.split(',')[1];

        chrome.runtime.sendMessage({
          action: 'RECORDER_AUDIO',
          audio: base64,
          mimeType: mimeType,
          size: blob.size,
        });

        document.getElementById('processing-step').textContent =
          'Audio verzonden (' + Math.round(blob.size / 1024) + ' KB). Wachten op API...';
      };
      reader.readAsDataURL(blob);

      // Clean up mic
      if (audioStream) {
        audioStream.getTracks().forEach(function(t) { t.stop(); });
        audioStream = null;
      }
    };

    // Start without timeslice — one big chunk on stop (most reliable)
    mediaRecorder.start();
    startTime = Date.now();
    timerInterval = setInterval(updateTimer, 1000);
    showState('recording');
    startWaveform();

    chrome.runtime.sendMessage({ action: 'RECORDER_STARTED' });

  } catch (err) {
    showError('Microfoon niet beschikbaar: ' + err.message);
  }
});

btnStop.addEventListener('click', function() {
  if (timerInterval) clearInterval(timerInterval);
  if (waveformId) cancelAnimationFrame(waveformId);
  showState('processing');
  document.getElementById('processing-step').textContent = 'Audio wordt samengevoegd...';

  if (mediaRecorder && mediaRecorder.state !== 'inactive') {
    mediaRecorder.stop();
  } else {
    showState('idle');
    showError('Geen actieve opname gevonden.');
  }
});

// Listen for updates from service worker
chrome.runtime.onMessage.addListener(function(msg) {
  if (msg.action === 'PROCESSING_UPDATE') {
    document.getElementById('processing-step').textContent = msg.step || 'Verwerken...';
  }
  if (msg.action === 'PROCESSING_COMPLETE') {
    showState('done');
  }
  if (msg.action === 'PROCESSING_ERROR') {
    showState('idle');
    showError(msg.error || 'Er is een fout opgetreden.');
  }
});
