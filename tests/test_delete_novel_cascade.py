"""
Regression: deleting a novel must clean up all novel-scoped data.

In SQLite, FK enforcement is often disabled by default. Without explicit cleanup
(or DB-level ON DELETE CASCADE), deleting a novel can leave orphan world-model rows.
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
import sqlalchemy as sa
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from app.core.auth import get_current_user_or_default
from app.database import Base, get_db
from app.models import (
    BootstrapJob,
    Chapter,
    Continuation,
    Exploration,
    ExplorationChapter,
    LoreEntry,
    LoreKey,
    Novel,
    Outline,
    User,
    WorldEntity,
    WorldEntityAttribute,
    WorldRelationship,
    WorldSystem,
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


def _make_app(db, *, user: User) -> FastAPI:
    from app.api import novels as novels_api

    app = FastAPI()
    app.include_router(novels_api.router)

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_or_default] = lambda: user
    return app


def test_delete_novel_cascades_to_world_and_explorations(db, tmp_path):
    user = User(id=1, username="u", hashed_password="x", role="admin", is_active=True)
    db.add(user)
    db.commit()

    # File that should be deleted with the novel.
    file_path = tmp_path / "novel.txt"
    file_path.write_text("hi", encoding="utf-8")

    novel = Novel(title="T", author="A", file_path=str(file_path), total_chapters=1, owner_id=user.id)
    db.add(novel)
    db.commit()
    db.refresh(novel)

    # ORM-cascaded tables.
    chapter = Chapter(novel_id=novel.id, chapter_number=1, title="c1", content="x")
    outline = Outline(novel_id=novel.id, chapter_start=1, chapter_end=1, outline_text="o")
    cont = Continuation(novel_id=novel.id, chapter_number=1, content="y")
    entry = LoreEntry(
        novel_id=novel.id,
        uid=str(uuid4()),
        title="l",
        content="z",
        entry_type="Character",
        token_budget=100,
        priority=10,
        enabled=True,
    )
    key = LoreKey(entry=entry, keyword="k", is_regex=False, case_sensitive=True)
    db.add_all([chapter, outline, cont, entry, key])

    # World model tables (NOT ORM-cascaded off Novel).
    e1 = WorldEntity(novel_id=novel.id, name="e1", entity_type="Character", description="", aliases=[])
    e2 = WorldEntity(novel_id=novel.id, name="e2", entity_type="Character", description="", aliases=[])
    db.add_all([e1, e2])
    db.commit()
    db.refresh(e1)
    db.refresh(e2)

    attr = WorldEntityAttribute(entity_id=e1.id, key="power", surface="10")
    rel = WorldRelationship(novel_id=novel.id, source_id=e1.id, target_id=e2.id, label="friend", description="")
    sys = WorldSystem(novel_id=novel.id, name="sys", display_type="hierarchy", description="", data={}, constraints=[])
    job = BootstrapJob(novel_id=novel.id, mode="initial", status="pending", initialized=False)
    db.add_all([attr, rel, sys, job])

    # Exploration tables (NOT ORM-cascaded off Novel).
    exp = Exploration(novel_id=novel.id, name="exp", description="", from_chapter=1, to_chapter=1)
    db.add(exp)
    db.commit()
    db.refresh(exp)
    exp_ch = ExplorationChapter(
        exploration_id=exp.id,
        chapter_number=1,
        title="x",
        content="y",
        sort_order=0,
    )
    db.add(exp_ch)
    db.commit()

    app = _make_app(db, user=user)

    with TestClient(app) as c:
        resp = c.delete(f"/api/novels/{novel.id}")
        assert resp.status_code == 204

    # Ensure the file is deleted.
    assert not Path(str(file_path)).exists()

    # Ensure all DB rows are deleted.
    db.expire_all()
    assert db.get(Novel, novel.id) is None

    assert db.query(Chapter).filter(Chapter.novel_id == novel.id).count() == 0
    assert db.query(Outline).filter(Outline.novel_id == novel.id).count() == 0
    assert db.query(Continuation).filter(Continuation.novel_id == novel.id).count() == 0
    assert db.query(LoreEntry).filter(LoreEntry.novel_id == novel.id).count() == 0
    # LoreKey rows should be gone when their entry is deleted.
    assert db.query(LoreKey).count() == 0

    assert db.query(WorldRelationship).filter(WorldRelationship.novel_id == novel.id).count() == 0
    assert db.query(WorldEntity).filter(WorldEntity.novel_id == novel.id).count() == 0
    assert db.query(WorldSystem).filter(WorldSystem.novel_id == novel.id).count() == 0
    assert db.query(BootstrapJob).filter(BootstrapJob.novel_id == novel.id).count() == 0

    assert db.query(Exploration).filter(Exploration.novel_id == novel.id).count() == 0
    assert db.query(ExplorationChapter).count() == 0


def test_delete_novel_does_not_delete_file_when_db_commit_fails(db, tmp_path):
    """
    Regression: deleting a novel must not delete the on-disk file before the DB commit succeeds.

    If the DB commit fails, the API should error and the file must remain.
    """
    user = User(id=1, username="u", hashed_password="x", role="admin", is_active=True)
    db.add(user)
    db.commit()

    file_path = tmp_path / "novel.txt"
    file_path.write_text("hi", encoding="utf-8")

    novel = Novel(title="T", author="A", file_path=str(file_path), total_chapters=1, owner_id=user.id)
    db.add(novel)
    db.commit()
    db.refresh(novel)

    def _boom_commit():
        raise RuntimeError("boom")

    # Only break the commit inside the delete endpoint (seed commits already done).
    db.commit = _boom_commit  # type: ignore[method-assign]

    app = _make_app(db, user=user)
    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.delete(f"/api/novels/{novel.id}")
        assert resp.status_code == 500

    assert file_path.exists()
    db.expire_all()
    assert db.get(Novel, novel.id) is not None


def test_delete_novel_best_effort_cleans_up_legacy_hierarchy_tables(db, tmp_path):
    """
    Regression: DBs upgraded from older versions may still have removed hierarchy tables.

    Deleting a novel should not crash on these tables (some don't have `novel_id`)
    and should clean up their rows so novel-scoped data doesn't linger.
    """
    # Create legacy tables that are intentionally NOT part of Base.metadata.
    # Keep schema minimal but aligned with the old migration contracts:
    # - character_epochs/character_moments don't have novel_id
    # - plot_threads/plot_beats don't have novel_id
    db.execute(
        sa.text(
            """
            CREATE TABLE character_arcs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                novel_id INTEGER NOT NULL
            )
            """
        )
    )
    db.execute(
        sa.text(
            """
            CREATE TABLE character_epochs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                arc_id INTEGER NOT NULL
            )
            """
        )
    )
    db.execute(
        sa.text(
            """
            CREATE TABLE character_moments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                epoch_id INTEGER NOT NULL
            )
            """
        )
    )

    db.execute(
        sa.text(
            """
            CREATE TABLE plot_arcs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                novel_id INTEGER NOT NULL
            )
            """
        )
    )
    db.execute(
        sa.text(
            """
            CREATE TABLE plot_threads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                arc_id INTEGER NOT NULL
            )
            """
        )
    )
    db.execute(
        sa.text(
            """
            CREATE TABLE plot_beats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_id INTEGER NOT NULL
            )
            """
        )
    )
    db.commit()

    user = User(id=1, username="u", hashed_password="x", role="admin", is_active=True)
    db.add(user)
    db.commit()

    file_path = tmp_path / "novel.txt"
    file_path.write_text("hi", encoding="utf-8")

    novel = Novel(title="T", author="A", file_path=str(file_path), total_chapters=1, owner_id=user.id)
    db.add(novel)
    db.commit()
    db.refresh(novel)

    # Seed legacy rows for this novel.
    arc_id = db.execute(
        sa.text("INSERT INTO character_arcs (novel_id) VALUES (:novel_id)"),
        {"novel_id": novel.id},
    ).lastrowid
    epoch_id = db.execute(
        sa.text("INSERT INTO character_epochs (arc_id) VALUES (:arc_id)"),
        {"arc_id": arc_id},
    ).lastrowid
    db.execute(
        sa.text("INSERT INTO character_moments (epoch_id) VALUES (:epoch_id)"),
        {"epoch_id": epoch_id},
    )

    plot_arc_id = db.execute(
        sa.text("INSERT INTO plot_arcs (novel_id) VALUES (:novel_id)"),
        {"novel_id": novel.id},
    ).lastrowid
    plot_thread_id = db.execute(
        sa.text("INSERT INTO plot_threads (arc_id) VALUES (:arc_id)"),
        {"arc_id": plot_arc_id},
    ).lastrowid
    db.execute(
        sa.text("INSERT INTO plot_beats (thread_id) VALUES (:thread_id)"),
        {"thread_id": plot_thread_id},
    )
    db.commit()

    app = _make_app(db, user=user)

    try:
        with TestClient(app) as c:
            resp = c.delete(f"/api/novels/{novel.id}")
            assert resp.status_code == 204

        assert not Path(str(file_path)).exists()

        # Verify legacy tables are cleaned (no novel_id on some tables, so check emptiness).
        assert db.execute(sa.text("SELECT COUNT(*) FROM character_moments")).scalar_one() == 0
        assert db.execute(sa.text("SELECT COUNT(*) FROM character_epochs")).scalar_one() == 0
        assert db.execute(sa.text("SELECT COUNT(*) FROM character_arcs")).scalar_one() == 0

        assert db.execute(sa.text("SELECT COUNT(*) FROM plot_beats")).scalar_one() == 0
        assert db.execute(sa.text("SELECT COUNT(*) FROM plot_threads")).scalar_one() == 0
        assert db.execute(sa.text("SELECT COUNT(*) FROM plot_arcs")).scalar_one() == 0
    finally:
        # Ensure isolation: Base.metadata.drop_all() doesn't know about these tables.
        db.execute(sa.text("DROP TABLE IF EXISTS character_moments"))
        db.execute(sa.text("DROP TABLE IF EXISTS character_epochs"))
        db.execute(sa.text("DROP TABLE IF EXISTS character_arcs"))
        db.execute(sa.text("DROP TABLE IF EXISTS plot_beats"))
        db.execute(sa.text("DROP TABLE IF EXISTS plot_threads"))
        db.execute(sa.text("DROP TABLE IF EXISTS plot_arcs"))
        db.commit()
