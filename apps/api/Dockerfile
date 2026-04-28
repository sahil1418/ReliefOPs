# ─────────────────────────────────────────────────────────────────────────────
# ReliefOps API · production image
# Used by both Render (free tier) and Cloud Run.
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# OR-Tools native libs need libstdc++ + curl for the healthcheck.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first so we cache them across code-only rebuilds.
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# App code
COPY src ./src

# Render injects PORT; default to 8080 (Cloud Run convention).
ENV PORT=8080
EXPOSE 8080

# Healthcheck — Render uses healthCheckPath in render.yaml; this is a fallback for Docker run.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT:-8080}/health" || exit 1

# Single worker keeps memory under Render's 512 MB free-tier limit while OR-Tools runs.
# Cloud Run can override --workers via CMD args without rebuilding.
CMD exec uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1
