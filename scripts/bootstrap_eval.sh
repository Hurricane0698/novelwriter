#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

"$ROOT_DIR/scripts/uv_run.sh" python benchmarks/bootstrap_v1/eval_runner.py "$@"
