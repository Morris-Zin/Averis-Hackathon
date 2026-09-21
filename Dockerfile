# syntax=docker/dockerfile:1.7

FROM node:24-bookworm-slim AS frontend-builder
WORKDIR /workspace/frontend

RUN npm install --global pnpm@10.26.2
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY frontend ./
RUN pnpm build

FROM python:3.12-slim AS python-builder
WORKDIR /app

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_NO_CACHE=1
RUN pip install --no-cache-dir uv

COPY backend/pyproject.toml backend/uv.lock ./
COPY README.md ./
COPY backend/src ./src
RUN uv sync --locked --no-dev --no-editable

FROM python:3.12-slim AS runtime
WORKDIR /app

RUN apt-get update \
    && apt-get install --no-install-recommends -y tesseract-ocr tesseract-ocr-eng \
       tesseract-ocr-msa tesseract-ocr-chi-sim tesseract-ocr-chi-tra \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system --gid 10001 averis \
    && useradd --system --uid 10001 --gid averis --home-dir /app --no-create-home averis

ENV PATH="/app/.venv/bin:$PATH" \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    AVERIS_ROLE=web

COPY --from=python-builder /app/.venv /app/.venv
COPY backend/src ./src
COPY backend/migrations ./migrations
COPY backend/alembic.ini ./
COPY --from=frontend-builder /workspace/frontend/out ./frontend/out

EXPOSE 8080

USER averis

# The same image serves the public application or the private worker. Cloud
# Run supplies PORT; AVERIS_ROLE is set per service by Terraform or Compose.
CMD ["sh", "-c", "if [ \"${AVERIS_ROLE}\" = \"worker\" ]; then exec uvicorn averis.worker:app --host 0.0.0.0 --port \"${PORT:-8080}\"; else exec uvicorn averis.api:app --host 0.0.0.0 --port \"${PORT:-8080}\"; fi"]
