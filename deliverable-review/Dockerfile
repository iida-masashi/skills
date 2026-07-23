# syntax=docker/dockerfile:1.6
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

WORKDIR /app

# System deps (pdfplumber/pypdf rely on pure-Python; no native deps needed today)
# kept minimal for image size.

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY scripts/ ./scripts/
COPY webui/ ./webui/

# Cloud Run injects $PORT (default 8080).
EXPOSE 8080

CMD ["sh", "-c", "streamlit run webui/app.py --server.port=${PORT:-8080} --server.address=0.0.0.0 --server.enableXsrfProtection=false --server.enableCORS=false"]
