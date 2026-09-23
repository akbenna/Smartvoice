/**
 * SmartVoice - Text rules for dictation
 *
 * Snelteksten: a spoken trigger ("normaal longen") becomes a fixed text.
 * Correcties: a word the recognizer keeps getting wrong is replaced.
 *
 * Rules live in chrome.storage.local on this computer only; they contain the
 * doctor's own templates, never patient data. Shared by the side panel and
 * the rules page, and loadable in Node for tests.
 */

(function (root) {
  var STORAGE_KEY = 'svTextRules';
  var MAX_KEYTERMS = 50;

  // Letters/digits incl. accents; anything else counts as a word boundary.
  var WORD_CHAR = 'A-Za-z0-9\\u00C0-\\u024F';

  function escapeRegex(s) {
    return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }

  function splitTriggers(value) {
    return String(value || '')
      .split(/[,;\n]/)
      .map(function (t) { return t.trim(); })
      .filter(Boolean);
  }

  /**
   * Regex for a spoken phrase. Recognizers vary punctuation and spacing
   * ("normaal L.O.", "Normaal lo,"), so words may be separated by any run of
   * spaces or punctuation and dots inside a word are ignored.
   */
  function phrasePattern(phrase) {
    var words = phrase.toLowerCase().split(/[\s.,;:!?-]+/).filter(Boolean);
    if (!words.length) return null;
    var body = words.map(function (w) {
      return w.split('').map(escapeRegex).join('\\.?');
    }).join('[\\s.,;:!?-]+');
    return body;
  }

  function buildRegex(phrase, consumeTrailingPunct) {
    var body = phrasePattern(phrase);
    if (!body) return null;
    var tail = consumeTrailingPunct ? '[.,;:]?' : '';
    return new RegExp('(^|[^' + WORD_CHAR + '])(' + body + ')' + tail + '(?![' + WORD_CHAR + '])', 'gi');
  }

  function applyCorrections(text, corrections) {
    (corrections || []).forEach(function (c) {
      if (!c || !c.wrong || !c.right) return;
      var re = buildRegex(c.wrong, false);
      if (re) text = text.replace(re, function (_m, pre) { return pre + c.right; });
    });
    return text;
  }

  // Same normalisation the phrase pattern tolerates: case, dots inside
  // words, and any run of spaces/punctuation between words.
  function normalizePhrase(phrase) {
    return phrase.toLowerCase().replace(/\./g, '').split(/[\s,;:!?-]+/).filter(Boolean).join(' ');
  }

  function applySnippets(text, snippets) {
    // One pass over the text with all triggers at once, so the text a snippet
    // inserts is never expanded again (a template containing "gb" stays as is).
    var byKey = {};
    var bodies = [];
    (snippets || []).forEach(function (s) {
      if (!s || !s.text) return;
      splitTriggers(s.triggers).forEach(function (t) {
        var key = normalizePhrase(t);
        var body = phrasePattern(t);
        if (!key || !body || byKey[key] !== undefined) return;
        byKey[key] = s.text;
        bodies.push({ body: body, len: t.length });
      });
    });
    if (!bodies.length) return text;
    // Longest triggers first, so "normaal LO buik" wins over "normaal LO".
    bodies.sort(function (a, b) { return b.len - a.len; });
    var re = new RegExp('(^|[^' + WORD_CHAR + '])(' + bodies.map(function (b) { return b.body; }).join('|') +
      ')([.,;:]?)(?![' + WORD_CHAR + '])', 'gi');
    return text.replace(re, function (match, pre, trigger, punct) {
      var replacement = byKey[normalizePhrase(trigger)];
      if (replacement === undefined) return match;
      // Keep the dictated punctuation, except a period the snippet already ends with.
      if (punct === '.' && /[.!?]\s*$/.test(replacement)) punct = '';
      return pre + replacement + punct;
    });
  }

  function applyRules(text, rules) {
    if (!text || !rules) return text;
    return applySnippets(applyCorrections(text, rules.corrections), rules.snippets);
  }

  /** Words worth biasing the recognizer towards: triggers and corrected spellings. */
  function keyterms(rules) {
    var seen = {};
    var out = [];
    function add(term) {
      term = String(term || '').trim();
      var key = term.toLowerCase();
      if (!term || term.length > 50 || seen[key]) return;
      seen[key] = true;
      out.push(term);
    }
    ((rules && rules.corrections) || []).forEach(function (c) { add(c.right); });
    // Short codes ("vg", "gb") would pull the recognizer towards letter
    // combinations; only spoken phrases are useful hints.
    ((rules && rules.snippets) || []).forEach(function (s) {
      splitTriggers(s.triggers).forEach(function (t) { if (t.length >= 5) add(t); });
    });
    return out.slice(0, MAX_KEYTERMS);
  }

  function emptyRules() {
    return { snippets: [], corrections: [] };
  }

  function normalize(rules) {
    rules = rules || {};
    return {
      snippets: Array.isArray(rules.snippets) ? rules.snippets.filter(function (s) { return s && s.text; }) : [],
      corrections: Array.isArray(rules.corrections) ? rules.corrections.filter(function (c) { return c && c.wrong; }) : [],
    };
  }

  async function load() {
    var r = await chrome.storage.local.get(STORAGE_KEY);
    return normalize(r[STORAGE_KEY]);
  }

  async function save(rules) {
    var data = {};
    data[STORAGE_KEY] = normalize(rules);
    await chrome.storage.local.set(data);
  }

  var api = {
    STORAGE_KEY: STORAGE_KEY,
    splitTriggers: splitTriggers,
    applyCorrections: applyCorrections,
    applySnippets: applySnippets,
    applyRules: applyRules,
    keyterms: keyterms,
    emptyRules: emptyRules,
    normalize: normalize,
    load: load,
    save: save,
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.SVTextRules = api;
})(typeof self !== 'undefined' ? self : this);
