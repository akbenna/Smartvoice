/**
 * SmartVoice - Dictation target (runs in every frame of every page)
 *
 * Remembers the text field the doctor last clicked and inserts dictated text
 * at the cursor there. The side panel / service worker decides WHICH frame to
 * talk to: each focus is reported together with its frameId. Only reacts to
 * focus on text fields; page content is never read or sent anywhere.
 *
 * The top frame also shows a small status pill while dictating without the
 * side panel (Alt+Shift+D).
 */

(function () {
  if (window.__svDictationTarget) return;
  window.__svDictationTarget = true;

  var target = null;
  var savedRange = null;

  function isEditable(el) {
    if (!el || el.disabled || el.readOnly) return false;
    if (el.isContentEditable) return true;
    if (el.tagName === 'TEXTAREA') return true;
    if (el.tagName === 'INPUT') {
      var type = (el.type || 'text').toLowerCase();
      return ['text', 'search', ''].indexOf(type) !== -1;
    }
    return false;
  }

  function editableRoot(el) {
    // Rich-text editors focus a child node; insert into the editable host.
    while (el && el.parentElement && el.parentElement.isContentEditable) el = el.parentElement;
    return el;
  }

  function describe(el) {
    var label = el.getAttribute('aria-label') || el.getAttribute('placeholder') || el.getAttribute('title') || '';
    if (!label && el.id) {
      var root = el.getRootNode ? el.getRootNode() : document;
      var lab = (root.querySelector ? root : document).querySelector('label[for="' + CSS.escape(el.id) + '"]');
      if (lab) label = lab.textContent;
    }
    if (!label && el.closest('label')) label = el.closest('label').textContent;
    label = label || el.getAttribute('name') || el.id || (el.isContentEditable ? 'tekstvak' : el.tagName.toLowerCase());
    return label.replace(/\s+/g, ' ').trim().slice(0, 60);
  }

  function saveSelection() {
    if (!target || !target.isContentEditable) return;
    var sel = window.getSelection();
    if (sel && sel.rangeCount && target.contains(sel.anchorNode)) {
      savedRange = sel.getRangeAt(0).cloneRange();
    }
  }

  document.addEventListener('focusin', function (e) {
    // composedPath()[0] reaches fields inside (open) shadow DOM, which modern
    // web apps use for their editors; e.target would only be the host element.
    var path = e.composedPath ? e.composedPath() : [];
    var el = path.length ? path[0] : e.target;
    if (!isEditable(el)) return;
    target = el.isContentEditable ? editableRoot(el) : el;
    savedRange = null;
    try {
      chrome.runtime.sendMessage({ action: 'SV_TARGET_FOCUS', label: describe(target) });
    } catch (err) { /* extension reloaded; page needs refresh */ }
  }, true);

  document.addEventListener('selectionchange', saveSelection);
  document.addEventListener('keyup', saveSelection, true);
  document.addEventListener('mouseup', saveSelection, true);

  function charBeforeCursor(el) {
    if (el.isContentEditable) {
      if (!savedRange) return el.textContent.slice(-1);
      var pre = savedRange.cloneRange();
      pre.selectNodeContents(el);
      pre.setEnd(savedRange.startContainer, savedRange.startOffset);
      return pre.toString().slice(-1);
    }
    var pos = el.selectionStart == null ? el.value.length : el.selectionStart;
    return el.value.charAt(pos - 1);
  }

  function withSpacing(el, text) {
    // Glue dictated fragments together like typed text: one space between
    // words, none before punctuation or after a line break.
    var before = charBeforeCursor(el);
    if (!before || /\s/.test(before) || /^[\s.,;:!?)]/.test(text)) return text;
    return ' ' + text;
  }

  function insertIntoField(el, text) {
    el.focus();
    var start = el.selectionStart == null ? el.value.length : el.selectionStart;
    var end = el.selectionEnd == null ? start : el.selectionEnd;
    // execCommand keeps the undo stack and fires the events frameworks listen to.
    var before = el.value;
    var ok = false;
    try { ok = document.execCommand('insertText', false, text); } catch (e) { ok = false; }
    if (!ok || el.value === before) {
      el.setRangeText(text, start, end, 'end');
      el.dispatchEvent(new Event('input', { bubbles: true }));
    }
    el.dispatchEvent(new Event('change', { bubbles: true }));
  }

  function insertIntoEditable(el, text) {
    el.focus();
    var sel = window.getSelection();
    if (savedRange) {
      sel.removeAllRanges();
      sel.addRange(savedRange);
    } else {
      var r = document.createRange();
      r.selectNodeContents(el);
      r.collapse(false);
      sel.removeAllRanges();
      sel.addRange(r);
    }
    // insertText drops "\n" in rich-text fields; emit explicit line breaks.
    var parts = text.split('\n');
    var ok = true;
    try {
      parts.forEach(function (part, i) {
        if (i > 0) ok = document.execCommand('insertLineBreak') && ok;
        if (part) ok = document.execCommand('insertText', false, part) && ok;
      });
    } catch (e) { ok = false; }
    if (!ok) {
      var range = sel.getRangeAt(0);
      range.deleteContents();
      var frag = document.createDocumentFragment();
      var last = null;
      parts.forEach(function (part, i) {
        if (i > 0) frag.appendChild(document.createElement('br'));
        last = document.createTextNode(part);
        frag.appendChild(last);
      });
      range.insertNode(frag);
      range.setStartAfter(last);
      range.collapse(true);
      sel.removeAllRanges();
      sel.addRange(range);
      el.dispatchEvent(new Event('input', { bubbles: true }));
    }
    savedRange = sel.rangeCount ? sel.getRangeAt(0).cloneRange() : null;
  }

  chrome.runtime.onMessage.addListener(function (msg, _sender, sendResponse) {
    if (msg.action !== 'SV_INSERT_TEXT') return false;
    if (!target || !target.isConnected) {
      sendResponse({ ok: false, error: 'Het gekozen veld bestaat niet meer. Klik opnieuw in een veld.' });
      return false;
    }
    var text = msg.raw ? msg.text : withSpacing(target, msg.text);
    if (target.isContentEditable) insertIntoEditable(target, text);
    else insertIntoField(target, text);
    sendResponse({ ok: true });
    return false;
  });

  // ── Status pill (top frame only) ──

  if (window.top !== window) return;

  var pill = null;
  var pillText = null;
  var pillLabel = null;
  var hideTimer = null;

  function buildPill() {
    var host = document.createElement('div');
    host.style.cssText = 'position:fixed;right:16px;bottom:16px;z-index:2147483647;';
    var shadow = host.attachShadow({ mode: 'closed' });
    shadow.innerHTML =
      '<style>' +
      '.p{display:flex;align-items:center;gap:8px;max-width:420px;padding:8px 10px 8px 12px;' +
      'background:#0f172a;color:#fff;border-radius:999px;box-shadow:0 4px 14px rgba(0,0,0,.25);' +
      'font:13px/1.3 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}' +
      '.d{width:10px;height:10px;border-radius:50%;background:#dc2626;flex-shrink:0;animation:b 1.2s infinite}' +
      '.p.err .d{background:#f59e0b;animation:none}.p.busy .d{background:#94a3b8;animation:none}' +
      '@keyframes b{50%{opacity:.35}}' +
      '.l{font-weight:600;white-space:nowrap}' +
      '.t{color:#cbd5e1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-style:italic}' +
      '.p.err{border-radius:12px;align-items:flex-start}.p.err .d{margin-top:4px}' +
      '.p.err .t{white-space:normal;font-style:normal;color:#fff}' +
      'button{margin-left:4px;border:0;border-radius:999px;padding:4px 10px;background:#dc2626;color:#fff;' +
      'font:inherit;font-weight:600;cursor:pointer}.p.err button,.p.busy button{display:none}' +
      '</style>' +
      '<div class="p"><span class="d"></span><span class="l"></span><span class="t"></span>' +
      '<button type="button" title="Stoppen (Alt+Shift+D)">Stop</button></div>';
    pill = shadow.querySelector('.p');
    pillLabel = shadow.querySelector('.l');
    pillText = shadow.querySelector('.t');
    shadow.querySelector('button').addEventListener('click', function () {
      chrome.runtime.sendMessage({ action: 'SV_QUICK_TOGGLE' });
    });
    document.documentElement.appendChild(host);
    pill.__host = host;
  }

  function showPill(state, text) {
    if (!pill) buildPill();
    clearTimeout(hideTimer);
    pill.__host.style.display = '';
    pill.className = 'p' + (state === 'error' ? ' err' : state === 'listening' ? '' : ' busy');
    pillLabel.textContent = {
      connecting: 'SmartVoice verbindt…',
      listening: 'SmartVoice luistert',
      stopping: 'Afronden…',
      error: 'SmartVoice',
    }[state] || 'SmartVoice';
    pillText.textContent = text || '';
    if (state === 'error') hideTimer = setTimeout(hidePill, 6000);
  }

  function hidePill() {
    if (pill) pill.__host.style.display = 'none';
  }

  chrome.runtime.onMessage.addListener(function (msg) {
    if (msg.action !== 'SV_PILL') return false;
    if (msg.state === 'idle') hidePill();
    else showPill(msg.state, msg.text);
    return false;
  });
})();
