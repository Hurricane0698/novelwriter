from unittest.mock import AsyncMock
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.core.continuation_runs import build_continuation_request_hash
from app.database import Base, get_db
from app.models import Chapter, Continuation, ContinuationRun, Novel, User
from app.schemas import ContinueRequest


engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _settings(**overrides) -> Settings:
    return Settings(
        openai_base_url="https://example.com/v1",
        openai_api_key="test-key",
        openai_model="test-model",
        _env_file=None,
        **overrides,
    )


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
    user = User(
        username="user",
        hashed_password="x",
        role="admin",
        is_active=True,
    )
    db.add(user)
    db.commit()
    return user


@pytest.fixture
def novel(db, user):
    n = Novel(
        title="测试小说",
        author="测试作者",
        file_path="/tmp/test.txt",
        total_chapters=1,
        owner_id=user.id,
    )
    db.add(n)
    db.commit()
    db.refresh(n)

    db.add(
        Chapter(
            novel_id=n.id,
            chapter_number=1,
            title="第一章",
            content="开篇。",
        )
    )
    db.commit()
    return n


@pytest.fixture
def client(db, user, monkeypatch):
    from app.api import novels, novel_support
    import app.api.novel_continuation_context as continuation_context
    import app.api.novel_continuation_runtime as continuation_api
    from app.core.auth import get_current_user_or_default
    from app.schemas import ContinueDebugSummary

    test_app = FastAPI()
    test_app.include_router(novels.router)

    def override_get_db():
        try:
            yield db
        finally:
            pass

    test_app.dependency_overrides[get_db] = override_get_db
    test_app.dependency_overrides[get_current_user_or_default] = lambda: user

    # Keep generation deterministic while exercising the real run store.
    ctx = continuation_context._ContinuationContext(
        recent_text="recent",
        chapter_recaps="",
        world_context="",
        narrative_constraints="",
        debug_summary=ContinueDebugSummary(context_chapters=1),
        writer_ctx={},
        effective_context_chapters=1,
    )

    def fake_prepare(db_sess, novel_id, req, current_user):
        novel_support.get_novel(db_sess, novel_id)
        return ctx

    monkeypatch.setattr(continuation_api, "_prepare_continuation_context", fake_prepare)
    monkeypatch.setattr(continuation_api, "postcheck_continuation", lambda **kwargs: [])

    # Avoid network calls: stub out generator and just persist dummy continuations.
    async def fake_continue_novel(*, db, novel_id, num_versions, **kwargs):
        from app.models import Continuation

        out = []
        for _ in range(int(num_versions or 1)):
            c = Continuation(
                novel_id=novel_id,
                chapter_number=2,
                content="续写内容",
                prompt_used="p",
            )
            db.add(c)
            db.commit()
            db.refresh(c)
            out.append(c)
        return out

    monkeypatch.setattr(continuation_api, "continue_novel", fake_continue_novel)

    with TestClient(test_app) as c:
        yield c
    test_app.dependency_overrides.clear()


def _continue_request_hash(payload: dict[str, object]) -> str:
    return build_continuation_request_hash(
        ContinueRequest.model_validate(payload).model_dump(mode="json", exclude_none=False)
    )


def test_continue_returns_busy_semaphore_503(client, db, user, novel, monkeypatch):
    import app.api.novel_continuation_runtime as continuation_api

    async def _busy() -> None:
        raise HTTPException(status_code=503, detail="busy", headers={"Retry-After": "1"})

    monkeypatch.setattr(continuation_api, "acquire_llm_slot", _busy)

    resp = client.post(
        f"/api/novels/{novel.id}/continue",
        json={"num_versions": 1, "context_chapters": 1},
    )
    assert resp.status_code == 503


