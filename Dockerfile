FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ backend/
COPY Procfile runtime.txt ./

# Default: web process
CMD uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000}
