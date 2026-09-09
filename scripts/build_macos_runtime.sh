#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/macos_build_common.sh"
novwr_check_macos_toolchain
cd "$NOVWR_ROOT"

runtime_dist="${1:-$NOVWR_ROOT/desktop/runtime-dist/macos}"
mkdir -p "$runtime_dist" desktop/build/macos-pyinstaller
runtime_dist="$(cd "$runtime_dist" && pwd)"
# Use the same standalone Python distribution locally and on hosted runners.
# System framework builds can retain a resource signature that does not describe
# the framework subset collected by PyInstaller.
uv sync --frozen --managed-python --python "$NOVWR_MACOS_PYTHON" --no-dev --group desktop-build
python_bin="$UV_PROJECT_ENVIRONMENT/bin/python"
"$python_bin" - "$NOVWR_MACOS_PYTHON" <<'PY'
import platform
import sys
import sysconfig

assert platform.python_version() == sys.argv[1]
assert platform.machine() == "arm64"
assert not sysconfig.get_config_var("PYTHONFRAMEWORK"), "Use uv-managed standalone Python for macOS packaging"
PY

(
    cd web
    npm ci
    VITE_API_URL='' VITE_DEPLOY_MODE=desktop npm run build
)
"$UV_PROJECT_ENVIRONMENT/bin/maturin" develop --locked --manifest-path rust/state_proto/Cargo.toml --release
"$python_bin" -c 'import _novwr_state_proto; assert _novwr_state_proto.payload_format_version() == 2'

# Module discovery must not create files in the developer's normal data folder.
SCNGS_DATA_DIR="$NOVWR_ROOT/desktop/build/macos-analysis-data" \
    "$UV_PROJECT_ENVIRONMENT/bin/pyinstaller" --noconfirm --clean \
    --distpath "$runtime_dist" --workpath "$NOVWR_ROOT/desktop/build/macos-pyinstaller" \
    desktop/runtime/novwr-runtime.spec
"$python_bin" scripts/verify_macos_artifact.py --runtime "$runtime_dist/novwr-runtime"
"$runtime_dist/novwr-runtime/novwr-runtime" --help
printf 'Packaged runtime: %s\n' "$runtime_dist/novwr-runtime"
