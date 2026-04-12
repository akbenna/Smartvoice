/**
 * SmartVoice — Options Page Controller
 */

const FIELDS = ["apiUrl", "apiKey", "sttProvider", "llmProvider", "bricksSelectors"];
const DEFAULTS = {
  apiUrl: "http://localhost:8002",
  apiKey: "",
  sttProvider: "groq",
  llmProvider: "mistral",
  bricksSelectors: "",
};

// Load saved settings
document.addEventListener("DOMContentLoaded", () => {
  chrome.storage.sync.get(DEFAULTS, (data) => {
    for (const field of FIELDS) {
      const el = document.getElementById(field);
      if (el) el.value = data[field] || DEFAULTS[field];
    }
  });
});

// Save
document.getElementById("btnSave").addEventListener("click", () => {
  const values = {};
  for (const field of FIELDS) {
    const el = document.getElementById(field);
    if (el) values[field] = el.value.trim();
  }

  // Validate JSON if provided
  if (values.bricksSelectors) {
    try {
      JSON.parse(values.bricksSelectors);
    } catch (e) {
      alert("Ongeldige JSON in Bricks Selectors. Controleer de syntax.");
      return;
    }
  }

  chrome.storage.sync.set(values, () => {
    const msg = document.getElementById("savedMsg");
    msg.style.display = "inline";
    setTimeout(() => (msg.style.display = "none"), 2000);
  });
});
