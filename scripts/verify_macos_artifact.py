"""Check the actual frozen runtime/application, including all native libraries."""

import argparse
import os
from pathlib import Path
import plistlib
import re
import subprocess


MACHO_MAGICS = {
    b"\xfe\xed\xfa\xce", b"\xce\xfa\xed\xfe",
    b"\xfe\xed\xfa\xcf", b"\xcf\xfa\xed\xfe",
    b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca",
    b"\xca\xfe\xba\xbf", b"\xbf\xba\xfe\xca",
}
MINIMUM_MACOS = "14.0"


def is_macho(path: Path) -> bool:
    with path.open("rb") as stream:
        return stream.read(4) in MACHO_MAGICS


def verify_minimum_os(path: Path) -> None:
    commands = subprocess.check_output(["otool", "-l", str(path)], text=True)
    builds = re.findall(r"cmd LC_BUILD_VERSION\s+cmdsize \d+\s+platform (\S+)\s+minos ([\d.]+)", commands)
    versions = [version for _, version in builds] + re.findall(
        r"cmd LC_VERSION_MIN_MACOSX\s+cmdsize \d+\s+version ([\d.]+)", commands,
    )
    if not versions or any(platform not in {"1", "MACOS"} for platform, _ in builds):
        raise ValueError(f"Missing macOS deployment target or wrong platform: {path}")
    limit = (tuple(map(int, MINIMUM_MACOS.split("."))) + (0, 0))[:3]
    if any((tuple(map(int, version.split("."))) + (0, 0))[:3] > limit for version in versions):
        raise ValueError(f"Requires macOS {versions}, exceeds {MINIMUM_MACOS}: {path}")


def verify_runtime(runtime: Path) -> None:
    for relative in ("novwr-runtime", "_internal/alembic.ini", "_internal/static/index.html"):
        if not (runtime / relative).is_file():
            raise ValueError(f"Missing runtime file: {relative}")
    for relative in (
        "alembic/versions", "static/assets", "data/common_words", "data/demo",
        "data/worldpacks", "app/core/indexing/data",
    ):
        directory = runtime / "_internal" / relative
        if not directory.is_dir() or not any(p.is_file() for p in directory.rglob("*")):
            raise ValueError(f"Missing or empty runtime directory: {relative}")
    extensions = list((runtime / "_internal/_novwr_state_proto").glob("_novwr_state_proto*.so"))
    if len(extensions) != 1:
        raise ValueError(f"Expected one state-proto extension, found {len(extensions)}")
    if not all(is_macho(path) for path in [runtime / "novwr-runtime", *extensions]):
        raise ValueError("Runtime executable and state-proto extension must be Mach-O files")
    if not os.access(runtime / "novwr-runtime", os.X_OK):
        raise ValueError("Runtime entry point is not executable")


def verify_native_code(root: Path) -> int:
    count = 0
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            if not path.resolve(strict=True).is_relative_to(root):
                raise ValueError(f"Bundle symlink escapes the artifact: {path}")
            continue
        if not path.is_file():
            continue
        if not is_macho(path):
            continue
        architectures = subprocess.check_output(["lipo", "-archs", str(path)], text=True).split()
        if architectures != ["arm64"]:
            raise ValueError(f"Expected native arm64 binary, found {architectures}: {path}")
        verify_minimum_os(path)
        subprocess.run(["codesign", "--verify", "--strict", str(path)], check=True)
        count += 1
    if count == 0:
        raise ValueError("Artifact contains no native code")
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--runtime", type=Path)
    target.add_argument("--app", type=Path)
    args = parser.parse_args()
    root = (args.app or args.runtime).resolve(strict=True)
    runtime = root / "Contents/Resources/runtime" if args.app else root
    verify_runtime(runtime)
    if args.app:
        with (root / "Contents/Info.plist").open("rb") as stream:
            info = plistlib.load(stream)
        if info.get("CFBundleExecutable") != "NovWr" or info.get("LSMinimumSystemVersion") != MINIMUM_MACOS:
            raise ValueError("Unexpected app executable or minimum macOS version")
        executable = root / "Contents/MacOS/NovWr"
        if not is_macho(executable) or not os.access(executable, os.X_OK):
            raise ValueError("App entry point must be an executable Mach-O file")
        subprocess.run(["codesign", "--verify", "--deep", "--strict", str(root)], check=True)
    count = verify_native_code(root)
    print(f"Verified {count} arm64 Mach-O files: signature integrity and minos <= {MINIMUM_MACOS} in {root}")


if __name__ == "__main__":
    main()
