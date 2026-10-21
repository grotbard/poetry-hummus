# Single-origin image for Render: builds the SPA, then serves it from the API
# so the session cookie is same-origin (separate *.onrender.com subdomains
# count as different sites and would drop a SameSite=Lax cookie).

# ---- 1. Build the frontend -------------------------------------------------
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- 2. Runtime ------------------------------------------------------------
FROM python:3.12-slim
WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .
COPY --from=web /web/dist ./static

# The API serves the SPA from here and stores uploads here.
ENV POETRY_STATIC_DIR=/app/static \
    POETRY_MEDIA_DIR=/app/media

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s \
    CMD curl -fsS http://localhost:${PORT:-8000}/api/health || exit 1

# Render supplies $PORT; migrations run from the blueprint's preDeployCommand.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
