/**
 * VitaScribe - Meetwaarden uit dictaat (lokaal, zonder AI)
 *
 * Herkent gangbare metingen in gedicteerde tekst zodat ze los in de
 * meetwaardenvelden van Bricks gezet kunnen worden. Alleen wat er letterlijk
 * staat; niets wordt berekend of aangevuld, behalve de BMI als gewicht én
 * lengte beide genoemd zijn (dan duidelijk als berekend gemarkeerd).
 */
var SVMeetwaarden = (function () {
  var NUM = '(\\d{1,3}(?:[.,]\\d{1,2})?)';
  function num(s) { return parseFloat(String(s).replace(',', '.')); }
  function fmt(n, d) { return (Math.round(n * Math.pow(10, d)) / Math.pow(10, d)).toString().replace('.', ','); }

  var RULES = [
    { key: 'rr', label: 'Bloeddruk', unit: 'mmHg',
      re: /\b(?:RR|bloeddruk|tensie|BD)\s*(?:van|is|:)?\s*(\d{2,3})\s*(?:\/|over|op)\s*(\d{2,3})/gi,
      val: function (m) { var s = +m[1], d = +m[2]; return (s >= 60 && s <= 260 && d >= 30 && d <= 160 && s > d) ? s + '/' + d : null; } },
    { key: 'pols', label: 'Pols', unit: '/min',
      re: new RegExp('\\b(?:pols|hartfrequentie|HF|polsfrequentie)\\s*(?:van|is|:)?\\s*(\\d{2,3})(?:\\s*(?:/min|per minuut|slagen))?', 'gi'),
      val: function (m) { var v = +m[1]; return v >= 25 && v <= 250 ? String(v) : null; } },
    { key: 'sat', label: 'Saturatie', unit: '%',
      re: /\b(?:sat(?:uratie)?|SpO2|O2-?sat)\s*(?:van|is|:)?\s*(\d{2,3})\s*(?:%|procent)?/gi,
      val: function (m) { var v = +m[1]; return v >= 50 && v <= 100 ? String(v) : null; } },
    { key: 'temp', label: 'Temperatuur', unit: '°C',
      re: new RegExp('\\b(?:temp(?:eratuur)?|T)\\s*(?:van|is|:)?\\s*' + NUM + '\\s*(?:°\\s*C|graden)?', 'gi'),
      val: function (m) { var v = num(m[1]); return v >= 30 && v <= 44 ? fmt(v, 1) : null; } },
    { key: 'af', label: 'Ademfrequentie', unit: '/min',
      re: /\b(?:ademfrequentie|AF)\s*(?:van|is|:)?\s*(\d{1,2})/gi,
      val: function (m) { var v = +m[1]; return v >= 5 && v <= 70 ? String(v) : null; } },
    { key: 'gewicht', label: 'Gewicht', unit: 'kg',
      re: new RegExp('\\b(?:gewicht|weegt|gewogen)\\s*(?:van|is|:)?\\s*' + NUM + '\\s*(?:kg|kilo)?', 'gi'),
      val: function (m) { var v = num(m[1]); return v >= 1 && v <= 350 ? fmt(v, 1) : null; } },
    { key: 'lengte', label: 'Lengte', unit: 'cm',
      re: /\b(?:lengte|lang)\s*(?:van|is|:)?\s*(\d(?:[.,]\d{1,2})|\d{2,3})\s*(m|meter|cm|centimeter)?/gi,
      val: function (m) {
        var v = num(m[1]);
        if (/^m/.test(m[2] || '') || v < 3) v = v * 100;
        return v >= 40 && v <= 230 ? String(Math.round(v)) : null;
      } },
    { key: 'buik', label: 'Middelomtrek', unit: 'cm',
      re: /\b(?:middelomtrek|buikomvang|buikomtrek)\s*(?:van|is|:)?\s*(\d{2,3})/gi,
      val: function (m) { var v = +m[1]; return v >= 40 && v <= 220 ? String(v) : null; } },
    { key: 'glucose', label: 'Glucose', unit: 'mmol/l',
      re: new RegExp('\\b((?:nuchter\\s+)?(?:glucose|glucosewaarde|bloedsuiker|BS))\\s*(?:van|is|:)?\\s*' + NUM + '\\s*(?:mmol)?', 'gi'),
      val: function (m) { var v = num(m[2]); return v >= 1 && v <= 50 ? fmt(v, 1) : null; },
      extra: function (m) { return /nuchter/i.test(m[1]) ? 'nuchter' : ''; } },
    { key: 'hba1c', label: 'HbA1c', unit: 'mmol/mol',
      re: /\bHbA1c\s*(?:van|is|:)?\s*(\d{2,3})/gi,
      val: function (m) { var v = +m[1]; return v >= 15 && v <= 200 ? String(v) : null; } },
  ];

  /** Returns [{key,label,value,unit,note}] in dictation order; repeated
   *  measurements (e.g. two blood pressures) are all kept. */
  function extract(text) {
    var list = [];
    var last = {};
    RULES.forEach(function (rule) {
      rule.re.lastIndex = 0;
      var m;
      while ((m = rule.re.exec(text || '')) !== null) {
        var v = rule.val(m);
        if (v === null) continue;
        var item = { key: rule.key, label: rule.label, value: v, unit: rule.unit,
                     note: rule.extra ? rule.extra(m) : '', pos: m.index };
        if (!list.some(function (x) { return x.key === item.key && x.value === item.value; })) list.push(item);
        last[rule.key] = item;
      }
    });
    list.sort(function (a, b) { return a.pos - b.pos; });
    if (last.gewicht && last.lengte) {
      var bmi = num(last.gewicht.value) / Math.pow(+last.lengte.value / 100, 2);
      list.push({ key: 'bmi', label: 'BMI', value: fmt(bmi, 1), unit: 'kg/m²', note: 'berekend' });
    }
    return list;
  }

  function asText(list) {
    return list.map(function (w) { return w.label + ' ' + w.value + ' ' + w.unit + (w.note ? ' (' + w.note + ')' : ''); }).join('; ');
  }

  return { extract: extract, asText: asText };
})();
if (typeof module !== 'undefined') module.exports = SVMeetwaarden;
