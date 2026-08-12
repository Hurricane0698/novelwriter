from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import event

import app.core.ingest.worker as ingest_worker
from app.api import novel_support
from app.models import Chapter, Novel

from .support import make_novels_app, novel_txt_bytes, patch_upload_dir, run_ingest_and_index_jobs


def test_selfhost_upload_persists_novel_and_chapters(db, tmp_path, monkeypatch, novels_api, active_user):
    upload_dir = patch_upload_dir(monkeypatch, tmp_path)
    app = make_novels_app(db, novels_api, active_user)

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
        status_resp = c.get(f"/api/novels/{resp.json()['novel_id']}/status")

    assert resp.status_code == 202
    assert status_resp.status_code == 200
    payload = resp.json()
    status_payload = status_resp.json()
    assert payload["status"] == "accepted"
    assert payload["total_chapters"] is None
    assert status_payload["readiness"] == "accepting"
    assert status_payload["capabilities"] == {
        "chapters_available": False,
        "whole_book_index_available": False,
        "bootstrap_available": False,
        "recent_fallback_only": False,
    }
    assert status_payload["ingest"]["status"] == "queued"
    assert status_payload["ingest"]["stage"] == "accepted"

    novel = db.get(Novel, payload["novel_id"])
    assert novel is not None
    assert novel.title == "T"
    assert novel.author == "A"
    assert novel.language == "zh"
    assert novel.content_format == "plain_text"
    assert novel.owner_id == active_user.id
    assert novel.total_chapters == 0
    assert novel.window_index_status == "missing"
    assert novel.window_index_revision == 0
    assert novel.window_index_built_revision is None
    assert novel.window_index is None
    assert novel.file_path
    assert Path(novel.file_path).exists()
    assert str(upload_dir) in novel.file_path

    run_ingest_and_index_jobs()
    db.refresh(novel)
    assert novel.language == "zh"
    assert novel.total_chapters == 2
    assert novel.window_index_status == "fresh"
    assert novel.window_index_revision == 1
    assert novel.window_index_built_revision == 1
    assert novel.window_index is not None
    assert novel.window_index_error is None

    chapters = (
        db.query(Chapter)
        .filter(Chapter.novel_id == novel.id)
        .order_by(Chapter.chapter_number.asc())
        .all()
    )
    assert [ch.chapter_number for ch in chapters] == [1, 2]
    assert chapters[0].title == "开端"
    assert chapters[0].source_chapter_label == "第一章 开端"
    assert chapters[0].source_chapter_number == 1
    assert chapters[1].title == "继续"
    assert chapters[1].source_chapter_label == "第二章 继续"
    assert chapters[1].source_chapter_number == 2
    assert "第一章内容" in chapters[0].content


def test_upload_keeps_failed_ingest_state_after_accept(db, tmp_path, monkeypatch, novels_api, active_user):
    patch_upload_dir(monkeypatch, tmp_path)
    app = make_novels_app(db, novels_api, active_user)

    def failing_parse_source_file(*args, **kwargs):
        _ = (args, kwargs)
        raise ValueError("broken source")

    monkeypatch.setattr(ingest_worker, "parse_source_file", failing_parse_source_file)

    with TestClient(app) as c:
        response = c.post(
            "/api/novels/upload",
            files={"file": ("novel.txt", novel_txt_bytes(), "text/plain")},
            data={
                "title": "T",
                "author": "A",
                "consent_acknowledged": "true",
                "consent_version": novel_support.UPLOAD_CONSENT_VERSION,
            },
        )

        assert response.status_code == 202
        novel_id = response.json()["novel_id"]

        run_ingest_and_index_jobs()

        status_response = c.get(f"/api/novels/{novel_id}/status")

    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["readiness"] == "failed_retryable"
    assert status_payload["capabilities"] == {
        "chapters_available": False,
        "whole_book_index_available": False,
        "bootstrap_available": False,
        "recent_fallback_only": False,
    }
    assert status_payload["ingest"]["status"] == "failed"
    assert status_payload["ingest"]["stage"] == "failed"
    assert status_payload["ingest"]["error_code"] == "ingest_internal_error"
    assert status_payload["ingest"]["error"] == "稿件导入失败，请稍后重试"

    novel = db.get(Novel, novel_id)
    assert novel is not None
    assert novel.total_chapters == 0
    assert novel.window_index_status == "missing"
    assert db.query(Chapter).filter(Chapter.novel_id == novel.id).count() == 0


