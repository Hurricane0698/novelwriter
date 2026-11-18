from __future__ import annotations


from fastapi.testclient import TestClient


from .support import make_novels_app, patch_upload_dir


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
            },
        )

    assert resp.status_code == 413
    assert resp.json()["detail"]["code"] == "upload_file_too_large"
    assert resp.json()["detail"]["max_megabytes"] == 30
    assert list(upload_dir.iterdir()) == []
