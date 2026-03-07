#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${VENV_DIR:-$ROOT_DIR/.venv}"
PY_BIN="$VENV_DIR/bin/python"

if ! command -v uv >/dev/null 2>&1; then
  echo "Error: uv is not installed." >&2
  exit 1
fi

if [[ ! -x "$PY_BIN" ]]; then
  echo "Error: project virtualenv not found at $PY_BIN" >&2
  echo "Run scripts/setup_python_env.sh first." >&2
  exit 1
fi

if [[ "$#" -eq 0 ]]; then
  echo "Usage: scripts/uv_run.sh <command> [args...]" >&2
  exit 2
fi

cd "$ROOT_DIR"
exec uv run --python "$PY_BIN" "$@"
