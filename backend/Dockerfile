FROM python:3.11-slim

WORKDIR /app

# Install system deps (curl needed for Docker healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY knowledge_base/ ./knowledge_base/

# Ingest knowledge base on build (may fail without API key, that's ok)
RUN python -m backend.scripts.ingest_knowledge_base || true

EXPOSE 8000

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]