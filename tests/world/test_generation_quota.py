"""
Hosted quota regression tests for world generation:

POST /api/novels/{novel_id}/world/generate
"""

from unittest.mock import AsyncMock
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.database import Base, get_db
from app.core.llm_config import ResolvedLlmConfig
from app.models import Novel, TokenUsage, User, WorldGenerationRun


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
    return n


@pytest.fixture
def client(db, hosted_user):
    from app.api import world
    from app.core.auth import get_current_user_or_default

    test_app = FastAPI()
    test_app.include_router(world.router)

    def override_get_db():
        try:
            yield db
        finally:
            pass

    test_app.dependency_overrides[get_db] = override_get_db
    test_app.dependency_overrides[get_current_user_or_default] = lambda: hosted_user

    with TestClient(test_app) as c:
        yield c
    test_app.dependency_overrides.clear()


def test_generate_world_does_not_charge_quota_on_llm_unavailable_503(client, db, hosted_user, novel, monkeypatch):
    from app.core.world import generation_application as generation_app
    from app.core.ai_client import LLMUnavailableError

    before = hosted_user.generation_quota

    mock = AsyncMock(side_effect=LLMUnavailableError("boom"))
    monkeypatch.setattr(generation_app, "generate_world_drafts", mock)

    resp = client.post(f"/api/novels/{novel.id}/world/generate", json={"text": "这是一段足够长的世界观设定文本。"})
    assert resp.status_code == 503

    db.refresh(hosted_user)
    assert hosted_user.generation_quota == before


def test_generate_world_does_not_charge_quota_on_busy_semaphore_503(client, db, hosted_user, novel, monkeypatch):
    from app.core.world import generation_application as generation_app

    before = hosted_user.generation_quota

    async def _busy() -> None:
        raise HTTPException(status_code=503, detail="busy", headers={"Retry-After": "1"})

    monkeypatch.setattr(generation_app, "acquire_llm_slot", _busy)

    resp = client.post(f"/api/novels/{novel.id}/world/generate", json={"text": "这是一段足够长的世界观设定文本。"})
    assert resp.status_code == 503
    assert resp.headers["retry-after"] == "1"

    db.refresh(hosted_user)
    assert hosted_user.generation_quota == before


def test_generate_world_duplicate_click_fast_fails_before_generation(client, db, hosted_user, novel, monkeypatch):
    from app.core.world import generation_application as generation_app

    before = hosted_user.generation_quota
    db.add(
        WorldGenerationRun(
            user_id=hosted_user.id,
            novel_id=novel.id,
            claim_token="existing-owner",
            status="running",
        )
    )
    db.commit()

    monkeypatch.setattr(
        generation_app,
        "generate_world_drafts",
        AsyncMock(side_effect=AssertionError("duplicate world generation should not execute")),
    )

    resp = client.post(f"/api/novels/{novel.id}/world/generate", json={"text": "这是一段足够长的世界观设定文本。"})
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "world_generate_duplicate_request"

    db.refresh(hosted_user)
    assert hosted_user.generation_quota == before


def test_generate_world_duplicate_click_beats_quota_exhaustion(client, db, hosted_user, novel, monkeypatch):
    from app.core.world import generation_application as generation_app

    hosted_user.generation_quota = 0
    db.add(
        WorldGenerationRun(
            user_id=hosted_user.id,
            novel_id=novel.id,
            claim_token="existing-owner",
            status="running",
        )
    )
    db.commit()

    monkeypatch.setattr(
        generation_app,
        "generate_world_drafts",
        AsyncMock(side_effect=AssertionError("duplicate world generation should not execute")),
    )

    resp = client.post(f"/api/novels/{novel.id}/world/generate", json={"text": "这是一段足够长的世界观设定文本。"})
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "world_generate_duplicate_request"


