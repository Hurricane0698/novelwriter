from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from app.core.derived_assets import DERIVED_ASSET_KIND_WINDOW_INDEX
from app.core.ingest import (
    enqueue_next_deferred_window_index_build,
    enqueue_novel_ingest_job,
    inspect_novel_ingest_job,
    is_novel_ingest_retry_allowed,
    reset_novel_ingest_job_for_retry,
    resolve_ingest_policy,
    run_novel_ingest_job_until_idle,
)
from app.core.ingest.job_store import claim_novel_ingest_job
from app.core.bootstrap import (
    BOOTSTRAP_RESULT_QUEUED_SOURCE_INGEST_AUTO,
    build_bootstrap_trigger_result,
)
from app.core.indexing import run_next_window_index_rebuild_job
from app.core.llm_config import ResolvedLlmConfig
from app.core.world import bootstrap_application as bootstrap_app
from app.config import Settings
from app.database import Base, get_db
from app.models import BootstrapJob, Chapter, DerivedAssetJob, Novel, NovelIngestJob, User


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


@pytest.fixture
def user(db):
    user = User(id=1, username="u", hashed_password="x", role="admin", is_active=True)
    db.add(user)
    db.commit()
    return user


@pytest.fixture
def client(db, user):
    from app.api import novels as novels_api
    from app.core.auth import get_current_user_or_default

    app = FastAPI()
    app.include_router(novels_api.router)

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_or_default] = lambda: user
    with TestClient(app) as c:
        yield c


def _write_source(tmp_path, name: str, text: str) -> str:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


def _selfhost_llm_ready_settings() -> Settings:
    return Settings(
        deploy_mode="selfhost",
        openai_api_key="sk-test",
        openai_base_url="https://api.openai.com/v1",
        openai_model="gpt-4o-mini",
        _env_file=None,
    )


def _selfhost_llm_missing_settings() -> Settings:
    return Settings(
        deploy_mode="selfhost",
        openai_api_key="",
        openai_base_url="",
        openai_model="",
        _env_file=None,
    )


def test_ingest_job_reclaims_stale_running_row_and_completes_without_auto_bootstrap_when_llm_missing(
    db,
    tmp_path,
    user,
):
    file_path = _write_source(
        tmp_path,
        "novel.txt",
        "第一章 开端\n这里是第一章内容。\n\n第二章 继续\n这里是第二章内容。\n",
    )
    novel = Novel(title="T", author="A", language="zh", file_path=file_path, owner_id=user.id)
    db.add(novel)
    db.commit()
    db.refresh(novel)

    enqueue_novel_ingest_job(db, novel_id=novel.id, source_bytes=123, requested_language=None)
    db.commit()

    job = db.query(NovelIngestJob).filter(NovelIngestJob.novel_id == novel.id).first()
    assert job is not None
    stale_time = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=10)
    job.status = "running"
    job.stage = "parsing"
    job.lease_owner = "stale-worker"
    job.lease_expires_at = stale_time
    job.started_at = stale_time
    db.commit()

    assert run_novel_ingest_job_until_idle(
        novel_id=novel.id,
        session_factory=TestingSessionLocal,
        settings=_selfhost_llm_missing_settings(),
    ) is True

    db.refresh(novel)
    db.refresh(job)
    chapters = db.query(Chapter).filter(Chapter.novel_id == novel.id).order_by(Chapter.chapter_number.asc()).all()
    assert job.status == "completed"
    assert job.stage == "completed"
    assert job.error is None
    assert job.lease_owner is None
    assert novel.total_chapters == 2
    assert novel.window_index_revision == 1
    assert [chapter.chapter_number for chapter in chapters] == [1, 2]

    bootstrap_job = db.query(BootstrapJob).filter(BootstrapJob.novel_id == novel.id).first()
    assert bootstrap_job is None


