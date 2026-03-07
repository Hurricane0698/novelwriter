import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.core.bootstrap import transition_bootstrap_job
from app.database import Base
from app.models import BootstrapJob, Chapter, Novel, User
from app.schemas import (
    BootstrapDraftPolicy,
    BootstrapJobResponse,
    BootstrapMode,
    BootstrapTriggerRequest,
)


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
def world_api(monkeypatch):
    from app.api import world

    async def _noop_bootstrap_job(*args, **kwargs):
        return None

    def _drop_background_task(coro):
        coro.close()

        class _DoneTask:
            def done(self):
                return True

        return _DoneTask()

    monkeypatch.setattr(world, "run_bootstrap_job", _noop_bootstrap_job)
    monkeypatch.setattr(world.asyncio, "create_task", _drop_background_task)
    return world


@pytest.fixture
def user():
    return User(id=1, username="tester", hashed_password="x", role="admin", is_active=True)


@pytest.fixture
def novel(db):
    item = Novel(title="测试小说", author="作者", file_path="/tmp/test.txt", total_chapters=1)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@pytest.fixture
def novel_with_text(db):
    item = Novel(title="测试小说", author="作者", file_path="/tmp/test.txt", total_chapters=1)
    db.add(item)
    db.commit()
    db.refresh(item)

    chapter = Chapter(novel_id=item.id, chapter_number=1, title="第一章", content="云澈看向远方。")
    db.add(chapter)
    db.commit()
    return item


def test_window_bootstrap_config_defaults():
    model_fields = Settings.model_fields

    assert model_fields["bootstrap_window_size"].default == 500
    assert model_fields["bootstrap_window_step"].default == 250
    assert model_fields["bootstrap_min_window_count"].default == 3
    assert model_fields["bootstrap_min_window_ratio"].default == 0.005
    assert model_fields["bootstrap_llm_temperature"].default == 0.3
    assert model_fields["bootstrap_max_candidates"].default == 500
    assert model_fields["bootstrap_common_words_dir"].default == "data/common_words"
    assert model_fields["bootstrap_stale_job_timeout_seconds"].default == 900


def test_bootstrap_job_status_transitions():
    job = BootstrapJob(
        novel_id=1,
        status="pending",
        progress={"step": 0, "detail": "queued"},
        result={},
    )

    for status in ("tokenizing", "extracting", "windowing", "refining", "completed"):
        transition_bootstrap_job(job, status, detail=f"{status} phase")

    assert job.status == "completed"
    assert job.progress == {"step": 5, "detail": "completed phase"}
    assert job.result == {"entities_found": 0, "relationships_found": 0, "index_refresh_only": False}
    assert job.error is None


def test_bootstrap_job_rejects_invalid_transition():
    job = BootstrapJob(novel_id=1, status="pending", progress={"step": 0, "detail": "queued"}, result={})

    with pytest.raises(ValueError, match="Invalid bootstrap transition"):
        transition_bootstrap_job(job, "completed")


def test_bootstrap_endpoint_request_contract():
    request = BootstrapTriggerRequest.model_validate({})
    assert request.mode == BootstrapMode.INDEX_REFRESH
    assert request.draft_policy is None
    assert request.force is False

    custom_request = BootstrapTriggerRequest.model_validate(
        {
            "mode": "reextract",
            "draft_policy": "merge",
            "force": True,
        }
    )
    assert custom_request.mode == BootstrapMode.REEXTRACT
    assert custom_request.draft_policy == BootstrapDraftPolicy.MERGE
    assert custom_request.force is True

    with pytest.raises(ValidationError):
        BootstrapTriggerRequest.model_validate({"unexpected": True})


def test_bootstrap_serializer_handles_legacy_missing_mode_and_result(world_api):
    now = datetime.now(timezone.utc)
    legacy_job = BootstrapJob(
        id=99,
        novel_id=1,
        status="completed",
        progress=None,
        result=None,
        created_at=now,
        updated_at=now,
    )
    legacy_job.mode = None

    response = world_api._serialize_bootstrap_job(legacy_job)
    assert response.mode == "index_refresh"
    assert response.initialized is True
    assert response.progress.step == 0
    assert response.result.entities_found == 0
    assert response.result.relationships_found == 0
    assert response.result.index_refresh_only is False


@pytest.mark.asyncio
async def test_bootstrap_endpoint_response_contract(world_api, db, novel_with_text, user):
    route_map = {route.path: route for route in world_api.router.routes}
    post_route = route_map["/api/novels/{novel_id}/world/bootstrap"]
    get_route = route_map["/api/novels/{novel_id}/world/bootstrap/status"]

    assert post_route.status_code == 202
    assert post_route.response_model is BootstrapJobResponse
    assert get_route.response_model is BootstrapJobResponse

    trigger = await world_api.trigger_bootstrap(
        novel_id=novel_with_text.id,
        body=BootstrapTriggerRequest(),
        db=db,
        current_user=user,
    )
    assert isinstance(trigger, BootstrapJobResponse)
    assert trigger.novel_id == novel_with_text.id
    assert trigger.status == "pending"
    assert trigger.mode == "initial"
    assert trigger.initialized is False
    assert trigger.result.index_refresh_only is False

    status = world_api.get_bootstrap_status(
        novel_id=novel_with_text.id,
        db=db,
        current_user=user,
    )
    assert isinstance(status, BootstrapJobResponse)
    assert status.job_id == trigger.job_id
    assert status.progress.step == 0
    assert status.progress.detail == "queued"
    assert status.mode == "initial"
    assert status.initialized is False
    assert status.result.index_refresh_only is False


