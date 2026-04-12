"""
SmartVoice Cloud API - Main Application

Lightweight FastAPI service for the Chrome extension.
Processes consultation audio -> SOEP + decisief regel.
Compatible with Python 3.9+.
"""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

import structlog
import uvicorn
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .auth import verify_api_key
from .config import get_config
from .pipeline import process_consultation

logger = structlog.get_logger()

app = FastAPI(
    title="SmartVoice Cloud API",
    description="Consult audio → SOEP + decisief regel voor Bricks Huisarts",
    version="1.0.0",
)

# ── CORS ──

config = get_config()
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Ensure temp directory exists ──

os.makedirs(config.temp_dir, exist_ok=True)


# ── Health check (no auth required) ──

@app.get("/health")
@app.get("/api/v1/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "smartvoice-cloud-api",
        "version": "1.0.0",
        "stt_provider": config.stt.default_provider,
        "llm_provider": config.llm.default_provider,
    }


# ── Main processing endpoint ──

@app.post("/api/v1/consult/process")
async def process_consult(
    audio: UploadFile = File(..., description="Audio bestand (webm, mp3, wav, m4a)"),
    stt_provider: str = Form(default=None, description="STT provider override"),
    llm_provider: str = Form(default=None, description="LLM provider override"),
    _api_key: str = Depends(verify_api_key),
):
    """Process a consultation audio recording through the full pipeline."""
    start_time = time.time()

    # Validate file size
    max_size = config.max_audio_size_mb * 1024 * 1024
    content = await audio.read()
    if len(content) > max_size:
        raise HTTPException(
            status_code=413,
            detail=f"Bestand te groot. Maximum is {config.max_audio_size_mb}MB.",
        )

    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Leeg audiobestand.")

    # Determine file extension
    ext = "webm"
    if audio.filename:
        ext = Path(audio.filename).suffix.lstrip(".") or ext
    elif audio.content_type:
        content_type_map = {
            "audio/webm": "webm",
            "audio/mp3": "mp3",
            "audio/mpeg": "mp3",
            "audio/wav": "wav",
            "audio/mp4": "m4a",
            "audio/ogg": "ogg",
        }
        ext = content_type_map.get(audio.content_type, ext)

    # Save to temp file
    with tempfile.NamedTemporaryFile(
        dir=config.temp_dir, suffix=f".{ext}", delete=False,
    ) as tmp:
        tmp.write(content)
        audio_path = Path(tmp.name)

    try:
        logger.info(
            "consult.process.start",
            file_size=len(content),
            file_ext=ext,
        )

        result = await process_consultation(
            audio_path=audio_path,
            stt_provider=stt_provider,
            llm_provider=llm_provider,
        )

        processing_time = time.time() - start_time
        logger.info(
            "consult.process.complete",
            processing_time_s=round(processing_time, 2),
        )

        response = result.to_dict()
        response["processing_time_secs"] = round(processing_time, 2)
        return response

    finally:
        # Always clean up temp file (privacy: no audio retention)
        try:
            audio_path.unlink(missing_ok=True)
        except OSError:
            pass


# ── Provider info endpoint ──

@app.get("/api/v1/providers")
async def list_providers(_api_key: str = Depends(verify_api_key)):
    """List available STT and LLM providers."""
    cfg = get_config()
    return {
        "stt": {
            "default": cfg.stt.default_provider,
            "available": {
                "groq": bool(cfg.stt.groq_api_key),
                "deepgram": bool(cfg.stt.deepgram_api_key),
                "openai": bool(cfg.stt.openai_api_key),
            },
        },
        "llm": {
            "default": cfg.llm.default_provider,
            "available": {
                "mistral": bool(cfg.llm.mistral_api_key),
                "anthropic": bool(cfg.llm.anthropic_api_key),
                "gemini": bool(cfg.llm.gemini_api_key),
            },
        },
    }


# ── Entry point ──

def main():
    cfg = get_config()
    uvicorn.run(
        "services.cloud_api.main:app",
        host=cfg.host,
        port=cfg.port,
        reload=cfg.debug,
    )


if __name__ == "__main__":
    main()
