#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SMOKE_IMAGE_TAG="${1:-${NOVWR_SMOKE_IMAGE:-novwr-selfhost:ci}}"
INSTALL_PORT="${NOVWR_SMOKE_INSTALL_PORT:-18080}"
COMPOSE_PORT="${NOVWR_SMOKE_COMPOSE_PORT:-18081}"
NOVWR_BIN="$HOME/.local/bin/novwr"

INSTALL_DIR=""
COMPOSE_DIR=""
COMPOSE_PROJECT_NAME=""

require_command() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Missing required command: $cmd" >&2
    exit 1
  fi
}

wait_for_health() {
  local url="$1"
  local attempts="${2:-45}"

  for ((i=1; i<=attempts; i++)); do
    if curl -fsSL "$url" | grep -q '"healthy"'; then
      echo "Healthcheck passed: $url"
      return 0
    fi
    sleep 1
  done

  echo "Healthcheck failed: $url" >&2
  return 1
}

cleanup() {
  set +e

  if [[ -n "$INSTALL_DIR" && -x "$NOVWR_BIN" ]]; then
    "$NOVWR_BIN" uninstall --dir "$INSTALL_DIR" --delete-data >/dev/null 2>&1 || true
  fi

  if [[ -n "$COMPOSE_DIR" && -f "$COMPOSE_DIR/docker-compose.yml" ]]; then
    docker compose --project-directory "$COMPOSE_DIR" --project-name "$COMPOSE_PROJECT_NAME" down --remove-orphans -v >/dev/null 2>&1 || true
  fi
}

trap cleanup EXIT

dump_compose_debug() {
  local dir="$1"
  local project_name="${2:-}"
  local compose_args=("--project-directory" "$dir")

  if [[ -z "$dir" || ! -f "$dir/docker-compose.yml" ]]; then
    return 0
  fi

  if [[ -n "$project_name" ]]; then
    compose_args+=("--project-name" "$project_name")
  fi

  echo "[selfhost-smoke] docker compose ps ($dir)"
  docker compose "${compose_args[@]}" ps || true
  echo "[selfhost-smoke] docker compose logs ($dir)"
  docker compose "${compose_args[@]}" logs --no-color || true
}

require_command uv
require_command curl
require_command docker
docker compose version >/dev/null

cd "$ROOT_DIR"

if [[ $# -eq 0 ]]; then
  echo "[selfhost-smoke] building local app image: $SMOKE_IMAGE_TAG"
  docker build -t "$SMOKE_IMAGE_TAG" .
fi

echo "[selfhost-smoke] building wheel"
uv build --wheel --out-dir dist >/dev/null
WHEEL_PATH="$(python3 - <<'PY'
from pathlib import Path
wheels = sorted(Path("dist").glob("novwr-*.whl"), key=lambda path: path.stat().st_mtime)
if not wheels:
    raise SystemExit("No wheel produced in dist/")
print(wheels[-1].resolve())
PY
)"

echo "[selfhost-smoke] wheel CLI help"
uv tool run --isolated --from "$WHEEL_PATH" novwr --help >/dev/null
uv tool run --isolated --from "$WHEEL_PATH" novwr uninstall --help >/dev/null

echo "[selfhost-smoke] installer flow via curl | bash"
INSTALL_DIR="$(mktemp -d)"
export NOVWR_HOME="$INSTALL_DIR"
export NOVWR_IMAGE="$SMOKE_IMAGE_TAG"
export NOVWR_BIND_HOST="127.0.0.1"
export NOVWR_PORT="$INSTALL_PORT"
export NOVWR_PACKAGE_SPEC="$WHEEL_PATH"
export NOVWR_UV_VERSION="$(tr -d '[:space:]' < .uv-version)"
curl -fsSL "file://${ROOT_DIR}/install.sh" | bash

if [[ ! -x "$NOVWR_BIN" ]]; then
  echo "Installed novwr CLI not found at $NOVWR_BIN" >&2
  exit 1
fi

if ! wait_for_health "http://127.0.0.1:${INSTALL_PORT}/api/health"; then
  dump_compose_debug "$INSTALL_DIR"
  exit 1
fi
"$NOVWR_BIN" doctor --dir "$INSTALL_DIR"
"$NOVWR_BIN" uninstall --dir "$INSTALL_DIR" --delete-data
INSTALL_DIR=""
unset NOVWR_HOME NOVWR_IMAGE NOVWR_BIND_HOST NOVWR_PORT NOVWR_PACKAGE_SPEC NOVWR_UV_VERSION

echo "[selfhost-smoke] official selfhost compose flow"
COMPOSE_DIR="$(mktemp -d)"
COMPOSE_PROJECT_NAME="novwr-smoke-${RANDOM}"
uv tool run --isolated --from "$WHEEL_PATH" novwr init \
  --dir "$COMPOSE_DIR" \
  --image "$SMOKE_IMAGE_TAG" \
  --bind-host 127.0.0.1 \
  --port "$COMPOSE_PORT" \
  --force >/dev/null

docker compose --project-directory "$COMPOSE_DIR" --project-name "$COMPOSE_PROJECT_NAME" config >/dev/null
docker compose --project-directory "$COMPOSE_DIR" --project-name "$COMPOSE_PROJECT_NAME" up -d
if ! wait_for_health "http://127.0.0.1:${COMPOSE_PORT}/api/health"; then
  dump_compose_debug "$COMPOSE_DIR" "$COMPOSE_PROJECT_NAME"
  exit 1
fi
docker compose --project-directory "$COMPOSE_DIR" --project-name "$COMPOSE_PROJECT_NAME" down --remove-orphans -v
COMPOSE_DIR=""
COMPOSE_PROJECT_NAME=""

echo "[selfhost-smoke] ok"
