# =============================================================================
# AI-Consultassistent — Backend Services
# =============================================================================
# Multi-stage build: Python 3.12 + CUDA runtime voor Whisper/PyAnnote
# Build context: project root (niet services/)
# =============================================================================

FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04 AS base

# Systeemafhankelijkheden
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.12 \
    python3.12-venv \
    python3-pip \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python setup
RUN python3.12 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Dependencies
COPY services/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Applicatie
WORKDIR /app
COPY services/ /app/services/
COPY shared/ /app/shared/

# Shared modules beschikbaar maken
ENV PYTHONPATH="/app"

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000

CMD ["uvicorn", "services.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
