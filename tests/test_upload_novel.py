"""
Tests for novel upload endpoint (multipart file import).

Focus: product flow contract — user uploads .txt → backend parses → persists Novel + Chapters.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.models import Chapter, Novel, User


engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def _make_app(db, router) -> FastAPI:
    app = FastAPI()
    app.include_router(router)

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    return app


def _novel_txt_bytes() -> bytes:
    # Two chapters; titles must appear at line start to match parser regex.
    text = "\n".join(
        [
            "第一章 开端",
            "这里是第一章内容。",
            "",
            "第二章 继续",
            "这里是第二章内容。",
            "",
        ]
    )
    return text.encode("utf-8")


class TestUploadNovel:
    def test_selfhost_upload_persists_novel_and_chapters(self, db, tmp_path, monkeypatch):
        from app.api import novels as novels_api
        from app.core.auth import get_current_user_or_default

        user = User(id=1, username="u", hashed_password="x", role="admin", is_active=True)
        db.add(user)
        db.commit()

        # Isolate filesystem writes.
        upload_dir = tmp_path / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(novels_api, "UPLOAD_DIR", upload_dir)

        app = _make_app(db, novels_api.router)
        app.dependency_overrides[get_current_user_or_default] = lambda: user

        with TestClient(app) as c:
            resp = c.post(
                "/api/novels/upload",
                files={"file": ("novel.txt", _novel_txt_bytes(), "text/plain")},
                data={
                    "title": "T",
                    "author": "A",
                    "consent_acknowledged": "true",
                    "consent_version": novels_api.UPLOAD_CONSENT_VERSION,
                },
            )

        assert resp.status_code == 200
        payload = resp.json()
        assert payload["total_chapters"] == 2

        novel = db.get(Novel, payload["novel_id"])
        assert novel is not None
        assert novel.title == "T"
        assert novel.author == "A"
        assert novel.owner_id == user.id

        # File path is persisted and should point into the isolated upload dir.
        assert novel.file_path
        assert Path(novel.file_path).exists()
        assert str(upload_dir) in novel.file_path

        chapters = (
            db.query(Chapter)
            .filter(Chapter.novel_id == novel.id)
            .order_by(Chapter.chapter_number.asc())
            .all()
        )
        assert [ch.chapter_number for ch in chapters] == [1, 2]
        assert chapters[0].title.startswith("第一章")
        assert "第一章内容" in chapters[0].content

    def test_upload_rejects_non_txt(self, db, tmp_path, monkeypatch):
        from app.api import novels as novels_api
        from app.core.auth import get_current_user_or_default

        user = User(id=1, username="u", hashed_password="x", role="admin", is_active=True)
        db.add(user)
        db.commit()

        upload_dir = tmp_path / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(novels_api, "UPLOAD_DIR", upload_dir)

        app = _make_app(db, novels_api.router)
        app.dependency_overrides[get_current_user_or_default] = lambda: user

        with TestClient(app) as c:
            resp = c.post(
                "/api/novels/upload",
                files={"file": ("novel.md", b"# hi", "text/markdown")},
                data={
                    "title": "T",
                    "author": "A",
                    "consent_acknowledged": "true",
                    "consent_version": novels_api.UPLOAD_CONSENT_VERSION,
                },
            )

        assert resp.status_code == 400

    def test_upload_rejects_too_large(self, db, tmp_path, monkeypatch):
        from app.api import novels as novels_api
        from app.core.auth import get_current_user_or_default

        user = User(id=1, username="u", hashed_password="x", role="admin", is_active=True)
        db.add(user)
        db.commit()

        upload_dir = tmp_path / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(novels_api, "UPLOAD_DIR", upload_dir)

        # 30MB + 1 byte
        too_big = b"a" * (30 * 1024 * 1024 + 1)

        app = _make_app(db, novels_api.router)
        app.dependency_overrides[get_current_user_or_default] = lambda: user

        with TestClient(app) as c:
            resp = c.post(
                "/api/novels/upload",
                files={"file": ("novel.txt", too_big, "text/plain")},
                data={
                    "title": "T",
                    "author": "A",
                    "consent_acknowledged": "true",
                    "consent_version": novels_api.UPLOAD_CONSENT_VERSION,
                },
            )

        assert resp.status_code == 413
        # Regression: partial writes are cleaned up when the upload is rejected.
        assert list(upload_dir.iterdir()) == []

    def test_hosted_upload_requires_auth(self, db, tmp_path, monkeypatch):
        from app.api import novels as novels_api
        import app.core.auth as auth_core

        upload_dir = tmp_path / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(novels_api, "UPLOAD_DIR", upload_dir)

        # Hosted mode requires an Authorization token; we don't provide one here.
        monkeypatch.setattr(auth_core, "get_settings", lambda: MagicMock(deploy_mode="hosted"))

        app = _make_app(db, novels_api.router)

        with TestClient(app) as c:
            resp = c.post(
                "/api/novels/upload",
                files={"file": ("novel.txt", _novel_txt_bytes(), "text/plain")},
                data={
                    "title": "T",
                    "author": "A",
                    "consent_acknowledged": "true",
                    "consent_version": novels_api.UPLOAD_CONSENT_VERSION,
                },
            )

        assert resp.status_code == 401

    def test_upload_requires_consent(self, db, tmp_path, monkeypatch):
        from app.api import novels as novels_api
        from app.core.auth import get_current_user_or_default

        user = User(id=1, username="u", hashed_password="x", role="admin", is_active=True)
        db.add(user)
        db.commit()

        upload_dir = tmp_path / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(novels_api, "UPLOAD_DIR", upload_dir)

        app = _make_app(db, novels_api.router)
        app.dependency_overrides[get_current_user_or_default] = lambda: user

        with TestClient(app) as c:
            resp = c.post(
                "/api/novels/upload",
                files={"file": ("novel.txt", _novel_txt_bytes(), "text/plain")},
                data={"title": "T", "author": "A", "consent_version": novels_api.UPLOAD_CONSENT_VERSION},
            )

        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "upload_consent_required"

    def test_upload_rejects_stale_consent_version(self, db, tmp_path, monkeypatch):
        from app.api import novels as novels_api
        from app.core.auth import get_current_user_or_default

        user = User(id=1, username="u", hashed_password="x", role="admin", is_active=True)
        db.add(user)
        db.commit()

        upload_dir = tmp_path / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(novels_api, "UPLOAD_DIR", upload_dir)

        app = _make_app(db, novels_api.router)
        app.dependency_overrides[get_current_user_or_default] = lambda: user

        with TestClient(app) as c:
            resp = c.post(
                "/api/novels/upload",
                files={"file": ("novel.txt", _novel_txt_bytes(), "text/plain")},
                data={
                    "title": "T",
                    "author": "A",
                    "consent_acknowledged": "true",
                    "consent_version": "outdated-version",
                },
            )

        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "upload_consent_version_mismatch"
