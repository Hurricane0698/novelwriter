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


def test_open_quota_reservation_is_atomic_across_sessions(hosted_settings):
    import pytest as _pytest
    from fastapi import HTTPException

    from app.core.auth import open_quota_reservation
    from app.models import QuotaReservation

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

        # Two independent sessions both load the same row before reserving.
        s1 = SessionLocal()
        s2 = SessionLocal()
        try:
            u1 = s1.query(User).filter(User.id == user_id).one()
            u2 = s2.query(User).filter(User.id == user_id).one()
            assert u1.generation_quota == 2
            assert u2.generation_quota == 2

            r1 = open_quota_reservation(s1, user_id, count=1)
            r2 = open_quota_reservation(s2, user_id, count=1)
            assert r1 is not None and r2 is not None and r1 != r2

            s1.refresh(u1)
            assert u1.generation_quota == 0
            assert s1.query(QuotaReservation).filter(QuotaReservation.user_id == user_id).count() == 2

            # A third reserve past zero must fail without going negative.
            with _pytest.raises(HTTPException) as exc_info:
                open_quota_reservation(s2, user_id, count=1)
            assert exc_info.value.status_code == 429
            s1.refresh(u1)
            assert u1.generation_quota == 0
        finally:
            s1.close()
            s2.close()
    finally:
        Base.metadata.drop_all(bind=engine)