def test_ingest_job_queues_auto_bootstrap_when_selfhost_llm_is_configured(db, tmp_path, user):
    file_path = _write_source(
        tmp_path,
        "novel-with-llm.txt",
        "第一章 开端\n这里是第一章内容。\n\n第二章 继续\n这里是第二章内容。\n",
    )
    novel = Novel(title="T", author="A", language="zh", file_path=file_path, owner_id=user.id)
    db.add(novel)
    db.commit()
    db.refresh(novel)

    enqueue_novel_ingest_job(db, novel_id=novel.id, source_bytes=123, requested_language=None)
    db.commit()

    assert run_novel_ingest_job_until_idle(
        novel_id=novel.id,
        session_factory=TestingSessionLocal,
        settings=_selfhost_llm_ready_settings(),
    ) is True

    bootstrap_job = db.query(BootstrapJob).filter(BootstrapJob.novel_id == novel.id).first()
    assert bootstrap_job is not None
    assert bootstrap_job.mode == "initial"
    assert bootstrap_job.status == "pending"
    assert bootstrap_job.result["index_refresh_only"] is False
    assert bootstrap_job.result["_queued_source"] == BOOTSTRAP_RESULT_QUEUED_SOURCE_INGEST_AUTO
    assert bootstrap_job.result["_queued_user_id"] == user.id

    observed: list[dict[str, object]] = []

    async def _runner(
        job_id: int,
        *,
        session_factory,
        llm_config: ResolvedLlmConfig,
        user_id=None,
    ):
        observed.append(
            {
                "job_id": job_id,
                "user_id": user_id,
                "llm_config": llm_config,
                "session_factory": session_factory,
            }
        )

    assert bootstrap_app.run_next_bootstrap_job(
        session_factory=TestingSessionLocal,
        settings=_selfhost_llm_ready_settings(),
        background_job_runner=_runner,
    ) is True
    assert observed[0]["job_id"] == bootstrap_job.id
    assert observed[0]["user_id"] == user.id
    assert observed[0]["llm_config"] == ResolvedLlmConfig(
        base_url="https://api.openai.com/v1",
        api_key="sk-test",
        model="gpt-4o-mini",
        billing_source_hint="selfhost",
        source="selfhost_settings",
    )


def test_selfhost_worker_skips_manual_bootstrap_jobs_to_preserve_request_scoped_byok(db, tmp_path, user):
    file_path = _write_source(tmp_path, "manual-bootstrap.txt", "第一章 开端\n这里是第一章内容。\n")
    novel = Novel(title="T", author="A", language="zh", file_path=file_path, owner_id=user.id, total_chapters=1)
    db.add(novel)
    db.commit()
    db.refresh(novel)
    db.add(Chapter(novel_id=novel.id, chapter_number=1, title="第一章", content="这里是第一章内容。"))
    job = BootstrapJob(
        novel_id=novel.id,
        mode="initial",
        status="pending",
        progress={"step": 0, "detail": "queued"},
        result=build_bootstrap_trigger_result(mode="initial", user_id=user.id),
    )
    db.add(job)
    db.commit()

    observed: list[int] = []

    async def _runner(
        job_id: int,
        *,
        session_factory,
        llm_config: ResolvedLlmConfig,
        user_id=None,
    ):
        _ = (session_factory, user_id, llm_config)
        observed.append(job_id)

    assert bootstrap_app.run_next_bootstrap_job(
        session_factory=TestingSessionLocal,
        settings=_selfhost_llm_ready_settings(),
        background_job_runner=_runner,
    ) is False
    assert observed == []


def test_ingest_policy_centralizes_normal_large_and_upload_limit_reject_thresholds():
    settings = SimpleNamespace(
        upload_max_megabytes=1,
        ingest_large_source_bytes=100,
        ingest_large_source_chars=100,
        ingest_large_chapter_count=10,
    )

    normal = resolve_ingest_policy(
        policy_input=SimpleNamespace(source_bytes=10, source_chars=10, chapter_count=1),
        settings=settings,
    )
    large = resolve_ingest_policy(
        policy_input=SimpleNamespace(source_bytes=150, source_chars=10, chapter_count=1),
        settings=settings,
    )
    large_by_chars = resolve_ingest_policy(
        policy_input=SimpleNamespace(source_bytes=10, source_chars=220, chapter_count=1),
        settings=settings,
    )
    large_by_chapters = resolve_ingest_policy(
        policy_input=SimpleNamespace(source_bytes=10, source_chars=10, chapter_count=40),
        settings=settings,
    )
    reject = resolve_ingest_policy(
        policy_input=SimpleNamespace(source_bytes=2 * 1024 * 1024, source_chars=10, chapter_count=1),
        settings=settings,
    )

    assert (normal.size_tier, normal.auto_index_plan, normal.readiness_mode) == ("normal", "immediate", "full_target")
    assert (large.size_tier, large.auto_index_plan, large.bootstrap_plan) == ("large", "deferred", "defer_until_index")
    assert (large_by_chars.size_tier, large_by_chars.auto_index_plan, large_by_chars.readiness_mode) == (
        "large",
        "deferred",
        "degraded_target",
    )
    assert (large_by_chapters.size_tier, large_by_chapters.auto_index_plan, large_by_chapters.bootstrap_plan) == (
        "large",
        "deferred",
        "defer_until_index",
    )
    assert (reject.size_tier, reject.auto_index_plan, reject.bootstrap_plan) == ("reject", "skip_auto", "manual_only")


