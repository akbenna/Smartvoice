/**
 * VitaScribe - One-time microphone permission for the side panel.
 * Permission is granted per extension origin, so granting it here also
 * covers the side panel.
 */

var result = document.getElementById('result');

async function requestMic() {
  try {
    var stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    stream.getTracks().forEach(function (t) { t.stop(); });
    result.className = 'ok';
    result.textContent = 'Gelukt. Je kunt dit tabblad sluiten en in het zijpaneel gaan dicteren.';
    setTimeout(function () { window.close(); }, 2500);
  } catch (err) {
    result.className = 'err';
    result.textContent = 'Geen toestemming (' + err.name + '). Klik op het slot-icoon in de adresbalk en zet Microfoon op "Toestaan".';
  }
}

document.getElementById('grant').addEventListener('click', requestMic);
requestMic();
