#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKER_PID=""
SERVER_PID=""

cleanup() {
  for pid in "$SERVER_PID" "$WORKER_PID"; do
    if [[ -n "$pid" ]]; then
      kill "$pid" >/dev/null 2>&1 || true
      wait "$pid" >/dev/null 2>&1 || true
    fi
  done
}

trap cleanup EXIT INT TERM

# Create the shared schema before the API and worker can race on first startup.
"$ROOT_DIR/scripts/uv_run.sh" python -c 'import app.models; from app.database import init_db; init_db()'

"$ROOT_DIR/scripts/uv_run.sh" python -m app.workers.background_jobs &
WORKER_PID="$!"

"$ROOT_DIR/scripts/uv_run.sh" uvicorn app.main:app --port 8000 &
SERVER_PID="$!"
wait "$SERVER_PID"
