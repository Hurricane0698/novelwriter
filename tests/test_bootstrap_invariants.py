"""Invariant gates for bootstrap workflow regressions."""

from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import BootstrapJob, Chapter, Novel, User, WorldEntity, WorldRelationship
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


@pytest.mark.asyncio
async def test_bi01_initial_still_allowed_after_index_refresh(world_api, db, user):
    novel = Novel(title="Invariant", author="Tester", file_path="/tmp/invariant.txt", total_chapters=1)
    db.add(novel)
    db.commit()
    db.refresh(novel)

    db.add(Chapter(novel_id=novel.id, chapter_number=1, title="One", content="云澈看向远方。"))
    job = BootstrapJob(
        novel_id=novel.id,
        mode="index_refresh",
        status="completed",
        initialized=False,
        progress={"step": 5, "detail": "completed"},
        result={"entities_found": 0, "relationships_found": 0, "index_refresh_only": True},
    )
    db.add(job)
    novel.window_index = b"{}"
    db.commit()

    response = await world_api.trigger_bootstrap(
        novel_id=novel.id,
        body=BootstrapTriggerRequest(mode="initial"),
        db=db,
        current_user=user,
    )

    assert response.mode == "initial"
    assert response.status == "pending"


def test_bi02_entity_edit_switches_origin_to_manual(world_api, db, user):
    novel = Novel(title="Invariant", author="Tester", file_path="/tmp/invariant.txt", total_chapters=0)
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
    novel = Novel(title="Invariant", author="Tester", file_path="/tmp/invariant.txt", total_chapters=0)
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
    novel = Novel(title="Invariant", author="Tester", file_path="/tmp/invariant.txt", total_chapters=0)
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
async def test_bi04_reextract_replace_blocks_ambiguous_legacy_drafts(world_api, db, user):
    novel = Novel(title="Invariant", author="Tester", file_path="/tmp/invariant.txt", total_chapters=1)
    db.add(novel)
    db.commit()
    db.refresh(novel)

    db.add(Chapter(novel_id=novel.id, chapter_number=1, title="One", content="云澈看向远方。"))
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
            body=BootstrapTriggerRequest(mode="reextract", draft_policy="replace_bootstrap_drafts", force=True),
            db=db,
            current_user=user,
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "bootstrap_legacy_ambiguity_conflict"
