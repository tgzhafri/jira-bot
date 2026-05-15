# =============================================================================
# Multi-stage Dockerfile for Atlassian Bot (Streamlit Web UI)
# =============================================================================

# ---------------------------------------------------------------------------
# Stage 1: Builder — install Python dependencies
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ---------------------------------------------------------------------------
# Stage 2: Runtime — Streamlit application
# ---------------------------------------------------------------------------
FROM python:3.11-slim

WORKDIR /app

# Install curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY src/ ./src/
COPY app.py .
COPY setup.py .
COPY README.md .
COPY .streamlit/ ./.streamlit/

# Install the package (registers entry points)
RUN pip install --no-cache-dir -e .

# Create directories for runtime data
RUN mkdir -p /app/reports /app/.cache

ENV PYTHONUNBUFFERED=1

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl --fail http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--browser.gatherUsageStats=false"]
