import asyncio
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.core.bootstrap import build_bootstrap_trigger_result, run_bootstrap_job
from app.core.llm_config import LlmConfigError, LlmConfigValues, ResolvedLlmConfig
from app.database import Base, get_db
from app.models import (
    BootstrapJob,
    Chapter,
    Novel,
    User,
    WorldEntity,
    WorldRelationship,
)


engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

_SELFHOST_LLM_CONFIG = ResolvedLlmConfig(
    base_url="https://example.com/v1",
    api_key="test-key",
    model="test-model",
    billing_source_hint="selfhost",
    source="selfhost_request",
)
_DESKTOP_LLM_CONFIG = ResolvedLlmConfig(
    base_url="https://desktop.example/v1",
    api_key="desktop-key",
    model="desktop-model",
    billing_source_hint="selfhost",
    source="desktop_store",
)


class _FakeAIClient:
    def __init__(self, payload: dict):
        self._payload = payload
        self.calls = 0

    async def generate_structured(self, **kwargs):
        self.calls += 1
        response_model = kwargs["response_model"]
        return response_model.model_validate(self._payload)


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
def client(db, monkeypatch):
    from app.api import world
    import app.config as config_mod
    from app.core.world import bootstrap_application as bootstrap_app

    captured: dict[str, object] = {}

    def _capture_bootstrap_launch(
        *,
        db,
        job_id: int,
        llm_config: ResolvedLlmConfig | None,
        user_id: int | None = None,
    ):
        # Hosted usage isolation depends on attributing bootstrap LLM calls to the trigger user.
        _ = db
        captured["job_id"] = job_id
        captured["user_id"] = user_id
        captured["llm_config"] = llm_config
        assert captured.get("user_id") == 1

    test_app = FastAPI()
    test_app.include_router(world.router)
    test_app.state._bootstrap_task_capture = captured

    monkeypatch.setattr(
        bootstrap_app, "launch_bootstrap_job", _capture_bootstrap_launch
    )
    monkeypatch.setattr(
        config_mod,
        "_settings_instance",
        Settings(
            deploy_mode="selfhost",
            openai_base_url="https://settings.example/v1",
            openai_api_key="settings-key",
            openai_model="settings-model",
            _env_file=None,
        ),
    )

    def override_get_db():
        try:
            yield db
        finally:
            pass

    user = User(
        id=1,
        username="tester",
        hashed_password="x",
        role="admin",
        is_active=True,
        generation_quota=5,
        feedback_submitted=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    test_app.dependency_overrides[get_db] = override_get_db
    test_app.dependency_overrides[world.get_current_user_or_default] = lambda: user

    with TestClient(test_app) as c:
        yield c
    test_app.dependency_overrides.clear()


def _create_novel_with_text(db) -> Novel:
    novel = Novel(
        title="Integration Bootstrap",
        author="Tester",
        file_path="/tmp/test.txt",
        total_chapters=1,
        owner_id=1,
    )
    db.add(novel)
    db.commit()
    db.refresh(novel)
    db.add(
        Chapter(
            novel_id=novel.id,
            chapter_number=1,
            title="One",
            content=("Alice met Bob in the city. " * 80),
        )
    )
    db.commit()
    return novel


def _create_initialized_novel_with_stale_index(db) -> Novel:
    novel = _create_novel_with_text(db)
    novel.window_index_revision = 2
    novel.window_index_built_revision = 1
    novel.window_index_status = "stale"
    db.add(
        BootstrapJob(
            novel_id=novel.id,
            mode="initial",
            initialized=True,
            status="completed",
            progress={"step": 5, "detail": "completed"},
            result={
                **build_bootstrap_trigger_result(mode="initial", user_id=1),
                "initialized": True,
            },
        )
    )
    db.commit()
    return novel


def test_bootstrap_forwards_byok_headers_to_background_job(client, db):
    novel = _create_novel_with_text(db)

    headers = {
        "x-llm-base-url": "https://example.com/v1",
        "x-llm-api-key": "test-key",
        "x-llm-model": "test-model",
    }
    response = client.post(
        f"/api/novels/{novel.id}/world/bootstrap",
        json={"mode": "initial"},
        headers=headers,
    )
    assert response.status_code == 202

    captured = client.app.state._bootstrap_task_capture
    assert captured["llm_config"] == _SELFHOST_LLM_CONFIG


def test_index_refresh_endpoint_does_not_require_llm_config(client, db):
    import app.config as config_mod

    novel = _create_initialized_novel_with_stale_index(db)

    previous_settings = config_mod._settings_instance
    config_mod._settings_instance = Settings(
        deploy_mode="selfhost",
        openai_base_url="",
        openai_api_key="",
        openai_model="",
        _env_file=None,
    )
    try:
        response = client.post(
            f"/api/novels/{novel.id}/world/bootstrap",
            json={"mode": "index_refresh"},
        )
    finally:
        config_mod._settings_instance = previous_settings

    assert response.status_code == 202
    assert response.json()["mode"] == "index_refresh"
    assert client.app.state._bootstrap_task_capture["llm_config"] is None


def test_desktop_index_refresh_endpoint_does_not_open_corrupt_config(
    client, db, monkeypatch, tmp_path
):
    import app.config as config_mod
    from app.core.world import bootstrap_application as bootstrap_app

    novel = _create_initialized_novel_with_stale_index(db)
    config_path = tmp_path / "llm-config.json"
    config_path.write_bytes(b"not-json")
    monkeypatch.setattr(
        config_mod,
        "_settings_instance",
        Settings(
            environment="desktop",
            deploy_mode="selfhost",
            novwr_desktop_llm_config_path=str(config_path),
            _env_file=None,
        ),
    )
    monkeypatch.setattr(
        bootstrap_app,
        "resolve_llm_config",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("resolver must not run")
        ),
    )

    response = client.post(
        f"/api/novels/{novel.id}/world/bootstrap",
        json={"mode": "index_refresh"},
    )

    assert response.status_code == 202
    assert response.json()["mode"] == "index_refresh"


