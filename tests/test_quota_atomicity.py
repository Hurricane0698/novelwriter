"""
Atomicity regression tests for hosted quota deduction helpers.

These tests simulate "lost update" behavior by using two independent SQLAlchemy
sessions that both read the same User row before applying quota deductions.
"""

import pytest
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import User


engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


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


def test_decrement_quota_is_atomic_across_sessions(hosted_settings):
    from app.core.auth import decrement_quota

    Base.metadata.create_all(bind=engine)
    try:
        # Create a user with 2 quota.
        s0 = SessionLocal()
        user = User(username="u", hashed_password="x", role="admin", is_active=True, generation_quota=2)
        s0.add(user)
        s0.commit()
        s0.refresh(user)
        user_id = int(user.id)
        s0.close()

        # Two independent sessions both load the same row before decrementing.
        s1 = SessionLocal()
        s2 = SessionLocal()
        try:
            u1 = s1.query(User).filter(User.id == user_id).one()
            u2 = s2.query(User).filter(User.id == user_id).one()
            assert u1.generation_quota == 2
            assert u2.generation_quota == 2

            decrement_quota(s1, u1, count=1)
            decrement_quota(s2, u2, count=1)

            s1.refresh(u1)
            assert u1.generation_quota == 0
        finally:
            s1.close()
            s2.close()
    finally:
        Base.metadata.drop_all(bind=engine)

