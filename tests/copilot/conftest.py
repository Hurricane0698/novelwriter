# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""Copilot backend workflow tests.

Tests verify user workflows and product contracts, not code paths:
  - evidence sourced from backend, not model invention
  - suggestion compilation validates against live world state
  - apply IS the approval boundary (confirmed, not draft)
  - draft_cleanup only targets draft rows
  - stale targets don't block other suggestions
  - session/run scoping is strict (user + novel)
  - inquiry-only runs are normal results
  - multilingual targeting safety
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import Base, get_db
from app.models import (
    Chapter,
    Novel,
    User,
    WorldEntity,
    WorldEntityAttribute,
    WorldRelationship,
    WorldSystem,
)
from tests.copilot.runtime_support import TestingSessionLocal, engine


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
    config_mod._settings_instance = Settings(
        deploy_mode="hosted",
        hosted_llm_base_url="https://hosted.example/v1",
        hosted_llm_api_key="hosted-key",
        hosted_llm_model="hosted-model",
        _env_file=None,
    )
    try:
        yield
    finally:
        config_mod._settings_instance = prev


@pytest.fixture
def novel(db):
    n = Novel(title="测试小说", author="测试", file_path="/tmp/t.txt", total_chapters=3, language="zh")
    db.add(n)
    db.commit()
    db.refresh(n)
    return n


@pytest.fixture
def hosted_user(db, hosted_settings):
    user = User(
        username="hosted_copilot_user",
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
def chapters(db, novel):
    chs = []
    for i in range(1, 4):
        ch = Chapter(novel_id=novel.id, chapter_number=i, title=f"第{i}章", content=f"这是第{i}章的内容。主角张三在宗门修行。")
        db.add(ch)
        chs.append(ch)
    db.commit()
    for ch in chs:
        db.refresh(ch)
    return chs


@pytest.fixture
def entities(db, novel):
    e1 = WorldEntity(novel_id=novel.id, name="张三", entity_type="Character", description="主角", aliases=["三哥"], status="confirmed", origin="manual")
    e2 = WorldEntity(novel_id=novel.id, name="李四", entity_type="Character", description="反派", aliases=[], status="confirmed", origin="manual")
    e3 = WorldEntity(novel_id=novel.id, name="王五", entity_type="Character", description="", aliases=[], status="draft", origin="bootstrap")
    db.add_all([e1, e2, e3])
    db.commit()
    for e in [e1, e2, e3]:
        db.refresh(e)
    return [e1, e2, e3]


@pytest.fixture
def attributes(db, entities):
    a = WorldEntityAttribute(entity_id=entities[0].id, key="境界", surface="金丹期", visibility="active", origin="manual")
    db.add(a)
    db.commit()
    db.refresh(a)
    return [a]


@pytest.fixture
def relationships(db, novel, entities):
    r = WorldRelationship(
        novel_id=novel.id, source_id=entities[0].id, target_id=entities[1].id,
        label="对手", label_canonical="对手", description="宿敌", status="confirmed", origin="manual",
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return [r]


@pytest.fixture
def systems(db, novel):
    s = WorldSystem(novel_id=novel.id, name="修行体系", display_type="hierarchy", description="宗门修行等级", constraints=["每阶需要突破"], status="confirmed", origin="manual")
    db.add(s)
    db.commit()
    db.refresh(s)
    return [s]


@pytest.fixture
def client(db):
    from app.api import copilot as copilot_api, world
    from app.core.llm_config import ResolvedLlmConfig
    from app.core.llm_request import get_llm_config

    test_app = FastAPI()
    test_app.include_router(copilot_api.router)
    test_app.include_router(world.router)

    def override_get_db():
        try:
            yield db
        finally:
            pass

    test_app.dependency_overrides[get_db] = override_get_db
    from app.core.auth import check_generation_quota, get_current_user, get_current_user_or_default
    fake_user = User(id=1, username="testuser", hashed_password="x", role="admin", is_active=True, generation_quota=999)
    test_app.dependency_overrides[get_current_user] = lambda: fake_user
    test_app.dependency_overrides[get_current_user_or_default] = lambda: fake_user
    test_app.dependency_overrides[check_generation_quota] = lambda: fake_user
    test_app.dependency_overrides[get_llm_config] = lambda: ResolvedLlmConfig(
        base_url="https://example.com/v1",
        api_key="key",
        model="model",
        billing_source_hint="selfhost",
        source="selfhost_settings",
    )

    with TestClient(test_app) as c:
        yield c
    test_app.dependency_overrides.clear()


@pytest.fixture
def hosted_client(db, hosted_user, monkeypatch):
    import app.core.auth as auth_core
    from app.api import copilot as copilot_api, world
    from app.core.auth import get_current_user, get_current_user_or_default
    from app.core.llm_config import ResolvedLlmConfig
    from app.core.llm_request import get_llm_config

    test_app = FastAPI()
    test_app.include_router(copilot_api.router)
    test_app.include_router(world.router)

    def override_get_db():
        try:
            yield db
        finally:
            pass

    test_app.dependency_overrides[get_db] = override_get_db
    test_app.dependency_overrides[get_current_user] = lambda: hosted_user
    test_app.dependency_overrides[get_current_user_or_default] = lambda: hosted_user
    test_app.dependency_overrides[get_llm_config] = lambda: ResolvedLlmConfig(
        base_url="https://hosted.example/v1",
        api_key="hosted-key",
        model="hosted-model",
        billing_source_hint="hosted",
        source="hosted_settings",
    )
    monkeypatch.setattr(auth_core, "ensure_ai_available", lambda *args, **kwargs: None)

    with TestClient(test_app) as c:
        yield c
    test_app.dependency_overrides.clear()
