# syntax=docker/dockerfile:1
# Multi-stage build for the FastAPI backend using uv. Final image is non-root.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app
# install deps first (cached unless pyproject/uv.lock change), then the project
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY . .
RUN uv sync --frozen --no-dev

FROM python:3.12-slim-bookworm AS runtime
RUN useradd -m -u 10001 appuser
WORKDIR /app
COPY --from=builder /app /app
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
USER appuser
EXPOSE 8000
# liveness probe — no DB, cheap (PORT honored so it matches the listen port)
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import os,urllib.request,sys; p=os.getenv('PORT','8000'); sys.exit(0 if urllib.request.urlopen(f'http://localhost:{p}/v1/health/live',timeout=3).status==200 else 1)"
# shell form so ${PORT} (set by Render) expands; defaults to 8000 locally
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
