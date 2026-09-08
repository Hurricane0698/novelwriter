#!/usr/bin/env bash
# Shared contract for the native Apple Silicon build scripts.

NOVWR_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NOVWR_MACOS_TARGET=aarch64-apple-darwin

novwr_check_macos_toolchain() {
    [[ "$(uname -s)" == Darwin && "$(uname -m)" == arm64 ]] || {
        echo 'Build NovWr on an Apple Silicon Mac, outside Rosetta.' >&2
        return 1
    }
    [[ "$(node --version)" == v20.19.5 && "$(node -p process.arch)" == arm64 ]] || {
        echo 'NovWr requires native Node.js 20.19.5.' >&2
        return 1
    }
    local rust_info
    rust_info="$(rustc --version --verbose)"
    [[ "$rust_info" == *'release: 1.85.0'* && "$rust_info" == *"host: $NOVWR_MACOS_TARGET"* ]] || {
        echo 'NovWr requires Rust 1.85.0 with the aarch64-apple-darwin host.' >&2
        return 1
    }
    [[ "$(uv self version --output-format json | node -pe 'JSON.parse(require("fs").readFileSync(0,"utf8")).version')" == "$(cat "$NOVWR_ROOT/.uv-version")" ]] || {
        echo 'Install the uv version specified in .uv-version.' >&2
        return 1
    }
    xcrun --find clang >/dev/null
    export MACOSX_DEPLOYMENT_TARGET=14.0
    export PYTHONUTF8=1
    # Keep desktop packaging dependencies separate from the development venv.
    export UV_PROJECT_ENVIRONMENT="$NOVWR_ROOT/desktop/build/macos-venv"
    export VIRTUAL_ENV="$UV_PROJECT_ENVIRONMENT"
}