def test_markdown_upload_round_trips_native_format_and_volume_metadata(
    db,
    tmp_path,
    monkeypatch,
    novels_api,
    active_user,
):
    patch_upload_dir(monkeypatch, tmp_path)
    app = make_novels_app(db, novels_api, active_user)
    source = (
        "# 第一卷\n"
        "## 第一章 开端\n"
        "\n"
        "正文有 **强调**。\n"
        "\n"
        "### 小节\n"
        "- 一\n"
        "- 二\n"
        "## 第二章 继续\n"
        "尾声。\n"
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/novels/upload",
            files={"file": ("novel.md", source.encode("utf-8"), "text/markdown")},
            data={
                "title": "Markdown Novel",
                "author": "A",
                "consent_acknowledged": "true",
                "consent_version": novel_support.UPLOAD_CONSENT_VERSION,
            },
        )
        assert response.status_code == 202
        novel_id = response.json()["novel_id"]

        run_ingest_and_index_jobs()

        novel_response = client.get(f"/api/novels/{novel_id}")
        chapters_response = client.get(f"/api/novels/{novel_id}/chapters")
        meta_response = client.get(f"/api/novels/{novel_id}/chapters/meta")

    assert novel_response.status_code == 200
    assert novel_response.json()["content_format"] == "markdown"
    assert chapters_response.status_code == 200
    chapters = chapters_response.json()
    assert [chapter["source_volume_title"] for chapter in chapters] == ["第一卷", "第一卷"]
    assert chapters[0]["title"] == "开端"
    assert chapters[0]["source_chapter_label"] == "第一章 开端"
    assert chapters[0]["source_chapter_number"] == 1
    assert chapters[0]["content"] == "\n正文有 **强调**。\n\n### 小节\n- 一\n- 二\n"
    assert [chapter["source_volume_title"] for chapter in meta_response.json()] == [
        "第一卷",
        "第一卷",
    ]

    novel = db.get(Novel, novel_id)
    assert novel is not None
    assert novel.content_format == "markdown"


def test_markdown_upload_reports_structure_error_without_retrying_same_file(
    db,
    tmp_path,
    monkeypatch,
    novels_api,
    active_user,
):
    patch_upload_dir(monkeypatch, tmp_path)
    app = make_novels_app(db, novels_api, active_user)

    with TestClient(app) as client:
        response = client.post(
            "/api/novels/upload",
            files={"file": ("disguised.md", b"plain body without h2", "text/markdown")},
            data={
                "title": "Broken",
                "consent_acknowledged": "true",
                "consent_version": novel_support.UPLOAD_CONSENT_VERSION,
            },
        )
        novel_id = response.json()["novel_id"]
        run_ingest_and_index_jobs()

        status_response = client.get(f"/api/novels/{novel_id}/status")
        retry_response = client.post(f"/api/novels/{novel_id}/ingest/retry")

    assert status_response.status_code == 200
    assert status_response.json()["readiness"] == "failed_terminal"
    assert status_response.json()["ingest"]["error_code"] == "markdown_structure_invalid"
    assert retry_response.status_code == 409
    assert retry_response.json()["detail"]["code"] == "ingest_retry_not_allowed"


def test_markdown_upload_reports_non_utf8_encoding(
    db,
    tmp_path,
    monkeypatch,
    novels_api,
    active_user,
):
    patch_upload_dir(monkeypatch, tmp_path)
    app = make_novels_app(db, novels_api, active_user)

    with TestClient(app) as client:
        response = client.post(
            "/api/novels/upload",
            files={"file": ("gbk.md", "## 第一章\n正文".encode("gbk"), "text/markdown")},
            data={
                "title": "GBK Markdown",
                "consent_acknowledged": "true",
                "consent_version": novel_support.UPLOAD_CONSENT_VERSION,
            },
        )
        novel_id = response.json()["novel_id"]
        run_ingest_and_index_jobs()
        status_response = client.get(f"/api/novels/{novel_id}/status")

    assert status_response.status_code == 200
    assert status_response.json()["readiness"] == "failed_terminal"
    assert status_response.json()["ingest"]["error_code"] == "source_encoding_unsupported"


