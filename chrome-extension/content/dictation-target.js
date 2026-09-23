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
    var newTarget = el.isContentEditable ? editableRoot(el) : el;
    // Refocusing the same field (also done by our own inserts) keeps the
    // provisional text; it is still reported so another tab can't steal it.
    if (newTarget !== target) {
      target = newTarget;
      savedRange = null;
      prov = null;
    }
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

  // ── Provisional (interim) text ──
  // While the doctor speaks, the recognizer's interim guess is shown in the
  // field right away and rewritten in place; the final text replaces it.
  // prov: { el, prefix, text, start } for input/textarea,
  //       { el, prefix, text, node } for rich-text (contenteditable).
  var prov = null;

  function provStillThere() {
    if (!prov || prov.el !== target || !target.isConnected) return false;
    if (prov.node) return prov.node.isConnected && prov.node.data === prov.text;
    return target.value.substr(prov.start, prov.text.length) === prov.text;
  }

  function caretAfter(node) {
    var sel = window.getSelection();
    var r = document.createRange();
    r.setStartAfter(node);
    r.collapse(true);
    sel.removeAllRanges();
    sel.addRange(r);
    savedRange = r.cloneRange();
  }

  function startProvisional(text) {
    var prefix = withSpacing(target, text).slice(0, -text.length || undefined);
    if (text === '') prefix = '';
    var full = prefix + text;
    if (target.isContentEditable) {
      target.focus();
      var sel = window.getSelection();
      var range;
      if (savedRange) {
        range = savedRange.cloneRange();
      } else {
        range = document.createRange();
        range.selectNodeContents(target);
        range.collapse(false);
      }
      range.deleteContents();
      var node = document.createTextNode(full);
      range.insertNode(node);
      caretAfter(node);
      target.dispatchEvent(new Event('input', { bubbles: true }));
      prov = { el: target, prefix: prefix, text: full, node: node };
    } else {
      var start = target.selectionStart == null ? target.value.length : target.selectionStart;
      insertIntoField(target, full);
      prov = { el: target, prefix: prefix, text: full, start: start };
    }
  }

  function rewriteProvisional(full) {
    if (full === prov.text) return;
    if (prov.node) {
      if (full.indexOf('\n') === -1) {
        prov.node.data = full;
        caretAfter(prov.node);
      } else {
        // Line breaks in rich text need <br> elements.
        var frag = document.createDocumentFragment();
        var last = null;
        full.split('\n').forEach(function (part, i) {
          if (i > 0) { last = document.createElement('br'); frag.appendChild(last); }
          if (part) { last = document.createTextNode(part); frag.appendChild(last); }
        });
        var anchor = last;
        prov.node.replaceWith(frag);
        if (anchor) caretAfter(anchor);
        prov.node = null;
      }
      target.dispatchEvent(new Event('input', { bubbles: true }));
    } else {
      var el = target;
      el.focus();
      el.setSelectionRange(prov.start, prov.start + prov.text.length);
      var before = el.value;
      var ok = false;
      try { ok = document.execCommand('insertText', false, full); } catch (e) { ok = false; }
      if (!ok || el.value === before) {
        el.setRangeText(full, prov.start, prov.start + prov.text.length, 'end');
        el.dispatchEvent(new Event('input', { bubbles: true }));
      }
    }
    prov.text = full;
  }

  function prefixFor(text) {
    return /^[\s.,;:!?)]/.test(text) ? '' : prov.prefix;
  }

  chrome.runtime.onMessage.addListener(function (msg, _sender, sendResponse) {
    if (msg.action !== 'SV_INSERT_TEXT' && msg.action !== 'SV_PROVISIONAL') return false;
    if (!target || !target.isConnected) {
      prov = null;
      sendResponse({ ok: false, error: 'Het gekozen veld bestaat niet meer. Klik opnieuw in een veld.' });
      return false;
    }
    // If the doctor edited around the provisional text, stop tracking it.
    if (prov && !provStillThere()) prov = null;

    if (msg.action === 'SV_PROVISIONAL') {
      if (prov) rewriteProvisional(prefixFor(msg.text) + msg.text);
      else if (msg.text) startProvisional(msg.text);
      sendResponse({ ok: true });
      return false;
    }

    // Final text: replace the provisional guess, or insert normally.
    if (prov) {
      rewriteProvisional(prefixFor(msg.text) + msg.text);
      prov = null;
    } else {
      var text = msg.raw ? msg.text : withSpacing(target, msg.text);
      if (target.isContentEditable) insertIntoEditable(target, text);
      else insertIntoField(target, text);
    }
    sendResponse({ ok: true });
    return false;
  });

  // ── Field mapping: remember the S/O/E/P fields by pointing at them ──
  // A descriptor locates a field again later: the frame's origin plus a CSS
  // selector per shadow-DOM level (host selectors, then the field itself).

  var calibrating = false;

  function quoteAttr(v) {
    return '"' + String(v).replace(/\\/g, '\\\\').replace(/"/g, '\\"') + '"';
  }

  function uniqueIn(root, sel) {
    try { return root.querySelectorAll(sel).length === 1; } catch (e) { return false; }
  }

  function selectorWithin(el, root) {
    var tag = el.tagName.toLowerCase();
    // Ids with long digit runs are usually generated per page load.
    if (el.id && !/\d{4,}/.test(el.id) && uniqueIn(root, '#' + CSS.escape(el.id))) return '#' + CSS.escape(el.id);
    var attrs = ['name', 'aria-label', 'placeholder', 'formcontrolname', 'data-field', 'data-testid', 'title'];
    for (var i = 0; i < attrs.length; i++) {
      var v = el.getAttribute(attrs[i]);
      if (!v) continue;
      var sel = tag + '[' + attrs[i] + '=' + quoteAttr(v) + ']';
      if (uniqueIn(root, sel)) return sel;
    }
    // Stable-looking class names (no generated hashes or numbers).
    var classes = Array.prototype.filter.call(el.classList || [], function (c) {
      return /^[a-zA-Z][\w-]*$/.test(c) && !/\d/.test(c) && c.length < 40;
    });
    if (classes.length) {
      var csel = tag + '.' + classes.map(function (c) { return CSS.escape(c); }).join('.');
      if (uniqueIn(root, csel)) return csel;
    }
    // Structural path up to the root (or an ancestor with a stable id).
    var parts = [];
    var node = el;
    while (node && node.nodeType === 1 && node !== root) {
      if (node !== el && node.id && !/\d{4,}/.test(node.id) && uniqueIn(root, '#' + CSS.escape(node.id))) {
        parts.unshift('#' + CSS.escape(node.id));
        break;
      }
      var n = 1;
      var sib = node;
      while ((sib = sib.previousElementSibling)) if (sib.tagName === node.tagName) n++;
      parts.unshift(node.tagName.toLowerCase() + ':nth-of-type(' + n + ')');
      node = node.parentElement;
    }
    return parts.join(' > ');
  }

  function buildDescriptor(el) {
    var chain = [];
    var node = el;
    while (node) {
      var root = node.getRootNode();
      chain.unshift(selectorWithin(node, root));
      node = root instanceof ShadowRoot ? root.host : null;
    }
    return { origin: location.origin, chain: chain, label: describe(el) };
  }

  function resolveDescriptor(desc) {
    if (!desc || desc.origin !== location.origin) return null;
    var root = document;
    var el = null;
    for (var i = 0; i < desc.chain.length; i++) {
      try { el = root.querySelector(desc.chain[i]); } catch (e) { return null; }
      if (!el) return null;
      if (i < desc.chain.length - 1) {
        root = el.shadowRoot;
        if (!root) return null;
      }
    }
    return el && isEditable(el) ? el : null;
  }

  function appendToField(el, text) {
    // Fill at the end of the field, keeping what is already there.
    target = el.isContentEditable ? editableRoot(el) : el;
    prov = null;
    savedRange = null;
    if (target.isContentEditable) {
      insertIntoEditable(target, withSpacing(target, text));
    } else {
      target.focus();
      var end = target.value.length;
      target.setSelectionRange(end, end);
      insertIntoField(target, withSpacing(target, text));
    }
  }

  document.addEventListener('focusin', function (e) {
    if (!calibrating) return;
    var path = e.composedPath ? e.composedPath() : [];
    var el = path.length ? path[0] : e.target;
    if (!isEditable(el)) return;
    el = el.isContentEditable ? editableRoot(el) : el;
    try {
      chrome.runtime.sendMessage({ action: 'SV_CALIBRATE_PICK', desc: buildDescriptor(el) });
    } catch (err) { /* extension reloaded */ }
  }, true);

  chrome.runtime.onMessage.addListener(function (msg, _sender, sendResponse) {
    if (msg.action === 'SV_CALIBRATE') {
      calibrating = !!msg.active;
      return false;
    }
    if (msg.action !== 'SV_FILL_SOEP') return false;
    var filled = [];
    Object.keys(msg.values || {}).forEach(function (key) {
      var value = msg.values[key];
      var el = value ? resolveDescriptor((msg.mapping || {})[key]) : null;
      if (!el) return;
      appendToField(el, value);
      filled.push(key);
    });
    if (filled.length) {
      try { chrome.runtime.sendMessage({ action: 'SV_FILL_REPORT', requestId: msg.requestId, filled: filled }); }
      catch (err) { /* ignore */ }
    }
    sendResponse({ ok: true });
    return false;
  });

  // ── Status pill (top frame only) ──

  if (window.top !== window) return;

  var pill = null;
  var pillText = null;
  var pillLabel = null;
  var hideTimer = null;
  var pillButton = null;

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
      '.p.cal .d{background:#0ea5e9;animation:none}.p.ok .d{background:#10b981;animation:none}' +
      '.p.cal .t,.p.ok .t{font-style:normal;color:#fff}.p.cal button{background:#475569}.p.ok button{display:none}' +
      '.p.ok{border-radius:12px;align-items:flex-start}.p.ok .d{margin-top:4px}.p.ok .t{white-space:normal}' +
      'button{margin-left:4px;border:0;border-radius:999px;padding:4px 10px;background:#dc2626;color:#fff;' +
      'font:inherit;font-weight:600;cursor:pointer}.p.err button,.p.busy button{display:none}' +
      '</style>' +
      '<div class="p"><span class="d"></span><span class="l"></span><span class="t"></span>' +
      '<button type="button" title="Stoppen (Alt+Shift+D)">Stop</button></div>';
    pill = shadow.querySelector('.p');
    pillLabel = shadow.querySelector('.l');
    pillText = shadow.querySelector('.t');
    pillButton = shadow.querySelector('button');
    pillButton.addEventListener('click', function () {
      chrome.runtime.sendMessage({ action: pillButton.dataset.action || 'SV_QUICK_TOGGLE' });
    });
    document.documentElement.appendChild(host);
    pill.__host = host;
  }

  function showPill(state, text, button) {
    if (!pill) buildPill();
    clearTimeout(hideTimer);
    pill.__host.style.display = '';
    pill.className = 'p' + ({ error: ' err', listening: '', calibrate: ' cal', info: ' ok' }[state] || ' busy');
    pillLabel.textContent = {
      connecting: 'SmartVoice verbindt…',
      listening: 'SmartVoice luistert',
      stopping: 'Afronden…',
      calibrate: 'Velden koppelen',
    }[state] || 'SmartVoice';
    pillText.textContent = text || '';
    pillButton.textContent = (button && button.label) || 'Stop';
    pillButton.dataset.action = (button && button.action) || 'SV_QUICK_TOGGLE';
    if (state === 'error' || state === 'info') hideTimer = setTimeout(hidePill, 6000);
  }

  function hidePill() {
    if (pill) pill.__host.style.display = 'none';
  }

  chrome.runtime.onMessage.addListener(function (msg) {
    if (msg.action !== 'SV_PILL') return false;
    if (msg.state === 'idle') hidePill();
    else showPill(msg.state, msg.text, msg.button);
    return false;
  });
})();
