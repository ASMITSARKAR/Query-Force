# Stage 1: Builder
FROM python:3.11-slim as builder

WORKDIR /app
ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: Runtime
FROM python:3.11-slim as runtime

WORKDIR /app

# Add curl for healthchecks
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy packages from builder
COPY --from=builder /opt/venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONPATH=/app

# Create non-root user with a home directory
RUN groupadd -r appuser && useradd -m -r -g appuser appuser && chown -R appuser:appuser /app

# Switch to the non-root user so all subsequent commands cache in /home/appuser
USER appuser

# Copy application source
COPY --chown=appuser:appuser src/ /app/src/
COPY --chown=appuser:appuser ui/ /app/ui/
COPY --chown=appuser:appuser scripts/ /app/scripts/
COPY --chown=appuser:appuser data/ /app/data/

# Ensure data directories exist, ingest the schema, and download the ONNX model
RUN mkdir -p /app/data/chroma_persist && \
    GROQ_API_KEY="dummy" QUERYFORCE_API_KEY="dummy" python scripts/ingest_schema.py && \
    python -c "from chromadb.utils.embedding_functions import DefaultEmbeddingFunction; DefaultEmbeddingFunction()"

EXPOSE 8000

CMD sh -c "uvicorn src.api.server:app --host 0.0.0.0 --port ${PORT:-8000}"
