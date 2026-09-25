#!/usr/bin/env bash
# Pakt chrome-extension/ in als CRX voor centrale uitrol (Edge/Chrome-beleid)
# en schrijft update.xml. Gebruik:
#   scripts/pack_extension.sh <pad/naar/vitascribe.pem> <https://jouw-server> [uitvoermap]
# De .pem-sleutel bepaalt het extensie-ID: bewaar hem veilig en NOOIT in git.
# Na de overstap van SmartVoice naar VitaScribe is het DEZELFDE sleutel onder een
# nieuwe bestandsnaam. Maak geen nieuwe: een andere sleutel geeft een ander ID, en
# dan installeert het beleid op geen enkele werkplek meer de bestaande extensie.
set -euo pipefail
KEY="${1:?pad naar .pem-sleutel}"
BASE="${2:?server-URL, bv. https://vitascribe-production.up.railway.app}"
OUT="${3:-dist/extension}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="$(python3 -c "import json;print(json.load(open('$ROOT/chrome-extension/manifest.json'))['version'])")"
mkdir -p "$OUT"
npx --yes crx3@1 -p "$KEY" -o "$OUT/vitascribe.crx" "$ROOT/chrome-extension"
# Extension ID = first 16 bytes of sha256(public key DER), mapped to a-p.
ID="$(openssl rsa -in "$KEY" -pubout -outform DER 2>/dev/null | openssl dgst -sha256 -binary | head -c16 | xxd -p | tr '0-9a-f' 'a-p')"
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
