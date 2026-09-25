# VitaScribe uitrollen op de werkplekken

## 1. Eén sleutel per gebruiker

Zet op de server (Railway → Variables) `API_USERS`, met per gebruiker een eigen sleutel:

```
API_USERS=dr.bennaghmouch:<lange-willekeurige-sleutel>,assistente-1:<sleutel>,poh-s:<sleutel>
```

Een sleutel maak je met `openssl rand -hex 24`. Ieder vult zijn eigen sleutel in bij Instellingen van de extensie. Wie uit dienst gaat of een laptop kwijtraakt, haal je uit de lijst. De rest merkt daar niets van. De oude gedeelde `API_KEYS` blijft werken (gebruiker "gedeeld") tot je hem leegmaakt.

## 2. Gebruikslog (NEN 7513)

De server schrijft per gebruik een regel met wie, wat, wanneer en de uitkomst. Er staat nooit inhoud in: geen audio, tekst of namen. De regels staan in de Railway-logs onder `audit`. Wil je ze ook in een bestand, zet dan `AUDIT_LOG_PATH`. Spreek af wie de logs periodiek bekijkt en hoe lang ze bewaard worden. NEN 7513 vraagt om controle, niet alleen om vastleggen.

## 3. Extensie automatisch installeren en bijwerken (Edge)

**Voorwaarde (Microsoft):** zelf gehoste extensies werken alleen op Windows-pc's die lid zijn van een Active Directory-domein of Entra *hybrid joined* zijn. Vraag je ICT-leverancier of dat voor de praktijk-pc's geldt. Is dat niet zo, dan zijn de alternatieven publicatie in de Edge Add-ons-winkel, of handmatig laden zoals nu.

Stappen:

1. De allereerste keer: `scripts/pack_extension.sh --nieuwe-sleutel vitascribe.pem https://<server>`. Dat maakt de ondertekensleutel `vitascribe.pem` aan, alleen leesbaar voor jou. Bewaar hem veilig, buiten git, met een kopie op een tweede plek: met dezelfde sleutel blijft het extensie-ID gelijk, en kwijt betekent op elke werkplek opnieuw installeren. Noteer het getoonde extensie-ID.
2. Elke keer daarna: `scripts/pack_extension.sh --verwacht-id <ID> vitascribe.pem https://<server>`. Het script controleert vóór het inpakken of de sleutel bij dat ID hoort, en weigert als er op het pad geen sleutel staat. Dat is met opzet: het onderliggende gereedschap zou anders stilletjes een nieuwe sleutel maken, met een nieuw ID, en dan pakt het beleid de extensie op geen enkele werkplek meer op. Is er al eens uitgerold met een sleutel die nog `smartvoice.pem` heet, gebruik dan die, hernoemd. Het script maakt `dist/extension/vitascribe.crx` en `update.xml`, en toont het ID en de beleidswaarde.
3. Zet beide bestanden op een https-adres dat de pc's zonder inloggen bereiken. Dat kan de VitaScribe-server zelf (`/extension/update.xml` en `/extension/vitascribe.crx`, via `EXTENSION_DIST_DIR`) of een andere statische host.
4. De ICT-leverancier zet in Groepsbeleid (Microsoft Edge → Extensies):
   - `ExtensionInstallForcelist`: `<ID>;https://<server>/extension/update.xml`
   - `ExtensionInstallSources`: `https://<server>/*`
5. Bij een nieuwe versie: verhoog `version` in `chrome-extension/manifest.json`, draai stap 2 opnieuw en vervang de bestanden. Edge werkt de extensie dan vanzelf bij, zonder ↻.

Bron: [Microsoft Learn – Self-host Microsoft Edge extensions](https://learn.microsoft.com/en-us/deployedge/microsoft-edge-manage-extensions-webstore)

## 4. Bewaking

- `/health` laat zien waar de gegevens heen gaan (`data_policy`).
- `/health/deep?token=<HEALTH_TOKEN>` opent een verbinding met Deepgram (EU) en controleert Mistral en Anthropic. Er gaan geen patiëntgegevens mee en het kost geen modeltokens. Bij een storing geeft hij HTTP 503.
- Laat een uptime-dienst (bijvoorbeeld UptimeRobot of Better Stack) die URL elke 5 minuten oproepen, met een melding naar je telefoon.
- Let op: `/health/deep` ziet niet of je Mistral-abonnement aan zijn limiet zit (fout 429). Dat merk je pas bij echt gebruik; kies daarom een betaald abonnement.
