# =============================================================================
# AI-Consultassistent — Python Dependencies
# =============================================================================

# --- Web Framework ---
fastapi==0.115.6
uvicorn[standard]==0.34.0
python-multipart==0.0.18

# --- Database ---
asyncpg==0.30.0
sqlalchemy[asyncio]==2.0.36
alembic==1.14.1

# --- Redis ---
redis[hiredis]==5.2.1

# --- Speech-to-Text ---
faster-whisper==1.1.0
# Voor Nederlands-geoptimaliseerd model:
# transformers==4.47.0
# torch==2.5.1

# --- Diarisatie ---
pyannote.audio==3.3.2

# --- LLM Client ---
httpx==0.28.1
ollama==0.4.4

# --- Audio Processing ---
soundfile==0.12.1
librosa==0.10.2.post1

# --- Security ---
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
cryptography==44.0.0

# --- Validatie ---
pydantic==2.10.3
jsonschema==4.23.0

# --- Logging & Monitoring ---
structlog==24.4.0

# --- Utilities ---
python-dotenv==1.0.1
aiofiles==24.1.0
