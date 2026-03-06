# ── Stage 1: Build React frontend ────────────────────────────────────────────
FROM node:20-slim AS frontend-build

WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci --silent
COPY frontend/ ./
RUN npm run build


# ── Stage 2: Python backend + Playwright ─────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# curl is needed for the health-check
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwright: download Chromium + install system libraries
RUN playwright install chromium --with-deps

# App code
COPY backend/ ./backend/
COPY run.py .

# React build from Stage 1
COPY --from=frontend-build /app/frontend/dist ./frontend/dist/

# Persistent data directory (mounted as volume)
RUN mkdir -p /data

EXPOSE 8000

CMD ["python", "run.py"]
