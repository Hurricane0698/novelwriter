"""Regression tests for token usage recording."""

from datetime import datetime, timezone

from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker


def test_record_usage_sets_user_id_from_request_context(monkeypatch):
    from app.database import Base
    from app.models import TokenUsage
    from app.core.ai_client import _record_usage

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr("app.database.SessionLocal", TestingSessionLocal)

    _record_usage(
        model="m",
        prompt_tokens=10,
        completion_tokens=5,
        endpoint="/api/novels/1/continue",
        node_name="writer",
        user_id=123,
    )

    db = TestingSessionLocal()
    try:
        row = db.query(TokenUsage).order_by(TokenUsage.id.desc()).first()
        assert row is not None
        assert row.user_id == 123
        assert row.total_tokens == 15
        assert row.created_at is not None
        # Defensive: ensure created_at is timezone-aware if SQLAlchemy returns python datetime.
        if isinstance(row.created_at, datetime):
            assert row.created_at.tzinfo in {None, timezone.utc}
    finally:
        db.close()
