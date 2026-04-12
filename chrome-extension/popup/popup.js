/**
 * SmartVoice Chrome Extension — Popup Controller
 * Beheert opname UI, communiceert met service worker en toont resultaten.
 */

const $ = (sel) => document.querySelector(sel);

// DOM refs
const statusBar = $("#status-bar");
const statusDot = $("#status-dot");
const statusText = $("#status-text");
const timer = $("#timer");
const btnRecord = $("#btn-record");
const iconMic = $("#icon-mic");
const iconStop = $("#icon-stop");
const waveformCanvas = $("#waveform-canvas");
const sectionRecord = $("#section-record");
const sectionProcessing = $("#section-processing");
const sectionResult = $("#section-result");
const sectionError = $("#section-error");

let isRecording = false;
let timerInterval = null;
let startTime = 0;
let analyserContext = null;

// ─── Init ────────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", async () => {
  // Restore state from service worker
  const state = await sendMessage({ type: "GET_STATE" });
  if (state) {
    if (state.isRecording) {
      enterRecordingState(state.startTime);
    } else if (state.isProcessing) {
      showSection("processing");
      setStatus("processing", "Verwerking bezig...");
    } else if (state.result) {
      showResult(state.result);
    }
  }

  // Listen for state updates
  chrome.runtime.onMessage.addListener((msg) => {
    if (msg.type === "PROCESSING_UPDATE") {
      $("#processing-step").textContent = msg.step;
    }
    if (msg.type === "RESULT") {
      showResult(msg.data);
    }
    if (msg.type === "ERROR") {
      showError(msg.message);
    }
  });
});

// ─── Record button ───────────────────────────────────────────────────────────

btnRecord.addEventListener("click", async () => {
  if (isRecording) {
    await stopRecording();
  } else {
    await startRecording();
  }
});

async function startRecording() {
  try {
    await sendMessage({ type: "START_RECORDING" });
    enterRecordingState(Date.now());
  } catch (err) {
    showError("Microfoon niet beschikbaar. Controleer de browser-permissies.");
  }
}

async function stopRecording() {
  setStatus("processing", "Opname gestopt, verwerking start...");
  await sendMessage({ type: "STOP_RECORDING" });
  isRecording = false;
  clearInterval(timerInterval);
  btnRecord.classList.remove("recording");
  iconMic.style.display = "";
  iconStop.style.display = "none";
  showSection("processing");
}

function enterRecordingState(recordStartTime) {
  isRecording = true;
  startTime = recordStartTime;
  btnRecord.classList.add("recording");
  iconMic.style.display = "none";
  iconStop.style.display = "";
  setStatus("recording", "Opname actief");
  showSection("record");

  // Timer
  clearInterval(timerInterval);
  timerInterval = setInterval(() => {
    const elapsed = Math.floor((Date.now() - startTime) / 1000);
    const min = String(Math.floor(elapsed / 60)).padStart(2, "0");
    const sec = String(elapsed % 60).padStart(2, "0");
    timer.textContent = `${min}:${sec}`;
  }, 200);

  // Simple waveform animation
  startWaveformAnimation();
}

// ─── Result display ──────────────────────────────────────────────────────────

function showResult(data) {
  setStatus("done", "Consult verwerkt");
  showSection("result");

  // Decisief regel
  $("#decisief-text").textContent = data.decisief_regel || "Geen decisief regel gegenereerd";

  // SOEP
  const soep = data.soep || {};
  $("#soep-s").textContent = soep.S || "-";
  $("#soep-o").textContent = soep.O || "-";
  $("#soep-e").textContent = soep.E || "-";
  $("#soep-p").textContent = soep.P || "-";

  // Red flags
  const flags = data.rode_vlaggen || [];
  const flagsContainer = $("#red-flags-container");
  const flagsList = $("#red-flags-list");
  flagsList.innerHTML = "";
  if (flags.length > 0) {
    flagsContainer.style.display = "";
    flags.forEach((f) => {
      const div = document.createElement("div");
      div.className = "flag-item";
      div.textContent = typeof f === "string" ? f : f.beschrijving || JSON.stringify(f);
      flagsList.appendChild(div);
    });
  } else {
    flagsContainer.style.display = "none";
  }
}

// ─── Action buttons ──────────────────────────────────────────────────────────

$("#btn-copy-decisief").addEventListener("click", () => {
  const text = $("#decisief-text").textContent;
  navigator.clipboard.writeText(text);
  $("#btn-copy-decisief").textContent = "Gekopieerd!";
  setTimeout(() => ($("#btn-copy-decisief").textContent = "Kopieer"), 1500);
});

$("#btn-copy-soep").addEventListener("click", async () => {
  const state = await sendMessage({ type: "GET_STATE" });
  if (state && state.result && state.result.soep) {
    const s = state.result.soep;
    const text = `S: ${s.S}\nO: ${s.O}\nE: ${s.E}\nP: ${s.P}`;
    navigator.clipboard.writeText(text);
    $("#btn-copy-soep").textContent = "Gekopieerd!";
    setTimeout(() => ($("#btn-copy-soep").textContent = "Kopieer SOEP"), 1500);
  }
});

$("#btn-push-bricks").addEventListener("click", async () => {
  const state = await sendMessage({ type: "GET_STATE" });
  if (state && state.result) {
    await sendMessage({ type: "PUSH_TO_BRICKS", data: state.result });
    $("#btn-push-bricks").textContent = "Verstuurd!";
    setTimeout(() => ($("#btn-push-bricks").textContent = "Naar Bricks"), 1500);
  }
});

$("#btn-new").addEventListener("click", async () => {
  await sendMessage({ type: "RESET" });
  setStatus("idle", "Klaar voor opname");
  showSection("record");
  timer.textContent = "00:00";
});

$("#btn-retry").addEventListener("click", async () => {
  setStatus("idle", "Klaar voor opname");
  showSection("record");
  timer.textContent = "00:00";
});

$("#btn-settings").addEventListener("click", () => {
  chrome.runtime.openOptionsPage();
});

// ─── Helpers ─────────────────────────────────────────────────────────────────

function showSection(name) {
  sectionRecord.style.display = name === "record" ? "" : "none";
  sectionProcessing.style.display = name === "processing" ? "" : "none";
  sectionResult.style.display = name === "result" ? "" : "none";
  sectionError.style.display = name === "error" ? "" : "none";
}

function setStatus(state, text) {
  statusBar.className = `status-bar status-${state}`;
  statusText.textContent = text;
}

function showError(msg) {
  setStatus("error", "Fout opgetreden");
  showSection("error");
  $("#error-text").textContent = msg;
}

function sendMessage(msg) {
  return chrome.runtime.sendMessage(msg);
}

function startWaveformAnimation() {
  const ctx = waveformCanvas.getContext("2d");
  const w = waveformCanvas.width;
  const h = waveformCanvas.height;
  let bars = new Array(28).fill(0).map(() => Math.random() * 0.3);

  function draw() {
    if (!isRecording) return;
    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = "#1B4F72";

    bars = bars.map((v) => {
      const target = 0.1 + Math.random() * 0.8;
      return v + (target - v) * 0.15;
    });

    const barW = w / bars.length - 2;
    bars.forEach((v, i) => {
      const barH = v * h;
      const x = i * (barW + 2);
      const y = (h - barH) / 2;
      ctx.beginPath();
      ctx.roundRect(x, y, barW, barH, 2);
      ctx.fill();
    });

    requestAnimationFrame(draw);
  }
  draw();
}
