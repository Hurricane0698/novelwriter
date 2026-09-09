"""Prepare only validated desktop packages and public provenance for a release."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil


def _digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def prepare_release(
    *,
    tag: str,
    commit: str,
    windows_dir: Path,
    macos_dir: Path,
    output_dir: Path,
    run_url: str = "",
) -> dict:
    if not re.fullmatch(r"v\d+\.\d+\.\d+", tag):
        raise ValueError("Expected a stable vMAJOR.MINOR.PATCH tag")
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Expected the complete source commit SHA")
    version = tag[1:]
    setup = windows_dir / f"NovWr_{version}_x64-setup.exe"
    dmg = macos_dir / f"NovWr_{version}_aarch64.dmg"
    if sorted(windows_dir.glob("NovWr_*_x64-setup.exe")) != [setup]:
        raise ValueError("Windows installer does not match the release tag")
    if sorted(macos_dir.glob("NovWr_*_aarch64.dmg")) != [dmg]:
        raise ValueError("macOS installer does not match the release tag")
    for package in (setup, dmg):
        if not package.is_file() or package.stat().st_size == 0:
            raise ValueError(f"Missing or empty package: {package.name}")

    mac = json.loads((macos_dir / "BUILD_INFO.json").read_text())
    if mac.get("source_commit") != commit or mac.get("source_dirty") is not False:
        raise ValueError("macOS package must come from the clean tagged source")
    if (
        mac.get("runtime_rebuilt") is not True
        or mac.get("target") != "aarch64-apple-darwin"
    ):
        raise ValueError("macOS release requires a rebuilt Apple Silicon runtime")
    dmg_digest = _digest(dmg)
    if (
        mac.get("artifact") != dmg.name
        or mac.get("artifact_sha256") != dmg_digest
        or mac.get("artifact_bytes") != dmg.stat().st_size
    ):
        raise ValueError("macOS package differs from its build metadata")
    if (macos_dir / "SHA256SUMS").read_text().split() != [dmg_digest, dmg.name]:
        raise ValueError("macOS checksum manifest does not match the package")

    # Both inputs are downloaded from this same workflow run after the Windows
    # installed-product and macOS application smoke jobs have succeeded.
    artifacts = [
        {
            "filename": setup.name,
            "target": "x86_64-pc-windows-msvc",
            "bytes": setup.stat().st_size,
            "sha256": _digest(setup),
            "signing": "unsigned",
        },
        {
            "filename": dmg.name,
            "target": "aarch64-apple-darwin",
            "bytes": dmg.stat().st_size,
            "sha256": dmg_digest,
            "signing": mac["signing"],
            "notarized": mac["notarized"],
            "minimum_macos": mac["minimum_macos"],
        },
    ]
    metadata = {
        "version": version,
        "source_commit": commit,
        "workflow_run_url": run_url,
        "artifacts": artifacts,
    }
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("Release output directory must be empty")
    output_dir.mkdir(parents=True, exist_ok=True)
    for package in (setup, dmg):
        shutil.copyfile(package, output_dir / package.name)
    (output_dir / "SHA256SUMS").write_text(
        "".join(
            f"{artifact['sha256']}  {artifact['filename']}\n" for artifact in artifacts
        )
    )
    (output_dir / "BUILD_INFO.json").write_text(json.dumps(metadata, indent=2) + "\n")
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--windows-dir", type=Path, required=True)
    parser.add_argument("--macos-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--run-url", default="")
    print(json.dumps(prepare_release(**vars(parser.parse_args())), indent=2))


if __name__ == "__main__":
    main()
