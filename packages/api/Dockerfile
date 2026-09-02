# Multi-stage build for the Arbiter API + worker (docs/28 §3).
# Same image runs both:  `arbiter-api`  (server)  /  `arbiter-api worker`.

FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app

# workspace metadata first, for a cached dependency layer
COPY pyproject.toml uv.lock ./
COPY packages/engine/pyproject.toml packages/engine/
COPY packages/datagen/pyproject.toml packages/datagen/
COPY packages/api/pyproject.toml packages/api/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-workspace --no-dev --package arbiter-api --extra postgres

# then the source
COPY packages/ packages/
COPY specs/ specs/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package arbiter-api --extra postgres


FROM python:3.12-slim AS runtime
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin arbiter
WORKDIR /app
COPY --from=build --chown=arbiter:arbiter /app /app
ENV PATH="/app/.venv/bin:$PATH" \
    ARBITER_ENV=prod \
    ARBITER_API_HOST=0.0.0.0 \
    ARBITER_DB_URL=postgresql+psycopg://arbiter:arbiter@db:5432/arbiter
USER arbiter
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --retries=5 \
    CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/healthz')"
ENTRYPOINT ["arbiter-api"]