def test_upload_reports_missing_saved_source_without_retrying(
    db,
    tmp_path,
    monkeypatch,
    novels_api,
    active_user,
):
    patch_upload_dir(monkeypatch, tmp_path)
    app = make_novels_app(db, novels_api, active_user)

    with TestClient(app) as client:
        response = client.post(
            "/api/novels/upload",
            files={"file": ("novel.txt", novel_txt_bytes(), "text/plain")},
            data={
                "title": "Missing source",
                "consent_acknowledged": "true",
                "consent_version": novel_support.UPLOAD_CONSENT_VERSION,
            },
        )
        novel_id = response.json()["novel_id"]
        novel = db.get(Novel, novel_id)
        assert novel is not None
        Path(novel.file_path).unlink()

        run_ingest_and_index_jobs()
        status_response = client.get(f"/api/novels/{novel_id}/status")
        retry_response = client.post(f"/api/novels/{novel_id}/ingest/retry")

    assert status_response.status_code == 200
    assert status_response.json()["readiness"] == "failed_terminal"
    ingest = status_response.json()["ingest"]
    assert ingest["status"] == "failed"
    assert ingest["stage"] == "failed"
    assert ingest["error_code"] == "source_missing"
    assert retry_response.status_code == 409


def test_get_novel_exposes_window_index_lifecycle_contract(
    db,
    tmp_path,
    monkeypatch,
    novels_api,
    active_user,
    sql_engine,
):
    from app.core.indexing import enqueue_window_index_rebuild_job, mark_window_index_inputs_changed

    upload_dir = patch_upload_dir(monkeypatch, tmp_path)
    app = make_novels_app(db, novels_api, active_user)

    novel = Novel(
        title="T",
        author="A",
        language="zh",
        file_path=str(upload_dir / "t.txt"),
        total_chapters=1,
        owner_id=active_user.id,
    )
    db.add(novel)
    db.commit()
    db.refresh(novel)
    db.add(Chapter(novel_id=novel.id, chapter_number=1, title="第一章", content="这里是第一章内容。"))
    db.commit()

    revision = mark_window_index_inputs_changed(novel)
    enqueue_window_index_rebuild_job(db, novel_id=novel.id, target_revision=revision)
    db.commit()
    detail_path = f"/api/novels/{novel.id}"

    queries = {"novels": []}

    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        _ = (conn, cursor, parameters, context, executemany)
        normalized = " ".join(statement.lower().split())
        if normalized.startswith("select") and " from novels " in normalized:
            queries["novels"].append(normalized)

    event.listen(sql_engine, "before_cursor_execute", before_cursor_execute)
    try:
        with TestClient(app) as c:
            response = c.get(detail_path)
    finally:
        event.remove(sql_engine, "before_cursor_execute", before_cursor_execute)

    assert response.status_code == 200
    payload = response.json()
    assert payload["is_seeded_demo"] is False
    assert payload["window_index"] == {
        "status": "missing",
        "revision": 1,
        "built_revision": None,
        "error": None,
        "readiness": "degraded_ready",
        "capabilities": {
            "chapters_available": True,
            "whole_book_index_available": False,
            "bootstrap_available": True,
            "recent_fallback_only": True,
        },
        "ingest": None,
        "job": {
            "status": "queued",
            "target_revision": 1,
            "completed_revision": None,
            "error": None,
            "created_at": payload["window_index"]["job"]["created_at"],
            "started_at": None,
            "finished_at": None,
            "metrics": None,
        },
    }
    assert len(queries["novels"]) == 1
    assert "window_index as novels_window_index" not in queries["novels"][0]
    assert "window_index is not null" in queries["novels"][0]