@pytest.mark.asyncio
async def test_bootstrap_omitted_mode_resolves_to_index_refresh_after_initialization(world_api, db, novel_with_text, user):
    db.add(
        BootstrapJob(
            novel_id=novel_with_text.id,
            mode="initial",
            initialized=True,
            status="completed",
            progress={"step": 5, "detail": "completed"},
            result={"entities_found": 2, "relationships_found": 1, "index_refresh_only": False},
        )
    )
    db.commit()

    trigger = await world_api.trigger_bootstrap(
        novel_id=novel_with_text.id,
        body=BootstrapTriggerRequest(),
        db=db,
        current_user=user,
    )

    assert trigger.mode == "index_refresh"
    assert trigger.initialized is True
    assert trigger.result.index_refresh_only is True


@pytest.mark.asyncio
async def test_bootstrap_rejects_initial_mode_after_initialization(world_api, db, novel_with_text, user):
    initialized_job = BootstrapJob(
        novel_id=novel_with_text.id,
        mode="initial",
        initialized=True,
        status="completed",
        progress={"step": 5, "detail": "completed"},
        result={"entities_found": 2, "relationships_found": 1, "index_refresh_only": False},
    )
    db.add(initialized_job)
    db.commit()

    with pytest.raises(HTTPException) as exc_info:
        await world_api.trigger_bootstrap(
            novel_id=novel_with_text.id,
            body=BootstrapTriggerRequest(mode="initial"),
            db=db,
            current_user=user,
    )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "bootstrap_initial_mode_not_allowed"


@pytest.mark.asyncio
async def test_bootstrap_requires_force_for_reextract_replace_policy(world_api, db, novel_with_text, user):
    with pytest.raises(HTTPException) as exc_info:
        await world_api.trigger_bootstrap(
            novel_id=novel_with_text.id,
            body=BootstrapTriggerRequest(mode="reextract"),
            db=db,
            current_user=user,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "bootstrap_force_required"


@pytest.mark.asyncio
async def test_bootstrap_reextract_merge_without_force(world_api, db, novel_with_text, user):
    response = await world_api.trigger_bootstrap(
        novel_id=novel_with_text.id,
        body=BootstrapTriggerRequest(mode="reextract", draft_policy="merge"),
        db=db,
        current_user=user,
    )

    assert response.mode == "reextract"
    assert response.result.index_refresh_only is False


@pytest.mark.asyncio
async def test_bootstrap_rejects_draft_policy_for_non_reextract_mode(world_api, db, novel_with_text, user):
    with pytest.raises(HTTPException) as exc_info:
        await world_api.trigger_bootstrap(
            novel_id=novel_with_text.id,
            body=BootstrapTriggerRequest(mode="index_refresh", draft_policy="merge"),
            db=db,
            current_user=user,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "bootstrap_draft_policy_not_allowed"


@pytest.mark.asyncio
async def test_bootstrap_rejects_running_job(world_api, db, novel_with_text, user):
    running_job = BootstrapJob(
        novel_id=novel_with_text.id,
        status="windowing",
        progress={"step": 4, "detail": "windowing"},
        result={"entities_found": 0, "relationships_found": 0},
    )
    db.add(running_job)
    db.commit()

    with pytest.raises(HTTPException) as exc_info:
        await world_api.trigger_bootstrap(
            novel_id=novel_with_text.id,
            body=BootstrapTriggerRequest(),
            db=db,
            current_user=user,
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "bootstrap_already_running"


@pytest.mark.asyncio
async def test_bootstrap_allows_retry_for_stale_running_job(world_api, db, novel_with_text, user, monkeypatch):
    monkeypatch.setattr(world_api, "get_settings", lambda: Settings(bootstrap_stale_job_timeout_seconds=1))
    stale_time = datetime.now(timezone.utc) - timedelta(minutes=1)
    running_job = BootstrapJob(
        novel_id=novel_with_text.id,
        status="windowing",
        progress={"step": 4, "detail": "windowing"},
        result={"entities_found": 0, "relationships_found": 0},
        created_at=stale_time,
        updated_at=stale_time,
    )
    db.add(running_job)
    db.commit()

    response = await world_api.trigger_bootstrap(
        novel_id=novel_with_text.id,
        body=BootstrapTriggerRequest(),
        db=db,
        current_user=user,
    )

    db.refresh(running_job)
    assert response.job_id == running_job.id
    assert response.status == "pending"
    assert running_job.status == "pending"


@pytest.mark.asyncio
async def test_bootstrap_concurrent_trigger_is_serialized(world_api, db, novel_with_text, user):
    async def _trigger():
        return await world_api.trigger_bootstrap(
            novel_id=novel_with_text.id,
            body=BootstrapTriggerRequest(),
            db=db,
            current_user=user,
        )

    first, second = await asyncio.gather(_trigger(), _trigger(), return_exceptions=True)

    success_count = sum(not isinstance(item, Exception) for item in (first, second))
    errors = [item for item in (first, second) if isinstance(item, Exception)]

    assert success_count == 1
    assert len(errors) == 1
    assert isinstance(errors[0], HTTPException)
    assert errors[0].status_code == 409


@pytest.mark.asyncio
async def test_bootstrap_rejects_empty_text_novel(world_api, db, novel, user):
    with pytest.raises(HTTPException) as exc_info:
        await world_api.trigger_bootstrap(
            novel_id=novel.id,
            body=BootstrapTriggerRequest(),
            db=db,
            current_user=user,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "bootstrap_no_text"
