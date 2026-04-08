# ============================================================
# Stage 1: Build the React frontend
# ============================================================
FROM node:20-alpine AS node-builder

WORKDIR /app/frontend

# Copy package files first for better layer caching.
# npm install only re-runs when package.json changes.
COPY frontend/package.json frontend/package-lock.json ./

RUN npm ci --silent

# Copy the rest of the frontend source
COPY frontend/ ./

# Build the React production bundle → output to frontend/build/
RUN npm run build

# ============================================================
# Stage 2: Python production runner
# ============================================================
FROM python:3.11-slim AS runner

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_ENV=production \
    PORT=8000

# System dependencies:
#   libpq-dev  — required by psycopg2-binary (PostgreSQL)
#   curl       — used by the healthcheck
#   gcc        — required to compile some Python packages
RUN apt-get update && apt-get install -y \
        libpq-dev \
        curl \
        gcc \
        --no-install-recommends \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies before copying source code so
# this layer is only invalidated when requirements.txt changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy Python source: backend package, root-level modules, fonts
COPY backend/         ./backend/
COPY *.py             ./
COPY gunicorn.conf.py ./
COPY fonts/           ./fonts/

# Copy the compiled React build from the node-builder stage.
# Flask serves these as static files in production.
COPY --from=node-builder /app/frontend/build ./frontend/build

# Create the data directory.
# Mount a volume here in production so data persists:
#   docker run -v ./data:/app/data ...
RUN mkdir -p data/raw data/clean data/charts data/reports

# Create a non-root user for security
RUN groupadd --gid 1001 appuser \
    && useradd --uid 1001 --gid 1001 --no-create-home appuser \
    && chown -R appuser:appuser /app

# Copy the startup script
COPY --chown=appuser:appuser scripts/docker-start.sh ./
RUN chmod +x docker-start.sh

USER appuser

EXPOSE 8000

# Docker restarts the container if this fails 3 times
HEALTHCHECK \
    --interval=30s \
    --timeout=10s \
    --start-period=40s \
    --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

CMD ["./docker-start.sh"]
