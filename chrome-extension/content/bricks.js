/**
 * SmartVoice — Bricks Content Script
 * Detecteert het Bricks HIS journaalscherm en injecteert SOEP-data.
 *
 * Bricks (BFRCloud) gebruikt een web-based interface. De exacte selectors
 * kunnen variëren per versie. Dit script probeert meerdere selector-patronen
 * en valt terug op een floating widget als injectie niet lukt.
 */

(() => {
  "use strict";

  // ─── Default selectors (configureerbaar via options) ─────────────────────

  const DEFAULT_SELECTORS = {
    // Journaalveld (hoofdtekstveld voor SOEP in Bricks)
    journaal: [
      'textarea[name*="journaal"]',
      'textarea[name*="soep"]',
      'textarea[data-field*="journaal"]',
      ".journaal-editor textarea",
      ".journal-entry textarea",
      '[class*="journaal"] textarea',
      '[class*="journal"] textarea',
      // Fallback: eerste grote textarea op de pagina
      "textarea.form-control",
    ],
    // Aparte S/O/E/P velden (als Bricks die heeft)
    s_field: ['textarea[name*="subjectief"]', '[data-soep="S"] textarea'],
    o_field: ['textarea[name*="objectief"]', '[data-soep="O"] textarea'],
    e_field: ['textarea[name*="evaluatie"]', '[data-soep="E"] textarea'],
    p_field: ['textarea[name*="plan"]', '[data-soep="P"] textarea'],
    // ICPC code veld
    icpc: ['input[name*="icpc"]', '[data-field*="icpc"] input', ".icpc-selector input"],
  };

  let selectors = { ...DEFAULT_SELECTORS };
  let widgetEl = null;
  let lastResult = null;

  // ─── Load custom selectors from storage ──────────────────────────────────

  chrome.storage.sync.get({ bricksSelectors: null }, (data) => {
    if (data.bricksSelectors) {
      try {
        const custom = JSON.parse(data.bricksSelectors);
        selectors = { ...DEFAULT_SELECTORS, ...custom };
      } catch (_) {
        // use defaults
      }
    }
  });

  // ─── Listen for INJECT_SOEP from service worker ──────────────────────────

  chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (msg.type === "INJECT_SOEP") {
      lastResult = msg.data;
      const success = injectSOEP(msg.data);
      sendResponse({ ok: success });

      if (!success) {
        showWidget(msg.data);
      }
    }
    return true;
  });

  // ─── SOEP Injection ──────────────────────────────────────────────────────

  function injectSOEP(data) {
    const soep = data.soep || {};

    // Strategie 1: Probeer aparte S/O/E/P velden
    const sField = findElement(selectors.s_field);
    const oField = findElement(selectors.o_field);
    const eField = findElement(selectors.e_field);
    const pField = findElement(selectors.p_field);

    if (sField && oField && eField && pField) {
      setFieldValue(sField, soep.S || "");
      setFieldValue(oField, soep.O || "");
      setFieldValue(eField, soep.E || "");
      setFieldValue(pField, soep.P || "");
      injectICPC(soep.icpc_code);
      showNotification("SOEP ingevuld in aparte velden");
      return true;
    }

    // Strategie 2: Probeer enkel journaalveld (SOEP als tekst)
    const journaal = findElement(selectors.journaal);
    if (journaal) {
      const formatted = formatSOEPText(soep, data.decisief_regel);
      setFieldValue(journaal, formatted);
      injectICPC(soep.icpc_code);
      showNotification("SOEP ingevuld in journaalveld");
      return true;
    }

    // Geen velden gevonden
    console.warn("[SmartVoice] Geen Bricks journaalvelden gevonden");
    return false;
  }

  function formatSOEPText(soep, decisief) {
    const parts = [];
    if (decisief) {
      parts.push(`[Decisief] ${decisief}`);
      parts.push("");
    }
    if (soep.S) parts.push(`S: ${soep.S}`);
    if (soep.O) parts.push(`O: ${soep.O}`);
    if (soep.E) parts.push(`E: ${soep.E}`);
    if (soep.P) parts.push(`P: ${soep.P}`);
    if (soep.icpc_code) {
      parts.push("");
      parts.push(`ICPC: ${soep.icpc_code}${soep.icpc_titel ? " — " + soep.icpc_titel : ""}`);
    }
    return parts.join("\n");
  }

  function injectICPC(code) {
    if (!code) return;
    const icpcField = findElement(selectors.icpc);
    if (icpcField) {
      setFieldValue(icpcField, code);
    }
  }

  // ─── DOM helpers ─────────────────────────────────────────────────────────

  function findElement(selectorList) {
    if (!Array.isArray(selectorList)) selectorList = [selectorList];
    for (const sel of selectorList) {
      const el = document.querySelector(sel);
      if (el) return el;
    }
    return null;
  }

  function setFieldValue(el, value) {
    // Trigger React/Angular change detection
    const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
      window.HTMLTextAreaElement.prototype,
      "value"
    )?.set || Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype,
      "value"
    )?.set;

    if (nativeInputValueSetter) {
      nativeInputValueSetter.call(el, value);
    } else {
      el.value = value;
    }

    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    el.dispatchEvent(new Event("blur", { bubbles: true }));
  }

  // ─── Floating Widget (fallback) ──────────────────────────────────────────

  function showWidget(data) {
    removeWidget();

    const soep = data.soep || {};
    widgetEl = document.createElement("div");
    widgetEl.id = "smartvoice-widget";
    widgetEl.innerHTML = `
      <div class="sv-widget-header">
        <span class="sv-widget-title">SmartVoice</span>
        <button class="sv-widget-close" title="Sluiten">&times;</button>
      </div>
      <div class="sv-widget-body">
        ${data.decisief_regel ? `<div class="sv-decisief">${escapeHtml(data.decisief_regel)}</div>` : ""}
        <div class="sv-soep-row"><span class="sv-badge sv-s">S</span><span>${escapeHtml(soep.S || "-")}</span></div>
        <div class="sv-soep-row"><span class="sv-badge sv-o">O</span><span>${escapeHtml(soep.O || "-")}</span></div>
        <div class="sv-soep-row"><span class="sv-badge sv-e">E</span><span>${escapeHtml(soep.E || "-")}</span></div>
        <div class="sv-soep-row"><span class="sv-badge sv-p">P</span><span>${escapeHtml(soep.P || "-")}</span></div>
        <div class="sv-widget-actions">
          <button class="sv-btn sv-btn-copy">Kopieer SOEP</button>
        </div>
      </div>
    `;

    document.body.appendChild(widgetEl);

    // Event listeners
    widgetEl.querySelector(".sv-widget-close").addEventListener("click", removeWidget);
    widgetEl.querySelector(".sv-btn-copy").addEventListener("click", () => {
      const text = formatSOEPText(soep, data.decisief_regel);
      navigator.clipboard.writeText(text);
      const btn = widgetEl.querySelector(".sv-btn-copy");
      btn.textContent = "Gekopieerd!";
      setTimeout(() => (btn.textContent = "Kopieer SOEP"), 1500);
    });

    // Make draggable
    makeDraggable(widgetEl, widgetEl.querySelector(".sv-widget-header"));
  }

  function removeWidget() {
    if (widgetEl) {
      widgetEl.remove();
      widgetEl = null;
    }
  }

  function makeDraggable(el, handle) {
    let offsetX = 0, offsetY = 0;
    handle.style.cursor = "move";

    handle.addEventListener("mousedown", (e) => {
      offsetX = e.clientX - el.getBoundingClientRect().left;
      offsetY = e.clientY - el.getBoundingClientRect().top;

      function onMove(e) {
        el.style.left = (e.clientX - offsetX) + "px";
        el.style.top = (e.clientY - offsetY) + "px";
        el.style.right = "auto";
        el.style.bottom = "auto";
      }
      function onUp() {
        document.removeEventListener("mousemove", onMove);
        document.removeEventListener("mouseup", onUp);
      }
      document.addEventListener("mousemove", onMove);
      document.addEventListener("mouseup", onUp);
    });
  }

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  // ─── Notification ────────────────────────────────────────────────────────

  function showNotification(text) {
    const notif = document.createElement("div");
    notif.className = "sv-notification";
    notif.textContent = text;
    document.body.appendChild(notif);
    setTimeout(() => {
      notif.classList.add("sv-notification-hide");
      setTimeout(() => notif.remove(), 300);
    }, 2500);
  }
})();