def test_ingest_policy_treats_within_upload_limit_huge_manuscript_as_deferred_large():
    decision = resolve_ingest_policy(
        policy_input=SimpleNamespace(
            source_bytes=14_463_031,
            source_chars=5_246_001,
            chapter_count=1_399,
        ),
        settings=SimpleNamespace(
            upload_max_megabytes=30,
            ingest_large_source_bytes=100,
            ingest_large_source_chars=100,
            ingest_large_chapter_count=10,
        ),
    )

    assert (decision.size_tier, decision.auto_index_plan, decision.bootstrap_plan) == (
        "large",
        "deferred",
        "defer_until_index",
    )


@pytest.mark.parametrize(
    "error_code",
    [
        "source_missing",
        "source_encoding_unsupported",
        "markdown_structure_invalid",
        None,
    ],
)
def test_status_endpoint_and_retry_admission_share_terminal_ingest_contract(
    client,
    db,
    tmp_path,
    user,
    error_code,
):
    file_path = _write_source(tmp_path, "failed.txt", "坏掉的内容")
    novel = Novel(title="T", author="A", language="zh", file_path=file_path, owner_id=user.id)
    db.add(novel)
    db.commit()
    db.refresh(novel)
    job = NovelIngestJob(
        novel_id=novel.id,
        status="failed",
        stage="failed",
        source_bytes=10,
        error_code=error_code,
        error="稿件源文件需要修复后重新上传",
    )
    db.add(job)
    db.commit()

    response = client.get(f"/api/novels/{novel.id}/status")
    retry_response = client.post(f"/api/novels/{novel.id}/ingest/retry")

    assert response.status_code == 200
    payload = response.json()
    assert payload["readiness"] == "failed_terminal"
    assert payload["capabilities"] == {
        "chapters_available": False,
        "whole_book_index_available": False,
        "bootstrap_available": False,
        "recent_fallback_only": False,
    }
    assert payload["ingest"]["status"] == "failed"
    assert payload["ingest"]["stage"] == "failed"
    assert payload["ingest"]["error_code"] == error_code
    assert payload["ingest"]["error"] == "稿件源文件需要修复后重新上传"
    assert retry_response.status_code == 409
    assert retry_response.json()["detail"]["code"] == "ingest_retry_not_allowed"


