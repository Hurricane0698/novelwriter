from __future__ import annotations

from fastapi.testclient import TestClient

import app.core.ingest.worker as ingest_worker
from app.api import novel_support
from app.content_formats import PLAIN_TEXT_CONTENT_FORMAT, NovelContentFormat
from app.core.parser import ParsedChapter

from .support import (
    english_novel_txt_bytes,
    japanese_novel_txt_bytes,
    korean_novel_txt_bytes,
    make_novels_app,
    novel_txt_bytes,
    patch_upload_dir,
    run_ingest_and_index_jobs,
)


def test_upload_normalizes_explicit_language(db, tmp_path, monkeypatch, novels_api, active_user):
    patch_upload_dir(monkeypatch, tmp_path)
    app = make_novels_app(db, novels_api, active_user)

    with TestClient(app) as c:
        resp = c.post(
            "/api/novels/upload",
            files={"file": ("novel.txt", novel_txt_bytes(), "text/plain")},
            data={
                "title": "T",
                "author": "A",
                "language": "EN_US",
                "consent_acknowledged": "true",
                "consent_version": novel_support.UPLOAD_CONSENT_VERSION,
            },
        )

    assert resp.status_code == 202
    novel = db.get(ingest_worker.Novel, resp.json()["novel_id"])
    assert novel is not None
    assert novel.language == "en-us"
    run_ingest_and_index_jobs()
    db.refresh(novel)
    assert novel.language == "en-us"


def test_upload_auto_detects_english_language_when_omitted(db, tmp_path, monkeypatch, novels_api, active_user):
    patch_upload_dir(monkeypatch, tmp_path)
    app = make_novels_app(db, novels_api, active_user)

    with TestClient(app) as c:
        resp = c.post(
            "/api/novels/upload",
            files={"file": ("novel.txt", english_novel_txt_bytes(), "text/plain")},
            data={
                "title": "T",
                "author": "A",
                "consent_acknowledged": "true",
                "consent_version": novel_support.UPLOAD_CONSENT_VERSION,
            },
        )

    assert resp.status_code == 202
    novel = db.get(ingest_worker.Novel, resp.json()["novel_id"])
    assert novel is not None
    assert novel.language == "zh"
    run_ingest_and_index_jobs()
    db.refresh(novel)
    assert novel.language == "en"


def test_upload_auto_detects_japanese_language_when_omitted(db, tmp_path, monkeypatch, novels_api, active_user):
    patch_upload_dir(monkeypatch, tmp_path)
    app = make_novels_app(db, novels_api, active_user)

    with TestClient(app) as c:
        resp = c.post(
            "/api/novels/upload",
            files={"file": ("novel.txt", japanese_novel_txt_bytes(), "text/plain")},
            data={
                "title": "T",
                "author": "A",
                "consent_acknowledged": "true",
                "consent_version": novel_support.UPLOAD_CONSENT_VERSION,
            },
        )

    assert resp.status_code == 202
    novel = db.get(ingest_worker.Novel, resp.json()["novel_id"])
    assert novel is not None
    assert novel.language == "zh"
    run_ingest_and_index_jobs()
    db.refresh(novel)
    assert novel.language == "ja"


def test_upload_auto_detects_korean_language_when_omitted(db, tmp_path, monkeypatch, novels_api, active_user):
    patch_upload_dir(monkeypatch, tmp_path)
    app = make_novels_app(db, novels_api, active_user)

    with TestClient(app) as c:
        resp = c.post(
            "/api/novels/upload",
            files={"file": ("novel.txt", korean_novel_txt_bytes(), "text/plain")},
            data={
                "title": "T",
                "author": "A",
                "consent_acknowledged": "true",
                "consent_version": novel_support.UPLOAD_CONSENT_VERSION,
            },
        )

    assert resp.status_code == 202
    novel = db.get(ingest_worker.Novel, resp.json()["novel_id"])
    assert novel is not None
    assert novel.language == "zh"
    run_ingest_and_index_jobs()
    db.refresh(novel)
    assert novel.language == "ko"


def test_upload_passes_normalized_language_to_parser(db, tmp_path, monkeypatch, novels_api, active_user):
    from app.core.ingest.contracts import ParsedNovelIngest

    patch_upload_dir(monkeypatch, tmp_path)
    seen: dict[str, str | None] = {"language": None}

    def fake_parse(
        path: str,
        *,
        content_format: NovelContentFormat,
        requested_language: str | None = None,
    ):
        assert path.endswith(".txt")
        assert content_format == PLAIN_TEXT_CONTENT_FORMAT
        seen["language"] = requested_language
        return ParsedNovelIngest(
            source_chars=len("plain body"),
            resolved_language=requested_language or "ja-jp",
            chapters=[
                ParsedChapter(
                    title="Opening",
                    content="content",
                    source_chapter_label="Chapter 1 Opening",
                    source_chapter_number=1,
                )
            ],
        )

    monkeypatch.setattr(ingest_worker, "parse_source_file", fake_parse)
    app = make_novels_app(db, novels_api, active_user)

    with TestClient(app) as c:
        resp = c.post(
            "/api/novels/upload",
            files={"file": ("novel.txt", b"plain body", "text/plain")},
            data={
                "title": "T",
                "author": "A",
                "language": "JA_JP",
                "consent_acknowledged": "true",
                "consent_version": novel_support.UPLOAD_CONSENT_VERSION,
            },
        )

    assert resp.status_code == 202
    run_ingest_and_index_jobs()
    assert seen["language"] == "ja-jp"


def test_upload_passes_detected_language_to_parser_when_language_omitted(
    db,
    tmp_path,
    monkeypatch,
    novels_api,
    active_user,
):
    from app.core.ingest.contracts import ParsedNovelIngest

    patch_upload_dir(monkeypatch, tmp_path)
    seen: dict[str, str | None] = {"language": None}

    def fake_parse(
        path: str,
        *,
        content_format: NovelContentFormat,
        requested_language: str | None = None,
    ):
        assert path.endswith(".txt")
        assert content_format == PLAIN_TEXT_CONTENT_FORMAT
        seen["language"] = requested_language
        return ParsedNovelIngest(
            source_chars=len("Chapter 1 Beginning\nAlice walked home."),
            resolved_language="en",
            chapters=[
                ParsedChapter(
                    title="Beginning",
                    content="content",
                    source_chapter_label="Chapter 1 Beginning",
                    source_chapter_number=1,
                )
            ],
        )

    monkeypatch.setattr(ingest_worker, "parse_source_file", fake_parse)
    app = make_novels_app(db, novels_api, active_user)

    with TestClient(app) as c:
        resp = c.post(
            "/api/novels/upload",
            files={"file": ("novel.txt", b"plain body", "text/plain")},
            data={
                "title": "T",
                "author": "A",
                "consent_acknowledged": "true",
                "consent_version": novel_support.UPLOAD_CONSENT_VERSION,
            },
        )

    assert resp.status_code == 202
    run_ingest_and_index_jobs()
    assert seen["language"] is None
    novel = db.get(ingest_worker.Novel, resp.json()["novel_id"])
    assert novel is not None
    db.refresh(novel)
    assert novel.language == "en"
