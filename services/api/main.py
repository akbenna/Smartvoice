"""
AI-Consultassistent — API Gateway
==================================
FastAPI applicatie die alle services orkestreert.
"""

import uuid
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import structlog

# Lokale imports (worden beschikbaar via PYTHONPATH)
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "shared"))

from config.settings import config

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(
        logging.getLevelName(config.log_level)
    ),
)
logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Lifespan (startup/shutdown)
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting AI-Consultassistent API", env=config.env)
    # TODO: Initialiseer database pool
    # TODO: Initialiseer Redis connectie
    # TODO: Laad Whisper model (warm-up)
    # TODO: Verifieer Ollama bereikbaarheid
    yield
    logger.info("Shutting down AI-Consultassistent API")
    # TODO: Sluit connecties


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="AI-Consultassistent",
    description="Privacy-first AI-systeem voor consultdocumentatie in de huisartsenpraktijk",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.security.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------
class ConsultStartRequest(BaseModel):
    patient_hash: str = Field(..., description="SHA-256 hash van BSN")


class ConsultStartResponse(BaseModel):
    session_id: str
    status: str = "recording"


class ConsultStopResponse(BaseModel):
    session_id: str
    transcript_id: str | None = None
    status: str = "transcribing"


class SOEPConcept(BaseModel):
    S: str = ""
    O: str = ""
    E: str = ""
    P: str = ""
    icpc_code: str | None = None
    icpc_titel: str | None = None
    confidence: float | None = None


class RedFlag(BaseModel):
    id: str
    ernst: str
    categorie: str
    beschrijving: str
    nhg_referentie: str | None = None


class MissingInfo(BaseModel):
    id: str
    veld: str
    beschrijving: str
    prioriteit: str


class DetectionResult(BaseModel):
    rode_vlaggen: list[RedFlag] = []
    ontbrekende_info: list[MissingInfo] = []


class ApproveRequest(BaseModel):
    soep_final: SOEPConcept
    corrections: list[dict] = []


class ExportRequest(BaseModel):
    target: str = "clipboard"  # "clipboard" | "api"


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.1.0"
    services: dict = {}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Systeemstatus check."""
    # TODO: Check database, Redis, Ollama, GPU
    return HealthResponse(
        status="ok",
        version="0.1.0",
        services={
            "database": "unchecked",
            "redis": "unchecked",
            "ollama": "unchecked",
            "whisper": "unchecked",
        }
    )


@app.post("/api/consult/start", response_model=ConsultStartResponse)
async def start_consult(request: ConsultStartRequest):
    """Start een nieuw consult met audio-opname."""
    session_id = str(uuid.uuid4())
    logger.info("Consult gestart", session_id=session_id)

    # TODO: Maak consult record in database
    # TODO: Start audio capture stream
    # TODO: Log audit event

    return ConsultStartResponse(session_id=session_id)


@app.post("/api/consult/{session_id}/stop", response_model=ConsultStopResponse)
async def stop_consult(session_id: str):
    """Stop opname en start verwerkingspipeline."""
    logger.info("Consult gestopt, pipeline gestart", session_id=session_id)

    # TODO: Stop audio capture
    # TODO: Trigger transcriptie via event bus
    # TODO: Update consult status

    return ConsultStopResponse(session_id=session_id, status="transcribing")


@app.post("/api/consult/upload")
async def upload_audio(
    file: UploadFile = File(...),
    patient_hash: str = "",
):
    """Upload een audiobestand voor verwerking (MVP Fase 1)."""
    session_id = str(uuid.uuid4())

    # Validatie
    if not file.filename.endswith((".wav", ".mp3", ".m4a", ".ogg", ".flac")):
        raise HTTPException(400, "Ongeldig audioformaat. Gebruik WAV, MP3, M4A, OGG of FLAC.")

    # TODO: Sla audio op (encrypted)
    # TODO: Start pipeline: transcriptie → extractie → SOEP → detectie
    # TODO: Return job status

    logger.info("Audio geüpload", session_id=session_id, filename=file.filename)

    return {
        "session_id": session_id,
        "status": "processing",
        "message": "Audio ontvangen, verwerking gestart."
    }


@app.get("/api/consult/{session_id}/status")
async def get_consult_status(session_id: str):
    """Poll de verwerkingsstatus van een consult."""
    # TODO: Haal status uit database/Redis
    return {
        "session_id": session_id,
        "status": "reviewing",  # placeholder
        "steps": {
            "transcription": "completed",
            "extraction": "completed",
            "soep_generation": "completed",
            "detection": "completed",
        }
    }


@app.get("/api/consult/{session_id}/transcript")
async def get_transcript(session_id: str):
    """Haal het transcript op voor een consult."""
    # TODO: Haal uit database, controleer autorisatie
    return {
        "session_id": session_id,
        "segments": [],  # placeholder
        "model_version": config.whisper.model,
    }


@app.get("/api/consult/{session_id}/soep", response_model=SOEPConcept)
async def get_soep(session_id: str):
    """Haal het SOEP-concept op voor review."""
    # TODO: Haal uit database
    return SOEPConcept(
        S="Placeholder — wordt ingevuld door LLM pipeline",
        O="",
        E="",
        P="",
    )


@app.get("/api/consult/{session_id}/detection", response_model=DetectionResult)
async def get_detection(session_id: str):
    """Haal rode vlaggen en ontbrekende info op."""
    # TODO: Haal uit database
    return DetectionResult()


@app.post("/api/consult/{session_id}/approve")
async def approve_soep(session_id: str, request: ApproveRequest):
    """Keur SOEP-concept goed na review."""
    logger.info("SOEP goedgekeurd", session_id=session_id,
                corrections_count=len(request.corrections))

    # TODO: Sla definitieve SOEP op
    # TODO: Sla correcties op (feedbackloop)
    # TODO: Update status naar 'approved'
    # TODO: Log audit event

    return {
        "session_id": session_id,
        "status": "approved",
        "export_ready": True,
    }


@app.post("/api/consult/{session_id}/export")
async def export_to_his(session_id: str, request: ExportRequest):
    """Exporteer goedgekeurd SOEP naar HIS."""
    logger.info("Export naar HIS", session_id=session_id, target=request.target)

    # TODO: Genereer HIS-compatibele output
    # TODO: Bij target='clipboard': return formatted text
    # TODO: Bij target='api': stuur naar HIS API
    # TODO: Log audit event
    # TODO: Trigger audio-verwijdering (indien goedgekeurd)

    return {
        "session_id": session_id,
        "status": "exported",
        "target": request.target,
    }


@app.get("/api/consults")
async def list_consults(
    limit: int = 20,
    offset: int = 0,
    status: str | None = None,
):
    """Lijst van recente consulten voor de review-interface."""
    # TODO: Haal uit database met filters en paginatie
    return {
        "consults": [],
        "total": 0,
        "limit": limit,
        "offset": offset,
    }
