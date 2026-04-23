# ---------------------------------------------------------------------------
# Hembudget — Cloud Run / GCP-container
# Multi-stage bygge:
#   1. Frontend (node:20-alpine) → vite build → /app/frontend/dist
#   2. Backend  (python:3.11-slim) + kopierar in dist från steg 1
#   3. Runtime: uvicorn lyssnar på $PORT (Cloud Run-konvention)
#
# Demo-läge aktiveras via HEMBUDGET_DEMO_MODE=1 i deploy-kommandot.
# Auto-seed av data/-mappen sker vid start (se backend/hembudget/demo.py).
# ---------------------------------------------------------------------------

# ---------- Stage 1: Frontend build ----------
FROM node:20-alpine AS frontend-build
WORKDIR /frontend

# Installera deps med cache-vänlig ordning (package.json först)
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-audit --no-fund

# Bygg med VITE_API_BASE=/ → same-origin (API serveras från samma container)
COPY frontend/ ./
ENV VITE_API_BASE="/"
RUN npm run build


# ---------- Stage 2: Backend + runtime ----------
FROM python:3.11-slim AS backend

# Systemberoenden för pypdfium2, Pillow och matplotlib
RUN apt-get update && apt-get install -y --no-install-recommends \
        libjpeg62-turbo \
        zlib1g \
        fonts-dejavu-core \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Installera Python-deps — installera FÖRE vi kopierar in källkoden
# så Docker-cachen inte invalideras av kodändringar.
COPY backend/pyproject.toml ./backend/pyproject.toml
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
        "fastapi>=0.110" \
        "uvicorn[standard]>=0.27" \
        "sqlalchemy>=2.0" \
        "alembic>=1.13" \
        "pydantic>=2.6" \
        "pydantic-settings>=2.2" \
        "openai>=1.30" \
        "pandas>=2.2" \
        "python-multipart>=0.0.9" \
        "argon2-cffi>=23.1" \
        "python-dateutil>=2.9" \
        "chardet>=5.2" \
        "Pillow>=10.2" \
        "pypdfium2>=4.28" \
        "reportlab>=4.1" \
        "openpyxl>=3.1" \
        "httpx>=0.27" \
        "rapidfuzz>=3.6" \
        "matplotlib>=3.8"
# OBS: sqlcipher3-binary hoppas över i demo — backend faller tillbaka på
# plain SQLite automatiskt. pytesseract/tesseract skippas också eftersom
# vision-import inte används i demo.

# Kopiera backend-källkoden
COPY backend/ /app/backend/

# Kopiera in byggd frontend från stage 1
COPY --from=frontend-build /frontend/dist /app/frontend/dist

# Data-mappen för auto-seed (Nordea/SEB CSV + XLSX)
COPY data/ /app/data/

# Cloud Run sätter PORT-env vid start. Vi bindar på 0.0.0.0 och inaktiverar
# SQLCipher (ingen master-password i demo) + pekar LM Studio till en
# icke-existerande host så AI-features failar tyst utan att blockera start.
ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend \
    HEMBUDGET_HOST=0.0.0.0 \
    HEMBUDGET_DEMO_MODE=1 \
    HEMBUDGET_SERVE_STATIC=1 \
    HEMBUDGET_DATA_DIR=/tmp/hembudget \
    HEMBUDGET_LM_STUDIO_BASE_URL=http://disabled.invalid:1234/v1

# Hälsokoll för Cloud Run
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8080}/healthz || exit 1

# Lyssna på Cloud Run:s PORT (default 8080 om kört lokalt)
EXPOSE 8080
CMD ["sh", "-c", "exec python -m hembudget.main --host 0.0.0.0 --port ${PORT:-8080}"]