def test_get_novel_exposes_window_index_job_metrics_after_success(
    db,
    tmp_path,
    monkeypatch,
    novels_api,
    active_user,
):
    from app.core.indexing import enqueue_window_index_rebuild_job, mark_window_index_inputs_changed

    upload_dir = patch_upload_dir(monkeypatch, tmp_path)
    app = make_novels_app(db, novels_api, active_user)

    novel = Novel(
        title="T",
        author="A",
        language="zh",
        file_path=str(upload_dir / "metrics.txt"),
        total_chapters=1,
        owner_id=active_user.id,
    )
    db.add(novel)
    db.commit()
    db.refresh(novel)
    db.add(Chapter(novel_id=novel.id, chapter_number=1, title="第一章", content="这里是第一章内容。"))
    db.commit()

    revision = mark_window_index_inputs_changed(novel)
    enqueue_window_index_rebuild_job(db, novel_id=novel.id, target_revision=revision)
    db.commit()
    run_ingest_and_index_jobs()

    with TestClient(app) as c:
        response = c.get(f"/api/novels/{novel.id}")

    assert response.status_code == 200
    job = response.json()["window_index"]["job"]
    assert job["status"] == "completed"
    assert job["completed_revision"] == 1
    assert job["started_at"] is not None
    assert job["finished_at"] is not None
    assert job["metrics"]["full_build_ms"] >= 0
    assert job["metrics"]["load_chapters_ms"] >= 0
    assert job["metrics"]["payload_bytes"] > 0
    assert job["metrics"]["index_backend"] == "state_proto_v2"
    assert job["metrics"]["executor_backend"] == "rust"
    assert job["metrics"]["segment_count"] > 0
    assert job["metrics"]["plan_mode"] in {"full", "incremental", "reuse_existing"}
    assert job["metrics"]["peak_rss_kib"] is None or job["metrics"]["peak_rss_kib"] >= 0


def test_list_novels_batches_window_index_job_reads(
    db,
    tmp_path,
    monkeypatch,
    novels_api,
    active_user,
    sql_engine,
):
    from app.core.indexing import enqueue_window_index_rebuild_job, mark_window_index_inputs_changed

    upload_dir = patch_upload_dir(monkeypatch, tmp_path)
    app = make_novels_app(db, novels_api, active_user)

    for idx in range(3):
        novel = Novel(
            title=f"T{idx}",
            author="A",
            language="zh",
            file_path=str(upload_dir / f"t{idx}.txt"),
            total_chapters=1,
            owner_id=active_user.id,
        )
        db.add(novel)
        db.flush()
        db.add(
            Chapter(
                novel_id=novel.id,
                chapter_number=1,
                title="第一章",
                content="这里是第一章内容。",
            )
        )
        revision = mark_window_index_inputs_changed(novel)
        enqueue_window_index_rebuild_job(db, novel_id=novel.id, target_revision=revision)
    db.commit()

    query_counts = {"derived_asset_jobs": 0, "novels": []}

    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        _ = (conn, cursor, parameters, context, executemany)
        normalized = " ".join(statement.lower().split())
        if "from derived_asset_jobs" in normalized:
            query_counts["derived_asset_jobs"] += 1
        if normalized.startswith("select") and " from novels " in normalized:
            query_counts["novels"].append(normalized)

    event.listen(sql_engine, "before_cursor_execute", before_cursor_execute)
    try:
        with TestClient(app) as c:
            query_counts["derived_asset_jobs"] = 0
            query_counts["novels"].clear()
            response = c.get("/api/novels")
    finally:
        event.remove(sql_engine, "before_cursor_execute", before_cursor_execute)

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 3
    assert query_counts["derived_asset_jobs"] == 1
    assert len(query_counts["novels"]) == 1
    assert "window_index as novels_window_index" not in query_counts["novels"][0]
    assert "window_index is not null" in query_counts["novels"][0]
    assert all(item["is_seeded_demo"] is False for item in payload)
    assert {item["window_index"]["job"]["status"] for item in payload} == {"queued"}


def test_get_novel_marks_seeded_demo_from_demo_asset_identity(db, novels_api, active_user):
    from app.core.seed_demo import DEMO_TXT

    app = make_novels_app(db, novels_api, active_user)

    novel = Novel(
        title="原创试读样例",
        author="A",
        language="zh",
        file_path=str(DEMO_TXT),
        total_chapters=1,
        owner_id=active_user.id,
    )
    db.add(novel)
    db.commit()
    db.refresh(novel)

    with TestClient(app) as c:
        response = c.get(f"/api/novels/{novel.id}")

    assert response.status_code == 200
    assert response.json()["is_seeded_demo"] is True
