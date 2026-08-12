from __future__ import annotations

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.api import novel_support

from .support import make_app, make_novels_app, novel_txt_bytes, patch_upload_dir


def test_upload_rejects_unsupported_extension(db, tmp_path, monkeypatch, novels_api, active_user):
    patch_upload_dir(monkeypatch, tmp_path)
    app = make_novels_app(db, novels_api, active_user)

    with TestClient(app) as c:
        resp = c.post(
            "/api/novels/upload",
            files={"file": ("novel.docx", b"not a novel source", "application/octet-stream")},
            data={
                "title": "T",
                "author": "A",
                "consent_acknowledged": "true",
                "consent_version": novel_support.UPLOAD_CONSENT_VERSION,
            },
        )

    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "upload_type_not_supported"


def test_upload_rejects_too_large(db, tmp_path, monkeypatch, novels_api, active_user):
    upload_dir = patch_upload_dir(monkeypatch, tmp_path)
    too_big = b"a" * (30 * 1024 * 1024 + 1)
    app = make_novels_app(db, novels_api, active_user)

    with TestClient(app) as c:
        resp = c.post(
            "/api/novels/upload",
            files={"file": ("novel.txt", too_big, "text/plain")},
            data={
                "title": "T",
                "author": "A",
                "consent_acknowledged": "true",
                "consent_version": novel_support.UPLOAD_CONSENT_VERSION,
            },
        )

    assert resp.status_code == 413
    assert resp.json()["detail"]["code"] == "upload_file_too_large"
    assert resp.json()["detail"]["max_megabytes"] == 30
    assert list(upload_dir.iterdir()) == []


def test_hosted_upload_requires_auth(db, tmp_path, monkeypatch, novels_api):
    import app.core.auth as auth_core

    patch_upload_dir(monkeypatch, tmp_path)
    monkeypatch.setattr(auth_core, "get_settings", lambda: MagicMock(deploy_mode="hosted"))
    app = make_app(db, novels_api.router)

    with TestClient(app) as c:
        resp = c.post(
            "/api/novels/upload",
            files={"file": ("novel.txt", novel_txt_bytes(), "text/plain")},
            data={
                "title": "T",
                "author": "A",
                "consent_acknowledged": "true",
                "consent_version": novel_support.UPLOAD_CONSENT_VERSION,
            },
        )

    assert resp.status_code == 401


def test_upload_requires_consent(db, tmp_path, monkeypatch, novels_api, active_user):
    patch_upload_dir(monkeypatch, tmp_path)
    app = make_novels_app(db, novels_api, active_user)

    with TestClient(app) as c:
        resp = c.post(
            "/api/novels/upload",
            files={"file": ("novel.txt", novel_txt_bytes(), "text/plain")},
            data={"title": "T", "author": "A", "consent_version": novel_support.UPLOAD_CONSENT_VERSION},
        )

    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "upload_consent_required"


def test_upload_rejects_stale_consent_version(db, tmp_path, monkeypatch, novels_api, active_user):
    patch_upload_dir(monkeypatch, tmp_path)
    app = make_novels_app(db, novels_api, active_user)

    with TestClient(app) as c:
        resp = c.post(
            "/api/novels/upload",
            files={"file": ("novel.txt", novel_txt_bytes(), "text/plain")},
            data={
                "title": "T",
                "author": "A",
                "consent_acknowledged": "true",
                "consent_version": "outdated-version",
            },
        )

    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "upload_consent_version_mismatch"