def test_index_refresh_endpoint_rejects_incomplete_selfhost_override(client, db):
    novel = _create_initialized_novel_with_stale_index(db)

    response = client.post(
        f"/api/novels/{novel.id}/world/bootstrap",
        json={"mode": "index_refresh"},
        headers={"x-llm-api-key": "only-a-key"},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "llm_config_incomplete"


def test_index_refresh_endpoint_rejects_hosted_override(client, db, monkeypatch):
    import app.config as config_mod

    novel = _create_initialized_novel_with_stale_index(db)
    monkeypatch.setattr(
        config_mod,
        "_settings_instance",
        Settings(
            deploy_mode="hosted",
            hosted_llm_base_url="https://hosted.example/v1",
            hosted_llm_api_key="hosted-key",
            hosted_llm_model="hosted-model",
            _env_file=None,
        ),
    )

    response = client.post(
        f"/api/novels/{novel.id}/world/bootstrap",
        json={"mode": "index_refresh"},
        headers={
            "x-llm-base-url": "https://override.example/v1",
            "x-llm-api-key": "override-key",
            "x-llm-model": "override-model",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "hosted_byok_disabled"


def test_index_refresh_endpoint_rejects_desktop_override_before_store_read(
    client, db, monkeypatch, tmp_path
):
    import app.config as config_mod

    novel = _create_initialized_novel_with_stale_index(db)
    config_path = tmp_path / "llm-config.json"
    config_path.write_bytes(b"not-json")
    monkeypatch.setattr(
        config_mod,
        "_settings_instance",
        Settings(
            environment="desktop",
            deploy_mode="selfhost",
            novwr_desktop_llm_config_path=str(config_path),
            _env_file=None,
        ),
    )

    response = client.post(
        f"/api/novels/{novel.id}/world/bootstrap",
        json={"mode": "index_refresh"},
        headers={"x-llm-api-key": ""},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "desktop_llm_override_disabled"


def test_hosted_bootstrap_queues_for_worker_instead_of_launching_inline(client, db):
    import app.config as config_mod

    novel = _create_novel_with_text(db)

    prev = config_mod._settings_instance
    config_mod._settings_instance = Settings(
        deploy_mode="hosted",
        hosted_llm_base_url="https://hosted.example/v1",
        hosted_llm_api_key="hosted-key",
        hosted_llm_model="hosted-model",
        _env_file=None,
    )
    try:
        response = client.post(
            f"/api/novels/{novel.id}/world/bootstrap",
            json={"mode": "initial"},
        )
        assert response.status_code == 202
        assert client.app.state._bootstrap_task_capture == {}
    finally:
        config_mod._settings_instance = prev


def test_hosted_bootstrap_default_trigger_fast_fails_when_index_is_already_fresh(
    client, db
):
    import app.config as config_mod

    novel = _create_novel_with_text(db)
    novel.window_index_revision = 1
    novel.window_index_built_revision = 1
    novel.window_index_status = "fresh"
    job = BootstrapJob(
        novel_id=novel.id,
        mode="initial",
        initialized=True,
        status="completed",
        progress={"step": 4, "detail": "bootstrap completed"},
        result={
            **build_bootstrap_trigger_result(mode="initial", user_id=1),
            "initialized": True,
        },
    )
    db.add(job)
    db.commit()

    prev = config_mod._settings_instance
    config_mod._settings_instance = Settings(
        deploy_mode="hosted",
        hosted_llm_base_url="https://hosted.example/v1",
        hosted_llm_api_key="hosted-key",
        hosted_llm_model="hosted-model",
        _env_file=None,
    )
    try:
        response = client.post(f"/api/novels/{novel.id}/world/bootstrap")
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "bootstrap_index_already_fresh"
        assert client.app.state._bootstrap_task_capture == {}
    finally:
        config_mod._settings_instance = prev


def test_hosted_bootstrap_does_not_require_generation_quota(client, db):
    import app.config as config_mod

    novel = _create_novel_with_text(db)
    user = db.get(User, 1)
    assert user is not None
    user.generation_quota = 0
    db.commit()

    prev = config_mod._settings_instance
    config_mod._settings_instance = Settings(
        deploy_mode="hosted",
        hosted_llm_base_url="https://hosted.example/v1",
        hosted_llm_api_key="hosted-key",
        hosted_llm_model="hosted-model",
        _env_file=None,
    )
    try:
        response = client.post(
            f"/api/novels/{novel.id}/world/bootstrap",
            json={"mode": "initial"},
        )
        assert response.status_code == 202
        db.refresh(user)
        assert user.generation_quota == 0
    finally:
        config_mod._settings_instance = prev


def test_hosted_worker_claims_bootstrap_job_and_uses_trigger_user(db):
    from app.core.world import bootstrap_application as bootstrap_app

    novel = _create_novel_with_text(db)
    job = BootstrapJob(
        novel_id=novel.id,
        mode="initial",
        status="pending",
        progress={"step": 0, "detail": "queued"},
        result=build_bootstrap_trigger_result(mode="initial", user_id=7),
    )
    db.add(job)
    db.commit()
    db.refresh(job)

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

    did_work = bootstrap_app.run_next_bootstrap_job(
        session_factory=TestingSessionLocal,
        settings=Settings(
            deploy_mode="hosted",
            hosted_llm_base_url="https://hosted.example/v1",
            hosted_llm_api_key="hosted-key",
            hosted_llm_model="hosted-model",
            _env_file=None,
        ),
        background_job_runner=_runner,
    )

    assert did_work is True
    assert observed[0]["job_id"] == job.id
    assert observed[0]["user_id"] == 7
    assert observed[0]["llm_config"] == ResolvedLlmConfig(
        base_url="https://hosted.example/v1",
        api_key="hosted-key",
        model="hosted-model",
        billing_source_hint="hosted",
        source="hosted_settings",
    )


@pytest.mark.asyncio
async def test_desktop_trigger_queues_for_worker_without_inline_launcher(
    db, monkeypatch
):
    from app.core.world import bootstrap_application as bootstrap_app

    user = User(
        id=1,
        username="desktop-user",
        hashed_password="x",
        role="admin",
        is_active=True,
    )
    db.add(user)
    db.commit()
    novel = _create_novel_with_text(db)
    launched: list[dict] = []
    monkeypatch.setattr(
        bootstrap_app,
        "resolve_llm_config",
        lambda **_kwargs: _DESKTOP_LLM_CONFIG,
    )

    job = await bootstrap_app.trigger_bootstrap(
        novel.id,
        body=None,
        db=db,
        current_user=user,
        llm_override=LlmConfigValues(),
        settings=Settings(
            environment="desktop",
            deploy_mode="selfhost",
            novwr_desktop_llm_config_path="/tmp/llm-config.json",
            _env_file=None,
        ),
        launch_bootstrap_job_fn=lambda **kwargs: launched.append(kwargs),
    )

    assert job.status == "pending"
    assert launched == []


def test_desktop_worker_recovers_manual_pending_job_with_persisted_config(
    db, monkeypatch
):
    from app.core.world import bootstrap_application as bootstrap_app

    novel = _create_novel_with_text(db)
    job = BootstrapJob(
        novel_id=novel.id,
        mode="initial",
        status="pending",
        progress={"step": 0, "detail": "queued"},
        result=build_bootstrap_trigger_result(mode="initial", user_id=1),
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    resolved_settings: list[Settings] = []
    monkeypatch.setattr(
        bootstrap_app,
        "resolve_llm_config",
        lambda *, settings: resolved_settings.append(settings) or _DESKTOP_LLM_CONFIG,
    )
    observed: list[dict] = []

    async def _runner(job_id: int, **kwargs):
        observed.append({"job_id": job_id, **kwargs})

    settings = Settings(
        environment="desktop",
        deploy_mode="selfhost",
        novwr_desktop_llm_config_path="/tmp/llm-config.json",
        _env_file=None,
    )
    did_work = bootstrap_app.run_next_bootstrap_job(
        session_factory=TestingSessionLocal,
        settings=settings,
        background_job_runner=_runner,
    )

    assert did_work is True
    assert resolved_settings == [settings]
    assert observed[0]["job_id"] == job.id
    assert observed[0]["llm_config"] == _DESKTOP_LLM_CONFIG


def test_worker_does_not_resolve_llm_config_without_candidate_job(db, monkeypatch):
    from app.core.world import bootstrap_application as bootstrap_app

    monkeypatch.setattr(
        bootstrap_app,
        "resolve_llm_config",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("resolver must not run")
        ),
    )

    assert (
        bootstrap_app.run_next_bootstrap_job(
            session_factory=TestingSessionLocal,
            settings=Settings(deploy_mode="hosted", _env_file=None),
        )
        is False
    )


def test_worker_keeps_pending_job_when_config_is_missing(db, monkeypatch):
    from app.core.world import bootstrap_application as bootstrap_app

    novel = _create_novel_with_text(db)
    job = BootstrapJob(
        novel_id=novel.id,
        mode="initial",
        status="pending",
        progress={"step": 0, "detail": "queued"},
        result=build_bootstrap_trigger_result(mode="initial", user_id=1),
    )
    db.add(job)
    db.commit()
    monkeypatch.setattr(
        bootstrap_app,
        "resolve_llm_config",
        lambda **_kwargs: (_ for _ in ()).throw(
            LlmConfigError(code="llm_config_missing", message="missing")
        ),
    )

    assert (
        bootstrap_app.run_next_bootstrap_job(
            session_factory=TestingSessionLocal,
            settings=Settings(
                environment="desktop", deploy_mode="selfhost", _env_file=None
            ),
        )
        is False
    )
    db.refresh(job)
    assert job.status == "pending"


def test_worker_skips_ai_jobs_without_config_and_runs_later_index_refresh(
    db, monkeypatch
):
    from app.core.world import bootstrap_application as bootstrap_app

    first_ai_novel = _create_novel_with_text(db)
    second_ai_novel = _create_novel_with_text(db)
    refresh_novel = _create_novel_with_text(db)
    first_ai_job = BootstrapJob(
        novel_id=first_ai_novel.id,
        mode="initial",
        status="pending",
        progress={"step": 0, "detail": "queued"},
        result=build_bootstrap_trigger_result(mode="initial", user_id=1),
    )
    second_ai_job = BootstrapJob(
        novel_id=second_ai_novel.id,
        mode="initial",
        status="pending",
        progress={"step": 0, "detail": "queued"},
        result=build_bootstrap_trigger_result(mode="initial", user_id=1),
    )
    refresh_job = BootstrapJob(
        novel_id=refresh_novel.id,
        mode="index_refresh",
        status="pending",
        progress={"step": 0, "detail": "queued"},
        result=build_bootstrap_trigger_result(mode="index_refresh", user_id=1),
    )
    db.add_all([first_ai_job, second_ai_job, refresh_job])
    db.commit()
    resolve_calls = 0

    def _missing_config(**_kwargs):
        nonlocal resolve_calls
        resolve_calls += 1
        raise LlmConfigError(code="llm_config_missing", message="missing")

    monkeypatch.setattr(bootstrap_app, "resolve_llm_config", _missing_config)
    observed: list[dict] = []

    async def _runner(job_id: int, **kwargs):
        observed.append({"job_id": job_id, **kwargs})

    assert (
        bootstrap_app.run_next_bootstrap_job(
            session_factory=TestingSessionLocal,
            settings=Settings(
                environment="desktop", deploy_mode="selfhost", _env_file=None
            ),
            background_job_runner=_runner,
        )
        is True
    )
    assert resolve_calls == 1
    assert observed[0]["job_id"] == refresh_job.id
    assert observed[0]["llm_config"] is None
    db.refresh(first_ai_job)
    db.refresh(second_ai_job)
    assert first_ai_job.status == "pending"
    assert second_ai_job.status == "pending"


def test_worker_propagates_corrupt_desktop_config(db, monkeypatch):
    from app.core.world import bootstrap_application as bootstrap_app

    novel = _create_novel_with_text(db)
    refresh_novel = _create_novel_with_text(db)
    db.add_all(
        [
            BootstrapJob(
                novel_id=novel.id,
                mode="initial",
                status="pending",
                progress={"step": 0, "detail": "queued"},
                result=build_bootstrap_trigger_result(mode="initial", user_id=1),
            ),
            BootstrapJob(
                novel_id=refresh_novel.id,
                mode="index_refresh",
                status="pending",
                progress={"step": 0, "detail": "queued"},
                result=build_bootstrap_trigger_result(mode="index_refresh", user_id=1),
            ),
        ]
    )
    db.commit()
    monkeypatch.setattr(
        bootstrap_app,
        "resolve_llm_config",
        lambda **_kwargs: (_ for _ in ()).throw(
            LlmConfigError(
                code="desktop_llm_config_unreadable",
                message="unreadable",
                status_code=500,
            )
        ),
    )

    with pytest.raises(LlmConfigError) as exc_info:
        bootstrap_app.run_next_bootstrap_job(
            session_factory=TestingSessionLocal,
            settings=Settings(
                environment="desktop", deploy_mode="selfhost", _env_file=None
            ),
        )

    assert exc_info.value.code == "desktop_llm_config_unreadable"


def test_worker_canonicalizes_candidate_mode_before_config_resolution(db, monkeypatch):
    from app.core.world import bootstrap_application as bootstrap_app

    novel = _create_novel_with_text(db)
    job = BootstrapJob(
        novel_id=novel.id,
        mode="unknown",
        status="pending",
        progress={"step": 0, "detail": "queued"},
        result=build_bootstrap_trigger_result(mode="unknown", user_id=1),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    monkeypatch.setattr(
        bootstrap_app,
        "resolve_llm_config",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("resolver must not run")
        ),
    )
    observed: list[dict] = []

    async def _runner(job_id: int, **kwargs):
        observed.append({"job_id": job_id, **kwargs})

    assert (
        bootstrap_app.run_next_bootstrap_job(
            session_factory=TestingSessionLocal,
            settings=Settings(deploy_mode="hosted", _env_file=None),
            background_job_runner=_runner,
        )
        is True
    )
    assert observed[0]["job_id"] == job.id
    assert observed[0]["llm_config"] is None


def test_reextract_merge_endpoint_and_job_flow(client, db):
    novel = _create_novel_with_text(db)
    confirmed = WorldEntity(
        novel_id=novel.id,
        name="Alice",
        entity_type="Character",
        aliases=["Hero"],
        status="confirmed",
        origin="manual",
    )
    db.add(confirmed)
    db.commit()

    response = client.post(
        f"/api/novels/{novel.id}/world/bootstrap",
        json={"mode": "reextract", "draft_policy": "merge"},
    )
    assert response.status_code == 202
    body = response.json()
    assert body["mode"] == "reextract"
    assert body["result"]["index_refresh_only"] is False

    fake_client = _FakeAIClient(
        payload={
            "entities": [
                {"name": "Alice", "entity_type": "Item", "aliases": ["Changed Alias"]},
                {"name": "Bob", "entity_type": "Character", "aliases": ["B"]},
            ],
            "relationships": [
                {"source_name": "Alice", "target_name": "Bob", "label": "ally"}
            ],
        }
    )
    asyncio.run(
        run_bootstrap_job(
            body["job_id"],
            session_factory=TestingSessionLocal,
            client=fake_client,
            llm_config=_SELFHOST_LLM_CONFIG,
        )
    )

    status = client.get(f"/api/novels/{novel.id}/world/bootstrap/status")
    assert status.status_code == 200
    status_body = status.json()
    assert status_body["status"] == "completed"
    assert status_body["mode"] == "reextract"
    assert status_body["result"]["index_refresh_only"] is False

    db.expire_all()
    refreshed_confirmed = (
        db.query(WorldEntity).filter(WorldEntity.id == confirmed.id).first()
    )
    assert refreshed_confirmed.status == "confirmed"
    assert refreshed_confirmed.origin == "manual"
    assert refreshed_confirmed.entity_type == "Character"
    assert refreshed_confirmed.aliases == ["Hero"]

    bob = (
        db.query(WorldEntity)
        .filter(WorldEntity.novel_id == novel.id, WorldEntity.name == "Bob")
        .first()
    )
    assert bob is not None
    assert bob.status == "draft"
    assert bob.origin == "bootstrap"

    ally = (
        db.query(WorldRelationship)
        .filter(
            WorldRelationship.novel_id == novel.id, WorldRelationship.label == "ally"
        )
        .first()
    )
    assert ally is not None
    assert ally.status == "draft"
    assert ally.origin == "bootstrap"
    assert fake_client.calls == 1


def test_reextract_replace_force_cleans_bootstrap_drafts(client, db):
    novel = _create_novel_with_text(db)
    confirmed = WorldEntity(
        novel_id=novel.id,
        name="Alice",
        entity_type="Character",
        aliases=["Hero"],
        status="confirmed",
        origin="manual",
    )
    manual_draft = WorldEntity(
        novel_id=novel.id,
        name="ManualDraft",
        entity_type="Location",
        aliases=[],
        status="draft",
        origin="manual",
        created_at=datetime(2026, 2, 19, 0, 0, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 2, 19, 0, 0, 0, tzinfo=timezone.utc),
    )
    old_bootstrap = WorldEntity(
        novel_id=novel.id,
        name="OldBootstrapDraft",
        entity_type="Faction",
        aliases=["Old Alias"],
        status="draft",
        origin="bootstrap",
    )
    db.add_all([confirmed, manual_draft, old_bootstrap])
    db.commit()
    db.refresh(confirmed)
    db.refresh(manual_draft)
    db.refresh(old_bootstrap)

    db.add_all(
        [
            WorldRelationship(
                novel_id=novel.id,
                source_id=confirmed.id,
                target_id=old_bootstrap.id,
                label="old-bootstrap",
                status="draft",
                origin="bootstrap",
            ),
            WorldRelationship(
                novel_id=novel.id,
                source_id=confirmed.id,
                target_id=manual_draft.id,
                label="manual-link",
                status="draft",
                origin="manual",
            ),
        ]
    )
    db.commit()

    response = client.post(
        f"/api/novels/{novel.id}/world/bootstrap",
        json={
            "mode": "reextract",
            "draft_policy": "replace_bootstrap_drafts",
            "force": True,
        },
    )
    assert response.status_code == 202
    body = response.json()
    assert body["mode"] == "reextract"

    fake_client = _FakeAIClient(
        payload={
            "entities": [
                {"name": "Alice", "entity_type": "Item", "aliases": ["Changed Alias"]},
                {"name": "Bob", "entity_type": "Character", "aliases": ["B"]},
            ],
            "relationships": [
                {"source_name": "Alice", "target_name": "Bob", "label": "ally"}
            ],
        }
    )
    asyncio.run(
        run_bootstrap_job(
            body["job_id"],
            session_factory=TestingSessionLocal,
            client=fake_client,
            llm_config=_SELFHOST_LLM_CONFIG,
        )
    )

    status = client.get(f"/api/novels/{novel.id}/world/bootstrap/status")
    assert status.status_code == 200
    assert status.json()["status"] == "completed"

    db.expire_all()
    entities = db.query(WorldEntity).filter(WorldEntity.novel_id == novel.id).all()
    relationships = (
        db.query(WorldRelationship).filter(WorldRelationship.novel_id == novel.id).all()
    )
    entities_by_name = {entity.name: entity for entity in entities}
    labels = {relationship.label for relationship in relationships}

    assert "OldBootstrapDraft" not in entities_by_name
    assert "ManualDraft" in entities_by_name
    assert entities_by_name["Alice"].status == "confirmed"
    assert entities_by_name["Alice"].origin == "manual"
    assert entities_by_name["Alice"].entity_type == "Character"
    assert entities_by_name["Alice"].aliases == ["Hero"]
    assert entities_by_name["Bob"].status == "draft"
    assert entities_by_name["Bob"].origin == "bootstrap"

    assert "old-bootstrap" not in labels
    assert "manual-link" in labels
    assert "ally" in labels
    assert fake_client.calls == 1
