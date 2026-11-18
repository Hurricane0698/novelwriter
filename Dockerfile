# syntax=docker/dockerfile:1.7

FROM python:3.13-slim AS uv-installer
WORKDIR /tmp/uv
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY .uv-version ./
RUN UV_VERSION="$(tr -d '[:space:]' < .uv-version)" \
    && curl -LsSf "https://astral.sh/uv/${UV_VERSION}/install.sh" \
      | env UV_UNMANAGED_INSTALL="/uv-bin" sh

# Stage 1: Build frontend
FROM node:20-slim AS frontend-build
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ .
ARG VITE_API_URL=""
ARG VITE_DEPLOY_MODE=selfhost
# Empty VITE_API_URL -> same-origin requests (no CORS needed)
RUN VITE_API_URL="$VITE_API_URL" VITE_DEPLOY_MODE="$VITE_DEPLOY_MODE" npm run build

# Stage 2: Python backend dependencies + app payload
FROM python:3.13-slim AS backend-build
COPY --from=uv-installer /uv-bin/ /usr/local/bin/
WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates build-essential pkg-config \
    && rm -rf /var/lib/apt/lists/*
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal

ENV UV_PROJECT_ENVIRONMENT=/app/.venv
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV UV_PYTHON_CACHE_DIR=/root/.cache/uv/python
ENV PATH="/root/.cargo/bin:${PATH}"

COPY .uv-version pyproject.toml uv.lock .python-version ./
COPY scripts/setup_python_env.sh scripts/ensure_state_proto_extension.sh scripts/build_state_proto_rust.sh ./scripts/
COPY rust/state_proto/ rust/state_proto/
COPY app/core/indexing/data/ app/core/indexing/data/
RUN --mount=type=cache,target=/root/.cache/uv \
    VENV_DIR=/app/.venv ./scripts/setup_python_env.sh --no-dev --skip-state-proto
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=cache,target=/root/.cargo/registry \
    --mount=type=cache,target=/root/.cargo/git \
    --mount=type=cache,target=/app/rust/state_proto/target \
    VENV_DIR=/app/.venv ./scripts/build_state_proto_rust.sh

COPY app/ app/
COPY alembic/ alembic/
COPY alembic.ini .
COPY data/common_words/ data/common_words/
COPY data/demo/ data/demo/
COPY data/worldpacks/ data/worldpacks/

# Stage 3: Runtime image
FROM python:3.13-slim
WORKDIR /app

COPY --from=backend-build /app/.venv /app/.venv
COPY --from=backend-build /app/app /app/app
COPY --from=backend-build /app/alembic /app/alembic
COPY --from=backend-build /app/alembic.ini /app/alembic.ini
COPY --from=backend-build /app/data /app/data
COPY --from=frontend-build /web/dist/ /app/static/
COPY LICENSE /app/static/LICENSE

# Selfhost defaults to a host bind-mounted /data volume. Keep the runtime user as
# root so first-run SQLite/bootstrap writes still succeed when the host path is
# created by an arbitrary UID/GID outside the image.
RUN mkdir -p /data

ENV DEPLOY_MODE=selfhost
ENV SCNGS_DATA_DIR=/data
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000

CMD ["sh", "-c", ".venv/bin/python -m app.selfhost_db_bootstrap && .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000"]
