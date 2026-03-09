"""Unit tests for hosted safety fuse helpers."""

import app.config as config_mod
import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.core.safety_fuses import get_ai_unavailable_detail, get_total_estimated_ai_spend_usd
from app.database import Base
from app.models import TokenUsage


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


def test_hosted_spend_sum_excludes_byok_usage(db):
    db.add_all(
        [
            TokenUsage(
                user_id=1,
                model="gemini-3.0-flash",
                prompt_tokens=10,
                completion_tokens=10,
                total_tokens=20,
                cost_estimate=4.5,
                billing_source="byok",
                node_name="writer",
            ),
            TokenUsage(
                user_id=1,
                model="gemini-3.0-flash",
                prompt_tokens=10,
                completion_tokens=10,
                total_tokens=20,
                cost_estimate=0.75,
                billing_source="hosted",
                node_name="writer",
            ),
        ]
    )
    db.commit()

    assert get_total_estimated_ai_spend_usd(db) == pytest.approx(0.75)


def test_hosted_budget_hard_stop_is_skipped_for_byok_requests(db):
    prev = config_mod._settings_instance
    config_mod._settings_instance = Settings(deploy_mode="hosted", ai_hard_stop_usd=1.0, _env_file=None)
    try:
        db.add(
            TokenUsage(
                user_id=1,
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

        assert get_ai_unavailable_detail(db, billing_source="byok") is None
    finally:
        config_mod._settings_instance = prev


def test_hosted_manual_disable_still_blocks_byok_requests(db):
    prev = config_mod._settings_instance
    config_mod._settings_instance = Settings(deploy_mode="hosted", ai_manual_disable=True, _env_file=None)
    try:
        detail = get_ai_unavailable_detail(db, billing_source="byok")
        assert detail is not None
        assert detail["code"] == "ai_manually_disabled"
    finally:
        config_mod._settings_instance = prev
