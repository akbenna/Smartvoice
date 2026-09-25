# VitaScribe — Go-Live Deployment Guide

## Overzicht

- **Frontend**: Vercel (`vitascribe.vercel.app`; tot dat domein is toegevoegd draait hij op `smartvoice-nine.vercel.app`)
- **Backend API**: Railway (CPU-only container)
- **Database**: Railway PostgreSQL plugin
- **Cache**: Railway Redis plugin (optioneel, graceful fallback)
- **STT/LLM**: Cloud API's (Deepgram + Mistral/Claude) of eigen GPU-server

---

## Stap 1 — Railway Project Aanmaken

1. Ga naar [railway.app](https://railway.app) en log in met GitHub
2. Klik **New Project** → **Deploy from GitHub repo**
3. Selecteer je VitaScribe repository
4. Railway detecteert automatisch `railway.toml` en `Dockerfile.railway`

## Stap 2 — Database & Redis Toevoegen

In het Railway dashboard:

1. Klik **+ New** → **Database** → **PostgreSQL**
2. Railway maakt `DATABASE_URL` automatisch aan als env var
3. (Optioneel) Klik **+ New** → **Database** → **Redis**
4. Railway maakt `REDIS_URL` automatisch aan

## Stap 3 — Environment Variables Instellen

Ga naar je service → **Variables** en stel in:

```
# Verplicht
APP_ENV=production
APP_SECRET_KEY=<genereer: openssl rand -hex 32>

# CORS — je Vercel frontend URL. Alleen services/api leest deze variabele. De
# cloud-API die Railway draait (Dockerfile.railway: services.cloud_api) laat elke
# herkomst toe, omdat de extensie vanaf chrome-extension:// aanroept.
# Tijdens de overstap staan beide erin: het nieuwe adres en het huidige live adres.
# Het oude kan eruit zodra de frontend alleen nog op vitascribe.vercel.app draait.
CORS_ALLOWED_ORIGINS=https://vitascribe.vercel.app,https://smartvoice-nine.vercel.app

# Database — Railway vult DATABASE_URL automatisch in
# Je hoeft POSTGRES_* niet handmatig te zetten

# Eerste keer users aanmaken
SEED_ON_START=true
ADMIN_PASSWORD=<kies een sterk wachtwoord>
ARTS_PASSWORD=<kies een sterk wachtwoord>

# STT — Deepgram cloud API (geen GPU nodig)
CLOUD_STT_PROVIDER=deepgram
CLOUD_STT_API_KEY=<je Deepgram API key>

# LLM — Cloud fallback (geen lokale Ollama nodig)
CLOUD_FALLBACK_ENABLED=true
CLOUD_FALLBACK_PROVIDER=mistral
CLOUD_FALLBACK_API_KEY=<je Mistral API key>
CLOUD_FALLBACK_API_URL=https://api.mistral.ai/v1

# Audit
AUDIT_LOG_RETENTION_YEARS=5
```

> Na eerste deploy: zet `SEED_ON_START=false` om te voorkomen dat seed elke keer draait.

## Stap 4 — Deploy

Railway bouwt automatisch bij push naar main. Je kunt ook handmatig triggeren:

1. Push je code: `git push origin main`
2. Railway bouwt de Docker image (duurt ~2-3 minuten)
3. Health check op `/health` bevestigt dat de API draait
4. Je krijgt een Railway URL. Bij de praktijk is dat `smartvoice-production.up.railway.app`. Dat adres houdt de oude
   naam met opzet: het staat in de extensie-instellingen op elke werkplek en in het
   installatiebeleid, en een ander adres betekent op elke pc opnieuw instellen.

## Stap 5 — Frontend Koppelen aan Backend

In het **Vercel** dashboard:

1. Ga naar je VitaScribe frontend project → **Settings** → **Environment Variables**
2. Voeg toe:
   ```
   NEXT_PUBLIC_API_URL=https://smartvoice-production.up.railway.app
   ```
   (vervang met je daadwerkelijke Railway URL)
3. Klik **Redeploy** om de nieuwe env var actief te maken

## Stap 6 — Testen

1. Ga naar `https://vitascribe.vercel.app` (of, tot de overstap, `https://smartvoice-nine.vercel.app`)
2. Log in met `arts1` / het wachtwoord dat je hebt ingesteld
3. Test de health check: `curl https://<railway-url>/health`
4. Wijzig wachtwoorden na eerste login

---

## STT & LLM Strategie (zonder GPU)

Railway biedt geen GPU's. Je hebt twee opties voor de Whisper STT en Ollama LLM:

### Optie A: Cloud API's (aanbevolen voor start)

| Component | Service       | Kosten              |
|-----------|---------------|---------------------|
| STT       | Deepgram Nova | ~$0.0043/min        |
| LLM       | Mistral       | ~$0.002/1K tokens   |

Dit is de snelste manier om live te gaan. Configureer via de env vars hierboven.

### Optie B: Eigen GPU Server

Als je een GPU-machine hebt (lokaal of cloud VM met NVIDIA):

1. Installeer Ollama + Faster-Whisper op die machine
2. Stel `OLLAMA_HOST` en `WHISPER_HOST` in als Railway env vars die naar je GPU server wijzen
3. Zorg voor een VPN of SSH tunnel voor veilige verbinding

### Optie C: Hybride

Start met cloud API's, migreer later naar eigen GPU als het volume toeneemt.

---

## Kosten Inschatting (Railway)

| Component     | Railway Plan | Geschatte kosten/maand |
|---------------|-------------|------------------------|
| API Container | Hobby       | ~$5                    |
| PostgreSQL    | Plugin      | ~$5                    |
| Redis         | Plugin      | ~$3 (optioneel)        |
| **Totaal**    |             | **~$10-13/maand**      |

Plus STT/LLM API kosten afhankelijk van gebruik (~$5-20/maand voor kleine praktijk).

---

## Checklist voor Go-Live

- [ ] Railway project aangemaakt met GitHub repo
- [ ] PostgreSQL plugin toegevoegd
- [ ] Environment variables ingesteld
- [ ] `APP_SECRET_KEY` gegenereerd en ingesteld
- [ ] `CORS_ALLOWED_ORIGINS` wijst naar Vercel URL
- [ ] Eerste deploy geslaagd, `/health` geeft `{"status": "ok"}`
- [ ] Seed users aangemaakt, `SEED_ON_START` daarna op `false`
- [ ] Vercel `NEXT_PUBLIC_API_URL` wijst naar Railway URL
- [ ] Frontend opnieuw gedeployed
- [ ] Inloggen werkt via de frontend
- [ ] Wachtwoorden gewijzigd na eerste login
- [ ] STT API key (Deepgram) geconfigureerd
- [ ] LLM API key (Mistral) geconfigureerd

---

## Live dicteren (zijpaneel)

De Chrome-extensie heeft een dicteerpaneel naast Bricks (knop in de popup of **Alt+Shift+D**).
De tekst verschijnt terwijl je spreekt en gaat naar het Bricks-veld waarin je het laatst klikte.

**Railway-variabelen:**

```
DEEPGRAM_API_KEY=<je Deepgram API key>      # ook gebruikt voor live dicteren
LLM_PROVIDER=anthropic                      # voor "Opschonen" en "Maak SOEP"
# SOEP op Claude Sonnet 5 (standaard), opschonen op Haiku; zie .env.example
ANTHROPIC_API_KEY=<je Anthropic API key>
# Optioneel (standaardwaarden):
DICTATION_DEEPGRAM_URL=wss://api.eu.deepgram.com/v1/listen   # EU-verwerking
DICTATION_DEEPGRAM_MODEL=nova-3
DICTATION_MAX_SECONDS=600
```

Kies bij Railway een EU-regio voor de service, zodat audio de EU niet verlaat en de vertraging laag blijft.

**Eerste gebruik:** bij de eerste start opent een tabblad dat eenmalig om microfoontoestemming vraagt
(Chrome kan dat niet vanuit het zijpaneel zelf). Na een update van de extensie: ververs het Bricks-tabblad.

**Dicteren zonder zijpaneel:** klik in het Bricks-veld en druk **Alt+Shift+D** (of klik op het
extensie-icoon en dan "Dicteer in veld"). Een label rechtsonder toont dat VitaScribe luistert; nogmaals
Alt+Shift+D of "Stop" beëindigt het. Lukt invoegen niet, dan staat het dictaat op het klembord.
Met het zijpaneel open bedient dezelfde sneltoets het paneel.

**S/O/E/P per veld:** klik in Bricks in de S-regel en kies "Alles invoegen": S komt in die regel, O, E en P
in de regels daarna (een ICPC-codeveld ertussen krijgt de code). Wijkt de opmaak af, gebruik dan eenmalig
"S/O/E/P-velden koppelen" (popup of zijpaneel) en klik in Bricks achter elkaar in het S-, O-, E- en P-veld. Daarna vult "Alles invoegen" (zijpaneel), "Push naar Bricks"
(popup) en de invoegknop in Bricks elke regel in het eigen veld. Bestaande tekst blijft staan. Opnieuw
koppelen kan altijd, bijvoorbeeld als Bricks van opmaak verandert.

**Snelteksten & correcties:** via de link onderaan het paneel. Een commando ("normaal longen") wordt
vervangen door je standaardtekst; correcties verbeteren woorden die verkeerd verstaan worden en gaan als
hint mee naar Deepgram. Opgeslagen per computer (Chrome, lokaal); overzetten via Exporteren/Importeren.

**Endpoints:**
- `WS /api/v1/dictation/stream`: audio in, tekst terug (eerste bericht: `{"type":"auth","api_key":"..."}`)
- `POST /api/v1/dictation/process`: `{"text": "...", "mode": "clean" | "soep"}`
