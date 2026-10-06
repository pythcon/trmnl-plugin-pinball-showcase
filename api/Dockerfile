# syntax=docker/dockerfile:1.7

# ---- build: resolve and install dependencies with uv -------------------------------------
FROM python:3.13-slim-bookworm AS build
COPY --from=ghcr.io/astral-sh/uv:0.12.0 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project
COPY README.md ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

# ---- runtime: slim image, non-root, data volume ------------------------------------------
FROM python:3.13-slim-bookworm AS runtime
LABEL org.opencontainers.image.title="trmnl-pinball-showcase" \
      org.opencontainers.image.description="Pinball of the Day API for TRMNL, powered by the OPDB daily export" \
      org.opencontainers.image.source="https://github.com/pythcon/trmnl-plugin-pinball-showcase" \
      org.opencontainers.image.licenses="MIT"

RUN useradd --system --uid 10001 --create-home app \
    && mkdir -p /data && chown app:app /data
COPY --from=build --chown=app:app /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PINBALL_DATA_DIR=/data \
    HOST=0.0.0.0 \
    PORT=8080

USER app
VOLUME ["/data"]
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/healthz', timeout=4)"
CMD ["pinball-showcase"]
