"""Invariant gates for bootstrap workflow regressions."""

from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.config import Settings
from app.core.llm_config import LlmConfigValues
from app.models import (
    BootstrapJob,
    Chapter,
    Novel,
    User,
    WorldEntity,
    WorldRelationship,
)
from app.schemas import (
    BootstrapTriggerRequest,
    WorldAttributeCreate,
    WorldEntityUpdate,
    WorldRelationshipUpdate,
)


engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

_LLM_OVERRIDE = LlmConfigValues(
    base_url="https://example.com/v1",
    api_key="test-key",
    model="test-model",
    provided=True,
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
def world_api(monkeypatch):
    from app.api import world
    from app.api import world_bootstrap
    from app.core.world import bootstrap_application as bootstrap_app

    def _noop_launch_bootstrap_job(*args, **kwargs):
        return None

    monkeypatch.setattr(
        bootstrap_app, "launch_bootstrap_job", _noop_launch_bootstrap_job
    )
    monkeypatch.setattr(
        world_bootstrap,
        "get_settings",
        lambda: Settings(
            deploy_mode="selfhost",
            openai_base_url="",
            openai_api_key="",
            openai_model="",
            _env_file=None,
        ),
    )
    return world


@pytest.fixture
def user():
    return User(
        id=1, username="tester", hashed_password="x", role="admin", is_active=True
    )


@pytest.mark.asyncio
async def test_bi01_initial_still_allowed_after_index_refresh(world_api, db, user):
    novel = Novel(
        title="Invariant",
        author="Tester",
        file_path="/tmp/invariant.txt",
        total_chapters=1,
    )
    db.add(novel)
    db.commit()
    db.refresh(novel)

    db.add(
        Chapter(
            novel_id=novel.id, chapter_number=1, title="One", content="云澈看向远方。"
        )
    )
    job = BootstrapJob(
        novel_id=novel.id,
        mode="index_refresh",
        status="completed",
        initialized=False,
        progress={"step": 5, "detail": "completed"},
        result={
            "entities_found": 0,
            "relationships_found": 0,
            "index_refresh_only": True,
        },
    )
    db.add(job)
    novel.window_index = b"{}"
    db.commit()

    response = await world_api.trigger_bootstrap(
        novel_id=novel.id,
        llm_override=_LLM_OVERRIDE,
        body=BootstrapTriggerRequest(mode="initial"),
        db=db,
        current_user=user,
    )

    assert response.mode == "initial"
    assert response.status == "pending"


@pytest.mark.asyncio
async def test_index_refresh_without_headers_does_not_resolve_llm_config(
    world_api, db, user, monkeypatch
):
    from app.core.world import bootstrap_application as bootstrap_app

    novel = Novel(
        title="Index only",
        author="Tester",
        file_path="/tmp/index-only.txt",
        total_chapters=1,
    )
    db.add(novel)
    db.commit()
    db.refresh(novel)
    db.add(
        Chapter(
            novel_id=novel.id, chapter_number=1, title="One", content="Index this text."
        )
    )
    db.add(
        BootstrapJob(
            novel_id=novel.id,
            mode="initial",
            status="completed",
            initialized=True,
            progress={"step": 5, "detail": "completed"},
            result={"entities_found": 1, "relationships_found": 0},
        )
    )
    db.commit()
    monkeypatch.setattr(
        bootstrap_app,
        "resolve_llm_config",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("resolver must not run")
        ),
    )

    response = await world_api.trigger_bootstrap(
        novel_id=novel.id,
        llm_override=LlmConfigValues(),
        body=BootstrapTriggerRequest(mode="index_refresh"),
        db=db,
        current_user=user,
    )

    assert response.mode == "index_refresh"
    assert response.status == "pending"


