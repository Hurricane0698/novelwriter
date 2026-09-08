#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/macos_build_common.sh"
novwr_check_macos_toolchain
cd "$NOVWR_ROOT"

# Record source state before build tools update generated files or Cargo formatting.
build_commit="$(git rev-parse HEAD)"
build_dirty="$(git status --porcelain)"
build_arg_count="$#"

# An existing runtime can be supplied explicitly for desktop-only iteration.
runtime_dir="${1:-$NOVWR_ROOT/desktop/runtime-dist/macos/novwr-runtime}"
if [[ $# -eq 0 ]]; then
    bash scripts/build_macos_runtime.sh
fi
runtime_dir="$(cd "$runtime_dir" && pwd)"
"$UV_PROJECT_ENVIRONMENT/bin/python" scripts/verify_macos_artifact.py --runtime "$runtime_dir"

resources="$NOVWR_ROOT/desktop/src-tauri/resources/novwr-runtime"
mkdir -p "$resources"
# This directory is exclusively generated build output; remove stale Windows files.
rsync -a --delete "$runtime_dir/" "$resources/"
(
    cd desktop
    npm ci
    npm run icons
    # CI mode also skips Finder cosmetics, so packaging needs no Automation grant.
    CI=true TAURI_BUNDLER_DMG_IGNORE_CI=false npm exec -- tauri build --ci --target "$NOVWR_MACOS_TARGET" \
        --config src-tauri/tauri.macos.conf.json --bundles app,dmg -- --locked
)

bundle_dir="$NOVWR_ROOT/desktop/src-tauri/target/$NOVWR_MACOS_TARGET/release/bundle"
output_dir="$NOVWR_ROOT/desktop/desktop-dist/macos"
mkdir -p "$output_dir"
"$UV_PROJECT_ENVIRONMENT/bin/python" scripts/verify_macos_artifact.py --app "$bundle_dir/macos/NovWr.app"
# ditto preserves the framework symlinks and signatures inside the application.
if [[ -e "$output_dir/NovWr.app" ]]; then
    rm -rf -- "$output_dir/NovWr.app"
fi
ditto "$bundle_dir/macos/NovWr.app" "$output_dir/NovWr.app"
version="$(node -p 'require("./desktop/package.json").version')"
dmg="$bundle_dir/dmg/NovWr_${version}_aarch64.dmg"
[[ -f "$dmg" ]] || { echo 'Versioned Apple Silicon DMG is missing.' >&2; exit 1; }
cp "$dmg" "$output_dir/"
(
    cd "$output_dir"
    shasum -a 256 "$(basename "$dmg")" > SHA256SUMS
)
"$UV_PROJECT_ENVIRONMENT/bin/python" - "$output_dir" "$build_commit" "$build_dirty" "$build_arg_count" <<'PY'
import json
from pathlib import Path
import sys

output = Path(sys.argv[1])
checksum, artifact_name = (output / "SHA256SUMS").read_text().strip().split(maxsplit=1)
info = {
    "source_commit": sys.argv[2],
    "source_dirty": bool(sys.argv[3]),
    "runtime_rebuilt": sys.argv[4] == "0",
    "target": "aarch64-apple-darwin",
    "minimum_macos": "14.0",
    "signing": "ad-hoc",
    "notarized": False,
    "artifact": artifact_name,
    "artifact_bytes": (output / artifact_name).stat().st_size,
    "artifact_sha256": checksum,
}
(output / "BUILD_INFO.json").write_text(json.dumps(info, indent=2) + "\n")
PY
printf 'macOS application and DMG: %s\n' "$output_dir"
