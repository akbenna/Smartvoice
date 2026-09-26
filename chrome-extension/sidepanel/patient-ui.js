/**
 * VitaScribe - Patiëntinstructie (B1 + vertaling) uit de SOEP-regel.
 * Uses from sidepanel.js: getConfig(), setStatus(), lastSoep, els.soepRows
 */
(function () {
  'use strict';
  var $ = function (id) { return document.getElementById(id); };

  function currentEP() {
    // The doctor may have edited the SOEP rows; read what is on screen.
    var get = function (k) {
      var el = document.querySelector('.soep-text[data-key="' + k + '"]');
      return el ? el.innerText.trim() : ((typeof lastSoep !== 'undefined' && lastSoep && lastSoep[k]) || '');
    };
    return { e: get('e'), p: get('p') };
  }

  $('btn-patient').addEventListener('click', function () { $('pi').classList.toggle('hidden'); });

  $('pi-go').addEventListener('click', async function () {
    var ep = currentEP();
    if (ep.p.length < 3) { setStatus('Er staat nog geen plan (P) om uit te leggen.', true); return; }
    var btn = this; btn.disabled = true; btn.textContent = 'Bezig…';
    try {
      var config = await getConfig();
      var headers = { 'Content-Type': 'application/json' };
      if (config.apiKey) headers['X-API-Key'] = config.apiKey;
      await SVPraktijk.metKop(headers);
      var resp = await fetch(config.apiUrl + '/api/v1/patient-instructions', {
        method: 'POST', headers: headers, body: JSON.stringify({ e: ep.e, p: ep.p, taal: $('pi-taal').value }),
      });
      if (!resp.ok) {
        var d = await resp.json().then(function (j) { return j.detail; }).catch(function () { return ''; });
        throw new Error('Server gaf fout ' + resp.status + (d ? ': ' + d : ''));
      }
      var data = await resp.json();
      $('pi-nl').value = data.nl;
      $('pi-nl').classList.remove('hidden');
      $('pi-tr').value = data.vertaling || '';
      $('pi-tr').classList.toggle('hidden', !data.vertaling);
      document.querySelector('.pi-actions').classList.remove('hidden');
      setStatus('Patiëntinstructie klaar. Lees hem na voordat je hem meegeeft.');
    } catch (e) {
      setStatus(e.message === 'Failed to fetch' ? 'Kan de server niet bereiken.' : e.message, true);
    } finally { btn.disabled = false; btn.textContent = 'Maak'; }
  });

  function fullText() {
    var t = $('pi-nl').value.trim();
    if ($('pi-tr').value.trim()) t += '\n\n────────\n\n' + $('pi-tr').value.trim();
    return t;
  }

  /* The chosen Thuisarts page, or null. The lookup lives in thuisarts-ui.js;
     here we only ask what the doctor picked. */
  function pagina() {
    return window.SVThuisartsUI ? window.SVThuisartsUI.huidigePagina() : null;
  }

  /* The explanation as it leaves. The link is in it only if the doctor added
     it; nothing is appended here on the doctor's behalf. */
  function berichtTekst() {
    return fullText();
  }

  /* Open the practice's own mail client. An anchor click hands mailto: to the
     protocol handler without opening an empty tab from the side panel. */
  function openMail(href) {
    var a = document.createElement('a');
    a.href = href;
    a.rel = 'noreferrer';
    document.body.appendChild(a);
    a.click();
    a.remove();
  }
  $('pi-copy').addEventListener('click', async function () {
    await navigator.clipboard.writeText(fullText());
    setStatus('Gekopieerd.');
  });
  /*
   * AFDRUKKEN MET QR-CODE
   *
   * De QR wordt hier gemaakt, in de browser van de arts, met de meegeleverde
   * bibliotheek. Een QR-dienst op internet zou de URL te zien krijgen die op
   * het papier van de patiënt komt, en die URL zegt welke aandoening het is.
   * Dat is een gezondheidsgegeven en hoort de praktijk niet te verlaten.
   */
  function qrSvg(url) {
    try {
      // Error correction M: enough margin for a fold or a coffee stain without
      // making the code needlessly fine for a phone camera.
      var qr = qrcode(0, 'M');
      qr.addData(url);
      qr.make();
      return qr.createSvgTag({ cellSize: 4, margin: 2, scalable: true });
    } catch (e) {
      return '';   // rather a printout without a QR than no printout
    }
  }

  $('pi-print').addEventListener('click', function () {
    var esc = function (s) { return s.replace(/[&<>]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]; }); };
    var p = pagina();
    var qr = p ? qrSvg(p.url) : '';
    var html = '<!doctype html><html lang="nl"><head><meta charset="utf-8"><title>Uitleg voor u</title>' +
      '<style>body{font:15px/1.6 system-ui,sans-serif;max-width:640px;margin:32px auto;padding:0 16px;white-space:pre-wrap}' +
      '.tr{margin-top:28px;padding-top:16px;border-top:1px solid #ccc}' +
      '.ta{margin-top:28px;padding-top:16px;border-top:1px solid #ccc;white-space:normal;' +
      'display:flex;gap:16px;align-items:center}' +
      '.ta svg{width:104px;height:104px;flex:none}' +
      '.ta .t{font-size:13px}.ta .u{font-size:12px;color:#555;word-break:break-all}' +
      '</style></head><body>' +
      '<div>' + esc($('pi-nl').value) + '</div>' +
      ($('pi-tr').value.trim() ? '<div class="tr" dir="auto">' + esc($('pi-tr').value) + '</div>' : '') +
      (p ? '<div class="ta">' + qr + '<div><div class="t"><strong>' + esc(p.titel) +
           '</strong> op Thuisarts.nl</div><div class="u">' + esc(p.url) + '</div></div></div>' : '') +
      '</body></html>';
    var url = URL.createObjectURL(new Blob([html], { type: 'text/html' }));
    var w = window.open(url);
    if (w) w.addEventListener('load', function () { w.print(); });
  });

  /*
   * ROUTE 2: KOPIEREN VOOR HET HIS-BERICHT OF HET PORTAAL
   *
   * De meeste waarde met het kleinste risico: het bericht blijft in het
   * dossier en loopt over een kanaal dat al beveiligd is. De tekst draagt geen
   * naam, geboortedatum of BSN - de uitleg wordt zonder die gegevens gemaakt -
   * en de link gaat mee, zodat de patiënt verderop leest bij de bron die de
   * beroepsgroep zelf onderhoudt.
   */
  $('pi-bericht').addEventListener('click', async function () {
    await navigator.clipboard.writeText(berichtTekst());
    setStatus('Gekopieerd voor het berichtenveld van Bricks of het portaal. Lees het na voordat je verstuurt.');
  });

  /*
   * ROUTE 3: MAILEN
   *
   * Alleen zichtbaar als de praktijk hem aanzet. Een uitleg over een
   * aandoening naast een e-mailadres is een gezondheidsgegeven, en dat geldt
   * ook voor een mail met enkel een Thuisarts-link: de link zegt welke
   * aandoening het is. Zulke mail hoort beveiligd te gaan (NEN 7510), en de
   * extensie kan niet zien of dat gebeurt.
   *
   * Daarom verstuurt de VitaScribe-server nooit zelf mail - dan werd hij
   * verwerker van een nieuwe gegevensstroom - en vult de extensie geen
   * ontvanger in. Het adres van de patiënt uit Bricks halen zou een nieuwe
   * schraaproute openen, en een verkeerd ingevuld adres is een datalek.
   */
  var MAIL_MAX = 1500;   // well under what mail clients take from a mailto

  $('pi-mail').addEventListener('click', async function () {
    var tekst = berichtTekst();
    var onderwerp = 'Uitleg van uw huisarts';
    if (tekst.length > MAIL_MAX) {
      // Mail clients silently truncate longer bodies. Better on the clipboard
      // and pasted in sight than half an explanation sent.
      await navigator.clipboard.writeText(tekst);
      openMail('mailto:?subject=' + encodeURIComponent(onderwerp));
      setStatus('De uitleg is te lang om vooraf in te vullen en staat op het klembord. Plak hem in de mail ' +
        'en vul zelf het adres in, via de beveiligde mail van de praktijk.');
      return;
    }
    openMail('mailto:?subject=' + encodeURIComponent(onderwerp) + '&body=' + encodeURIComponent(tekst));
    setStatus('Mail geopend zonder ontvanger. Vul het adres zelf in, via de beveiligde mail van de praktijk.');
  });

  // The mail button exists only when the practice has switched it on.
  chrome.storage.sync.get(['delenPerMail']).then(function (opgeslagen) {
    $('pi-mail').classList.toggle('hidden', opgeslagen.delenPerMail !== 'aan');
  }).catch(function () { /* then it stays hidden, which is the safe side */ });

})();
