# syntax=docker/dockerfile:1.6
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

WORKDIR /app

# Install deps first (better layer caching): copy only lockfiles, then sync.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

# Now copy the actual source tree (libs/history_audit is excluded via
# .dockerignore — it's out of scope for this deployment).
COPY libs/ ./libs/

# anaplan-skill is an unpackaged ("virtual") uv project (no [build-system]),
# so `uv sync` only installs dependencies, not libs/ itself. PYTHONPATH=/app
# above replicates what `uv run` gives for free when run from the repo root:
# `from libs.model_analyzer...` imports resolve against /app.

# Cloud Run injects $PORT (default 8080).
EXPOSE 8080

CMD ["sh", "-c", "uv run streamlit run libs/model_analyzer/dashboard.py --server.port=${PORT:-8080} --server.address=0.0.0.0 --server.headless=true"]
