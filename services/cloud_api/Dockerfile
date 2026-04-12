FROM python:3.12-slim

WORKDIR /app

# Install curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY services/cloud_api/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Copy cloud API service
COPY services/__init__.py /app/services/__init__.py
COPY services/cloud_api/ /app/services/cloud_api/

ENV PYTHONPATH=/app

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8002/health || exit 1

EXPOSE ${PORT:-8002}

CMD uvicorn services.cloud_api.main:app --host 0.0.0.0 --port ${PORT:-8002}
