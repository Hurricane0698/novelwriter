"""
Hosted quota regression tests for non-stream continue:

POST /api/novels/{novel_id}/continue
"""

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
from app.models import Chapter, Continuation, ContinuationRun, Novel, QuotaReservation, TokenUsage, User
from app.schemas import ContinueRequest


engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _hosted_settings(**overrides) -> Settings:
    return Settings(
        deploy_mode="hosted",
        hosted_llm_base_url="https://hosted.example/v1",
        hosted_llm_api_key="hosted-key",
        hosted_llm_model="hosted-model",
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


@pytest.fixture(scope="function")
def hosted_settings(_force_selfhost_settings):  # ensure conftest runs first
    import app.config as config_mod
    prev = config_mod._settings_instance
    config_mod._settings_instance = _hosted_settings()
    try:
        yield
    finally:
        config_mod._settings_instance = prev


@pytest.fixture
def hosted_user(db, hosted_settings):
    user = User(
        username="hosted_user",
        hashed_password="x",
        role="admin",
        is_active=True,
        generation_quota=2,
        feedback_submitted=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def novel(db, hosted_user):
    n = Novel(
        title="测试小说",
        author="测试作者",
        file_path="/tmp/test.txt",
        total_chapters=1,
        owner_id=hosted_user.id,
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
def client(db, hosted_user, monkeypatch):
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
    test_app.dependency_overrides[get_current_user_or_default] = lambda: hosted_user

    # Avoid pulling in the full context assembly stack; quota behavior is the target.
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
        n = db_sess.query(Novel).filter(Novel.id == novel_id).first()
        novel_support.verify_novel_access(n, current_user)
        return ctx

    monkeypatch.setattr(continuation_api, "_prepare_continuation_context", fake_prepare)
    monkeypatch.setattr(continuation_api, "postcheck_continuation", lambda **kwargs: [])
    monkeypatch.setattr(continuation_api, "record_event", lambda *args, **kwargs: None)

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


def test_continue_charges_quota_on_success(client, db, hosted_user, novel):
    before = hosted_user.generation_quota

    resp = client.post(
        f"/api/novels/{novel.id}/continue",
        json={"num_versions": 1, "context_chapters": 1},
    )
    assert resp.status_code == 200

    db.refresh(hosted_user)
    assert hosted_user.generation_quota == before - 1


def test_continue_does_not_charge_quota_on_busy_semaphore_503(client, db, hosted_user, novel, monkeypatch):
    import app.api.novel_continuation_runtime as continuation_api

    before = hosted_user.generation_quota

    async def _busy() -> None:
        raise HTTPException(status_code=503, detail="busy", headers={"Retry-After": "1"})

    monkeypatch.setattr(continuation_api, "acquire_llm_slot", _busy)

    resp = client.post(
        f"/api/novels/{novel.id}/continue",
        json={"num_versions": 1, "context_chapters": 1},
    )
    assert resp.status_code == 503

    db.refresh(hosted_user)
    assert hosted_user.generation_quota == before


def test_continue_rejects_when_ai_budget_hard_stop_is_reached(client, db, hosted_user, novel, monkeypatch):
    import app.config as config_mod
    prev = config_mod._settings_instance
    config_mod._settings_instance = _hosted_settings(ai_hard_stop_usd=1.0)
    try:
        db.add(
            TokenUsage(
                user_id=hosted_user.id,
                model="gemini-3.0-flash",
                prompt_tokens=10,
                completion_tokens=10,
                total_tokens=20,
                cost_estimate=1.0,
                billing_source="hosted",
                node_name="writer",
            )
        )
        db.commit()

        before = hosted_user.generation_quota
        resp = client.post(
            f"/api/novels/{novel.id}/continue",
            json={"num_versions": 1, "context_chapters": 1},
        )
        assert resp.status_code == 503
        assert resp.json()["detail"]["code"] == "ai_budget_hard_stop"

        db.refresh(hosted_user)
        assert hosted_user.generation_quota == before
    finally:
        config_mod._settings_instance = prev


def test_continue_rejects_byok_when_ai_budget_hard_stop_is_reached(
    client,
    db,
    hosted_user,
    novel,
    monkeypatch,
):
    import app.config as config_mod
    prev = config_mod._settings_instance
    config_mod._settings_instance = _hosted_settings(ai_hard_stop_usd=1.0)
    try:
        db.add(
            TokenUsage(
                user_id=hosted_user.id,
                model="gemini-3.0-flash",
                prompt_tokens=10,
                completion_tokens=10,
                total_tokens=20,
                cost_estimate=1.0,
                billing_source="hosted",
                node_name="writer",
            )
        )
        db.commit()

        before = hosted_user.generation_quota
        resp = client.post(
            f"/api/novels/{novel.id}/continue",
            json={"num_versions": 1, "context_chapters": 1},
            headers={
                "x-llm-base-url": "https://example.com/v1",
                "x-llm-api-key": "byok-key",
                "x-llm-model": "byok-model",
            },
        )
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "hosted_byok_disabled"

        db.refresh(hosted_user)
        assert hosted_user.generation_quota == before
    finally:
        config_mod._settings_instance = prev


def test_continue_refunds_quota_on_generation_failure(client, db, hosted_user, novel, monkeypatch):
    import app.api.novel_continuation_runtime as continuation_api

    before = hosted_user.generation_quota

    mock = AsyncMock(side_effect=RuntimeError("boom"))
    monkeypatch.setattr(continuation_api, "continue_novel", mock)

    resp = client.post(
        f"/api/novels/{novel.id}/continue",
        json={"num_versions": 1, "context_chapters": 1},
    )
    assert resp.status_code == 500

    db.refresh(hosted_user)
    assert hosted_user.generation_quota == before


def test_continue_stream_releases_llm_slot_on_non_http_quota_failure(client, novel, monkeypatch):
    import app.api.novel_continuation_runtime as continuation_api

    releases: list[str] = []

    class BrokenQuotaScope:
        charged = 0

        def __init__(self, *args, **kwargs):
            pass

        def reserve(self) -> None:
            raise RuntimeError("boom")

        def finalize(self) -> None:
            raise AssertionError("finalize should not run when reserve fails")

    async def _acquire() -> None:
        return None

    def _release() -> None:
        releases.append("released")

    monkeypatch.setattr(continuation_api, "QuotaScope", BrokenQuotaScope)
    monkeypatch.setattr(continuation_api, "acquire_llm_slot", _acquire)
    monkeypatch.setattr(continuation_api, "release_llm_slot", _release)

    with pytest.raises(RuntimeError, match="boom"):
        client.post(
            f"/api/novels/{novel.id}/continue/stream",
            json={"num_versions": 1, "context_chapters": 1},
        )

    assert releases == ["released"]


def test_continue_stream_reclaims_abandoned_reservation_before_quota_check(client, db, hosted_user, novel, monkeypatch):
    import app.api.novel_continuation_runtime as continuation_api

    hosted_user.generation_quota = 0
    db.commit()
    db.refresh(hosted_user)

    stale = QuotaReservation(
        user_id=hosted_user.id,
        reserved_count=2,
        charged_count=1,
        lease_token="stale-owner-token",
    )
    db.add(stale)
    db.commit()
    db.refresh(stale)

    async def fake_continue_novel_stream(**kwargs):
        yield {"type": "start", "variant": 0, "total_variants": 1}
        yield {"type": "variant_done", "variant": 0, "continuation_id": 101, "content": "续写内容"}
        yield {"type": "done", "continuation_ids": [101]}

    monkeypatch.setattr(continuation_api, "continue_novel_stream", fake_continue_novel_stream)

    resp = client.post(
        f"/api/novels/{novel.id}/continue/stream",
        json={"num_versions": 1, "context_chapters": 1},
    )
    assert resp.status_code == 200

    latest = db.query(QuotaReservation).order_by(QuotaReservation.id.desc()).first()
    db.refresh(hosted_user)
    db.refresh(stale)

    assert stale.released_at is not None
    assert latest is not None
    assert latest.lease_token != stale.lease_token
    assert latest.charged_count == 1
    assert hosted_user.generation_quota == 0


def test_continue_fallback_reuses_completed_request_without_second_generation(client, db, hosted_user, novel, monkeypatch):
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

    hosted_user.generation_quota = 0
    db.commit()

    db.add(
        ContinuationRun(
            user_id=hosted_user.id,
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

    before_reservations = db.query(QuotaReservation).count()
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

    db.refresh(hosted_user)
    assert hosted_user.generation_quota == 0
    assert db.query(QuotaReservation).count() == before_reservations
    assert db.query(Continuation).count() == 1


def test_continue_fallback_returns_conflict_while_original_request_is_still_running(client, db, hosted_user, novel, monkeypatch):
    import app.api.novel_continuation_runtime as continuation_api

    payload = {"num_versions": 1, "context_chapters": 1}
    request_id = "continue-req-running"
    monkeypatch.setattr(continuation_api, "_CONTINUATION_RUN_WAIT_TIMEOUT_SECONDS", 0.01)
    hosted_user.generation_quota = 0
    db.commit()

    db.add(
        ContinuationRun(
            user_id=hosted_user.id,
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

    before_reservations = db.query(QuotaReservation).count()
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

    db.refresh(hosted_user)
    assert hosted_user.generation_quota == 0
    assert db.query(QuotaReservation).count() == before_reservations


def test_continue_duplicate_click_without_request_id_fast_fails(client, db, hosted_user, novel, monkeypatch):
    import app.api.novel_continuation_runtime as continuation_api

    payload = {"num_versions": 1, "context_chapters": 1}
    db.add(
        ContinuationRun(
            user_id=hosted_user.id,
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

    before_reservations = db.query(QuotaReservation).count()
    resp = client.post(
        f"/api/novels/{novel.id}/continue",
        json=payload,
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "continuation_duplicate_request"

    db.refresh(hosted_user)
    assert hosted_user.generation_quota == 2
    assert db.query(QuotaReservation).count() == before_reservations


def test_continue_does_not_reclaim_old_running_semantic_run_on_timeout(client, db, hosted_user, novel, monkeypatch):
    import app.config as config_mod
    import app.api.novel_continuation_runtime as continuation_api
    payload = {"num_versions": 1, "context_chapters": 1}
    stale_started = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=10)
    db.add(
        ContinuationRun(
            user_id=hosted_user.id,
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
    config_mod._settings_instance = _hosted_settings(
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
        db.refresh(hosted_user)
        assert hosted_user.generation_quota == 2
    finally:
        config_mod._settings_instance = prev


def test_continue_fallback_can_take_over_failed_request_with_no_delivered_output(client, db, hosted_user, novel, monkeypatch):
    import app.api.novel_continuation_runtime as continuation_api

    payload = {"num_versions": 1, "context_chapters": 1}
    request_id = "continue-req-takeover"

    db.add(
        ContinuationRun(
            user_id=hosted_user.id,
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
    db.refresh(hosted_user)
    assert run.status == "completed"
    assert run.delivered_count == 1
    assert len(run.continuation_ids or []) == 1
    assert hosted_user.generation_quota == 1
    reservation = db.query(QuotaReservation).one()
    assert reservation.charged_count == 1
    assert reservation.released_at is not None


def test_continue_fallback_failed_request_id_respects_active_semantic_run(client, db, hosted_user, novel, monkeypatch):
    import app.api.novel_continuation_runtime as continuation_api

    payload = {"num_versions": 1, "context_chapters": 1}
    request_id = "continue-req-failed-retry"

    db.add(
        ContinuationRun(
            user_id=hosted_user.id,
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
            user_id=hosted_user.id,
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
