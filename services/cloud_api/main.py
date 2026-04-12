"""
SmartVoice Cloud API — FastAPI Application
=============================================
Lichtgewicht API die de Chrome Extension bedient.
Endpoint: POST /api/v1/consult/process
  - Ontvangt audio (multipart/form-data)
  - Draait pipeline: STT → SOEP → decisief → rode vlaggen
  - Retourneert JSON met transcript, SOEP, decisief regel
"""

import logging
import sys

from fastapi import Depends, FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from services.cloud_api.auth import verify_api_key
from services.cloud_api.config import config
from services.cloud_api.pipeline import process_consultation

# ── Logging ────────────────────────────────────────────────────────

logging.basicConfig(
    level=getattr(logging, config.api.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("smartvoice.api")

# ── FastAPI app ────────────────────────────────────────────────────

app = FastAPI(
    title="SmartVoice Cloud API",
    version="0.1.0",
    description=(
        "AI Consultassistent voor de huisartsenpraktijk. "
        "Zet consultatie-audio om naar SOEP-documentatie en een decisiefe journaalregel."
    ),
)

# CORS — Chrome Extension heeft dit nodig
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.api.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health check ───────────────────────────────────────────────────

@app.get("/health")
async def health():
    """Eenvoudige health check voor monitoring."""
    return {
        "status": "ok",
        "service": "smartvoice-cloud-api",
        "version": "0.1.0",
    }


# ── Providers info ─────────────────────────────────────────────────

@app.get("/api/v1/providers")
async def list_providers(api_key: str = Depends(verify_api_key)):
    """Beschikbare STT en LLM providers."""
    return {
        "stt": {
            "default": config.stt.default_provider,
            "available": ["groq", "deepgram", "openai"],
        },
        "llm": {
            "default": config.llm.default_provider,
            "available": ["mistral", "anthropic", "gemini"],
        },
    }


# ── Hoofdendpoint: consult verwerken ───────────────────────────────

@app.post("/api/v1/consult/process")
async def process_consult(
    audio: UploadFile = File(..., description="Audio-opname van het consult (webm/wav/mp3)"),
    stt_provider: str = Form(default="", description="STT provider (groq/deepgram/openai)"),
    llm_provider: str = Form(default="", description="LLM provider (mistral/anthropic/gemini)"),
    skip_red_flags: bool = Form(default=False, description="Sla rode vlaggen detectie over"),
    api_key: str = Depends(verify_api_key),
):
    """
    Verwerk een consultatie-opname.

    Accepteert audio als multipart upload. Retourneert:
    - transcript: ruwe transcriptie
    - soep: gestructureerd SOEP-verslag (S/O/E/P)
    - decisief: één-regel journaalsamenvatting
    - red_flags: eventuele alarmsymptomen
    - meta: verwerkingsinformatie
    """
    # Valideer bestandsgrootte
    audio_bytes = await audio.read()
    max_bytes = config.api.max_audio_mb * 1024 * 1024

    if len(audio_bytes) > max_bytes:
        return JSONResponse(
            status_code=413,
            content={
                "error": f"Audio te groot: {len(audio_bytes) / 1024 / 1024:.1f} MB "
                         f"(max {config.api.max_audio_mb} MB)"
            },
        )

    if len(audio_bytes) < 1000:
        return JSONResponse(
            status_code=400,
            content={"error": "Audio te kort of leeg bestand."},
        )

    logger.info(
        "Consult verwerking gestart: %.1f MB, stt=%s, llm=%s",
        len(audio_bytes) / 1024 / 1024,
        stt_provider or "default",
        llm_provider or "default",
    )

    # Draai de pipeline
    result = await process_consultation(
        audio_bytes=audio_bytes,
        filename=audio.filename or "audio.webm",
        stt_provider_name=stt_provider or None,
        llm_provider_name=llm_provider or None,
        skip_red_flags=skip_red_flags,
    )

    # Foutafhandeling
    if result.error:
        logger.warning("Pipeline fout: %s", result.error)
        return JSONResponse(
            status_code=422,
            content={
                "error": result.error,
                "partial": result.to_dict(),
            },
        )

    return result.to_dict()


# ── Transcript-only endpoint (goedkoper) ──────────────────────────

@app.post("/api/v1/consult/transcribe")
async def transcribe_only(
    audio: UploadFile = File(...),
    stt_provider: str = Form(default=""),
    api_key: str = Depends(verify_api_key),
):
    """
    Alleen transcriptie, zonder SOEP-generatie.
    Goedkoper — geen LLM-kosten.
    """
    from services.cloud_api.stt_service import get_stt_provider

    audio_bytes = await audio.read()
    max_bytes = config.api.max_audio_mb * 1024 * 1024

    if len(audio_bytes) > max_bytes:
        return JSONResponse(
            status_code=413,
            content={"error": f"Audio te groot (max {config.api.max_audio_mb} MB)"},
        )

    try:
        stt = get_stt_provider(stt_provider or None)
        transcript = await stt.transcribe(audio_bytes, audio.filename or "audio.webm")
        return {"transcript": transcript, "stt_provider": stt_provider or "default"}
    except Exception as exc:
        logger.exception("Transcriptie fout: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"error": str(exc)},
        )


# ── Uvicorn runner ─────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "services.cloud_api.main:app",
        host=config.api.host,
        port=config.api.port,
        reload=True,
        log_level=config.api.log_level.lower(),
    )
