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
from typing import Literal, Optional

import httpx
import structlog
import uvicorn
from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    WebSocket,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from .auth import verify_api_key
from .config import get_config
from .dictation import relay_dictation
from . import llm_service
from .medical_vocabulary import (
    add_custom_correction,
    correct_transcript_full,
    get_hotwords,
    load_custom_vocabulary,
    save_custom_vocabulary,
)
from .pipeline import _parse_json_response, process_consultation
from .prompts import (
    DICTAAT_OPSCHONEN_SYSTEM_PROMPT,
    DICTAAT_OPSCHONEN_USER_TEMPLATE,
    DICTAAT_SOEP_SYSTEM_PROMPT,
    DICTAAT_SOEP_USER_TEMPLATE,
    SOEP_JSON_SCHEMA,
    DICTAAT_SOEP_JSON_SCHEMA,
)

logger = structlog.get_logger()

app = FastAPI(
    title="SmartVoice Cloud API",
    description="Consult audio → SOEP + decisief regel voor Bricks Huisarts",
    version="1.0.0",
)

# ── CORS ──

config = get_config()

# Chrome-extension:// origins are NOT matched by allow_origins=["*"].
# Use allow_origin_regex to match everything including chrome-extension://.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r".*",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Permissions-Policy header ──
# Allow microphone access for pages served from this API (e.g. /debug).
# This tells browsers that microphone usage is explicitly permitted.

@app.middleware("http")
async def add_permissions_policy(request: Request, call_next):
    response = await call_next(request)
    response.headers["Permissions-Policy"] = "microphone=*"
    return response


# ── Ensure temp directory exists ──

os.makedirs(config.temp_dir, exist_ok=True)

# ── Load custom vocabulary if available ──

_custom_vocab_path = Path(config.temp_dir) / "custom_vocabulary.json"
if _custom_vocab_path.exists():
    load_custom_vocabulary(_custom_vocab_path)


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
            file_size_kb=round(len(content) / 1024, 1),
            file_ext=ext,
            content_type=audio.content_type,
            filename=audio.filename,
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


# ── Live dictation (side panel) ──

# Output-budgetten: een dictaat is kort, dus ruim genoeg maar begrensd.
DICTAAT_OPSCHONEN_MAX_TOKENS = 1200
DICTAAT_SOEP_MAX_TOKENS = 900
DICTAAT_MAX_CHARS = 20000


@app.websocket("/api/v1/dictation/stream")
async def dictation_stream(ws: WebSocket):
    """Live dictation: audio in, transcript text out while speaking."""
    await relay_dictation(ws)


class DictationProcessRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=DICTAAT_MAX_CHARS)
    mode: Literal["clean", "soep"]
    llm_provider: Optional[str] = None


@app.post("/api/v1/dictation/process")
async def process_dictation(
    body: DictationProcessRequest,
    _api_key: str = Depends(verify_api_key),
):
    """Dictaat licht opschonen (clean) of omzetten naar een SOEP-regel (soep)."""
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Leeg dictaat.")

    start_time = time.time()
    try:
        if body.mode == "clean":
            cleaned = await llm_service.complete(
                system_prompt=DICTAAT_OPSCHONEN_SYSTEM_PROMPT,
                user_prompt=DICTAAT_OPSCHONEN_USER_TEMPLATE.format(dictaat=text),
                provider=body.llm_provider,
                max_tokens=DICTAAT_OPSCHONEN_MAX_TOKENS,
            )
            result = {"mode": "clean", "text": cleaned.strip()}
        else:
            raw = await llm_service.complete(
                system_prompt=DICTAAT_SOEP_SYSTEM_PROMPT,
                user_prompt=DICTAAT_SOEP_USER_TEMPLATE.format(dictaat=text),
                provider=body.llm_provider,
                json_mode=True,
                max_tokens=DICTAAT_SOEP_MAX_TOKENS,
                quality=True,
                json_schema=DICTAAT_SOEP_JSON_SCHEMA,
            )
            data = _parse_json_response(raw)
            soep = {
                key: str(data.get(key) or "").strip()
                for key in ("s", "o", "e", "p", "icpc_code", "icpc_titel")
            }
            points = data.get("aandachtspunten")
            soep["aandachtspunten"] = [
                str(x).strip() for x in points if str(x or "").strip()
            ][:4] if isinstance(points, list) else []
            result = {"mode": "soep", "soep": soep}
    except (ValueError, httpx.HTTPError) as exc:
        # Missing provider key, provider error or unparseable model output.
        logger.error("dictation.process_error", mode=body.mode, error=str(exc))
        raise HTTPException(status_code=502, detail=f"Verwerking mislukt: {exc}")

    result["processing_time_secs"] = round(time.time() - start_time, 2)
    return result


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


# ── Vocabulary management endpoints ──


@app.get("/api/v1/vocabulary/hotwords")
async def get_vocabulary_hotwords(_api_key: str = Depends(verify_api_key)):
    """Geeft de hotwords-string voor VibeVoice-ASR (toekomstig)."""
    return {"hotwords": get_hotwords()}


@app.post("/api/v1/vocabulary/correction")
async def add_vocabulary_correction(
    wrong: str = Form(..., description="Verkeerde transcriptie"),
    correct: str = Form(..., description="Correcte spelling"),
    _api_key: str = Depends(verify_api_key),
):
    """
    Voeg een correctie toe aan de custom woordenlijst.
    Onderdeel van de feedbackloop: arts corrigeert -> systeem leert.
    """
    add_custom_correction(wrong, correct)

    # Persist naar disk
    custom_path = Path(get_config().temp_dir) / "custom_vocabulary.json"
    save_custom_vocabulary(custom_path)

    return {
        "status": "ok",
        "wrong": wrong,
        "correct": correct,
        "message": f"Correctie toegevoegd: '{wrong}' → '{correct}'",
    }


@app.post("/api/v1/vocabulary/test")
async def test_vocabulary_correction(
    text: str = Form(..., description="Tekst om te corrigeren"),
    _api_key: str = Depends(verify_api_key),
):
    """Test de woordenlijstcorrectie op een stuk tekst."""
    corrected, stats = correct_transcript_full(text)
    return {
        "original": text,
        "corrected": corrected,
        "total_corrections": stats.total_corrections,
        "corrections": [
            {"from": wrong, "to": correct}
            for wrong, correct in stats.corrections_applied
        ],
    }


# ── Debug test page ──

@app.get("/debug", response_class=HTMLResponse)
async def debug_page():
    """Serve the debug test page."""
    debug_html = Path(__file__).parent / "debug_test.html"
    if debug_html.exists():
        return debug_html.read_text(encoding="utf-8")
    return "<h1>debug_test.html niet gevonden</h1>"


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
