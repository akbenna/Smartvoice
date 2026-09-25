/**
 * SmartVoice - Thuisarts.nl bij de SOEP-regel
 *
 * Gebruikt uit sidepanel.js: lastSoep, setStatus(). Het opzoeken zelf staat in
 * lib/thuisarts.js en raakt het scherm niet aan; hier staat alleen wat de arts
 * ziet en kan aanklikken.
 *
 * Twee dingen die met opzet zo zijn:
 *
 * - De chip verschijnt alleen bij een code die de arts op het scherm heeft
 *   staan. Verandert hij de code, dan verandert de chip mee. Er wordt nergens
 *   een pagina afgeleid uit het dictaat.
 * - Staat er geen pagina bij de code, dan zegt het scherm dat, en biedt het
 *   een zoekveld. Stil niets tonen zou de indruk wekken dat er niets is,
 *   terwijl de tabel misschien alleen nog niet is ingevuld.
 */
window.SVThuisartsUI = (function () {
  'use strict';

  var $ = function (id) { return document.getElementById(id); };
  var tabel = null;
  var gekozen = null;   // the page the doctor added to the explanation

  // The table is a file inside the extension; nothing goes over the network.
  var geladen = fetch(chrome.runtime.getURL('lib/thuisarts-icpc.json'))
    .then(function (r) { return r.json(); })
    .then(function (j) { tabel = j; })
    .catch(function () { tabel = { paginas: [] }; });

  function huidigeCode() {
    var el = $('icpc-code');
    return el ? el.innerText.trim() : '';
  }

  function nieuwLink(url, tekst, titel) {
    var a = document.createElement('a');
    a.href = url;
    a.target = '_blank';
    a.rel = 'noreferrer';
    a.className = 'ta-chip';
    a.textContent = tekst;
    if (titel) a.title = titel;
    return a;
  }

  function toonZoeken(code) {
    var vak = $('ta');
    var p = document.createElement('span');
    p.className = 'ta-leeg';
    p.textContent = code ? 'Geen Thuisarts-pagina bij deze code.' : 'Geen ICPC-code, dus geen voorstel.';
    vak.appendChild(p);

    var veld = document.createElement('input');
    veld.type = 'search';
    veld.className = 'ta-zoek';
    veld.placeholder = 'Zoek op thuisarts.nl';
    veld.setAttribute('aria-label', 'Zoek op thuisarts.nl');
    veld.addEventListener('keydown', function (e) {
      if (e.key !== 'Enter' || !veld.value.trim()) return;
      window.open(SVThuisarts.zoekUrl(veld.value), '_blank', 'noreferrer');
    });
    vak.appendChild(veld);
  }

  /** Rebuild the chip for the code currently on screen. */
  function toon() {
    var vak = $('ta');
    if (!vak) return;
    geladen.then(function () {
      var code = huidigeCode();
      vak.textContent = '';
      // Showing a page is not choosing it. `gekozen` is only set by an explicit
      // click below, so nothing reaches the patient that the doctor did not pick.

      var paginas = SVThuisarts.pagesForIcpc(code, tabel);
      if (!paginas.length) {
        vak.classList.remove('hidden');
        toonZoeken(code);
        return;
      }

      // One chip per page, each with its own add button: when a code has two
      // pages (R78: the condition and "hoesten"), the doctor picks which.
      paginas.forEach(function (pagina) {
        var groep = document.createElement('span');
        groep.className = 'ta-pagina';
        // The doctor reads what the patient will read: the link simply opens.
        groep.appendChild(nieuwLink(pagina.url, 'Thuisarts: ' + pagina.titel + ' ↗',
          'Gecontroleerd op ' + pagina.gecontroleerd_op));
        var knop = document.createElement('button');
        knop.className = 'btn small ta-voeg-toe';
        knop.textContent = 'Voeg toe aan uitleg';
        knop.title = 'Zet een regel met ' + pagina.titel + ' onder de uitleg voor de patiënt';
        knop.addEventListener('click', function () { voegToe(pagina); });
        groep.appendChild(knop);
        vak.appendChild(groep);
      });
      vak.classList.remove('hidden');
    });
  }

  /**
   * Put the reference under the B1 text, and under a translation a sentence in
   * that language saying the website is Dutch. Without it the explanation
   * suggests there is information in Turkish to be found.
   */
  function voegToe(pagina) {
    var nl = $('pi-nl');
    if (!nl || !nl.value.trim()) {
      setStatus('Maak eerst de uitleg voor de patiënt; daarna kan de link eronder.', true);
      return;
    }
    gekozen = pagina;
    var regelNl = SVThuisarts.verwijzing(pagina.url, 'nl');
    if (nl.value.indexOf(pagina.url) === -1) nl.value = nl.value.replace(/\s*$/, '') + '\n\n' + regelNl;

    var tr = $('pi-tr');
    if (tr && tr.value.trim() && tr.value.indexOf(pagina.url) === -1) {
      var taal = $('pi-taal') ? $('pi-taal').value : '';
      tr.value = tr.value.replace(/\s*$/, '') + '\n\n' + SVThuisarts.verwijzing(pagina.url, taal);
    }
    meldGebruik(pagina.icpc);
    setStatus('Link toegevoegd. De QR-code komt vanzelf op de afdruk.');
  }

  /**
   * One usage line, without URL and without text: the main rubric only, so the
   * practice can see whether this function is used. On failure nothing visible
   * happens; a usage log must never hold up care.
   */
  async function meldGebruik(icpc) {
    try {
      var config = await getConfig();
      if (!config.apiUrl) return;
      var headers = { 'Content-Type': 'application/json' };
      if (config.apiKey) headers['X-API-Key'] = config.apiKey;
      await fetch(config.apiUrl + '/api/v1/usage', {
        method: 'POST', headers: headers,
        body: JSON.stringify({ action: 'patient.thuisarts', kind: icpc }),
      });
    } catch (e) { /* silence is the right answer here */ }
  }

  // The doctor may correct the code; the chip follows while typing, and the
  // rest of the panel (insert into Bricks, copy) uses the same value.
  var codeEl = $('icpc-code');
  if (codeEl) {
    codeEl.addEventListener('input', function () {
      var code = huidigeCode();
      // The title shown next to the code belonged to the old code. Replace it
      // with the table's title for the new one, or leave it empty: "R78 ·
      // Spanningshoofdpijn" is worse than no title at all.
      geladen.then(function () {
        var titel = SVThuisarts.titelVoor(code, tabel);
        $('icpc-titel').textContent = titel ? ' \u00b7 ' + titel : '';
        if (typeof lastSoep !== 'undefined' && lastSoep) {
          lastSoep.icpc_code = code;
          lastSoep.icpc_titel = titel;
        }
      });
      toon();
    });
    // One line, no formatting: enter and pasted markup do not belong here.
    codeEl.addEventListener('keydown', function (e) { if (e.key === 'Enter') e.preventDefault(); });
    codeEl.addEventListener('paste', function (e) {
      e.preventDefault();
      var tekst = (e.clipboardData || window.clipboardData).getData('text').replace(/\s+/g, ' ').trim();
      document.execCommand('insertText', false, tekst);
    });
  }

  /**
   * The page the doctor added, for as long as its link is still in the text.
   * Regenerating the explanation or deleting the "Meer lezen" line removes the
   * link; then the QR on the printout should disappear with it, not linger.
   */
  function huidigePagina() {
    var nl = $('pi-nl');
    if (!gekozen || !nl || nl.value.indexOf(gekozen.url) === -1) return null;
    return gekozen;
  }

  return { toon: toon, huidigePagina: huidigePagina };
})();
