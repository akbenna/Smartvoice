# Licentiebeheer VitaScribe

VitaScribe kan nu ook aan andere praktijken worden aangeboden. Een praktijk meldt zich aan, jij activeert haar in het beheer, en elke gebruiker krijgt een eigen sleutel. Dat is hetzelfde systeem als bij Bricks Companion, met één verschil: het register staat op de VitaScribe-server en niet in de extensie.

Bricks Companion heeft geen server en moest daarom werken met ondertekende codes die offline worden gecontroleerd. VitaScribe werkt toch al alleen via de server, dus daar komt geen nieuwe gegevensstroom bij. Het register op de server heeft drie voordelen:

- Een praktijk of gebruiker zet je direct uit. Je hoeft niet te wachten tot een code verloopt.
- Je ziet wie VitaScribe werkelijk gebruikt, en wanneer.
- Het register gaat niet verloren als je de extensie opnieuw installeert.

## Directe links

| Wat | Waar |
|---|---|
| Beheerpagina | `https://<server>/beheer` |
| Aanmeldformulier voor praktijken | `https://<server>/aanmelden` |
| Licentiecontrole | `services/cloud_api/licentie.py` |
| Beheer en aanmelden | `services/cloud_api/beheer.py`, `services/cloud_api/aanmelden.py` |
| Eigen sleutels van praktijken | `services/cloud_api/praktijk_sleutels.py`, `services/cloud_api/kluis.py` |
| Schema | `services/cloud_api/register_schema.sql` |
| Praktijknummer in de extensie | `chrome-extension/lib/praktijk.js` |

## Aanzetten op Railway

1. **Database.** Voeg in het Railway-project een PostgreSQL toe (+ New → Database → PostgreSQL). Koppel de variabele `DATABASE_URL` aan de service van de cloud-API. Bij de eerste start maakt de server zelf de tabellen aan.
2. **Beheersleutel.** Zet `ADMIN_KEY` op een lange willekeurige waarde (`openssl rand -hex 32`). Die sleutel opent de beheerpagina; bewaar hem in je wachtwoordmanager.
3. **Kluis voor eigen sleutels.** Zet `SLEUTELKLUIS` op een Fernet-sleutel:
   ```bash
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```
   Zonder kluis kunnen praktijken geen eigen AI-sleutels opslaan; de rest werkt dan wel.
4. **Deploy**, en open `https://<server>/health`: daar hoort `"register": true` te staan. `/health/deep` controleert ook de database.

**Wat er niet verandert:**
- De sleutels in `API_USERS` en `API_KEYS` blijven werken, zoals je eigen sleutel bij Het Roosendael. Je eigen praktijk valt dus niet stil als het register aangaat.
- Staat er geen `DATABASE_URL`, dan werkt de server zoals voorheen.

**Wat er wel verandert:** met het register aan bestaat de ontwikkelmodus niet meer. Daarin werkte alles zonder sleutel zolang er geen sleutels in de omgeving stonden.

## Dagelijks beheer

**Een praktijk meldt zich aan** via `/aanmelden`. Ze vult in: naam, plaats, het Bricks-praktijknummer, een contactpersoon, het aantal huisarts-FTE en het aantal werkplekken. Patiëntgegevens worden niet gevraagd. De praktijk verschijnt in het beheer onder **Aanmeldingen**, met status *aangemeld* en licentietype *kandidaat*.

**Activeren.** Klik op de praktijk en controleer de gegevens, vooral het **praktijknummer**. Klik dan op **Activeren als pilot (12 maanden)**. Voor een betalende praktijk kies je het licentietype *Betaald*, en voor je eigen praktijk *Eigen praktijk / intern*. Alleen dat laatste type mag onbeperkt geldig zijn.

**Gebruikers aanmaken.** Voeg per gebruiker een naam toe en klik op **Toevoegen en sleutel maken**. De sleutel verschijnt één keer, samen met een kant-en-klaar bericht met het serveradres, de sleutel en de installatiestappen. Stuur dat bericht via een beveiligde mail. De server bewaart alleen de sha256 van de sleutel, dus een kwijtgeraakte sleutel is niet terug te halen. Maak in dat geval een nieuwe sleutel: de oude werkt dan meteen niet meer.

**Praktijkbeheerder.** Geef één gebruiker per praktijk de rol *Praktijkbeheerder*. Die kan in de extensie de eigen AI-sleutels van de praktijk instellen.

**Verlengen en uithalen.**
- **Verlengen met 12 maanden** telt vanaf de huidige einddatum, of vanaf vandaag als die al voorbij is.
- **Uithalen** zet alle sleutels van de praktijk binnen een halve minuut uit.
- Een gebruiker zet je apart uit met **Uitzetten**.

**Instellingen, export en logboek** staan onder aan de pagina:
- Het tarief per huisarts-FTE per jaar. De tegels bovenaan rekenen daarmee de licentie-omzet uit, en wat de pilots samen waard zijn.
- Het serveradres en de winkellink die in het bericht aan gebruikers komen.
- Een export van het register als JSON, om naast de database te bewaren.
- Het logboek van alle beheerhandelingen, zonder sleutels.

## Praktijkbinding

