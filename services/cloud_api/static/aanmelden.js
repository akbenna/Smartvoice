(function () {
  var form = document.getElementById('formulier');
  var knop = document.getElementById('verstuur');
  var melding = document.getElementById('melding');

  function toon(tekst, soort) {
    melding.textContent = tekst;
    melding.className = 'melding ' + soort;
  }

  function getal(id) {
    var v = document.getElementById(id).value.trim().replace(',', '.');
    return v === '' ? null : Number(v);
  }

  form.addEventListener('submit', async function (e) {
    e.preventDefault();
    var waarde = function (id) { return document.getElementById(id).value.trim(); };
    var data = {
      praktijknaam: waarde('praktijknaam'),
      plaats: waarde('plaats'),
      praktijknummer: waarde('praktijknummer'),
      agb: waarde('agb'),
      contact_naam: waarde('contact_naam'),
      email: waarde('email'),
      telefoon: waarde('telefoon'),
      fte: getal('fte'),
      werkplekken: getal('werkplekken'),
      opmerking: waarde('opmerking'),
      akkoord: document.getElementById('akkoord').checked,
      website: waarde('website'),
    };
    if (data.werkplekken !== null) data.werkplekken = Math.round(data.werkplekken);
    if (!data.praktijknaam || !data.plaats || !data.contact_naam || !data.email) {
      toon('Vul de naam en plaats van de praktijk in, een contactpersoon en een e-mailadres.', 'fout');
      return;
    }
    if (!data.akkoord) {
      toon('Vink aan dat we contact met u mogen opnemen.', 'fout');
      return;
    }
    knop.disabled = true;
    try {
      var r = await fetch('/api/v1/aanmelden', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
      var body = await r.json().catch(function () { return {}; });
      if (!r.ok) {
        var d = body.detail;
        toon(typeof d === 'string' ? d : 'Controleer de ingevulde gegevens en probeer het opnieuw.', 'fout');
        knop.disabled = false;
        return;
      }
      form.querySelectorAll('input,textarea,button').forEach(function (el) { el.disabled = true; });
      toon('Dank u wel. Uw aanmelding is binnen; we nemen binnen enkele werkdagen contact met u op.', 'goed');
    } catch (err) {
      toon('De aanmelding kon niet worden verstuurd. Controleer de verbinding en probeer het opnieuw.', 'fout');
      knop.disabled = false;
    }
  });
})();