@pytest.mark.asyncio
async def test_ai_bootstrap_mode_requires_llm_config(world_api, db, user, monkeypatch):
    from app.api import world_bootstrap

    novel = Novel(
        title="Needs AI",
        author="Tester",
        file_path="/tmp/needs-ai.txt",
        total_chapters=1,
    )
    db.add(novel)
    db.commit()
    db.refresh(novel)
    db.add(
        Chapter(
            novel_id=novel.id,
            chapter_number=1,
            title="One",
            content="Extract this text.",
        )
    )
    db.commit()
    monkeypatch.setattr(
        world_bootstrap,
        "get_settings",
        lambda: Settings(
            deploy_mode="selfhost",
            openai_base_url="",
            openai_api_key="",
            openai_model="",
            _env_file=None,
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        await world_api.trigger_bootstrap(
            novel_id=novel.id,
            llm_override=LlmConfigValues(),
            body=BootstrapTriggerRequest(mode="initial"),
            db=db,
            current_user=user,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "llm_config_missing"


def test_bi02_entity_edit_switches_origin_to_manual(world_api, db, user):
    novel = Novel(
        title="Invariant",
        author="Tester",
        file_path="/tmp/invariant.txt",
        total_chapters=0,
    )
    db.add(novel)
    db.commit()
    db.refresh(novel)

    entity = WorldEntity(
        novel_id=novel.id,
        name="千叶影儿",
        entity_type="Character",
        status="draft",
        origin="bootstrap",
        aliases=[],
    )
    db.add(entity)
    db.commit()
    db.refresh(entity)

    world_api.update_entity(
        novel_id=novel.id,
        entity_id=entity.id,
        body=WorldEntityUpdate(description="用户补充说明"),
        db=db,
        current_user=user,
    )
    db.refresh(entity)

    assert entity.origin == "manual"


def test_bi02_relationship_edit_switches_origin_to_manual(world_api, db, user):
    novel = Novel(
        title="Invariant",
        author="Tester",
        file_path="/tmp/invariant.txt",
        total_chapters=0,
    )
    db.add(novel)
    db.commit()
    db.refresh(novel)

    source = WorldEntity(
        novel_id=novel.id,
        name="云澈",
        entity_type="Character",
        status="confirmed",
        origin="manual",
        aliases=[],
    )
    target = WorldEntity(
        novel_id=novel.id,
        name="千叶影儿",
        entity_type="Character",
        status="draft",
        origin="bootstrap",
        aliases=[],
    )
    db.add_all([source, target])
    db.commit()
    db.refresh(source)
    db.refresh(target)

    relationship = WorldRelationship(
        novel_id=novel.id,
        source_id=source.id,
        target_id=target.id,
        label="主仆",
        status="draft",
        origin="bootstrap",
    )
    db.add(relationship)
    db.commit()
    db.refresh(relationship)

    world_api.update_relationship(
        novel_id=novel.id,
        relationship_id=relationship.id,
        body=WorldRelationshipUpdate(label="夫妻"),
        db=db,
        current_user=user,
    )
    db.refresh(relationship)

    assert relationship.origin == "manual"


def test_bi02_attribute_edit_switches_entity_origin_to_manual(world_api, db, user):
    novel = Novel(
        title="Invariant",
        author="Tester",
        file_path="/tmp/invariant.txt",
        total_chapters=0,
    )
    db.add(novel)
    db.commit()
    db.refresh(novel)

    entity = WorldEntity(
        novel_id=novel.id,
        name="云澈",
        entity_type="Character",
        status="draft",
        origin="bootstrap",
        aliases=[],
    )
    db.add(entity)
    db.commit()
    db.refresh(entity)

    world_api.add_attribute(
        novel_id=novel.id,
        entity_id=entity.id,
        body=WorldAttributeCreate(key="身份", surface="深渊魔主"),
        db=db,
        current_user=user,
    )
    db.refresh(entity)

    assert entity.origin == "manual"


@pytest.mark.asyncio
async def test_bi04_reextract_replace_blocks_ambiguous_legacy_drafts(
    world_api, db, user
):
    novel = Novel(
        title="Invariant",
        author="Tester",
        file_path="/tmp/invariant.txt",
        total_chapters=1,
    )
    db.add(novel)
    db.commit()
    db.refresh(novel)

    db.add(
        Chapter(
            novel_id=novel.id, chapter_number=1, title="One", content="云澈看向远方。"
        )
    )
    db.add(
        WorldEntity(
            novel_id=novel.id,
            name="LegacyDraft",
            entity_type="Character",
            status="draft",
            origin="manual",
            aliases=[],
            created_at=datetime(2026, 2, 17, 0, 0, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 2, 17, 0, 0, 0, tzinfo=timezone.utc),
        )
    )
    db.commit()

    with pytest.raises(HTTPException) as exc_info:
        await world_api.trigger_bootstrap(
            novel_id=novel.id,
            llm_override=_LLM_OVERRIDE,
            body=BootstrapTriggerRequest(
                mode="reextract", draft_policy="replace_bootstrap_drafts", force=True
            ),
            db=db,
            current_user=user,
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "bootstrap_legacy_ambiguity_conflict"