def test_continue_fallback_reuses_completed_request_without_second_generation(client, db, user, novel, monkeypatch):
    import app.api.novel_continuation_runtime as continuation_api

    payload = {"num_versions": 1, "context_chapters": 1}
    request_id = "continue-req-completed"
    continuation = Continuation(
        novel_id=novel.id,
        chapter_number=2,
        content="已完成续写",
        prompt_used="p",
    )
    db.add(continuation)
    db.commit()
    db.refresh(continuation)

    db.commit()

    db.add(
        ContinuationRun(
            user_id=user.id,
            novel_id=novel.id,
            client_request_id=request_id,
            request_hash=_continue_request_hash(payload),
            claim_token="original-owner",
            status="completed",
            delivered_count=1,
            continuation_ids=[continuation.id],
            debug_summary={
                "context_chapters": 1,
                "injected_systems": [],
                "injected_entities": [],
                "injected_relationships": [],
                "relevant_entity_ids": [],
                "ambiguous_keywords_disabled": [],
                "drift_warnings": [],
                "prose_warnings": [],
            },
        )
    )
    db.commit()

    monkeypatch.setattr(
        continuation_api,
        "continue_novel",
        AsyncMock(side_effect=AssertionError("completed request should be replayed, not regenerated")),
    )

    resp = client.post(
        f"/api/novels/{novel.id}/continue",
        json=payload,
        headers={
            "X-Novwr-Continuation-Request-ID": request_id,
            "X-Novwr-Delivery-Mode": "stream-fallback",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["continuations"][0]["id"] == continuation.id

    assert db.query(Continuation).count() == 1


def test_continue_fallback_returns_conflict_while_original_request_is_still_running(client, db, user, novel, monkeypatch):
    import app.api.novel_continuation_runtime as continuation_api

    payload = {"num_versions": 1, "context_chapters": 1}
    request_id = "continue-req-running"
    monkeypatch.setattr(continuation_api, "_CONTINUATION_RUN_WAIT_TIMEOUT_SECONDS", 0.01)
    db.commit()

    db.add(
        ContinuationRun(
            user_id=user.id,
            novel_id=novel.id,
            client_request_id=request_id,
            request_hash=_continue_request_hash(payload),
            claim_token="stream-owner",
            status="running",
            delivered_count=0,
            continuation_ids=[],
        )
    )
    db.commit()

    monkeypatch.setattr(
        continuation_api,
        "continue_novel",
        AsyncMock(side_effect=AssertionError("running request should not start a second sync generation")),
    )

    resp = client.post(
        f"/api/novels/{novel.id}/continue",
        json=payload,
        headers={
            "X-Novwr-Continuation-Request-ID": request_id,
            "X-Novwr-Delivery-Mode": "stream-fallback",
        },
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "continuation_request_still_running"


def test_continue_duplicate_click_without_request_id_fast_fails(client, db, user, novel, monkeypatch):
    import app.api.novel_continuation_runtime as continuation_api

    payload = {"num_versions": 1, "context_chapters": 1}
    db.add(
        ContinuationRun(
            user_id=user.id,
            novel_id=novel.id,
            client_request_id="existing-implicit-run",
            request_hash=_continue_request_hash(payload),
            semantic_key="continue",
            claim_token="existing-owner",
            status="running",
            delivered_count=0,
            continuation_ids=[],
        )
    )
    db.commit()

    monkeypatch.setattr(
        continuation_api,
        "continue_novel",
        AsyncMock(side_effect=AssertionError("duplicate continuation click should not start generation")),
    )

    resp = client.post(
        f"/api/novels/{novel.id}/continue",
        json=payload,
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "continuation_duplicate_request"


def test_continue_does_not_reclaim_old_running_semantic_run_on_timeout(client, db, user, novel, monkeypatch):
    import app.config as config_mod
    import app.api.novel_continuation_runtime as continuation_api
    payload = {"num_versions": 1, "context_chapters": 1}
    stale_started = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=10)
    db.add(
        ContinuationRun(
            user_id=user.id,
            novel_id=novel.id,
            client_request_id="stale-continuation-run",
            request_hash=_continue_request_hash(payload),
            semantic_key="continue",
            claim_token="stale-owner",
            status="running",
            delivered_count=0,
            continuation_ids=[],
            created_at=stale_started,
            updated_at=stale_started,
        )
    )
    db.commit()

    prev = config_mod._settings_instance
    config_mod._settings_instance = _settings(
        generation_run_stale_timeout_seconds=1,
    )
    try:
        monkeypatch.setattr(
            continuation_api,
            "continue_novel",
            AsyncMock(side_effect=AssertionError("timeout alone must not reclaim a live continuation run")),
        )
        resp = client.post(f"/api/novels/{novel.id}/continue", json=payload)
        assert resp.status_code == 409
        assert resp.json()["detail"]["code"] == "continuation_duplicate_request"
    finally:
        config_mod._settings_instance = prev


def test_continue_fallback_can_take_over_failed_request_with_no_delivered_output(client, db, user, novel, monkeypatch):
    import app.api.novel_continuation_runtime as continuation_api

    payload = {"num_versions": 1, "context_chapters": 1}
    request_id = "continue-req-takeover"

    db.add(
        ContinuationRun(
            user_id=user.id,
            novel_id=novel.id,
            client_request_id=request_id,
            request_hash=_continue_request_hash(payload),
            claim_token="stale-owner",
            status="failed",
            delivered_count=0,
            continuation_ids=[],
            error_code="continuation_stream_cancelled",
            error_message="previous stream died early",
        )
    )
    db.commit()

    async def fake_continue_novel(*, db, novel_id, num_versions, **kwargs):
        out = []
        for _ in range(int(num_versions or 1)):
            continuation = Continuation(
                novel_id=novel_id,
                chapter_number=2,
                content="接管后续写",
                prompt_used="p",
            )
            db.add(continuation)
            db.commit()
            db.refresh(continuation)
            out.append(continuation)
        return out

    monkeypatch.setattr(continuation_api, "continue_novel", fake_continue_novel)

    resp = client.post(
        f"/api/novels/{novel.id}/continue",
        json=payload,
        headers={
            "X-Novwr-Continuation-Request-ID": request_id,
            "X-Novwr-Delivery-Mode": "stream-fallback",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["continuations"][0]["content"] == "接管后续写"

    run = db.query(ContinuationRun).filter(ContinuationRun.client_request_id == request_id).one()
    assert run.status == "completed"
    assert run.delivered_count == 1
    assert len(run.continuation_ids or []) == 1


def test_continue_fallback_failed_request_id_respects_active_semantic_run(client, db, user, novel, monkeypatch):
    import app.api.novel_continuation_runtime as continuation_api

    payload = {"num_versions": 1, "context_chapters": 1}
    request_id = "continue-req-failed-retry"

    db.add(
        ContinuationRun(
            user_id=user.id,
            novel_id=novel.id,
            client_request_id=request_id,
            request_hash=_continue_request_hash(payload),
            claim_token="failed-owner",
            status="failed",
            delivered_count=0,
            continuation_ids=[],
            error_code="continuation_stream_cancelled",
            error_message="previous stream died early",
        )
    )
    db.add(
        ContinuationRun(
            user_id=user.id,
            novel_id=novel.id,
            client_request_id="active-semantic-owner",
            request_hash=_continue_request_hash(payload),
            semantic_key="continue",
            claim_token="active-owner",
            status="running",
            delivered_count=0,
            continuation_ids=[],
        )
    )
    db.commit()

    monkeypatch.setattr(
        continuation_api,
        "continue_novel",
        AsyncMock(side_effect=AssertionError("failed request retry must not bypass an active semantic run")),
    )

    resp = client.post(
        f"/api/novels/{novel.id}/continue",
        json=payload,
        headers={
            "X-Novwr-Continuation-Request-ID": request_id,
            "X-Novwr-Delivery-Mode": "stream-fallback",
        },
    )

    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "continuation_duplicate_request"
