#!/usr/bin/env bash
# Pakt chrome-extension/ in als CRX voor centrale uitrol (Edge/Chrome-beleid)
# en schrijft update.xml. Gebruik:
#
#   scripts/pack_extension.sh [--verwacht-id <id>] <vitascribe.pem> <https://jouw-server> [uitvoermap]
#   scripts/pack_extension.sh --nieuwe-sleutel <vitascribe.pem> <https://jouw-server> [uitvoermap]
#
# De .pem-sleutel bepaalt het extensie-ID, en op dat ID steunt het beleid
# (ExtensionInstallForcelist) op elke werkplek. Bewaar hem veilig, met een kopie
# op een tweede plek, en NOOIT in git.
#
# WAAROM DIT SCRIPT WEIGERT
#
# Het onderliggende gereedschap (crx3) maakt zonder waarschuwing een nieuwe
# sleutel aan als er op het opgegeven pad geen staat. Een tikfout in de
# bestandsnaam gaf dus stilletjes een nieuw extensie-ID, en daarna installeert
# het beleid de bestaande extensie op geen enkele werkplek meer. Daarom:
#
#   - Staat er geen sleutel op het pad, dan stopt het script, tenzij je met
#     --nieuwe-sleutel uitdrukkelijk zegt dat je een nieuwe extensie wilt. Dat
#     is alleen goed bij de allereerste uitrol.
#   - Staat er wel een, en geef je --nieuwe-sleutel mee, dan stopt het ook: dan
#     klopt wat je vraagt niet met wat er ligt.
#   - Met --verwacht-id <id> controleert het script vóór het inpakken of de
#     sleutel bij het ID hoort dat op de werkplekken staat. Gebruik dat bij
#     elke uitrol na de eerste; het ID staat in de beleidswaarde en op
#     edge://extensions.
set -euo pipefail

NIEUW=0
VERWACHT=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --nieuwe-sleutel) NIEUW=1; shift ;;
    --verwacht-id) VERWACHT="${2:?--verwacht-id heeft een extensie-ID nodig}"; shift 2 ;;
    --) shift; break ;;
    -*) echo "Onbekende optie: $1" >&2; exit 2 ;;
    *) break ;;
  esac
done

KEY="${1:?pad naar .pem-sleutel}"
BASE="${2:?server-URL, bv. https://vitascribe-production.up.railway.app}"
OUT="${3:-dist/extension}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# Extension ID = first 16 bytes of sha256(public key DER), as hex mapped to a-p.
# od instead of xxd: xxd ships with vim and is missing on many servers, and a
# missing tool here stopped the script after the package was already built.
#
# The public key goes through a file, not a pipe, and an empty or unreadable
# result is a failure. In a pipe a key that openssl cannot read yields no
# bytes, and the sha256 of nothing is a perfectly valid-looking ID
# (odlameec...), which would have gone into update.xml without complaint.
extensie_id() {
  local der
  der="$(mktemp)"
  if ! openssl rsa -in "$1" -pubout -outform DER -out "$der" 2>/dev/null || [[ ! -s "$der" ]]; then
    rm -f "$der"
    return 1
  fi
  openssl dgst -sha256 -binary "$der" | od -An -tx1 -v | tr -d ' \n' | cut -c1-32 | tr '0-9a-f' 'a-p'
  rm -f "$der"
}

if [[ -e "$KEY" ]]; then
  if (( NIEUW )); then
    echo "Er staat al een sleutel op $KEY; --nieuwe-sleutel past daar niet bij." >&2
    echo "Wil je de bestaande extensie bijwerken, laat --nieuwe-sleutel dan weg." >&2
    exit 1
  fi
  if ! ID="$(extensie_id "$KEY")" || [[ ${#ID} -ne 32 ]]; then
    echo "$KEY is niet te lezen als RSA-sleutel; er is niets ingepakt." >&2
    exit 1
  fi
  if [[ -n "$VERWACHT" && "$ID" != "$VERWACHT" ]]; then
    echo "Deze sleutel hoort bij extensie-ID $ID, niet bij $VERWACHT." >&2
    echo "Er is niets ingepakt. Zoek de sleutel waarmee de extensie eerder is uitgerold." >&2
    exit 1
  fi
else
  if (( ! NIEUW )); then
    echo "Geen sleutel gevonden op $KEY; er is niets ingepakt." >&2
    echo >&2
    echo "Is de extensie al eens uitgerold, zoek dan de sleutel van toen (hij kan nog" >&2
    echo "smartvoice.pem heten) en geef dat pad op. Een nieuwe sleutel geeft een nieuw" >&2
    echo "extensie-ID, en dan installeert het beleid de bestaande extensie nergens meer." >&2
    echo >&2
    echo "Is dit de allereerste uitrol, draai het script dan met --nieuwe-sleutel." >&2
    exit 1
  fi
  if [[ -n "$VERWACHT" ]]; then
    echo "--verwacht-id en --nieuwe-sleutel sluiten elkaar uit: een nieuwe sleutel heeft een nieuw ID." >&2
    exit 2
  fi
fi

VERSION="$(python3 -c "import json;print(json.load(open('$ROOT/chrome-extension/manifest.json'))['version'])")"
mkdir -p "$OUT"
npx --yes crx3@1 -p "$KEY" -o "$OUT/vitascribe.crx" "$ROOT/chrome-extension"

if ! ID="$(extensie_id "$KEY")" || [[ ${#ID} -ne 32 ]]; then
  echo "Het extensie-ID kon niet uit $KEY worden berekend; update.xml is niet geschreven." >&2
  exit 1
fi

if (( NIEUW )); then
  chmod 600 "$KEY"
  echo "────────────────────────────────────────────────────────────────────"
  echo "Nieuwe sleutel gemaakt: $KEY"
  echo "Dit bestand is vanaf nu de extensie. Kwijt betekent: op elke werkplek"
  echo "opnieuw installeren. Maak nu een kopie op een tweede veilige plek."
  echo "────────────────────────────────────────────────────────────────────"
fi

cat > "$OUT/update.xml" <<XML
<?xml version='1.0' encoding='UTF-8'?>
<gupdate xmlns='http://www.google.com/update2/response' protocol='2.0'>
  <app appid='$ID'>
    <updatecheck codebase='$BASE/extension/vitascribe.crx' version='$VERSION' />
  </app>
</gupdate>
XML
echo "Klaar: $OUT/vitascribe.crx (versie $VERSION)"
echo "Extensie-ID: $ID"
echo "Beleidswaarde ExtensionInstallForcelist: $ID;$BASE/extension/update.xml"
