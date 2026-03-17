# SmartVoice — Go-Live Deployment Guide

## Overzicht

- **Frontend**: Vercel (`smartvoice-nine.vercel.app`) — al live
- **Backend API**: Railway (CPU-only container)
- **Database**: Railway PostgreSQL plugin
- **Cache**: Railway Redis plugin (optioneel, graceful fallback)
- **STT/LLM**: Cloud API's (Deepgram + Mistral/Claude) of eigen GPU-server

---

## Stap 1 — Railway Project Aanmaken

1. Ga naar [railway.app](https://railway.app) en log in met GitHub
2. Klik **New Project** → **Deploy from GitHub repo**
3. Selecteer je SmartVoice repository
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

# CORS — je Vercel frontend URL
CORS_ALLOWED_ORIGINS=https://smartvoice-nine.vercel.app

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
4. Je krijgt een Railway URL, bijv. `smartvoice-api-production.up.railway.app`

## Stap 5 — Frontend Koppelen aan Backend

In het **Vercel** dashboard:

1. Ga naar je SmartVoice frontend project → **Settings** → **Environment Variables**
2. Voeg toe:
   ```
   NEXT_PUBLIC_API_URL=https://smartvoice-api-production.up.railway.app
   ```
   (vervang met je daadwerkelijke Railway URL)
3. Klik **Redeploy** om de nieuwe env var actief te maken

## Stap 6 — Testen

1. Ga naar `https://smartvoice-nine.vercel.app`
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
