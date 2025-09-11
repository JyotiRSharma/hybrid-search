# ---------- Base image ----------
FROM python:3.9-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    POETRY_VERSION=1.8.3 \
    POETRY_VIRTUALENVS_CREATE=false

# System deps (build tools & runtime libs; adjust as needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential curl git \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry via pipx (recommended)
RUN pip install --no-cache-dir pipx && pipx ensurepath && \
    pipx install "poetry==${POETRY_VERSION}"

WORKDIR /app

# ---------- Dependency layer (cached) ----------
# Copy only the files needed to resolve dependencies
COPY pyproject.toml /app/
# If you have a lockfile, include it for reproducible builds & better caching
# (Optional but recommended)
COPY poetry.lock /app/poetry.lock

# Install only *main* deps (no dev deps) into system env
RUN /root/.local/bin/poetry install --only main --no-interaction --no-ansi --no-root

# ---------- App layer ----------
# Now copy your app code
COPY app /app/app
COPY scripts/ /app/scripts/

# Optional: pre-download the embedding model to avoid first-request delay
# (uncomment if you want the image to include the model cache)
# RUN python - <<'PY'
# from sentence_transformers import SentenceTransformer
# SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
# PY

# Add a prod server
RUN pip install --no-cache-dir "gunicorn==21.2.0" "uvicorn[standard]==0.30.0"

# Expose and run
EXPOSE 8000
CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "app.main:app", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "120"]
