# Naslag en patiëntuitleg uit ProVita Care

Bij de ICPC-code die de huisarts vastlegt, toont het zijpaneel naast de Thuisarts-link nog twee soorten links. De eerste is een naslagdeel in ProVita Care voor de arts: protocollen, doseringstabellen en vergoedingen. De tweede is een uitlegfilmpje dat de arts de patiënt kan laten zien. Het werkt precies als de Thuisarts-koppeling: een vaste tabel (`chrome-extension/lib/beslistools-icpc.json`), geen taalmodel, en VitaScribe rekent zelf niets uit.

## Wat er wel en niet in staat, en waarom

Klinische suggesties staan in VitaScribe uit (`data_policy.clinical_decision_support`). Een link bij de code die de arts zelf kiest, is geen suggestie. Maar de tool achter de link kan er wel een zijn. Daarom bevat de tabel alleen:

| Soort | Wat | Codes (voorstel) |
|---|---|---|
| Naslag | Farmacowijzer: diabetes, hartfalen, COPD, astma, nierfunctie, ABCD-groepen | T90, K77, R95, R96, U99.01, K86/K87 |
| Naslag | Vergoedingen: GLP-1, PCSK9-remmers, sacubitril/valsartan | T90, T93, K77 |
| Patiënt | Zestien animaties uit het patiëntdeel van ProVita (voeding, bewegen, roken, overgang, botten) | T82/T83, T90, K86/K87, T93, K74-K76, P17, X11, L95 |

Bewust niet in de tabel staan de tools die met gegevens van één patiënt een advies of score maken:
- de Smart Adviseur van de Farmacowijzer, de PCCV-score, de Nierschade Tool en de CVA-nazorgindex;
- de rekenhulpen (ADHD, opioïden, benzo-afbouw, wisselen van antidepressiva);
- de keuzehulpen (anticonceptie, menopauze, obesitas);
- de AI-consultvoorbereiding.

Die vallen waarschijnlijk onder MDR-regel 11, en geen ervan heeft een CE-markering. Een test (`tests/js/beslistools.test.js`) weigert elke regel die daarheen wijst. ProVita Care zelf opent via een link alleen de naslagtabbladen van de Farmacowijzer (`src/lib/deeplink.js` in die repo).

## Aanzetten

Een regel verschijnt pas als een arts hem heeft nagekeken: de link geopend en gezien dat de inhoud bij de code past.

```bash
python3 scripts/beslistools_tabel.py --toon                          # wat staat nog open
python3 scripts/beslistools_tabel.py --controleer fw-copd --door AB  # een regel aanzetten
python3 scripts/beslistools_tabel.py --intrekken fw-copd             # weer uitzetten
```

Daarna een nieuwe versie van de extensie uitbrengen. De tabel zit in de extensie zelf, en voor het opzoeken gaat niets het netwerk op.

## Wat de arts ziet

Onder de SOEP-regel staat eerst "Naslag in ProVita Care (geen advies voor deze patiënt)", met groene links, en daaronder "Uitleg voor de patiënt", met paarse links.
- **Naslaglink:** die opent ProVita Care. Wie nog niet is ingelogd, komt na het inloggen op het goede tabblad terecht.
- **Uitleglink:** die opent een openbare animatie.

Bij een klik gaat één gebruiksregel naar de server, met alleen de handeling en de hoofdrubriek, net als bij Thuisarts.
