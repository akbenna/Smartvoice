/**
 * SmartVoice - Dictation target (runs in every Bricks frame)
 *
 * Remembers the text field the doctor last clicked and inserts dictated text
 * at the cursor there. The side panel decides WHICH frame to talk to: each
 * focus is reported to the service worker together with its frameId.
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
    var label = el.getAttribute('aria-label') || el.getAttribute('placeholder') || '';
    if (!label && el.id) {
      var lab = document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
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
    var el = e.target;
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
})();
