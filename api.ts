# =============================================================================
# AI-Consultassistent — Environment Configuration
# =============================================================================
# Kopieer naar .env en pas aan voor jouw omgeving.
# BEWAAR DIT BESTAND NOOIT IN VERSIEBEHEER MET INGEVULDE WAARDEN.
# =============================================================================

# --- Algemeen ---
APP_ENV=development
APP_LOG_LEVEL=INFO
APP_SECRET_KEY=CHANGE_ME_GENERATE_WITH_openssl_rand_hex_32

# --- Database (PostgreSQL) ---
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=consultassistent
POSTGRES_USER=ca_app
POSTGRES_PASSWORD=CHANGE_ME
# Encryptie-sleutel voor pgcrypto kolommen (AES-256)
DB_ENCRYPTION_KEY=CHANGE_ME_GENERATE_WITH_openssl_rand_hex_32

# --- Redis ---
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=CHANGE_ME

# --- Whisper STT ---
WHISPER_MODEL=large-v3-turbo
# Of voor optimaal Nederlands: whisper-large-v3-high-mixed-nl
WHISPER_MODEL_PATH=/models/whisper
WHISPER_DEVICE=cuda
WHISPER_COMPUTE_TYPE=float16
WHISPER_LANGUAGE=nl
WHISPER_BEAM_SIZE=5

# --- Diarisatie (PyAnnote) ---
DIARIZATION_ENABLED=true
# HuggingFace token nodig voor PyAnnote model download
HF_TOKEN=CHANGE_ME

# --- Ollama (LLM) ---
OLLAMA_HOST=http://host.docker.internal:11434
OLLAMA_MODEL=llama3.3:8b-instruct-q4_K_M
# Fallback model (optioneel, zwaarder)
OLLAMA_FALLBACK_MODEL=llama3.3:70b-instruct-q4_K_M

# --- Cloud Fallback (standaard UIT) ---
CLOUD_FALLBACK_ENABLED=false
# Alleen Europees gehoste API's
CLOUD_FALLBACK_PROVIDER=mistral
CLOUD_FALLBACK_API_KEY=
CLOUD_FALLBACK_API_URL=https://api.mistral.ai/v1
# Drempel: confidence onder deze waarde triggert fallback-optie
CLOUD_FALLBACK_CONFIDENCE_THRESHOLD=0.6

# --- Audio Capture ---
AUDIO_SAMPLE_RATE=16000
AUDIO_FORMAT=wav
AUDIO_MAX_DURATION_SECONDS=3600
# Pad voor tijdelijke audio-opslag (encrypted volume)
AUDIO_STORAGE_PATH=/data/audio

# --- Export ---
HIS_EXPORT_MODE=clipboard
# HIS_EXPORT_API_URL=  # Indien API-koppeling beschikbaar

# --- Audit ---
AUDIT_LOG_RETENTION_YEARS=5
AUDIT_LOG_PATH=/data/audit

# --- Frontend ---
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_APP_NAME=AI-Consultassistent

# --- Beveiliging ---
CORS_ALLOWED_ORIGINS=http://localhost:3000
SESSION_TIMEOUT_MINUTES=30
MAX_LOGIN_ATTEMPTS=5
