"""
Hosted quota regression tests for non-stream continue:

POST /api/novels/{novel_id}/continue
"""

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException
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
    from app.api import novels
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
    ctx = novels._ContinuationContext(
        recent_text="recent",
        world_context="",
        narrative_constraints="",
        debug_summary=ContinueDebugSummary(context_chapters=1),
        writer_ctx={},
        effective_context_chapters=1,
    )

    def fake_prepare(db_sess, novel_id, req, current_user):
        n = db_sess.query(Novel).filter(Novel.id == novel_id).first()
        novels._verify_novel_access(n, current_user)
        return ctx

    monkeypatch.setattr(novels, "_prepare_continuation_context", fake_prepare)
    monkeypatch.setattr(novels, "postcheck_continuation", lambda **kwargs: [])
    monkeypatch.setattr(novels, "record_event", lambda *args, **kwargs: None)

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

    monkeypatch.setattr(novels, "continue_novel", fake_continue_novel)

    with TestClient(test_app) as c:
        yield c
    test_app.dependency_overrides.clear()


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
    from app.api import novels

    before = hosted_user.generation_quota

    async def _busy() -> None:
        raise HTTPException(status_code=503, detail="busy", headers={"Retry-After": "1"})

    monkeypatch.setattr(novels, "acquire_llm_slot", _busy)

    resp = client.post(
        f"/api/novels/{novel.id}/continue",
        json={"num_versions": 1, "context_chapters": 1},
    )
    assert resp.status_code == 503

    db.refresh(hosted_user)
    assert hosted_user.generation_quota == before


def test_continue_rejects_when_ai_budget_hard_stop_is_reached(client, db, hosted_user, novel, monkeypatch):
    import app.config as config_mod
    from app.config import Settings

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


def test_continue_refunds_quota_on_generation_failure(client, db, hosted_user, novel, monkeypatch):
    from app.api import novels

    before = hosted_user.generation_quota

    mock = AsyncMock(side_effect=RuntimeError("boom"))
    monkeypatch.setattr(novels, "continue_novel", mock)

    resp = client.post(
        f"/api/novels/{novel.id}/continue",
        json={"num_versions": 1, "context_chapters": 1},
    )
    assert resp.status_code == 500

    db.refresh(hosted_user)
    assert hosted_user.generation_quota == before