def test_status_endpoint_surfaces_huge_within_upload_limit_file_as_deferred_large(client, db, tmp_path, user):
    file_path = _write_source(tmp_path, "long.txt", "第一章 开端\n内容\n")
    novel = Novel(
        title="T",
        author="A",
        language="zh",
        file_path=file_path,
        owner_id=user.id,
        total_chapters=1,
        window_index_status="missing",
        window_index_revision=1,
        window_index_built_revision=None,
    )
    db.add(novel)
    db.commit()
    db.refresh(novel)
    db.add(Chapter(novel_id=novel.id, chapter_number=1, title="第一章", content="内容"))
    db.add(
        NovelIngestJob(
            novel_id=novel.id,
            status="completed",
            stage="completed",
            size_tier="large",
            source_bytes=14_463_031,
            source_chars=5_246_001,
            chapter_count=1_399,
            resolved_language="zh",
            auto_index_plan="deferred",
            bootstrap_plan="defer_until_index",
            readiness_mode="degraded_target",
        )
    )
    db.commit()

    response = client.get(f"/api/novels/{novel.id}/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "missing"
    assert payload["readiness"] == "degraded_ready"
    assert payload["capabilities"] == {
        "chapters_available": True,
        "whole_book_index_available": False,
        "bootstrap_available": False,
        "recent_fallback_only": True,
    }
    assert payload["ingest"]["size_tier"] == "large"
    assert payload["ingest"]["auto_index_plan"] == "deferred"
    assert payload["ingest"]["bootstrap_plan"] == "defer_until_index"


def test_status_endpoint_surfaces_defer_until_index_bootstrap_unavailable_until_index_ready(client, db, tmp_path, user):
    file_path = _write_source(tmp_path, "large.txt", "第一章 开端\n内容\n")
    novel = Novel(
        title="T",
        author="A",
        language="zh",
        file_path=file_path,
        owner_id=user.id,
        total_chapters=1,
        window_index_status="missing",
        window_index_revision=1,
        window_index_built_revision=None,
    )
    db.add(novel)
    db.commit()
    db.refresh(novel)
    db.add(Chapter(novel_id=novel.id, chapter_number=1, title="第一章", content="内容"))
    db.add(
        NovelIngestJob(
            novel_id=novel.id,
            status="completed",
            stage="completed",
            size_tier="large",
            source_bytes=2_500_000,
            source_chars=500_000,
            chapter_count=1,
            resolved_language="zh",
            auto_index_plan="deferred",
            bootstrap_plan="defer_until_index",
            readiness_mode="degraded_target",
        )
    )
    db.commit()

    response = client.get(f"/api/novels/{novel.id}/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["readiness"] == "degraded_ready"
    assert payload["capabilities"] == {
        "chapters_available": True,
        "whole_book_index_available": False,
        "bootstrap_available": False,
        "recent_fallback_only": True,
    }
    assert payload["ingest"]["bootstrap_plan"] == "defer_until_index"


def test_retry_endpoint_resets_failed_ingest_job_to_accepted(client, db, tmp_path, user):
    file_path = _write_source(
        tmp_path,
        "retry.txt",
        "第一章 开端\n这里是第一章内容。\n\n第二章 继续\n这里是第二章内容。\n",
    )
    novel = Novel(title="T", author="A", language="zh", file_path=file_path, owner_id=user.id)
    db.add(novel)
    db.commit()
    db.refresh(novel)
    db.add(
        NovelIngestJob(
            novel_id=novel.id,
            status="failed",
            stage="failed",
            source_bytes=128,
            error_code="ingest_internal_error",
            error="稿件导入失败，请稍后重试",
        )
    )
    db.commit()

    status_response = client.get(f"/api/novels/{novel.id}/status")
    response = client.post(f"/api/novels/{novel.id}/ingest/retry")

    assert status_response.status_code == 200
    assert status_response.json()["readiness"] == "failed_retryable"
    assert response.status_code == 202
    payload = response.json()
    assert payload["window_index"]["readiness"] == "accepting"
    assert payload["window_index"]["ingest"]["status"] == "queued"
    assert payload["window_index"]["ingest"]["stage"] == "accepted"

    job = db.query(NovelIngestJob).filter(NovelIngestJob.novel_id == novel.id).first()
    assert job is not None
    assert job.status == "queued"
    assert job.stage == "accepted"
    assert job.error_code is None
    assert job.error is None


def test_retry_reset_admits_failed_job_only_once(db, tmp_path, user):
    novel = Novel(
        title="T",
        author="A",
        language="zh",
        file_path=_write_source(tmp_path, "retry-once.txt", "第一章\n正文"),
        owner_id=user.id,
    )
    db.add(novel)
    db.commit()
    db.refresh(novel)
    job = NovelIngestJob(
        novel_id=novel.id,
        status="failed",
        stage="failed",
        source_bytes=64,
        error_code="ingest_internal_error",
        error="稿件导入失败，请稍后重试",
        finished_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    db.add(job)
    db.commit()

    assert reset_novel_ingest_job_for_retry(db, novel_id=novel.id) is True
    assert reset_novel_ingest_job_for_retry(db, novel_id=novel.id) is False
    db.commit()
    db.refresh(job)

    assert job.status == "queued"
    assert job.stage == "accepted"
    assert job.error_code is None
    assert job.error is None
    assert job.finished_at is None


def test_retry_reset_preserves_running_claim_after_failed_snapshot(db, tmp_path, user):
    novel = Novel(
        title="T",
        author="A",
        language="zh",
        file_path=_write_source(tmp_path, "retry-claimed.txt", "第一章\n正文"),
        owner_id=user.id,
    )
    db.add(novel)
    db.commit()
    db.refresh(novel)
    db.add(
        NovelIngestJob(
            novel_id=novel.id,
            status="failed",
            stage="failed",
            source_bytes=64,
            error_code="ingest_internal_error",
            error="稿件导入失败，请稍后重试",
        )
    )
    db.commit()

    failed_snapshot = inspect_novel_ingest_job(db, novel_id=novel.id)
    assert failed_snapshot is not None
    assert is_novel_ingest_retry_allowed(failed_snapshot) is True

    assert reset_novel_ingest_job_for_retry(db, novel_id=novel.id) is True
    db.commit()
    claim = claim_novel_ingest_job(
        novel_id=novel.id,
        session_factory=TestingSessionLocal,
        worker_id="retry-race-worker",
        settings=_selfhost_llm_missing_settings(),
    )
    assert claim is not None
    running_snapshot = inspect_novel_ingest_job(db, novel_id=novel.id)
    assert running_snapshot is not None
    assert running_snapshot.status == "running"
    assert running_snapshot.lease_owner == "retry-race-worker"
    assert running_snapshot.lease_expires_at is not None

    assert reset_novel_ingest_job_for_retry(db, novel_id=novel.id) is False
    db.rollback()
    after_reset = inspect_novel_ingest_job(db, novel_id=novel.id)

    assert after_reset is not None
    assert after_reset.status == running_snapshot.status
    assert after_reset.stage == running_snapshot.stage
    assert after_reset.lease_owner == running_snapshot.lease_owner
    assert after_reset.lease_expires_at == running_snapshot.lease_expires_at


def test_retry_endpoint_returns_conflict_when_job_is_claimed_after_snapshot(
    client,
    db,
    tmp_path,
    user,
    monkeypatch,
):
    from app.api import novel_uploads as novel_uploads_api

    novel = Novel(
        title="T",
        author="A",
        language="zh",
        file_path=_write_source(tmp_path, "retry-endpoint-race.txt", "第一章\n正文"),
        owner_id=user.id,
    )
    db.add(novel)
    db.commit()
    db.refresh(novel)
    db.add(
        NovelIngestJob(
            novel_id=novel.id,
            status="failed",
            stage="failed",
            source_bytes=64,
            error_code="ingest_internal_error",
            error="稿件导入失败，请稍后重试",
        )
    )
    db.commit()

    original_inspect = novel_uploads_api.inspect_novel_ingest_job
    race_injected = False

    def inspect_then_claim(session, *, novel_id: int):
        nonlocal race_injected
        snapshot = original_inspect(session, novel_id=novel_id)
        if snapshot is not None and not race_injected:
            race_injected = True
            assert reset_novel_ingest_job_for_retry(session, novel_id=novel_id) is True
            session.commit()
            claim = claim_novel_ingest_job(
                novel_id=novel_id,
                session_factory=TestingSessionLocal,
                worker_id="endpoint-race-worker",
                settings=_selfhost_llm_missing_settings(),
            )
            assert claim is not None
        return snapshot

    monkeypatch.setattr(
        novel_uploads_api,
        "inspect_novel_ingest_job",
        inspect_then_claim,
    )

    response = client.post(f"/api/novels/{novel.id}/ingest/retry")

    assert race_injected is True
    assert response.status_code == 409
    assert response.json()["detail"] == {
        "code": "ingest_retry_not_allowed",
        "message": "Novel ingest retry is not allowed",
    }
    db.expire_all()
    job = db.query(NovelIngestJob).filter(NovelIngestJob.novel_id == novel.id).one()
    assert job.status == "running"
    assert job.lease_owner == "endpoint-race-worker"
    assert job.lease_expires_at is not None


def test_deferred_window_index_build_waits_until_ingest_queue_is_idle(db, tmp_path, user):
    deferred_file = _write_source(
        tmp_path,
        "deferred.txt",
        "第一章 开端\n这里是第一章内容。\n\n第二章 继续\n这里是第二章内容。\n",
    )
    deferred_novel = Novel(
        title="Deferred",
        author="A",
        language="zh",
        file_path=deferred_file,
        owner_id=user.id,
        total_chapters=2,
        window_index_status="missing",
        window_index_revision=1,
        window_index_built_revision=None,
    )
    db.add(deferred_novel)
    db.commit()
    db.refresh(deferred_novel)
    db.add_all(
        [
            Chapter(novel_id=deferred_novel.id, chapter_number=1, title="第一章", content="这里是第一章内容。"),
            Chapter(novel_id=deferred_novel.id, chapter_number=2, title="第二章", content="这里是第二章内容。"),
            NovelIngestJob(
                novel_id=deferred_novel.id,
                status="completed",
                stage="completed",
                source_bytes=2_500_000,
                source_chars=500_000,
                chapter_count=2,
                resolved_language="zh",
                auto_index_plan="deferred",
                bootstrap_plan="defer_until_index",
                readiness_mode="degraded_target",
            ),
        ]
    )

    queued_file = _write_source(tmp_path, "queued.txt", "第一章 阻塞\n内容\n")
    queued_novel = Novel(title="Queued", author="A", language="zh", file_path=queued_file, owner_id=user.id)
    db.add(queued_novel)
    db.commit()
    db.refresh(queued_novel)
    db.add(
        NovelIngestJob(
            novel_id=queued_novel.id,
            status="queued",
            stage="accepted",
            source_bytes=64,
        )
    )
    db.commit()

    settings = _selfhost_llm_ready_settings()

    assert enqueue_next_deferred_window_index_build(session_factory=TestingSessionLocal, settings=settings) is False
    assert db.query(DerivedAssetJob).filter(DerivedAssetJob.novel_id == deferred_novel.id).count() == 0

    blocking_job = db.query(NovelIngestJob).filter(NovelIngestJob.novel_id == queued_novel.id).first()
    assert blocking_job is not None
    blocking_job.status = "completed"
    blocking_job.stage = "completed"
    db.commit()

    assert enqueue_next_deferred_window_index_build(session_factory=TestingSessionLocal, settings=settings) is True

    job = db.query(DerivedAssetJob).filter(DerivedAssetJob.novel_id == deferred_novel.id).first()
    assert job is not None
    assert job.status == "queued"
    assert job.target_revision == 1
    assert db.query(BootstrapJob).filter(BootstrapJob.novel_id == deferred_novel.id).count() == 0

    assert run_next_window_index_rebuild_job(session_factory=TestingSessionLocal, settings=settings) is True

    db.refresh(deferred_novel)
    db.refresh(job)
    assert deferred_novel.window_index_status == "fresh"
    assert deferred_novel.window_index_built_revision == 1
    assert job.status == "completed"

    bootstrap_job = db.query(BootstrapJob).filter(BootstrapJob.novel_id == deferred_novel.id).first()
    assert bootstrap_job is not None
    assert bootstrap_job.mode == "initial"
    assert bootstrap_job.status == "pending"
    assert bootstrap_job.result["index_refresh_only"] is False
    assert bootstrap_job.result["_queued_user_id"] == user.id


def test_deferred_window_index_build_requeues_failed_job_row(db, tmp_path, user):
    deferred_file = _write_source(
        tmp_path,
        "deferred-failed.txt",
        "第一章 开端\n这里是第一章内容。\n\n第二章 继续\n这里是第二章内容。\n",
    )
    deferred_novel = Novel(
        title="DeferredFailed",
        author="A",
        language="zh",
        file_path=deferred_file,
        owner_id=user.id,
        total_chapters=2,
        window_index_status="failed",
        window_index_revision=1,
        window_index_built_revision=None,
    )
    db.add(deferred_novel)
    db.commit()
    db.refresh(deferred_novel)
    db.add_all(
        [
            Chapter(novel_id=deferred_novel.id, chapter_number=1, title="第一章", content="这里是第一章内容。"),
            Chapter(novel_id=deferred_novel.id, chapter_number=2, title="第二章", content="这里是第二章内容。"),
            NovelIngestJob(
                novel_id=deferred_novel.id,
                status="completed",
                stage="completed",
                source_bytes=2_500_000,
                source_chars=500_000,
                chapter_count=2,
                resolved_language="zh",
                auto_index_plan="deferred",
                bootstrap_plan="defer_until_index",
                readiness_mode="degraded_target",
            ),
            DerivedAssetJob(
                novel_id=deferred_novel.id,
                asset_kind=DERIVED_ASSET_KIND_WINDOW_INDEX,
                status="failed",
                target_revision=1,
                completed_revision=None,
                error="窗口索引重建失败，请稍后重试",
                result={},
            ),
        ]
    )
    db.commit()

    assert enqueue_next_deferred_window_index_build(session_factory=TestingSessionLocal) is True

    job = db.query(DerivedAssetJob).filter(DerivedAssetJob.novel_id == deferred_novel.id).first()
    assert job is not None
    assert job.status == "queued"
    assert job.target_revision == 1
    assert job.error is None

    assert run_next_window_index_rebuild_job(session_factory=TestingSessionLocal) is True

    db.refresh(deferred_novel)
    db.refresh(job)
    assert deferred_novel.window_index_status == "fresh"
    assert deferred_novel.window_index_built_revision == 1
    assert job.status == "completed"
