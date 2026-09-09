#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${VENV_DIR:-$ROOT_DIR/.venv}"
PYTHON_REQUEST="${PYTHON_BIN:-}"
INSTALL_DEV=true
SYNC_GROUPS=()
ENSURE_STATE_PROTO=true

usage() {
  cat <<'EOF'
Usage: scripts/setup_python_env.sh [--no-dev] [--skip-state-proto]

Options:
  --group <name>        Include an additional uv dependency group (repeatable)
  --skip-state-proto    Skip automatic state-proto extension assurance

Bootstraps the repo-local uv-managed virtualenv from pyproject.toml + uv.lock.

Environment overrides:
  VENV_DIR   Custom virtualenv path (default: <repo>/.venv)
  PYTHON_BIN Python executable or version request for `uv venv --python`
EOF
}

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --dev)
      INSTALL_DEV=true
      ;;
    --no-dev)
      INSTALL_DEV=false
      ;;
    --group)
      if [[ "$#" -lt 2 ]]; then
        echo "Missing value for --group" >&2
        usage >&2
        exit 2
      fi
      SYNC_GROUPS+=("$2")
      shift
      ;;
    --skip-state-proto)
      ENSURE_STATE_PROTO=false
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

if ! command -v uv >/dev/null 2>&1; then
  echo "Error: uv is not installed." >&2
  exit 1
fi

if [[ -z "$PYTHON_REQUEST" ]] && [[ -f "$ROOT_DIR/.python-version" ]]; then
  PYTHON_REQUEST="$(tr -d '[:space:]' < "$ROOT_DIR/.python-version")"
fi

if [[ -z "$PYTHON_REQUEST" ]]; then
  PYTHON_REQUEST="python3"
fi

mkdir -p "$(dirname "$VENV_DIR")"

cd "$ROOT_DIR"
uv venv --allow-existing --python "$PYTHON_REQUEST" "$VENV_DIR"

PY_BIN="$VENV_DIR/bin/python"
export UV_PROJECT_ENVIRONMENT="$VENV_DIR"

sync_cmd=(
  uv sync
  --project "$ROOT_DIR"
  --python "$PY_BIN"
  --frozen
  --no-install-project
)

if [[ "$INSTALL_DEV" == false ]]; then
  sync_cmd+=(--no-dev)
fi

# Bash 3.2 (the macOS system shell) treats an empty array as unset under -u.
for group in ${SYNC_GROUPS[@]+"${SYNC_GROUPS[@]}"}; do
  sync_cmd+=(--group "$group")
done

"${sync_cmd[@]}"

if [[ "$ENSURE_STATE_PROTO" == "true" ]]; then
  "$ROOT_DIR/scripts/ensure_state_proto_extension.sh"
fi

echo "Python environment ready at $VENV_DIR"
