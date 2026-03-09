"""Hosted AI safety fuse tests for bootstrap endpoints."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.models import Chapter, Novel, TokenUsage, User


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
def client(db, monkeypatch):
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

    user = User(
        id=1,
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

    novel = Novel(
        title="测试小说",
        author="测试作者",
        file_path="/tmp/test.txt",
        total_chapters=1,
        owner_id=user.id,
    )
    db.add(novel)
    db.commit()
    db.refresh(novel)

    test_app.dependency_overrides[get_current_user_or_default] = lambda: user

    with TestClient(test_app) as c:
        yield c, db, user, novel
    test_app.dependency_overrides.clear()


def test_bootstrap_rejects_when_ai_budget_hard_stop_is_reached(client, monkeypatch):
    import app.config as config_mod
    from app.config import Settings

    c, db, user, novel = client

    prev = config_mod._settings_instance
    config_mod._settings_instance = Settings(deploy_mode="hosted", ai_hard_stop_usd=1.0, _env_file=None)
    try:
        db.add(
            TokenUsage(
                user_id=user.id,
                model="gemini-3.0-flash",
                prompt_tokens=10,
                completion_tokens=10,
                total_tokens=20,
                cost_estimate=1.0,
                billing_source="hosted",
                node_name="bootstrap",
            )
        )
        db.commit()

        before = user.generation_quota
        resp = c.post(f"/api/novels/{novel.id}/world/bootstrap", json={})
        assert resp.status_code == 503
        assert resp.json()["detail"]["code"] == "ai_budget_hard_stop"

        db.refresh(user)
        assert user.generation_quota == before
    finally:
        config_mod._settings_instance = prev


def test_bootstrap_allows_byok_when_ai_budget_hard_stop_is_reached(client, monkeypatch):
    import app.config as config_mod
    from app.api import world
    from app.config import Settings

    c, db, user, novel = client

    prev = config_mod._settings_instance
    config_mod._settings_instance = Settings(deploy_mode="hosted", ai_hard_stop_usd=1.0, _env_file=None)
    try:
        db.add(
            TokenUsage(
                user_id=user.id,
                model="gemini-3.0-flash",
                prompt_tokens=10,
                completion_tokens=10,
                total_tokens=20,
                cost_estimate=1.0,
                billing_source="hosted",
                node_name="bootstrap",
            )
        )
        db.add(
            Chapter(
                novel_id=novel.id,
                chapter_number=1,
                title="第一章",
                content="这里有可以启动 bootstrap 的正文。",
            )
        )
        db.commit()

        async def fake_run_bootstrap_job(*args, **kwargs):
            return None

        monkeypatch.setattr(world, "run_bootstrap_job", fake_run_bootstrap_job)

        before = user.generation_quota
        resp = c.post(
            f"/api/novels/{novel.id}/world/bootstrap",
            json={},
            headers={
                "x-llm-base-url": "https://example.com/v1",
                "x-llm-api-key": "byok-key",
                "x-llm-model": "byok-model",
            },
        )
        assert resp.status_code == 202

        db.refresh(user)
        assert user.generation_quota == before - 1
    finally:
        config_mod._settings_instance = prev