def test_generate_world_does_not_reclaim_old_running_row_on_timeout(client, db, hosted_user, novel, monkeypatch):
    import app.config as config_mod
    from app.core.world import generation_application as generation_app

    before = hosted_user.generation_quota
    stale_started = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=10)
    db.add(
        WorldGenerationRun(
            user_id=hosted_user.id,
            novel_id=novel.id,
            claim_token="stale-owner",
            status="running",
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
            generation_app,
            "generate_world_drafts",
            AsyncMock(side_effect=AssertionError("timeout alone must not reclaim a live world-generation run")),
        )

        resp = client.post(f"/api/novels/{novel.id}/world/generate", json={"text": "这是一段足够长的世界观设定文本。"})
        assert resp.status_code == 409
        assert resp.json()["detail"]["code"] == "world_generate_duplicate_request"

        db.refresh(hosted_user)
        assert hosted_user.generation_quota == before
    finally:
        config_mod._settings_instance = prev


def test_generate_world_charges_quota_on_success(client, db, hosted_user, novel, monkeypatch):
    from app.core.world import generation_application as generation_app
    from app.schemas import WorldGenerateResponse

    before = hosted_user.generation_quota

    mock = AsyncMock(
        return_value=WorldGenerateResponse(
            entities_created=0,
            relationships_created=0,
            systems_created=0,
            warnings=[],
        )
    )
    monkeypatch.setattr(generation_app, "generate_world_drafts", mock)

    resp = client.post(f"/api/novels/{novel.id}/world/generate", json={"text": "这是一段足够长的世界观设定文本。"})
    assert resp.status_code == 200

    db.refresh(hosted_user)
    assert hosted_user.generation_quota == before - 1


def test_generate_world_settles_durable_reservation_on_success(client, db, hosted_user, novel, monkeypatch):
    """World generation charges through a durable reservation row, not a bare decrement."""
    from app.core.world import generation_application as generation_app
    from app.models import QuotaReservation
    from app.schemas import WorldGenerateResponse

    mock = AsyncMock(
        return_value=WorldGenerateResponse(
            entities_created=0,
            relationships_created=0,
            systems_created=0,
            warnings=[],
        )
    )
    monkeypatch.setattr(generation_app, "generate_world_drafts", mock)

    resp = client.post(f"/api/novels/{novel.id}/world/generate", json={"text": "这是一段足够长的世界观设定文本。"})
    assert resp.status_code == 200

    reservations = db.query(QuotaReservation).filter(QuotaReservation.user_id == hosted_user.id).all()
    assert len(reservations) == 1
    assert reservations[0].reserved_count == 1
    assert reservations[0].charged_count == 1
    assert reservations[0].released_at is not None


def test_generate_world_failure_refunds_and_releases_durable_reservation(client, db, hosted_user, novel, monkeypatch):
    """Failed generation refunds via the reservation row and leaves no open lease."""
    from app.core.world import generation_application as generation_app
    from app.models import QuotaReservation

    before = hosted_user.generation_quota
    monkeypatch.setattr(
        generation_app,
        "generate_world_drafts",
        AsyncMock(side_effect=RuntimeError("boom")),
    )

    resp = client.post(f"/api/novels/{novel.id}/world/generate", json={"text": "这是一段足够长的世界观设定文本。"})
    assert resp.status_code == 500

    db.refresh(hosted_user)
    assert hosted_user.generation_quota == before

    reservations = db.query(QuotaReservation).filter(QuotaReservation.user_id == hosted_user.id).all()
    assert len(reservations) == 1
    assert reservations[0].charged_count == 0
    assert reservations[0].released_at is not None


def test_generate_world_rejects_byok_when_ai_budget_hard_stop_is_reached(
    client,
    db,
    hosted_user,
    novel,
    monkeypatch,
):
    import app.config as config_mod
    from app.core.world import generation_application as generation_app
    from app.schemas import WorldGenerateResponse

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
                node_name="world_generate",
            )
        )
        db.commit()

        before = hosted_user.generation_quota
        mock = AsyncMock(
            return_value=WorldGenerateResponse(
                entities_created=0,
                relationships_created=0,
                systems_created=0,
                warnings=[],
            )
        )
        monkeypatch.setattr(generation_app, "generate_world_drafts", mock)

        resp = client.post(
            f"/api/novels/{novel.id}/world/generate",
            json={"text": "这是一段足够长的世界观设定文本。"},
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


@pytest.mark.asyncio
async def test_generate_world_records_setting_import_project_start_and_success_event(
    db,
    hosted_user,
    novel,
    monkeypatch,
):
    from app.core.world import generation_application as generation_app
    from app.schemas import WorldGenerateResponse

    recorded: list[dict] = []
    ensured: list[dict] = []

    async def _runner(**kwargs):
        del kwargs
        return WorldGenerateResponse(
            entities_created=2,
            relationships_created=1,
            systems_created=1,
            warnings=[],
        )

    async def _acquire() -> None:
        return None

    monkeypatch.setattr(
        generation_app,
        "ensure_project_start_event",
        lambda *args, **kwargs: ensured.append({"args": args, "kwargs": kwargs}) or True,
    )

    result = await generation_app.generate_world_from_text(
        novel.id,
        text="这是一段足够长的世界观设定文本。",
        db=db,
        current_user=hosted_user,
        llm_config=ResolvedLlmConfig(
            base_url="https://hosted.example/v1",
            api_key="hosted-key",
            model="hosted-model",
            billing_source_hint="hosted",
            source="hosted_settings",
        ),
        generate_world_drafts_fn=_runner,
        acquire_llm_slot_fn=_acquire,
        release_llm_slot_fn=lambda: None,
        record_event_fn=lambda db, user_id, event, novel_id=None, meta=None: recorded.append(
            {
                "db": db,
                "user_id": user_id,
                "event": event,
                "novel_id": novel_id,
                "meta": meta,
            }
        ),
    )

    assert result.entities_created == 2
    assert ensured == [
        {
            "args": (db,),
            "kwargs": {
                "user_id": hosted_user.id,
                "novel_id": novel.id,
                "start_mode": "setting_import",
                "meta": {"entry_action": "world_generate"},
            },
        }
    ]
    assert recorded == [
        {
            "db": db,
            "user_id": hosted_user.id,
            "event": "world_generate",
            "novel_id": novel.id,
            "meta": {
                "entities_created": 2,
                "relationships_created": 1,
                "systems_created": 1,
                "warnings_count": 0,
            },
        }
    ]
