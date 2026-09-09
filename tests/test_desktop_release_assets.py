import hashlib
import json

import pytest

from scripts.prepare_desktop_release import prepare_release


@pytest.fixture
def packages(tmp_path):
    windows, macos = tmp_path / "windows", tmp_path / "macos"
    windows.mkdir()
    macos.mkdir()
    setup = windows / "NovWr_0.5.2_x64-setup.exe"
    dmg = macos / "NovWr_0.5.2_aarch64.dmg"
    setup.write_bytes(b"controlled Windows package")
    dmg.write_bytes(b"controlled macOS package")
    digest = hashlib.sha256(dmg.read_bytes()).hexdigest()
    (macos / "BUILD_INFO.json").write_text(
        json.dumps(
            {
                "source_commit": "a" * 40,
                "source_dirty": False,
                "runtime_rebuilt": True,
                "target": "aarch64-apple-darwin",
                "artifact": dmg.name,
                "artifact_bytes": dmg.stat().st_size,
                "artifact_sha256": digest,
                "signing": "ad-hoc",
                "notarized": False,
                "minimum_macos": "14.0",
                "private_diagnostic": "must not be published",
            }
        )
    )
    (macos / "SHA256SUMS").write_text(f"{digest}  {dmg.name}\n")
    return dict(
        tag="v0.5.2",
        commit="a" * 40,
        windows_dir=windows,
        macos_dir=macos,
        output_dir=tmp_path / "public",
    )


def test_prepares_only_versioned_packages_checksums_and_public_metadata(packages):
    (packages["windows_dir"] / "private.log").write_text("internal diagnostics")
    (packages["macos_dir"] / "validation.md").write_text("internal report")
    result = prepare_release(**packages)
    output = packages["output_dir"]
    assert {path.name for path in output.iterdir()} == {
        "NovWr_0.5.2_x64-setup.exe",
        "NovWr_0.5.2_aarch64.dmg",
        "SHA256SUMS",
        "BUILD_INFO.json",
    }
    assert "private_diagnostic" not in (output / "BUILD_INFO.json").read_text()
    for artifact in result["artifacts"]:
        assert (
            hashlib.sha256((output / artifact["filename"]).read_bytes()).hexdigest()
            == artifact["sha256"]
        )


@pytest.mark.parametrize(
    "fault",
    [
        "wrong_version",
        "wrong_commit",
        "dirty",
        "reused_runtime",
        "tampered_dmg",
        "bad_checksum",
    ],
)
def test_rejects_mismatched_or_unverified_packages(packages, fault):
    macos = packages["macos_dir"]
    metadata_path = macos / "BUILD_INFO.json"
    metadata = json.loads(metadata_path.read_text())
    if fault == "wrong_version":
        packages["tag"] = "v0.5.3"
    elif fault == "wrong_commit":
        packages["commit"] = "b" * 40
    elif fault == "dirty":
        metadata["source_dirty"] = True
    elif fault == "reused_runtime":
        metadata["runtime_rebuilt"] = False
    elif fault == "tampered_dmg":
        (macos / "NovWr_0.5.2_aarch64.dmg").write_bytes(b"changed")
    else:
        (macos / "SHA256SUMS").write_text("0" * 64 + "  wrong.dmg\n")
    metadata_path.write_text(json.dumps(metadata))
    with pytest.raises(ValueError):
        prepare_release(**packages)
    assert not packages["output_dir"].exists()
