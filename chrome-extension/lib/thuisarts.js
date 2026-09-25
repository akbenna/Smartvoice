/**
 * SmartVoice - ICPC naar Thuisarts.nl
 *
 * De arts kiest de informatie, de extensie zoekt haar alleen op. Een pagina
 * op Thuisarts hoort bij een diagnose; laat je een taalmodel uit het dictaat
 * afleiden welke pagina past, dan stelt dat model in feite een diagnose voor.
 * Dat is klinische beslisondersteuning, en precies wat data_policy uitsluit.
 * Het opzoeken loopt daarom over de ICPC-code die de arts zelf vastlegt, met
 * een vaste tabel en zonder model ertussen.
 *
 * Gevolg voor de privacy: hier is geen server bij nodig. De tabel zit in de
 * extensie en er gaat geen patiëntgegeven de browser uit om een link te
 * vinden.
 *
 * Alles hieronder is zuivere rekenkunde: geen DOM, geen chrome.*, geen fetch.
 * Daardoor is het met `node --test` na te lopen, en dat is ook de reden dat
 * dit bestand los staat van de schermcode.
 */
var SVThuisarts = (function () {
  'use strict';

  var ICPC = /^[A-Z]\d{2}$/;

  /**
   * "r78.01" and " R78 " both become R78. A subrubric falls back on its main
   * rubric: Thuisarts writes for the patient and does not make that
   * distinction, so R78.01 reads the same page as R78.
   */
  function normaliseer(code) {
    if (typeof code !== 'string') return '';
    var kaal = code.trim().toUpperCase().replace(/\s+/g, '');
    var hoofd = kaal.split('.')[0];
    return ICPC.test(hoofd) ? hoofd : '';
  }

  /**
   * The pages for a code, or an empty list.
   *
   * Only rows with both a URL and a check date count. An unchecked row is more
   * dangerous here than an empty table: a link that opens but covers another
   * condition is read by the patient with the same trust as a correct one.
   */
  function pagesForIcpc(code, tabel) {
    var hoofd = normaliseer(code);
    if (!hoofd) return [];
    var rijen = (tabel && tabel.paginas) || [];
    var uit = [];
    for (var i = 0; i < rijen.length; i++) {
      var r = rijen[i];
      if (!r || normaliseer(r.icpc) !== hoofd) continue;
      if (!r.url || !r.gecontroleerd_op) continue;
      if (String(r.url).indexOf('https://www.thuisarts.nl/') !== 0) continue;
      uit.push({ icpc: hoofd, titel: r.titel || hoofd, url: r.url,
                 gecontroleerd_op: r.gecontroleerd_op });
    }
    return uit;
  }

  /**
   * The Thuisarts search URL, for when no page is listed for the code.
   *
   * This URL has not been checked by eye: thuisarts.nl was unreachable from
   * the build environment. If it is wrong, this is the only place to change.
   */
  function zoekUrl(term) {
    return 'https://www.thuisarts.nl/zoeken?query=' + encodeURIComponent(String(term || '').trim());
  }

  /**
   * The line that goes under the patient explanation. Thuisarts is in Dutch;
   * when a translation is present it gets a sentence in that language saying
   * the website is Dutch, not the same line. Without it the explanation soon
   * promises information in Turkish that is not there.
   */
  var NEDERLANDS = {
    nl: 'Meer lezen: ',
    en: 'Read more (this website is in Dutch): ',
    ar: 'لمزيد من المعلومات (هذا الموقع باللغة الهولندية): ',
    tr: 'Daha fazla bilgi (bu web sitesi Felemenkçe dilindedir): ',
    pl: 'Więcej informacji (ta strona jest w języku niderlandzkim): ',
    uk: 'Докладніше (цей сайт голландською мовою): ',
    fr: 'En savoir plus (ce site est en néerlandais) : ',
    de: 'Mehr lesen (diese Website ist auf Niederländisch): ',
    es: 'Más información (este sitio web está en neerlandés): '
  };

  function verwijzing(url, taal) {
    var aanhef = NEDERLANDS[taal || 'nl'] || NEDERLANDS.nl;
    return aanhef + url;
  }

  return {
    normaliseer: normaliseer,
    pagesForIcpc: pagesForIcpc,
    zoekUrl: zoekUrl,
    verwijzing: verwijzing,
    TALEN: NEDERLANDS
  };
})();

// The extension loads this as a plain script (like lib/privacy.js); node --test
// needs an export. Hence this tail, and nothing more.
if (typeof module !== 'undefined' && module.exports) module.exports = SVThuisarts;
