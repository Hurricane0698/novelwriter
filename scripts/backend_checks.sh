#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

"$ROOT_DIR/scripts/uv_run.sh" ruff check app tests scripts
"$ROOT_DIR/scripts/uv_run.sh" pytest tests "$@"
