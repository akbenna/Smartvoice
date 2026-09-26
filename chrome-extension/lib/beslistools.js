/**
 * VitaScribe - ICPC naar naslag en patiëntuitleg in ProVita Care
 *
 * Werkt als de Thuisarts-koppeling (lib/thuisarts.js): de arts legt de
 * ICPC-code vast, deze tabel zoekt er een link bij. Er zit geen taalmodel
 * tussen en VitaScribe rekent niets uit, dus er ontstaat geen advies voor
 * deze patiënt. Dat is waarom klinische suggesties in data_policy uit staan,
 * en waarom de tabel alleen naslag bevat: protocollen, doseringstabellen,
 * vergoedingen, en uitlegfilmpjes voor de patiënt. Tools die met gegevens van
 * één patiënt een advies of score maken, horen hier niet in.
 *
 * Er gaat niets het netwerk op om een link te vinden. De link zelf bevat
 * alleen het tabblad (?tab=copd), nooit een patiëntgegeven.
 *
 * Zuivere rekenkunde, zonder DOM of chrome.*: na te lopen met node --test.
 */
var SVBeslistools = (function () {
  'use strict';

  var CODE = /^[A-Z]\d{2}(\.\d{1,2})?$/;
  var BASIS = 'https://provitacare.nl';

  /** " t90.02 " wordt "T90.02"; iets wat geen ICPC-code is wordt "". */
  function normaliseer(code) {
    if (typeof code !== 'string') return '';
    var kaal = code.trim().toUpperCase().replace(/\s+/g, '');
    return CODE.test(kaal) ? kaal : '';
  }

  /**
   * Past een regel bij de code? "T90" in de tabel past bij T90 en T90.02;
   * "U99.01" past alleen bij U99.01. Een hoofdrubriek als U99 dekt veel
   * verschillende aandoeningen, dus daar mag een subrubriek niet terugvallen
   * op de hoofdrubriek, andersom wel.
   */
  function past(tabelcode, code) {
    var t = normaliseer(tabelcode);
    if (!t || !code) return false;
    return code === t || code.indexOf(t + '.') === 0;
  }

  /** Alleen een pad binnen ProVita Care. Het adres van de site staat hier vast
      en niet in de tabel: een tabelregel kan de arts nooit naar een andere site sturen. */
  function url(pad) {
    if (typeof pad !== 'string' || pad.charAt(0) !== '/' || pad.charAt(1) === '/' || pad.indexOf('\\') !== -1) return null;
    return BASIS + pad;
  }

  /**
   * De links bij een code, gesplitst in naslag (voor de arts, met ProVita-
   * login) en uitleg voor de patiënt (openbaar). Een regel telt alleen mee
   * als iemand hem heeft gecontroleerd: 'gecontroleerd_op' en 'door' gevuld.
   */
  function voorCode(code, tabel) {
    var uit = { naslag: [], patient: [] };
    var c = normaliseer(code);
    if (!c) return uit;
    var rijen = (tabel && tabel.links) || [];
    for (var i = 0; i < rijen.length; i++) {
      var r = rijen[i];
      if (!r || !r.gecontroleerd_op || !r.door) continue;
      if (r.soort !== 'naslag' && r.soort !== 'patient') continue;
      var codes = Array.isArray(r.icpc) ? r.icpc : [r.icpc];
      if (!codes.some(function (t) { return past(t, c); })) continue;
      var adres = url(r.pad);
      if (!adres) continue;
      uit[r.soort].push({ id: r.id, titel: r.titel || r.id, url: adres, uitleg: r.uitleg || '',
                          gecontroleerd_op: r.gecontroleerd_op });
    }
    return uit;
  }

  return { normaliseer: normaliseer, past: past, voorCode: voorCode, BASIS: BASIS };
})();

if (typeof module !== 'undefined' && module.exports) module.exports = SVBeslistools;