Het praktijknummer staat in de Bricks-URL: `https://groep06.brickshuisarts.nl/2876/login` hoort bij praktijk 2876. De extensie leest het uit de hostnaam en het eerste deel van het pad, en stuurt het bij elke aanroep mee (kop `X-Bricks-Praktijk`, en bij dicteren in het aanmeldbericht). Dossier- en consultnummers staan dieper in het pad; die gaan nooit mee.

Noemt de licentie praktijknummers en hoort het dossier herkenbaar bij een ándere praktijk, dan weigert de server: *"Deze licentie geldt voor praktijknummer 2876; dit Bricks-dossier hoort bij praktijk 4410."* Ziet de extensie geen nummer, dan gaat de aanroep gewoon door. Een huisarts mag nooit midden in het spreekuur worden geblokkeerd omdat Tetra de URL-opbouw verandert. Dezelfde veiligheidsklep zit in Bricks Companion.

Activeer je een praktijk zonder praktijknummer, dan waarschuwt de beheerpagina: die sleutels werken dan bij elke praktijk.

## Eigen AI-sleutels van een praktijk

Afgesproken op 26 september 2026:

| Dienst | Aanbieders | Waarvoor | Zonder eigen sleutel |
|---|---|---|---|
| Brieven | Claude (Anthropic), ChatGPT (OpenAI) | Alleen informatie- en verwijsbrieven, die gepseudonimiseerd zijn | Via de sleutel van de server (Claude) |
| Spraak | Deepgram | Dicteren en consultopnames, EU-eindpunt, training uit | Via de Deepgram-sleutel van de server |

Dictaat, SOEP, consultverslag en schermafdrukken gaan **nooit** over een eigen sleutel: daaruit is een patiënt te herkennen, en die blijven bij het EU-model van de server (Mistral). Dat staat in de code (`llm_service.stream_llm` weigert een praktijksleutel voor Mistral), niet alleen in een afspraak.

De praktijkbeheerder plakt de sleutel in de instellingen van de extensie onder *Eigen AI-sleutels van de praktijk*. De server controleert de sleutel bij de aanbieder met een lijstopvraging die niets verbruikt. Daarna versleutelt hij de sleutel met `SLEUTELKLUIS` en slaat hem op. In de browser blijft niets staan, en de extensie en de beheerpagina tonen alleen de laatste vier tekens. Jij kunt een eigen sleutel van een praktijk verwijderen, maar niet lezen.

Zet je bij een praktijk **Eigen AI-sleutels verplicht** aan, dan draaien brieven en spraak alleen nog op de sleutels van die praktijk. Heeft ze die niet ingesteld, dan geeft de extensie een duidelijke melding. Dat past bij betalende praktijken; pilots draaien op jouw sleutels.

Voor ChatGPT staan de modellen in `OPENAI_LETTERS_MODEL` (standaard `gpt-4.1-mini`) en `OPENAI_LETTERS_QUALITY_MODEL` (standaard `gpt-4.1`). Controleer vóór de eerste betalende praktijk of die modellen nog worden aangeboden.

**Kluissleutel vervangen:** zet de nieuwe vooraan in `SLEUTELKLUIS` en laat de oude erachter staan (`nieuw,oud`). Opgeslagen sleutels blijven zo leesbaar. Pas als alle praktijken hun sleutel opnieuw hebben opgeslagen, kan de oude eruit.

## Wat de gebruiker ziet

| Situatie | Melding in de extensie |
|---|---|
| Geldige licentie | Instellingen → Licentie: "Voor Praktijk X (gratis pilot), geldig tot …" |
| Praktijk nog niet geactiveerd of uitgehaald | "De licentie van Praktijk X is niet actief. …" |
| Licentie verlopen | "De licentie van Praktijk X is verlopen op …. Neem contact op voor verlenging." |
| Gebruiker uitgezet | "Deze sleutel is uitgezet. Vraag de beheerder van VitaScribe om een nieuwe." |
| Dossier van een andere praktijk | "Deze licentie geldt voor praktijknummer …; dit Bricks-dossier hoort bij praktijk …" |
| Eigen sleutels verplicht, maar niet ingesteld | "Uw praktijk schrijft brieven met een eigen AI-sleutel. …" |

## Beveiliging in het kort

- Sleutels van gebruikers bestaan alleen als sha256 in de database.
- Eigen AI-sleutels van praktijken staan er alleen versleuteld in, met een kluissleutel die niet in de database staat.
- De beheerpagina wordt geserveerd met een strikte Content-Security-Policy, `X-Frame-Options: DENY` en `no-store`. Na tien foute pogingen blokkeert de server dat adres een kwartier.
- Gegevens uit een aanmelding komen altijd als tekst in de pagina, nooit als HTML. Iemand die code in een praktijknaam stopt, ziet die code als tekst terug.
- Aanmelden is begrensd op vijf per adres per uur en vijftig per dag, met een verborgen veld tegen robots.
- Na uitzetten werkt een sleutel hooguit dertig seconden door; zo lang bewaart de server een opgezochte sleutel.
- Valt de database even weg, dan blijft een sleutel die het afgelopen uur nog klopte, werken. Een onbekende sleutel krijgt dan de melding dat de licentiecontrole even niet bereikbaar is.
- Activeer je een praktijk zonder einddatum, dan krijgt de licentie twaalf maanden. Alleen het type *Eigen praktijk / intern* blijft dan onbeperkt geldig.
