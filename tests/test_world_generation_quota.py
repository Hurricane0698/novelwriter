"""
Hosted quota regression tests for world generation:

POST /api/novels/{novel_id}/world/generate
"""

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.models import Novel, TokenUsage, User


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


@pytest.fixture(scope="function")
def hosted_settings(_force_selfhost_settings):  # ensure conftest runs first
    import app.config as config_mod
    from app.config import Settings

    prev = config_mod._settings_instance
    config_mod._settings_instance = Settings(deploy_mode="hosted", _env_file=None)
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
    from app.api import world
    from app.core.ai_client import LLMUnavailableError

    before = hosted_user.generation_quota

    mock = AsyncMock(side_effect=LLMUnavailableError("boom"))
    monkeypatch.setattr(world, "generate_world_drafts", mock)

    resp = client.post(f"/api/novels/{novel.id}/world/generate", json={"text": "这是一段足够长的世界观设定文本。"})
    assert resp.status_code == 503

    db.refresh(hosted_user)
    assert hosted_user.generation_quota == before


def test_generate_world_does_not_charge_quota_on_busy_semaphore_503(client, db, hosted_user, novel, monkeypatch):
    from app.api import world

    before = hosted_user.generation_quota

    async def _busy() -> None:
        raise HTTPException(status_code=503, detail="busy", headers={"Retry-After": "1"})

    monkeypatch.setattr(world, "acquire_llm_slot", _busy)

    resp = client.post(f"/api/novels/{novel.id}/world/generate", json={"text": "这是一段足够长的世界观设定文本。"})
    assert resp.status_code == 503

    db.refresh(hosted_user)
    assert hosted_user.generation_quota == before


def test_generate_world_charges_quota_on_success(client, db, hosted_user, novel, monkeypatch):
    from app.api import world
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
    monkeypatch.setattr(world, "generate_world_drafts", mock)

    resp = client.post(f"/api/novels/{novel.id}/world/generate", json={"text": "这是一段足够长的世界观设定文本。"})
    assert resp.status_code == 200

    db.refresh(hosted_user)
    assert hosted_user.generation_quota == before - 1


def test_generate_world_allows_byok_when_ai_budget_hard_stop_is_reached(client, db, hosted_user, novel, monkeypatch):
    import app.config as config_mod
    from app.api import world
    from app.config import Settings
    from app.schemas import WorldGenerateResponse

    prev = config_mod._settings_instance
    config_mod._settings_instance = Settings(deploy_mode="hosted", ai_hard_stop_usd=1.0, _env_file=None)
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
        monkeypatch.setattr(world, "generate_world_drafts", mock)

        resp = client.post(
            f"/api/novels/{novel.id}/world/generate",
            json={"text": "这是一段足够长的世界观设定文本。"},
            headers={
                "x-llm-base-url": "https://example.com/v1",
                "x-llm-api-key": "byok-key",
                "x-llm-model": "byok-model",
            },
        )
        assert resp.status_code == 200

        db.refresh(hosted_user)
        assert hosted_user.generation_quota == before - 1
    finally:
        config_mod._settings_instance = prev
