# Overstap van SmartVoice naar VitaScribe

In de repo heet alles nu VitaScribe: de extensie, de schermen, de documentatie,
de bestandsnamen, de serverpaden en de voorbeeldadressen. Maar een naam in de
code verandert niets aan wat er draait. De adressen en instellingen hieronder
staan buiten de repo, bij Railway, bij Vercel, op de server en in de browser van
elke werkplek. Die zet je zelf om, in deze volgorde. Tot dat gebeurd is, blijft
alles gewoon werken: waar de oude naam nog live is, vangt de code hem op.

## 1. De sleutel van de extensie — eerst, en voorzichtig

`smartvoice.pem` heet voortaan `vitascribe.pem`. Hernoem het bestand, maar maak
**geen nieuwe sleutel**. De sleutel bepaalt het extensie-ID; een andere sleutel
geeft een andere extensie, en dan installeert het beleid (ExtensionInstallForcelist)
op geen enkele werkplek meer de bestaande. Controleer na het inpakken met
`scripts/pack_extension.sh` dat het getoonde ID gelijk is aan het oude.

## 2. GitHub

Hernoem de repository `akbenna/Smartvoice` naar `akbenna/VitaScribe`
(Settings → General → Repository name). GitHub stuurt oude adressen door, dus
bestaande clones en links blijven werken; `git remote set-url` kan later.

## 3. Vercel (frontend)

De frontend draait nu op `smartvoice-nine.vercel.app`; een VitaScribe-adres
bestaat nog niet. Voeg in het project een domein toe (Settings → Domains),
bij voorkeur `vitascribe.vercel.app`. Is dat bezet, kies dan een ander en zet
dat in `.env.production` en `DEPLOY.md` op de plek van `vitascribe.vercel.app`.
Laat het oude domein staan tot stap 4 klaar is.

## 4. Railway (API)

Zet `CORS_ALLOWED_ORIGINS` op beide adressen, zoals in `.env.production`:

```
CORS_ALLOWED_ORIGINS=https://vitascribe.vercel.app,https://smartvoice-nine.vercel.app
```

De service mag een nieuwe naam krijgen. **Het adres van de API liever niet
veranderen**, of alleen door een nieuw adres náást het oude te zetten. Dat
adres staat op twee plekken die niet in deze repo zitten: in de instellingen van
de extensie op elke werkplek (`apiUrl`), en in de beleidswaarde
`ExtensionInstallForcelist` (`<id>;<adres>/extension/update.xml`). Wie het adres
wisselt, moet beide op elke pc bijwerken.

## 5. De praktijkserver

Het pad `/opt/smartvoice`, de systeemgebruiker `smartvoice` en de cron- en
systemd-bestanden heten nu `vitascribe`:

```bash
sudo systemctl disable --now smartvoice-learning.timer
sudo mv /opt/smartvoice /opt/vitascribe
sudo usermod -l vitascribe smartvoice && sudo groupmod -n vitascribe smartvoice
sudo cp /opt/vitascribe/deploy/systemd/vitascribe-learning.* /etc/systemd/system/
sudo rm /etc/systemd/system/smartvoice-learning.*
sudo systemctl daemon-reload && sudo systemctl enable --now vitascribe-learning.timer
# cron: vervang de oude regels door die uit deploy/cron/vitascribe-*.cron
```

Stond `SMARTVOICE_ROOT` in een omgeving, zet dan `VITASCRIBE_ROOT`; tot die tijd
leest `run_learning_jobs.sh` de oude naam nog.

## 6. Het extensiepakket

Pak de extensie opnieuw in met de hernoemde sleutel en publiceer
`vitascribe.crx` en de nieuwe `update.xml`. Werkplekken met een oude
`update.xml` vragen nog naar `/extension/smartvoice.crx`; de server geeft op
beide paden hetzelfde pakket, dus niemand blijft op een oude versie hangen.

## 7. Opruimen, als alles om is

Pas als geen werkplek, beleid of omgeving de oude naam nog gebruikt:

- `smartvoice-nine.vercel.app` uit Vercel en uit `CORS_ALLOWED_ORIGINS`;
- de route `/extension/smartvoice.crx` en `smartvoice.crx` uit `_CRX_NAMES` in
  `services/cloud_api/main.py`, met de bijbehorende proef;
- de terugval op `SMARTVOICE_ROOT` in `scripts/run_learning_jobs.sh`.

`git grep -i smartvoice` laat dan alleen dit document nog zien.

## Wat bewust niet hernoemd is

De interne voorvoegsels `SV` in de extensie (`SVPrivacy`, `SVThuisarts`,
`SV_FILL_SOEP_REQUEST` en dergelijke) zijn afkortingen die niemand ziet.
Hernoemen raakt ruim honderd verwijzingen tussen scripts en levert niets zichtbaars
op. De opslagsleutels van de extensie bevatten de naam niet, dus instellingen en
API-sleutels op de werkplekken blijven gewoon staan.
