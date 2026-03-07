"""Tests for transaction-neutral event recording."""

import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import reload_settings
from app.core.events import record_event
from app.database import Base
from app.models import Novel, User


@pytest.fixture()
def event_tracking_session(tmp_path):
    """DB session with ENABLE_EVENT_TRACKING enabled."""
    db_path = tmp_path / "events.db"

    orig_env = {}
    env_overrides = {
        "ENABLE_EVENT_TRACKING": "true",
        "JWT_SECRET_KEY": "test-secret-key",
    }
    for key, val in env_overrides.items():
        orig_env[key] = os.environ.get(key)
        os.environ[key] = val
    reload_settings()

    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        for key, orig_val in orig_env.items():
            if orig_val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = orig_val
        reload_settings()


def test_record_event_does_not_commit_caller_session(event_tracking_session):
    db = event_tracking_session

    user = User(username="u1", hashed_password="x")
    db.add(user)
    db.commit()
    db.refresh(user)

    # Add a novel but do NOT commit. If record_event() commits the caller session,
    # this novel will become persisted (bug).
    db.add(Novel(title="t", author="", file_path="f", owner_id=user.id))

    record_event(db, user.id, "signup")

    # Caller should still be able to rollback uncommitted work.
    db.rollback()

    # Verify the novel was not persisted.
    assert db.query(Novel).count() == 0
